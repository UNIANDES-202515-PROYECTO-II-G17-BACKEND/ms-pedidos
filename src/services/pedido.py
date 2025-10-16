from decimal import Decimal
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime, UTC
import uuid

from src.domain.models import Pedido, PedidoItem, PedidoEvento
from src.domain.enums import PedidoTipo, PedidoEstado

def _dec(v, d="0"):
    from decimal import Decimal
    return Decimal(str(v if v is not None else d))

def calcular_totales(pedido: Pedido):
    sub = Decimal("0"); imp = Decimal("0")
    for it in pedido.items:
        li = _dec(it.precio_unitario) * it.cantidad
        dsc = li * _dec(it.descuento_pct) / 100
        neto = li - dsc
        imp += neto * _dec(it.impuesto_pct) / 100
        sub += neto
    pedido.subtotal = sub; pedido.impuesto_total = imp; pedido.total = sub + imp

class PedidosService:
    def __init__(self, db: Session):
        self.db = db

    def _gen_codigo(self, tipo: str) -> str:
        pref = "PO" if tipo == PedidoTipo.COMPRA.value else "SO"
        return f"{pref}-{datetime.now(UTC).year}-{uuid.uuid4().hex[:6].upper()}"

    def crear(self, payload: dict) -> Pedido:
        tipo = payload["tipo"]
        p = Pedido(
            codigo=self._gen_codigo(tipo),
            tipo=tipo,
            estado=PedidoEstado.BORRADOR.value,
            proveedor_id=payload.get("proveedor_id"),
            bodega_destino_id=payload.get("bodega_destino_id"),
            cliente_id=payload.get("cliente_id"),
            vendedor_id=payload.get("vendedor_id"),
            bodega_origen_id=payload.get("bodega_origen_id"),
            observaciones=payload.get("observaciones"),
        )
        self.db.add(p); self.db.flush()
        p.items = [] # Initialize the items list for the Pedido object
        for it in payload["items"]:
            item = PedidoItem(
                pedido_id=p.id,
                producto_id=it["producto_id"],
                cantidad=it["cantidad"],
                precio_unitario=it.get("precio_unitario"),
                impuesto_pct=it.get("impuesto_pct"),
                descuento_pct=it.get("descuento_pct"),
                sku=it.get("sku"),
            )
            self.db.add(item)
            p.items.append(item) # Add item to the pedido's items list
        calcular_totales(p)
        self._log(p, p.estado, "Creado")
        self.db.commit(); self.db.refresh(p)
        return p

    def aprobar(self, pedido_id: UUID) -> Pedido:
        p = self._ensure(pedido_id)
        if p.estado not in (PedidoEstado.BORRADOR.value, PedidoEstado.PENDIENTE_APROBACION.value):
            raise ValueError("Transición no válida")
        # Sólo cambia estado local. El FE hará llamadas externas.
        p.estado = PedidoEstado.APROBADO.value
        self._log(p, p.estado, "Aprobado (sin orquestación)")
        self.db.commit(); self.db.refresh(p)
        return p

    # ----- COMPRA: set OC y marcar recibido (después de ms-compras/ms-inventario) -----
    def link_oc(self, pedido_id: UUID, oc_id: UUID) -> Pedido:
        p = self._ensure(pedido_id)
        if p.tipo != PedidoTipo.COMPRA.value:
            raise ValueError("Solo aplica para pedidos de COMPRA")
        # idempotente
        if p.oc_id != oc_id:
            p.oc_id = oc_id
        # opcional: mover a EN_TRANSITO si ya estaba APROBADO
        if p.estado == PedidoEstado.APROBADO.value:
            p.estado = PedidoEstado.EN_TRANSITO.value
        self._log(p, p.estado, f"OC vinculada {oc_id}")
        self.db.commit(); self.db.refresh(p)
        return p

    def marcar_recibido(self, pedido_id: UUID) -> Pedido:
        p = self._ensure(pedido_id)
        if p.tipo != PedidoTipo.COMPRA.value:
            raise ValueError("Solo aplica para pedidos de COMPRA")
        if p.estado not in (PedidoEstado.APROBADO.value, PedidoEstado.EN_TRANSITO.value):
            raise ValueError("Transición no válida")
        p.estado = PedidoEstado.RECIBIDO.value
        self._log(p, p.estado, "Recepción confirmada (por FE)")
        self.db.commit(); self.db.refresh(p)
        return p

    # ----- VENTA: set reserva y marcar despachado (después de ms-inventario) -----
    def set_reserva(self, pedido_id: UUID, reserva_token: str) -> Pedido:
        p = self._ensure(pedido_id)
        if p.tipo != PedidoTipo.VENTA.value:
            raise ValueError("Solo aplica para pedidos de VENTA")
        # idempotente
        p.reserva_token = reserva_token
        self._log(p, p.estado, f"Reserva vinculada")
        self.db.commit(); self.db.refresh(p)
        return p

    def marcar_despachado(self, pedido_id: UUID) -> Pedido:
        p = self._ensure(pedido_id)
        if p.tipo != PedidoTipo.VENTA.value:
            raise ValueError("Solo aplica para pedidos de VENTA")
        if p.estado != PedidoEstado.APROBADO.value:
            raise ValueError("Transición no válida")
        p.estado = PedidoEstado.DESPACHADO.value
        self._log(p, p.estado, "Despacho confirmado (por FE)")
        self.db.commit(); self.db.refresh(p)
        return p

    # ----- comunes -----
    def cancelar(self, pedido_id: UUID) -> Pedido:
        p = self._ensure(pedido_id)
        if p.estado in (PedidoEstado.RECIBIDO.value, PedidoEstado.DESPACHADO.value, PedidoEstado.CANCELADO.value):
            raise ValueError("No se puede cancelar en este estado")
        p.estado = PedidoEstado.CANCELADO.value
        self._log(p, p.estado, "Cancelado")
        self.db.commit(); self.db.refresh(p)
        return p

    def obtener(self, pedido_id: UUID) -> Pedido | None:
        return self.db.get(Pedido, pedido_id)

    def listar(self, tipo: str | None, estado: str | None, limit: int, offset: int):
        q = self.db.query(Pedido)
        if tipo: q = q.filter(Pedido.tipo == tipo)
        if estado: q = q.filter(Pedido.estado == estado)
        return q.order_by(Pedido.fecha_creacion.desc()).offset(offset).limit(limit).all()

    def _ensure(self, pedido_id: UUID) -> Pedido:
        p = self.obtener(pedido_id)
        if not p: raise ValueError("Pedido no encontrado")
        return p

    def _log(self, pedido: Pedido, estado: str, detalle: str, quien_user_id: int | None = None):
        self.db.add(PedidoEvento(pedido_id=pedido.id, estado=estado, detalle=detalle, quien_user_id=quien_user_id))
