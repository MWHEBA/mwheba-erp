# -*- coding: utf-8 -*-
"""
اختبارات شاملة للمرحلة الخامسة من منظومة WhatsApp Business Cloud API
MWHEBA ERP — Phase 5 Automated Campaigns, Quality Shield & Celery Throttling Pytest Suite
"""
import json
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.urls import reverse

from core.models import SystemSetting, WhatsAppAccount, WhatsAppCampaign, WhatsAppCampaignRecipient, WhatsAppMessageLog
from core.services.whatsapp_service import WhatsAppService
from core.services.whatsapp_campaign_service import WhatsAppCampaignService
from core.tasks.whatsapp_tasks import retry_pending_outbox_messages_task
from customer.models import Customer, CustomerTier
from supplier.models import Supplier

User = get_user_model()


@pytest.mark.django_db
class TestWhatsAppPhase5Campaigns:
    """مصفوفة اختبارات الحملات الإعلانية وخنق التدفق ودرع حماية الجودة وصندوق الصادر المؤجل"""

    def setup_method(self):
        cache.clear()
        WhatsAppService.reset_session()
        WhatsAppCampaignRecipient.objects.all().delete()
        WhatsAppCampaign.objects.all().delete()
        WhatsAppMessageLog.objects.all().delete()
        WhatsAppAccount.objects.all().delete()

        # إنشاء الحساب الافتراضي المشفر
        self.account = WhatsAppAccount.objects.create(
            name="الفرع الرئيسي - حملات",
            phone_number_id="1099887766554",
            waba_id="9988776655443",
            display_phone_number="+201011223344",
            access_token="EAATestCampaignToken2026",
            is_default=True,
            is_coexistence=True,
            account_status="CONNECTED",
            quality_rating="GREEN"
        )

        SystemSetting.objects.update_or_create(
            key="whatsapp_enabled",
            defaults={"value": "true", "data_type": "boolean", "group": "whatsapp", "is_active": True}
        )

        self.user = User.objects.create_user(
            username="campaign_manager_p5",
            email="campaign_p5@example.com",
            password="password123",
            is_staff=True
        )
        can_send_perm = Permission.objects.get(codename="can_send_whatsapp")
        can_broadcast_perm = Permission.objects.get(codename="can_broadcast_whatsapp_campaigns")
        self.user.user_permissions.add(can_send_perm, can_broadcast_perm)

        # إنشاء شرائح وعملاء وموردين للاختبار
        self.tier_vip = CustomerTier.objects.create(name="شريحة كبار العملاء VIP", code="TIER-VIP")
        
        self.cust1 = Customer.objects.create(
            name="شركة الفرسان للمقاولات",
            code="CUST-P5-01",
            phone="01011112222",
            phone_primary="01011112222",
            tier=self.tier_vip
        )
        if hasattr(self.cust1, 'balance'):
            self.cust1.balance = Decimal('5000.00')
            self.cust1.save()

        self.cust2_opt_out = Customer.objects.create(
            name="مكتب السلام الهندسي",
            code="CUST-P5-02",
            phone="01133334444",
            phone_primary="01133334444",
            whatsapp_opt_out=True
        )

        self.supp1 = Supplier.objects.create(
            name="شركة الحديد والصلب",
            code="SUPP-P5-01",
            phone="01244445555"
        )

    # 1. تعبئة مستلمي الحملة آلياً وتخطي الـ Opt-Out
    def test_populate_campaign_recipients(self):
        campaign = WhatsAppCampaign.objects.create(
            name="حملة كشوف الحسابات الشهرية",
            campaign_type='STATEMENT',
            audience_type='ALL_CUSTOMERS',
            account=self.account,
            created_by=self.user
        )

        total = WhatsAppCampaignService.populate_recipients(campaign)
        assert total >= 2
        assert campaign.total_recipients >= 2

        rec1 = campaign.recipients.filter(customer=self.cust1).first()
        assert rec1 is not None
        assert rec1.status == 'PENDING'

        rec2 = campaign.recipients.filter(customer=self.cust2_opt_out).first()
        assert rec2 is not None
        assert rec2.status == 'SKIPPED'
        assert "Opt-Out" in rec2.error_message

    # 2. إطلاق وتنفيذ الحملة بنجاح وتحديث العدادات
    @patch("requests.Session.post")
    def test_launch_and_execute_campaign_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "messaging_product": "whatsapp",
            "messages": [{"id": "wamid.CAMP_MSG_001"}]
        }
        mock_post.return_value = mock_resp

        campaign = WhatsAppCampaign.objects.create(
            name="حملة إشعار الجاهزية",
            campaign_type='STATEMENT',
            audience_type='ALL_CUSTOMERS',
            account=self.account,
            created_by=self.user
        )

        res = WhatsAppCampaignService.launch_campaign(campaign.id)
        assert res["success"] is True

        campaign.refresh_from_db()
        assert campaign.status in ('RUNNING', 'COMPLETED')
        assert campaign.sent_count >= 1

    # 3. درع حماية الجودة (Quality Score Shield) وتجميد الحملات الترويجية عند RED / FLAGGED
    def test_quality_score_shield_freezes_promotional_campaign(self):
        self.account.quality_rating = "RED"
        self.account.account_status = "FLAGGED"
        self.account.save()

        campaign = WhatsAppCampaign.objects.create(
            name="عروض وتخفيضات نهاية العام",
            campaign_type='PROMOTIONAL',
            audience_type='ALL_CUSTOMERS',
            account=self.account,
            created_by=self.user
        )

        res = WhatsAppCampaignService.launch_campaign(campaign.id)
        assert res["success"] is False
        assert res.get("frozen") is True
        assert "تم تجميد الحملة الترويجية تلقائياً لحماية تقييم جودة الرقم" in res["error"]

        campaign.refresh_from_db()
        assert campaign.status == 'FROZEN_QUALITY'

    # 4. إعادة محاولة إرسال رسائل صندوق الصادر المؤجل (Offline Outbox Recovery)
    @patch("requests.Session.post")
    def test_offline_outbox_retry_task(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "messaging_product": "whatsapp",
            "messages": [{"id": "wamid.OUTBOX_RECOVERED_01"}]
        }
        mock_post.return_value = mock_resp

        # إنشاء رسالة فشلت بسبب انقطاع اتصال مؤقت
        failed_log = WhatsAppMessageLog.objects.create(
            account=self.account,
            recipient_phone="201011112222",
            recipient_name=self.cust1.name,
            customer=self.cust1,
            template_name="document_send_ar",
            status='FAILED',
            error_code='TIMEOUT',
            error_message='انتهت مهلة الاتصال بسيرفرات Meta',
            retry_count=0
        )

        task_res = retry_pending_outbox_messages_task()
        assert task_res["success"] is True
        assert task_res["recovered_count"] >= 1

        failed_log.refresh_from_db()
        assert failed_log.retry_count == 1

    # 5. اختبار واجهات الـ Web والـ REST APIs للحملات
    def test_campaign_views_and_apis(self, client):
        client.force_login(self.user)

        # 1. شاشة عرض قائمة الحملات
        list_url = reverse('core:whatsapp_campaigns')
        resp_list = client.get(list_url)
        assert resp_list.status_code == 200
        assert "إدارة الحملات والإشعارات الجماعية" in resp_list.content.decode('utf-8')
        assert "newCampaignModal" in resp_list.content.decode('utf-8')

        # 2. إنشاء حملة عبر الـ API
        create_url = reverse('core:whatsapp_campaign_create')
        create_payload = {
            "name": "حملة تجريبية عبر الـ API",
            "campaign_type": "STATEMENT",
            "audience_type": "ALL_CUSTOMERS",
            "account_id": self.account.id,
            "template_name": "order_status_ar",
            "throttle_rate": 20
        }
        resp_create = client.post(create_url, data=json.dumps(create_payload), content_type="application/json")
        assert resp_create.status_code == 200
        create_data = resp_create.json()
        assert create_data["success"] is True
        camp_id = create_data["campaign_id"]

        # 3. فحص حالة الحملة
        status_url = reverse('core:whatsapp_campaign_status', kwargs={'campaign_id': camp_id})
        resp_status = client.get(status_url)
        assert resp_status.status_code == 200
        status_data = resp_status.json()
        assert status_data["success"] is True
        assert status_data["name"] == "حملة تجريبية عبر الـ API"

        # 4. حذف الحملة
        delete_url = reverse('core:whatsapp_campaign_delete', kwargs={'campaign_id': camp_id})
        resp_delete = client.post(delete_url)
        assert resp_delete.status_code == 200
        assert resp_delete.json()["success"] is True
        assert not WhatsAppCampaign.objects.filter(id=camp_id).exists()
