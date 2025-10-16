from enum import Enum
class PedidoTipo(str, Enum):
    COMPRA = "COMPRA"
    VENTA = "VENTA"

class PedidoEstado(str, Enum):
    BORRADOR = "BORRADOR"
    PENDIENTE_APROBACION = "PENDIENTE_APROBACION"
    APROBADO = "APROBADO"
    EN_TRANSITO = "EN_TRANSITO"  # solo COMPRA
    RECIBIDO = "RECIBIDO"        # solo COMPRA
    DESPACHADO = "DESPACHADO"    # solo VENTA
    CANCELADO = "CANCELADO"
