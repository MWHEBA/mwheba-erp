# -*- coding: utf-8 -*-
"""
اختبارات شاملة للمرحلة الثانية من منظومة WhatsApp Business Cloud API
MWHEBA ERP — WhatsApp Phase 2 Pytest Suite (Dispatcher, PDF Pipeline, Views API)
"""
import json
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory
from django.urls import reverse

from core.models import SystemSetting, WhatsAppMessageLog
from core.services.whatsapp_service import WhatsAppService
from core.services.document_dispatcher import DocumentDispatcher
from core.views.whatsapp_views import (
    whatsapp_prepare_send,
    whatsapp_send_document,
    whatsapp_document_status,
    whatsapp_partner_logs
)
from customer.models import Customer
from supplier.models import Supplier
from product.models import Warehouse
from sale.models import Sale, Quotation
from purchase.models import Purchase
from purchase.models.procurement_models import PurchaseOrder

User = get_user_model()


@pytest.mark.django_db
class TestWhatsAppPhase2Dispatcher:
    """اختبارات موزع المستندات الموحد وقوالب المراسلة وتوليد الـ PDF وكاش الميديا"""

    def setup_method(self):
        # تهيئة إعدادات النظام
        SystemSetting.objects.update_or_create(
            key="whatsapp_enabled",
            defaults={"value": "true", "data_type": "boolean", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_access_token",
            defaults={"value": "EAATestTokenPhase2", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_phone_number_id",
            defaults={"value": "1000123456789", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="company_name",
            defaults={"value": "شركة موهبة للطباعة والتوريدات", "data_type": "string", "group": "general", "is_active": True}
        )

        from django.core.cache import cache
        cache.clear()
        WhatsAppService.reset_session()

        self.user = User.objects.create_user(username="test_dispatcher_user", password="password123")
        self.warehouse = Warehouse.objects.create(name="المخزن الرئيسي", code="WH-DISPATCH-01")

        self.customer = Customer.objects.create(
            name="مؤسسة النور الحديثة",
            code="CUST-001",
            phone="01011112222",
            balance=Decimal("25000.00")
        )

        self.supplier = Supplier.objects.create(
            name="شركة الأهرام للورق",
            code="SUPP-001",
            phone="01233334444",
            balance=Decimal("18000.00")
        )

    def test_sale_document_info_confirmed(self):
        """التحقق من استخراج بيانات فاتورة المبيعات المعتمدة وتطبيق القالب الصارم"""
        sale = Sale.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            number="INV-2026-0001",
            date=timezone.now().date(),
            status="confirmed",
            subtotal=Decimal("15250.00"),
            total=Decimal("15250.00")
        )

        info = DocumentDispatcher.get_document_info(sale)
        assert info["doc_title"] == "فاتورة مبيعات"
        assert info["doc_number"] == "INV-2026-0001"
        assert info["partner"] == self.customer
        assert info["can_send"] is True
        assert info["has_pdf"] is True
        assert info["template_name"] == "document_send_ar"
        assert "15,250.00" in info["financial_summary"]
        assert len(info["components"]) == 1
        params = info["components"][0]["parameters"]
        assert len(params) == 4
        assert params[0]["text"] == "مؤسسة النور الحديثة"

    def test_sale_state_guard_draft_blocked(self):
        """التحقق من حظر إرسال الفاتورة غير المعتمدة (مسودة) عبر State Guard"""
        draft_sale = Sale.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            number="INV-2026-DRAFT",
            date=timezone.now().date(),
            status="draft",
            subtotal=Decimal("5000.00"),
            total=Decimal("5000.00")
        )

        info = DocumentDispatcher.get_document_info(draft_sale)
        assert info["can_send"] is False
        assert "قبل اعتمادها" in info["cannot_send_reason"]

        res = DocumentDispatcher.dispatch(draft_sale, recipient_phone="01011112222")
        assert res["success"] is False
        assert "قبل اعتمادها" in res["error"]

    def test_quotation_cancelled_blocked(self):
        """التحقق من حظر إرسال عرض الأسعار الملغي"""
        quotation = Quotation.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            number="QUO-2026-0009",
            date=timezone.now().date(),
            status="cancelled",
            subtotal=Decimal("8000.00"),
            total=Decimal("8000.00")
        )

        info = DocumentDispatcher.get_document_info(quotation)
        assert info["can_send"] is False
        assert "ملغي" in info["cannot_send_reason"]

    def test_customer_statement_info(self):
        """التحقق من استخراج بيانات كشف حساب العميل ونطاق التواريخ"""
        extra = {"from_date": "2026-01-01", "to_date": "2026-09-28"}
        info = DocumentDispatcher.get_document_info(self.customer, extra_params=extra)

        assert info["doc_title"] == "كشف حساب عميل"
        assert "CUST-001" in info["doc_number"]
        assert "25,000.00" in info["financial_summary"]
        assert info["partner"] == self.customer

    def test_pdf_rendering_fallback(self):
        """التحقق من توليد بايتات الـ PDF المضمونة بدون انهيار"""
        sale = Sale.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            number="INV-2026-PDF-TEST",
            date=timezone.now().date(),
            status="confirmed",
            subtotal=Decimal("1200.00"),
            total=Decimal("1200.00")
        )

        pdf_bytes, filename = DocumentDispatcher.render_document_pdf_bytes(sale)
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 0
        assert filename.endswith(".pdf")

    @patch('core.services.whatsapp_service.WhatsAppService.upload_media')
    def test_media_cache_timestamp_invalidation(self, mock_upload):
        """التحقق من حفظ واسترجاع الـ Media ID من الكاش وإبطاله عند تعديل المستند"""
        mock_upload.return_value = {"success": True, "media_id": "meta_media_id_554433"}

        sale = Sale.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            number="INV-2026-CACHE",
            date=timezone.now().date(),
            status="confirmed",
            subtotal=Decimal("3000.00"),
            total=Decimal("3000.00")
        )

        # الرفع لأول مرة
        pdf_bytes = b"%PDF test bytes"
        media_id1 = DocumentDispatcher.get_or_upload_media_id(sale, pdf_bytes, "Invoice_INV.pdf")
        assert media_id1 == "meta_media_id_554433"
        assert mock_upload.call_count == 1

        # المرة الثانية (يجب أن يجلب من الكاش دون استدعاء Meta Upload)
        media_id2 = DocumentDispatcher.get_or_upload_media_id(sale, pdf_bytes, "Invoice_INV.pdf")
        assert media_id2 == "meta_media_id_554433"
        assert mock_upload.call_count == 1  # لم يتغير العدد

    @patch('requests.Session.post')
    def test_dispatch_end_to_end_success(self, mock_post):
        """التحقق من تنفيذ الإرسال الشامل بنجاح عبر DocumentDispatcher وتوثيق السجل"""
        mock_upload_resp = MagicMock()
        mock_upload_resp.status_code = 200
        mock_upload_resp.json.return_value = {"id": "meta_media_id_9999"}

        mock_send_resp = MagicMock()
        mock_send_resp.status_code = 200
        mock_send_resp.json.return_value = {
            "messaging_product": "whatsapp",
            "messages": [{"id": "wamid.HBgLUEhBU0UyVEVTVDEyMw=="}]
        }

        # Session.post للرفع أولاً ثم للإرسال
        mock_post.side_effect = [mock_upload_resp, mock_send_resp]

        sale = Sale.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            number="INV-2026-DISPATCH",
            date=timezone.now().date(),
            status="confirmed",
            subtotal=Decimal("7500.00"),
            total=Decimal("7500.00")
        )

        res = DocumentDispatcher.dispatch(
            content_object=sale,
            recipient_phone="01011112222",
            partner=self.customer
        )

        assert res["success"] is True
        assert res["message_id"] == "wamid.HBgLUEhBU0UyVEVTVDEyMw=="

        log = WhatsAppMessageLog.objects.get(id=res["log_id"])
        assert log.status == "SENT"
        assert log.recipient_phone == "201011112222"
        assert log.customer == self.customer
        assert log.has_media is True

    def test_purchase_order_dispatcher_info(self):
        """التحقق من معالجة أمر الشراء للمورد وحماية حالة الاعتماد"""
        from purchase.models.procurement_models import PurchaseOrder

        po = PurchaseOrder.objects.create(
            supplier=self.supplier,
            warehouse=self.warehouse,
            created_by=self.user,
            order_number="PO-2026-099",
            order_date=timezone.now().date(),
            status="APPROVED",
            subtotal=Decimal("35000.00"),
            total_amount=Decimal("35000.00")
        )

        info = DocumentDispatcher.get_document_info(po)
        assert info["doc_title"] == "أمر شراء"
        assert info["doc_number"] == "PO-2026-099"
        assert info["partner"] == self.supplier
        assert info["partner_type"] == "supplier"
        assert info["can_send"] is True
        assert info["has_pdf"] is True
        assert "35,000.00" in info["financial_summary"]

        pdf_bytes, filename = DocumentDispatcher.render_document_pdf_bytes(po)
        assert pdf_bytes is not None
        assert filename.startswith("PO_")

    def test_goods_received_note_dispatcher_info(self):
        """التحقق من معالجة إذن استلام بضاعة GRN"""
        from purchase.models.procurement_models import GoodsReceivedNote

        grn = GoodsReceivedNote.objects.create(
            supplier=self.supplier,
            warehouse=self.warehouse,
            grn_number="GRN-2026-044",
            status="POSTED"
        )

        info = DocumentDispatcher.get_document_info(grn)
        assert info["doc_title"] == "إذن استلام بضاعة (GRN)"
        assert info["doc_number"] == "GRN-2026-044"
        assert info["partner"] == self.supplier
        assert info["partner_type"] == "supplier"
        assert info["has_pdf"] is True

        pdf_bytes, filename = DocumentDispatcher.render_document_pdf_bytes(grn)
        assert pdf_bytes is not None
        assert filename.startswith("GRN_")

    def test_purchase_return_dispatcher_info(self):
        """التحقق من مرتجع المشتريات وتفقيط الإجمالي"""
        from purchase.models.purchase import Purchase
        from purchase.models.return_model import PurchaseReturn

        pur = Purchase.objects.create(
            supplier=self.supplier,
            warehouse=self.warehouse,
            created_by=self.user,
            number="PUR-TEST-001",
            date=timezone.now().date(),
            status="confirmed",
            subtotal=Decimal("10000.00"),
            total=Decimal("10000.00")
        )

        pret = PurchaseReturn.objects.create(
            purchase=pur,
            warehouse=self.warehouse,
            created_by=self.user,
            number="PRET-2026-005",
            date=timezone.now().date(),
            status="confirmed",
            subtotal=Decimal("2000.00"),
            total=Decimal("2000.00")
        )

        info = DocumentDispatcher.get_document_info(pret)
        assert info["doc_title"] == "مرتجع مشتريات"
        assert info["doc_number"] == "PRET-2026-005"
        assert info["partner"] == self.supplier
        assert "2,000.00" in info["financial_summary"]
        assert info["has_pdf"] is True

    def test_supplier_statement_dispatcher_info(self):
        """التحقق من كشف حساب المورد الدوري"""
        extra = {"from_date": "2026-01-01", "to_date": "2026-06-30"}
        info = DocumentDispatcher.get_document_info(self.supplier, extra_params=extra)

        assert info["doc_title"] == "كشف حساب مورد"
        assert "SUPP-001" in info["doc_number"]
        assert info["partner"] == self.supplier
        assert "18,000.00" in info["financial_summary"]
        assert info["has_pdf"] is True

        pdf_bytes, filename = DocumentDispatcher.render_document_pdf_bytes(self.supplier)
        assert pdf_bytes is not None
        assert filename.startswith("Supplier_Statement_")

    def test_stock_transfer_dispatcher_info(self):
        """التحقق من إذن تحويل المخزون بين المخازن"""
        from product.models.warehouse import StockTransfer
        from product.models.product_core import Product, Category, Unit

        wh_to = Warehouse.objects.create(name="مخزن فرعي", code="WH-SUB-01")
        cat = Category.objects.create(name="خامات")
        unit = Unit.objects.create(name="قطعة", symbol="PCS")
        prod = Product.objects.create(
            name="ورق كوشيه 150 جرام",
            sku="RAW-001",
            category=cat,
            unit=unit,
            cost_price=Decimal("10.00"),
            selling_price=Decimal("15.00"),
            created_by=self.user
        )

        st = StockTransfer.objects.create(
            from_warehouse=self.warehouse,
            to_warehouse=wh_to,
            product=prod,
            quantity=500,
            transfer_number="TR-2026-888",
            requested_by=self.user,
            status="completed"
        )

        info = DocumentDispatcher.get_document_info(st)
        assert info["doc_title"] == "إذن تحويل بين المخازن"
        assert info["doc_number"] == "TR-2026-888"
        assert "ورق كوشيه" in info["financial_summary"]
        assert "500" in info["financial_summary"]
        assert info["has_pdf"] is True

    def test_work_order_dispatcher_info(self):
        """التحقق من أمر شغل التصنيع والإنتاج"""
        from work_order.models import WorkOrder

        wo = WorkOrder.objects.create(
            number="WO-2026-777",
            customer=self.customer,
            created_by=self.user,
            estimated_cost=Decimal("42000.00"),
            status="in_progress"
        )

        info = DocumentDispatcher.get_document_info(wo)
        assert info["doc_title"] == "أمر شغل تصنيع"
        assert info["doc_number"] == "WO-2026-777"
        assert info["partner"] == self.customer
        assert "42,000.00" in info["financial_summary"]
        assert info["has_pdf"] is True

        pdf_bytes, filename = DocumentDispatcher.render_document_pdf_bytes(wo)
        assert pdf_bytes is not None
        assert filename.startswith("WorkOrder_")

    def test_printing_order_dispatcher_info(self):
        """التحقق من عرض تسعير المطبوعات"""
        from printing_pricing.models.order import PrintingOrder

        po = PrintingOrder.objects.create(
            order_number="PRINT-2026-12",
            customer=self.customer,
            created_by=self.user,
            quantity=1000,
            final_price=Decimal("16500.00"),
            title="طباعة بروشورات فاخرة"
        )

        info = DocumentDispatcher.get_document_info(po)
        assert info["doc_title"] == "عرض تسعير مطبوعات"
        assert info["doc_number"] == "PRINT-2026-12"
        assert info["partner"] == self.customer
        assert "16,500.00" in info["financial_summary"]
        assert info["has_pdf"] is True

        pdf_bytes, filename = DocumentDispatcher.render_document_pdf_bytes(po)
        assert pdf_bytes is not None
        assert filename.startswith("PrintingOrder_")


@pytest.mark.django_db
class TestWhatsAppViewsAPI:
    """اختبارات العروض والواجهات البرمجية (API Endpoints) وحوكمة الصلاحيات"""

    def setup_method(self):
        # تهيئة إعدادات النظام للـ API
        SystemSetting.objects.update_or_create(
            key="whatsapp_enabled",
            defaults={"value": "true", "data_type": "boolean", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_access_token",
            defaults={"value": "EAATestTokenPhase2Views", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_phone_number_id",
            defaults={"value": "1000123456789", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="company_name",
            defaults={"value": "شركة موهبة للطباعة والتوريدات", "data_type": "string", "group": "general", "is_active": True}
        )

        from django.core.cache import cache
        cache.clear()
        WhatsAppService.reset_session()

        self.user = User.objects.create_user(
            username="test_accountant_views",
            email="accountant_views@example.com",
            password="password123"
        )
        
        # منح الصلاحيات الثنائية
        can_send_perm = Permission.objects.get(codename="can_send_whatsapp")
        view_sale_perm = Permission.objects.get(codename="view_sale")
        self.user.user_permissions.add(can_send_perm, view_sale_perm)

        self.warehouse = Warehouse.objects.create(name="مخزن الواجهات", code="WH-VIEWS-01")

        self.customer = Customer.objects.create(
            name="شركة السهم الذهبي",
            code="CUST-GOLD",
            phone="01022223333",
            balance=Decimal("14000.00")
        )

        self.sale = Sale.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            number="INV-2026-VIEW",
            date=timezone.now().date(),
            status="confirmed",
            subtotal=Decimal("6200.00"),
            total=Decimal("6200.00")
        )
        self.ct_sale = ContentType.objects.get_for_model(Sale)

    def test_whatsapp_prepare_send_api(self, client):
        """التحقق من استجابة واجهة تجهيز بيانات الإرسال للمودال (GET prepare)"""
        client.force_login(self.user)
        response = client.get(f"/api/whatsapp/prepare/?content_type_id={self.ct_sale.id}&object_id={self.sale.pk}")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["doc_title"] == "فاتورة مبيعات"
        assert data["doc_number"] == "INV-2026-VIEW"
        assert data["partner_name"] == "شركة السهم الذهبي"
        assert len(data["phone_options"]) >= 1
        assert data["can_send"] is True

    @patch('requests.Session.post')
    def test_whatsapp_send_document_api(self, mock_post, client):
        """التحقق من تنفيذ إرسال المستند عبر الـ API (POST send)"""
        mock_upload_resp = MagicMock()
        mock_upload_resp.status_code = 200
        mock_upload_resp.json.return_value = {"id": "media_view_123"}

        mock_send_resp = MagicMock()
        mock_send_resp.status_code = 200
        mock_send_resp.json.return_value = {
            "messaging_product": "whatsapp",
            "messages": [{"id": "wamid.HBgLVklFV0FQSTc4OQ=="}]
        }
        mock_post.side_effect = [mock_upload_resp, mock_send_resp]

        payload = {
            "content_type_id": self.ct_sale.id,
            "object_id": self.sale.pk,
            "phone": "01022223333",
            "partner_id": self.customer.pk,
            "partner_type": "customer"
        }

        client.force_login(self.user)
        response = client.post(
            "/api/whatsapp/send/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["message_id"] == "wamid.HBgLVklFV0FQSTc4OQ=="

    def test_whatsapp_document_status_api(self, client):
        """التحقق من قراءة الحالة اللحظية لشارة الهيدر (GET status)"""
        client.force_login(self.user)

        # قبل الإرسال
        resp1 = client.get(f"/api/whatsapp/status/?content_type_id={self.ct_sale.id}&object_id={self.sale.pk}")
        data1 = resp1.json()
        assert data1["has_sent"] is False

        # تسجيل رسالة
        WhatsAppMessageLog.objects.create(
            content_type=self.ct_sale,
            object_id=self.sale.pk,
            recipient_phone="201022223333",
            template_name="document_send_ar",
            status="READ",
            message_id="wamid.STATUS_TEST"
        )

        # بعد الإرسال
        resp2 = client.get(f"/api/whatsapp/status/?content_type_id={self.ct_sale.id}&object_id={self.sale.pk}")
        data2 = resp2.json()
        assert data2["has_sent"] is True
        assert data2["status"] == "READ"

    def test_whatsapp_partner_logs_api(self, client):
        """التحقق من جلب سجل رسائل الشريك لويدجت تفاصيل العميل"""
        client.force_login(self.user)
        WhatsAppMessageLog.objects.create(
            customer=self.customer,
            recipient_phone="201022223333",
            template_name="document_send_ar",
            status="DELIVERED"
        )

        response = client.get(f"/api/whatsapp/partner/customer/{self.customer.pk}/")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert len(data["logs"]) >= 1
        assert data["logs"][0]["status"] == "DELIVERED"

    def test_permission_denied_without_can_send_whatsapp(self, client):
        """التحقق من رفض الوصول للـ API في حال عدم امتلاك الصلاحية can_send_whatsapp"""
        unauthorized_user = User.objects.create_user(
            username="unauth_user_distinct",
            email="unauth_distinct@example.com",
            password="password123"
        )
        
        client.force_login(unauthorized_user)
        response = client.get(f"/api/whatsapp/prepare/?content_type_id={self.ct_sale.id}&object_id={self.sale.pk}")
        assert response.status_code == 403
        data = response.json()
        assert data["success"] is False
        assert "الصلاحية" in data["error"]
