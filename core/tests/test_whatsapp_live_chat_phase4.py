# -*- coding: utf-8 -*-
"""
اختبارات شاملة للمرحلة الرابعة من منظومة WhatsApp Business Cloud API
MWHEBA ERP — Phase 4 Live Chat, Differential Polling & Inbound Lead Conversion Pytest Suite
"""
import json
import pytest
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.urls import reverse

from core.models import SystemSetting, WhatsAppAccount, WhatsAppMessageLog
from core.services.whatsapp_service import WhatsAppService
from customer.models import Customer
from supplier.models import Supplier

User = get_user_model()


@pytest.mark.django_db
class TestWhatsAppPhase4LiveChat:
    """مصفوفة اختبارات الشات الحي والاستعلام التفاضلي وتحويل الشركاء"""

    def setup_method(self):
        cache.clear()
        WhatsAppService.reset_session()
        WhatsAppMessageLog.objects.all().delete()
        WhatsAppAccount.objects.all().delete()

        # إنشاء الحساب الافتراضي المشفر
        self.account = WhatsAppAccount.objects.create(
            name="الفرع الرئيسي - شات",
            phone_number_id="1011122334455",
            waba_id="9988776655443",
            display_phone_number="+201000000000",
            access_token="EAATestLiveChatToken2026",
            is_default=True,
            is_coexistence=True,
            account_status="CONNECTED"
        )

        SystemSetting.objects.update_or_create(
            key="whatsapp_enabled",
            defaults={"value": "true", "data_type": "boolean", "group": "whatsapp", "is_active": True}
        )

        self.user = User.objects.create_user(
            username="chat_agent_p4",
            email="agent_p4@example.com",
            password="password123",
            is_staff=True
        )
        can_send_perm = Permission.objects.get(codename="can_send_whatsapp")
        self.user.user_permissions.add(can_send_perm)

        self.customer = Customer.objects.create(
            name="شركة الأمل للتوزيع",
            code="CUST-CHAT-01",
            phone="01055554444"
        )

        self.supplier = Supplier.objects.create(
            name="مؤسسة الهدى للتوريدات",
            code="SUPP-CHAT-01",
            phone="01122223333"
        )

    # 1. فحص حساب حالة وصلاحية نافذة الـ 24 ساعة (24-Hour Window Status)
    def test_24h_window_status_calculation(self):
        norm_phone = "201055554444"
        now = timezone.now()

        # حالة 1: لا توجد رسائل واردة -> النافذة مغلقة
        status_none = WhatsAppService.get_conversation_window_status(norm_phone)
        assert status_none["is_open"] is False
        assert status_none["seconds_remaining"] == 0

        # حالة 2: رسالة واردة قبل ساعتين -> النافذة نشطة (~ 22 ساعة متبقية)
        log_active = WhatsAppMessageLog.objects.create(
            account=self.account,
            recipient_phone=norm_phone,
            recipient_name=self.customer.name,
            customer=self.customer,
            direction='INBOUND',
            message_type='text',
            body_text='استفسار بخصوص الأسعار',
            status='DELIVERED',
            created_at=now - timedelta(hours=2)
        )
        WhatsAppMessageLog.objects.filter(id=log_active.id).update(created_at=now - timedelta(hours=2))

        status_active = WhatsAppService.get_conversation_window_status(norm_phone)
        assert status_active["is_open"] is True
        assert status_active["seconds_remaining"] > 70000  # أكثر من 20 ساعة
        assert ":" in status_active["formatted_remaining"]

        # حالة 3: رسالة واردة قبل 26 ساعة -> النافذة منتهية
        WhatsAppMessageLog.objects.filter(id=log_active.id).update(created_at=now - timedelta(hours=26))
        status_expired = WhatsAppService.get_conversation_window_status(norm_phone)
        assert status_expired["is_open"] is False
        assert status_expired["seconds_remaining"] == 0

    # 2. إرسال رسالة نصية حرة داخل نافذة الـ 24 ساعة بنجاح
    @patch("requests.Session.post")
    def test_send_freeform_text_within_24h_window(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "messaging_product": "whatsapp",
            "messages": [{"id": "wamid.TEXT_SUCCESS_001"}]
        }
        mock_post.return_value = mock_resp

        norm_phone = "201055554444"
        # إنشاء رسالة واردة حديثة لفتح النافذة
        WhatsAppMessageLog.objects.create(
            account=self.account,
            recipient_phone=norm_phone,
            direction='INBOUND',
            message_type='text',
            body_text='أهلاً بك',
            status='DELIVERED'
        )

        res = WhatsAppService.send_text_message(
            phone=norm_phone,
            text="أهلاً بك، تفضل كيف يمكنني مساعدتك؟",
            account=self.account,
            created_by=self.user
        )

        assert res["success"] is True
        assert res["message_id"] == "wamid.TEXT_SUCCESS_001"

        log = WhatsAppMessageLog.objects.get(id=res["log_id"])
        assert log.direction == 'OUTBOUND_ERP'
        assert log.message_type == 'text'
        assert log.body_text == "أهلاً بك، تفضل كيف يمكنني مساعدتك؟"
        assert log.status == 'SENT'
        assert log.customer == self.customer
        assert log.created_by == self.user

    # 3. حظر إرسال الرسائل الحرة خارج نافذة الـ 24 ساعة
    def test_block_freeform_text_outside_24h_window(self):
        norm_phone = "201055554444"
        # لا توجد رسائل واردة نهائياً

        res = WhatsAppService.send_text_message(
            phone=norm_phone,
            text="رسالة حرة بدون فتح النافذة",
            account=self.account
        )

        assert res["success"] is False
        assert res.get("window_expired") is True
        assert "انتهت صلاحية نافذة خدمة العملاء" in res["error"]

    # 4. استرجاع وعرض شاشة الشات المباشر (whatsapp_live_chat_view)
    def test_whatsapp_live_chat_view_render(self, client):
        client.force_login(self.user)
        url = reverse('core:whatsapp_live_chat')
        response = client.get(url)

        assert response.status_code == 200
        assert "المحادثات المباشرة" in response.content.decode('utf-8')
        assert "chatAccountSelect" in response.content.decode('utf-8')
        assert "convertLeadModal" in response.content.decode('utf-8')

    # 5. واجهة API قائمة المحادثات (whatsapp_chat_conversations_api)
    def test_whatsapp_chat_conversations_api(self, client):
        client.force_login(self.user)

        # إنشاء محادثات للشريك ولجهة اتصال مجهولة
        WhatsAppMessageLog.objects.create(
            account=self.account,
            recipient_phone="201055554444",
            recipient_name=self.customer.name,
            customer=self.customer,
            direction='INBOUND',
            message_type='text',
            body_text='طلب عرض سعر جديد',
            status='DELIVERED'
        )
        WhatsAppMessageLog.objects.create(
            account=self.account,
            recipient_phone="201299998888",
            recipient_name="رقم مجهول",
            direction='INBOUND',
            message_type='text',
            body_text='مرحبا بكم',
            status='SENT'
        )

        url = reverse('core:whatsapp_chat_conversations')
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert len(data["conversations"]) >= 2

        cust_conv = next((c for c in data["conversations"] if c["phone"] == "201055554444"), None)
        assert cust_conv is not None
        assert cust_conv["partner_type"] == "customer"
        assert cust_conv["display_name"] == self.customer.name
        assert cust_conv["unread_count"] == 1

        lead_conv = next((c for c in data["conversations"] if c["phone"] == "201299998888"), None)
        assert lead_conv is not None
        assert lead_conv["partner_type"] == "lead"

    # 6. الاستعلام التفاضلي الفائق للرسائل (Differential Polling <1ms)
    def test_whatsapp_chat_messages_differential_polling(self, client):
        client.force_login(self.user)
        norm_phone = "201055554444"

        # إنشاء 3 رسائل سابقة
        m1 = WhatsAppMessageLog.objects.create(
            account=self.account,
            recipient_phone=norm_phone,
            direction='INBOUND',
            message_type='text',
            body_text='الرسالة الأولى',
            status='DELIVERED'
        )
        m2 = WhatsAppMessageLog.objects.create(
            account=self.account,
            recipient_phone=norm_phone,
            direction='OUTBOUND_ERP',
            message_type='text',
            body_text='الرسالة الثانية',
            status='SENT'
        )

        # استعلام مبدئي (last_id=0)
        url = reverse('core:whatsapp_chat_messages')
        resp1 = client.get(f"{url}?phone={norm_phone}&last_id=0")
        assert resp1.status_code == 200
        data1 = resp1.json()

        assert data1["success"] is True
        assert len(data1["messages"]) == 2
        last_id = data1["max_id"]
        assert last_id == m2.id

        # إضافة رسالة جديدة واستعلام تفاضلي (last_id=m2.id)
        m3 = WhatsAppMessageLog.objects.create(
            account=self.account,
            recipient_phone=norm_phone,
            direction='INBOUND',
            message_type='text',
            body_text='الرسالة الثالثة الجديدة',
            status='DELIVERED'
        )

        resp2 = client.get(f"{url}?phone={norm_phone}&last_id={last_id}")
        data2 = resp2.json()

        assert data2["success"] is True
        assert len(data2["messages"]) == 1
        assert data2["messages"][0]["id"] == m3.id
        assert data2["messages"][0]["body_text"] == 'الرسالة الثالثة الجديدة'
        assert data2["max_id"] == m3.id

        # التحقق من أن الرسالة الواردة تم تحديث حالتها تلقائياً إلى READ
        m3.refresh_from_db()
        assert m3.status == 'READ'

    # 7. إسناد المحادثة للموظف وقفل التصادم (Agent Assignment & Collision Lock)
    def test_whatsapp_chat_assign_agent_api(self, client):
        client.force_login(self.user)
        norm_phone = "201055554444"

        WhatsAppMessageLog.objects.create(
            account=self.account,
            recipient_phone=norm_phone,
            direction='INBOUND',
            body_text='طلب محادثة',
            status='DELIVERED'
        )

        url = reverse('core:whatsapp_chat_assign_agent')
        response = client.post(
            url,
            data=json.dumps({"phone": norm_phone, "user_id": self.user.id}),
            content_type="application/json"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # التحقق من قفل الكاش
        lock = cache.get(f"wa_chat_agent_lock_{norm_phone}")
        assert lock is not None
        assert lock["user_id"] == self.user.id

    # 8. التحويل السريع للرقم المجهول إلى عميل أو مورد (1-Click Lead Conversion)
    def test_whatsapp_chat_convert_lead_api(self, client):
        client.force_login(self.user)
        lead_phone = "01099881122"
        norm_lead_phone = "201099881122"

        # إنشاء سجلات مسبقة للرقم المجهول
        log1 = WhatsAppMessageLog.objects.create(
            account=self.account,
            recipient_phone=norm_lead_phone,
            recipient_name="جهة اتصال جديدة",
            direction='INBOUND',
            body_text='نريد التعاقد معكم',
            status='DELIVERED'
        )

        # 1. تحويل إلى عميل جديد
        url = reverse('core:whatsapp_chat_convert_lead')
        payload = {
            "phone": lead_phone,
            "name": "مؤسسة الرواد الدولية",
            "target_type": "customer",
            "email": "alrowad@example.com",
            "notes": "فرع مدينة نصر"
        }
        resp = client.post(url, data=json.dumps(payload), content_type="application/json")
        assert resp.status_code == 200
        data = resp.json()

        assert data["success"] is True
        assert data["partner_type"] == "customer"
        assert data["partner_name"] == "مؤسسة الرواد الدولية"

        # التحقق من إنشاء العميل وربطه بالسجلات السابقة
        created_cust = Customer.objects.get(id=data["partner_id"])
        assert created_cust.name == "مؤسسة الرواد الدولية"
        assert created_cust.phone == norm_lead_phone

        log1.refresh_from_db()
        assert log1.customer == created_cust
        assert log1.recipient_name == "مؤسسة الرواد الدولية"
