# -*- coding: utf-8 -*-
"""
اختبارات شاملة للمرحلة 0 من منظومة WhatsApp Business Cloud API
MWHEBA ERP — WhatsApp Phase 0 Pytest Suite:
- System Settings & Credentials Configuration
- Phone Normalization, Landline Detection & BiDi Isolation
- Direct Meta Graph API Connection Diagnostics & Latency
- Test Message Sandbox with Backend Debounce Lock
- Template Sync API
- HMAC-SHA256 Webhook Verification & State Machine Safety (Sent -> Delivered -> Read)
- Inbound STOP / Opt-Out Engine
"""
import json
import hmac
import hashlib
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from core.models import SystemSetting, WhatsAppMessageLog
from core.services.whatsapp_service import WhatsAppService
from customer.models import Customer
from supplier.models import Supplier

User = get_user_model()


@pytest.mark.django_db
class TestWhatsAppPhase0Foundation:
    """اختبارات البنية التحتية والإعدادات والتشخيص الحي والـ Webhook للمرحلة 0"""

    def setup_method(self):
        # 1. تهيئة إعدادات النظام للواتساب
        SystemSetting.objects.update_or_create(
            key="whatsapp_enabled",
            defaults={"value": "true", "data_type": "boolean", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_access_token",
            defaults={"value": "EAATestTokenPhase0Mock", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_phone_number_id",
            defaults={"value": "100123456789012", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_waba_id",
            defaults={"value": "200987654321098", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_app_secret",
            defaults={"value": "test_app_secret_phase0_super_secure_key", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_webhook_verify_token",
            defaults={"value": "MWHEBA_TEST_VERIFY_TOKEN_2026", "data_type": "string", "group": "whatsapp", "is_active": True}
        )

        from django.core.cache import cache
        cache.clear()
        WhatsAppService.reset_session()

        # 2. إنشاء مستخدمين للاختبار (مصرح وغير مصرح)
        self.admin_user = User.objects.create_user(
            username="wa_admin_p0",
            email="wa_admin_p0@example.com",
            password="password123",
            is_staff=True,
            is_superuser=True
        )
        self.staff_user = User.objects.create_user(
            username="wa_staff_p0",
            email="wa_staff_p0@example.com",
            password="password123",
            is_staff=True
        )
        can_send_perm = Permission.objects.get(codename="can_send_whatsapp")
        self.staff_user.user_permissions.add(can_send_perm)

        self.unauth_user = User.objects.create_user(
            username="unauth_p0",
            email="unauth_p0@example.com",
            password="password123"
        )

        # 3. إنشاء عميل ومورد
        self.customer = Customer.objects.create(
            name="شركة الوادي للصناعات المتطورة",
            code="CUST-P0-01",
            phone="01099887766"
        )
        self.supplier = Supplier.objects.create(
            name="شركة السويس للتوريدات",
            code="SUPP-P0-01",
            phone="01155443322"
        )

    # ==================== 1. Phone Normalization & Utilities ====================

    def test_phone_normalization_egyptian_numbers(self):
        """التحقق من تنظيف وتوحيد أرقام الهواتف المصرية للصيغة الدولية E.164"""
        assert WhatsAppService.normalize_phone("01099887766") == "201099887766"
        assert WhatsAppService.normalize_phone("1099887766") == "201099887766"
        assert WhatsAppService.normalize_phone("+20 11 5544 3322") == "201155443322"
        assert WhatsAppService.normalize_phone("012-3456-7890") == "201234567890"
        assert WhatsAppService.normalize_phone("01500001111") == "201500001111"

    def test_phone_normalization_gcc_and_international(self):
        """التحقق من معالجة أرقام دول الخليج والدولية"""
        assert WhatsAppService.normalize_phone("0501234567", default_country_code="+966") == "966501234567"
        assert WhatsAppService.normalize_phone("+971501234567") == "971501234567"
        assert WhatsAppService.normalize_phone("00447123456789") == "447123456789"

    def test_landline_detection(self):
        """التحقق من كشف الأرقام الأرضية لمنع إرسال الواتساب لها"""
        assert WhatsAppService.is_landline("0223456789") is True    # القاهرة / الجيزة
        assert WhatsAppService.is_landline("035432100") is True     # الإسكندرية
        assert WhatsAppService.is_landline("0403332211") is True    # طنطا / الغربية
        assert WhatsAppService.is_landline("01012345678") is False  # موبايل فودافون
        assert WhatsAppService.is_landline("01112345678") is False  # موبايل اتصالات

    def test_isolate_bidi_and_sanitize_filename(self):
        """التحقق من عزل النصوص ثنائية الاتجاه BiDi وتطهير أسماء الملفات المرفقة"""
        bidi_doc = WhatsAppService.isolate_bidi("INV-2026-001")
        assert bidi_doc.startswith("\u200E")
        assert bidi_doc.endswith("\u200E")
        assert "INV-2026-001" in bidi_doc

        clean_fn = WhatsAppService.sanitize_filename("فاتورة مبيعات رقم #101/2026?.pdf")
        assert "/" not in clean_fn
        assert "#" not in clean_fn
        assert "?" not in clean_fn
        assert clean_fn.endswith(".pdf")

    # ==================== 2. Meta Graph API Test Ping & Diagnostics ====================

    @patch('requests.Session.get')
    def test_meta_test_connection_success(self, mock_get):
        """التحقق من فحص الاتصال الحي بـ Meta واسترجاع مؤشرات الجودة والـ Tier"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "display_phone_number": "+20 10 9988 7766",
            "verified_name": "MWHEBA ERP OFFICIAL",
            "quality_rating": "GREEN",
            "code_verification_status": "VERIFIED"
        }
        mock_get.return_value = mock_resp

        res = WhatsAppService.test_connection(
            access_token="EAATestToken",
            phone_number_id="100123456789012"
        )
        assert res["success"] is True
        assert res["display_phone"] == "+20 10 9988 7766"
        assert res["verified_name"] == "MWHEBA ERP OFFICIAL"
        assert "Green" in res["quality_rating"]
        assert "latency_ms" in res

    @patch('requests.Session.get')
    def test_meta_test_connection_expired_token_error(self, mock_get):
        """التحقق من ترجمة أخطاء ميتا التوجيهية (مثل انتهاء التوكن كود 190)"""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {
            "error": {
                "message": "Invalid OAuth access token.",
                "type": "OAuthException",
                "code": 190
            }
        }
        mock_get.return_value = mock_resp

        res = WhatsAppService.test_connection(
            access_token="ExpiredToken",
            phone_number_id="100123456789012"
        )
        assert res["success"] is False
        assert res["error_code"] == 190
        assert "رمز الوصول" in res["message"]

    # ==================== 3. Live Test Message & Backend Debounce Lock ====================

    @patch('requests.Session.post')
    def test_send_test_message_and_debounce_lock(self, mock_post):
        """التحقق من إرسال رسالة تجريبية وتفعيل قفل منع التكرار السحابي (Debounce Lock)"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "messaging_product": "whatsapp",
            "messages": [{"id": "wamid.TESTMESSAGE001"}]
        }
        mock_post.return_value = mock_resp

        # الإرسال الأول الناجح
        res1 = WhatsAppService.send_test_message(phone="01099887766")
        assert res1["success"] is True
        assert res1["message_id"] == "wamid.TESTMESSAGE001"

        # محاولة الإرسال الفوري لنفس الرقم والقالب قبل انتهاء الـ Debounce
        from django.core.cache import cache
        cache.set("wa_send_lock_201099887766_document_send_ar", "locked", timeout=15)

        res2 = WhatsAppService.send_test_message(phone="01099887766")
        assert res2["success"] is False
        assert "جاري إرسال نفس الرسالة" in res2["error"]

    # ==================== 4. Template Sync API ====================

    @patch('requests.Session.get')
    def test_whatsapp_sync_templates_api(self, mock_get, client):
        """التحقق من مزامنة القوالب المعتمدة من Meta Graph API"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"name": "document_send_ar", "status": "APPROVED", "language": "ar"},
                {"name": "payment_receipt_ar", "status": "APPROVED", "language": "ar"},
                {"name": "account_statement_ar", "status": "APPROVED", "language": "ar"}
            ]
        }
        mock_get.return_value = mock_resp

        client.force_login(self.staff_user)
        response = client.get(reverse("core:whatsapp_sync_templates"))
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 3
        assert len(data["templates"]) == 3

    # ==================== 5. HMAC-SHA256 & Webhook Verification ====================

    def test_webhook_get_verification_challenge_success(self, client):
        """التحقق من قبول تحدي الاشتراك (hub.challenge) مع الـ Verify Token الصحيح"""
        response = client.get(
            reverse("core:whatsapp_webhook"),
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "MWHEBA_TEST_VERIFY_TOKEN_2026",
                "hub.challenge": "1122334455"
            }
        )
        assert response.status_code == 200
        assert response.content.decode("utf-8") == "1122334455"

    def test_webhook_get_verification_challenge_invalid_token(self, client):
        """التحقق من رفض تحدي الاشتراك عند استخدام Verify Token خاطئ"""
        response = client.get(
            reverse("core:whatsapp_webhook"),
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "WRONG_TOKEN",
                "hub.challenge": "1122334455"
            }
        )
        assert response.status_code == 403

    def test_webhook_post_hmac_signature_verification(self, client):
        """التحقق من فحص توقيع HMAC-SHA256 لمنع تزوير الـ Webhook"""
        payload = json.dumps({
            "object": "whatsapp_business_account",
            "entry": []
        }).encode('utf-8')

        app_secret = "test_app_secret_phase0_super_secure_key"
        valid_sig = "sha256=" + hmac.new(app_secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()

        # إرسال توقيع صحيح
        response = client.post(
            reverse("core:whatsapp_webhook"),
            data=payload,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=valid_sig
        )
        assert response.status_code == 200

        # إرسال توقيع غير صالح
        response_invalid = client.post(
            reverse("core:whatsapp_webhook"),
            data=payload,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256="sha256=invalid_tampered_signature"
        )
        assert response_invalid.status_code == 403

    # ==================== 6. Status Transition State Machine & Out-of-Order Safety ====================

    def test_webhook_status_progression_and_anti_rollback(self, client):
        """التحقق من التدرج الآمن لحالات التسليم (SENT -> DELIVERED -> READ) ومنع الارتداد"""
        # إنشاء سجل بحالة SENT
        log = WhatsAppMessageLog.objects.create(
            recipient_phone="201099887766",
            recipient_name="شركة الوادي",
            customer=self.customer,
            template_name="document_send_ar",
            message_id="wamid.STATUS_TEST_001",
            status="SENT",
            created_by=self.staff_user
        )

        app_secret = "test_app_secret_phase0_super_secure_key"

        # 1. إرسال حدث DELIVERED
        payload_delivered = json.dumps({
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [{
                            "id": "wamid.STATUS_TEST_001",
                            "status": "delivered",
                            "timestamp": "1727500000"
                        }]
                    }
                }]
            }]
        }).encode('utf-8')
        sig1 = "sha256=" + hmac.new(app_secret.encode('utf-8'), payload_delivered, hashlib.sha256).hexdigest()
        client.post(reverse("core:whatsapp_webhook"), data=payload_delivered, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sig1)

        log.refresh_from_db()
        assert log.status == "DELIVERED"

        # 2. إرسال حدث READ
        payload_read = json.dumps({
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [{
                            "id": "wamid.STATUS_TEST_001",
                            "status": "read",
                            "timestamp": "1727500100"
                        }]
                    }
                }]
            }]
        }).encode('utf-8')
        sig2 = "sha256=" + hmac.new(app_secret.encode('utf-8'), payload_read, hashlib.sha256).hexdigest()
        client.post(reverse("core:whatsapp_webhook"), data=payload_read, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sig2)

        log.refresh_from_db()
        assert log.status == "READ"

        # 3. محاكاة وصول webhook متأخر بحالة DELIVERED (يجب ألا يرتد السجل إلى DELIVERED)
        client.post(reverse("core:whatsapp_webhook"), data=payload_delivered, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sig1)
        log.refresh_from_db()
        assert log.status == "READ"

    # ==================== 7. Inbound STOP / Opt-Out Engine ====================

    def test_webhook_inbound_opt_out_keyword(self, client):
        """التحقق من رصد كلمات إلغاء الاشتراك (STOP / إلغاء) وتحديث سجل العميل فوراً"""
        assert self.customer.whatsapp_opt_out is False

        app_secret = "test_app_secret_phase0_super_secure_key"
        payload_opt_out = json.dumps({
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "201099887766",
                            "id": "wamid.INBOUND_STOP_01",
                            "type": "text",
                            "text": {"body": "STOP"}
                        }]
                    }
                }]
            }]
        }).encode('utf-8')
        sig = "sha256=" + hmac.new(app_secret.encode('utf-8'), payload_opt_out, hashlib.sha256).hexdigest()

        response = client.post(reverse("core:whatsapp_webhook"), data=payload_opt_out, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sig)
        assert response.status_code == 200

        self.customer.refresh_from_db()
        assert self.customer.whatsapp_opt_out is True
        assert self.customer.whatsapp_opt_out_at is not None

        # محاولة إرسال رسالة لعميل ملغي للاشتراك -> يتم تخطيها بحالة SKIPPED
        skip_res = WhatsAppService.send_template_message(
            phone="01099887766",
            template_name="document_send_ar",
            partner=self.customer
        )
        assert skip_res["success"] is False
        assert "إلغاء الاشتراك" in skip_res["error"]

    # ==================== 8. Settings View & Form Update ====================

    def test_whatsapp_settings_view_get_and_post(self, client):
        """التحقق من استعراض وحفظ إعدادات الواتساب عبر الواجهة بـ 4 تبويبات"""
        client.force_login(self.admin_user)

        # GET
        response = client.get(reverse("core:whatsapp_settings"))
        assert response.status_code == 200
        assert "config" in response.context
        assert response.context["config"]["access_token"] == "EAATestTokenPhase0Mock"

        # POST (تحديث الإعدادات)
        post_data = {
            "whatsapp_enabled": "on",
            "whatsapp_access_token": "EAANewPermanentToken2026",
            "whatsapp_phone_number_id": "100999888777",
            "whatsapp_waba_id": "200999888777",
            "whatsapp_app_secret": "new_app_secret_abc123",
            "whatsapp_default_country_code": "+20",
            "whatsapp_fallback_template": "document_send_ar",
            "whatsapp_fallback_template_lang": "ar",
            "public_portal_url": "https://mwheba.co.uk",
            "whatsapp_send_invoice": "on",
            "whatsapp_send_payment": "on",
            "whatsapp_send_overdue": "on",
            "whatsapp_overdue_days": "10",
            "whatsapp_skip_landlines": "on",
            "whatsapp_honor_opt_out": "on",
        }
        res_post = client.post(reverse("core:whatsapp_settings"), data=post_data)
        assert res_post.status_code == 302

        # التحقق من تحديث الإعدادات في قاعدة البيانات
        assert SystemSetting.get_setting("whatsapp_access_token") == "EAANewPermanentToken2026"
        assert SystemSetting.get_setting("whatsapp_overdue_days") == 10
        assert SystemSetting.get_setting("public_portal_url") == "https://mwheba.co.uk"
