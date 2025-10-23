from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, String, DateTime, Integer, Numeric, ForeignKey, CheckConstraint, Index, Date
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

Base = declarative_base()

class Pedido(Base):
    __tablename__ = "pedido"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    codigo = Column(String(32), unique=True, nullable=False, index=True)
    tipo = Column(String(16), nullable=False)      # COMPRA|VENTA
    estado = Column(String(24), nullable=False, default="BORRADOR")
    observaciones = Column(String(500))

    fecha_compromiso = Column(Date, nullable=False)

    proveedor_id = Column(UUID(as_uuid=True), nullable=True)   # COMPRA
    oc_id = Column(UUID(as_uuid=True), nullable=True)          # ms-compras.orden_compra.id
    cliente_id = Column(Integer, nullable=True, index=True)    # VENTA (ms-usuarios)
    vendedor_id = Column(Integer, nullable=True, index=True)   # VENTA
    bodega_origen_id = Column(UUID(as_uuid=True), nullable=True)
    bodega_destino_id = Column(UUID(as_uuid=True), nullable=True)

    reserva_token = Column(String(64))  # VENTA
    fecha_creacion = Column(DateTime, default=datetime.utcnow, nullable=False)

    subtotal = Column(Numeric(14,4))
    impuesto_total = Column(Numeric(14,4))
    total = Column(Numeric(14,4))

    items = relationship("PedidoItem", back_populates="pedido", cascade="all, delete-orphan")
    eventos = relationship("PedidoEvento", back_populates="pedido", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "(tipo='COMPRA' AND proveedor_id IS NOT NULL AND bodega_destino_id IS NOT NULL) OR "
            "(tipo='VENTA' AND cliente_id IS NOT NULL AND vendedor_id IS NOT NULL AND bodega_origen_id IS NOT NULL)",
            name="ck_pedido_refs_por_tipo"
        ),
        Index("ix_pedido_tipo_estado", "tipo", "estado"),
    )

class PedidoItem(Base):
    __tablename__ = "pedido_item"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pedido_id = Column(UUID(as_uuid=True), ForeignKey("pedido.id", ondelete="CASCADE"), nullable=False)
    producto_id = Column(UUID(as_uuid=True), nullable=False)
    sku = Column(String(64))
    cantidad = Column(Integer, nullable=False)
    precio_unitario = Column(Numeric(14,4))
    impuesto_pct = Column(Numeric(5,2))
    descuento_pct = Column(Numeric(5,2))
    pedido = relationship("Pedido", back_populates="items")
    __table_args__ = (CheckConstraint("cantidad > 0", name="ck_item_cantidad_pos"),)

class PedidoEvento(Base):
    __tablename__ = "pedido_evento"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pedido_id = Column(UUID(as_uuid=True), ForeignKey("pedido.id", ondelete="CASCADE"), nullable=False)
    estado = Column(String(24), nullable=False)
    detalle = Column(String(500))
    quien_user_id = Column(Integer)   # ms-usuarios id
    cuando = Column(DateTime, default=datetime.utcnow, nullable=False)
    pedido = relationship("Pedido", back_populates="eventos")