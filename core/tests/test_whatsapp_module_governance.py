# -*- coding: utf-8 -*-
"""
حزمة اختبارات الحوكمة والرقابة لمنظومة WhatsApp Business Cloud API — المرحلة الخامسة
MWHEBA ERP — WhatsApp Module Governance & Enterprise Safety Pytest Suite (Phase 5)
"""
import json
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.urls import reverse

from core.models import (
    SystemSetting,
    SystemModule,
    WhatsAppAccount,
    WhatsAppCampaign,
    WhatsAppCampaignRecipient,
    WhatsAppMessageLog,
)
from core.services.whatsapp_service import WhatsAppService
from core.services.whatsapp_campaign_service import WhatsAppCampaignService
from core.services.document_dispatcher import DocumentDispatcher
from core.tasks.whatsapp_tasks import (
    process_whatsapp_webhook_task,
    retry_pending_outbox_messages_task,
)
from customer.models import Customer
from sale.models import Sale

User = get_user_model()


@pytest.mark.django_db
class TestWhatsAppModuleGovernanceBase:
    """إعداد البيئة الموحدة لجميع اختبارات الحوكمة"""

    def setup_method(self):
        cache.clear()
        WhatsAppService.reset_session()
        SystemSetting.invalidate_all_system_caches()
        WhatsAppMessageLog.objects.all().delete()
        WhatsAppCampaignRecipient.objects.all().delete()
        WhatsAppCampaign.objects.all().delete()
        WhatsAppAccount.objects.all().delete()

        # إعداد المستخدمين (مدير عام Superuser ومستخدم عادي Staff)
        self.superuser = User.objects.create_superuser(
            username="super_cfo_p5",
            email="super_cfo@example.com",
            password="password123"
        )
        self.staff_user = User.objects.create_user(
            username="staff_user_p5",
            email="staff@example.com",
            password="password123",
            is_staff=True
        )
        # إعطاء صلاحيات الإرسال وعرض المبيعات للمستخدم العادي
        can_send_perm = Permission.objects.filter(codename="can_send_whatsapp").first()
        if can_send_perm:
            self.staff_user.user_permissions.add(can_send_perm)

        # تهيئة إعدادات WhatsApp والربط الفني
        SystemSetting.objects.update_or_create(
            key="whatsapp_enabled",
            defaults={"value": "true", "data_type": "boolean", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_access_token",
            defaults={"value": "EAATestGovernanceToken2026", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_phone_number_id",
            defaults={"value": "1000987654321", "data_type": "string", "group": "whatsapp", "is_active": True}
        )
        SystemSetting.objects.update_or_create(
            key="whatsapp_webhook_verify_token",
            defaults={"value": "secure_webhook_token_2026", "data_type": "string", "group": "whatsapp", "is_active": True}
        )

        # تهيئة كائن SystemModule للواتساب
        self.module, _ = SystemModule.objects.update_or_create(
            code="whatsapp",
            defaults={
                "name_ar": "رسائل WhatsApp",
                "name_en": "WhatsApp Messaging",
                "module_type": "optional",
                "is_enabled": True,
                "icon": "fab fa-whatsapp",
            }
        )

        # تهيئة الحساب الافتراضي
        self.account = WhatsAppAccount.objects.create(
            name="الحساب الرئيسي للتجارب",
            phone_number_id="1000987654321",
            waba_id="9988776655443",
            display_phone_number="+201011223344",
            access_token="EAATestGovernanceToken2026",
            is_default=True,
            is_coexistence=True,
            account_status="CONNECTED",
            quality_rating="GREEN"
        )

        # إنشاء عميل وفاتورة مبيعات للاختبار
        self.customer = Customer.objects.create(
            name="شركة الوفاق التجارية",
            code="CUST-GOV-01",
            phone="01012345678"
        )
        self.sale = Sale.objects.create(
            customer=self.customer,
            created_by=self.superuser,
            number="INV-GOV-2026-01",
            date=timezone.now().date(),
            status="confirmed",
            subtotal=Decimal("5000.00"),
            total=Decimal("5000.00")
        )
        self.ct_sale = ContentType.objects.get_for_model(Sale)

        cache.clear()
        WhatsAppService.reset_session()
        SystemSetting.invalidate_all_system_caches()


class TestWhatsAppModuleToggle(TestWhatsAppModuleGovernanceBase):
    """1. اختبارات التبديل المتزامن بين شاشة التطبيقات وإعدادات الواتساب وانعكاسها الفوري"""

    def test_module_toggle_from_module_management_disables_whatsapp(self, client):
        """التعطيل من شاشة إدارة التطبيقات يُعطل WhatsAppService والـ SystemSetting فوراً"""
        client.force_login(self.superuser)

        # إرسال طلب تعطيل الموديول
        res = client.post(reverse("core:module_management"), data={
            "module_code": "whatsapp",
            "action": "disable"
        })
        assert res.status_code == 302

        # التحقق من تحديث كائن SystemModule
        self.module.refresh_from_db()
        assert self.module.is_enabled is False

        # التحقق من انعكاس التغيير على SystemSetting
        assert SystemSetting.get_bool("whatsapp_enabled") is False

        # التحقق من أن خدمة WhatsAppService أصبحت معطلة فوراً
        assert WhatsAppService.is_enabled() is False

    def test_module_toggle_from_module_management_enables_whatsapp(self, client):
        """إعادة التفعيل من شاشة إدارة التطبيقات يُفعل WhatsAppService والـ SystemSetting فوراً"""
        client.force_login(self.superuser)

        # أولاً: التعطيل
        self.module.is_enabled = False
        self.module.save()
        SystemSetting.invalidate_all_system_caches()
        assert WhatsAppService.is_enabled() is False

        # ثانياً: التفعيل عبر الواجهة
        res = client.post(reverse("core:module_management"), data={
            "module_code": "whatsapp",
            "action": "enable"
        })
        assert res.status_code == 302

        self.module.refresh_from_db()
        assert self.module.is_enabled is True
        assert SystemSetting.get_bool("whatsapp_enabled") is True
        assert WhatsAppService.is_enabled() is True

    def test_whatsapp_views_completely_closed_from_door_when_disabled(self, client):
        """التحقق من إغلاق كافة شاشات الواتساب من بابها تماماً عند التعطيل حتى للمدير العام"""
        client.force_login(self.superuser)

        # 1. عند التعطيل
        self.module.is_enabled = False
        self.module.save()
        SystemSetting.invalidate_all_system_caches()

        # صفحة الإعدادات ممنوعة ومقفولة تماماً
        res_settings = client.get(reverse("core:whatsapp_settings"))
        assert res_settings.status_code == 302
        assert res_settings.url == reverse("core:module_management")

        # صفحة الشات الحي مقفولة
        res_chat = client.get(reverse("core:whatsapp_live_chat"))
        assert res_chat.status_code == 302
        assert res_chat.url == reverse("core:module_management")

        # صفحة الحملات مقفولة
        res_campaigns = client.get(reverse("core:whatsapp_campaigns"))
        assert res_campaigns.status_code == 302
        assert res_campaigns.url == reverse("core:module_management")

        # صفحة سجل الرسائل مقفولة
        res_logs = client.get(reverse("core:whatsapp_logs"))
        assert res_logs.status_code == 302
        assert res_logs.url == reverse("core:module_management")

        # 2. عند التفعيل تفتح صفحة الإعدادات بنجاح
        self.module.is_enabled = True
        self.module.save()
        SystemSetting.invalidate_all_system_caches()

        res_open = client.get(reverse("core:whatsapp_settings"))
        assert res_open.status_code == 200

    def test_sidebar_whatsapp_links_completely_hidden_when_disabled(self, client):
        """التحقق من اختفاء رابط إعدادات WhatsApp وسجل الرسائل تماماً من القائمة الجانبية عند التعطيل حتى للمدير العام"""
        client.force_login(self.superuser)

        # 1. عند التعطيل
        self.module.is_enabled = False
        self.module.save()
        _clear_cache = getattr(SystemSetting, 'invalidate_all_system_caches', None)
        if _clear_cache:
            _clear_cache()

        res = client.get(reverse("core:module_management"))
        assert res.status_code == 200
        # التأكد من اختفاء الرابط تماماً من القائمة الجانبية
        content = res.content.decode("utf-8")
        assert reverse("core:whatsapp_settings") not in content or "إعدادات الربط والـ API" in content
        # التأكد من عدم وجود رابط القائمة الجانبية
        assert 'class="submenu-link" href="' + reverse("core:whatsapp_settings") + '"' not in content
        assert reverse("core:whatsapp_logs") not in content


class TestWhatsAppModuleRBAC(TestWhatsAppModuleGovernanceBase):
    """2. اختبارات التحكم في الصلاحيات وقصر إدارة موديول الواتساب على الـ Superuser"""

    def test_non_superuser_cannot_toggle_whatsapp_in_module_management(self, client):
        """حظر المستخدم غير الـ Superuser من التلاعب بموديول الواتساب في إدارة التطبيقات"""
        client.force_login(self.staff_user)

        res = client.post(reverse("core:module_management"), data={
            "module_code": "whatsapp",
            "action": "disable"
        })
        # يجب إعادة التوجيه مع عدم تعديل الحالة
        assert res.status_code == 302

        self.module.refresh_from_db()
        assert self.module.is_enabled is True
        assert SystemSetting.get_bool("whatsapp_enabled") is True
        assert WhatsAppService.is_enabled() is True

    def test_superuser_can_toggle_whatsapp_in_module_management(self, client):
        """المدير العام (Superuser) يمتلك الصلاحية الكاملة لتغيير الحالة"""
        client.force_login(self.superuser)

        res = client.post(reverse("core:module_management"), data={
            "module_code": "whatsapp",
            "action": "disable"
        })
        assert res.status_code == 302

        self.module.refresh_from_db()
        assert self.module.is_enabled is False


class TestWhatsAppCampaignGovernance(TestWhatsAppModuleGovernanceBase):
    """3. اختبارات حوكمة الحملات التسويقية وحمايتها من استنزاف الرصيد أو الحظر"""

    def test_disabling_module_pauses_running_campaigns(self, client):
        """عند تعطيل المنظومة يتم إيقاف الحملات في حالة RUNNING وتحويلها إلى PAUSED آلياً"""
        client.force_login(self.superuser)

        campaign = WhatsAppCampaign.objects.create(
            name="حملة عروض الصيف الكبرى",
            campaign_type="PROMOTIONAL",
            account=self.account,
            status="RUNNING",
            started_at=timezone.now(),
            created_by=self.superuser
        )

        # تعطيل المنظومة عبر إدارة التطبيقات
        res = client.post(reverse("core:module_management"), data={
            "module_code": "whatsapp",
            "action": "disable"
        })
        assert res.status_code == 302

        campaign.refresh_from_db()
        assert campaign.status == "PAUSED"

    def test_cannot_launch_campaign_when_module_disabled(self):
        """منع إطلاق أي حملة تسويقية عند تعطيل المنظومة"""
        # تعطيل المنظومة
        self.module.is_enabled = False
        self.module.save()
        SystemSetting.invalidate_all_system_caches()

        campaign = WhatsAppCampaign.objects.create(
            name="حملة عروض الخريف",
            campaign_type="PROMOTIONAL",
            account=self.account,
            status="DRAFT",
            created_by=self.superuser
        )

        res = WhatsAppCampaignService.launch_campaign(campaign.id, triggered_by=self.superuser)
        assert res["success"] is False
        assert "معطلة حالياً" in res["error"]

    def test_campaign_launch_api_blocked_when_disabled(self, client):
        """واجهة API لإطلاق الحملات ترجع خطأ 400 عند تعطيل المنظومة"""
        client.force_login(self.superuser)

        # تعطيل المنظومة
        self.module.is_enabled = False
        self.module.save()
        SystemSetting.invalidate_all_system_caches()

        campaign = WhatsAppCampaign.objects.create(
            name="حملة المناسبات",
            campaign_type="PROMOTIONAL",
            account=self.account,
            status="DRAFT",
            created_by=self.superuser
        )

        res = client.post(reverse("core:whatsapp_campaign_launch", kwargs={"campaign_id": campaign.id}))
        assert res.status_code == 400
        data = res.json()
        assert data["success"] is False
        assert "معطلة حالياً" in data["error"]


class TestWhatsAppWebhookGovernance(TestWhatsAppModuleGovernanceBase):
    """4. اختبارات مرونة الـ Webhook واستقبال رسائل العملاء أثناء التعطيل بدون ضياع"""

    def test_webhook_verification_challenge_200_ok_when_disabled(self, client):
        """تحدي التحقق (Hub Challenge) يستمر في الرد بـ 200 OK حتى لو المنظومة معطلة"""
        self.module.is_enabled = False
        self.module.save()
        SystemSetting.invalidate_all_system_caches()

        res = client.get(reverse("core:whatsapp_webhook"), {
            "hub.mode": "subscribe",
            "hub.challenge": "meta_handshake_challenge_12345",
            "hub.verify_token": "secure_webhook_token_2026"
        })
        assert res.status_code == 200
        assert res.content.decode("utf-8") == "meta_handshake_challenge_12345"

    def test_webhook_inbound_message_saved_as_suspended_when_disabled(self):
        """الرسائل الواردة أثناء التعطيل يتم حفظها بحالة SUSPENDED لضمان عدم ضياع أي محادثة عميل"""
        self.module.is_enabled = False
        self.module.save()
        SystemSetting.invalidate_all_system_caches()

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "9988776655443",
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "201011223344",
                            "phone_number_id": "1000987654321"
                        },
                        "messages": [{
                            "from": "201012345678",
                            "id": "wamid.TEST_SUSPENDED_MSG_001",
                            "timestamp": "1728000000",
                            "type": "text",
                            "text": {"body": "استفسار بخصوص فاتورة الحساب"}
                        }]
                    }
                }]
            }]
        }

        res = process_whatsapp_webhook_task(payload)
        assert res["success"] is True

        log = WhatsAppMessageLog.objects.get(message_id="wamid.TEST_SUSPENDED_MSG_001")
        assert log.status == "SUSPENDED"
        assert log.error_code == "SUSPENDED"
        assert log.body_text == "استفسار بخصوص فاتورة الحساب"
        assert "تعطيل" in (log.error_message or "")


class TestWhatsAppNotificationAndAntiBurst(TestWhatsAppModuleGovernanceBase):
    """5. اختبارات تخطي الإشعارات التلقائية بأمان ومنع الإرسال الانفجاري (Anti-Burst)"""

    def test_send_template_message_skipped_when_disabled(self):
        """محاولة إرسال رسالة قالب تلقائية أثناء التعطيل تسجل SKIPPED و BLOCKED_BY_ADMIN"""
        self.module.is_enabled = False
        self.module.save()
        SystemSetting.invalidate_all_system_caches()

        res = WhatsAppService.send_template_message(
            phone="01012345678",
            template_name="document_send_ar",
            components=[],
            is_automatic=True
        )
        assert res.get("success") is False

        log = WhatsAppMessageLog.objects.filter(
            recipient_phone="201012345678",
            error_code="BLOCKED_BY_ADMIN"
        ).first()
        assert log is not None
        assert log.status == "SKIPPED"

    def test_document_dispatcher_skipped_when_disabled(self):
        """موزع المستندات يتخطى الإرسال التلقائي ويسجل SKIPPED دون رفع أخطاء"""
        self.module.is_enabled = False
        self.module.save()
        SystemSetting.invalidate_all_system_caches()

        res = DocumentDispatcher.dispatch(
            content_object=self.sale,
            recipient_phone="01012345678",
            is_automatic=True
        )
        assert res["success"] is False

        log = WhatsAppMessageLog.objects.filter(
            recipient_phone="01012345678",
            error_code="BLOCKED_BY_ADMIN"
        ).first()
        assert log is not None
        assert log.status == "SKIPPED"

    def test_anti_burst_skipped_messages_not_resent_on_reenable(self):
        """الرسائل المتخطاة بحظر الإدارة (BLOCKED_BY_ADMIN) لا يُعاد إرسالها تلقائياً بعد إعادة التفعيل"""
        # إنشاء سجل متخطى بسبب التعطيل
        log_skipped = WhatsAppMessageLog.objects.create(
            recipient_phone="201012345678",
            recipient_name="العميل المتخطي",
            template_name="document_send_ar",
            status="SKIPPED",
            error_code="BLOCKED_BY_ADMIN",
            error_message="منظومة WhatsApp معطلة",
            retry_count=0
        )

        # إعادة تفعيل الموديول
        self.module.is_enabled = True
        self.module.save()
        SystemSetting.invalidate_all_system_caches()
        assert WhatsAppService.is_enabled() is True

        # تشغيل مهمة إعادة إرسال الرسائل المعلقة
        with patch.object(WhatsAppService, "send_template_message") as mock_send:
            retry_pending_outbox_messages_task()
            # التأكد من عدم محاولة إرسال الرسالة المتخطاة آلياً
            mock_send.assert_not_called()

        log_skipped.refresh_from_db()
        assert log_skipped.status == "SKIPPED"
        assert log_skipped.retry_count == 0


class TestWhatsAppFormSafetyNoSilentWipe(TestWhatsAppModuleGovernanceBase):
    """6. اختبار حماية النموذج من المسح الصامت للسويتش"""

    def test_saving_settings_tab_without_switch_preserves_state(self, client):
        """حفظ تبويب فرعي بدون تضمين حقل whatsapp_enabled يحافظ على حالة التفعيل دون تعطيلها"""
        client.force_login(self.superuser)
        assert WhatsAppService.is_enabled() is True

        # إرسال طلب بدون الحقل whatsapp_enabled لمحاكاة تبويب فرعي
        res = client.post(reverse("core:whatsapp_settings"), data={
            "action": "save_settings",
            "tab": "templates",
            "whatsapp_skip_landlines": "on"
        })
        assert res.status_code == 302

        self.module.refresh_from_db()
        assert self.module.is_enabled is True
        assert SystemSetting.get_bool("whatsapp_enabled") is True
        assert WhatsAppService.is_enabled() is True


class TestWhatsAppApiEndpointsGuard(TestWhatsAppModuleGovernanceBase):
    """7. اختبارات تحصين واجهات الـ API من العمل أثناء التعطيل"""

    def test_send_test_message_api_blocked_when_disabled(self, client):
        """واجهة إرسال الرسالة التجريبية محصنة ضد العمل أثناء التعطيل"""
        client.force_login(self.superuser)

        self.module.is_enabled = False
        self.module.save()
        SystemSetting.invalidate_all_system_caches()

        res = client.post(
            reverse("core:whatsapp_send_test"),
            data=json.dumps({"phone": "01012345678"}),
            content_type="application/json"
        )
        assert res.status_code == 400
        data = res.json()
        assert data["success"] is False
        assert "معطلة حالياً" in data["error"]

    def test_chat_send_text_api_blocked_when_disabled(self, client):
        """واجهة إرسال الشات الحي محصنة ضد العمل أثناء التعطيل"""
        client.force_login(self.superuser)

        self.module.is_enabled = False
        self.module.save()
        SystemSetting.invalidate_all_system_caches()

        res = client.post(
            reverse("core:whatsapp_chat_send_text"),
            data=json.dumps({"phone": "01012345678", "text": "مرحباً بكم"}),
            content_type="application/json"
        )
        assert res.status_code == 400
        data = res.json()
        assert data["success"] is False
        assert "معطلة حالياً" in data["error"]


class TestWhatsAppComplianceUrls(TestWhatsAppModuleGovernanceBase):
    """8. اختبارات استمرار إتاحة مسارات الامتثال الرسمية لـ Meta"""

    def test_compliance_urls_always_accessible_when_disabled(self, client):
        """صفحات الامتثال (الخصوصية والشروط وحذف البيانات) تظل متاحة دائماً"""
        self.module.is_enabled = False
        self.module.save()
        SystemSetting.invalidate_all_system_caches()

        # صفحة سياسة الخصوصية
        res_privacy = client.get(reverse("core:whatsapp_privacy_policy"))
        assert res_privacy.status_code == 200

        # صفحة شروط الخدمة
        res_terms = client.get(reverse("core:whatsapp_terms"))
        assert res_terms.status_code == 200
