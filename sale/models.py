"""
استيرادات نماذج المبيعات
"""
# استيراد النماذج من المجلدات المنفصلة
from sale.models.sale import Sale
from sale.models.sale_item import SaleItem
from sale.models.payment import SalePayment
from sale.models.return_model import SaleReturn, SaleReturnItem
from sale.models.quotation import Quotation
from sale.models.quotation_item import QuotationItem

# تم نقل جميع التعريفات الفعلية إلى مجلد sale/models/
