# -*- coding: utf-8 -*-
"""
MetaWhatsAppPayloadBuilder - محرك بناء حمولات قوالب واتساب المعتمدة من ميتا
MWHEBA ERP — Meta Graph API v21.0 Compliant Utility Template Engine
"""
import re
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.utils.translation import gettext_lazy as _


class MetaWhatsAppPayloadBuilder:
    """
    محرك بناء وتدقيق قوالب Meta WhatsApp Utility المعتمدة
    يضمن التوافق 100% مع Meta Graph API v21.0+ وحظر الرسائل الحرة خارج نافذة 24 ساعة
    """

    GRAPH_API_VERSION = "v21.0"

    # أسماء القوالب المعتمدة رسمياً في Meta Business Manager
    TEMPLATE_INSTALLMENT_REMINDER = "re_installment_reminder"
    TEMPLATE_BOOKING_CONFIRMATION = "re_booking_confirmation"
    TEMPLATE_LEGAL_NOTICE_DEMAND = "re_legal_notice_demand"

    @classmethod
    def normalize_phone_number(cls, raw_phone: str) -> str:
        """
        تطهير وتوحيد تنسيق رقم الهاتف للصيغة الدولية (E.164)
        يدعم الأرقام المصرية (01x -> +201x) والدولية
        """
        if not raw_phone:
            return ""
        digits = re.sub(r'[^\d+]', '', str(raw_phone).strip())
        if digits.startswith('+'):
            return digits
        if digits.startswith('00'):
            return '+' + digits[2:]
        if digits.startswith('01') and len(digits) == 11:
            return '+2' + digits
        if digits.startswith('20') and len(digits) == 12:
            return '+' + digits
        return '+' + digits if digits else ""

    @classmethod
    def clean_text_parameter(cls, text: Any, max_length: int = 120) -> str:
        """
        تطهير نصوص المتغيرات لمنع حروف التحكم أو الأسطر المتعددة التي تسبب رفض Meta (Error 132000)
        """
        if text is None:
            return "-"
        clean = re.sub(r'[\r\n\t]+', ' ', str(text)).strip()
        clean = re.sub(r'\s{2,}', ' ', clean)
        return clean[:max_length] if clean else "-"

    @classmethod
    def build_installment_reminder_payload(
        cls,
        recipient_phone: str,
        customer_name: str,
        unit_code: str,
        due_date: str,
        amount: Decimal,
        currency_code: str = "EGP",
        statement_url: str = "",
        statement_token: Optional[str] = None,
        language_code: str = "ar"
    ) -> Dict[str, Any]:
        """
        قالب: re_installment_reminder
        المتغيرات المعتمدة:
        {{1}}: اسم العميل
        {{2}}: كود الوحدة العقارية
        {{3}}: تاريخ الاستحقاق
        {{4}}: مبلغ القسط
        {{5}}: رابط كشف الحساب
        """
        phone = cls.normalize_phone_number(recipient_phone)
        formatted_amount = f"{Decimal(str(amount)):,.2f} {currency_code}"
        url_text = cls.clean_text_parameter(statement_url, max_length=200)

        body_parameters = [
            {"type": "text", "text": cls.clean_text_parameter(customer_name, 60)},
            {"type": "text", "text": cls.clean_text_parameter(unit_code, 40)},
            {"type": "text", "text": cls.clean_text_parameter(due_date, 30)},
            {"type": "text", "text": formatted_amount},
            {"type": "text", "text": url_text},
        ]

        components: List[Dict[str, Any]] = [
            {
                "type": "body",
                "parameters": body_parameters
            }
        ]

        if statement_token:
            components.append({
                "type": "button",
                "sub_type": "url",
                "index": "0",
                "parameters": [
                    {"type": "text", "text": cls.clean_text_parameter(statement_token, 64)}
                ]
            })

        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": "template",
            "template": {
                "name": cls.TEMPLATE_INSTALLMENT_REMINDER,
                "language": {"code": language_code},
                "components": components
            }
        }

    @classmethod
    def build_booking_confirmation_payload(
        cls,
        recipient_phone: str,
        customer_name: str,
        unit_code: str,
        expiry_date: str,
        paid_amount: Decimal,
        currency_code: str = "EGP",
        language_code: str = "ar"
    ) -> Dict[str, Any]:
        """
        قالب: re_booking_confirmation
        المتغيرات المعتمدة:
        {{1}}: اسم الحاجز
        {{2}}: كود الوحدة العقارية
        {{3}}: تاريخ انتهاء مهلة الحجز
        {{4}}: مقدم الحجز المسدد
        """
        phone = cls.normalize_phone_number(recipient_phone)
        formatted_amount = f"{Decimal(str(paid_amount)):,.2f} {currency_code}"

        body_parameters = [
            {"type": "text", "text": cls.clean_text_parameter(customer_name, 60)},
            {"type": "text", "text": cls.clean_text_parameter(unit_code, 40)},
            {"type": "text", "text": cls.clean_text_parameter(expiry_date, 30)},
            {"type": "text", "text": formatted_amount},
        ]

        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": "template",
            "template": {
                "name": cls.TEMPLATE_BOOKING_CONFIRMATION,
                "language": {"code": language_code},
                "components": [
                    {
                        "type": "body",
                        "parameters": body_parameters
                    }
                ]
            }
        }

    @classmethod
    def build_legal_demand_payload(
        cls,
        recipient_phone: str,
        customer_name: str,
        unit_code: str,
        contract_number: str,
        overdue_days: int,
        total_overdue_amount: Decimal,
        cure_deadline: str,
        currency_code: str = "EGP",
        language_code: str = "ar"
    ) -> Dict[str, Any]:
        """
        قالب: re_legal_notice_demand
        المتغيرات المعتمدة:
        {{1}}: اسم العميل
        {{2}}: كود الوحدة
        {{3}}: رقم العقد
        {{4}}: أيام التأخير
        {{5}}: إجمالي المبلغ المطالب به (شامل الغرامات)
        {{6}}: تاريخ نهاية مهلة توفيق الأوضاع قبل الفسخ
        """
        phone = cls.normalize_phone_number(recipient_phone)
        formatted_amount = f"{Decimal(str(total_overdue_amount)):,.2f} {currency_code}"

        body_parameters = [
            {"type": "text", "text": cls.clean_text_parameter(customer_name, 60)},
            {"type": "text", "text": cls.clean_text_parameter(unit_code, 40)},
            {"type": "text", "text": cls.clean_text_parameter(contract_number, 50)},
            {"type": "text", "text": str(max(0, int(overdue_days)))},
            {"type": "text", "text": formatted_amount},
            {"type": "text", "text": cls.clean_text_parameter(cure_deadline, 30)},
        ]

        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": "template",
            "template": {
                "name": cls.TEMPLATE_LEGAL_NOTICE_DEMAND,
                "language": {"code": language_code},
                "components": [
                    {
                        "type": "body",
                        "parameters": body_parameters
                    }
                ]
            }
        }
