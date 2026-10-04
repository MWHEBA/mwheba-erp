# -*- coding: utf-8 -*-
"""
اختبارات الوحدة والتكامل لمنظومة WhatsApp Coexistence & Inbound Webhook (Phase 5)
MWHEBA ERP — Coexistence & Multi-Directional Webhook Tests
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.core.cache import cache

from core.models import WhatsAppMessageLog, SystemSetting
from core.services.whatsapp_service import WhatsAppService
from core.tasks.whatsapp_tasks import process_whatsapp_webhook_task
from customer.models import Customer
from supplier.models import Supplier


@pytest.mark.django_db
class TestWhatsAppCoexistencePhase5:
    """اختبارات التعايش المشترك ومعالجة الرسائل الواردة وصادرة الموبايل والـ Idempotency"""

    def setup_method(self):
        cache.clear()
        WhatsAppService.reset_session()

        # ضبط إعدادات الواتساب
        SystemSetting.objects.update_or_create(key="whatsapp_enabled", defaults={"value": "true", "data_type": "boolean", "group": "whatsapp", "is_active": True})
        SystemSetting.objects.update_or_create(key="whatsapp_access_token", defaults={"value": "EAABtesttoken123", "data_type": "string", "group": "whatsapp", "is_active": True})
        SystemSetting.objects.update_or_create(key="whatsapp_phone_number_id", defaults={"value": "1009988776655", "data_type": "string", "group": "whatsapp", "is_active": True})
        SystemSetting.objects.update_or_create(key="whatsapp_waba_id", defaults={"value": "2001122334455", "data_type": "string", "group": "whatsapp", "is_active": True})
        SystemSetting.objects.update_or_create(key="whatsapp_app_secret", defaults={"value": "secret123456", "data_type": "string", "group": "whatsapp", "is_active": True})

        # إنشاء عميل ومورد للاختبار
        self.customer = Customer.objects.create(
            name="شركة الأمل للتجارة",
            code="CUST-TEST-001",
            phone="01012345678",
            phone_primary="01012345678",
            whatsapp_opt_out=False
        )

        self.supplier = Supplier.objects.create(
            name="مؤسسة النور للتوريدات",
            code="SUPP-TEST-001",
            phone="01188776655",
            whatsapp="01188776655",
            whatsapp_opt_out=False
        )

        self.client = Client()

    def test_partner_matching_by_normalized_phone(self):
        """اختبار مطابقة العميل والمورد برقم الهاتف الدولي بدقة"""
        cust, supp, name = WhatsAppService.match_partner_by_phone("201012345678")
        assert cust == self.customer
        assert supp is None
        assert name == "شركة الأمل للتجارة"

        cust2, supp2, name2 = WhatsAppService.match_partner_by_phone("01188776655")
        assert cust2 is None
        assert supp2 == self.supplier
        assert name2 == "مؤسسة النور للتوريدات"

    def test_inbound_text_message_webhook_task(self):
        """اختبار معالجة رسالة نصية واردة من العميل وتحديث نافذة الـ 24 ساعة"""
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "2001122334455",
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "201099999999",
                            "phone_number_id": "1009988776655"
                        },
                        "messages": [{
                            "from": "201012345678",
                            "id": "wamid.HBgTESTINBOUND001",
                            "timestamp": "1728000000",
                            "type": "text",
                            "text": {"body": "مرحباً، أود الاستفسار عن رصيد حسابي"}
                        }]
                    }
                }]
            }]
        }

        res = process_whatsapp_webhook_task(payload)
        assert res["success"] is True
        assert res["processed_count"] == 1

        # التحقق من إنشاء السجل
        log = WhatsAppMessageLog.objects.get(message_id="wamid.HBgTESTINBOUND001")
        assert log.direction == "INBOUND"
        assert log.customer == self.customer
        assert log.body_text == "مرحباً، أود الاستفسار عن رصيد حسابي"
        assert log.status == "DELIVERED"

        # التحقق من فتح نافذة الـ 24 ساعة
        cached_window = cache.get("wa_24h_session_201012345678")
        assert cached_window is not None

    def test_coexistence_mobile_echo_message_webhook_task(self):
        """اختبار معالجة رسالة صادرة من تطبيق الموبايل (Coexistence Echo Event)"""
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "2001122334455",
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "201099999999",
                            "phone_number_id": "1009988776655"
                        },
                        "messages": [{
                            "from": "201099999999",  # مطابق لرقم النشاط التجاري
                            "recipient_id": "201012345678",
                            "id": "wamid.HBgTESTECHO001",
                            "timestamp": "1728000010",
                            "type": "text",
                            "text": {"body": "أهلاً بك، تم إرسال كشف الحساب لمكتبكم"}
                        }]
                    }
                }]
            }]
        }

        res = process_whatsapp_webhook_task(payload)
        assert res["success"] is True

        log = WhatsAppMessageLog.objects.get(message_id="wamid.HBgTESTECHO001")
        assert log.direction == "OUTBOUND_MOBILE"
        assert log.customer == self.customer
        assert log.body_text == "أهلاً بك، تم إرسال كشف الحساب لمكتبكم"

    def test_inbound_opt_out_and_re_opt_in_both_partners(self):
        """اختبار إلغاء وإعادة الاشتراك للعملاء والموردين آلياً"""
        # 1. إرسال STOP من العميل
        payload_stop = {
            "entry": [{
                "changes": [{
                    "value": {
                        "metadata": {"display_phone_number": "201099999999"},
                        "messages": [{
                            "from": "201012345678",
                            "id": "wamid.HBgSTOP001",
                            "type": "text",
                            "text": {"body": "STOP"}
                        }]
                    }
                }]
            }]
        }
        process_whatsapp_webhook_task(payload_stop)
        self.customer.refresh_from_db()
        assert self.customer.whatsapp_opt_out is True

        # 2. إرسال إلغاء من المورد
        payload_stop_supp = {
            "entry": [{
                "changes": [{
                    "value": {
                        "metadata": {"display_phone_number": "201099999999"},
                        "messages": [{
                            "from": "201188776655",
                            "id": "wamid.HBgSTOP002",
                            "type": "text",
                            "text": {"body": "إلغاء الاشتراك"}
                        }]
                    }
                }]
            }]
        }
        process_whatsapp_webhook_task(payload_stop_supp)
        self.supplier.refresh_from_db()
        assert self.supplier.whatsapp_opt_out is True

        # 3. إرسال START لإعادة التفعيل
        payload_start = {
            "entry": [{
                "changes": [{
                    "value": {
                        "metadata": {"display_phone_number": "201099999999"},
                        "messages": [{
                            "from": "201012345678",
                            "id": "wamid.HBgSTART001",
                            "type": "text",
                            "text": {"body": "START"}
                        }]
                    }
                }]
            }]
        }
        process_whatsapp_webhook_task(payload_start)
        self.customer.refresh_from_db()
        assert self.customer.whatsapp_opt_out is False

    def test_status_update_webhook_task(self):
        """اختبار تحديث حالات التسليم والقراءة للرسائل الصادرة"""
        log = WhatsAppMessageLog.objects.create(
            recipient_phone="201012345678",
            customer=self.customer,
            direction="OUTBOUND_ERP",
            template_name="document_send_ar",
            message_id="wamid.HBgTESTOUT001",
            status="SENT"
        )

        payload_status = {
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [
                            {"id": "wamid.HBgTESTOUT001", "status": "delivered", "timestamp": "1728000050"},
                            {"id": "wamid.HBgTESTOUT001", "status": "read", "timestamp": "1728000060"},
                        ]
                    }
                }]
            }]
        }

        res = process_whatsapp_webhook_task(payload_status)
        assert res["success"] is True

        log.refresh_from_db()
        assert log.status == "READ"
        assert log.delivered_at is not None
        assert log.read_at is not None
