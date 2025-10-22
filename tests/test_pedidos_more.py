import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4
from decimal import Decimal
from src.services.pedido import PedidosService
from src.domain.models import Pedido, PedidoItem
from src.domain.enums import PedidoTipo, PedidoEstado

@pytest.fixture
def db():
    db = MagicMock(name="Session")
    db.add.side_effect = lambda obj: setattr(obj, "id", getattr(obj, "id", uuid4()))
    db.flush.return_value = None
    db.commit.return_value = None
    db.refresh.side_effect = lambda x: x
    db.get.side_effect = lambda model, pid: None
    db.query.return_value = MagicMock()
    return db

@pytest.fixture
def service(db):
    return PedidosService(db)

def _build_pedido(service, tipo):
    payload = {
        "tipo": tipo,
        "proveedor_id": uuid4(),
        "bodega_destino_id": uuid4(),
        "cliente_id": 1,
        "vendedor_id": 2,
        "bodega_origen_id": uuid4(),
        "items": [{
            "producto_id": uuid4(),
            "cantidad": 1,
            "precio_unitario": 10
        }],
        "observaciones": "obs"
    }
    with patch('src.services.pedido.MsClient') as mc, patch('src.services.pedido.calcular_totales') as ct:
        ct.side_effect = lambda p: setattr(p, "total", Decimal("10"))
        mc.return_value.post.return_value = {"id": str(uuid4())}
        p = service.crear(payload, x_country="co")
    return p

def test_cancelar_en_borrador(service, db):
    p = Pedido(codigo="X", tipo=PedidoTipo.VENTA.value, estado=PedidoEstado.BORRADOR.value)
    db.get.side_effect = lambda model, pid: p
    out = service.cancelar(uuid4())
    assert out.estado == PedidoEstado.CANCELADO.value

def test_cancelar_estado_no_permitido(service, db):
    p = Pedido(codigo="X", tipo=PedidoTipo.COMPRA.value, estado=PedidoEstado.RECIBIDO.value)
    db.get.side_effect = lambda model, pid: p
    with pytest.raises(ValueError):
        service.cancelar(uuid4())

def test_marcar_despachado_valido(service, db):
    p = Pedido(codigo="X", tipo=PedidoTipo.VENTA.value, estado=PedidoEstado.APROBADO.value)
    db.get.side_effect = lambda model, pid: p
    out = service.marcar_despachado(uuid4())
    assert out.estado == PedidoEstado.DESPACHADO.value

def test_marcar_despachado_tipo_invalido(service, db):
    p = Pedido(codigo="X", tipo=PedidoTipo.COMPRA.value, estado=PedidoEstado.APROBADO.value)
    db.get.side_effect = lambda model, pid: p
    with pytest.raises(ValueError):
        service.marcar_despachado(uuid4())

def test_marcar_despachado_estado_invalido(service, db):
    p = Pedido(codigo="X", tipo=PedidoTipo.VENTA.value, estado=PedidoEstado.BORRADOR.value)
    db.get.side_effect = lambda model, pid: p
    with pytest.raises(ValueError):
        service.marcar_despachado(uuid4())

def test_marcar_recibido_valido(service, db):
    p = Pedido(codigo="X", tipo=PedidoTipo.COMPRA.value, estado=PedidoEstado.EN_TRANSITO.value, bodega_destino_id=uuid4())
    it = PedidoItem(pedido_id=uuid4(), producto_id=uuid4(), cantidad=1)
    p.items = [it]
    db.get.side_effect = lambda model, pid: p
    with patch('src.services.pedido.MsClient') as mc:
        mc.return_value.post.side_effect = [
            {"id": str(uuid4())},  # lote
            {"id": str(uuid4())},  # ubicacion
            {"ok": True},          # entrada
        ]
        out = service.marcar_recibido(uuid4(), x_country="co")
    assert out.estado == PedidoEstado.RECIBIDO.value

def test_marcar_recibido_sin_x_country(service, db):
    # Si no hay x_country, debe cambiar a RECIBIDO sin llamar servicios externos
    p = Pedido(codigo="X", tipo=PedidoTipo.COMPRA.value, estado=PedidoEstado.EN_TRANSITO.value, bodega_destino_id=uuid4())
    it = PedidoItem(pedido_id=uuid4(), producto_id=uuid4(), cantidad=1)
    p.items = [it]
    db.get.side_effect = lambda model, pid: p
    out = service.marcar_recibido(uuid4(), x_country=None)
    assert out.estado == PedidoEstado.RECIBIDO.value

def test_marcar_recibido_tipo_invalido(service, db):
    p = Pedido(codigo="X", tipo=PedidoTipo.VENTA.value, estado=PedidoEstado.APROBADO.value)
    db.get.side_effect = lambda model, pid: p
    with pytest.raises(ValueError):
        service.marcar_recibido(uuid4())
