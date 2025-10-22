from decimal import Decimal
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime, UTC
import logging
import json
import uuid

from src.domain.models import Pedido, PedidoItem, PedidoEvento
from src.domain.enums import PedidoTipo, PedidoEstado
from src.infrastructure.http import MsClient


log = logging.getLogger("PedidosService")

def _dec(v, d="0"):
    from decimal import Decimal
    return Decimal(str(v if v is not None else d))

def _safe_json(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return json.dumps({"detail": str(obj)}, ensure_ascii=False)

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

    def crear(self, payload: dict, x_country: str, ctx = None) -> Pedido:
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
        p.items = []
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
            p.items.append(item)

        calcular_totales(p)
        self._log(p, p.estado, {"message":"Creado", "items": len(p.items)}, ctx=ctx, evento="pedido_creado")
        self.db.commit(); self.db.refresh(p)

        # ---------- Auto-aprobar y orquestar ----------
        prev = p.estado
        p.estado = PedidoEstado.APROBADO.value
        self._log(p, p.estado, "Auto-aprobado al crear", ctx=ctx, evento="pedido_aprobado", de=prev)
        self.db.commit(); self.db.refresh(p)

        client = MsClient(x_country)

        if p.tipo == PedidoTipo.COMPRA.value:
            # Crear OC en ms-compras (dejar pedido en APROBADO)
            oc_payload = {
                "proveedor_id": str(p.proveedor_id),
                "pedido_ref": str(p.id),
                "moneda": "COP",
                "notas": p.observaciones or "",
                "items": [
                    {
                        "producto_id": str(it.producto_id),
                        "cantidad": int(it.cantidad),
                        "precio_unitario": float(it.precio_unitario or 0),
                        "impuesto_pct": float(it.impuesto_pct or 0),
                        "descuento_pct": float(it.descuento_pct or 0),
                        "sku_proveedor": it.sku or None
                    } for it in p.items
                ]
            }
            oc = client.post("/v1/ordenes-compra", json=oc_payload)  # espera { id, ... }
            if oc and oc.get("id"):
                p.oc_id = oc["id"]
                self._log(
                    p, p.estado,
                    {"message": "OC creada y vinculada", "oc_id": p.oc_id},
                    ctx=ctx, evento="oc_creada"
                )

        elif p.tipo == PedidoTipo.VENTA.value:
            # Salida FEFO por cada ítem (mantener estado APROBADO)
            tokens = []
            for it in p.items:
                resp = client.post(
                    "/v1/inventario/salida/fefo",
                    params={"producto_id": str(it.producto_id), "cantidad": int(it.cantidad)}
                )
                tokens.append((resp or {}).get("token") or "OK")
            p.reserva_token = ",".join(tokens)
            self._log(
                p, p.estado,
                {"message": "Salida FEFO completada", "tokens": tokens, "items": len(p.items)},
                ctx=ctx, evento="salida_fefo"
            )

        self.db.commit(); self.db.refresh(p)
        return p

    def marcar_recibido(self, pedido_id: UUID, x_country: str | None = None,  ctx = None) -> Pedido:
        p = self._ensure(pedido_id)
        if p.tipo != PedidoTipo.COMPRA.value:
            raise ValueError("Solo aplica para pedidos de COMPRA")
        if p.estado not in (PedidoEstado.APROBADO.value, PedidoEstado.EN_TRANSITO.value):
            raise ValueError("Transición no válida")

        prev = p.estado

        if x_country:
            client = MsClient(x_country)
            # Para cada item: crear lote (si no se definió), y registrar entrada
            for idx, it in enumerate(p.items, start=1):
                # 3.1 crear lote
                lote_code = f"LOTE-{p.codigo}-{idx:02d}"
                lote = client.post("/v1/inventario/lote", json={
                    "producto_id": str(it.producto_id),
                    "codigo": lote_code,
                    "vencimiento": None  # opcional: podrías inferir/recibirlo
                })
                lote_id = lote.get("id")

                # 3.2 obtener ubicacion_id
                ubicacion_id = getattr(it, "ubicacion_id", None)  # si extendiste esquema
                if not ubicacion_id:
                    # estrategia simple: crea una ubicación default en la bodega destino
                    ub = client.post("/v1/inventario/ubicacion", json={
                        "bodega_id": str(p.bodega_destino_id),
                        "pasillo": "A", "estante": "1", "posicion": "1"
                    })
                    ubicacion_id = ub.get("id")

                # 3.3 registrar entrada
                client.post("/v1/inventario/entrada", json={
                    "lote_id": lote_id,
                    "ubicacion_id": ubicacion_id,
                    "cantidad": int(it.cantidad),
                    "estado": "DISPONIBLE"
                })

        p.estado = PedidoEstado.RECIBIDO.value
        self._log(p, p.estado, "Recepción confirmada", ctx=ctx, evento="pedido_recibido", de=prev)
        self.db.commit(); self.db.refresh(p)
        return p

    def marcar_despachado(self, pedido_id: UUID, x_country: str | None = None, ctx = None) -> Pedido:
        p = self._ensure(pedido_id)
        if p.tipo != PedidoTipo.VENTA.value:
            raise ValueError("Solo aplica para pedidos de VENTA")
        if p.estado != PedidoEstado.APROBADO.value:
            raise ValueError("Transición no válida")
        prev = p.estado
        p.estado = PedidoEstado.DESPACHADO.value
        self._log(p, p.estado, "Despacho confirmado", ctx=ctx, evento="pedido_despachado", de=prev)

        self.db.commit(); self.db.refresh(p)
        return p

    # ----- comunes -----
    def cancelar(self, pedido_id: UUID, ctx=None) -> Pedido:
        p = self._ensure(pedido_id)
        if p.estado in (PedidoEstado.RECIBIDO.value, PedidoEstado.DESPACHADO.value, PedidoEstado.CANCELADO.value):
            raise ValueError("No se puede cancelar en este estado")
        prev = p.estado
        p.estado = PedidoEstado.CANCELADO.value
        self._log(p, p.estado, "Cancelado", ctx=ctx, evento="pedido_cancelado", de=prev)
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

    def _log(
            self,
            pedido: Pedido,
            estado: str,
            detalle: str | dict,
            quien_user_id: int | None = None,
            ctx=None,
            evento: str | None = None,
            de: str | None = None,
            extra: dict | None = None,
    ):
        inferred_who = quien_user_id
        if inferred_who is None:
            if pedido.tipo == PedidoTipo.VENTA.value:
                # cliente institucional
                inferred_who = getattr(pedido, "cliente_id", None)

        payload = {
            "event": evento or "state_change",
            "pedido_id": str(pedido.id),
            "codigo": pedido.codigo,
            "type": pedido.tipo,
            "from": de,
            "to": estado,
            "detail": detalle if isinstance(detalle, dict) else {"message": str(detalle)},
            "who": inferred_who,
            "ctx": {
                "request_id": getattr(ctx, "request_id", None) if ctx else None,
                "country": getattr(ctx, "country", None) if ctx else None,
                "ip": getattr(ctx, "ip", None) if ctx else None,
                "user_id": getattr(ctx, "user_id", None) if ctx else None,
            },
        }
        if extra:
            payload["extra"] = extra

        self.db.add(PedidoEvento(
            pedido_id=pedido.id,
            estado=estado,
            detalle=_safe_json(payload),
            quien_user_id=inferred_who,  # 👈 persistimos el mismo valor
        ))

        try:
            log.info(_safe_json({"audit": payload}))
        except Exception:
            pass

