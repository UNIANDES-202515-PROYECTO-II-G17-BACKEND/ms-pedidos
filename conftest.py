import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.domain.models import Base
from src.dependencies import get_session
from src.app import app
from unittest.mock import MagicMock

# Setup an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(name="test_engine")
def test_engine_fixture():
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="test_session")
def test_session_fixture(test_engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture(name="mock_get_session")
def mock_get_session_fixture(test_session):
    # Override the get_session dependency to use the test_session
    # This mock is specifically for the API tests that use the client fixture
    def override_get_session():
        yield test_session
    app.dependency_overrides[get_session] = override_get_session
    yield test_session
    app.dependency_overrides.clear() # Clear overrides after test

@pytest.fixture(name="client")
async def client_fixture(mock_get_session): # Depends on mock_get_session to ensure dependency is overridden
    from httpx import AsyncClient
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest.fixture
def mock_pedido_service():
    # This fixture is for mocking the service layer, not the DB directly
    return MagicMock()

# Ensure that the app's get_session dependency is overridden for all API tests
# This is handled by the client_fixture which depends on mock_get_session
