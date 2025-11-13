from fastapi import (APIRouter, Depends, HTTPException, Query, Path,
                     Request, Response, status, Header)
from sqlalchemy.orm import Session
from datetime import date
from typing import List, Optional
from uuid import UUID
import json
import base64
import logging

from src.dependencies import get_session
from src.domain import schemas
from src.services.pedido import PedidosService
from src.dependencies import audit_context, AuditContext
from src.dependencies import session_for_schema
from src.config import settings

router = APIRouter(prefix="/v1/pedidos", tags=["Pedidos"])

log = logging.getLogger(__name__)

def svc(db: Session): return PedidosService(db)

@router.post("", response_model=schemas.PedidoOut, status_code=status.HTTP_201_CREATED)
def crear_pedido(
    body: schemas.PedidoCreate,
    session: Session = Depends(get_session),
    x_country: str = Header(..., alias=settings.COUNTRY_HEADER),  # Sigue siendo obligatorio
    ctx: AuditContext = Depends(audit_context),
):
    """
    Creación de pedido:
    - VENTA: fecha_entrega opcional -> si no viene, se usará hoy+1.
    - COMPRA: fecha_recepcion opcional -> si no viene, se calculará usando lead_time (ms-compras).
    """
    try:
        return svc(session).crear(body.model_dump(), x_country=x_country, ctx=ctx)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("", response_model=List[schemas.PedidoOut])
def listar_pedidos(
    tipo: Optional[str] = Query(None),
    estado: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    # nuevos filtros
    fecha_compromiso: Optional[date] = Query(None),
    fc_desde: Optional[date] = Query(None),
    fc_hasta: Optional[date] = Query(None),
    session: Session = Depends(get_session),
):
    # ✅ si no hay filtros de fecha, conserva exactamente la firma original (4 posicionales)
    if not (fecha_compromiso or fc_desde or fc_hasta):
        return svc(session).listar(tipo, estado, limit, offset)

    # ✅ si hay filtros de fecha, pasa kwargs para que el test pueda leerlos en kwargs
    return svc(session).listar(
        tipo, estado, limit, offset,
        fecha_compromiso=fecha_compromiso,
        fc_desde=fc_desde,
        fc_hasta=fc_hasta,
    )

@router.get("/{pedido_id}", response_model=schemas.PedidoOut)
def obtener_pedido(pedido_id: UUID, session: Session = Depends(get_session)):
    p = svc(session).obtener(pedido_id)
    if not p: raise HTTPException(404, detail="Pedido no encontrado")
    return p

@router.post("/{pedido_id}/marcar-recibido", response_model=schemas.PedidoOut)
def marcar_recibido(pedido_id: UUID, session: Session = Depends(get_session)):
    try:
        return svc(session).marcar_recibido(pedido_id)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))

@router.post("/{pedido_id}/marcar-despachado", response_model=schemas.PedidoOut)
def marcar_despachado(pedido_id: UUID, session: Session = Depends(get_session)):
    try:
        return svc(session).marcar_despachado(pedido_id)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))

@router.post("/{pedido_id}/cancelar", response_model=schemas.PedidoOut)
def cancelar_pedido(pedido_id: UUID, session: Session = Depends(get_session)):
    try:
        return svc(session).cancelar(pedido_id)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))

@router.post("/pubsub", status_code=204)
async def handle_pubsub_push(request: Request):
    """
    Endpoint receptor de Pub/Sub (Push).
    Recibe un envelope estándar:
    {
      "message": {
        "data": "<base64(JSON)>",
        "attributes": {},
        "messageId": "...",
        "publishTime": "..."
      },
      "subscription": "projects/.../subscriptions/..."
    }

    El JSON decodificado debe contener:
    {
      "event": "pedido_recibido | pedido_despachado | pedido_cancelado | ...",
      "pedido_id": "...",
      "ctx": { "country": "co", ... }
    }
    """
    try:
        envelope = await request.json()
    except Exception as e:
        log.error(f"[PUBSUB] Envelope inválido: {e}")
        return Response(status_code=204)

    message = envelope.get("message")
    if not message:
        log.warning("[PUBSUB] Envelope sin 'message'")
        return Response(status_code=204)

    # ---------------------------
    # 1. Decodificar data base64
    # ---------------------------
    data_b64 = message.get("data")
    if not data_b64:
        log.warning("[PUBSUB] message.data faltante")
        return Response(status_code=204)

    try:
        raw = base64.b64decode(data_b64).decode("utf-8")
        event = json.loads(raw)
    except Exception as e:
        log.error(f"[PUBSUB] Error decodificando data: {e}")
        return Response(status_code=204)

    # ---------------------------
    # 2. Extraer contexto + país
    # ---------------------------
    ctx_dict = event.get("ctx") or {}
    event_type = event.get("event")

    if not event_type:
        log.warning(f"[PUBSUB] Evento sin 'event': {event}")
        return Response(status_code=204)

    country = (
        ctx_dict.get("country")
        or event.get("country")
        or settings.DEFAULT_SCHEMA
    )

    # ---------------------------
    # 3. Crear sesión por schema
    # ---------------------------
    with session_for_schema(country) as session:
        service = PedidosService(session)

        try:
            # ===== DISPATCH por tipo de evento =====
            if event_type == "pedido_recibido":
                service.marcar_recibido(
                    event["pedido_id"],
                    x_country=country,
                    ctx=ctx_dict,
                )
                log.info(f"[PUBSUB] pedido_recibido procesado OK")

            elif event_type == "pedido_despachado":
                service.marcar_despachado(
                    event["pedido_id"],
                    x_country=country,
                    ctx=ctx_dict,
                )
                log.info("[PUBSUB] pedido_despachado procesado OK")

            elif event_type == "pedido_cancelado":
                service.cancelar(
                    event["pedido_id"],
                    ctx=ctx_dict,
                )
                log.info("[PUBSUB] pedido_cancelado procesado OK")

            else:
                log.info(f"[PUBSUB] Evento no manejado: {event_type}")

        except ValueError as e:
            # Error de negocio → NO reintentar
            log.warning(f"[PUBSUB] Error de negocio en {event_type}: {e}")

        except Exception as e:
            # Error inesperado → pero respondemos 204 para evitar loops
            # (Pub/Sub reintentaría si devolvemos 5xx)
            log.error(f"[PUBSUB] Error procesando {event_type}: {e}")

    return Response(status_code=204)