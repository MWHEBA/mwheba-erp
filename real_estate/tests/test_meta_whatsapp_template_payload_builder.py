# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from real_estate.services.meta_whatsapp_payload_builder import MetaWhatsAppPayloadBuilder


class TestMetaWhatsAppPayloadBuilder:
    """
    اختبارات محرك بناء حمولات قوالب واتساب المتوافقة مع Meta Graph API v21.0
    """

    def test_phone_number_normalization(self):
        """اختبار توحيد وتطهير أرقام الهواتف للصيغة الدولية القياسية E.164"""
        # رقم مصري محلي يبدأ بـ 010
        assert MetaWhatsAppPayloadBuilder.normalize_phone_number("01012345678") == "+201012345678"
        # رقم مصري بصيغة 2010
        assert MetaWhatsAppPayloadBuilder.normalize_phone_number("201012345678") == "+201012345678"
        # رقم دولي يبدأ بـ 00
        assert MetaWhatsAppPayloadBuilder.normalize_phone_number("00966501234567") == "+966501234567"
        # رقم دولي يبدأ بالفعل بـ +
        assert MetaWhatsAppPayloadBuilder.normalize_phone_number("+201112223344") == "+201112223344"
        # أرقام بمسافات ورموز
        assert MetaWhatsAppPayloadBuilder.normalize_phone_number("012 - 345 67 890") == "+201234567890"

    def test_clean_text_parameter(self):
        """اختبار تطهير نصوص المتغيرات لمنع الأسطر المتعددة وحروف التحكم"""
        raw_text = "  سطر أول \n سطر ثاني \t مع مسافات زائدة   "
        clean = MetaWhatsAppPayloadBuilder.clean_text_parameter(raw_text, max_length=50)
        assert "\n" not in clean
        assert "\t" not in clean
        assert "  " not in clean
        assert clean == "سطر أول سطر ثاني مع مسافات زائدة"

    def test_build_installment_reminder_payload(self):
        """اختبار بناء قالب تذكير القسط re_installment_reminder وفق معايير Meta"""
        payload = MetaWhatsAppPayloadBuilder.build_installment_reminder_payload(
            recipient_phone="01012345678",
            customer_name="أحمد محمود السيد",
            unit_code="TW1-F04-U02",
            due_date="2026-12-01",
            amount=Decimal("75000.50"),
            currency_code="EGP",
            statement_url="https://mwheba.com/stmt/123",
            statement_token="a1b2c3d4e5f6"
        )

        assert payload["messaging_product"] == "whatsapp"
        assert payload["recipient_type"] == "individual"
        assert payload["to"] == "+201012345678"
        assert payload["type"] == "template"

        template = payload["template"]
        assert template["name"] == MetaWhatsAppPayloadBuilder.TEMPLATE_INSTALLMENT_REMINDER
        assert template["language"]["code"] == "ar"

        # فحص مكون الـ body
        components = template["components"]
        body_comp = next(c for c in components if c["type"] == "body")
        params = body_comp["parameters"]
        assert len(params) == 5
        assert params[0]["text"] == "أحمد محمود السيد"
        assert params[1]["text"] == "TW1-F04-U02"
        assert params[2]["text"] == "2026-12-01"
        assert "75,000.50 EGP" in params[3]["text"]
        assert params[4]["text"] == "https://mwheba.com/stmt/123"

        # فحص زر الرابط الديناميكي
        btn_comp = next((c for c in components if c["type"] == "button"), None)
        assert btn_comp is not None
        assert btn_comp["sub_type"] == "url"
        assert btn_comp["index"] == "0"
        assert btn_comp["parameters"][0]["text"] == "a1b2c3d4e5f6"

    def test_build_booking_confirmation_payload(self):
        """اختبار بناء قالب تأكيد الحجز re_booking_confirmation"""
        payload = MetaWhatsAppPayloadBuilder.build_booking_confirmation_payload(
            recipient_phone="01198765432",
            customer_name="خالد عبد الرحمن",
            unit_code="TW2-F02-U01",
            expiry_date="2026-11-15",
            paid_amount=Decimal("50000.00"),
            currency_code="EGP"
        )

        assert payload["to"] == "+201198765432"
        template = payload["template"]
        assert template["name"] == MetaWhatsAppPayloadBuilder.TEMPLATE_BOOKING_CONFIRMATION

        body_comp = template["components"][0]
        params = body_comp["parameters"]
        assert len(params) == 4
        assert params[0]["text"] == "خالد عبد الرحمن"
        assert params[1]["text"] == "TW2-F02-U01"
        assert params[2]["text"] == "2026-11-15"
        assert "50,000.00 EGP" in params[3]["text"]

    def test_build_legal_demand_payload(self):
        """اختبار بناء قالب الإنذار القانوني re_legal_notice_demand"""
        payload = MetaWhatsAppPayloadBuilder.build_legal_demand_payload(
            recipient_phone="01234567890",
            customer_name="طارق مصطفى",
            unit_code="VIL-05",
            contract_number="CTR-2026-0089",
            overdue_days=35,
            total_overdue_amount=Decimal("185400.00"),
            cure_deadline="2026-11-20",
            currency_code="EGP"
        )

        assert payload["to"] == "+201234567890"
        template = payload["template"]
        assert template["name"] == MetaWhatsAppPayloadBuilder.TEMPLATE_LEGAL_NOTICE_DEMAND

        body_comp = template["components"][0]
        params = body_comp["parameters"]
        assert len(params) == 6
        assert params[0]["text"] == "طارق مصطفى"
        assert params[1]["text"] == "VIL-05"
        assert params[2]["text"] == "CTR-2026-0089"
        assert params[3]["text"] == "35"
        assert "185,400.00 EGP" in params[4]["text"]
        assert params[5]["text"] == "2026-11-20"
