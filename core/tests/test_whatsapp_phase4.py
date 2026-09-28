# -*- coding: utf-8 -*-
"""
اختبارات شاملة للمرحلة الرابعة من منظومة WhatsApp Business Cloud API
MWHEBA ERP — WhatsApp Phase 4 Pytest Suite (ListView Logs, SSR Pagination, KPI, Details Modal & Fresh Media Resend)
"""
import json
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from core.models import SystemSetting, WhatsAppMessageLog
from core.services.whatsapp_service import WhatsAppService
from customer.models import Customer
from supplier.models import Supplier
from product.models import Warehouse
from sale.models import Sale

User = get_user_model()


@pytest.mark.django_db
class TestWhatsAppPhase4LogsAndAudit:
    """اختبارات سجل الرسائل والمراقبة الشاملة والفلاتر والـ KPI وإعادة الإرسال"""

    def setup_method(self):
        SystemSetting.objects.update_or_create(
            key="whatsapp_enabled",
            defaults={"value": "true", "data_type": "boolean", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_access_token",
            defaults={"value": "EAATestTokenPhase4", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_phone_number_id",
            defaults={"value": "1098765432101", "data_type": "string", "group": "whatsapp", "is_active": True}
        )

        from django.core.cache import cache
        cache.clear()
        WhatsAppService.reset_session()
        WhatsAppMessageLog.objects.all().delete()

        self.user = User.objects.create_user(
            username="test_auditor_p4",
            email="auditor_p4@example.com",
            password="password123",
            is_staff=True
        )
        can_send_perm = Permission.objects.get(codename="can_send_whatsapp")
        view_sale_perm = Permission.objects.get(codename="view_sale")
        self.user.user_permissions.add(can_send_perm, view_sale_perm)

        self.unauth_user = User.objects.create_user(
            username="unauth_auditor_p4",
            email="unauth_p4@example.com",
            password="password123"
        )

        self.customer = Customer.objects.create(
            name="شركة الأهرام للتجارة",
            code="CUST-LOGS-01",
            phone="01011112222"
        )
        self.supplier = Supplier.objects.create(
            name="مصنع النصر للكرتون",
            code="SUPP-LOGS-01",
            phone="01233334444"
        )

        self.warehouse = Warehouse.objects.create(name="مخزن السجلات", code="WH-LOGS-01")
        self.sale = Sale.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            created_by=self.user,
            number="INV-2026-P4-01",
            date=timezone.now().date(),
            status="confirmed",
            subtotal=Decimal("10000.00"),
            total=Decimal("10000.00")
        )
        self.ct_sale = ContentType.objects.get_for_model(Sale)

        # إنشاء سجلات متنوعة لاختبار الفلترة والإحصائيات
        self.log_delivered = WhatsAppMessageLog.objects.create(
            recipient_phone="201011112222",
            recipient_name="شركة الأهرام للتجارة",
            customer=self.customer,
            content_type=self.ct_sale,
            object_id=self.sale.pk,
            template_name="document_send_ar",
            message_id="wamid.DELIV001",
            status="DELIVERED",
            has_media=True,
            created_by=self.user
        )

        self.log_read = WhatsAppMessageLog.objects.create(
            recipient_phone="201011112222",
            recipient_name="شركة الأهرام للتجارة",
            customer=self.customer,
            template_name="payment_receipt_ar",
            message_id="wamid.READ002",
            status="READ",
            has_media=False,
            created_by=self.user
        )

        self.log_failed = WhatsAppMessageLog.objects.create(
            recipient_phone="201233334444",
            recipient_name="مصنع النصر للكرتون",
            supplier=self.supplier,
            template_name="document_send_ar",
            message_id="wamid.FAIL003",
            status="FAILED",
            error_code="131026",
            error_message="الرقم غير مسجل على واتساب",
            has_media=True,
            created_by=self.user
        )

    def test_logs_list_get_authorized(self, client):
        """التحقق من استعراض صفحة سجل رسائل الواتساب وحساب مؤشرات الـ KPI بدقة"""
        client.force_login(self.user)
        response = client.get(reverse("core:whatsapp_logs"))
        assert response.status_code == 200
        assert "logs" in response.context
        assert response.context["total_messages"] == 3
        assert response.context["delivered_count"] == 2  # DELIVERED + READ
        assert response.context["read_count"] == 1
        assert response.context["failed_count"] == 1
        assert response.context["delivery_rate"] == 66.7
        assert response.context["read_rate"] == 33.3

    def test_logs_list_filter_by_status(self, client):
        """التحقق من فلترة الرسائل حسب الحالة (status=FAILED)"""
        client.force_login(self.user)
        response = client.get(reverse("core:whatsapp_logs") + "?status=FAILED")
        assert response.status_code == 200
        assert response.context["total_messages"] == 1
        logs = list(response.context["logs"])
        assert len(logs) == 1
        assert logs[0].status == "FAILED"

    def test_logs_list_filter_by_query_search(self, client):
        """التحقق من البحث السريع برقم الهاتف أو اسم الشريك"""
        client.force_login(self.user)
        response = client.get(reverse("core:whatsapp_logs") + "?q=01233334444")
        assert response.status_code == 200
        logs = list(response.context["logs"])
        assert len(logs) == 1
        assert logs[0].supplier == self.supplier

    def test_logs_list_filter_by_template(self, client):
        """التحقق من فلترة الرسائل بالقالب (template_name=payment_receipt_ar)"""
        client.force_login(self.user)
        response = client.get(reverse("core:whatsapp_logs") + "?template_name=payment_receipt_ar")
        assert response.status_code == 200
        logs = list(response.context["logs"])
        assert len(logs) == 1
        assert logs[0].template_name == "payment_receipt_ar"

    def test_logs_list_ajax_dynamic_search(self, client):
        """التحقق من التبديل الديناميكي عبر AJAX وعودة HTML البارتشال والـ KPI"""
        client.force_login(self.user)
        response = client.get(
            reverse("core:whatsapp_logs") + "?status=DELIVERED",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "table_html" in data
        assert "pagination_html" in data
        assert data["total_messages"] == 1

    def test_logs_list_unauthorized_access(self, client):
        """التحقق من حظر وصول المستخدم غير المصرح له"""
        client.force_login(self.unauth_user)
        response = client.get(reverse("core:whatsapp_logs"))
        assert response.status_code == 200
        assert "غير مصرح" in response.content.decode("utf-8")

    def test_whatsapp_log_detail_api(self, client):
        """التحقق من جلب التفاصيل الكاملة للسجل للمودال عبر الـ API"""
        client.force_login(self.user)
        response = client.get(reverse("core:whatsapp_log_detail", args=[self.log_failed.id]))
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["recipient_phone"] == "201233334444"
        assert data["error_code"] == "131026"
        assert "الرقم غير مسجل" in data["error_message"]

    @patch('requests.Session.post')
    def test_whatsapp_resend_message_with_document_fresh_media(self, mock_post, client):
        """التحقق من إعادة إرسال رسالة مستند مع توليد ورفع PDF حديث في الذاكرة (Fresh Media Resend)"""
        mock_upload_resp = MagicMock()
        mock_upload_resp.status_code = 200
        mock_upload_resp.json.return_value = {"id": "fresh_media_id_998877"}

        mock_send_resp = MagicMock()
        mock_send_resp.status_code = 200
        mock_send_resp.json.return_value = {
            "messaging_product": "whatsapp",
            "messages": [{"id": "wamid.HBgLUkVTRU5EOTk5"}]
        }
        mock_post.side_effect = [mock_upload_resp, mock_send_resp]

        client.force_login(self.user)
        response = client.post(reverse("core:whatsapp_resend_message", args=[self.log_delivered.id]))
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message_id"] == "wamid.HBgLUkVTRU5EOTk5"

        # التأكد من إنشاء أو تحديث سجل جديد لحالة الإرسال الحديث
        new_log = WhatsAppMessageLog.objects.get(id=data["log_id"])
        assert new_log.status == "SENT"
        assert new_log.message_id == "wamid.HBgLUkVTRU5EOTk5"
        assert new_log.has_media is True

    @patch('core.services.whatsapp_service.WhatsAppService.send_template_message')
    def test_whatsapp_resend_message_without_document(self, mock_send, client):
        """التحقق من إعادة إرسال رسالة غير مرتبطة بمستند"""
        mock_send.return_value = {
            "success": True,
            "message_id": "wamid.HBgLUkVTRU5ETk9ET0M=",
            "log_id": self.log_read.id
        }

        client.force_login(self.user)
        response = client.post(reverse("core:whatsapp_resend_message", args=[self.log_read.id]))
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message_id"] == "wamid.HBgLUkVTRU5ETk9ET0M="
