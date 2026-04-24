"""
خدمة إرسال رسائل WhatsApp عبر Kapso API
"""
import logging
import requests
from django.conf import settings

from ..models import SystemSetting

logger = logging.getLogger(__name__)


class WhatsAppService:
    """
    خدمة WhatsApp - تقرأ الإعدادات من قاعدة البيانات (SystemSetting)
    وترسل الرسائل عبر Kapso API
    """

    KAPSO_API_BASE = "https://api.kapso.ai/platform/v1"

    # ==================== إعدادات ====================

    @classmethod
    def get_config(cls) -> dict:
        """قراءة إعدادات WhatsApp من قاعدة البيانات"""
        return {
            "enabled": SystemSetting.get_setting("whatsapp_enabled", False),
            "api_key": SystemSetting.get_setting("whatsapp_api_key", ""),
            "phone_number_id": SystemSetting.get_setting("whatsapp_phone_number_id", ""),
            "send_invoice_notification": SystemSetting.get_setting("whatsapp_send_invoice", True),
            "send_payment_notification": SystemSetting.get_setting("whatsapp_send_payment", True),
            "send_overdue_reminder": SystemSetting.get_setting("whatsapp_send_overdue", True),
            "overdue_reminder_days": SystemSetting.get_setting("whatsapp_overdue_days", 7),
        }

    @classmethod
    def is_enabled(cls) -> bool:
        """هل خدمة WhatsApp مفعلة ومهيأة؟"""
        config = cls.get_config()
        return bool(config.get("enabled") and config.get("api_key") and config.get("phone_number_id"))

    # ==================== الإرسال الأساسي ====================

    @classmethod
    def send_message(cls, phone: str, message: str, customer_name: str = "") -> bool:
        """
        إرسال رسالة عبر template دائماً.
        الرسالة العادية متوقفة - WhatsApp يرفضها خارج نافذة 24 ساعة.
        """
        return cls._send_via_template(phone, message, customer_name=customer_name)

    @classmethod
    def send_template_message(cls, phone: str, template_name: str,
                               language_code: str = "ar",
                               components: list = None) -> bool:
        """
        إرسال template message معتمد من Meta.
        يُستخدم لفتح محادثة جديدة أو خارج نافذة 24 ساعة.

        Args:
            phone: رقم الهاتف
            template_name: اسم القالب (Template) المعتمد في Meta
            language_code: كود اللغة (ar, en_US, ...)
            components: مكونات الـ template (header, body, buttons)

        Returns:
            True عند النجاح، False عند الفشل
        """
        if not cls.is_enabled():
            return False

        config = cls.get_config()
        phone = cls._normalize_phone(phone)
        if not phone:
            return False

        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }
        if components:
            payload["template"]["components"] = components

        try:
            response = requests.post(
                f"https://api.kapso.ai/meta/whatsapp/v24.0/{config['phone_number_id']}/messages",
                headers={
                    "X-API-Key": config["api_key"],
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10,
            )
            response.raise_for_status()

            # تحقق من الـ response body - الـ API ممكن ترجع 200 مع error
            resp_json = response.json()
            error = cls._extract_response_error(resp_json)
            if error:
                error_code = error.get("code")
                logger.error(f"WhatsApp template '{template_name}' delivery error {error_code} لـ {phone}: {error.get('message', '')}")
                return False

            logger.info(f"✅ WhatsApp template '{template_name}' أُرسل إلى {phone}")
            return True
        except requests.exceptions.HTTPError as e:
            logger.error(f"WhatsApp template error {e.response.status_code}: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"WhatsApp template خطأ غير متوقع: {e}")
            return False

    @classmethod
    def get_templates(cls) -> list:
        """
        جلب قائمة الـ templates المعتمدة من Meta عبر Kapso proxy.
        محتاج WABA ID اللي بيتجيب من phone_numbers endpoint.
        """
        if not cls.is_enabled():
            return []

        config = cls.get_config()
        headers = {"X-API-Key": config["api_key"]}

        # أولاً: جيب الـ WABA ID من phone_numbers (اللي بتشتغل)
        try:
            r = requests.get(
                f"{cls.KAPSO_API_BASE}/whatsapp/phone_numbers",
                headers=headers,
                timeout=10,
            )
            if r.status_code == 200:
                numbers = r.json().get("data", [])
                match = next(
                    (n for n in numbers if n.get("phone_number_id") == config["phone_number_id"]),
                    numbers[0] if numbers else None
                )
                if match:
                    waba_id = (match.get("waba_id") or match.get("business_account_id")
                               or match.get("whatsapp_business_account_id", ""))
                    logger.info(f"WhatsApp WABA ID: {waba_id}, phone data keys: {list(match.keys())}")

                    if waba_id:
                        # جيب الـ templates بالـ WABA ID عبر Kapso proxy
                        tr = requests.get(
                            f"https://api.kapso.ai/meta/whatsapp/v24.0/{waba_id}/message_templates",
                            headers=headers,
                            params={"fields": "name,status,language,category,components", "limit": 100},
                            timeout=10,
                        )
                        if tr.status_code == 200:
                            templates = tr.json().get("data", [])
                            logger.info(f"WhatsApp templates: {len(templates)}")
                            return templates
                        logger.warning(f"WhatsApp templates WABA: {tr.status_code} - {tr.text[:200]}")
        except Exception as e:
            logger.error(f"WhatsApp get_templates: {e}")

        return []

    @classmethod
    def _extract_response_error(cls, resp_json: dict):
        """
        استخراج الـ error من الـ response body لو الـ API رجعت 200 مع error.
        Meta API ممكن ترجع errors في:
        - resp["error"]
        - resp["messages"][0]["message_status"] == "failed"
        - resp["statuses"][0]["errors"][0]
        """
        # حالة error مباشر في الـ response
        if "error" in resp_json:
            err = resp_json["error"]
            return {"code": err.get("code"), "message": err.get("message", str(err))}

        # حالة messages array فيها status failed
        messages = resp_json.get("messages", [])
        if messages and isinstance(messages, list):
            first = messages[0]
            if first.get("message_status") == "failed":
                errors = first.get("errors", [{}])
                err = errors[0] if errors else {}
                return {"code": err.get("code"), "message": err.get("message", "message_status=failed")}

        # حالة statuses array (webhook-style في بعض الـ proxies)
        statuses = resp_json.get("statuses", [])
        if statuses and isinstance(statuses, list):
            first = statuses[0]
            if first.get("status") == "failed":
                errors = first.get("errors", [{}])
                err = errors[0] if errors else {}
                return {"code": err.get("code"), "message": err.get("message", "status=failed")}

        return None

    @classmethod
    def _send_via_template(cls, phone: str, original_message: str, customer_name: str = "") -> bool:
        """
        إرسال عبر template دائماً - الطريقة الوحيدة للإرسال.
        يملأ الـ parameters تلقائياً من محتوى الرسالة واسم العميل.
        """
        if not cls.is_enabled():
            return False

        config = cls.get_config()
        phone = cls._normalize_phone(phone)
        if not phone:
            logger.warning("WhatsApp: رقم هاتف غير صالح")
            return False

        template_name = SystemSetting.get_setting("whatsapp_fallback_template", "")
        if not template_name:
            logger.warning(f"WhatsApp: مش قادر يبعت لـ {phone} - مفيش template مهيأ في الإعدادات.")
            return False

        template_lang = SystemSetting.get_setting("whatsapp_fallback_template_lang", "ar")
        components = cls._get_template_components(template_name, config)
        param_names = cls._get_body_param_names(components)
        # جيب نص الـ body عشان نعرف السياق
        body_text = cls._get_body_text(components)

        logger.info(f"WhatsApp template '{template_name}' - params: {param_names} - لـ {phone}")

        if not param_names:
            return cls.send_template_message(phone, template_name, language_code=template_lang)

        import re as _re
        parameters = []
        for i, param in enumerate(param_names):
            param_lower = param.lower()
            # حدد القيمة بناءً على اسم الـ parameter أو موضعه في الـ body text
            is_name_param = any(k in param_lower for k in ["name", "customer", "client", "عميل", "اسم"])
            if not is_name_param and body_text:
                # ابحث عن السياق حول الـ parameter في نص الـ template
                pattern = _re.compile(r'([^\n]{0,20})\{\{' + _re.escape(param) + r'\}\}([^\n]{0,20})')
                m = pattern.search(body_text)
                if m:
                    context = (m.group(1) + m.group(2)).lower()
                    is_name_param = any(k in context for k in ["اسم", "عميل", "name", "customer"])

            if is_name_param:
                value = (customer_name or "عميلنا العزيز")[:60]
            else:
                msg = original_message or "لديك إشعار جديد"
                msg = msg.replace('\n', ' ').replace('\t', ' ')
                msg = _re.sub(r' {5,}', '    ', msg)
                value = msg

            # numbered parameters في utility templates لها حد 30 حرف
            if param.isdigit():
                value = value[:30]
                parameters.append({"type": "text", "text": value})
            else:
                parameters.append({"type": "text", "parameter_name": param, "text": value})

        components_payload = [{"type": "body", "parameters": parameters}]
        return cls.send_template_message(phone, template_name, language_code=template_lang, components=components_payload)

    @classmethod
    def _get_template_components(cls, template_name: str, config: dict) -> list:
        """جيب الـ components بتاعة template معين"""
        try:
            templates = cls.get_templates()
            match = next((t for t in templates if t.get("name") == template_name), None)
            if match:
                return match.get("components", [])
        except Exception:
            pass
        return []

    @staticmethod
    def _get_body_text(components: list) -> str:
        """استخرج نص الـ body من الـ template components"""
        for comp in components:
            if comp.get("type", "").upper() == "BODY":
                return comp.get("text", "")
        return ""

    @staticmethod
    def _get_body_param_names(components: list) -> list:
        """استخرج أسماء الـ parameters من الـ body - يدعم {{1}} و {{customer_name}}"""
        import re
        for comp in components:
            if comp.get("type", "").upper() == "BODY":
                text = comp.get("text", "")
                return re.findall(r'\{\{([\w]+)\}\}', text)
        return []

    @staticmethod
    def _count_body_params(components: list) -> int:
        """عد عدد الـ parameters في الـ body component - يدعم {{1}} و {{customer_name}}"""
        import re
        for comp in components:
            if comp.get("type", "").upper() == "BODY":
                text = comp.get("text", "")
                return len(re.findall(r'\{\{[\w]+\}\}', text))
        return 0

    @classmethod
    def test_connection(cls, api_key: str, phone_number_id: str) -> dict:
        """
        اختبار الاتصال بـ Kapso API
        - لو phone_number_id موجود: يتحقق منه مباشرة
        - لو فاضي: يجيب قائمة الأرقام المتاحة في الحساب

        Returns:
            {"success": bool, "message": str, "phone_numbers": list (optional)}
        """
        if not api_key:
            return {"success": False, "message": "أدخل API Key أولاً"}

        headers = {"X-API-Key": api_key}

        try:
            # أولاً: جرب تجيب قائمة الأرقام (يثبت صحة الـ API Key)
            list_response = requests.get(
                f"{cls.KAPSO_API_BASE}/whatsapp/phone_numbers",
                headers=headers,
                timeout=10,
            )

            if list_response.status_code == 401:
                return {"success": False, "message": "API Key غير صحيح"}

            if list_response.status_code != 200:
                return {"success": False, "message": f"خطأ في الاتصال ({list_response.status_code})"}

            data = list_response.json()
            numbers = data.get("data", [])

            # لو مفيش phone_number_id، ارجع قائمة الأرقام المتاحة
            if not phone_number_id:
                if not numbers:
                    return {"success": True, "message": "API Key صحيح ✅ - لا توجد أرقام في الحساب بعد", "phone_numbers": []}
                options = [
                    {"id": n["phone_number_id"], "label": f'{n.get("display_phone_number") or n["phone_number_id"]} — {n.get("name", "")}'}
                    for n in numbers
                ]
                return {
                    "success": True,
                    "message": f"API Key صحيح ✅ - اختر رقم الواتساب",
                    "phone_numbers": options,
                }

            # لو phone_number_id موجود، تحقق منه في القائمة
            match = next((n for n in numbers if n["phone_number_id"] == phone_number_id), None)
            if match:
                display = match.get("display_phone_number") or phone_number_id
                name = match.get("verified_name") or match.get("name", "")
                status = match.get("status", "")
                return {
                    "success": True,
                    "message": f"متصل ✅ — {display} ({name}) | الحالة: {status}",
                }
            else:
                # Phone Number ID مش في الحساب ده
                options = [
                    {"id": n["phone_number_id"], "label": f'{n.get("display_phone_number") or n["phone_number_id"]} — {n.get("name", "")}'}
                    for n in numbers
                ]
                return {
                    "success": False,
                    "message": "Phone Number ID غير موجود في هذا الحساب",
                    "phone_numbers": options,
                }

        except requests.exceptions.Timeout:
            return {"success": False, "message": "انتهت مهلة الاتصال"}
        except Exception as e:
            return {"success": False, "message": f"خطأ في الاتصال: {str(e)}"}

    # ==================== رسائل جاهزة ====================

    @classmethod
    def send_invoice_notification(cls, customer_name: str, phone: str,
                                   invoice_number: str, total: float,
                                   currency: str = "ج.م") -> bool:
        """إشعار فاتورة جديدة للعميل"""
        config = cls.get_config()
        if not config.get("send_invoice_notification"):
            return False
        site_name = SystemSetting.get_site_name()
        message = (
            f"🧾 فاتورة جديدة\n"
            f"العميل: {customer_name}\n"
            f"رقم الفاتورة: {invoice_number}\n"
            f"الإجمالي: {total:,.2f} {currency}\n\n"
            f"شكراً لتعاملكم مع {site_name} 🙏"
        )
        return cls._send_via_template(phone, message, customer_name=customer_name)

    @classmethod
    def send_payment_receipt(cls, customer_name: str, phone: str,
                              amount: float, invoice_number: str,
                              currency: str = "ج.م") -> bool:
        """إيصال استلام دفعة"""
        config = cls.get_config()
        if not config.get("send_payment_notification"):
            return False
        site_name = SystemSetting.get_site_name()
        message = (
            f"✅ تم استلام دفعتك\n"
            f"العميل: {customer_name}\n"
            f"المبلغ: {amount:,.2f} {currency}\n"
            f"الفاتورة: {invoice_number}\n\n"
            f"شكراً لتعاملكم مع {site_name} 🙏"
        )
        return cls._send_via_template(phone, message, customer_name=customer_name)

    @classmethod
    def send_overdue_reminder(cls, customer_name: str, phone: str,
                               invoice_number: str, amount_due: float,
                               days_overdue: int, currency: str = "ج.م") -> bool:
        """تذكير بفاتورة متأخرة"""
        config = cls.get_config()
        if not config.get("send_overdue_reminder"):
            return False
        site_name = SystemSetting.get_site_name()
        message = (
            f"⚠️ تذكير بسداد فاتورة\n"
            f"العميل: {customer_name}\n"
            f"رقم الفاتورة: {invoice_number}\n"
            f"المبلغ المستحق: {amount_due:,.2f} {currency}\n"
            f"متأخرة منذ: {days_overdue} يوم\n\n"
            f"يرجى التواصل مع {site_name} لتسوية المبلغ 🙏"
        )
        return cls._send_via_template(phone, message, customer_name=customer_name)

    @classmethod
    def send_test_message(cls, phone: str) -> dict:
        """إرسال رسالة تجريبية عبر template"""
        if not cls.is_enabled():
            return {"success": False, "message": "خدمة WhatsApp غير مفعلة أو غير مهيأة"}
        if not cls._normalize_phone(phone):
            return {"success": False, "message": "رقم الهاتف غير صحيح"}

        template_name = SystemSetting.get_setting("whatsapp_fallback_template", "")
        if not template_name:
            return {"success": False, "message": "لم يتم تحديد template في إعدادات WhatsApp"}

        config = cls.get_config()
        template_lang = SystemSetting.get_setting("whatsapp_fallback_template_lang", "ar")
        components = cls._get_template_components(template_name, config)
        param_names = cls._get_body_param_names(components)

        from django.utils import timezone
        now = timezone.localtime()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%I:%M %p")

        # ملأ كل parameter بقيمة تجريبية منطقية (تاريخ أو وقت أو نص قصير)
        test_values = [date_str, time_str, "اختبار", "تجريبي", "Test"]
        parameters = []
        for i, param in enumerate(param_names):
            value = test_values[i] if i < len(test_values) else f"قيمة {i+1}"
            value = value[:30]
            if param.isdigit():
                parameters.append({"type": "text", "text": value})
            else:
                parameters.append({"type": "text", "parameter_name": param, "text": value})

        components_payload = [{"type": "body", "parameters": parameters}] if parameters else None
        ok = cls.send_template_message(phone, template_name, language_code=template_lang, components=components_payload)

        if ok:
            return {"success": True, "message": f"✅ تم إرسال الرسالة التجريبية إلى {phone}"}
        return {"success": False, "message": "فشل الإرسال - تحقق من الـ logs"}

    # ==================== مساعدات ====================

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """
        تنظيف رقم الهاتف وتحويله للصيغة الدولية
        يدعم الأرقام المصرية والخليجية
        """
        if not phone:
            return ""

        # إزالة المسافات والشرطات والأقواس
        phone = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

        # إزالة + من البداية
        if phone.startswith("+"):
            phone = phone[1:]

        # تحويل الأرقام المصرية: 01x -> 201x
        if phone.startswith("01") and len(phone) == 11:
            phone = "2" + phone

        # التحقق من أن الرقم يحتوي على أرقام فقط
        if not phone.isdigit():
            return ""

        return phone
