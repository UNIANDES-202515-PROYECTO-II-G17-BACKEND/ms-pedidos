# tests/test_pedidos_router.py
import base64
import json
from unittest.mock import MagicMock

import pytest
from uuid import uuid4
from decimal import Decimal
from datetime import date
from src.domain import schemas

# -------------------------
# Helpers para fabricar respuestas válidas
# -------------------------
def make_pedido_out_venta(estado="aprobado"):
    return schemas.PedidoOut(
        id=uuid4(),
        codigo=f"SO-{uuid4().hex[:6].upper()}",
        tipo="VENTA",
        estado=estado,
        cliente_id=123,
        vendedor_id=456,
        bodega_origen_id=uuid4(),
        items=[
            schemas.ItemIn(
                producto_id=uuid4(),
                cantidad=1,
                precio_unitario=Decimal("10.0"),
            )
        ],
        subtotal=Decimal("10.0"),
        impuesto_total=Decimal("0.0"),
        total=Decimal("10.0"),
        fecha_compromiso=date.today(),  # ← NUEVO
    )

def make_pedido_out_compra(estado="aprobado"):
    return schemas.PedidoOut(
        id=uuid4(),
        codigo=f"PO-{uuid4().hex[:6].upper()}",
        tipo="COMPRA",
        estado=estado,
        proveedor_id=uuid4(),
        bodega_destino_id=uuid4(),
        items=[
            schemas.ItemIn(
                producto_id=uuid4(),
                cantidad=2,
                precio_unitario=Decimal("5.0"),
            )
        ],
        subtotal=Decimal("10.0"),
        impuesto_total=Decimal("0.0"),
        total=Decimal("10.0"),
        fecha_compromiso=date.today(),  # ← NUEVO
    )

# -------------------------
# Tests de endpoints
# -------------------------

@pytest.mark.asyncio
async def test_crear_pedido_success(client, mock_svc):
    mock_svc.crear.return_value = make_pedido_out_venta("aprobado")

    body = {
        "tipo": "VENTA",
        "cliente_id": 123,
        "vendedor_id": 456,
        "bodega_origen_id": str(uuid4()),
        "items": [{"producto_id": str(uuid4()), "cantidad": 1, "precio_unitario": 10.0}],
        "observaciones": "Test Venta",
    }
    r = await client.post("/v1/pedidos", json=body, headers={"X-Country": "co"})
    assert r.status_code == 201
    assert r.json()["estado"] == "aprobado"

    mock_svc.crear.assert_called_once()
    args, kwargs = mock_svc.crear.call_args
    assert isinstance(args[0], dict)
    assert kwargs.get("x_country") == "co"

@pytest.mark.asyncio
async def test_crear_pedido_value_error(client, mock_svc):
    mock_svc.crear.side_effect = ValueError("Items invalidos")
    bodega_origen_uuid = uuid4()
    producto_uuid = uuid4()
    body = {
        "tipo": "VENTA",
        "cliente_id": 123,
        "vendedor_id": 456,
        "bodega_origen_id": str(bodega_origen_uuid),
        "items": [{
            "producto_id": str(producto_uuid),
            "cantidad": 1,
            "precio_unitario": "10.0",
        }],
        "observaciones": "Test Venta"
    }
    r = await client.post("/v1/pedidos", json=body, headers={"X-Country": "co"})
    assert r.status_code == 400
    assert r.json()["detail"] == "Items invalidos"

@pytest.mark.asyncio
async def test_listar_pedidos_success(client, mock_svc):
    mock_svc.listar.return_value = [make_pedido_out_compra("aprobado")]
    r = await client.get("/v1/pedidos?tipo=COMPRA&estado=aprobado&limit=10&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) == 1
    mock_svc.listar.assert_called_once_with("COMPRA", "aprobado", 10, 0)

@pytest.mark.asyncio
async def test_obtener_pedido_success(client, mock_svc):
    pedido = make_pedido_out_venta("aprobado")
    mock_svc.obtener.return_value = pedido
    r = await client.get(f"/v1/pedidos/{pedido.id}")
    assert r.status_code == 200
    assert r.json()["id"] == str(pedido.id)
    mock_svc.obtener.assert_called_once()

@pytest.mark.asyncio
async def test_obtener_pedido_not_found(client, mock_svc):
    mock_svc.obtener.return_value = None
    r = await client.get(f"/v1/pedidos/{uuid4()}")
    assert r.status_code == 404
    assert r.json()["detail"] == "Pedido no encontrado"

# ---- COMPRA ----
@pytest.mark.asyncio
async def test_marcar_recibido_success(client, mock_svc):
    p = make_pedido_out_compra("recibido")
    mock_svc.marcar_recibido.return_value = p
    r = await client.post(f"/v1/pedidos/{p.id}/marcar-recibido")
    assert r.status_code == 200
    assert r.json()["estado"] == "recibido"
    mock_svc.marcar_recibido.assert_called_once_with(p.id)

@pytest.mark.asyncio
async def test_marcar_recibido_value_error(client, mock_svc):
    mock_svc.marcar_recibido.side_effect = ValueError("Solo aplica para pedidos de COMPRA")
    r = await client.post(f"/v1/pedidos/{uuid4()}/marcar-recibido")
    assert r.status_code == 400
    assert r.json()["detail"] == "Solo aplica para pedidos de COMPRA"

@pytest.mark.asyncio
async def test_marcar_despachado_success(client, mock_svc):
    p = make_pedido_out_venta("despachado")
    mock_svc.marcar_despachado.return_value = p
    r = await client.post(f"/v1/pedidos/{p.id}/marcar-despachado")
    assert r.status_code == 200
    assert r.json()["estado"] == "despachado"
    mock_svc.marcar_despachado.assert_called_once_with(p.id)

@pytest.mark.asyncio
async def test_marcar_despachado_value_error(client, mock_svc):
    mock_svc.marcar_despachado.side_effect = ValueError("Solo aplica para pedidos de VENTA")
    r = await client.post(f"/v1/pedidos/{uuid4()}/marcar-despachado")
    assert r.status_code == 400
    assert r.json()["detail"] == "Solo aplica para pedidos de VENTA"

@pytest.mark.asyncio
async def test_cancelar_success(client, mock_svc):
    p = make_pedido_out_venta("cancelado")
    mock_svc.cancelar.return_value = p
    r = await client.post(f"/v1/pedidos/{p.id}/cancelar")
    assert r.status_code == 200
    assert r.json()["estado"] == "cancelado"
    mock_svc.cancelar.assert_called_once_with(p.id)

@pytest.mark.asyncio
async def test_cancelar_value_error(client, mock_svc):
    mock_svc.cancelar.side_effect = ValueError("No se puede cancelar en este estado")
    r = await client.post(f"/v1/pedidos/{uuid4()}/cancelar")
    assert r.status_code == 400
    assert r.json()["detail"] == "No se puede cancelar en este estado"

@pytest.mark.asyncio
async def test_listar_pedidos_por_fecha_compromiso(client, mock_svc):
    mock_svc.listar.return_value = [make_pedido_out_compra("aprobado")]
    r = await client.get("/v1/pedidos?fecha_compromiso=2025-10-25")
    assert r.status_code == 200
    mock_svc.listar.assert_called_once()
    _, kwargs = mock_svc.listar.call_args
    assert kwargs.get("fecha_compromiso") == date(2025, 10, 25)


@pytest.mark.asyncio
async def test_pubsub_pedido_recibido_ok(client, monkeypatch):
    # Importamos el módulo de la ruta para poder parchear dentro de él
    import src.routes.pedido as pedido_router

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

    r = await client.post("/v1/pedidos/pubsub", json=envelope)
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

    r = await client.post("/v1/pedidos/pubsub", json=envelope)
    assert r.status_code == 204

    # No se llamó a ningún método del servicio
    assert not svc_mock.method_calls

@pytest.mark.asyncio
async def test_pubsub_sin_message(client):
    r = await client.post("/v1/pedidos/pubsub", json={})
    assert r.status_code == 204

@pytest.mark.asyncio
async def test_pubsub_data_invalida(client):
    envelope = {"message": {"data": "%%%no-es-base64%%%"}}
    r = await client.post("/v1/pedidos/pubsub", json=envelope)
    assert r.status_code == 204