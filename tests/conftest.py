# tests/conftest.py
import logging
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import MagicMock, patch
from uuid import uuid4

# --- Silenciar logs en la suite ---
@pytest.fixture(scope="session", autouse=True)
def disable_logging():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)

# Intentamos importar LifespanManager desde asgi-lifespan
try:
    from asgi_lifespan import LifespanManager
except ImportError:
    LifespanManager = None

@pytest.fixture(name="client")
async def client_fixture(override_get_session=None, override_lifespan=None):
    from src.app import app  # importa la app tras aplicar overrides/patches

    if LifespanManager is None:
        # Fallback manual si no está instalada asgi-lifespan
        await app.router.startup()
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield client
        finally:
            await app.router.shutdown()
    else:
        # Con LifespanManager se corre startup/shutdown de FastAPI
        async with LifespanManager(app):
            transport = ASGITransport(app=app)  # sin lifespan=
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield client


# --- Session falsa (NO DB) ---
@pytest.fixture(scope="function")
def mock_db_session():
    """
    Devuelve un MagicMock que simula Session de SQLAlchemy sin tocar DB.
    - Autoasigna UUIDs a objetos con atributo id cuando se hace add()
    - Configura chaining para .query() en los casos comunes
    """
    mock_session = MagicMock()

    # Asignar id si falta, para evitar FlushError en objetos nuevos simulados
    def add_side_effect(obj):
        if hasattr(obj, "id") and getattr(obj, "id") in (None, "", 0):
            setattr(obj, "id", uuid4())
        return None

    mock_session.add.side_effect = add_side_effect
    mock_session.flush.return_value = None
    mock_session.commit.return_value = None
    mock_session.rollback.return_value = None
    mock_session.refresh.side_effect = lambda x: x

    # Cadena típica para listar: query().filter(...).order_by(...).offset(...).limit(...).all()
    q = mock_session.query.return_value
    q.filter.return_value = q
    q.order_by.return_value = q
    q.offset.return_value = q
    q.limit.return_value = q
    q.all.return_value = []      # puedes sobreescribir en cada test según necesites
    q.first.return_value = None  # para obtener uno

    # Para get(...)
    mock_session.get.return_value = None

    return mock_session

# --- App FastAPI con dependencias parchadas ---
@pytest.fixture(scope="function")
async def app_instance(mock_db_session):
    """
    Crea la app pero:
      - parchea engine e inspect para que NUNCA pegue a DB
      - hace no-op de Base.metadata.create_all()
      - override de get_session para usar mock_db_session
    """
    # Parches de infra y metadata ANTES de importar la app
    with (
        patch("src.infrastructure.infrastructure.engine") as mock_engine,
        patch("src.domain.models.Base.metadata.create_all") as mock_create_all,
        patch("sqlalchemy.inspect") as mock_inspect,
    ):
        mock_engine.execution_options.return_value = mock_engine
        mock_engine.connect.return_value.__enter__.return_value = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = MagicMock()
        mock_create_all.return_value = None
        mock_inspect.return_value.get_table_names.return_value = ["fake_table"]

        from src.app import app as fastapi_app
        from src.dependencies import get_session as real_get_session

        def _override_get_session():
            yield mock_db_session

        fastapi_app.dependency_overrides[real_get_session] = _override_get_session
        yield fastapi_app

        fastapi_app.dependency_overrides.clear()
