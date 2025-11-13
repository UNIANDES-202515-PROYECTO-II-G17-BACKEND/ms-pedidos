from fastapi import (APIRouter, Depends, HTTPException, Query, Path,
                     Request, Response, status, Header)
from sqlalchemy.orm import Session
import json
import base64
import logging

from src.services.pedido import PedidosService
from src.dependencies import session_for_schema
from src.config import settings


router = APIRouter(prefix="/pubsub", tags=["PubSub"])

log = logging.getLogger(__name__)

def svc(db: Session): return PedidosService(db)


@router.post("", status_code=204)
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