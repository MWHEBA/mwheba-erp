# -*- coding: utf-8 -*-
"""
خدمة موزع المستندات الموحد لمنظومة WhatsApp الرسمية من Meta
MWHEBA ERP — Universal WhatsApp Document Dispatcher & PDF Media Pipeline
"""
import io
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple, List

from django.conf import settings
from django.core.cache import cache
from django.contrib.contenttypes.models import ContentType
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import SystemSetting, WhatsAppMessageLog
from core.services.whatsapp_service import WhatsAppService

logger = logging.getLogger('core.services.whatsapp.dispatcher')


class DocumentDispatcher:
    """
    الموزع المركزي لكافة مستندات النظام الـ 20 عبر WhatsApp API
    المسؤول عن:
    - استخراج بيانات المستند والجهة المستلمة وخيارات أرقام الاتصال
    - التحقق من شروط الحالة (State Guard) لمنع إرسال المسودات والملغيات
    - تطبيق العقد البرمجي الصارم للقوالب الأربعة (Meta Strict Parameter Contracts)
    - توليد ملفات الـ PDF الثنائية مباشرة في الذاكرة (In-Memory Stream)
    - إدارة كاش الـ Media ID الزمني لتفادي الرفع المتكرر (Timestamp-based Media Cache)
    """

    MEDIA_CACHE_TTL = 25 * 86400  # 25 يوماً (سيرفرات Meta تحتفظ بالوسائط لـ 30 يوماً)

    # ==================== 1. استخراج بيانات المستند والشريك ====================

    @classmethod
    def get_document_info(cls, content_object: Any, partner: Any = None, extra_params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        استخراج البيانات الوصفية للمستند والشريك وتحديد القالب وصلاحية الإرسال
        """
        extra_params = extra_params or {}
        model_name = content_object.__class__.__name__
        site_name = SystemSetting.get_site_name()

        ct_id = None
        if content_object is not None and hasattr(content_object, "_meta"):
            try:
                ct_id = ContentType.objects.get_for_model(content_object).id
            except Exception:
                ct_id = None

        info = {
            "content_type_id": ct_id,
            "object_id": getattr(content_object, "pk", None),
            "model_name": model_name,
            "doc_title": "",
            "doc_number": "",
            "doc_number_bidi": "",
            "partner": partner,
            "partner_type": "customer",
            "partner_name": "",
            "phone_options": [],
            "status": "",
            "status_display": "",
            "can_send": True,
            "cannot_send_reason": "",
            "has_pdf": True,
            "pdf_filename": "Document.pdf",
            "template_name": "document_share_ar",
            "language_code": "ar",
            "financial_summary": "",
            "components": [],
            "site_name": site_name,
            "last_log": None,
        }

        # جلب آخر رسالة مرسلة لهذا المستند
        if content_object and hasattr(content_object, 'pk'):
            last_msg = WhatsAppMessageLog.objects.filter(
                content_type_id=info["content_type_id"],
                object_id=info["object_id"]
            ).order_by('-created_at').first()
            if last_msg:
                info["last_log"] = {
                    "id": last_msg.id,
                    "status": last_msg.status,
                    "status_display": last_msg.get_status_display(),
                    "recipient_phone": last_msg.recipient_phone,
                    "message_id": last_msg.message_id,
                    "created_at": last_msg.created_at.strftime("%Y-%m-%d %H:%M"),
                    "error_message": last_msg.error_message or "",
                }

        # ----------------------------------------------------
        # 1. فاتورة مبيعات (Sale)
        # ----------------------------------------------------
        if model_name == "Sale":
            info["doc_title"] = "فاتورة مبيعات"
            info["doc_number"] = getattr(content_object, "number", "")
            info["partner"] = partner or getattr(content_object, "customer", None)
            info["partner_type"] = "customer"
            info["status"] = getattr(content_object, "status", "")
            info["status_display"] = getattr(content_object, "get_status_display", lambda: info["status"])()
            info["pdf_filename"] = f"Invoice_{info['doc_number']}.pdf"

            # شرط الحالة: يجب أن تكون الفاتورة معتمدة
            if info["status"] != "confirmed":
                info["can_send"] = False
                info["cannot_send_reason"] = "لا يمكن إرسال الفاتورة عبر الواتساب قبل اعتمادها وترحيلها."

            grand_total = Decimal(str(getattr(content_object, "total", getattr(content_object, "grand_total", 0)) or 0))
            paid_amount = Decimal(str(getattr(content_object, "paid_amount", 0) or 0))
            remaining = Decimal(str(getattr(content_object, "remaining_amount", getattr(content_object, "remaining_total", grand_total - paid_amount)) or 0))
            currency_code = getattr(getattr(content_object, "currency", None), "symbol", "ج.م")

            info["financial_summary"] = f"الإجمالي: {WhatsAppService.format_currency_amount(grand_total, currency_code)} | المتبقي: {WhatsAppService.format_currency_amount(remaining, currency_code)}"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 2. عرض أسعار (Quotation)
        # ----------------------------------------------------
        elif model_name == "Quotation":
            info["doc_title"] = "عرض أسعار"
            info["doc_number"] = getattr(content_object, "number", "")
            info["partner"] = partner or getattr(content_object, "customer", None)
            info["partner_type"] = "customer"
            info["status"] = getattr(content_object, "status", "")
            info["status_display"] = getattr(content_object, "get_status_display", lambda: info["status"])()
            info["pdf_filename"] = f"Quotation_{info['doc_number']}.pdf"

            if info["status"] in ("cancelled", "rejected"):
                info["can_send"] = False
                info["cannot_send_reason"] = "لا يمكن إرسال عرض أسعار ملغي أو مرفوض."

            grand_total = Decimal(str(getattr(content_object, "total", getattr(content_object, "grand_total", 0)) or 0))
            currency_code = getattr(getattr(content_object, "currency", None), "symbol", "ج.م")
            info["financial_summary"] = f"إجمالي العرض: {WhatsAppService.format_currency_amount(grand_total, currency_code)}"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 3. أمر بيع / طلبية (SalesOrder)
        # ----------------------------------------------------
        elif model_name == "SalesOrder":
            info["doc_title"] = "أمر بيع"
            info["doc_number"] = getattr(content_object, "order_number", getattr(content_object, "number", f"#{content_object.pk}"))
            info["partner"] = partner or getattr(content_object, "customer", None)
            info["partner_type"] = "customer"
            info["status"] = getattr(content_object, "status", "")
            info["status_display"] = getattr(content_object, "get_status_display", lambda: info["status"])()
            info["pdf_filename"] = f"SalesOrder_{info['doc_number']}.pdf"

            grand_total = Decimal(str(getattr(content_object, "total_amount", getattr(content_object, "grand_total", getattr(content_object, "total", 0))) or 0))
            info["financial_summary"] = f"الإجمالي: {WhatsAppService.format_currency_amount(grand_total, 'ج.م')}"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 4. إذن تسليم بضاعة (DeliveryNote)
        # ----------------------------------------------------
        elif model_name == "DeliveryNote":
            info["doc_title"] = "إذن تسليم بضاعة"
            info["doc_number"] = getattr(content_object, "delivery_number", getattr(content_object, "number", f"#{content_object.pk}"))
            info["partner"] = partner or getattr(content_object, "customer", None)
            info["partner_type"] = "customer"
            info["status"] = getattr(content_object, "status", "")
            info["status_display"] = getattr(content_object, "get_status_display", lambda: info["status"])()
            info["pdf_filename"] = f"DeliveryNote_{info['doc_number']}.pdf"
            info["financial_summary"] = "إذن تسليم واستلام بضاعة معتمد"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 5. مرتجع مبيعات (SaleReturn)
        # ----------------------------------------------------
        elif model_name == "SaleReturn":
            info["doc_title"] = "مرتجع مبيعات"
            info["doc_number"] = getattr(content_object, "number", f"#{content_object.pk}")
            info["partner"] = partner or getattr(content_object, "customer", getattr(getattr(content_object, "sale", None), "customer", None))
            info["partner_type"] = "customer"
            info["status"] = getattr(content_object, "status", "")
            info["status_display"] = getattr(content_object, "get_status_display", lambda: info["status"])()
            info["pdf_filename"] = f"SaleReturn_{info['doc_number']}.pdf"

            if str(info["status"]).lower() not in ("confirmed", "approved"):
                info["can_send"] = False
                info["cannot_send_reason"] = "لا يمكن إرسال إشعار المرتجع قبل اعتماده."

            grand_total = Decimal(str(getattr(content_object, "total", getattr(content_object, "grand_total", 0)) or 0))
            info["financial_summary"] = f"إجمالي المرتجع: {WhatsAppService.format_currency_amount(grand_total, 'ج.م')}"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 6. إشعار دائن (CreditNote)
        # ----------------------------------------------------
        elif model_name == "CreditNote":
            info["doc_title"] = "إشعار دائن"
            info["doc_number"] = getattr(content_object, "credit_note_number", getattr(content_object, "number", f"#{content_object.pk}"))
            info["partner"] = partner or getattr(content_object, "customer", None)
            info["partner_type"] = "customer"
            info["status"] = getattr(content_object, "status", "")
            info["status_display"] = getattr(content_object, "get_status_display", lambda: info["status"])()
            info["pdf_filename"] = f"CreditNote_{info['doc_number']}.pdf"

            amount = Decimal(str(getattr(content_object, "total_amount", getattr(content_object, "amount", 0)) or 0))
            info["financial_summary"] = f"مبلغ الإشعار الدائن: {WhatsAppService.format_currency_amount(amount, 'ج.م')}"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 7. كشف حساب عميل (Customer Statement)
        # ----------------------------------------------------
        elif model_name == "Customer":
            info["doc_title"] = "كشف حساب عميل"
            info["partner"] = content_object
            info["partner_type"] = "customer"
            from_date = extra_params.get("from_date", "")
            to_date = extra_params.get("to_date", "")
            date_label = f"{from_date} إلى {to_date}" if from_date and to_date else "الفترة الشاملة"
            info["doc_number"] = f"{content_object.code} ({date_label})"
            info["pdf_filename"] = f"Statement_{content_object.code}.pdf"

            bal = Decimal(str(getattr(content_object, "balance", 0) or 0))
            info["financial_summary"] = f"الرصيد الحالي: {WhatsAppService.format_currency_amount(bal, 'ج.م')}"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 8 & 9. سندات القبض والدفع (Payment Vouchers / Receipts)
        # ----------------------------------------------------
        elif model_name in ("SalePayment", "CustomerPayment", "PurchasePayment", "SupplierPayment", "PaymentVoucher", "ReceiptVoucher", "IncomeTransaction", "ExpenseTransaction"):
            info["has_pdf"] = False
            info["template_name"] = "payment_receipt_ar"
            info["doc_number"] = getattr(content_object, "payment_code", getattr(content_object, "voucher_number", getattr(content_object, "number", getattr(content_object, "reference_number", f"#{content_object.pk}"))))

            if model_name in ("SalePayment", "CustomerPayment", "ReceiptVoucher", "IncomeTransaction"):
                info["doc_title"] = "سند قبض مالي"
                info["partner"] = partner or getattr(content_object, "customer", getattr(getattr(content_object, "sale", None), "customer", None))
                info["partner_type"] = "customer"
            else:
                info["doc_title"] = "سند صرف مالي"
                info["partner"] = partner or getattr(content_object, "supplier", getattr(getattr(content_object, "purchase", None), "supplier", None))
                info["partner_type"] = "supplier"

            amount = Decimal(str(getattr(content_object, "amount", 0) or 0))
            currency_code = getattr(getattr(content_object, "currency", None), "symbol", "ج.م")
            info["financial_summary"] = WhatsAppService.format_currency_amount(amount, currency_code)

        # ----------------------------------------------------
        # 10. إشعار مدين (DebitNote)
        # ----------------------------------------------------
        elif model_name == "DebitNote":
            info["doc_title"] = "إشعار مدين"
            info["doc_number"] = getattr(content_object, "number", f"#{content_object.pk}")
            info["partner"] = partner or getattr(content_object, "supplier", getattr(content_object, "customer", None))
            info["partner_type"] = "supplier" if hasattr(content_object, "supplier") else "customer"
            info["pdf_filename"] = f"DebitNote_{info['doc_number']}.pdf"
            amount = Decimal(str(getattr(content_object, "amount", 0) or 0))
            info["financial_summary"] = f"مبلغ الإشعار المدين: {WhatsAppService.format_currency_amount(amount, 'ج.م')}"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 10.b قيد يومية معتمد (JournalEntry)
        # ----------------------------------------------------
        elif model_name == "JournalEntry":
            info["doc_title"] = "إشعار قيد يومية"
            info["doc_number"] = getattr(content_object, "number", f"#{content_object.pk}")
            info["partner"] = partner
            info["pdf_filename"] = f"JV_{info['doc_number']}.pdf"
            total_dr = Decimal(str(getattr(content_object, "total_debit", 0) or 0))
            info["financial_summary"] = f"إجمالي القيد: {WhatsAppService.format_currency_amount(total_dr, 'ج.م')}"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 10.c مناقلات الخزائن والعهد (CustodyTransfer)
        # ----------------------------------------------------
        elif model_name in ("CustodyTransfer", "TreasuryTransfer"):
            info["doc_title"] = "إذن تحويل نقدية"
            info["doc_number"] = getattr(content_object, "number", getattr(content_object, "transfer_number", f"#{content_object.pk}"))
            info["has_pdf"] = False
            info["template_name"] = "order_status_ar"
            info["status_display"] = "تم التحويل بنجاح"
            amount = Decimal(str(getattr(content_object, "amount", 0) or 0))
            info["financial_summary"] = f"مبلغ التحويل: {WhatsAppService.format_currency_amount(amount, 'ج.م')}"

        # ----------------------------------------------------
        # 11. أمر شراء للمورد (PurchaseOrder)
        # ----------------------------------------------------
        elif model_name == "PurchaseOrder":
            info["doc_title"] = "أمر شراء"
            info["doc_number"] = getattr(content_object, "order_number", getattr(content_object, "number", f"PO-{content_object.pk}"))
            info["partner"] = partner or getattr(content_object, "supplier", None)
            info["partner_type"] = "supplier"
            info["status"] = getattr(content_object, "status", "")
            info["status_display"] = getattr(content_object, "get_status_display", lambda: info["status"])()
            info["pdf_filename"] = f"PO_{info['doc_number']}.pdf"

            if str(info["status"]).lower() not in ("confirmed", "approved"):
                info["can_send"] = False
                info["cannot_send_reason"] = "لا يمكن إرسال أمر الشراء للمورد قبل اعتماده."

            grand_total = Decimal(str(getattr(content_object, "total_amount", getattr(content_object, "grand_total", getattr(content_object, "total", 0))) or 0))
            info["financial_summary"] = f"إجمالي أمر الشراء: {WhatsAppService.format_currency_amount(grand_total, 'ج.م')}"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 12. إذن استلام بضاعة بالمخزن (GoodsReceivedNote / GRN)
        # ----------------------------------------------------
        elif model_name in ("GoodsReceivedNote", "GoodsReceiptNote"):
            info["doc_title"] = "إذن استلام بضاعة (GRN)"
            info["doc_number"] = getattr(content_object, "grn_number", getattr(content_object, "number", f"GRN-{content_object.pk}"))
            info["partner"] = partner or getattr(content_object, "supplier", getattr(getattr(content_object, "purchase_order", None), "supplier", None))
            info["partner_type"] = "supplier"
            info["status"] = getattr(content_object, "status", "")
            info["status_display"] = getattr(content_object, "get_status_display", lambda: info["status"])()
            info["pdf_filename"] = f"GRN_{info['doc_number']}.pdf"
            info["financial_summary"] = "إذن استلام بضاعة معتمد بالمخزن"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 12.b فاتورة مشتريات / مطالبة مورد (Purchase / SupplierBill)
        # ----------------------------------------------------
        elif model_name in ("Purchase", "SupplierBill"):
            info["doc_title"] = "فاتورة مشتريات"
            info["doc_number"] = getattr(content_object, "number", f"PUR-{content_object.pk}")
            info["partner"] = partner or getattr(content_object, "supplier", None)
            info["partner_type"] = "supplier"
            info["status"] = getattr(content_object, "status", "")
            info["status_display"] = getattr(content_object, "get_status_display", lambda: info["status"])()
            info["pdf_filename"] = f"Purchase_{info['doc_number']}.pdf"

            grand_total = Decimal(str(getattr(content_object, "total", getattr(content_object, "grand_total", 0)) or 0))
            info["financial_summary"] = f"الإجمالي: {WhatsAppService.format_currency_amount(grand_total, 'ج.م')}"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 13. مرتجع مشتريات (PurchaseReturn)
        # ----------------------------------------------------
        elif model_name == "PurchaseReturn":
            info["doc_title"] = "مرتجع مشتريات"
            info["doc_number"] = getattr(content_object, "number", f"PRET-{content_object.pk}")
            info["partner"] = partner or getattr(content_object, "supplier", getattr(getattr(content_object, "purchase", None), "supplier", None))
            info["partner_type"] = "supplier"
            info["status"] = getattr(content_object, "status", "")
            info["status_display"] = getattr(content_object, "get_status_display", lambda: info["status"])()
            info["pdf_filename"] = f"PurchaseReturn_{info['doc_number']}.pdf"

            grand_total = Decimal(str(getattr(content_object, "total", getattr(content_object, "grand_total", 0)) or 0))
            info["financial_summary"] = f"إجمالي المرتجع: {WhatsAppService.format_currency_amount(grand_total, 'ج.م')}"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 14. كشف حساب مورد (Supplier Statement)
        # ----------------------------------------------------
        elif model_name == "Supplier":
            info["doc_title"] = "كشف حساب مورد"
            info["partner"] = content_object
            info["partner_type"] = "supplier"
            from_date = extra_params.get("from_date", "")
            to_date = extra_params.get("to_date", "")
            date_label = f"{from_date} إلى {to_date}" if from_date and to_date else "الفترة الشاملة"
            info["doc_number"] = f"{content_object.code} ({date_label})"
            info["pdf_filename"] = f"Supplier_Statement_{content_object.code}.pdf"

            bal = Decimal(str(getattr(content_object, "balance", 0) or 0))
            info["financial_summary"] = f"الرصيد الحالي: {WhatsAppService.format_currency_amount(bal, 'ج.م')}"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 15. أمر شغل تصنيع وإنتاج (WorkOrder)
        # ----------------------------------------------------
        elif model_name == "WorkOrder":
            info["doc_title"] = "أمر شغل تصنيع"
            info["doc_number"] = getattr(content_object, "number", f"WO-{content_object.pk}")
            info["partner"] = partner or getattr(content_object, "customer", None)
            info["partner_type"] = "customer"
            info["status"] = getattr(content_object, "status", "")
            info["status_display"] = getattr(content_object, "get_status_display", lambda: info["status"])()
            info["pdf_filename"] = f"WorkOrder_{info['doc_number']}.pdf"
            cost = Decimal(str(getattr(content_object, "estimated_cost", 0) or 0))
            info["financial_summary"] = f"الحالة: {info['status_display']} | التكلفة التقديرية: {WhatsAppService.format_currency_amount(cost, 'ج.م')}"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 16. عرض تسعير مطبوعات (PrintingOrder)
        # ----------------------------------------------------
        elif model_name == "PrintingOrder":
            info["doc_title"] = "عرض تسعير مطبوعات"
            info["doc_number"] = getattr(content_object, "order_number", getattr(content_object, "number", f"PO-{content_object.pk}"))
            info["partner"] = partner or getattr(content_object, "customer", getattr(getattr(content_object, "work_order", None), "customer", None))
            info["partner_type"] = "customer"
            info["pdf_filename"] = f"PrintingOrder_{info['doc_number']}.pdf"

            grand_total = Decimal(str(getattr(content_object, "final_price", getattr(content_object, "grand_total", getattr(content_object, "total_price", 0))) or 0))
            info["financial_summary"] = f"إجمالي العرض: {WhatsAppService.format_currency_amount(grand_total, 'ج.م')}"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 17. إذن تحويل بين المخازن (StockTransfer)
        # ----------------------------------------------------
        elif model_name in ("StockTransfer", "StockTransferVoucher"):
            info["doc_title"] = "إذن تحويل بين المخازن"
            info["doc_number"] = getattr(content_object, "transfer_number", getattr(content_object, "number", f"TR-{content_object.pk}"))
            info["partner_type"] = "custom"
            info["pdf_filename"] = f"StockTransfer_{info['doc_number']}.pdf"
            product_name = getattr(getattr(content_object, "product", None), "name", "")
            qty = getattr(content_object, "quantity", 0)
            info["financial_summary"] = f"تحويل: {product_name} (كمية: {qty})" if product_name else "إذن تحويل مخزني معتمد"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 18. سلفة / عهدة مالية (EmployeeAdvance / EmployeeCustodyAdvance / Advance)
        # ----------------------------------------------------
        elif model_name in ("EmployeeAdvance", "EmployeeCustodyAdvance", "Advance", "AdvanceInstallment", "PettyCashSettlement"):
            info["doc_title"] = "سند سلفة / عهدة مالية"
            info["doc_number"] = getattr(content_object, "number", getattr(content_object, "advance_number", f"#{content_object.pk}"))
            info["partner"] = partner or getattr(content_object, "employee", getattr(content_object, "user", getattr(content_object, "custodian", None)))
            info["partner_type"] = "user"
            info["has_pdf"] = False
            info["template_name"] = "payment_receipt_ar"
            amount = Decimal(str(getattr(content_object, "amount", getattr(content_object, "principal_amount", 0)) or 0))
            info["financial_summary"] = f"مبلغ السلفة: {WhatsAppService.format_currency_amount(amount, 'ج.م')}"

        # ----------------------------------------------------
        # 19. قسيمة راتب الموظف (Payroll / PayrollSlip / PayrollLine / SalarySlip)
        # ----------------------------------------------------
        elif model_name in ("Payroll", "PayrollSlip", "PayrollLine", "SalarySlip"):
            info["doc_title"] = "قسيمة راتب"
            slip_no = getattr(content_object, "number", getattr(content_object, "id", content_object.pk))
            info["doc_number"] = f"#{slip_no}"
            info["partner"] = partner or getattr(content_object, "employee", None)
            info["partner_type"] = "user"
            info["has_pdf"] = True
            info["pdf_filename"] = f"Payslip_{slip_no}.pdf"
            net_salary = Decimal(str(getattr(content_object, "net_salary", 0) or 0))
            info["financial_summary"] = f"صافي الراتب: {WhatsAppService.format_currency_amount(net_salary, 'ج.م')}"
            info["template_name"] = "document_share_ar"

        # ----------------------------------------------------
        # 20. إشعار الموافقة على طلب إجازة (LeaveRequest / Leave)
        # ----------------------------------------------------
        elif model_name in ("LeaveRequest", "Leave"):
            info["doc_title"] = "طلب إجازة"
            info["doc_number"] = getattr(content_object, "number", f"#{content_object.pk}")
            info["partner"] = partner or getattr(content_object, "employee", None)
            info["partner_type"] = "user"
            info["has_pdf"] = False
            info["template_name"] = "order_status_ar"
            days = getattr(content_object, "days_count", getattr(content_object, "days", getattr(content_object, "duration_days", 1)))
            status_str = getattr(content_object, "get_status_display", lambda: getattr(content_object, "status", "معتمد"))()
            info["status_display"] = f"تم تحديث حالة الإجازة ({days} يوم) إلى: {status_str}"
            info["financial_summary"] = f"إجازة ({days} يوم)"

        # ----------------------------------------------------
        # 21. إشعار إذن انصراف / مأمورية (PermissionRequest / Permission)
        # ----------------------------------------------------
        elif model_name in ("PermissionRequest", "Permission", "ExitPermission", "MissionRequest"):
            info["doc_title"] = "إذن انصراف / مأمورية"
            info["doc_number"] = f"#{content_object.pk}"
            info["partner"] = partner or getattr(content_object, "employee", None)
            info["partner_type"] = "user"
            info["has_pdf"] = False
            info["template_name"] = "order_status_ar"
            status_str = getattr(content_object, "get_status_display", lambda: getattr(content_object, "status", "معتمد"))()
            info["status_display"] = f"تمت الموافقة على طلب الإذن / المأمورية ({status_str})"
            info["financial_summary"] = "إذن انصراف معتمد"

        # ----------------------------------------------------
        # 22. إشعار مكافأة / جزاء إداري (PenaltyReward / DisciplinaryAction)
        # ----------------------------------------------------
        elif model_name in ("PenaltyReward", "Reward", "Penalty", "DisciplinaryAction"):
            info["doc_title"] = "قرار إداري"
            info["doc_number"] = f"#{content_object.pk}"
            info["partner"] = partner or getattr(content_object, "employee", None)
            info["partner_type"] = "user"
            info["has_pdf"] = False
            info["template_name"] = "order_status_ar"
            type_str = getattr(content_object, "get_category_display", getattr(content_object, "get_type_display", lambda: getattr(content_object, "category", getattr(content_object, "type", "قرار إداري"))))()
            info["status_display"] = f"تم اعتماد {type_str} في سجلكم الوظيفي"
            info["financial_summary"] = str(type_str)

        # ----------------------------------------------------
        # 23. إشعار تجديد العقد / زيادة الراتب (Contract / EmployeeContract)
        # ----------------------------------------------------
        elif model_name in ("Contract", "EmployeeContract", "ContractIncrease"):
            info["doc_title"] = "عقد عمل"
            info["doc_number"] = getattr(content_object, "contract_number", getattr(content_object, "number", f"#{content_object.pk}"))
            info["partner"] = partner or getattr(content_object, "employee", None)
            info["partner_type"] = "user"
            info["has_pdf"] = False
            info["template_name"] = "order_status_ar"
            info["status_display"] = "تم سريان واعتماد العقد الوظيفي بنجاح"
            info["financial_summary"] = "عقد عمل ساري"

        # ----------------------------------------------------
        # 24. إشعار تسليم/استلام عهدة أصول (EmployeeAssetCustody / AssetCustody)
        # ----------------------------------------------------
        elif model_name in ("EmployeeAssetCustody", "AssetCustody", "CustodyRecord"):
            info["doc_title"] = "عهدة أصول ومعدات"
            info["doc_number"] = getattr(content_object, "custody_code", getattr(content_object, "number", f"#{content_object.pk}"))
            info["partner"] = partner or getattr(content_object, "employee", None)
            info["partner_type"] = "user"
            info["has_pdf"] = False
            info["template_name"] = "order_status_ar"
            asset_name = getattr(content_object, "item_name", getattr(content_object, "asset_name", getattr(getattr(content_object, "asset", None), "name", "عهدة أصول")))
            info["status_display"] = f"تم تسجيل تسليم واستلام: {asset_name}"
            info["financial_summary"] = str(asset_name)

        # ----------------------------------------------------
        # 25. رمز التحقق وتأكيد الهوية (OTP / OTPVerification)
        # ----------------------------------------------------
        elif model_name in ("OTP", "OTPVerification", "UserVerification") or extra_params.get("otp_code"):
            info["doc_title"] = "رمز التحقق OTP"
            info["doc_number"] = "OTP-Auth"
            info["has_pdf"] = False
            info["template_name"] = "otp_code"
            info["otp_code"] = str(getattr(content_object, "code", extra_params.get("otp_code", "000000")))
            info["financial_summary"] = f"كود التوثيق: {info['otp_code']}"

        # ----------------------------------------------------
        # 26. تنبيه أمني ودخول غير معتاد (SecurityIncident / ActiveSession / SecurityAlert)
        # ----------------------------------------------------
        elif model_name in ("SecurityIncident", "ActiveSession", "SecurityAlert", "LoginAlert"):
            info["doc_title"] = "تنبيه أمان الحساب"
            info["doc_number"] = "SEC-LOG"
            info["partner"] = partner or getattr(content_object, "user", None)
            info["partner_type"] = "user"
            info["has_pdf"] = False
            info["template_name"] = "order_status_ar"
            info["status_display"] = "تم رصد تسجيل دخول جديد لحسابكم"
            info["financial_summary"] = "تنبيه أمان نشط"

        # ----------------------------------------------------
        # 27. إشعار نجاح النسخ الاحتياطي للنظام (BackupRecord / SystemBackup)
        # ----------------------------------------------------
        elif model_name in ("BackupRecord", "SystemBackup", "BackupLog"):
            info["doc_title"] = "النسخ الاحتياطي للنظام"
            info["doc_number"] = getattr(content_object, "file_name", "Backup-Daily")
            info["has_pdf"] = False
            info["template_name"] = "order_status_ar"
            info["status_display"] = "اكتمل النسخ الاحتياطي اليومي لقاعدة البيانات بنجاح ✅"
            info["financial_summary"] = "نسخة احتياطية مكتملة"

        # ----------------------------------------------------
        # 28. تنبيه إداري عاجل من النظام (Alert / Notification / SystemAlert)
        # ----------------------------------------------------
        elif model_name in ("Alert", "Notification", "SystemAlert"):
            info["doc_title"] = "إشعار إداري عاجل"
            info["doc_number"] = getattr(content_object, "title", f"#{getattr(content_object, 'pk', 1)}")
            info["partner"] = partner or getattr(content_object, "user", getattr(content_object, "recipient", None))
            info["partner_type"] = "user"
            info["has_pdf"] = False
            info["template_name"] = "order_status_ar"
            info["status_display"] = getattr(content_object, "message", getattr(content_object, "text", "تنبيه إداري من النظام"))
            info["financial_summary"] = str(info["status_display"])[:80]

        # ----------------------------------------------------
        # 29. إشعار تسوية ومطابقة بنكية (BankStatementBatch / BankReconciliation)
        # ----------------------------------------------------
        elif model_name in ("BankStatementBatch", "BankReconciliation", "BankReconciliationSession"):
            info["doc_title"] = "مطابقة وتسوية بنكية"
            info["doc_number"] = getattr(content_object, "reference", getattr(content_object, "statement_number", f"#{content_object.pk}"))
            info["has_pdf"] = False
            info["template_name"] = "order_status_ar"
            info["status_display"] = "تم اعتماد وإقفال المطابقة والتسوية البنكية بنجاح"
            info["financial_summary"] = "تسوية بنكية معتمدة"

        # ----------------------------------------------------
        # 30. إشعار تقييم فروق العملة (FXRevaluationRun)
        # ----------------------------------------------------
        elif model_name in ("FXRevaluationRun", "FXRun"):
            info["doc_title"] = "تقييم فروق العملة (FX)"
            info["doc_number"] = getattr(content_object, "run_number", getattr(content_object, "code", f"FX-{content_object.pk}"))
            info["has_pdf"] = False
            info["template_name"] = "order_status_ar"
            gl_amt = Decimal(str(getattr(content_object, "total_unrealized_gain_loss", getattr(content_object, "total_gain_loss", 0)) or 0))
            info["status_display"] = f"تم ترحيل تقييم فروق العملات: {WhatsAppService.format_currency_amount(gl_amt, 'ج.م')}"
            info["financial_summary"] = f"فروق التقييم: {WhatsAppService.format_currency_amount(gl_amt, 'ج.م')}"

        # ----------------------------------------------------
        # 31. طلب اعتماد بروفة تصميم/طباعة (PrintingProof / ProofApproval)
        # ----------------------------------------------------
        elif model_name in ("PrintingProof", "ProofApproval"):
            info["doc_title"] = "بروفة تصميم وطباعة"
            info["doc_number"] = getattr(content_object, "proof_number", getattr(content_object, "number", f"PRF-{content_object.pk}"))
            info["partner"] = partner or getattr(content_object, "customer", getattr(getattr(content_object, "order", None), "customer", None))
            info["partner_type"] = "customer"
            info["has_pdf"] = False
            info["template_name"] = "order_status_ar"
            info["status_display"] = "بروفة التصميم الفنية جاهزة للمعاينة والاعتماد"
            info["financial_summary"] = "بروفة طباعة جاهزة"

        # ----------------------------------------------------
        # 32. إشعار جاهزية الشغل للتسليم (WorkOrderReady / JobReady)
        # ----------------------------------------------------
        elif model_name in ("WorkOrderReady", "JobReady"):
            info["doc_title"] = "أمر شغل جاهز للتسليم"
            info["doc_number"] = getattr(content_object, "number", getattr(content_object, "order_number", f"WO-{content_object.pk}"))
            info["partner"] = partner or getattr(content_object, "customer", None)
            info["partner_type"] = "customer"
            info["has_pdf"] = False
            info["template_name"] = "order_status_ar"
            info["status_display"] = "أمر الشغل مكتمل وجاهز للتسليم والشحن 🚚"
            info["financial_summary"] = "جاهز للتسليم"

        # ----------------------------------------------------
        # 33. ترحيب بعميل جديد وفتح حساب (Customer)
        # ----------------------------------------------------
        elif model_name == "Customer":
            info["doc_title"] = "بطاقة ترحيب عميل جديد"
            info["doc_number"] = getattr(content_object, "code", str(getattr(content_object, "pk", "")))
            info["partner"] = partner or content_object
            info["partner_type"] = "customer"
            info["has_pdf"] = False
            info["template_name"] = "welcome_new_customer"
            info["status_display"] = "حساب عميل نشط ومسجل"
            info["financial_summary"] = "ترحيب بتسجيل عميل جديد"

        # ----------------------------------------------------
        # Fallback لأي مستند آخر
        # ----------------------------------------------------
        else:
            info["doc_title"] = getattr(content_object._meta, "verbose_name", "مستند") if hasattr(content_object, "_meta") else "مستند"
            info["doc_number"] = getattr(content_object, "number", f"#{getattr(content_object, 'pk', 1)}")
            info["partner"] = partner
            info["pdf_filename"] = f"Document_{info['doc_number']}.pdf"
            info["financial_summary"] = str(content_object)

        # استخراج خيارات الاتصال للشريك
        if info["partner"]:
            info["partner_name"] = getattr(info["partner"], "name", str(info["partner"]))
            info["phone_options"] = WhatsAppService.get_partner_contact_options(info["partner"])
        else:
            info["partner_name"] = ""
            info["phone_options"] = []

        # ضبط عزل BiDi لرقم ونوع المستند
        info["doc_number_bidi"] = WhatsAppService.isolate_bidi(f"{info['doc_title']} #{info['doc_number']}")

        # بناء معاملات القالب الافتراضية الصارمة (Strict Parameter Contract)
        info["components"] = cls._build_template_components(info)

        return info

    # ==================== 2. بناء معاملات القوالب الأربعة ====================

    @classmethod
    def _build_template_components(cls, info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        بناء مصفوفة معاملات القالب بمطابقة 100% لعقد Meta البرمجي الصارم
        """
        template_name = info.get("template_name", "document_share_ar")
        recipient_name = info.get("partner_name") or "عميلنا العزيز"
        doc_label = info.get("doc_number_bidi") or WhatsAppService.isolate_bidi(info.get("doc_number", ""))
        financial_sum = info.get("financial_summary") or "مستند صادر معتمد"
        site_name = info.get("site_name") or SystemSetting.get_site_name()

        # 1. قالب إرسال المستندات (document_share_ar / document_send_ar / document_send_en)
        if template_name in ("document_share_ar", "document_send_ar", "document_send_en", "document_share_en"):
            if template_name.endswith("_en") and recipient_name == "عميلنا العزيز":
                recipient_name = "Valued Customer"
            return [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": recipient_name[:60]},
                    {"type": "text", "text": doc_label[:80]},
                    {"type": "text", "text": financial_sum[:100]},
                    {"type": "text", "text": site_name[:50]},
                ]
            }]

        # 2. قالب إيصالات القبض والدفع (payment_receipt_ar / payment_receipt_en)
        elif template_name in ("payment_receipt_ar", "payment_receipt_en"):
            if template_name.endswith("_en") and recipient_name == "عميلنا العزيز":
                recipient_name = "Valued Customer"
            amount_str = financial_sum
            voucher_num = doc_label
            remaining_bal = "تم تحديث الحساب" if not template_name.endswith("_en") else "Account Updated"
            if info.get("partner") and hasattr(info["partner"], "balance"):
                bal_val = WhatsAppService.format_currency_amount(Decimal(str(info['partner'].balance or 0)))
                remaining_bal = f"الرصيد الحالي: {bal_val}" if not template_name.endswith("_en") else f"Current Balance: {bal_val}"

            return [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": recipient_name[:60]},
                    {"type": "text", "text": amount_str[:50]},
                    {"type": "text", "text": voucher_num[:80]},
                    {"type": "text", "text": remaining_bal[:60]},
                    {"type": "text", "text": site_name[:50]},
                ]
            }]

        # 3. قالب تحديث الحالة والتذكيرات (order_status_ar / order_status_en)
        elif template_name in ("order_status_ar", "order_status_en"):
            if template_name.endswith("_en") and recipient_name == "عميلنا العزيز":
                recipient_name = "Valued Customer"
            status_text = info.get("status_display") or ("جاهز للتسليم" if not template_name.endswith("_en") else "Ready")
            return [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": recipient_name[:60]},
                    {"type": "text", "text": doc_label[:80]},
                    {"type": "text", "text": status_text[:60]},
                    {"type": "text", "text": site_name[:50]},
                ]
            }]

        # 4. قالب OTP (يدعم otp_code المعتمد في Meta و otp_auth_code)
        elif template_name in ("otp_code", "otp_auth_code"):
            otp_code = info.get("otp_code", "000000")
            return [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(otp_code)}]
                },
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [{"type": "text", "text": str(otp_code)}]
                }
            ]

        # 5. قالب الترحيب بالعميل الجديد (welcome_new_customer)
        elif template_name == "welcome_new_customer":
            return [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": recipient_name[:60]}
                ]
            }]

        # 6. قالب الاختبار العام المعتمد من Meta (hello_world)
        elif template_name == "hello_world":
            return []

        return []

    # ==================== 3. توليد ملفات الـ PDF الثنائية في الذاكرة ====================

    @classmethod
    def _build_full_document_context(cls, content_object: Any, extra_params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        بناء سياق طباعة موحد وكامل متضمناً شعار وهوية الشركة وبيانات الفوتر والترويسة
        لكافة المستندات لإنتاج ملف PDF رسمي فائق الجودة مطابق للواجهة 100%
        """
        from ..models import SystemSetting
        settings_dict = SystemSetting._get_all_settings_dict()

        company_name = settings_dict.get("company_name") or "مؤسسة موهبة"
        company_address = settings_dict.get("company_address", "")
        company_phone = settings_dict.get("company_phone", "")
        company_tax_number = settings_dict.get("company_tax_number", "")
        company_logo = settings_dict.get("company_logo", "")
        company_stamp = settings_dict.get("company_stamp", "")
        company_email = settings_dict.get("company_email", "")
        company_website = settings_dict.get("company_website", "")

        currency_symbol = getattr(getattr(content_object, "currency", None), "symbol", None) or settings_dict.get("currency_symbol", "ج.م")

        base_ctx = {
            "settings": settings_dict,
            "company_name": company_name,
            "company_address": company_address,
            "company_phone": company_phone,
            "company_tax_number": company_tax_number,
            "company_logo": company_logo,
            "company_stamp": company_stamp,
            "company_email": company_email,
            "company_website": company_website,
            "currency_symbol_active": currency_symbol,
            "currency_symbol": currency_symbol,
            "print_lang": "ar",
            "print_dir": "rtl",
            "is_english": False,
            "is_bilingual": False,
        }

        if extra_params:
            base_ctx.update(extra_params)

        return base_ctx

    @classmethod
    def render_document_pdf_bytes(cls, content_object: Any, extra_params: Dict[str, Any] = None) -> Tuple[Optional[bytes], str]:
        """
        توليد بايتات الـ PDF مباشرة في الذاكرة (In-Memory Stream) لكافة المستندات
        """
        if not content_object:
            return None, "document.pdf"

        model_name = content_object.__class__.__name__
        from utils.pdf_utils import generate_pdf_from_html, generate_guaranteed_pdf_response
        from ..models import SystemSetting

        # 1. فاتورة مبيعات
        if model_name == "Sale":
            try:
                ctx = cls._build_full_document_context(content_object, extra_params)
                items = content_object.items.all().select_related('product', 'product__unit', 'product__category')
                ctx.update({
                    "sale": content_object,
                    "items": items,
                    "title": f"فاتورة مبيعات - {content_object.number}",
                    "document_title": "فاتورة مبيعات",
                    "default_notes": SystemSetting.get_setting('default_sale_invoice_notes', ''),
                })
                html = render_to_string("sale/sale_print.html", ctx)
                resp = generate_pdf_from_html(html, None, filename=f"{content_object.number}.pdf", doc_type="sale", context=ctx)
                if resp and hasattr(resp, 'content') and resp.content:
                    return resp.content, f"Invoice_{content_object.number}.pdf"
            except Exception as e:
                logger.warning(f"Sale HTML PDF render exception ({e}), generating guaranteed fallback")
            resp = generate_guaranteed_pdf_response("sale", {"sale": content_object}, filename=f"{content_object.number}.pdf")
            return getattr(resp, 'content', None), f"Invoice_{content_object.number}.pdf"

        # 2. عرض أسعار
        elif model_name == "Quotation":
            try:
                ctx = cls._build_full_document_context(content_object, extra_params)
                items = content_object.items.all().select_related('product', 'product__unit', 'product__category')
                ctx.update({
                    "quotation": content_object,
                    "items": items,
                    "title": f"عرض سعر - {content_object.number}",
                    "document_title": "عرض سعر",
                    "translated_status": content_object.get_status_display() if hasattr(content_object, 'get_status_display') else "معتمد",
                    "default_notes": SystemSetting.get_setting('default_quotation_notes', ''),
                    "has_item_discounts": getattr(content_object, 'has_item_discounts', False),
                    "salesman_name": getattr(content_object, 'salesman_display_name', ''),
                })
                html = render_to_string("sale/quotation_print.html", ctx)
                resp = generate_pdf_from_html(html, None, filename=f"{content_object.number}.pdf", doc_type="quotation", context=ctx)
                if resp and hasattr(resp, 'content') and resp.content:
                    return resp.content, f"Quotation_{content_object.number}.pdf"
            except Exception as e:
                logger.warning(f"Quotation HTML PDF render exception ({e}), generating guaranteed fallback")
            resp = generate_guaranteed_pdf_response("quotation", {"quotation": content_object}, filename=f"{content_object.number}.pdf")
            return getattr(resp, 'content', None), f"Quotation_{content_object.number}.pdf"

        # 3. أمر بيع (SalesOrder)
        elif model_name == "SalesOrder":
            order_no = getattr(content_object, "order_number", content_object.pk)
            try:
                ctx = cls._build_full_document_context(content_object, extra_params)
                ctx.update({
                    "so": content_object,
                    "items": content_object.items.all(),
                    "title": f"أمر بيع - {order_no}",
                    "document_title": "أمر بيع",
                })
                html = render_to_string("sale/sales_order_print.html", ctx)
                resp = generate_pdf_from_html(html, None, filename=f"{order_no}.pdf", doc_type="sales_order", context=ctx)
                if resp and hasattr(resp, 'content') and resp.content:
                    return resp.content, f"SalesOrder_{order_no}.pdf"
            except Exception as e:
                logger.warning(f"SalesOrder HTML PDF render exception ({e}), generating guaranteed fallback")
            resp = generate_guaranteed_pdf_response("sales_order", {"so": content_object}, filename=f"{order_no}.pdf")
            return getattr(resp, 'content', None), f"SalesOrder_{order_no}.pdf"

        # 4. إذن تسليم بضاعة (DeliveryNote)
        elif model_name == "DeliveryNote":
            dn_no = getattr(content_object, "delivery_number", content_object.pk)
            try:
                ctx = cls._build_full_document_context(content_object, extra_params)
                ctx.update({
                    "dn": content_object,
                    "items": content_object.items.all(),
                    "title": f"إذن تسليم بضاعة - {dn_no}",
                    "document_title": "إذن تسليم بضاعة",
                })
                html = render_to_string("sale/delivery_note_print.html", ctx)
                resp = generate_pdf_from_html(html, None, filename=f"{dn_no}.pdf", doc_type="delivery_note", context=ctx)
                if resp and hasattr(resp, 'content') and resp.content:
                    return resp.content, f"DeliveryNote_{dn_no}.pdf"
            except Exception as e:
                logger.warning(f"DeliveryNote HTML PDF render exception ({e}), generating guaranteed fallback")
            resp = generate_guaranteed_pdf_response("delivery_note", {"dn": content_object}, filename=f"{dn_no}.pdf")
            return getattr(resp, 'content', None), f"DeliveryNote_{dn_no}.pdf"

        # 5. مرتجع مبيعات (SaleReturn)
        elif model_name == "SaleReturn":
            ret_no = getattr(content_object, "number", getattr(content_object, "pk", ""))
            try:
                ctx = cls._build_full_document_context(content_object, extra_params)
                ctx.update({
                    "sale_return": content_object,
                    "items": content_object.items.all(),
                    "title": f"مرتجع مبيعات - {ret_no}",
                    "document_title": "مرتجع مبيعات",
                })
                html = render_to_string("sale/sale_return.html", ctx)
                resp = generate_pdf_from_html(html, None, filename=f"{ret_no}.pdf", doc_type="sale_return", context=ctx)
                if resp and hasattr(resp, 'content') and resp.content:
                    return resp.content, f"SaleReturn_{ret_no}.pdf"
            except Exception as e:
                logger.warning(f"SaleReturn HTML PDF render exception ({e}), generating guaranteed fallback")
            resp = generate_guaranteed_pdf_response("sale_return", {"sale_return": content_object}, filename=f"{ret_no}.pdf")
            return getattr(resp, 'content', None), f"SaleReturn_{ret_no}.pdf"

        # 6. إشعار دائن (CreditNote)
        elif model_name == "CreditNote":
            cn_no = getattr(content_object, "credit_note_number", getattr(content_object, "number", content_object.pk))
            try:
                ctx = cls._build_full_document_context(content_object, extra_params)
                ctx.update({"credit_note": content_object})
                resp = generate_guaranteed_pdf_response("credit_note", ctx, filename=f"{cn_no}.pdf")
                if resp and hasattr(resp, 'content') and resp.content:
                    return resp.content, f"CreditNote_{cn_no}.pdf"
            except Exception as e:
                logger.warning(f"CreditNote PDF render exception ({e})")
            return getattr(resp, 'content', None), f"CreditNote_{cn_no}.pdf"

        # 7. كشف حساب عميل (Customer Statement)
        elif model_name == "Customer":
            cust_code = getattr(content_object, "code", content_object.pk)
            try:
                ctx = cls._build_full_document_context(content_object, extra_params)
                ctx.update({"customer": content_object})
                resp = generate_guaranteed_pdf_response("statement", ctx, filename=f"Statement_{cust_code}.pdf")
                if resp and hasattr(resp, 'content') and resp.content:
                    return resp.content, f"Statement_{cust_code}.pdf"
            except Exception as e:
                logger.warning(f"Customer Statement PDF render exception ({e})")
            return getattr(resp, 'content', None), f"Statement_{cust_code}.pdf"

        # 8. أمر شراء للمورد (PurchaseOrder)
        elif model_name == "PurchaseOrder":
            order_no = getattr(content_object, 'order_number', content_object.pk)
            try:
                ctx = cls._build_full_document_context(content_object, extra_params)
                items = content_object.items.all().select_related('product', 'product__unit')
                ctx.update({
                    "order": content_object,
                    "items": items,
                    "title": f"أمر شراء - {order_no}",
                    "document_title": "أمر شراء",
                })
                html = render_to_string("purchase/po_print.html", ctx)
                resp = generate_pdf_from_html(html, None, filename=f"{order_no}.pdf", doc_type="po", context=ctx)
                if resp and hasattr(resp, 'content') and resp.content:
                    return resp.content, f"PO_{order_no}.pdf"
            except Exception as e:
                logger.warning(f"PO HTML PDF render exception ({e}), generating guaranteed fallback")
            resp = generate_guaranteed_pdf_response("po", {"po": content_object}, filename=f"{content_object.pk}.pdf")
            return getattr(resp, 'content', None), f"PO_{content_object.pk}.pdf"

        # 9. إذن استلام بضاعة (GoodsReceivedNote / GRN)
        elif model_name in ("GoodsReceivedNote", "GoodsReceiptNote"):
            grn_no = getattr(content_object, "grn_number", getattr(content_object, "number", content_object.pk))
            try:
                ctx = cls._build_full_document_context(content_object, extra_params)
                ctx.update({
                    "grn": content_object,
                    "items": content_object.items.all(),
                    "title": f"إذن استلام بضاعة - {grn_no}",
                    "document_title": "إذن استلام بضاعة",
                })
                html = render_to_string("purchase/grn_print.html", ctx)
                resp = generate_pdf_from_html(html, None, filename=f"{grn_no}.pdf", doc_type="grn", context=ctx)
                if resp and hasattr(resp, 'content') and resp.content:
                    return resp.content, f"GRN_{grn_no}.pdf"
            except Exception as e:
                logger.warning(f"GRN HTML PDF render exception ({e}), generating guaranteed fallback")
            resp = generate_guaranteed_pdf_response("grn", {"grn": content_object}, filename=f"{grn_no}.pdf")
            return getattr(resp, 'content', None), f"GRN_{grn_no}.pdf"

        # 10. فاتورة مشتريات (Purchase)
        elif model_name in ("Purchase", "SupplierBill"):
            try:
                ctx = cls._build_full_document_context(content_object, extra_params)
                items = content_object.items.all().select_related('product', 'product__unit')
                ctx.update({
                    "purchase": content_object,
                    "items": items,
                    "title": f"فاتورة مشتريات - {content_object.number}",
                    "document_title": "فاتورة مشتريات",
                })
                html = render_to_string("purchase/purchase_print.html", ctx)
                resp = generate_pdf_from_html(html, None, filename=f"{content_object.number}.pdf", doc_type="purchase", context=ctx)
                if resp and hasattr(resp, 'content') and resp.content:
                    return resp.content, f"Purchase_{content_object.number}.pdf"
            except Exception as e:
                logger.warning(f"Purchase HTML PDF render exception ({e}), generating guaranteed fallback")
            resp = generate_guaranteed_pdf_response("purchase", {"purchase": content_object}, filename=f"{content_object.number}.pdf")
            return getattr(resp, 'content', None), f"Purchase_{content_object.number}.pdf"

        # 11. مرتجع مشتريات (PurchaseReturn)
        elif model_name == "PurchaseReturn":
            ret_no = getattr(content_object, "number", getattr(content_object, "pk", ""))
            try:
                ctx = cls._build_full_document_context(content_object, extra_params)
                ctx.update({
                    "purchase_return": content_object,
                    "items": content_object.items.all(),
                    "title": f"مرتجع مشتريات - {ret_no}",
                    "document_title": "مرتجع مشتريات",
                })
                html = render_to_string("purchase/purchase_return_print.html", ctx)
                resp = generate_pdf_from_html(html, None, filename=f"{ret_no}.pdf", doc_type="purchase_return", context=ctx)
                if resp and hasattr(resp, 'content') and resp.content:
                    return resp.content, f"PurchaseReturn_{ret_no}.pdf"
            except Exception as e:
                logger.warning(f"PurchaseReturn HTML PDF render exception ({e}), generating guaranteed fallback")
            resp = generate_guaranteed_pdf_response("purchase_return", {"purchase_return": content_object}, filename=f"{ret_no}.pdf")
            return getattr(resp, 'content', None), f"PurchaseReturn_{ret_no}.pdf"

        # 12. كشف حساب مورد (Supplier Statement)
        elif model_name == "Supplier":
            supp_code = getattr(content_object, "code", content_object.pk)
            try:
                ctx = cls._build_full_document_context(content_object, extra_params)
                ctx.update({"supplier": content_object})
                resp = generate_guaranteed_pdf_response("supplier_statement", ctx, filename=f"Supplier_Statement_{supp_code}.pdf")
                if resp and hasattr(resp, 'content') and resp.content:
                    return resp.content, f"Supplier_Statement_{supp_code}.pdf"
            except Exception as e:
                logger.warning(f"Supplier Statement PDF render exception ({e})")
            return getattr(resp, 'content', None), f"Supplier_Statement_{supp_code}.pdf"

        # 13. أمر شغل تصنيع وإنتاج (WorkOrder)
        elif model_name == "WorkOrder":
            wo_no = getattr(content_object, "number", content_object.pk)
            try:
                ctx = cls._build_full_document_context(content_object, extra_params)
                ctx.update({
                    "work_order": content_object,
                    "title": f"أمر شغل تصنيع - {wo_no}",
                    "document_title": "أمر شغل تصنيع وإنتاج",
                })
                html = render_to_string("work_order/work_order_print.html", ctx)
                resp = generate_pdf_from_html(html, None, filename=f"{wo_no}.pdf", doc_type="work_order", context=ctx)
                if resp and hasattr(resp, 'content') and resp.content:
                    return resp.content, f"WorkOrder_{wo_no}.pdf"
            except Exception as e:
                logger.warning(f"WorkOrder HTML PDF render exception ({e}), generating guaranteed fallback")
            resp = generate_guaranteed_pdf_response("work_order", {"work_order": content_object}, filename=f"{wo_no}.pdf")
            return getattr(resp, 'content', None), f"WorkOrder_{wo_no}.pdf"

        # 14. عرض تسعير مطبوعات (PrintingOrder)
        elif model_name == "PrintingOrder":
            po_no = getattr(content_object, "order_number", getattr(content_object, "number", content_object.pk))
            try:
                ctx = cls._build_full_document_context(content_object, extra_params)
                ctx.update({"order": content_object})
                resp = generate_guaranteed_pdf_response("printing_order", ctx, filename=f"PrintingOrder_{po_no}.pdf")
                if resp and hasattr(resp, 'content') and resp.content:
                    return resp.content, f"PrintingOrder_{po_no}.pdf"
            except Exception as e:
                logger.warning(f"PrintingOrder PDF render exception ({e})")
            return getattr(resp, 'content', None), f"PrintingOrder_{po_no}.pdf"

        # 15. إذن تحويل بين المخازن (StockTransfer)
        elif model_name in ("StockTransfer", "StockTransferVoucher"):
            tr_no = getattr(content_object, "transfer_number", getattr(content_object, "number", content_object.pk))
            try:
                ctx = cls._build_full_document_context(content_object, extra_params)
                ctx.update({"transfer": content_object})
                resp = generate_guaranteed_pdf_response("stock_transfer", ctx, filename=f"StockTransfer_{tr_no}.pdf")
                if resp and hasattr(resp, 'content') and resp.content:
                    return resp.content, f"StockTransfer_{tr_no}.pdf"
            except Exception as e:
                logger.warning(f"StockTransfer PDF render exception ({e})")
            return getattr(resp, 'content', None), f"StockTransfer_{tr_no}.pdf"

        # 16. قسيمة راتب الموظف (Payroll / PayrollSlip / PayrollLine)
        elif model_name in ("Payroll", "PayrollSlip", "PayrollLine", "SalarySlip"):
            slip_no = getattr(content_object, "number", getattr(content_object, "id", content_object.pk))
            try:
                ctx = cls._build_full_document_context(content_object, extra_params)
                ctx.update({"payroll": content_object})
                resp = generate_guaranteed_pdf_response("payroll_slip", ctx, filename=f"Payslip_{slip_no}.pdf")
                if resp and hasattr(resp, 'content') and resp.content:
                    return resp.content, f"Payslip_{slip_no}.pdf"
            except Exception as e:
                logger.warning(f"Payroll PDF render exception ({e})")
            return getattr(resp, 'content', None), f"Payslip_{slip_no}.pdf"

        # Fallback عام ومضمون
        ctx = cls._build_full_document_context(content_object, extra_params)
        ctx.update({"document": content_object})
        resp = generate_guaranteed_pdf_response("generic", ctx, filename="Document.pdf")
        return getattr(resp, 'content', None), "Document.pdf"

    # ==================== 4. كاش الميديا الزمني (Timestamp Media Cache) ====================

    @classmethod
    def get_or_upload_media_id(cls, content_object: Any, pdf_bytes: bytes, filename: str) -> Optional[str]:
        """
        التحقق من كاش الـ Media ID الزمني ورفع الملف الثنائي لـ Meta إذا لم يتوفر كاش صالح
        """
        if not pdf_bytes:
            return None

        # حساب البصمة الزمنية لآخر تحديث للمستند لإبطال الكاش فور تعديل المستند
        updated_at = getattr(content_object, "updated_at", None) or timezone.now()
        ts = int(updated_at.timestamp())
        ct_id = ContentType.objects.get_for_model(content_object).id if content_object else 0
        obj_id = getattr(content_object, "pk", 0)

        cache_key = f"wa_media_{ct_id}_{obj_id}_{ts}"
        cached_media_id = cache.get(cache_key)

        if cached_media_id:
            logger.info(f"⚡ استخدام Media ID من الكاش: {cached_media_id} للمستند {ct_id}:{obj_id}")
            return cached_media_id

        # رفع الملف الثنائي مباشرة إلى Meta Graph API
        logger.info(f"📤 جاري رفع ملف PDF الثنائي لـ Meta للمستند {ct_id}:{obj_id}...")
        res = WhatsAppService.upload_media(pdf_bytes, filename=filename, mime_type="application/pdf")
        if res.get("success") and res.get("media_id"):
            media_id = res["media_id"]
            cache.set(cache_key, media_id, cls.MEDIA_CACHE_TTL)
            return media_id

        logger.error(f"❌ فشل رفع ملف PDF الثنائي لـ Meta: {res.get('error')}")
        return None

    # ==================== 5. الإرسال الشامل والتنفيذ ====================

    @classmethod
    def dispatch(
        cls,
        content_object: Any,
        recipient_phone: str,
        template_name: str = None,
        partner: Any = None,
        created_by: Any = None,
        is_custom_phone: bool = False,
        is_automatic: bool = False,
        custom_components: List[Dict[str, Any]] = None,
        extra_params: Dict[str, Any] = None,
        account: Any = None,
        account_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        تنفيذ عملية الإرسال الشاملة مع تطبيق كافة الضمانات التشغيلية
        """
        extra_params = extra_params or {}
        info = cls.get_document_info(content_object, partner=partner, extra_params=extra_params)

        # 1. التحقق من شروط الحالة (State Guard)
        if not info["can_send"]:
            return {
                "success": False,
                "error": info["cannot_send_reason"] or "لا يمكن إرسال هذا المستند في حالته الحالية."
            }

        target_partner = partner or info["partner"]
        target_template = template_name or info["template_name"]
        components = custom_components or info["components"]

        if target_template == "hello_world":
            components = []
            header_media_id = None
            header_filename = None
        else:
            # 2. رفع أو جلب مرفق الـ PDF إذا كان القالب يدعم المرفقات
            header_media_id = None
            header_filename = None
            if info["has_pdf"] and target_template in ("document_share_ar", "document_send_ar", "payment_receipt_ar"):
                pdf_bytes, filename = cls.render_document_pdf_bytes(content_object, extra_params=extra_params)
                if pdf_bytes:
                    header_filename = filename
                    header_media_id = cls.get_or_upload_media_id(content_object, pdf_bytes, filename)
                    if not header_media_id:
                        # في حال فشل رفع المرفق، يمكن التحول للوضع النصي أو إشعار المستخدم
                        logger.warning("تعذر رفع مرفق الـ PDF لـ Meta، سيتم محاولة الإرسال بدون مرفق")

        # 3. تفويض الإرسال لـ WhatsAppService
        res = WhatsAppService.send_template_message(
            phone=recipient_phone,
            template_name=target_template,
            language_code="en_US" if target_template == "hello_world" else info.get("language_code", "ar"),
            components=components,
            header_media_id=header_media_id,
            header_filename=header_filename,
            content_object=content_object,
            partner=target_partner,
            created_by=created_by,
            is_custom_phone=is_custom_phone,
            is_automatic=is_automatic,
            account=account,
            account_id=account_id
        )

        return res
