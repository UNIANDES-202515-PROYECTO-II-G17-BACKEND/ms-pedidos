import base64
import json
from unittest.mock import MagicMock

import pytest
from uuid import uuid4

@pytest.mark.asyncio
async def test_pubsub_pedido_recibido_ok(client, monkeypatch):
    # Importamos el módulo de la ruta para poder parchear dentro de él
    import src.routes.pubsub as pedido_router

    # Fake session_for_schema que solo guarda el country y entrega un "session" dummy
    captured = {}
    class DummyCtx:
        def __init__(self, country):
            self.country = country
        def __enter__(self):
            captured["country"] = self.country
            return MagicMock(name="Session")
        def __exit__(self, exc_type, exc, tb):
            pass

    def fake_session_for_schema(country):
        return DummyCtx(country)

    monkeypatch.setattr(pedido_router, "session_for_schema", fake_session_for_schema)

    # Fake PedidosService que podamos inspeccionar
    svc_mock = MagicMock()
    monkeypatch.setattr(pedido_router, "PedidosService", lambda session: svc_mock)

    pedido_id = str(uuid4())
    payload = {
        "event": "pedido_recibido",
        "pedido_id": pedido_id,
        "ctx": {"country": "co", "user_id": 123},
    }
    data = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    envelope = {"message": {"data": data}}

    r = await client.post("/pubsub", json=envelope)
    assert r.status_code == 204

    # Se usó el country correcto
    assert captured["country"] == "co"
    # Se llamó al método adecuado
    svc_mock.marcar_recibido.assert_called_once_with(
        pedido_id,
        x_country="co",
        ctx=payload["ctx"],
    )

async def test_pubsub_evento_no_manejado(client, monkeypatch):
    import src.routes.pedido as pedido_router

    # Evitar que intente hablar con la base
    class DummyCtx:
        def __enter__(self): return MagicMock(name="Session")
        def __exit__(self, exc_type, exc, tb): pass
    monkeypatch.setattr(pedido_router, "session_for_schema", lambda country: DummyCtx())
    svc_mock = MagicMock()
    monkeypatch.setattr(pedido_router, "PedidosService", lambda s: svc_mock)

    payload = {
        "event": "evento_raro",
        "pedido_id": str(uuid4()),
        "ctx": {"country": "co"},
    }
    data = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    envelope = {"message": {"data": data}}

    r = await client.post("/pubsub", json=envelope)
    assert r.status_code == 204

    # No se llamó a ningún método del servicio
    assert not svc_mock.method_calls

@pytest.mark.asyncio
async def test_pubsub_sin_message(client):
    r = await client.post("/pubsub", json={})
    assert r.status_code == 204

@pytest.mark.asyncio
async def test_pubsub_data_invalida(client):
    envelope = {"message": {"data": "%%%no-es-base64%%%"}}
    r = await client.post("/pubsub", json=envelope)
    assert r.status_code == 204