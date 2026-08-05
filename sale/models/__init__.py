from sale.models.sale import Sale
from sale.models.sale_item import SaleItem
from sale.models.payment import SalePayment
from sale.models.return_model import SaleReturn, SaleReturnItem
from sale.models.quotation import Quotation
from sale.models.quotation_item import QuotationItem
from sale.models.custom_field import CustomFieldDefinition

try:
    from sale.models.sales_models import SalesOrder, SalesOrderItem, DeliveryNote, DeliveryNoteItem, SalesInvoice, SalesInvoiceItem
    from sale.models.sales_return import ReturnAuthorization, SalesReturnHeader, SalesReturnItem, SalesReturnInspection, ReturnCostTrace, SalesReturnAudit
    from sale.models.credit_note import CreditNote, CreditNoteItem, CreditNoteAllocation, CreditNoteReversal, CreditNoteAudit
except Exception:
    pass
