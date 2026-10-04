# -*- coding: utf-8 -*-
"""
مصفوفة الاختبارات الآلية الشاملة للمرحلة الثانية:
مزود الحلول التكنولوجية (Meta Tech Provider)، التسجيل المضمن (Embedded Signup)،
التعايش المتوازي (Coexistence)، والتشفير بـ AES-256 (5-Point Pytest & Mocking Matrix)
"""
import pytest
from unittest.mock import patch, MagicMock
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.conf import settings

from core.models import WhatsAppAccount, WhatsAppMessageLog, SystemSetting
from core.services.whatsapp_crypto import encrypt_token, decrypt_token, get_cached_decrypted_token
from core.services.whatsapp_service import WhatsAppService
from core.services.whatsapp_embedded_signup_service import WhatsAppEmbeddedSignupService

User = get_user_model()


@pytest.mark.django_db
class TestWhatsAppPhase6TechProviderMatrix:
    """مصفوفة الاختبارات الصارمة لمرحلة مزود التكنولوجيا والتسجيل المضمن"""

    def setup_method(self):
        WhatsAppAccount.objects.all().delete()
        WhatsAppMessageLog.objects.all().delete()
        SystemSetting.objects.filter(key__startswith="WHATSAPP_").delete()
        WhatsAppService.reset_session()

        self.user = User.objects.create_superuser(
            username="whatsapp_cfo_admin",
            email="cfo@mwheba.co.uk",
            password="StrongPassword2026!"
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_crypto_roundtrip_and_transparent_property(self):
        """1. اختبار التشفير الدائري بـ AES-256 وخاصية التوكن الشفافة مع الكاش"""
        raw_token = "EAAG_TEST_PERMANENT_SYSTEM_USER_TOKEN_2026_VERY_SECURE"
        encrypted = encrypt_token(raw_token)
        assert encrypted != raw_token
        assert encrypted.startswith("gAAAAA")

        decrypted = decrypt_token(encrypted)
        assert decrypted == raw_token

        # إنشاء حساب وتجربة الـ Property Getter/Setter
        account = WhatsAppAccount.objects.create(
            name="فرع القاهرة الرئيسي",
            company_name="شركة موهبة للبرمجيات",
            phone_number_id="109876543210987",
            waba_id="209876543210987",
            is_coexistence=True,
            is_default=True
        )
        account.access_token = raw_token
        account.save()

        # قراءة الحساب من قاعدة البيانات والتأكد من التشفير والفك التلقائي
        account.refresh_from_db()
        assert account.encrypted_access_token.startswith("gAAAAA")
        assert account.access_token == raw_token

    def test_single_default_account_guard(self):
        """2. اختبار حارس الحساب الافتراضي الواحد (Single Default Integrity Guard)"""
        acc1 = WhatsAppAccount.objects.create(
            name="فرع القاهرة",
            phone_number_id="1111111111",
            is_default=True
        )
        assert acc1.is_default is True

        acc2 = WhatsAppAccount.objects.create(
            name="فرع الإسكندرية",
            phone_number_id="2222222222",
            is_default=True
        )
        acc1.refresh_from_db()
        acc2.refresh_from_db()
        assert acc2.is_default is True
        assert acc1.is_default is False

    def test_three_tier_config_resolution(self):
        """3. اختبار طبقة التوافق العكسي ثلاثية المستويات (3-Tier Fallback Layer)"""
        from django.test import override_settings

        # Tier 3: من django.conf.settings
        with override_settings(WHATSAPP_PHONE_NUMBER_ID='3333333333', WHATSAPP_ACCESS_TOKEN='TOKEN_TIER_3'):
            cfg3 = WhatsAppService.get_config()
            assert cfg3['phone_number_id'] == '3333333333'
            assert cfg3['access_token'] == 'TOKEN_TIER_3'

        # Tier 2: من SystemSetting في الداتابيز
        SystemSetting.set_setting('whatsapp_phone_number_id', '2222222222')
        SystemSetting.set_setting('whatsapp_access_token', 'TOKEN_TIER_2')
        cfg2 = WhatsAppService.get_config()
        assert cfg2['phone_number_id'] == '2222222222'
        assert cfg2['access_token'] == 'TOKEN_TIER_2'

        # Tier 1: من WhatsAppAccount الافتراضي
        acc = WhatsAppAccount.objects.create(
            name="الحساب الأساسي Tier 1",
            phone_number_id="1111111111",
            is_default=True
        )
        acc.access_token = "TOKEN_TIER_1"
        acc.save()

        cfg1 = WhatsAppService.get_config()
        assert cfg1['phone_number_id'] == '1111111111'
        assert cfg1['access_token'] == 'TOKEN_TIER_1'
        assert cfg1['account_id'] == acc.id

    def test_embedded_signup_coexistence_pin_skip_guard(self):
        """4. اختبار صمام أمان التعايش وتخطي تسجيل الـ PIN للحفاظ على جلسة الموبايل"""
        # في وضع التعايش (is_coexistence=True) يجب تخطي استدعاء endpoint الـ PIN
        res_coex = WhatsAppEmbeddedSignupService.register_phone_number_safely(
            phone_number_id="109876543210987",
            access_token="TEST_TOKEN",
            pin="123456",
            is_coexistence=True
        )
        assert res_coex["success"] is True
        assert res_coex["skipped"] is True
        assert "تخطي" in res_coex["message"]

    @patch('core.services.whatsapp_service.WhatsAppService.get_session')
    def test_embedded_signup_complete_onboarding_flow(self, mock_get_session):
        """5. اختبار دورة الربط الشاملة (Embedded Signup Complete Onboarding Flow)"""
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session

        # Mock GET phone details response
        mock_resp_phone = MagicMock()
        mock_resp_phone.status_code = 200
        mock_resp_phone.json.return_value = {
            "display_phone_number": "+20 101 234 5678",
            "verified_name": "موهبة للحلول التقنية المعتمدة",
            "quality_rating": "GREEN",
            "status": "CONNECTED"
        }

        # Mock POST subscribed_apps response
        mock_resp_subs = MagicMock()
        mock_resp_subs.status_code = 200
        mock_resp_subs.json.return_value = {"success": True}

        def session_router(*args, **kwargs):
            url = args[0] if args else kwargs.get('url', '')
            if 'subscribed_apps' in url:
                return mock_resp_subs
            return mock_resp_phone

        mock_session.get.side_effect = session_router
        mock_session.post.side_effect = session_router

        # تنفيذ دورة الربط
        res = WhatsAppEmbeddedSignupService.complete_onboarding(
            phone_number_id="109876543210987",
            access_token="EAAG_ONBOARDING_TOKEN_2026",
            waba_id="209876543210987",
            account_name="فرع القاهرة",
            is_coexistence=True,
            is_default=True
        )

        assert res["success"] is True
        account = WhatsAppAccount.objects.get(phone_number_id="109876543210987")
        assert account.is_default is True
        assert account.is_coexistence is True
        assert account.access_token == "EAAG_ONBOARDING_TOKEN_2026"
        assert account.verified_name == "موهبة للحلول التقنية المعتمدة"
        assert account.quality_rating == "GREEN"

    def test_bidi_unicode_parameter_sanitizer(self):
        """6. اختبار تطهير المتغيرات وعزل الاتجاه ثنائي اللغة (BiDi Isolation & Fallback)"""
        # فحص استبدال القيم الفارغة
        assert WhatsAppService.clean_template_variable(None) == "-"
        assert WhatsAppService.clean_template_variable("") == "-"
        assert WhatsAppService.clean_template_variable("   ") == "-"

        # فحص عزل الأرقام والعلامات
        clean_inv = WhatsAppService.clean_template_variable("INV-2026-001")
        assert clean_inv == "\u2066INV-2026-001\u2069"

        # فحص حساب البصمة التشفيرية للمستند
        sha = WhatsAppService.calculate_document_sha256(b"%PDF-1.4 Mock Invoice Content")
        assert len(sha) == 64

    def test_account_management_apis(self):
        """7. اختبار واجهات إدارة الحسابات (Account Save, Toggle Default, Delete APIs)"""
        # حفظ حساب جديد عبر API
        save_resp = self.client.post(reverse('core:whatsapp_account_save'), {
            'name': 'فرع الدقي',
            'phone_number_id': '9988776655',
            'access_token': 'EAAG_API_SAVED_TOKEN',
            'is_coexistence': 'on',
            'is_default': 'on'
        })
        assert save_resp.status_code == 200
        save_data = save_resp.json()
        assert save_data['success'] is True

        acc = WhatsAppAccount.objects.get(phone_number_id='9988776655')
        assert acc.is_default is True
        assert acc.access_token == 'EAAG_API_SAVED_TOKEN'

        # إضافة حساب ثانٍ
        acc2 = WhatsAppAccount.objects.create(
            name='فرع المعادي',
            phone_number_id='4455667788',
            is_default=False
        )
        acc2.access_token = 'TOKEN_MAADI'
        acc2.save()

        # تفعيل الحساب الثاني كافتراضي عبر API
        toggle_resp = self.client.post(reverse('core:whatsapp_account_toggle_default', args=[acc2.id]))
        assert toggle_resp.status_code == 200
        acc.refresh_from_db()
        acc2.refresh_from_db()
        assert acc2.is_default is True
        assert acc.is_default is False

        # حذف الحساب الثاني
        del_resp = self.client.post(reverse('core:whatsapp_account_delete', args=[acc2.id]))
        assert del_resp.status_code == 200
        assert not WhatsAppAccount.objects.filter(pk=acc2.id).exists()
        acc.refresh_from_db()
        assert acc.is_default is True
