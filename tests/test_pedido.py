# tests/test_service_pedidos.py
import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4
from decimal import Decimal
from datetime import datetime

from src.services.pedido import PedidosService, calcular_totales, _dec
from src.domain.models import Pedido, PedidoItem, PedidoEvento
from src.domain.enums import PedidoTipo, PedidoEstado

# --------------------
# Fixtures
# --------------------
@pytest.fixture
def mock_db():
    db = MagicMock(name="Session")

    def add_side_effect(obj):
        # Simular autogeneración de ID cuando se hace add()
        if hasattr(obj, "id") and getattr(obj, "id", None) is None:
            setattr(obj, "id", uuid4())
        return None

    db.add.side_effect = add_side_effect
    db.flush.return_value = None
    db.commit.return_value = None
    db.rollback.return_value = None
    db.refresh.side_effect = lambda x: x
    db.query.return_value = MagicMock()
    db.get.side_effect = lambda model, pid: None
    return db

@pytest.fixture
def service(mock_db):
    return PedidosService(mock_db)

# --------------------
# Unit tests de helpers
# --------------------
def test_gen_codigo_compra(service):
    codigo = service._gen_codigo(PedidoTipo.COMPRA.value)
    assert codigo.startswith("PO-")
    assert f"-{datetime.now().year}-" in codigo

def test_gen_codigo_venta(service):
    codigo = service._gen_codigo(PedidoTipo.VENTA.value)
    assert codigo.startswith("SO-")
    assert f"-{datetime.now().year}-" in codigo

def test_calcular_totales():
    # Construimos un pedido minimal con 2 items
    p = MagicMock(spec=Pedido)
    item1 = MagicMock(spec=PedidoItem)
    item1.precio_unitario = Decimal("100")
    item1.cantidad = 2
    item1.descuento_pct = Decimal("5")   # 5% sobre 200 = 10
    item1.impuesto_pct = Decimal("10")   # 10% sobre 190 = 19

    item2 = MagicMock(spec=PedidoItem)
    item2.precio_unitario = Decimal("50")
    item2.cantidad = 1
    item2.descuento_pct = Decimal("0")
    item2.impuesto_pct = Decimal("10")   # 10% sobre 50 = 5

    p.items = [item1, item2]
    p.subtotal = Decimal("0")
    p.impuesto_total = Decimal("0")
    p.total = Decimal("0")

    calcular_totales(p)
    # Subtotal = (200 - 10) + (50 - 0) = 240
    # Impuesto  = 19 + 5 = 24
    # Total = 264
    assert p.subtotal == Decimal("240")
    assert p.impuesto_total == Decimal("24")
    assert p.total == Decimal("264")

def test_dec():
    assert _dec(None) == Decimal("0")
    assert _dec(None, "5") == Decimal("5")
    assert _dec("10.5") == Decimal("10.5")

# --------------------
# Tests del servicio: crear auto-aprueba y orquesta
# --------------------
@patch('src.services.pedido.calcular_totales')
@patch('src.services.pedido.MsClient')
def test_crear_pedido_venta_autoaprueba_y_salida_fefo(mock_client_cls, mock_calc, service, mock_db):
    from uuid import uuid4

    payload = {
        "tipo": PedidoTipo.VENTA.value,
        "cliente_id": 1,
        "vendedor_id": 2,
        "bodega_origen_id": uuid4(),
        "items": [{
            "producto_id": uuid4(),
            "cantidad": 2,
            "precio_unitario": 100,
            "impuesto_pct": 10,
            "descuento_pct": 5
        }],
        "observaciones": "Test Venta"
    }

    # calcular_totales simulado
    def se(p):
        p.subtotal = Decimal("190.0")
        p.impuesto_total = Decimal("19.0")
        p.total = Decimal("209.0")
    mock_calc.side_effect = se

    # Mock MsClient.post -> respuesta **actual** de salida/fefo (lista de dicts)
    inv_id = uuid4()
    mock_client = MagicMock()
    mock_client.post.return_value = [{"inventario_id": str(inv_id), "consumido": 2}]
    mock_client_cls.return_value = mock_client

    pedido = service.crear(payload, x_country="co")

    # Estado final
    assert pedido.tipo == PedidoTipo.VENTA.value
    assert pedido.estado == PedidoEstado.APROBADO.value
    # reserva_token ahora es CSV de inventario_id; debe contener el inv_id retornado
    assert pedido.reserva_token is not None
    assert str(inv_id) in pedido.reserva_token

    # Llamadas a MsClient: salida FEFO por cada ítem (1 ítem)
    calls = [c for c in mock_client.post.call_args_list if "/v1/inventario/salida/fefo" in c.args[0]]
    assert len(calls) == 1
    _, kwargs = calls[0]
    assert "params" in kwargs and kwargs["params"]["cantidad"] == 2

    # Múltiples commits
    assert mock_db.commit.call_count >= 2
    mock_db.flush.assert_called_once()
    # Eventos registrados
    assert any(isinstance(a.args[0], PedidoEvento) for a in mock_db.add.call_args_list)

@patch('src.services.pedido.calcular_totales')
@patch('src.services.pedido.MsClient')
def test_crear_pedido_compra_autoaprueba_y_crea_oc(mock_client_cls, mock_calc, service, mock_db):
    payload = {
        "tipo": PedidoTipo.COMPRA.value,
        "proveedor_id": uuid4(),
        "bodega_destino_id": uuid4(),
        "items": [{"producto_id": uuid4(), "cantidad": 2, "precio_unitario": 50}],
        "observaciones": "Test Compra"
    }

    def se(p):
        p.subtotal = Decimal("100.0")
        p.impuesto_total = Decimal("0.0")
        p.total = Decimal("100.0")
    mock_calc.side_effect = se

    # Mock MsClient.post -> respuesta típica de crear OC
    mock_client = MagicMock()
    mock_client.post.return_value = {"id": str(uuid4())}
    mock_client_cls.return_value = mock_client

    pedido = service.crear(payload, x_country="co")

    # Estado final
    assert pedido.tipo == PedidoTipo.COMPRA.value
    assert pedido.estado == PedidoEstado.APROBADO.value
    assert pedido.oc_id is not None

    # Debe llamar a crear OC
    calls = [c for c in mock_client.post.call_args_list if "/v1/ordenes-compra" in c.args[0]]
    assert len(calls) == 1

    # Múltiples commits
    assert mock_db.commit.call_count >= 2
    mock_db.flush.assert_called_once()
