import pytest
from uuid import uuid4
from decimal import Decimal
from src.domain import schemas

# -------------------------
# Helpers para fabricar respuestas válidas
# -------------------------
def make_pedido_out_venta(estado="creado"):
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
    )

def make_pedido_out_compra(estado="creado"):
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
    )

# -------------------------
# Tests de endpoints
# -------------------------

@pytest.mark.asyncio
async def test_crear_pedido_success(client, mock_svc):
    mock_svc.crear.return_value = make_pedido_out_venta("creado")

    body = {
        "tipo": "VENTA",
        "cliente_id": 123,
        "vendedor_id": 456,
        "bodega_origen_id": str(uuid4()),
        "items": [{"producto_id": str(uuid4()), "cantidad": 1, "precio_unitario": 10.0}],
        "observaciones": "Test Venta",
    }
    r = await client.post("/v1/pedidos", json=body)
    assert r.status_code == 201
    assert r.json()["estado"] == "creado"
    mock_svc.crear.assert_called_once()
    # opcional: validar que recibió un dict con keys esperadas
    args, _ = mock_svc.crear.call_args
    assert set(args[0].keys()) >= {"tipo", "items"}

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
    r = await client.post("/v1/pedidos", json=body)
    assert r.status_code == 400
    assert r.json()["detail"] == "Items invalidos"

@pytest.mark.asyncio
async def test_listar_pedidos_success(client, mock_svc):
    mock_svc.listar.return_value = [make_pedido_out_compra("pendiente")]
    r = await client.get("/v1/pedidos?tipo=COMPRA&estado=pendiente&limit=10&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) == 1
    mock_svc.listar.assert_called_once_with("COMPRA", "pendiente", 10, 0)

@pytest.mark.asyncio
async def test_obtener_pedido_success(client, mock_svc):
    pedido = make_pedido_out_venta("creado")
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

@pytest.mark.asyncio
async def test_aprobar_pedido_success(client, mock_svc):
    p = make_pedido_out_venta("aprobado")
    mock_svc.aprobar.return_value = p
    r = await client.post(f"/v1/pedidos/{p.id}/aprobar")
    assert r.status_code == 200
    assert r.json()["estado"] == "aprobado"
    mock_svc.aprobar.assert_called_once_with(p.id)

@pytest.mark.asyncio
async def test_aprobar_pedido_value_error(client, mock_svc):
    pid = uuid4()
    mock_svc.aprobar.side_effect = ValueError("Transición no válida")
    r = await client.post(f"/v1/pedidos/{pid}/aprobar")
    assert r.status_code == 400
    assert r.json()["detail"] == "Transición no válida"
    mock_svc.aprobar.assert_called_once_with(pid)

# ---- COMPRA ----

@pytest.mark.asyncio
async def test_link_oc_success(client, mock_svc):
    p = make_pedido_out_compra("en_transito")
    mock_svc.link_oc.return_value = p
    oc_id = str(uuid4())
    r = await client.post(f"/v1/pedidos/{p.id}/link-oc", json={"oc_id": oc_id})
    assert r.status_code == 200
    assert r.json()["estado"].lower() in ("en_transito", "en-transito", "en_transito")
    mock_svc.link_oc.assert_called_once()

@pytest.mark.asyncio
async def test_link_oc_missing_body(client, mock_svc):
    r = await client.post(f"/v1/pedidos/{uuid4()}/link-oc", json={})
    assert r.status_code == 400
    assert r.json()["detail"] == "Falta oc_id"
    mock_svc.link_oc.assert_not_called()

@pytest.mark.asyncio
async def test_link_oc_value_error(client, mock_svc):
    mock_svc.link_oc.side_effect = ValueError("Solo aplica para pedidos de COMPRA")
    r = await client.post(f"/v1/pedidos/{uuid4()}/link-oc", json={"oc_id": str(uuid4())})
    assert r.status_code == 400
    assert r.json()["detail"] == "Solo aplica para pedidos de COMPRA"

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

# ---- VENTA ----

@pytest.mark.asyncio
async def test_set_reserva_success(client, mock_svc):
    p = make_pedido_out_venta("reservado")
    mock_svc.set_reserva.return_value = p
    r = await client.post(f"/v1/pedidos/{p.id}/set-reserva", json={"reserva_token": "R-123"})
    assert r.status_code == 200
    assert r.json()["estado"] == "reservado"
    mock_svc.set_reserva.assert_called_once_with(p.id, "R-123")

@pytest.mark.asyncio
async def test_set_reserva_missing_token(client, mock_svc):
    r = await client.post(f"/v1/pedidos/{uuid4()}/set-reserva", json={})
    assert r.status_code == 400
    assert r.json()["detail"] == "Falta reserva_token"
    mock_svc.set_reserva.assert_not_called()

@pytest.mark.asyncio
async def test_set_reserva_value_error(client, mock_svc):
    mock_svc.set_reserva.side_effect = ValueError("Solo aplica para pedidos de VENTA")
    r = await client.post(f"/v1/pedidos/{uuid4()}/set-reserva", json={"reserva_token": "R-123"})
    assert r.status_code == 400
    assert r.json()["detail"] == "Solo aplica para pedidos de VENTA"

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
