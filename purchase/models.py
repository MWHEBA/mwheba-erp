"""
استيرادات نماذج المشتريات
"""
# استيراد النماذج من المجلدات المنفصلة
from purchase.models.purchase import Purchase
from purchase.models.purchase_item import PurchaseItem
from purchase.models.payment import PurchasePayment
from purchase.models.return_model import PurchaseReturn, PurchaseReturnItem


# تم نقل جميع التعريفات الفعلية إلى مجلد purchase/models/
