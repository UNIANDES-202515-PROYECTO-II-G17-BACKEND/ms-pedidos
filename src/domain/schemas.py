from pydantic import BaseModel, conint, condecimal
from typing import List, Optional, Literal, Union
from uuid import UUID
from datetime import datetime, date # ← nuevo

class ItemIn(BaseModel):
    producto_id: UUID
    cantidad: conint(gt=0)
    precio_unitario: Optional[condecimal(max_digits=14, decimal_places=4)] = None
    impuesto_pct: Optional[condecimal(max_digits=5, decimal_places=2)] = None
    descuento_pct: Optional[condecimal(max_digits=5, decimal_places=2)] = None
    sku: Optional[str] = None
    ubicacion_id: Optional[UUID] = None

class PedidoCompraCreate(BaseModel):
    tipo: Literal["COMPRA"] = "COMPRA"
    proveedor_id: UUID
    bodega_destino_id: UUID
    items: List[ItemIn]
    observaciones: Optional[str] = None
    fecha_recepcion: Optional[date] = None

class PedidoVentaCreate(BaseModel):
    tipo: Literal["VENTA"] = "VENTA"
    cliente_id: int
    vendedor_id: int
    bodega_origen_id: UUID
    items: List[ItemIn]
    observaciones: Optional[str] = None
    fecha_entrega: Optional[date] = None

PedidoCreate = Union[PedidoCompraCreate, PedidoVentaCreate]

class PedidoOut(BaseModel):
    id: UUID
    codigo: str
    tipo: Literal["COMPRA","VENTA"]
    estado: str
    proveedor_id: Optional[UUID] = None
    oc_id: Optional[UUID] = None
    cliente_id: Optional[int] = None
    vendedor_id: Optional[int] = None
    bodega_origen_id: Optional[UUID] = None
    bodega_destino_id: Optional[UUID] = None
    total: Optional[condecimal(max_digits=14, decimal_places=4)] = None
    items: List[ItemIn] = []
    fecha_compromiso: date