"""
استيرادات نماذج المبيعات
"""
# استيراد النماذج من المجلدات المنفصلة
from sale.models.sale import Sale
from sale.models.sale_item import SaleItem
from sale.models.payment import SalePayment
from sale.models.return_model import SaleReturn, SaleReturnItem

# تم نقل جميع التعريفات الفعلية إلى مجلد sale/models/ 