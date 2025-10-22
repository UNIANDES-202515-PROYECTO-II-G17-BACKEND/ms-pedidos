from fastapi import APIRouter, Depends, HTTPException, Query, Path, status, Header
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from src.dependencies import get_session
from src.domain import schemas
from src.services.pedido import PedidosService
from src.dependencies import audit_context, AuditContext
from src.config import settings

router = APIRouter(prefix="/v1/pedidos", tags=["Pedidos"])

def svc(db: Session): return PedidosService(db)

@router.post("", response_model=schemas.PedidoOut, status_code=status.HTTP_201_CREATED)
def crear_pedido(
    body: schemas.PedidoCreate,
    session: Session = Depends(get_session),
    x_country: str = Header(..., alias=settings.COUNTRY_HEADER),  # ← NUEVO
    ctx: AuditContext = Depends(audit_context),
):
    try:
        return svc(session).crear(body.model_dump(), x_country=x_country, ctx=ctx)  # ← pasa el header
    except ValueError as e:
        raise HTTPException(400, detail=str(e))

@router.get("", response_model=List[schemas.PedidoOut])
def listar_pedidos(tipo: Optional[str]=Query(None), estado: Optional[str]=Query(None),
                   limit:int=Query(50, ge=1, le=200), offset:int=Query(0, ge=0),
                   session: Session = Depends(get_session)):
    return svc(session).listar(tipo, estado, limit, offset)

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
