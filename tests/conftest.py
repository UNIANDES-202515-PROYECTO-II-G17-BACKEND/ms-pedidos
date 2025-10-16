import logging
import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport

# -------------------------------------------------
# Silenciar logs
# -------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def disable_logging():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)

# -------------------------------------------------
# Mocks básicos
# -------------------------------------------------
@pytest.fixture(scope="function")
def mock_session():
    """Mock de Session: nunca toca DB."""
    sess = MagicMock()
    # Métodos no-op
    sess.add.return_value = None
    sess.flush.return_value = None
    sess.commit.return_value = None
    sess.rollback.return_value = None
    sess.refresh.return_value = None
    # Lo más importante: comportarse como context manager (por si acaso)
    sess.__enter__.return_value = sess
    sess.__exit__.return_value = None
    return sess

@pytest.fixture(scope="function")
def mock_svc():
    """Mock del servicio PedidosService que se inyecta en el router."""
    return MagicMock()

# -------------------------------------------------
# Client HTTP sin DB real
# -------------------------------------------------
@pytest.fixture(scope="function")
async def client(mock_session, mock_svc):
    """
    - Overridea get_session con un mock (app.dependency_overrides)
    - Parchea src.routes.pedido.svc para devolver mock_svc
    - Parchea cualquier cosa de startup que toque DB
    - Devuelve AsyncClient con ASGITransport
    """
    # Importar aquí para que los parches afecten desde antes del startup
    from src.app import app
    from src.dependencies import get_session

    # 1) Override de dependencia (¡la clave!)
    app.dependency_overrides[get_session] = lambda: mock_session

    # 2) Parchar el factory del servicio en el router
    svc_patcher = patch("src.routes.pedido.svc", return_value=mock_svc)

    # 3) Evitar toques a DB en startup (ajusta según tu app si no hace nada de DB en startup puedes omitir)
    create_all_patcher = patch("src.domain.models.Base.metadata.create_all", return_value=None)
    inspect_patcher = patch("sqlalchemy.inspect", return_value=MagicMock())
    engine_patcher = patch("src.infrastructure.infrastructure.engine")  # evita .connect/.begin reales

    with svc_patcher, create_all_patcher, inspect_patcher, engine_patcher:
        # Startup / Shutdown manuales
        await app.router.startup()
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac
        finally:
            # Limpieza
            await app.router.shutdown()
            app.dependency_overrides.clear()
