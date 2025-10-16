import pytest
from httpx import AsyncClient
from unittest.mock import MagicMock, patch
from fastapi.middleware.cors import CORSMiddleware
import importlib

@pytest.mark.asyncio
async def test_app_lifespan_success(client: AsyncClient):
    """Test that the lifespan function executes successfully on app startup."""
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_app_middleware_configured(app_instance_factory):
    """Test that CORS middleware is configured."""
    app_factory_app, _, _, _ = app_instance_factory(lifespan_error=False)
    middleware_types = [mw.cls for mw in app_factory_app.user_middleware]
    assert CORSMiddleware in middleware_types

@pytest.mark.asyncio
async def test_app_routers_included(app_instance_factory):
    """Test that health and pedido routers are included."""
    app_factory_app, _, _, _ = app_instance_factory(lifespan_error=False)
    paths = [route.path for route in app_factory_app.routes]
    assert "/health" in paths
    assert "/v1/pedidos" in paths
