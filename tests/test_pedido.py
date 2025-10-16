import pytest
from httpx import AsyncClient
from unittest.mock import MagicMock, patch
from src.domain import schemas
from uuid import uuid4, UUID
from decimal import Decimal

# Import the service and domain models
from src.services.pedido import PedidosService, calcular_totales, _dec
from src.domain.models import Pedido, PedidoItem, PedidoEvento
from src.domain.enums import PedidoTipo, PedidoEstado
from sqlalchemy.orm import Session
from datetime import datetime

# Helper function to create a valid PedidoOut for VENTA
def create_venta_pedido_out(pedido_id: UUID, estado: str = "creado") -> schemas.PedidoOut:
    return schemas.PedidoOut(
        id=pedido_id,
        codigo=f"PED-VENTA-{str(pedido_id)[:4]}",
        tipo="VENTA",
        estado=estado,
        cliente_id=123,
        vendedor_id=456,
        bodega_origen_id=uuid4(),
        items=[schemas.ItemIn(producto_id=uuid4(), cantidad=1, precio_unitario=Decimal("10.0"))]
    )

# Helper function to create a valid PedidoOut for COMPRA
def create_compra_pedido_out(pedido_id: UUID, estado: str = "creado") -> schemas.PedidoOut:
    return schemas.PedidoOut(
        id=pedido_id,
        codigo=f"PED-COMPRA-{str(pedido_id)[:4]}",
        tipo="COMPRA",
        estado=estado,
        proveedor_id=uuid4(),
        bodega_destino_id=uuid4(),
        items=[schemas.ItemIn(producto_id=uuid4(), cantidad=1, precio_unitario=Decimal("10.0"))]
    )

@pytest.mark.asyncio
async def test_crear_pedido_success(client: AsyncClient, mock_pedido_service, mock_get_session):
    # Generate UUIDs once to use in both request and expected call
    bodega_origen_uuid = uuid4()
    producto_uuid = uuid4()

    pedido_data_request = {
        "tipo": "VENTA",
        "cliente_id": 123,
        "vendedor_id": 456,
        "bodega_origen_id": str(bodega_origen_uuid),
        "items": [{"producto_id": str(producto_uuid), "cantidad": 1, "precio_unitario": 10.0}],
        "observaciones": "Test Venta"
    }

    # Expected data after Pydantic parsing
    expected_pedido_data_in_service = {
        "tipo": "VENTA",
        "cliente_id": 123,
        "vendedor_id": 456,
        "bodega_origen_id": bodega_origen_uuid, # Changed to UUID object
        "items": [{
            "producto_id": producto_uuid, # Changed to UUID object
            "cantidad": 1,
            "precio_unitario": Decimal("10.0"), # Changed to Decimal object
            "impuesto_pct": None, # Added default None values
            "descuento_pct": None, # Added default None values
            "sku": None # Added default None values
        }],
        "observaciones": "Test Venta"
    }

    mock_pedido_service.crear.return_value = create_venta_pedido_out(uuid4(), "creado")

    response = await client.post("/v1/pedidos", json=pedido_data_request)

    assert response.status_code == 201
    assert response.json()["estado"] == "creado"
    mock_pedido_service.crear.assert_called_once_with(expected_pedido_data_in_service)

@pytest.mark.asyncio
async def test_crear_pedido_value_error(client: AsyncClient, mock_pedido_service, mock_get_session):
    # Generate UUIDs once to use in both request and expected call
    bodega_origen_uuid = uuid4()
    producto_uuid = uuid4()

    pedido_data_request = {
        "tipo": "VENTA",
        "cliente_id": 123,
        "vendedor_id": 456,
        "bodega_origen_id": str(bodega_origen_uuid),
        "items": [{"producto_id": str(producto_uuid), "cantidad": 1, "precio_unitario": 10.0}],
        "observaciones": "Test Venta"
    }

    # Expected data after Pydantic parsing
    expected_pedido_data_in_service = {
        "tipo": "VENTA",
        "cliente_id": 123,
        "vendedor_id": 456,
        "bodega_origen_id": bodega_origen_uuid, # Changed to UUID object
        "items": [{
            "producto_id": producto_uuid, # Changed to UUID object
            "cantidad": 1,
            "precio_unitario": Decimal("10.0"), # Changed to Decimal object
            "impuesto_pct": None, # Added default None values
            "descuento_pct": None, # Added default None values
            "sku": None # Added default None values
        }],
        "observaciones": "Test Venta"
    }

    mock_pedido_service.crear.side_effect = ValueError("Items cannot be empty")

    response = await client.post("/v1/pedidos", json=pedido_data_request)

    assert response.status_code == 400
    assert response.json()["detail"] == "Items cannot be empty"
    mock_pedido_service.crear.assert_called_once_with(expected_pedido_data_in_service)

@pytest.mark.asyncio
async def test_listar_pedidos_success(client: AsyncClient, mock_pedido_service, mock_get_session):
    mock_pedido_service.listar.return_value = [
        create_compra_pedido_out(uuid4(), "pendiente")
    ]

    response = await client.get("/v1/pedidos?tipo=compra&estado=pendiente&limit=10&offset=0")

    assert response.status_code == 200
    assert len(response.json()) == 1
    mock_pedido_service.listar.assert_called_once_with("compra", "pendiente", 10, 0)

@pytest.mark.asyncio
async def test_obtener_pedido_success(client: AsyncClient, mock_pedido_service, mock_get_session):
    pedido_id = uuid4()
    mock_pedido_service.obtener.return_value = create_venta_pedido_out(pedido_id, "creado")

    response = await client.get(f"/v1/pedidos/{pedido_id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(pedido_id)
    mock_pedido_service.obtener.assert_called_once_with(pedido_id)

@pytest.mark.asyncio
async def test_obtener_pedido_not_found(client: AsyncClient, mock_pedido_service, mock_get_session):
    pedido_id = uuid4()
    mock_pedido_service.obtener.return_value = None

    response = await client.get(f"/v1/pedidos/{pedido_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Pedido no encontrado"
    mock_pedido_service.obtener.assert_called_once_with(pedido_id)

@pytest.mark.asyncio
async def test_aprobar_pedido_success(client: AsyncClient, mock_pedido_service, mock_get_session):
    pedido_id = uuid4()
    mock_pedido_service.aprobar.return_value = create_venta_pedido_out(pedido_id, "aprobado")

    response = await client.post(f"/v1/pedidos/{pedido_id}/aprobar")

    assert response.status_code == 200
    assert response.json()["estado"] == "aprobado"
    mock_pedido_service.aprobar.assert_called_once_with(pedido_id)

@pytest.mark.asyncio
async def test_aprobar_pedido_value_error(client: AsyncClient, mock_pedido_service, mock_get_session):
    pedido_id = uuid4()
    mock_pedido_service.aprobar.side_effect = ValueError("Transición no válida")

    response = await client.post(f"/v1/pedidos/{pedido_id}/aprobar")

    assert response.status_code == 400
    assert response.json()["detail"] == "Transición no válida"
    mock_pedido_service.aprobar.assert_called_once_with(pedido_id)

@pytest.mark.asyncio
async def test_link_oc_key_error(client: AsyncClient, mock_pedido_service, mock_get_session):
    pedido_id = uuid4()

    response = await client.post(f"/v1/pedidos/{pedido_id}/link-oc", json={})

    assert response.status_code == 400
    assert response.json()["detail"] == "Falta oc_id"
    mock_pedido_service.link_oc.assert_not_called()


@pytest.mark.asyncio
async def test_marcar_recibido_success(client: AsyncClient, mock_pedido_service, mock_get_session):
    pedido_id = uuid4()
    mock_pedido_service.marcar_recibido.return_value = create_compra_pedido_out(pedido_id, "recibido")

    response = await client.post(f"/v1/pedidos/{pedido_id}/marcar-recibido")

    assert response.status_code == 200
    assert response.json()["estado"] == "recibido"
    mock_pedido_service.marcar_recibido.assert_called_once_with(pedido_id)

@pytest.mark.asyncio
async def test_marcar_recibido_value_error(client: AsyncClient, mock_pedido_service, mock_get_session):
    pedido_id = uuid4()
    mock_pedido_service.marcar_recibido.side_effect = ValueError("Solo aplica para pedidos de COMPRA")

    response = await client.post(f"/v1/pedidos/{pedido_id}/marcar-recibido")

    assert response.status_code == 400
    assert response.json()["detail"] == "Solo aplica para pedidos de COMPRA"
    mock_pedido_service.marcar_recibido.assert_called_once_with(pedido_id)

@pytest.mark.asyncio
async def test_set_reserva_success(client: AsyncClient, mock_pedido_service, mock_get_session):
    pedido_id = uuid4()
    reserva_token = "TOKEN-123"
    mock_pedido_service.set_reserva.return_value = create_venta_pedido_out(pedido_id, "reservado")

    response = await client.post(f"/v1/pedidos/{pedido_id}/set-reserva", json={"reserva_token": reserva_token})

    assert response.status_code == 200
    assert response.json()["estado"] == "reservado"
    mock_pedido_service.set_reserva.assert_called_once_with(pedido_id, reserva_token)

@pytest.mark.asyncio
async def test_set_reserva_key_error(client: AsyncClient, mock_pedido_service, mock_get_session):
    pedido_id = uuid4()

    response = await client.post(f"/v1/pedidos/{pedido_id}/set-reserva", json={})

    assert response.status_code == 400
    assert response.json()["detail"] == "Falta reserva_token"
    mock_pedido_service.set_reserva.assert_not_called()

@pytest.mark.asyncio
async def test_set_reserva_value_error(client: AsyncClient, mock_pedido_service, mock_get_session):
    pedido_id = uuid4()
    reserva_token = "TOKEN-123"
    mock_pedido_service.set_reserva.side_effect = ValueError("Solo aplica para pedidos de VENTA")

    response = await client.post(f"/v1/pedidos/{pedido_id}/set-reserva", json={"reserva_token": reserva_token})

    assert response.status_code == 400
    assert response.json()["detail"] == "Solo aplica para pedidos de VENTA"
    mock_pedido_service.set_reserva.assert_called_once_with(pedido_id, reserva_token)

@pytest.mark.asyncio
async def test_marcar_despachado_success(client: AsyncClient, mock_pedido_service, mock_get_session):
    pedido_id = uuid4()
    mock_pedido_service.marcar_despachado.return_value = create_venta_pedido_out(pedido_id, "despachado")

    response = await client.post(f"/v1/pedidos/{pedido_id}/marcar-despachado")

    assert response.status_code == 200
    assert response.json()["estado"] == "despachado"
    mock_pedido_service.marcar_despachado.assert_called_once_with(pedido_id)

@pytest.mark.asyncio
async def test_marcar_despachado_value_error(client: AsyncClient, mock_pedido_service, mock_get_session):
    pedido_id = uuid4()
    mock_pedido_service.marcar_despachado.side_effect = ValueError("Solo aplica para pedidos de VENTA")

    response = await client.post(f"/v1/pedidos/{pedido_id}/marcar-despachado")

    assert response.status_code == 400
    assert response.json()["detail"] == "Solo aplica para pedidos de VENTA"
    mock_pedido_service.marcar_despachado.assert_called_once_with(pedido_id)

@pytest.mark.asyncio
async def test_cancelar_pedido_success(client: AsyncClient, mock_pedido_service, mock_get_session):
    pedido_id = uuid4()
    mock_pedido_service.cancelar.return_value = create_venta_pedido_out(pedido_id, "cancelado")

    response = await client.post(f"/v1/pedidos/{pedido_id}/cancelar")

    assert response.status_code == 200
    assert response.json()["estado"] == "cancelado"
    mock_pedido_service.cancelar.assert_called_once_with(pedido_id)

@pytest.mark.asyncio
async def test_cancelar_pedido_value_error(client: AsyncClient, mock_pedido_service, mock_get_session):
    pedido_id = uuid4()
    mock_pedido_service.cancelar.side_effect = ValueError("Pedido no puede ser cancelado")

    response = await client.post(f"/v1/pedidos/{pedido_id}/cancelar")

    assert response.status_code == 400
    assert response.json()["detail"] == "Pedido no puede ser cancelado"
    mock_pedido_service.cancelar.assert_called_once_with(pedido_id)


# Fixture for a mocked PedidosService instance
@pytest.fixture
def mock_db_session():
    return MagicMock(spec=Session)

@pytest.fixture
def pedido_service(mock_db_session):
    return PedidosService(mock_db_session)

# New Unit Tests for PedidosService
class TestPedidosService:

    def test_gen_codigo_compra(self, pedido_service):
        codigo = pedido_service._gen_codigo(PedidoTipo.COMPRA.value)
        assert codigo.startswith("PO-")
        assert f"-{datetime.utcnow().year}-" in codigo
        assert len(codigo) == len(f"PO-{datetime.utcnow().year}-{uuid4().hex[:6].upper()}")

    def test_gen_codigo_venta(self, pedido_service):
        codigo = pedido_service._gen_codigo(PedidoTipo.VENTA.value)
        assert codigo.startswith("SO-")
        assert f"-{datetime.utcnow().year}-" in codigo
        assert len(codigo) == len(f"SO-{datetime.utcnow().year}-{uuid4().hex[:6].upper()}")

    @patch('src.services.pedido.calcular_totales')
    def test_crear_pedido_venta_success(self, mock_calcular_totales, pedido_service, mock_db_session):
        payload = {
            "tipo": PedidoTipo.VENTA.value,
            "cliente_id": 1,
            "vendedor_id": 2,
            "bodega_origen_id": uuid4(),
            "items": [
                {"producto_id": uuid4(), "cantidad": 1, "precio_unitario": 100, "impuesto_pct": 10, "descuento_pct": 5}
            ],
            "observaciones": "Test Venta"
        }

        # Configure mock_calcular_totales to set the expected values on the pedido object
        def mock_calcular_totales_side_effect(pedido_obj):
            pedido_obj.subtotal = Decimal("95.0")
            pedido_obj.impuesto_total = Decimal("9.5")
            pedido_obj.total = Decimal("104.5")
            # Manually populate items for assertion, as they are not loaded by mocked db.refresh
            pedido_obj.items = []
            for item_data in payload["items"]:
                pedido_obj.items.append(PedidoItem(
                    pedido_id=pedido_obj.id,
                    producto_id=item_data["producto_id"],
                    cantidad=item_data["cantidad"],
                    precio_unitario=Decimal(str(item_data["precio_unitario"])) if "precio_unitario" in item_data else None,
                    impuesto_pct=Decimal(str(item_data["impuesto_pct"])) if "impuesto_pct" in item_data else None,
                    descuento_pct=Decimal(str(item_data["descuento_pct"])) if "descuento_pct" in item_data else None,
                    sku=item_data.get("sku"),
                ))

        mock_calcular_totales.side_effect = mock_calcular_totales_side_effect

        mock_db_session.flush.return_value = None
        mock_db_session.commit.return_value = None
        mock_db_session.refresh.side_effect = lambda x: x # refresh should return the same object

        pedido = pedido_service.crear(payload)

        assert pedido.tipo == PedidoTipo.VENTA.value
        assert pedido.estado == PedidoEstado.BORRADOR.value
        assert pedido.cliente_id == 1
        assert len(pedido.items) == 1
        assert pedido.subtotal == Decimal("95.0")
        assert pedido.impuesto_total == Decimal("9.5")
        assert pedido.total == Decimal("104.5")

        # Assertions for add calls
        add_calls = mock_db_session.add.call_args_list
        assert any(isinstance(call.args[0], Pedido) for call in add_calls)
        assert any(isinstance(call.args[0], PedidoItem) for call in add_calls)
        assert any(isinstance(call.args[0], PedidoEvento) for call in add_calls)

        mock_db_session.flush.assert_called_once()
        mock_calcular_totales.assert_called_once_with(pedido)
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once_with(pedido)

    @patch('src.services.pedido.calcular_totales')
    def test_crear_pedido_compra_success(self, mock_calcular_totales, pedido_service, mock_db_session):
        payload = {
            "tipo": PedidoTipo.COMPRA.value,
            "proveedor_id": uuid4(),
            "bodega_destino_id": uuid4(),
            "items": [
                {"producto_id": uuid4(), "cantidad": 2, "precio_unitario": 50}
            ],
            "observaciones": "Test Compra"
        }

        # Configure mock_calcular_totales to set the expected values on the pedido object
        def mock_calcular_totales_side_effect(pedido_obj):
            pedido_obj.subtotal = Decimal("100.0")
            pedido_obj.impuesto_total = Decimal("0.0")
            pedido_obj.total = Decimal("100.0")
            # Manually populate items for assertion, as they are not loaded by mocked db.refresh
            pedido_obj.items = []
            for item_data in payload["items"]:
                pedido_obj.items.append(PedidoItem(
                    pedido_id=pedido_obj.id,
                    producto_id=item_data["producto_id"],
                    cantidad=item_data["cantidad"],
                    precio_unitario=Decimal(str(item_data["precio_unitario"])) if "precio_unitario" in item_data else None,
                    impuesto_pct=Decimal(str(item_data["impuesto_pct"])) if "impuesto_pct" in item_data else None,
                    descuento_pct=Decimal(str(item_data["descuento_pct"])) if "descuento_pct" in item_data else None,
                    sku=item_data.get("sku"),
                ))

        mock_calcular_totales.side_effect = mock_calcular_totales_side_effect

        mock_db_session.flush.return_value = None
        mock_db_session.commit.return_value = None
        mock_db_session.refresh.side_effect = lambda x: x

        pedido = pedido_service.crear(payload)

        assert pedido.tipo == PedidoTipo.COMPRA.value
        assert pedido.estado == PedidoEstado.BORRADOR.value
        assert pedido.proveedor_id is not None
        assert len(pedido.items) == 1
        assert pedido.subtotal == Decimal("100.0")
        assert pedido.impuesto_total == Decimal("0.0") # No impuesto_pct provided
        assert pedido.total == Decimal("100.0")

        # Assertions for add calls
        add_calls = mock_db_session.add.call_args_list
        assert any(isinstance(call.args[0], Pedido) for call in add_calls)
        assert any(isinstance(call.args[0], PedidoItem) for call in add_calls)
        assert any(isinstance(call.args[0], PedidoEvento) for call in add_calls)

        mock_db_session.flush.assert_called_once()
        mock_calcular_totales.assert_called_once_with(pedido)
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once_with(pedido)

    def test_aprobar_pedido_success_borrador(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        mock_pedido = Pedido(id=pedido_id, estado=PedidoEstado.BORRADOR.value, tipo=PedidoTipo.VENTA.value)
        mock_db_session.get.return_value = mock_pedido
        mock_db_session.commit.return_value = None
        mock_db_session.refresh.side_effect = lambda x: x

        approved_pedido = pedido_service.aprobar(pedido_id)

        assert approved_pedido.estado == PedidoEstado.APROBADO.value
        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.add.assert_called_once() # For PedidoEvento
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once_with(approved_pedido)

    def test_aprobar_pedido_success_pendiente_aprobacion(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        mock_pedido = Pedido(id=pedido_id, estado=PedidoEstado.PENDIENTE_APROBACION.value, tipo=PedidoTipo.VENTA.value)
        mock_db_session.get.return_value = mock_pedido
        mock_db_session.commit.return_value = None
        mock_db_session.refresh.side_effect = lambda x: x

        approved_pedido = pedido_service.aprobar(pedido_id)

        assert approved_pedido.estado == PedidoEstado.APROBADO.value
        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.add.assert_called_once() # For PedidoEvento
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once_with(approved_pedido)

    def test_aprobar_pedido_invalid_transition(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        mock_pedido = Pedido(id=pedido_id, estado=PedidoEstado.APROBADO.value, tipo=PedidoTipo.VENTA.value)
        mock_db_session.get.return_value = mock_pedido

        with pytest.raises(ValueError, match="Transición no válida"):
            pedido_service.aprobar(pedido_id)

        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.commit.assert_not_called()

    def test_aprobar_pedido_not_found(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        mock_db_session.get.return_value = None

        with pytest.raises(ValueError, match="Pedido no encontrado"):
            pedido_service.aprobar(pedido_id)

        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.commit.assert_not_called()

    def test_link_oc_success_new_oc_aprobado(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        oc_id = uuid4()
        mock_pedido = Pedido(id=pedido_id, tipo=PedidoTipo.COMPRA.value, estado=PedidoEstado.APROBADO.value, oc_id=None)
        mock_db_session.get.return_value = mock_pedido
        mock_db_session.commit.return_value = None
        mock_db_session.refresh.side_effect = lambda x: x

        linked_pedido = pedido_service.link_oc(pedido_id, oc_id)

        assert linked_pedido.oc_id == oc_id
        assert linked_pedido.estado == PedidoEstado.EN_TRANSITO.value
        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.add.assert_called_once() # For PedidoEvento
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once_with(linked_pedido)

    def test_link_oc_success_existing_oc_same_id(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        oc_id = uuid4()
        mock_pedido = Pedido(id=pedido_id, tipo=PedidoTipo.COMPRA.value, estado=PedidoEstado.APROBADO.value, oc_id=oc_id)
        mock_db_session.get.return_value = mock_pedido
        mock_db_session.commit.return_value = None
        mock_db_session.refresh.side_effect = lambda x: x

        linked_pedido = pedido_service.link_oc(pedido_id, oc_id)

        assert linked_pedido.oc_id == oc_id
        assert linked_pedido.estado == PedidoEstado.EN_TRANSITO.value # Still transitions if approved
        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.add.assert_called_once() # For PedidoEvento
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once_with(linked_pedido)

    def test_link_oc_success_existing_oc_different_id(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        oc_id_old = uuid4()
        oc_id_new = uuid4()
        mock_pedido = Pedido(id=pedido_id, tipo=PedidoTipo.COMPRA.value, estado=PedidoEstado.APROBADO.value, oc_id=oc_id_old)
        mock_db_session.get.return_value = mock_pedido
        mock_db_session.commit.return_value = None
        mock_db_session.refresh.side_effect = lambda x: x

        linked_pedido = pedido_service.link_oc(pedido_id, oc_id_new)

        assert linked_pedido.oc_id == oc_id_new
        assert linked_pedido.estado == PedidoEstado.EN_TRANSITO.value
        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.add.assert_called_once() # For PedidoEvento
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once_with(linked_pedido)

    def test_link_oc_wrong_type(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        oc_id = uuid4()
        mock_pedido = Pedido(id=pedido_id, tipo=PedidoTipo.VENTA.value, estado=PedidoEstado.APROBADO.value)
        mock_db_session.get.return_value = mock_pedido

        with pytest.raises(ValueError, match="Solo aplica para pedidos de COMPRA"):
            pedido_service.link_oc(pedido_id, oc_id)

        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.commit.assert_not_called()

    def test_marcar_recibido_success_aprobado(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        mock_pedido = Pedido(id=pedido_id, tipo=PedidoTipo.COMPRA.value, estado=PedidoEstado.APROBADO.value)
        mock_db_session.get.return_value = mock_pedido
        mock_db_session.commit.return_value = None
        mock_db_session.refresh.side_effect = lambda x: x

        received_pedido = pedido_service.marcar_recibido(pedido_id)

        assert received_pedido.estado == PedidoEstado.RECIBIDO.value
        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once_with(received_pedido)

    def test_marcar_recibido_success_en_transito(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        mock_pedido = Pedido(id=pedido_id, tipo=PedidoTipo.COMPRA.value, estado=PedidoEstado.EN_TRANSITO.value)
        mock_db_session.get.return_value = mock_pedido
        mock_db_session.commit.return_value = None
        mock_db_session.refresh.side_effect = lambda x: x

        received_pedido = pedido_service.marcar_recibido(pedido_id)

        assert received_pedido.estado == PedidoEstado.RECIBIDO.value
        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once_with(received_pedido)

    def test_marcar_recibido_wrong_type(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        mock_pedido = Pedido(id=pedido_id, tipo=PedidoTipo.VENTA.value, estado=PedidoEstado.APROBADO.value)
        mock_db_session.get.return_value = mock_pedido

        with pytest.raises(ValueError, match="Solo aplica para pedidos de COMPRA"):
            pedido_service.marcar_recibido(pedido_id)

        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.commit.assert_not_called()

    def test_marcar_recibido_invalid_transition(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        mock_pedido = Pedido(id=pedido_id, tipo=PedidoTipo.COMPRA.value, estado=PedidoEstado.BORRADOR.value)
        mock_db_session.get.return_value = mock_pedido

        with pytest.raises(ValueError, match="Transición no válida"):
            pedido_service.marcar_recibido(pedido_id)

        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.commit.assert_not_called()

    def test_set_reserva_success(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        reserva_token = "test_token"
        mock_pedido = Pedido(id=pedido_id, tipo=PedidoTipo.VENTA.value, estado=PedidoEstado.APROBADO.value, reserva_token=None)
        mock_db_session.get.return_value = mock_pedido
        mock_db_session.commit.return_value = None
        mock_db_session.refresh.side_effect = lambda x: x

        reserved_pedido = pedido_service.set_reserva(pedido_id, reserva_token)

        assert reserved_pedido.reserva_token == reserva_token
        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once_with(reserved_pedido)

    def test_set_reserva_wrong_type(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        reserva_token = "test_token"
        mock_pedido = Pedido(id=pedido_id, tipo=PedidoTipo.COMPRA.value, estado=PedidoEstado.APROBADO.value)
        mock_db_session.get.return_value = mock_pedido

        with pytest.raises(ValueError, match="Solo aplica para pedidos de VENTA"):
            pedido_service.set_reserva(pedido_id, reserva_token)

        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.commit.assert_not_called()

    def test_marcar_despachado_success(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        mock_pedido = Pedido(id=pedido_id, tipo=PedidoTipo.VENTA.value, estado=PedidoEstado.APROBADO.value)
        mock_db_session.get.return_value = mock_pedido
        mock_db_session.commit.return_value = None
        mock_db_session.refresh.side_effect = lambda x: x

        dispatched_pedido = pedido_service.marcar_despachado(pedido_id)

        assert dispatched_pedido.estado == PedidoEstado.DESPACHADO.value
        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once_with(dispatched_pedido)

    def test_marcar_despachado_wrong_type(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        mock_pedido = Pedido(id=pedido_id, tipo=PedidoTipo.COMPRA.value, estado=PedidoEstado.APROBADO.value)
        mock_db_session.get.return_value = mock_pedido

        with pytest.raises(ValueError, match="Solo aplica para pedidos de VENTA"):
            pedido_service.marcar_despachado(pedido_id)

        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.commit.assert_not_called()

    def test_marcar_despachado_invalid_transition(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        mock_pedido = Pedido(id=pedido_id, tipo=PedidoTipo.VENTA.value, estado=PedidoEstado.BORRADOR.value)
        mock_db_session.get.return_value = mock_pedido

        with pytest.raises(ValueError, match="Transición no válida"):
            pedido_service.marcar_despachado(pedido_id)

        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.commit.assert_not_called()

    def test_cancelar_pedido_success(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        mock_pedido = Pedido(id=pedido_id, estado=PedidoEstado.BORRADOR.value)
        mock_db_session.get.return_value = mock_pedido
        mock_db_session.commit.return_value = None
        mock_db_session.refresh.side_effect = lambda x: x

        cancelled_pedido = pedido_service.cancelar(pedido_id)

        assert cancelled_pedido.estado == PedidoEstado.CANCELADO.value
        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once_with(cancelled_pedido)

    @pytest.mark.parametrize("estado_invalido", [
        PedidoEstado.RECIBIDO.value,
        PedidoEstado.DESPACHADO.value,
        PedidoEstado.CANCELADO.value
    ])
    def test_cancelar_pedido_invalid_transition(self, pedido_service, mock_db_session, estado_invalido):
        pedido_id = uuid4()
        mock_pedido = Pedido(id=pedido_id, estado=estado_invalido)
        mock_db_session.get.return_value = mock_pedido

        with pytest.raises(ValueError, match="No se puede cancelar en este estado"):
            pedido_service.cancelar(pedido_id)

        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)
        mock_db_session.commit.assert_not_called()

    def test_obtener_pedido_success(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        mock_pedido = Pedido(id=pedido_id)
        mock_db_session.get.return_value = mock_pedido

        found_pedido = pedido_service.obtener(pedido_id)

        assert found_pedido == mock_pedido
        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)

    def test_obtener_pedido_not_found(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        mock_db_session.get.return_value = None

        found_pedido = pedido_service.obtener(pedido_id)

        assert found_pedido is None
        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)

    def test_listar_pedidos_no_filters(self, pedido_service, mock_db_session):
        mock_query = MagicMock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [Pedido(id=uuid4()), Pedido(id=uuid4())]

        pedidos = pedido_service.listar(tipo=None, estado=None, limit=10, offset=0)

        assert len(pedidos) == 2
        mock_db_session.query.assert_called_once_with(Pedido)
        mock_query.filter.assert_not_called()
        mock_query.order_by.assert_called_once()
        mock_query.offset.assert_called_once_with(0)
        mock_query.limit.assert_called_once_with(10)
        mock_query.all.assert_called_once()

    def test_listar_pedidos_with_filters(self, pedido_service, mock_db_session):
        mock_query = MagicMock()
        mock_db_session.query.return_value = mock_query

        # Configure mock_query to return itself for chaining methods
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [Pedido(id=uuid4())] # Set the return value for the final .all() call

        pedidos = pedido_service.listar(tipo=PedidoTipo.VENTA.value, estado=PedidoEstado.APROBADO.value, limit=5, offset=1)

        assert len(pedidos) == 1
        mock_db_session.query.assert_called_once_with(Pedido)

        filter_calls = mock_query.filter.call_args_list
        assert len(filter_calls) == 2

        found_tipo_filter = False
        found_estado_filter = False
        for expr_call in filter_calls:
            expr = expr_call.args[0]
            if hasattr(expr, 'left') and hasattr(expr, 'right'):
                if expr.left.key == 'tipo' and expr.right.value == PedidoTipo.VENTA.value:
                    found_tipo_filter = True
                if expr.left.key == 'estado' and expr.right.value == PedidoEstado.APROBADO.value:
                    found_estado_filter = True
        assert found_tipo_filter
        assert found_estado_filter

        mock_query.order_by.assert_called_once()
        mock_query.offset.assert_called_once_with(1)
        mock_query.limit.assert_called_once_with(5)
        mock_query.all.assert_called_once()

    def test_ensure_success(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        mock_pedido = Pedido(id=pedido_id)
        mock_db_session.get.return_value = mock_pedido

        ensured_pedido = pedido_service._ensure(pedido_id)

        assert ensured_pedido == mock_pedido
        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)

    def test_ensure_not_found(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        mock_db_session.get.return_value = None

        with pytest.raises(ValueError, match="Pedido no encontrado"):
            pedido_service._ensure(pedido_id)

        mock_db_session.get.assert_called_once_with(Pedido, pedido_id)

    def test_log_event(self, pedido_service, mock_db_session):
        pedido_id = uuid4()
        mock_pedido = Pedido(id=pedido_id)
        estado = PedidoEstado.APROBADO.value
        detalle = "Pedido aprobado"
        quien_user_id = 123

        pedido_service._log(mock_pedido, estado, detalle, quien_user_id)

        mock_db_session.add.assert_called_once()
        added_event = mock_db_session.add.call_args[0][0]
        assert isinstance(added_event, PedidoEvento)
        assert added_event.pedido_id == pedido_id
        assert added_event.estado == estado
        assert added_event.detalle == detalle
        assert added_event.quien_user_id == quien_user_id

    def test_calcular_totales(self):
        # Mock Pedido and PedidoItem objects
        mock_item1 = MagicMock(spec=PedidoItem)
        mock_item1.precio_unitario = Decimal("100")
        mock_item1.cantidad = 1
        mock_item1.descuento_pct = Decimal("10")
        mock_item1.impuesto_pct = Decimal("15")

        mock_item2 = MagicMock(spec=PedidoItem)
        mock_item2.precio_unitario = Decimal("50")
        mock_item2.cantidad = 2
        mock_item2.descuento_pct = Decimal("0")
        mock_item2.impuesto_pct = Decimal("0")

        mock_pedido = MagicMock(spec=Pedido)
        mock_pedido.items = [mock_item1, mock_item2]
        mock_pedido.subtotal = Decimal("0")
        mock_pedido.impuesto_total = Decimal("0")
        mock_pedido.total = Decimal("0")

        calcular_totales(mock_pedido)

        # Item 1:
        # li = 100 * 1 = 100
        # dsc = 100 * 10 / 100 = 10
        # neto = 100 - 10 = 90
        # imp_item1 = 90 * 15 / 100 = 13.5
        # sub_item1 = 90

        # Item 2:
        # li = 50 * 2 = 100
        # dsc = 100 * 0 / 100 = 0
        # neto = 100 - 0 = 100
        # imp_item2 = 100 * 0 / 100 = 0
        # sub_item2 = 100

        # Total:
        # subtotal = 90 + 100 = 190
        # impuesto_total = 13.5 + 0 = 13.5
        # total = 190 + 13.5 = 203.5

        assert mock_pedido.subtotal == Decimal("190.0")
        assert mock_pedido.impuesto_total == Decimal("13.5")
        assert mock_pedido.total == Decimal("203.5")

    def test_dec_with_none(self):
        assert _dec(None) == Decimal("0")
        assert _dec(None, "5") == Decimal("5")

    def test_dec_with_value(self):
        assert _dec(10) == Decimal("10")
        assert _dec("10.5") == Decimal("10.5")
        assert _dec(Decimal("12.3")) == Decimal("12.3")
