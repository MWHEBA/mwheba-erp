"""
استيراد جميع النماذج للمنتجات
"""

# استيراد النماذج الأساسية
from .base_models import *

# النماذج المحسنة الجديدة
try:
    from .warehouse import ProductStock, StockTransfer, StockSnapshot
    from .inventory_movement import (
        InventoryMovement,
        InventoryAdjustment,
        InventoryAdjustmentItem,
    )
    from .reservation_system import (
        StockReservation,
        ReservationFulfillment,
        ReservationRule,
    )
    from .expiry_tracking import (
        ProductBatch,
        BatchConsumption,
        BatchReservation,
        ExpiryAlert,
        ExpiryRule,
    )
    from .location_system import (
        LocationZone,
        LocationAisle,
        LocationShelf,
        ProductLocation,
        LocationMovement,
        LocationTask,
    )
except ImportError:
    # في حالة عدم توفر النماذج الجديدة، استخدم None
    ProductStock = StockTransfer = StockSnapshot = None
    InventoryMovement = InventoryAdjustment = InventoryAdjustmentItem = None
    StockReservation = ReservationFulfillment = ReservationRule = None
    ProductBatch = BatchConsumption = BatchReservation = None
    ExpiryAlert = ExpiryRule = None
    LocationZone = LocationAisle = LocationShelf = None
    ProductLocation = LocationMovement = LocationTask = None

# تصدير جميع النماذج (الأساسية والمحسنة)
__all__ = [
    # النماذج الأساسية من base_models
    "Category",
    "Brand",
    "Unit",
    "Product",
    "ProductImage",
    "ProductVariant",
    "Warehouse",
    "Stock",
    "StockMovement",
    "SerialNumber",
    "SupplierProductPrice",
    "PriceHistory",
    # النماذج المحسنة - المخازن
    "ProductStock",
    "StockTransfer",
    "StockSnapshot",
    # النماذج المحسنة - حركات المخزون
    "InventoryMovement",
    "InventoryAdjustment",
    "InventoryAdjustmentItem",
    # نظام الحجوزات
    "StockReservation",
    "ReservationFulfillment",
    "ReservationRule",
    # نظام انتهاء الصلاحية
    "ProductBatch",
    "BatchConsumption",
    "BatchReservation",
    "ExpiryAlert",
    "ExpiryRule",
    # نظام المواقع
    "LocationZone",
    "LocationAisle",
    "LocationShelf",
    "ProductLocation",
    "LocationMovement",
    "LocationTask",
]
