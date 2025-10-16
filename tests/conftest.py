import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import MagicMock, patch
from src.domain import models # Import models to access Base.metadata
from src.infrastructure import infrastructure
import logging
from uuid import uuid4
from decimal import Decimal

@pytest.fixture(scope="session", autouse=True)
def disable_logging():
    """Fixture to disable logging during tests."""
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)

@pytest.fixture(scope="function")
async def app_instance_factory():
    """
    Factory fixture to create a FastAPI app instance with specific patches applied
    before the app is initialized, useful for lifespan tests.
    Yields (app, mock_create_all, mock_log_instance, mock_inspect).
    """
    def _factory(lifespan_error=False):
        mock_create_all = MagicMock()
        mock_log_instance = MagicMock() # Mock for the logger instance
        mock_inspect = MagicMock()

        # Default behavior for mocks (success scenario)
        mock_create_all.return_value = None
        mock_inspector_instance = MagicMock()
        mock_inspector_instance.get_table_names.return_value = ["mock_table_1", "mock_table_2"]
        mock_inspect.return_value = mock_inspector_instance

        if lifespan_error:
            mock_create_all.side_effect = Exception("Database connection error during lifespan")
            mock_inspector_instance.get_table_names.return_value = [] # No tables created

        with (
            patch('src.infrastructure.infrastructure.engine') as mock_engine,
            patch('src.domain.models.Base.metadata.create_all', new=mock_create_all), # Corrected patch target
            patch('sqlalchemy.inspect', new=mock_inspect),
            patch('logging.getLogger') as mock_get_logger # Patch logging.getLogger
        ):
            # Configure mock_get_logger to return our mock_log_instance for src.app's logger
            def get_logger_side_effect(name):
                if name == 'src.app':
                    return mock_log_instance
                return logging.getLogger(name) # Return real logger for others
            mock_get_logger.side_effect = get_logger_side_effect

            # Configure the mock engine for success
            mock_engine.execution_options.return_value = mock_engine
            mock_engine.connect.return_value.__aenter__.return_value = MagicMock()
            mock_engine.begin.return_value.__aenter__.return_value = MagicMock()

            # Import app here to ensure it's created after patches are applied
            from src.app import app as fastapi_app
            return fastapi_app, mock_create_all, mock_log_instance, mock_inspect
    yield _factory

@pytest.fixture(scope="function")
async def app_transport(app_instance_factory):
    """Fixture to provide an ASGITransport for the FastAPI app (success scenario)."""
    fastapi_app, _, _, _ = app_instance_factory(lifespan_error=False)
    return ASGITransport(app=fastapi_app)

@pytest.fixture(scope="function")
async def client(app_transport):
    """
    Fixture that provides a test client for the FastAPI application (success scenario).
    """
    async with AsyncClient(transport=app_transport, base_url="http://test") as ac:
        yield ac

@pytest.fixture(scope="function")
async def app_transport_lifespan_error(app_instance_factory):
    """
    Fixture to provide an ASGITransport for the FastAPI app (lifespan error scenario).
    Yields (transport, mock_create_all, mock_log_instance, mock_inspect).
    """
    fastapi_app, mock_create_all, mock_log_instance, mock_inspect = app_instance_factory(lifespan_error=True)
    transport = ASGITransport(app=fastapi_app)
    yield transport, mock_create_all, mock_log_instance, mock_inspect

@pytest.fixture(scope="function")
async def client_with_lifespan_error(app_transport_lifespan_error):
    """
    Fixture that provides a test client for the FastAPI application (lifespan error scenario).
    Yields (client, mock_create_all, mock_log_instance, mock_inspect).
    """
    transport, mock_create_all, mock_log_instance, mock_inspect = app_transport_lifespan_error
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, mock_create_all, mock_log_instance, mock_inspect

@pytest.fixture
def mock_get_session():
    mock_session = MagicMock()
    # Configure mock_session to prevent FlushError
    def add_side_effect(obj):
        if hasattr(obj, 'id') and getattr(obj, 'id', None) is None:
            # Assign a UUID to simulate auto-generated primary key
            setattr(obj, 'id', uuid4())
        return None

    mock_session.add.side_effect = add_side_effect
    mock_session.flush.return_value = None
    mock_session.commit.return_value = None
    mock_session.rollback.return_value = None
    mock_session.refresh.return_value = None
    # Mock query methods for PedidosService.obtener and listar
    mock_session.query.return_value.filter.return_value.first.return_value = None # Default for .obtener
    mock_session.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [] # Default for .listar

    # Mock the context manager behavior for the session
    mock_session.__enter__.return_value = mock_session
    mock_session.__exit__.return_value = None

    with patch("src.dependencies.get_session", return_value=mock_session):
        yield mock_session

@pytest.fixture(autouse=True, scope="function") # Make it autouse and function scope
def mock_pedido_service():
    # Patch the svc function where it's defined in the router
    mock_instance = MagicMock()
    with patch("src.routes.pedido.svc", return_value=mock_instance):
        yield mock_instance
