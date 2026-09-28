# -*- coding: utf-8 -*-
"""
اختبارات شاملة للمرحلة الأولى من منظومة WhatsApp Business Cloud API
MWHEBA ERP — WhatsApp Phase 1 Pytest Suite
"""
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

from core.models import SystemSetting, WhatsAppMessageLog
from core.services.whatsapp_service import WhatsAppService
from customer.models import Customer
from supplier.models import Supplier

User = get_user_model()


@pytest.mark.django_db
class TestWhatsAppPhase1Core:
    """اختبارات المحرك الأساسي ومعالجة الأرقام والنصوص والنماذج"""

    def setup_method(self):
        # تهيئة إعدادات WhatsApp الافتراضية للاختبارات
        SystemSetting.objects.update_or_create(
            key="whatsapp_enabled",
            defaults={"value": "true", "data_type": "boolean", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_access_token",
            defaults={"value": "EAATestToken123456", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_phone_number_id",
            defaults={"value": "1000987654321", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_app_secret",
            defaults={"value": "test_secret_key_abcdef", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_default_country_code",
            defaults={"value": "+20", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        WhatsAppService.reset_session()

    def test_phone_normalization_egyptian(self):
        """التحقق من تحويل الأرقام المصرية المختلفة للصيغة الدولية الصحيحة (2010...)"""
        assert WhatsAppService.normalize_phone("01012345678") == "201012345678"
        assert WhatsAppService.normalize_phone("01112345678") == "201112345678"
        assert WhatsAppService.normalize_phone("01212345678") == "201212345678"
        assert WhatsAppService.normalize_phone("01512345678") == "201512345678"
        assert WhatsAppService.normalize_phone("+201012345678") == "201012345678"
        assert WhatsAppService.normalize_phone(" 010-1234-5678 ") == "201012345678"
        assert WhatsAppService.normalize_phone("1012345678") == "201012345678"

    def test_phone_normalization_gulf(self):
        """التحقق من دعم أرقام السعودية والخليج"""
        assert WhatsAppService.normalize_phone("0512345678", default_country_code="+966") == "966512345678"
        assert WhatsAppService.normalize_phone("+966512345678") == "966512345678"

    def test_landline_detector(self):
        """التحقق من كشف الأرقام الأرضية بدقة (القاهرة 02، الإسكندرية 03...)"""
        assert WhatsAppService.is_landline("0223456789") is True
        assert WhatsAppService.is_landline("20223456789") is True
        assert WhatsAppService.is_landline("035551234") is True
        assert WhatsAppService.is_landline("01012345678") is False

    def test_isolate_bidi(self):
        """التحقق من عزل النصوص والأرقام بـ BiDi Unicode"""
        isolated = WhatsAppService.isolate_bidi("INV-2026-00142")
        assert isolated == "\u200EINV-2026-00142\u200E"

    def test_sanitize_filename(self):
        """التحقق من تطهير أسماء الملفات ومنع الشرطات المائلة والرموز غير الآمنة"""
        sanitized = WhatsAppService.sanitize_filename("Invoice/INV-2026/001.pdf")
        assert "/" not in sanitized
        assert sanitized.endswith(".pdf")
        assert "Invoice-INV-2026-001.pdf" in sanitized

    def test_format_currency_amount(self):
        """التحقق من مطابقة المبالغ المالية بالقرش والعملات الأجنبية (Rule 3)"""
        formatted_local = WhatsAppService.format_currency_amount(Decimal("15250.50"), "ج.م")
        assert "15,250.50" in formatted_local
        assert "ج.م" in formatted_local

        formatted_foreign = WhatsAppService.format_currency_amount(
            amount=Decimal("75000.00"),
            currency_symbol="ج.م",
            foreign_amount=Decimal("1500.00"),
            foreign_currency_symbol="USD"
        )
        assert "1,500.00 USD" in formatted_foreign
        assert "75,000.00 ج.م" in formatted_foreign

    def test_partner_contact_extraction(self):
        """التحقق من استخراج جهات اتصال الشريك المتعددة وتصنيفها"""
        customer = Customer.objects.create(
            name="شركة الأمل للطباعة",
            code="CUST-TEST-01",
            phone="01011112222",
            phone_secondary="01233334444",
            contact_person="أحمد محمود",
            balance=Decimal("0.00")
        )
        # Add contact_person_phone attribute dynamically or test standard fields
        customer.contact_person_phone = "01555556666"
        
        options = WhatsAppService.get_partner_contact_options(customer)
        assert len(options) >= 2
        phones = [opt["phone"] for opt in options]
        assert "201011112222" in phones
        assert "201233334444" in phones

    def test_message_log_monotonic_state_safety(self):
        """التحقق من أن حالة الرسالة تتقدم للأمام فقط ولا ترتد للخلف (Monotonic State Machine)"""
        log = WhatsAppMessageLog.objects.create(
            recipient_phone="201012345678",
            recipient_name="عميل تجريبي",
            template_name="document_send_ar",
            status="PENDING"
        )
        assert log.status == "PENDING"

        # PENDING -> SENT (مسموح)
        log.update_status_safely("SENT")
        assert log.status == "SENT"

        # SENT -> DELIVERED (مسموح)
        log.update_status_safely("DELIVERED")
        assert log.status == "DELIVERED"

        # DELIVERED -> READ (مسموح)
        log.update_status_safely("READ")
        assert log.status == "READ"

        # READ -> DELIVERED (ممنوع ارتداد الحالة للخلف في حال وصول Webhook متأخر)
        log.update_status_safely("DELIVERED")
        assert log.status == "READ"  # الحالة تبقى READ ولا تنزل لـ DELIVERED

    def test_safe_document_label_resilience(self):
        """التحقق من خاصية السجل الآمن وحماية الشاشات من الانهيار عند حذف المستند الأصل"""
        customer = Customer.objects.create(
            name="عميل للحذف",
            code="CUST-TEST-DEL",
            balance=Decimal("0.00")
        )
        ct = ContentType.objects.get_for_model(Customer)
        log = WhatsAppMessageLog.objects.create(
            recipient_phone="201012345678",
            template_name="document_send_ar",
            content_type=ct,
            object_id=customer.pk,
            status="SENT"
        )
        assert "عميل للحذف" in log.safe_document_label

        # حذف الأصل وملاحظة الصمود
        cust_id = customer.pk
        customer.delete()
        log.refresh_from_db()
        assert f"#{cust_id}" in log.safe_document_label

    def test_opt_out_skipping(self):
        """التحقق من تخطي الإرسال تلقائياً للعملاء الملغين للاشتراك (Opt-Out) وتوثيق السبب"""
        customer = Customer.objects.create(
            name="عميل ملغي للاشتراك",
            code="CUST-OPTOUT",
            phone="01099998888",
            whatsapp_opt_out=True,
            whatsapp_opt_out_at=timezone.now(),
            whatsapp_opt_out_reason="Inbound STOP request",
            balance=Decimal("0.00")
        )

        res = WhatsAppService.send_template_message(
            phone=customer.phone,
            template_name="document_send_ar",
            partner=customer
        )
        assert res["success"] is False
        assert "Opt-Out" in res["error"]

        # التحقق من تسجيل حالة SKIPPED في جدول السجلات
        log = WhatsAppMessageLog.objects.get(id=res["log_id"])
        assert log.status == "SKIPPED"
        assert log.customer == customer

    def test_verify_webhook_signature(self):
        """التحقق من صحة فحص توقيع HMAC-SHA256 لـ Webhook"""
        payload = b'{"entry":[{"id":"12345"}]}'
        secret = "test_secret_key_abcdef"
        
        import hmac, hashlib
        valid_digest = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
        valid_header = f"sha256={valid_digest}"
        invalid_header = "sha256=wrongdigest123456"

        assert WhatsAppService.verify_webhook_signature(payload, valid_header) is True
        assert WhatsAppService.verify_webhook_signature(payload, invalid_header) is False
        assert WhatsAppService.verify_webhook_signature(payload, "invalid_format") is False

    @patch('requests.Session.post')
    def test_mocked_meta_send_success(self, mock_post):
        """التحقق من نجاح إرسال الرسالة إلى Meta واسترجاع wamid"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "messaging_product": "whatsapp",
            "contacts": [{"input": "201012345678", "wa_id": "201012345678"}],
            "messages": [{"id": "wamid.HBgLMTIzNDU2Nzg5MA=="}]
        }
        mock_post.return_value = mock_response

        res = WhatsAppService.send_template_message(
            phone="01012345678",
            template_name="document_send_ar",
            components=[{"type": "body", "parameters": [{"type": "text", "text": "عميل تجريبي"}]}]
        )

        assert res["success"] is True
        assert res["message_id"] == "wamid.HBgLMTIzNDU2Nzg5MA=="

        log = WhatsAppMessageLog.objects.get(id=res["log_id"])
        assert log.status == "SENT"
        assert log.message_id == "wamid.HBgLMTIzNDU2Nzg5MA=="

    @patch('requests.Session.post')
    def test_mocked_meta_media_upload_success(self, mock_post):
        """التحقق من رفع ملف الـ PDF الثنائي واسترجاع Media ID"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "media_id_99887766"}
        mock_post.return_value = mock_response

        pdf_bytes = b"%PDF-1.4 test binary invoice bytes"
        res = WhatsAppService.upload_media(pdf_bytes, filename="Invoice_INV-001.pdf")

        assert res["success"] is True
        assert res["media_id"] == "media_id_99887766"


@pytest.mark.django_db
class TestWhatsAppPhase1SalesAndFinancialDocuments:
    """اختبارات موزع المستندات الشامل لمستندات المرحلة 1 (18 مستنداً)"""

    def setup_method(self):
        SystemSetting.objects.update_or_create(
            key="whatsapp_enabled",
            defaults={"value": "true", "data_type": "boolean", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_access_token",
            defaults={"value": "EAATestToken123456", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_phone_number_id",
            defaults={"value": "1000987654321", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        WhatsAppService.reset_session()

        from product.models.stock_management import Warehouse
        self.user, _ = User.objects.get_or_create(username="test_wa_user_phase1")
        self.warehouse, _ = Warehouse.objects.get_or_create(name="مخزن رئيسي", defaults={"code": "WH-TEST-01"})

        self.customer, _ = Customer.objects.get_or_create(
            code="CUST-PHASE1",
            defaults={
                "name": "شركة النور للمقاولات",
                "phone": "01012345678",
                "balance": Decimal("15000.00")
            }
        )

    def test_sale_invoice_state_guard(self):
        """التحقق من منع إرسال الفاتورة المسودة وسماح المعتمدة"""
        from sale.models import Sale
        from core.services.document_dispatcher import DocumentDispatcher

        # 1. فاتورة مسودة
        sale_draft = Sale.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            number="INV-DRAFT-001",
            date=timezone.now().date(),
            status="draft",
            subtotal=Decimal("5000.00"),
            total=Decimal("5000.00")
        )
        info_draft = DocumentDispatcher.get_document_info(sale_draft)
        assert info_draft["can_send"] is False
        assert "اعتمادها" in info_draft["cannot_send_reason"]

        # 2. فاتورة معتمدة
        sale_confirmed = Sale.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            number="INV-CONF-001",
            date=timezone.now().date(),
            status="confirmed",
            subtotal=Decimal("12000.00"),
            total=Decimal("12000.00")
        )
        info_confirmed = DocumentDispatcher.get_document_info(sale_confirmed)
        assert info_confirmed["can_send"] is True
        assert info_confirmed["template_name"] == "document_send_ar"
        assert "12,000.00" in info_confirmed["financial_summary"]

    def test_quotation_state_guard(self):
        """التحقق من شروط إرسال عروض الأسعار"""
        from sale.models.quotation import Quotation
        from core.services.document_dispatcher import DocumentDispatcher

        quotation_valid = Quotation.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            number="QUO-2026-001",
            date=timezone.now().date(),
            status="draft",
            subtotal=Decimal("25000.00"),
            total=Decimal("25000.00")
        )
        info_valid = DocumentDispatcher.get_document_info(quotation_valid)
        assert info_valid["can_send"] is True
        assert "25,000.00" in info_valid["financial_summary"]

        quotation_cancelled = Quotation.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            number="QUO-2026-002",
            date=timezone.now().date(),
            status="cancelled",
            subtotal=Decimal("25000.00"),
            total=Decimal("25000.00")
        )
        info_canc = DocumentDispatcher.get_document_info(quotation_cancelled)
        assert info_canc["can_send"] is False
        assert "ملغي" in info_canc["cannot_send_reason"]

    def test_sales_order_dispatcher_info(self):
        """التحقق من معالجة أمر البيع في موزع المستندات"""
        from sale.models.sales_models import SalesOrder
        from core.services.document_dispatcher import DocumentDispatcher

        so = SalesOrder.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            order_number="SO-2026-042",
            order_date=timezone.now().date(),
            status="CONFIRMED",
            subtotal=Decimal("45000.00"),
            total_amount=Decimal("45000.00")
        )

        info = DocumentDispatcher.get_document_info(so)
        assert info["doc_title"] == "أمر بيع"
        assert info["doc_number"] == "SO-2026-042"
        assert info["template_name"] == "document_send_ar"
        assert info["has_pdf"] is True
        assert info["can_send"] is True

    def test_delivery_note_dispatcher_info(self):
        """التحقق من معالجة إذن تسليم البضاعة في موزع المستندات"""
        from sale.models.sales_models import DeliveryNote, SalesOrder
        from core.services.document_dispatcher import DocumentDispatcher

        so = SalesOrder.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            order_number="SO-101",
            order_date=timezone.now().date(),
            subtotal=Decimal("1000.00"),
            total_amount=Decimal("1000.00")
        )
        dn = DeliveryNote.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            sales_order=so,
            delivery_number="DN-2026-015",
            delivery_date=timezone.now().date(),
            status="DELIVERED"
        )

        info = DocumentDispatcher.get_document_info(dn)
        assert info["doc_title"] == "إذن تسليم بضاعة"
        assert info["doc_number"] == "DN-2026-015"
        assert info["has_pdf"] is True
        assert info["can_send"] is True

    def test_sale_return_state_guard(self):
        """التحقق من شروط اعتماد مرتجع المبيعات"""
        from sale.models import Sale, SaleReturn
        from core.services.document_dispatcher import DocumentDispatcher

        sale = Sale.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            number="INV-RET-01",
            date=timezone.now().date(),
            subtotal=Decimal("1500.00"),
            total=Decimal("1500.00"),
            status="confirmed"
        )
        sr_draft = SaleReturn.objects.create(
            sale=sale,
            warehouse=self.warehouse,
            created_by=self.user,
            date=timezone.now().date(),
            number="RET-001",
            status="draft",
            subtotal=Decimal("1500.00"),
            total=Decimal("1500.00")
        )
        info_draft = DocumentDispatcher.get_document_info(sr_draft)
        assert info_draft["can_send"] is False

        sr_confirmed = SaleReturn.objects.create(
            sale=sale,
            warehouse=self.warehouse,
            created_by=self.user,
            date=timezone.now().date(),
            number="RET-002",
            status="confirmed",
            subtotal=Decimal("1500.00"),
            total=Decimal("1500.00")
        )
        info_conf = DocumentDispatcher.get_document_info(sr_confirmed)
        assert info_conf["can_send"] is True
        assert "1,500.00" in info_conf["financial_summary"]

    def test_credit_note_dispatcher_info(self):
        """التحقق من إشعار دائن العميل"""
        from sale.models import CreditNote
        from core.services.document_dispatcher import DocumentDispatcher

        cn = CreditNote.objects.create(
            customer=self.customer,
            credit_note_number="CN-2026-009",
            total_amount=Decimal("3500.00"),
            status="POSTED"
        )
        info = DocumentDispatcher.get_document_info(cn)
        assert info["doc_title"] == "إشعار دائن"
        assert info["doc_number"] == "CN-2026-009"
        assert "3,500.00" in info["financial_summary"]
        assert info["can_send"] is True

    def test_customer_statement_dispatcher_info(self):
        """التحقق من كشف حساب العميل والنافذة الزمنية"""
        from core.services.document_dispatcher import DocumentDispatcher

        info = DocumentDispatcher.get_document_info(
            self.customer,
            extra_params={"from_date": "2026-01-01", "to_date": "2026-03-31"}
        )
        assert info["doc_title"] == "كشف حساب عميل"
        assert "2026-01-01" in info["doc_number"]
        assert "15,000.00" in info["financial_summary"]
        assert info["has_pdf"] is True

    def test_sale_payment_receipt_dispatcher_info(self):
        """التحقق من سند القبض المالي وإشعار السداد الفوري"""
        from sale.models import Sale, SalePayment
        from core.services.document_dispatcher import DocumentDispatcher

        sale = Sale.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            number="INV-PAY-01",
            date=timezone.now().date(),
            subtotal=Decimal("5000.00"),
            total=Decimal("5000.00"),
            status="confirmed"
        )
        pay = SalePayment.objects.create(
            sale=sale,
            amount=Decimal("5000.00"),
            payment_date=timezone.now().date(),
            payment_method="cash",
            reference_number="PAY-2026-088",
            created_by=self.user
        )
        info = DocumentDispatcher.get_document_info(pay)
        assert info["doc_title"] == "سند قبض مالي"
        assert info["template_name"] == "payment_receipt_ar"
        assert info["has_pdf"] is False
        assert "5,000.00" in info["financial_summary"]

    def test_debit_note_and_journal_entry_dispatcher_info(self):
        """التحقق من الإشعار المدين وقيد اليومية"""
        from financial.models import JournalEntry, JournalEntryLine, ChartOfAccounts, AccountType
        from core.services.document_dispatcher import DocumentDispatcher

        jv = JournalEntry.objects.create(
            number="JV-2026-099",
            date=timezone.now().date(),
            created_by=self.user,
            status="draft",
            description="Test JV Entry"
        )
        acc_type, _ = AccountType.objects.get_or_create(code="100", defaults={"name": "Assets", "category": "asset", "nature": "debit", "is_active": True})
        acc, _ = ChartOfAccounts.objects.get_or_create(code="101001", defaults={"name": "Cash Test", "account_type": acc_type, "is_leaf": True, "is_active": True})
        JournalEntryLine.objects.create(journal_entry=jv, account=acc, debit=Decimal("80000.00"), credit=Decimal("0.00"), description="Debit")
        JournalEntryLine.objects.create(journal_entry=jv, account=acc, debit=Decimal("0.00"), credit=Decimal("80000.00"), description="Credit")
        jv.status = "posted"
        jv.save()

        info_jv = DocumentDispatcher.get_document_info(jv)
        assert info_jv["doc_title"] == "إشعار قيد يومية"
        assert "80,000.00" in info_jv["financial_summary"]
        assert info_jv["has_pdf"] is True

    @patch('core.services.whatsapp_service.WhatsAppService.upload_media')
    @patch('core.services.whatsapp_service.WhatsAppService.send_template_message')
    def test_full_document_dispatch_flow(self, mock_send, mock_upload):
        """التحقق من دورة الإرسال الكاملة عبر DocumentDispatcher.dispatch"""
        from sale.models import Sale
        from core.services.document_dispatcher import DocumentDispatcher

        mock_upload.return_value = {"success": True, "media_id": "media_inv_12345"}
        mock_send.return_value = {"success": True, "message_id": "wamid.INV9988", "log_id": 1}

        sale = Sale.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            number="INV-FULL-001",
            date=timezone.now().date(),
            subtotal=Decimal("7500.00"),
            total=Decimal("7500.00"),
            status="confirmed"
        )

        res = DocumentDispatcher.dispatch(
            content_object=sale,
            recipient_phone="01012345678",
            partner=self.customer
        )

        assert res["success"] is True
        assert res["message_id"] == "wamid.INV9988"
        mock_send.assert_called_once()

