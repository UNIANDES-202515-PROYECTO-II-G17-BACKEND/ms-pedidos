# tests/test_service_pedidos.py
import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4
from decimal import Decimal
from datetime import datetime

from src.services.pedido import PedidosService, calcular_totales, _dec
from src.domain.models import Pedido, PedidoItem, PedidoEvento
from src.domain.enums import PedidoTipo, PedidoEstado

@pytest.fixture
def mock_db():
    db = MagicMock(name="Session")

    def add_side_effect(obj):
        if hasattr(obj, "id") and getattr(obj, "id", None) is None:
            setattr(obj, "id", uuid4())
        return None

    db.add.side_effect = add_side_effect
    db.flush.return_value = None
    db.commit.return_value = None
    db.rollback.return_value = None
    db.refresh.side_effect = lambda x: x
    db.query.return_value = MagicMock()
    return db

@pytest.fixture
def service(mock_db):
    return PedidosService(mock_db)

def test_gen_codigo_compra(service):
    codigo = service._gen_codigo(PedidoTipo.COMPRA.value)
    assert codigo.startswith("PO-")
    assert f"-{datetime.utcnow().year}-" in codigo

def test_gen_codigo_venta(service):
    codigo = service._gen_codigo(PedidoTipo.VENTA.value)
    assert codigo.startswith("SO-")
    assert f"-{datetime.utcnow().year}-" in codigo

@patch('src.services.pedido.calcular_totales')
def test_crear_pedido_venta_success(mock_calc, service, mock_db):
    payload = {
        "tipo": PedidoTipo.VENTA.value,
        "cliente_id": 1,
        "vendedor_id": 2,
        "bodega_origen_id": uuid4(),
        "items": [{"producto_id": uuid4(), "cantidad": 1, "precio_unitario": 100, "impuesto_pct": 10, "descuento_pct": 5}],
        "observaciones": "Test Venta"
    }

    def se(p):
        p.subtotal = Decimal("95.0")
        p.impuesto_total = Decimal("9.5")
        p.total = Decimal("104.5")
        p.items = [PedidoItem(
            pedido_id=p.id,
            producto_id=payload["items"][0]["producto_id"],
            cantidad=1,
            precio_unitario=Decimal("100"),
            impuesto_pct=Decimal("10"),
            descuento_pct=Decimal("5"),
        )]
    mock_calc.side_effect = se

    pedido = service.crear(payload)
    assert pedido.tipo == PedidoTipo.VENTA.value
    assert pedido.estado == PedidoEstado.BORRADOR.value
    assert pedido.subtotal == Decimal("95.0")
    assert any(isinstance(a.args[0], Pedido) for a in mock_db.add.call_args_list)
    assert any(isinstance(a.args[0], PedidoItem) for a in mock_db.add.call_args_list)
    assert any(isinstance(a.args[0], PedidoEvento) for a in mock_db.add.call_args_list)
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_called_once()

@patch('src.services.pedido.calcular_totales')
def test_crear_pedido_compra_success(mock_calc, service, mock_db):
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
        p.items = [PedidoItem(
            pedido_id=p.id,
            producto_id=payload["items"][0]["producto_id"],
            cantidad=2,
            precio_unitario=Decimal("50"),
        )]
    mock_calc.side_effect = se

    pedido = service.crear(payload)
    assert pedido.tipo == PedidoTipo.COMPRA.value
    assert pedido.estado == PedidoEstado.BORRADOR.value
    assert pedido.total == Decimal("100.0")
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_called_once()

def test_aprobar_pedido_success(service, mock_db):
    pid = uuid4()
    p = Pedido(id=pid, estado=PedidoEstado.BORRADOR.value, tipo=PedidoTipo.VENTA.value)
    mock_db.get.return_value = p

    res = service.aprobar(pid)
    assert res.estado == PedidoEstado.APROBADO.value
    mock_db.commit.assert_called_once()

def test_aprobar_pedido_invalid(service, mock_db):
    pid = uuid4()
    p = Pedido(id=pid, estado=PedidoEstado.APROBADO.value, tipo=PedidoTipo.VENTA.value)
    mock_db.get.return_value = p
    with pytest.raises(ValueError, match="Transición no válida"):
        service.aprobar(pid)

def test_link_oc_success(service, mock_db):
    pid, ocid = uuid4(), uuid4()
    p = Pedido(id=pid, tipo=PedidoTipo.COMPRA.value, estado=PedidoEstado.APROBADO.value, oc_id=None)
    mock_db.get.return_value = p
    res = service.link_oc(pid, ocid)
    assert res.oc_id == ocid
    assert res.estado == PedidoEstado.EN_TRANSITO.value

def test_link_oc_wrong_type(service, mock_db):
    pid, ocid = uuid4(), uuid4()
    p = Pedido(id=pid, tipo=PedidoTipo.VENTA.value, estado=PedidoEstado.APROBADO.value)
    mock_db.get.return_value = p
    with pytest.raises(ValueError, match="Solo aplica para pedidos de COMPRA"):
        service.link_oc(pid, ocid)

def test_marcar_recibido_success(service, mock_db):
    pid = uuid4()
    p = Pedido(id=pid, tipo=PedidoTipo.COMPRA.value, estado=PedidoEstado.EN_TRANSITO.value)
    mock_db.get.return_value = p
    res = service.marcar_recibido(pid)
    assert res.estado == PedidoEstado.RECIBIDO.value

def test_set_reserva_success(service, mock_db):
    pid = uuid4()
    p = Pedido(id=pid, tipo=PedidoTipo.VENTA.value, estado=PedidoEstado.APROBADO.value, reserva_token=None)
    mock_db.get.return_value = p
    res = service.set_reserva(pid, "RT-1")
    assert res.reserva_token == "RT-1"

def test_marcar_despachado_success(service, mock_db):
    pid = uuid4()
    p = Pedido(id=pid, tipo=PedidoTipo.VENTA.value, estado=PedidoEstado.APROBADO.value)
    mock_db.get.return_value = p
    res = service.marcar_despachado(pid)
    assert res.estado == PedidoEstado.DESPACHADO.value

def test_cancelar_pedido_success(service, mock_db):
    pid = uuid4()
    p = Pedido(id=pid, estado=PedidoEstado.BORRADOR.value)
    mock_db.get.return_value = p
    res = service.cancelar(pid)
    assert res.estado == PedidoEstado.CANCELADO.value

def test_calcular_totales():
    item1 = MagicMock(spec=PedidoItem)
    item1.precio_unitario = Decimal("100")
    item1.cantidad = 1
    item1.descuento_pct = Decimal("10")
    item1.impuesto_pct = Decimal("15")

    item2 = MagicMock(spec=PedidoItem)
    item2.precio_unitario = Decimal("50")
    item2.cantidad = 2
    item2.descuento_pct = Decimal("0")
    item2.impuesto_pct = Decimal("0")

    p = MagicMock(spec=Pedido)
    p.items = [item1, item2]
    p.subtotal = Decimal("0")
    p.impuesto_total = Decimal("0")
    p.total = Decimal("0")

    calcular_totales(p)
    assert p.subtotal == Decimal("190.0")
    assert p.impuesto_total == Decimal("13.5")
    assert p.total == Decimal("203.5")

def test_dec():
    assert _dec(None) == Decimal("0")
    assert _dec(None, "5") == Decimal("5")
    assert _dec("10.5") == Decimal("10.5")
