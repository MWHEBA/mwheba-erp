"""
استيرادات نماذج المشتريات
"""
# استيراد النماذج من المجلدات المنفصلة
from purchase.models.purchase import Purchase
from purchase.models.purchase_item import PurchaseItem
from purchase.models.payment import PurchasePayment
from purchase.models.return_model import PurchaseReturn, PurchaseReturnItem

# استيراد نموذج أمر الشراء إذا كان موجوداً
try:
    from purchase.models.purchase_order import PurchaseOrder, PurchaseOrderItem
except ImportError:
    pass

# تم نقل جميع التعريفات الفعلية إلى مجلد purchase/models/ 