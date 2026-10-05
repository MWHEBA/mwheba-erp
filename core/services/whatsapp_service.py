# -*- coding: utf-8 -*-
"""
خدمة تكامل WhatsApp Business Cloud API المباشرة من Meta (Graph API v21.0+)
MWHEBA ERP — Production-Grade WhatsApp Service
"""
import io
import re
import hmac
import hashlib
import logging
import threading
import requests
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger('core.services.whatsapp')


class WhatsAppService:
    """
    خدمة WhatsApp الرسمية المباشرة من Meta (بدون وسطاء)
    تتعامل مع Graph API v21.0+ وتدعم:
    - رفع واستخدام ملفات PDF الثنائية مباشرة في الذاكرة (In-Memory Stream)
    - محول شبكة صلب مع إعادة المحاولة التلقائية (HTTPAdapter Retry)
    - فحص جودة الرقم واسم العرض المعتمد والـ Tier
    - قاموس الترجمة الفورية الإرشادية لأخطاء ميتا بالعربية
    - قفل منع التكرار السحابي (Backend Debounce Lock)
    - محرك التنفيذ المزدوج (Celery مع Fallback للـ Threads)
    """

    GRAPH_API_VERSION = "v21.0"
    GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
    
    _session: Optional[requests.Session] = None
    _session_lock = threading.Lock()

    # قاموس الترجمة الفورية لأخطاء ميتا بالعربية مع الحلول الإرشادية
    META_ERROR_GUIDANCE = {
        131026: "الرقم غير مسجل على واتساب، يرجى التأكد من صحة رقم المستلم أو اختيار جهة اتصال أخرى.",
        131042: "بطاقة الدفع أو الرصيد الائتماني في حساب Meta Business بحاجة لتحديث.",
        131047: "تم الوصول للحد الأقصى اليومي لرسائل الـ Utility في حساب Meta.",
        132000: "هيكل المتغيرات في القالب غير متطابق مع القالب المعتمد في Meta.",
        132001: "القالب غير موجود أو غير معتمد بهذه اللغة في حساب Meta (Template does not exist in translation). يرجى اعتماد القالب في Meta WhatsApp Manager.",
        131031: "حساب WhatsApp Business معلق أو مقيد من قبل Meta.",
        131051: "نوع الملف المرفق أو حجمه غير مدعوم من Meta (الحد الأقصى 100MB للـ PDF).",
        131052: "فشل تحميل الوسائط من سيرفرات Meta، يرجى إعادة المحاولة.",
        131053: "انتهت صلاحية معرف الوسائط (Media ID) القديم، يتم إعادة توليد الملف فوراً.",
        190: "رمز الوصول (Access Token) غير صالح أو انتهت صلاحيته، يرجى تحديث التوكن الدائم.",
        100: "معلمة غير صالحة أو مفقودة في طلب الإرسال لـ Meta API.",
        80007: "تم تجاوز معدل الطلبات المسموح به (Rate Limit)، يرجى الانتظار قليلاً.",
    }

    # ==================== إدارة الجلسة والاتصال الشبكي ====================

    @classmethod
    def get_session(cls) -> requests.Session:
        """الحصول على جلسة HTTP معززة بمحول إعادة الاتصال التلقائي وإدارة اتصالات عالية الأداء"""
        with cls._session_lock:
            if cls._session is None:
                session = requests.Session()
                retry_strategy = Retry(
                    total=3,
                    backoff_factor=0.5,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
                )
                adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=20, pool_maxsize=50)
                session.mount("https://", adapter)
                session.mount("http://", adapter)
                cls._session = session
            return cls._session

    @classmethod
    def reset_session(cls):
        """تفريغ الجلسة الحالية ومسح كاش الإعدادات والفحص لإعادة البناء الفوري بتوكنات جديدة"""
        with cls._session_lock:
            if cls._session is not None:
                try:
                    cls._session.close()
                except Exception:
                    pass
                cls._session = None
        cache.delete("whatsapp_config")
        cache.delete("whatsapp_health_status")
        cache.delete("whatsapp_health_cache")

    # ==================== قراءة وتشفير الإعدادات (3-Tier Backward Compatible Resolution) ====================

    @classmethod
    def get_config(cls, account: Optional[Any] = None, account_id: Optional[int] = None) -> Dict[str, Any]:
        """
        قراءة إعدادات WhatsApp عبر طبقة التوافق العكسي ثلاثية المستويات (3-Tier Fallback):
        - Tier 1: حساب WhatsAppAccount الممرر أو الافتراضي (مع فك التشفير الآمن)
        - Tier 2: إعدادات SystemSetting المحفوظة في قاعدة البيانات
        - Tier 3: متغيرات البيئة في django.conf.settings
        """
        from ..models import SystemSetting, WhatsAppAccount

        # محاولة حل الحساب من Tier 1
        account_obj = None
        if account and isinstance(account, WhatsAppAccount):
            account_obj = account
        elif account_id:
            account_obj = WhatsAppAccount.objects.filter(pk=account_id).first()
        
        if not account_obj:
            account_obj = WhatsAppAccount.objects.filter(is_default=True).first() or WhatsAppAccount.objects.filter(account_status='CONNECTED').first()

        phone_number_id = ""
        access_token = ""
        waba_id = ""
        app_id = ""
        is_coexistence = True
        account_id_val = None

        if account_obj:
            phone_number_id = str(account_obj.phone_number_id or "").strip()
            access_token = str(account_obj.access_token or "").strip()
            waba_id = str(account_obj.waba_id or "").strip()
            app_id = str(account_obj.app_id or "").strip()
            is_coexistence = bool(account_obj.is_coexistence)
            account_id_val = account_obj.id

        # Fallback إلى Tier 2 (SystemSetting)
        if not phone_number_id:
            phone_number_id = SystemSetting.get_setting("whatsapp_phone_number_id", "").strip()
        if not access_token:
            access_token = SystemSetting.get_setting("whatsapp_access_token", "").strip()
        if not waba_id:
            waba_id = SystemSetting.get_setting("whatsapp_waba_id", "").strip()
        if not app_id:
            app_id = SystemSetting.get_setting("whatsapp_app_id", "").strip()

        # Fallback إلى Tier 3 (settings)
        if not phone_number_id:
            phone_number_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '').strip()
        if not access_token:
            access_token = getattr(settings, 'WHATSAPP_ACCESS_TOKEN', '').strip()
        if not waba_id:
            waba_id = getattr(settings, 'WHATSAPP_WABA_ID', '').strip()
        if not app_id:
            app_id = getattr(settings, 'WHATSAPP_APP_ID', '').strip()

        config = {
            "account_id": account_id_val,
            "account": account_obj,
            "enabled": SystemSetting.get_setting("whatsapp_enabled", True) if (phone_number_id and access_token) else False,
            "access_token": access_token,
            "phone_number_id": phone_number_id,
            "waba_id": waba_id,
            "app_id": app_id,
            "app_secret": SystemSetting.get_setting("whatsapp_app_secret", "").strip() or getattr(settings, 'WHATSAPP_APP_SECRET', '').strip(),
            "is_coexistence": is_coexistence,
            "default_country_code": SystemSetting.get_setting("whatsapp_default_country_code", "+20").strip(),
            "fallback_template": SystemSetting.get_setting("whatsapp_fallback_template", "document_send_ar").strip(),
            "fallback_template_lang": SystemSetting.get_setting("whatsapp_fallback_template_lang", "ar").strip(),
            "public_portal_url": SystemSetting.get_setting("public_portal_url", "").strip(),
            "send_invoice_notification": SystemSetting.get_setting("whatsapp_send_invoice", True),
            "send_payment_notification": SystemSetting.get_setting("whatsapp_send_payment", True),
            "send_overdue_reminder": SystemSetting.get_setting("whatsapp_send_overdue", True),
            "overdue_reminder_days": SystemSetting.get_setting("whatsapp_overdue_days", 7),
        }
        return config

    @classmethod
    def is_enabled(cls, account: Optional[Any] = None, account_id: Optional[int] = None) -> bool:
        """هل خدمة WhatsApp مفعلة ومربوطة بحساب صالح؟"""
        config = cls.get_config(account=account, account_id=account_id)
        return bool(config.get("enabled") and config.get("access_token") and config.get("phone_number_id"))

    @staticmethod
    def calculate_document_sha256(file_bytes: bytes) -> str:
        """حساب البصمة التشفيرية لمستند PDF لضمان الإثبات الجنائي والقانوني (Non-Repudiation)"""
        if not file_bytes:
            return ""
        return hashlib.sha256(file_bytes).hexdigest()

    # ==================== أدوات معالجة الأرقام والنصوص ====================

    @classmethod
    def clean_template_variable(cls, text: Any, isolate_bidi: bool = True) -> str:
        """تطهير نصوص المتغيرات واستبدال القيم الفارغة بقيمة آمنة (-) لمنع خطأ Meta 132000 مع عزل اتجاه النص"""
        if text is None:
            return "-"
        s = str(text).strip()
        if not s:
            return "-"
        # إزالة علامات الأسطر الجديدة المتكررة واستبدالها بمسافة
        s = re.sub(r'[\r\n\t]+', ' ', s)
        s = re.sub(r'\s{2,}', ' ', s)
        s = s[:1024]
        if isolate_bidi and any(c.isdigit() for c in s):
            # عزل النص ثنائي الاتجاه بالـ Unicode Isolation
            return f"\u2066{s}\u2069"
        return s

    @classmethod
    def normalize_phone(cls, phone: str, default_country_code: str = None, partner: Any = None) -> str:
        """
        تنظيف رقم الهاتف وتحويله للصيغة الدولية الصريحة (E.164 بدون +)
        يدعم الأرقام المصرية والخليجية وكافة الصيغ الدولية مع كشف بلد الشريك
        """
        if not phone:
            return ""

        # تحويل الأرقام المشرقية (٠-٩) إلى أرقام لاتينية (0-9)
        eastern_digits = '٠١٢٣٤٥٦٧٨٩'
        for i, d in enumerate(eastern_digits):
            phone = str(phone).replace(d, str(i))

        # إزالة كافة الرموز والمسافات
        phone = re.sub(r'[\s\-\(\)\.\+]', '', str(phone).strip())

        if not phone.isdigit():
            return ""

        # استخراج كود الدولة من الشريك إذا كان مسجلاً بدولة معينة
        if partner and not default_country_code:
            partner_country = getattr(partner, 'country', None)
            if partner_country:
                country_code_map = {
                    'EG': '20', 'SA': '966', 'AE': '971', 'KW': '965',
                    'QA': '974', 'OM': '968', 'BH': '973', 'JO': '962',
                    'مصر': '20', 'السعودية': '966', 'الإمارات': '971', 'الكويت': '965'
                }
                c_val = str(partner_country).strip()
                if c_val in country_code_map:
                    default_country_code = country_code_map[c_val]

        if not default_country_code:
            config = cls.get_config()
            default_country_code = config.get("default_country_code", "+20")

        country_prefix = default_country_code.replace("+", "").strip()

        # معالجة الأرقام المصرية الشائعة: 010 / 011 / 012 / 015
        if country_prefix in ("20", ""):
            if phone.startswith("01") and len(phone) == 11:
                return "2" + phone
            if phone.startswith("1") and len(phone) == 10:
                return "20" + phone

        # معالجة أرقام السعودية والخليج (05xxxxxxx -> 9665xxxxxxx)
        if country_prefix == "966":
            if phone.startswith("05") and len(phone) == 10:
                return "966" + phone[1:]

        # معالجة الأرقام الدولية التي تبدأ بصفرين دوليين 00 (0044 -> 44)
        if phone.startswith("00") and len(phone) > 4:
            return phone[2:]

        # إذا كان الرقم يبدأ بصفر محلي، استبدل الصفر بكود الدولة
        if phone.startswith("0") and country_prefix:
            return country_prefix + phone[1:]

        # إذا كان الرقم دولياً بالفعل
        if len(phone) >= 10:
            return phone

        return phone

    @classmethod
    def is_landline(cls, phone: str) -> bool:
        """كشف ما إذا كان الرقم أرضياً لا يدعم الواتساب (مثل أرقام المحافظات المصرية 02 / 03 / ...)"""
        if not phone:
            return False
        raw = re.sub(r'[\s\-\(\)\.\+]', '', str(phone).strip())
        if not raw.isdigit():
            return False
        if raw.startswith("20"):
            raw = raw[2:]
        if raw.startswith("0"):
            raw = raw[1:]

        # الأرقام المحمولة في مصر تبدأ بـ 10, 11, 12, 15 وطولها 10 أرقام (11 مع الصفر الأول)
        if raw.startswith(('10', '11', '12', '15')) and len(raw) == 10:
            return False

        # أكواد المحافظات الأرضية في مصر (2=القاهرة/الجيزة, 3=الإسكندرية, 13=القليوبية, 40=الغربية...)
        landline_prefixes = (
            '2', '3', '13', '40', '45', '46', '47', '48', '50', '55', '57',
            '62', '64', '65', '66', '68', '69', '82', '84', '86', '88', '92', '93', '95', '96', '97'
        )
        if raw.startswith(landline_prefixes) and len(raw) in (7, 8, 9):
            return True
        return False

    @staticmethod
    def isolate_bidi(text: str) -> str:
        """عزل النصوص الرقمية والإنجليزية بـ Unicode BiDi لمنع انعكاس الأرقام والشرطات بالعربية"""
        if not text:
            return ""
        return f"\u200E{text}\u200E"

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """تطهير اسم ملف المرفق لمنع رفض Meta Multipart Upload"""
        if not filename:
            return "Document.pdf"
        # استبدال الشرطات المائلة والمسافات والرموز غير الآمنة
        clean = re.sub(r'[/\\?%*:|"<>#]', '-', filename)
        clean = re.sub(r'\s+', '_', clean)
        if not clean.lower().endswith('.pdf'):
            clean += '.pdf'
        return clean[:80]

    @classmethod
    def _format_num_clean(cls, val: Any) -> str:
        """تنسيق الأرقام مع إزالة العلامة العشرية للأرقام الصحيحة تماماً وفواصل الآلاف"""
        if val is None or val == "":
            return "0"
        try:
            d = Decimal(str(val))
            if d == d.to_integral():
                return f"{int(d):,}"
            else:
                # إذا كان به كسور فعلية تظهر بمنزلتين
                return f"{d:,.2f}"
        except Exception:
            return str(val)

    @classmethod
    def format_currency_amount(cls, amount: Decimal, currency_symbol: str = "ج.م",
                               foreign_amount: Decimal = None, foreign_currency_symbol: str = None) -> str:
        """تنسيق المبالغ المالية بحيث لا يحتوي أي رقم صحيح على أي علامة عشرية نهائياً"""
        if amount is None:
            amount = Decimal("0")
        
        main_str = cls._format_num_clean(amount)
        if foreign_amount and foreign_currency_symbol and foreign_currency_symbol != currency_symbol:
            foreign_str = cls._format_num_clean(foreign_amount)
            return f"{foreign_str} {foreign_currency_symbol} (ما يعادل {main_str} {currency_symbol})"
        return f"{main_str} {currency_symbol}"

    @classmethod
    def get_partner_contact_options(cls, partner: Any) -> List[Dict[str, str]]:
        """استخراج وتفكيك جهات الاتصال المتعددة للشريك (عميل / مورد) كخيارات واضحة"""
        options = []
        if not partner:
            return options

        added_phones = set()

        def add_opt(label: str, raw_phone: str):
            if not raw_phone:
                return
            normalized = cls.normalize_phone(raw_phone)
            if normalized and normalized not in added_phones:
                added_phones.add(normalized)
                is_land = cls.is_landline(raw_phone)
                options.append({
                    "phone": normalized,
                    "raw_phone": raw_phone,
                    "label": f"{label} ({raw_phone})" + (" ⚠️ أرضي" if is_land else ""),
                    "is_landline": is_land
                })

        # 1. الموبايل الأساسي
        for field in ['mobile_phone', 'mobile', 'phone_primary', 'phone', 'phone_number']:
            val = getattr(partner, field, None)
            if val:
                add_opt("رقم الهاتف الأساسي", val)

        # 2. الهاتف الثانوي وهاتف المنزل
        for field in ['phone_secondary', 'home_phone']:
            val = getattr(partner, field, None)
            if val:
                add_opt("رقم الهاتف الثانوي", val)

        # 3. مسؤول التواصل / الحسابات / الطوارئ
        contact_phone = getattr(partner, 'contact_person_phone', None) or getattr(partner, 'emergency_contact_phone', None)
        contact_person = getattr(partner, 'contact_person', None) or getattr(partner, 'emergency_contact_name', None)
        if contact_phone:
            label = f"مسؤول التواصل ({contact_person})" if contact_person else "مسؤول التواصل"
            add_opt(label, contact_phone)

        return options

    # ==================== عمليات الرفع والإرسال لـ Meta Cloud ====================

    @classmethod
    def upload_media(cls, file_bytes: bytes, filename: str, mime_type: str = "application/pdf",
                     account: Any = None, account_id: Optional[int] = None) -> Dict[str, Any]:
        """
        رفع ملف وسائط ثنائي (In-Memory Stream) مباشرة إلى Meta Graph API
        POST /v21.0/{phone_number_id}/media
        """
        if not cls.is_enabled():
            return {"success": False, "error": "خدمة WhatsApp غير مفعلة"}

        config = cls.get_config(account=account, account_id=account_id)
        clean_filename = cls.sanitize_filename(filename)
        url = f"{cls.GRAPH_API_BASE}/{config['phone_number_id']}/media"
        headers = {"Authorization": f"Bearer {config['access_token']}"}

        try:
            session = cls.get_session()
            files = {
                'file': (clean_filename, io.BytesIO(file_bytes), mime_type),
                'type': (None, mime_type),
                'messaging_product': (None, 'whatsapp'),
            }
            response = session.post(url, headers=headers, files=files, timeout=30)
            resp_json = response.json()

            if response.status_code == 200 and "id" in resp_json:
                media_id = resp_json["id"]
                logger.info(f"✅ تم رفع الوسائط لـ Meta بنجاح: {clean_filename} -> Media ID: {media_id}")
                return {"success": True, "media_id": media_id, "filename": clean_filename}

            error_data = resp_json.get("error", {})
            error_code = error_data.get("code")
            error_msg = cls.META_ERROR_GUIDANCE.get(error_code, error_data.get("message", "فشل رفع الملف لـ Meta"))
            logger.error(f"❌ فشل رفع الوسائط لـ Meta ({error_code}): {error_msg}")
            return {"success": False, "error_code": error_code, "error": error_msg}

        except requests.exceptions.Timeout:
            return {"success": False, "error": "انتهت مهلة رفع الملف لسيرفرات Meta (30 ثانية)"}
        except Exception as e:
            logger.exception(f"خطأ غير متوقع أثناء رفع الوسائط لـ Meta: {e}")
            return {"success": False, "error": str(e)}

    @classmethod
    def send_template_message(cls, phone: str, template_name: str, language_code: str = "ar",
                               components: List[Dict[str, Any]] = None, header_media_id: str = None,
                               header_filename: str = "Document.pdf", partner: Any = None,
                               content_object: Any = None, created_by: Any = None,
                               is_custom_phone: bool = False, is_automatic: bool = False,
                               account: Any = None, account_id: Optional[int] = None) -> Dict[str, Any]:
        """
        إرسال رسالة قالب Meta معتمدة مع إدارة قفل التكرار والسجل التدقيقي الآمن ودعم تعدد الحسابات
        POST /v21.0/{phone_number_id}/messages
        """
        if not cls.is_enabled():
            return {"success": False, "error": "خدمة WhatsApp غير مفعلة في إعدادات النظام"}

        # استرجاع الحساب المخصص إذا تم تحديده
        from ..models import WhatsAppAccount
        if account_id and not account:
            account = WhatsAppAccount.objects.filter(id=account_id).exclude(account_status='DISCONNECTED').first()

        normalized_phone = cls.normalize_phone(phone, partner=partner)
        if not normalized_phone:
            return {"success": False, "error": "رقم الهاتف غير صالح"}

        # فحص حالة إلغاء الاشتراك (Opt-Out) إذا كان المستلم عميلاً
        from customer.models import Customer
        from supplier.models import Supplier
        from ..models import WhatsAppMessageLog

        customer_obj = partner if isinstance(partner, Customer) else None
        supplier_obj = partner if isinstance(partner, Supplier) else None

        if customer_obj and customer_obj.whatsapp_opt_out:
            logger.warning(f"تم تخطي الإرسال للعميل {customer_obj.name} لإلغائه الاشتراك (Opt-Out)")
            log = WhatsAppMessageLog.objects.create(
                recipient_phone=normalized_phone,
                recipient_name=customer_obj.name,
                customer=customer_obj,
                template_name=template_name,
                language_code=language_code,
                status='SKIPPED',
                error_message="تم التخطي: العميل ملغي للاشتراك (Opt-Out)",
                created_by=created_by,
                is_automatic=is_automatic
            )
            return {"success": False, "error": "تم تخطي الإرسال لأن العميل قام بإلغاء الاشتراك مسبقاً (Opt-Out)", "log_id": log.id}

        # 1. قفل منع التكرار في الباك إند على مستوى المستند الدقيق (Granular Debounce Lock)
        ct_id = None
        obj_id = None
        if content_object and hasattr(content_object, 'pk'):
            from django.contrib.contenttypes.models import ContentType
            try:
                ct_id = ContentType.objects.get_for_model(content_object).id
                obj_id = content_object.pk
            except Exception:
                pass

        if ct_id and obj_id:
            lock_key = f"wa_send_lock_{normalized_phone}_{template_name}_{ct_id}_{obj_id}"
        else:
            lock_key = f"wa_send_lock_{normalized_phone}_{template_name}"

        if cache.get(lock_key) or not cache.add(lock_key, "locked", timeout=15):
            return {"success": False, "error": "جاري إرسال نفس الرسالة لهذا الرقم بالفعل، يرجى الانتظار بضع ثوانٍ"}

        config = cls.get_config()
        token = account.decrypted_access_token if (account and account.decrypted_access_token) else config.get('access_token')
        phone_id = account.phone_number_id if (account and account.phone_number_id) else config.get('phone_number_id')

        if not token or not phone_id:
            return {"success": False, "error": "بيانات اعتماد WhatsApp API (Access Token / Phone Number ID) غير مهيأة"}

        url = f"{cls.GRAPH_API_BASE}/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # تجهيز مكونات القالب وتطهير نصوص المتغيرات آلياً
        payload_components = []
        if components:
            for comp in components:
                clean_comp = dict(comp)
                if "parameters" in clean_comp:
                    clean_params = []
                    for p in clean_comp["parameters"]:
                        p_copy = dict(p)
                        if p_copy.get("type") == "text" and "text" in p_copy:
                            p_copy["text"] = cls.clean_template_variable(p_copy["text"])
                        clean_params.append(p_copy)
                    clean_comp["parameters"] = clean_params
                payload_components.append(clean_comp)

        # إذا وجد مرفق PDF في الهيدر
        has_media = bool(header_media_id)
        if header_media_id:
            payload_components.insert(0, {
                "type": "header",
                "parameters": [{
                    "type": "document",
                    "document": {
                        "id": header_media_id,
                        "filename": cls.sanitize_filename(header_filename)
                    }
                }]
            })

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalized_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": "en_US" if template_name == "hello_world" else language_code},
            }
        }
        if payload_components and template_name != "hello_world":
            payload["template"]["components"] = payload_components

        # استخراج المرجع النصي الدائم للمستند
        doc_ref_text = ""
        if content_object:
            try:
                num = getattr(content_object, 'number', '') or getattr(content_object, 'reference_number', '')
                doc_title = getattr(content_object._meta, 'verbose_name', 'مستند')
                doc_ref_text = f"{doc_title} #{num}" if num else str(content_object)
            except Exception:
                doc_ref_text = str(content_object)

        # استرجاع الحساب الافتراضي إذا لم يتم تمرير حساب محدد
        if not account:
            account = WhatsAppAccount.objects.filter(is_default=True).exclude(account_status='DISCONNECTED').first()

        # إنشاء سجل مبدئي بحالة PENDING
        recipient_display_name = getattr(partner, 'name', '') if partner else ''
        log = WhatsAppMessageLog(
            account=account,
            recipient_phone=normalized_phone,
            recipient_name=recipient_display_name,
            is_custom_phone=is_custom_phone,
            customer=customer_obj,
            supplier=supplier_obj,
            template_name=template_name,
            language_code=language_code,
            has_media=has_media,
            media_id=header_media_id,
            document_reference_text=doc_ref_text[:250],
            status='PENDING',
            created_by=created_by,
            is_automatic=is_automatic,
        )
        if content_object and ct_id and obj_id:
            log.content_type_id = ct_id
            log.object_id = obj_id
        log.save()

        try:
            session = cls.get_session()
            response = session.post(url, headers=headers, json=payload, timeout=10)
            resp_json = response.json()

            # إذا فشل الإرسال بسبب عدم تطابق الهيدر (132001 أو 100)، نعيد المحاولة تلقائياً بدون مكون الهيدر
            if response.status_code not in (200, 201) and has_media and any(c.get('type') == 'header' for c in payload_components):
                logger.warning("إعادة محاولة إرسال القالب بدون مكون Header لتفادي عدم تطابق بنية القالب في Meta...")
                body_only_components = [c for c in payload_components if c.get('type') != 'header']
                fallback_payload = dict(payload)
                if body_only_components:
                    fallback_payload["template"]["components"] = body_only_components
                else:
                    fallback_payload["template"].pop("components", None)
                retry_resp = session.post(url, headers=headers, json=fallback_payload, timeout=10)
                if retry_resp.status_code in (200, 201):
                    response = retry_resp
                    resp_json = retry_resp.json()

            if response.status_code in (200, 201) and "messages" in resp_json:
                msg_info = resp_json["messages"][0]
                wamid = msg_info.get("id")
                
                # تحديث السجل بنجاح الإرسال لـ Meta
                log.update_status_safely('SENT', message_id=wamid)
                logger.info(f"✅ تم تسليم رسالة القالب '{template_name}' لـ Meta بنجاح -> wamid: {wamid}")

                # إرسال ملف PDF الثنائي كرسالة وسائط منفصلة لضمان استلام المستند
                if has_media and header_media_id:
                    try:
                        doc_payload = {
                            "messaging_product": "whatsapp",
                            "recipient_type": "individual",
                            "to": normalized_phone,
                            "type": "document",
                            "document": {
                                "id": header_media_id,
                                "filename": cls.sanitize_filename(header_filename)
                            }
                        }
                        session.post(url, headers=headers, json=doc_payload, timeout=10)
                    except Exception as doc_err:
                        logger.warning(f"تعذر إرسال مرفق الـ PDF المنفصل: {doc_err}")

                return {"success": True, "message_id": wamid, "log_id": log.id}

            # استخراج ومعالجة الخطأ
            error_data = resp_json.get("error", {})
            error_code = error_data.get("code")
            raw_msg = error_data.get("error_user_msg") or error_data.get("message", "")
            error_subcode = error_data.get("error_subcode")
            guidance = cls.META_ERROR_GUIDANCE.get(error_code)

            sub_str = f" [Subcode {error_subcode}]" if error_subcode else ""
            if guidance and raw_msg and raw_msg != guidance:
                error_msg = f"{guidance} ({raw_msg}){sub_str}"
            else:
                error_msg = f"{guidance or raw_msg or 'خطأ Meta'}{sub_str} (كود {error_code})"

            log.update_status_safely('FAILED', error_code=str(error_code), error_message=error_msg)
            logger.error(f"❌ فشل إرسال رسالة القالب '{template_name}' ({error_code}): {error_msg}")
            return {"success": False, "error_code": error_code, "error": error_msg, "log_id": log.id}

        except requests.exceptions.Timeout:
            error_msg = "انتهت مهلة الاتصال بسيرفرات Meta (10 ثوانٍ)"
            log.update_status_safely('FAILED', error_code='TIMEOUT', error_message=error_msg)
            return {"success": False, "error": error_msg, "log_id": log.id}
        except Exception as e:
            logger.exception(f"خطأ غير متوقع أثناء إرسال رسالة الواتساب: {e}")
            log.update_status_safely('FAILED', error_code='EXCEPTION', error_message=str(e))
            return {"success": False, "error": str(e), "log_id": log.id}

    # ==================== إرسال الرسائل النصية الحرة وإدارة نافذة الـ 24 ساعة (Phase 4 Live Chat) ====================

    @classmethod
    def get_conversation_window_status(cls, phone: str, account_id: Optional[int] = None) -> Dict[str, Any]:
        """
        فحص حالة نافذة خدمة العملاء (24-Hour Customer Service Window)
        تحسب التوقيت المتبقي بالثواني والصيغة البشرية بناءً على آخر رسالة واردة INBOUND
        """
        from datetime import timedelta
        from ..models import WhatsAppMessageLog
        normalized_phone = cls.normalize_phone(phone)
        if not normalized_phone:
            return {
                "is_open": False,
                "seconds_remaining": 0,
                "formatted_remaining": "رقم غير صالح",
                "last_inbound_at": None,
                "expires_at": None,
            }

        qs = WhatsAppMessageLog.objects.filter(
            recipient_phone=normalized_phone,
            direction='INBOUND'
        )
        if account_id:
            qs = qs.filter(account_id=account_id)

        last_inbound = qs.order_by('-created_at').first()
        if not last_inbound:
            # تحقق من كاش الجلسة كـ Fallback
            cache_ts = cache.get(f"wa_24h_session_{normalized_phone}")
            if cache_ts:
                try:
                    from django.utils.dateparse import parse_datetime
                    dt = parse_datetime(cache_ts)
                    if dt:
                        exp = dt + timedelta(hours=24)
                        now = timezone.now()
                        secs = max(0, int((exp - now).total_seconds()))
                        if secs > 0:
                            h, rem = divmod(secs, 3600)
                            m, s = divmod(rem, 60)
                            return {
                                "is_open": True,
                                "seconds_remaining": secs,
                                "formatted_remaining": f"{h:02d}:{m:02d}:{s:02d}",
                                "last_inbound_at": dt.isoformat(),
                                "expires_at": exp.isoformat(),
                            }
                except Exception:
                    pass

            return {
                "is_open": False,
                "seconds_remaining": 0,
                "formatted_remaining": "منتهية",
                "last_inbound_at": None,
                "expires_at": None,
            }

        now = timezone.now()
        expires_at = last_inbound.created_at + timedelta(hours=24)
        seconds_remaining = max(0, int((expires_at - now).total_seconds()))
        is_open = seconds_remaining > 0

        if is_open:
            h, rem = divmod(seconds_remaining, 3600)
            m, s = divmod(rem, 60)
            formatted = f"{h:02d}:{m:02d}:{s:02d}"
        else:
            formatted = "منتهية"

        return {
            "is_open": is_open,
            "seconds_remaining": seconds_remaining,
            "formatted_remaining": formatted,
            "last_inbound_at": last_inbound.created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

    @classmethod
    def send_text_message(cls, phone: str, text: str, account: Any = None,
                          account_id: Optional[int] = None, created_by: Any = None,
                          bypass_window_check: bool = False) -> Dict[str, Any]:
        """
        إرسال رسالة نصية حرة (Freeform Text Message) داخل نافذة خدمة العملاء الـ 24 ساعة
        POST /v21.0/{phone_number_id}/messages
        """
        if not text or not str(text).strip():
            return {"success": False, "error": "نص الرسالة لا يمكن أن يكون فارغاً"}

        if not cls.is_enabled():
            return {"success": False, "error": "خدمة WhatsApp غير مفعلة في إعدادات النظام"}

        normalized_phone = cls.normalize_phone(phone)
        if not normalized_phone:
            return {"success": False, "error": "رقم الهاتف غير صالح"}

        # 1. التحقق من صلاحية نافذة الـ 24 ساعة
        window_status = cls.get_conversation_window_status(normalized_phone, account_id=account_id)
        if not window_status["is_open"] and not bypass_window_check:
            return {
                "success": False,
                "window_expired": True,
                "error": "انتهت صلاحية نافذة خدمة العملاء (24-Hour Window). يلزم إرسال قالب معتمد لدى Meta لإعادة فتح المحادثة.",
            }

        # 2. استرجاع الحساب والتشفير
        from ..models import WhatsAppAccount, WhatsAppMessageLog
        if account_id and not account:
            account = WhatsAppAccount.objects.filter(id=account_id).exclude(account_status='DISCONNECTED').first()
        if not account:
            account = WhatsAppAccount.objects.filter(is_default=True).exclude(account_status='DISCONNECTED').first()

        config = cls.get_config()
        token = account.decrypted_access_token if (account and account.decrypted_access_token) else config.get('access_token')
        phone_id = account.phone_number_id if (account and account.phone_number_id) else config.get('phone_number_id')

        if not token or not phone_id:
            return {"success": False, "error": "بيانات اعتماد WhatsApp API غير مهيأة"}

        # مطابقة الشريك
        customer_obj, supplier_obj, partner_display_name = cls.match_partner_by_phone(normalized_phone)

        # قفل منع التكرار اللحظي
        lock_key = f"wa_send_lock_text_{normalized_phone}"
        if cache.get(lock_key) or not cache.add(lock_key, "locked", timeout=5):
            return {"success": False, "error": "جاري إرسال رسالة لهذا الرقم بالفعل، يرجى الانتظار ثانية واحدة"}

        url = f"{cls.GRAPH_API_BASE}/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        clean_text = str(text).strip()
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalized_phone,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": clean_text
            }
        }

        log = WhatsAppMessageLog(
            account=account,
            recipient_phone=normalized_phone,
            recipient_name=partner_display_name,
            customer=customer_obj,
            supplier=supplier_obj,
            direction='OUTBOUND_ERP',
            sent_via='SYSTEM',
            message_type='text',
            body_text=clean_text[:2000],
            status='PENDING',
            created_by=created_by,
            assigned_user=created_by,
        )
        log.save()

        try:
            session = cls.get_session()
            response = session.post(url, headers=headers, json=payload, timeout=10)
            resp_json = response.json()

            if response.status_code in (200, 201) and "messages" in resp_json:
                msg_info = resp_json["messages"][0]
                wamid = msg_info.get("id")
                log.update_status_safely('SENT', message_id=wamid)
                logger.info(f"✅ تم إرسال الرسالة النصية لـ Meta بنجاح -> wamid: {wamid}")
                return {
                    "success": True,
                    "message_id": wamid,
                    "log_id": log.id,
                    "message": "تم إرسال الرسالة بنجاح ✅"
                }

            error_data = resp_json.get("error", {})
            error_code = error_data.get("code")
            raw_msg = error_data.get("error_user_msg") or error_data.get("message", "")
            guidance = cls.META_ERROR_GUIDANCE.get(error_code)
            error_msg = f"{guidance or raw_msg or 'خطأ Meta'} (كود {error_code})"

            log.update_status_safely('FAILED', error_code=str(error_code), error_message=error_msg)
            logger.error(f"❌ فشل إرسال الرسالة النصية ({error_code}): {error_msg}")
            return {"success": False, "error_code": error_code, "error": error_msg, "log_id": log.id}

        except requests.exceptions.Timeout:
            error_msg = "انتهت مهلة الاتصال بسيرفرات Meta (10 ثوانٍ)"
            log.update_status_safely('FAILED', error_code='TIMEOUT', error_message=error_msg)
            return {"success": False, "error": error_msg, "log_id": log.id}
        except Exception as e:
            logger.exception(f"خطأ غير متوقع أثناء إرسال الرسالة النصية: {e}")
            log.update_status_safely('FAILED', error_code='EXCEPTION', error_message=str(e))
            return {"success": False, "error": str(e), "log_id": log.id}


    # ==================== إرسال رسالة اختبارية لحظية ====================

    @classmethod
    def send_test_message(cls, phone: str, template_name: str = None) -> Dict[str, Any]:
        """
        إرسال رسالة اختبارية لحظية عبر WhatsApp Business Cloud API
        """
        from ..models import SystemSetting
        target_template = template_name or "document_share_ar"
        site_name = SystemSetting.get_site_name()

        # بناء المعاملات بناءً على نوع القالب
        components = []
        if target_template in ("document_share_ar", "document_send_ar", "document_send_en", "document_share_en"):
            components = [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": "عميلنا التجريبي"},
                    {"type": "text", "text": "INV-TEST-001"},
                    {"type": "text", "text": "100 ج.م"},
                    {"type": "text", "text": site_name[:50]},
                ]
            }]
        elif target_template in ("payment_receipt_ar", "payment_receipt_en"):
            components = [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": "عميلنا التجريبي"},
                    {"type": "text", "text": "100 ج.م"},
                    {"type": "text", "text": "REC-TEST-001"},
                    {"type": "text", "text": "الرصيد المتبقي: صفر ج.م"},
                    {"type": "text", "text": site_name[:50]},
                ]
            }]
        elif target_template in ("order_status_ar", "order_status_en"):
            components = [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": "عميلنا التجريبي"},
                    {"type": "text", "text": "SO-TEST-001"},
                    {"type": "text", "text": "تم استلام الطلب وتأكيد الجاهزية"},
                    {"type": "text", "text": site_name[:50]},
                ]
            }]
        elif target_template == "welcome_new_customer":
            components = [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": "عميلنا التجريبي"}
                ]
            }]
        elif target_template in ("otp_code", "otp_auth_code"):
            components = [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": "123456"}]
                },
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [{"type": "text", "text": "123456"}]
                }
            ]

        return cls.send_template_message(
            phone=phone,
            template_name=target_template,
            language_code="ar",
            components=components,
            is_custom_phone=True,
            is_automatic=False
        )

    # ==================== فحص الاتصال وجودة الرقم وتوليد التوكن ====================

    @classmethod
    def test_connection(cls, access_token: str = None, phone_number_id: str = None, waba_id: str = None, account_id: Optional[int] = None) -> Dict[str, Any]:
        """
        فحص الاتصال الحي بسيرفرات Meta واسترجاع:
        - حالة التوكن وصلاحيته
        - اسم العرض المعتمد (Verified Name)
        - تقييم جودة الرقم (Quality Rating)
        - مستوى الـ Tier وسقف الرسائل اليومي
        - زمن الاستجابة (Latency ms)
        """
        from ..models import WhatsAppAccount
        account = None
        if account_id:
            account = WhatsAppAccount.objects.filter(id=account_id).first()

        config = cls.get_config()
        token = access_token.strip() if access_token else (account.decrypted_access_token if (account and account.decrypted_access_token) else config.get("access_token"))
        phone_id = phone_number_id.strip() if phone_number_id else (account.phone_number_id if (account and account.phone_number_id) else config.get("phone_number_id"))
        waba = waba_id.strip() if waba_id else (account.waba_id if (account and account.waba_id) else config.get("waba_id"))

        if not token or not phone_id:
            return {"success": False, "message": "يرجى إدخال Access Token و Phone Number ID للاختبار"}

        url = f"{cls.GRAPH_API_BASE}/{phone_id}"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"fields": "display_phone_number,verified_name,quality_rating,messaging_limit_tier,code_verification_status,status,platform_type,throughput,name_status,new_name_status"}

        import time
        start_time = time.time()

        try:
            session = cls.get_session()
            response = session.get(url, headers=headers, params=params, timeout=10)
            latency_ms = int((time.time() - start_time) * 1000)
            resp_json = response.json()

            if response.status_code == 200:
                display_phone = resp_json.get("display_phone_number", phone_id)
                verified_name = resp_json.get("verified_name", "غير محدد")
                quality = resp_json.get("quality_rating", "UNKNOWN")
                status = resp_json.get("status", resp_json.get("code_verification_status", "CONNECTED"))
                raw_tier = resp_json.get("messaging_limit_tier", "TIER_250")
                raw_name_status = resp_json.get("name_status", "UNKNOWN")
                new_name_status = resp_json.get("new_name_status")

                # تحديث بيانات الحساب في قاعدة البيانات إذا كان فحص حساب محدد
                if account:
                    try:
                        account.verified_name = verified_name
                        account.display_phone_number = display_phone
                        if quality in ('GREEN', 'YELLOW', 'RED', 'UNKNOWN'):
                            account.quality_rating = quality
                        if status in ('CONNECTED', 'RESTRICTED', 'FLAGGED', 'BLOCKED'):
                            account.account_status = status
                        account.save(update_fields=['verified_name', 'display_phone_number', 'quality_rating', 'account_status', 'updated_at'])
                    except Exception as db_err:
                        logger.warning(f"Failed to update WhatsAppAccount live diagnostics: {db_err}")

                # ترجمة حالة اسم العرض
                name_status_map = {
                    "APPROVED": ("معتمد رسمياً ✅", "success"),
                    "AVAILABLE_WITHOUT_REVIEW": ("متاح ومفعل", "success"),
                    "PENDING_REVIEW": ("قيد مراجعة فريق Meta ⏳", "warning"),
                    "DECLINED": ("مرفوض من Meta ❌ (راجع شروط تطابق الاسم)", "danger"),
                    "EXPIRED": ("منتهي الصلاحية ⚠️", "secondary"),
                    "NON_EXISTS": ("غير مسجل", "secondary"),
                }
                name_status_display, name_status_badge = name_status_map.get(raw_name_status, (raw_name_status, "info"))

                # ترجمة تقييم الجودة
                quality_map = {
                    "GREEN": ("ممتاز (Green 🟢)", "success"),
                    "YELLOW": ("متوسط (Yellow 🟡)", "warning"),
                    "RED": ("منخفض - خطر حظر (Red 🔴)", "danger"),
                    "UNKNOWN": ("قيد التقييم", "secondary")
                }
                quality_display, quality_badge = quality_map.get(quality, (quality, "info"))

                # خريطة حدود التراسل اليومي (Daily Messaging Limits)
                tier_map = {
                    "TIER_50": ("50 عميل فريد / 24 ساعة", 50),
                    "TIER_250": ("250 عميل فريد / 24 ساعة (المستوى التجريبي)", 250),
                    "TIER_1K": ("المستوى 1 (1,000 عميل فريد / 24 ساعة)", 1000),
                    "TIER_10K": ("المستوى 2 (10,000 عميل فريد / 24 ساعة)", 10000),
                    "TIER_100K": ("المستوى 3 (100,000 عميل فريد / 24 ساعة)", 100000),
                    "TIER_UNLIMITED": ("المستوى 4 (تراسل غير محدود يومياً)", 999999999),
                }
                tier_display, tier_limit = tier_map.get(raw_tier, (raw_tier, 250))

                return {
                    "success": True,
                    "message": f"متصل بنجاح مع Meta Cloud API ✅ ({latency_ms}ms) | حالة الاسم: {name_status_display}",
                    "display_phone": display_phone,
                    "verified_name": verified_name,
                    "raw_name_status": raw_name_status,
                    "name_status_display": name_status_display,
                    "name_status_badge": name_status_badge,
                    "new_name_status": new_name_status,
                    "raw_quality": quality,
                    "quality_rating": quality_display,
                    "quality_badge": quality_badge,
                    "status": status,
                    "raw_tier": raw_tier,
                    "tier_info": tier_display,
                    "tier_limit": tier_limit,
                    "latency_ms": latency_ms
                }

            error_data = resp_json.get("error", {})
            error_code = error_data.get("code")
            error_msg = cls.META_ERROR_GUIDANCE.get(error_code, error_data.get("message", "فشل فحص الاتصال مع Meta"))
            return {"success": False, "message": error_msg, "error_code": error_code, "latency_ms": latency_ms}

        except requests.exceptions.Timeout:
            return {"success": False, "message": "انتهت مهلة الاتصال بسيرفرات Meta (10 ثوانٍ)"}
        except Exception as e:
            return {"success": False, "message": f"خطأ في الاتصال: {str(e)}"}

    SYSTEM_DEFAULT_TEMPLATES = [
        {
            "name": "document_share_ar",
            "status": "APPROVED",
            "category": "UTILITY",
            "language": "ar",
            "components": [
                {"type": "HEADER", "format": "DOCUMENT"},
                {"type": "BODY", "text": "مرحباً بك أ/ {{1}}، تم إصدار مستند جديد لحسابكم وهو {{2}} بقيمة {{3}}، وتجدون كافة التفاصيل بالملف المرفق. شكراً لتعاملكم مع {{4}} ويسعدنا دائماً خدمتكم."},
            ]
        },
        {
            "name": "payment_receipt_ar",
            "status": "APPROVED",
            "category": "UTILITY",
            "language": "ar",
            "components": [
                {"type": "HEADER", "format": "DOCUMENT"},
                {"type": "BODY", "text": "مرحباً بك أ/ {{1}}، تم استلام وتسجيل دفعة مالية بقيمة {{2}} بموجب سند رقم {{3}}، ورصيدكم المتبقي {{4}}. شكراً لتعاملكم مع {{5}} ويسعدنا خدمتكم."},
            ]
        },
        {
            "name": "order_status_ar",
            "status": "APPROVED",
            "category": "UTILITY",
            "language": "ar",
            "components": [
                {"type": "BODY", "text": "مرحباً بك أ/ {{1}}، نود إحاطتكم بتحديث حالة الطلب رقم {{2}} حيث أصبحت: {{3}}. شكراً لتعاملكم مع {{4}} ويسعدنا خدمتكم دائماً."},
            ]
        },
        {
            "name": "otp_auth_code",
            "status": "APPROVED",
            "category": "AUTHENTICATION",
            "language": "ar",
            "components": [
                {"type": "BODY", "add_security_recommendation": True},
                {"type": "BUTTONS", "buttons": [{"type": "OTP", "otp_type": "COPY_CODE", "text": "Copy Code"}]}
            ]
        }
    ]

    @classmethod
    def sync_templates_with_meta(cls) -> Dict[str, Any]:
        """
        مزامنة حية مع Meta Graph API لجلب القوالب المعتمدة مع تشخيص كامل للمصدر والحالة
        GET /v21.0/{waba_id}/message_templates
        """
        config = cls.get_config()
        token = config.get("access_token")
        waba_id = config.get("waba_id")

        if not token:
            return {
                "success": False,
                "source": "local_blueprint",
                "count": len(cls.SYSTEM_DEFAULT_TEMPLATES),
                "templates": cls.SYSTEM_DEFAULT_TEMPLATES,
                "message": "رمز الوصول الدائم (Access Token) غير مدخل. تم تحميل المخطط المعياري المحلي للنظام.",
            }

        if not waba_id:
            return {
                "success": False,
                "source": "local_blueprint",
                "count": len(cls.SYSTEM_DEFAULT_TEMPLATES),
                "templates": cls.SYSTEM_DEFAULT_TEMPLATES,
                "message": "معرف حساب واتساب للأعمال (WABA ID) غير مدخل في التبويب الأول. أدخل WABA ID للمزامنة الحية مباشرة من Meta.",
            }

        url = f"{cls.GRAPH_API_BASE}/{waba_id}/message_templates"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"fields": "name,status,language,category,components", "limit": 100}

        try:
            session = cls.get_session()
            response = session.get(url, headers=headers, params=params, timeout=10)
            resp_json = response.json()

            if response.status_code == 200:
                raw_templates = resp_json.get("data", [])
                approved_count = sum(1 for t in raw_templates if t.get("status") in ("APPROVED", "ACTIVE", "Active - Quality pending"))
                return {
                    "success": True,
                    "source": "meta_cloud_api",
                    "count": len(raw_templates),
                    "approved_count": approved_count,
                    "waba_id": waba_id,
                    "templates": raw_templates or cls.SYSTEM_DEFAULT_TEMPLATES,
                    "message": f"تمت المزامنة الحية بنجاح من Meta Business Manager (WABA ID: {waba_id})! تم جلب {len(raw_templates)} قالب ({approved_count} معتمد).",
                }

            error_data = resp_json.get("error", {})
            error_code = error_data.get("code")
            error_msg = cls.META_ERROR_GUIDANCE.get(error_code, error_data.get("message", "فشل جلب القوالب من Meta"))
            return {
                "success": False,
                "source": "local_blueprint",
                "count": len(cls.SYSTEM_DEFAULT_TEMPLATES),
                "templates": cls.SYSTEM_DEFAULT_TEMPLATES,
                "error_code": error_code,
                "message": f"تعذر الاتصال بـ Meta ({error_code}): {error_msg}. تم تحميل المخطط المعياري المحلي.",
            }

        except Exception as e:
            return {
                "success": False,
                "source": "local_blueprint",
                "count": len(cls.SYSTEM_DEFAULT_TEMPLATES),
                "templates": cls.SYSTEM_DEFAULT_TEMPLATES,
                "message": f"خطأ غير متوقع أثناء المزامنة مع Meta: {str(e)}",
            }

    @classmethod
    def get_resumable_upload_handle(cls, file_bytes: bytes, filename: str = "sample.pdf", mime_type: str = "application/pdf") -> Optional[str]:
        """
        رفع عينة مستند إلى Meta Resumable Upload API للحصول على header_handle لاعتماد القوالب ذات المرفقات
        POST /v21.0/{app_id}/uploads -> POST /v21.0/{upload_id} -> returns "h" handle
        """
        config = cls.get_config()
        token = config.get("access_token")
        app_id = config.get("app_id")
        if not token:
            return None

        # استخراج app_id آلياً إذا لم يكن مسجلاً
        if not app_id:
            try:
                debug_res = cls.get_session().get(
                    f"{cls.GRAPH_API_BASE}/debug_token",
                    params={"input_token": token, "access_token": token},
                    timeout=10
                )
                if debug_res.status_code == 200:
                    app_id = debug_res.json().get("data", {}).get("app_id")
            except Exception:
                pass

        if not app_id:
            logger.warning("Meta Resumable Upload: تعذر تحديد App ID لاستخراج Header Handle")
            return None

        try:
            session = cls.get_session()
            session_url = f"{cls.GRAPH_API_BASE}/{app_id}/uploads"
            init_res = session.post(
                session_url,
                params={
                    "file_length": len(file_bytes),
                    "file_type": mime_type,
                    "access_token": token
                },
                timeout=15
            )
            if init_res.status_code != 200:
                logger.warning(f"Meta Upload Session init failed ({init_res.status_code}): {init_res.text}")
                return None

            upload_session_id = init_res.json().get("id")
            if not upload_session_id:
                return None

            upload_url = f"{cls.GRAPH_API_BASE}/{upload_session_id}"
            upload_headers = {
                "Authorization": f"OAuth {token}",
                "file_offset": "0",
                "Content-Type": "application/octet-stream"
            }
            upload_res = session.post(upload_url, headers=upload_headers, data=file_bytes, timeout=30)
            if upload_res.status_code == 200:
                handle = upload_res.json().get("h")
                logger.info(f"✅ تم استخراج Meta Header Handle بنجاح: {handle}")
                return handle
            else:
                logger.warning(f"Meta Upload binary chunk failed: {upload_res.text}")
                return None

        except Exception as e:
            logger.exception(f"Exception during Meta Resumable Upload: {e}")
            return None

    @classmethod
    def create_system_templates_on_meta(cls) -> Dict[str, Any]:
        """
        إنشاء واعتماد القوالب الأساسية للنظام مباشرة على خوادم Meta Graph API بضغطة واحدة:
        POST /v21.0/{waba_id}/message_templates
        """
        config = cls.get_config()
        token = config.get("access_token")
        waba_id = config.get("waba_id")

        if not token or not waba_id:
            return {
                "success": False,
                "message": "يرجى التأكد من حفظ رمز الوصول (Access Token) ومعرف WABA ID أولاً في التبويب الأول."
            }

        url = f"{cls.GRAPH_API_BASE}/{waba_id}/message_templates"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # توليد عينة PDF صغيرة واستخراج handle لها من Meta
        sample_pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF"
        header_handle = cls.get_resumable_upload_handle(sample_pdf, filename="Document_Sample.pdf")

        header_component = {
            "type": "HEADER",
            "format": "DOCUMENT"
        }
        if header_handle:
            header_component["example"] = {
                "header_handle": [header_handle]
            }

        templates_payload = [
            {
                "name": "document_share_ar",
                "language": "ar",
                "category": "UTILITY",
                "allow_category_change": True,
                "components": [
                    header_component,
                    {
                        "type": "BODY",
                        "text": "مرحباً بك أ/ {{1}}، تم إصدار مستند جديد لحسابكم وهو {{2}} بقيمة {{3}}، وتجدون كافة التفاصيل بالملف المرفق. شكراً لتعاملكم مع {{4}} ويسعدنا دائماً خدمتكم.",
                        "example": {
                            "body_text": [
                                ["أحمد علي", "فاتورة مبيعات INV-2026-001", "1500 ج.م", "موهبة"]
                            ]
                        }
                    }
                ]
            },
            {
                "name": "payment_receipt_ar",
                "language": "ar",
                "category": "UTILITY",
                "allow_category_change": True,
                "components": [
                    header_component,
                    {
                        "type": "BODY",
                        "text": "مرحباً بك أ/ {{1}}، تم استلام وتسجيل دفعة مالية بقيمة {{2}} بموجب سند رقم {{3}}، ورصيدكم المتبقي {{4}}. شكراً لتعاملكم مع {{5}} ويسعدنا خدمتكم.",
                        "example": {
                            "body_text": [
                                ["أحمد علي", "5000 ج.م", "REC-2026-001", "صفر ج.م", "MEGroup"]
                            ]
                        }
                    }
                ]
            },
            {
                "name": "order_status_ar",
                "language": "ar",
                "category": "UTILITY",
                "allow_category_change": True,
                "components": [
                    {
                        "type": "BODY",
                        "text": "مرحباً بك أ/ {{1}}، نود إحاطتكم بتحديث حالة الطلب رقم {{2}} حيث أصبحت: {{3}}. شكراً لتعاملكم مع {{4}} ويسعدنا خدمتكم دائماً.",
                        "example": {
                            "body_text": [
                                ["أحمد علي", "PO-2026-001", "تم التجهيز والشحن", "MEGroup"]
                            ]
                        }
                    }
                ]
            }
        ]

        results = []
        session = cls.get_session()

        # جلب القوالب الحالية المسجلة في Meta لمعرفة معرفاتها وحالاتها وهيكلها
        existing_map = {}
        try:
            get_res = session.get(url, headers=headers, params={"fields": "id,name,status,language,components", "limit": 100}, timeout=10)
            if get_res.status_code == 200:
                for t in get_res.json().get("data", []):
                    if t.get("language") == "ar":
                        existing_map[t.get("name")] = t
        except Exception:
            pass

        for tpl in templates_payload:
            name = tpl["name"]
            existing_tpl = existing_map.get(name)

            # فحص إذا كان القالب الحالي في Meta ينقصه الـ Header Document المطلوب
            needs_recreate = False
            if existing_tpl:
                has_req_header = any(c.get("type") == "HEADER" for c in tpl.get("components", []))
                existing_has_header = any(c.get("type") == "HEADER" for c in existing_tpl.get("components", []))
                if has_req_header and not existing_has_header:
                    # القالب مسجل قديماً كنص فقط بدون هيدر ملف، نقوم بحذفه وإعادة إنشائه بالهيدر المعتمد
                    logger.info(f"إعادة بناء القالب {name} على Meta لإضافة رأس المستند (Header Document)...")
                    try:
                        del_res = session.delete(url, headers=headers, params={"name": name}, timeout=10)
                        logger.info(f"Meta delete old template {name}: {del_res.status_code}")
                    except Exception as del_err:
                        logger.warning(f"Failed to delete old template {name}: {del_err}")
                    needs_recreate = True

            # إذا كان القالب مسجلاً بالفعل ومطابق للهيكل
            if existing_tpl and not needs_recreate:
                tpl_id = existing_tpl.get("id")
                tpl_status = existing_tpl.get("status", "APPROVED")
                results.append({"name": name, "success": True, "already_exists": True, "id": tpl_id, "status": tpl_status, "message": f"مسجل ومطابق في Meta بحالة ({tpl_status}) 👍"})
                continue

            # إنشاء القالب الجديد بهيكله المعتمد
            try:
                res = session.post(url, headers=headers, json=tpl, timeout=15)
                res_data = res.json()
                if res.status_code in (200, 201):
                    tpl_id = res_data.get("id")
                    tpl_status = res_data.get("status", "APPROVED")
                    results.append({"name": name, "success": True, "id": tpl_id, "status": tpl_status, "message": "تم إنشاء واعتماد القالب مع رأس المستند على Meta بنجاح ✅"})
                else:
                    err_info = res_data.get("error", {})
                    err_msg = err_info.get("error_user_msg") or err_info.get("message", "فشل الإنشاء")
                    err_code = err_info.get("code")
                    err_subcode = err_info.get("error_subcode")
                    if any(w in err_msg.lower() for w in ("already", "exist", "duplicate")) or err_subcode in (2388024, 2388017, 2388040):
                        results.append({"name": name, "success": True, "already_exists": True, "message": "مسجل بالفعل في حساب Meta وجاهز للاستخدام 👍"})
                    else:
                        sub_info = f" (Subcode: {err_subcode})" if err_subcode else ""
                        results.append({"name": name, "success": False, "message": f"خطأ Meta ({err_code}{sub_info}): {err_msg}"})
            except Exception as e:
                results.append({"name": name, "success": False, "message": f"خطأ اتصال: {str(e)}"})

        success_count = sum(1 for r in results if r["success"])
        return {
            "success": success_count > 0,
            "results": results,
            "message": f"تمت معالجة القوالب بنجاح ({success_count} من {len(templates_payload)} جاهز ومسجل في Meta) ✅"
        }

    @classmethod
    def get_approved_templates(cls) -> List[Dict[str, Any]]:
        """جلب ومزامنة قائمة القوالب المعتمدة من Meta وفحص عدد متغيراتها مع fallback للقوالب الأربعة"""
        sync_res = cls.sync_templates_with_meta()
        return sync_res.get("templates", cls.SYSTEM_DEFAULT_TEMPLATES)

    @classmethod
    def send_test_message(cls, phone: str, template_name: str = None) -> Dict[str, Any]:
        """إرسال رسالة تجريبية فورية مع تجربة القوالب المعتمدة المتاحة بأقصى سرعة"""
        if not phone:
            return {"success": False, "error": "يرجى إدخال رقم هاتف المستلم"}

        from ..models import SystemSetting
        site_name = SystemSetting.get_site_name()

        # إذا حدد المستخدم قالباً معيناً نلتزم به، وإلا نجرب القوالب المعتمدة فوراً
        if template_name:
            candidates = [template_name]
        else:
            candidates = ["welcome_new_customer", "document_share_ar", "document_send_ar", "payment_receipt_ar", "visit", "hello_world"]

        last_res = None
        for tpl_name in candidates:
            if tpl_name == "welcome_new_customer":
                lang = "ar"
                components = [{
                    "type": "body",
                    "parameters": [{"type": "text", "parameter_name": "customer_name", "text": "عميلنا العزيز"}]
                }]
            elif tpl_name == "visit":
                lang = "ar"
                components = []
            elif tpl_name == "hello_world":
                lang = "en_US"
                components = []
            elif tpl_name in ("otp_code", "otp_auth_code"):
                lang = "ar"
                components = [{"type": "body", "parameters": [{"type": "text", "text": "123456"}]}]
            else:
                lang = "ar"
                components = [{
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": "عميلنا العزيز"},
                        {"type": "text", "text": cls.isolate_bidi("TEST-2026-001")},
                        {"type": "text", "text": "1,500 ج.م"},
                        {"type": "text", "text": site_name[:50]},
                    ]
                }]

            res = cls.send_template_message(
                phone=phone,
                template_name=tpl_name,
                language_code=lang,
                components=components,
                is_automatic=False
            )

            if res.get("success"):
                res["message"] = f"تم إرسال الرسالة التجريبية بنجاح عبر القالب المعتمد ({tpl_name})! ✅"
                return res

            last_res = res
            # إذا كان الخطأ خارج أخطاء عدم توفر القالب أو متغيراته، نرجع الخطأ فوراً
            if res.get("error_code") not in (100, 132000, 132001, 132005, 132015):
                return res

        return last_res or {"success": False, "error": "تعذر إرسال الرسالة التجريبية عبر القوالب المتاحة"}

    # ==================== محرك الإرسال المزدوج (Dual-Engine Execution) ====================

    @classmethod
    def send_async(cls, **kwargs):
        """
        إرسال غير متزامن يدعم المحرك المزدوج (Dual-Engine):
        1. يحاول إدراج المهمة في Celery Queue 'notifications'.
        2. في حال عدم توفر البروكر أو حدوث OperationalError، يتحول تلقائياً لـ Daemon Thread.
        """
        try:
            from ..tasks.whatsapp_tasks import send_whatsapp_task
            send_whatsapp_task.delay(**kwargs)
            logger.info("WhatsApp async: تم إدراج المهمة في طابور Celery بنجاح")
            return True
        except Exception as e:
            logger.warning(f"WhatsApp Celery broker unavailable ({e}) -> التحول الفوري للـ Daemon Thread")
            thread = threading.Thread(target=cls._run_thread_dispatch, kwargs=kwargs, daemon=True)
            thread.start()
            return True

    @classmethod
    def _run_thread_dispatch(cls, **kwargs):
        """تنفيذ الإرسال في خيط معالجة خلفي مستقل مع إغلاق اتصالات قاعدة البيانات تلقائياً لمنع تسريب الـ DB Connections"""
        from django.db import connections
        try:
            cls.send_template_message(**kwargs)
        except Exception as e:
            logger.exception(f"خطأ في خيط المعالجة الخلفي للواتساب: {e}")
        finally:
            try:
                connections.close_all()
            except Exception:
                pass

    # ==================== إدارة مفاتيح تفعيل الـ 49 مستند في الكاش ====================

    @classmethod
    def get_document_triggers(cls) -> Dict[str, bool]:
        """جلب حالة تفعيل الـ 49 مستند من الكاش الموحد في 0ms"""
        cached = cache.get("whatsapp_document_triggers")
        if cached is not None:
            return cached

        from ..models import SystemSetting
        triggers_json = SystemSetting.get_setting("whatsapp_document_triggers", {})
        if isinstance(triggers_json, str):
            try:
                import json
                triggers_json = json.loads(triggers_json)
            except Exception:
                triggers_json = {}

        # القيمة الافتراضية: الفواتير والإيصالات وسندات الصرف مفعلة تلقائياً
        defaults = {
            "sale_invoice": True,
            "quotation": True,
            "sales_order": True,
            "delivery_note": True,
            "sale_return": True,
            "payment_receipt": True,
            "credit_note": True,
            "purchase_order": True,
            "payment_voucher": True,
            "stock_transfer": True,
            "payroll_slip": True,
            "otp_code": True,
        }
        merged = {**defaults, **triggers_json}
        cache.set("whatsapp_document_triggers", merged, timeout=86400)
        return merged

    @classmethod
    def set_document_trigger(cls, doc_key: str, is_enabled: bool) -> bool:
        """تحديث حالة تفعيل مستند معين في الكاش و SystemSetting بشكل ذري وسريع"""
        from ..models import SystemSetting
        import json
        triggers = cls.get_document_triggers()
        triggers[doc_key] = bool(is_enabled)

        # تحديث الكاش أولاً للاستجابة الفورية في 0ms
        cache.set("whatsapp_document_triggers", triggers, timeout=86400)

        # حفظ دائم في SystemSetting
        setting, _ = SystemSetting.objects.get_or_create(
            key="whatsapp_document_triggers",
            defaults={"value": json.dumps(triggers), "data_type": "json", "group": "whatsapp", "is_active": True}
        )
        setting.value = json.dumps(triggers)
        setting.data_type = "json"
        setting.save()
        return True

    # ==================== محرك المعاينة الحية للقوالب والبيانات الواقعية ====================

    @classmethod
    def get_template_preview_text(cls, template_name: str, doc_display: str = None) -> Dict[str, Any]:
        """توليد نص المعاينة الواقعية ومحاكاة شكل الرسالة على هاتف العميل بناءً على القالب والمستند المختار"""
        try:
            from ..models import SystemSetting
            site_name = SystemSetting.get_site_name() or "موهبة ERP"
        except Exception:
            site_name = "موهبة ERP"

        doc_title = doc_display.strip() if doc_display else "مستند معتمد"

        # تفصيل النصوص الواقعية حسب نوع القالب والمستند المحدد
        if template_name in ("document_share_ar", "document_send_ar", "document_send_en", "document_share_en"):
            raw_text = "مرحباً بك أ/ {{1}}، تم إصدار مستند جديد لحسابكم وهو {{2}} بقيمة {{3}}، وتجدون كافة التفاصيل بالملف المرفق. شكراً لتعاملكم مع {{4}} ويسعدنا دائماً خدمتكم."
            mock_text = f"مرحباً بك أ/ شركة الأمل للتجارة والمقاولات، تم إصدار مستند جديد لحسابكم وهو {doc_title} برقم INV-2026-0042 بقيمة 15,450 ج.م، وتجدون كافة التفاصيل بالملف المرفق. شكراً لتعاملكم مع {site_name} ويسعدنا دائماً خدمتكم."
            return {
                "title": f"معاينة {doc_title}",
                "template_name": template_name,
                "category": "UTILITY",
                "has_pdf": True,
                "doc_title": doc_title,
                "pdf_filename": f"{doc_title.replace(' ', '_')}_INV-0042.pdf",
                "raw_text": raw_text,
                "mock_text": mock_text,
                "rendered_text": mock_text,
                "variables": [
                    {"code": "{{1}}", "name": "اسم الشريك / المستلم", "example": "شركة الأمل للتجارة والمقاولات"},
                    {"code": "{{2}}", "name": "نوع ورقم المستند", "example": f"{doc_title} برقم INV-2026-0042"},
                    {"code": "{{3}}", "name": "القيمة الإجمالية", "example": "15,450 ج.م"},
                    {"code": "{{4}}", "name": "اسم المنشأة", "example": site_name},
                ]
            }

        elif template_name in ("payment_receipt_ar", "payment_receipt_en"):
            raw_text = "مرحباً بك أ/ {{1}}، تم استلام وتسجيل دفعة مالية بقيمة {{2}} بموجب سند رقم {{3}}، ورصيدكم المتبقي {{4}}. شكراً لتعاملكم مع {{5}} ويسعدنا خدمتكم."
            mock_text = f"مرحباً بك أ/ م. محمود عبد العزيز، تم تسجيل {doc_title} بقيمة 5,000 ج.م بموجب إيصال رقم REC-2026-0089، ورصيدكم المتبقي 10,450 ج.م. شكراً لتعاملكم مع {site_name} ويسعدنا خدمتكم."
            return {
                "title": f"معاينة {doc_title}",
                "template_name": template_name,
                "category": "UTILITY",
                "has_pdf": False,
                "doc_title": doc_title,
                "raw_text": raw_text,
                "mock_text": mock_text,
                "rendered_text": mock_text,
                "variables": [
                    {"code": "{{1}}", "name": "اسم الشريك / المستلم", "example": "م. محمود عبد العزيز"},
                    {"code": "{{2}}", "name": "المبلغ المالي", "example": "5,000 ج.م"},
                    {"code": "{{3}}", "name": "رقم السند / الإيصال", "example": "REC-2026-0089"},
                    {"code": "{{4}}", "name": "الرصيد المتبقي بعد الحركة", "example": "10,450 ج.م"},
                    {"code": "{{5}}", "name": "اسم المنشأة", "example": site_name},
                ]
            }

        elif template_name in ("order_status_ar", "order_status_en"):
            raw_text = "مرحباً بك أ/ {{1}}، نود إحاطتكم بتحديث حالة الطلب رقم {{2}} حيث أصبحت: {{3}}. شكراً لتعاملكم مع {{4}} ويسعدنا خدمتكم دائماً."
            mock_text = f"مرحباً بك أ/ شركة النور الحديثة، نود إحاطتكم بشأن {doc_title} (رقم SO-2026-0155) حيث أصبحت حالته: معتمد وجاهز للتنفيذ. شكراً لتعاملكم مع {site_name} ويسعدنا خدمتكم دائماً."
            return {
                "title": f"معاينة {doc_title}",
                "template_name": template_name,
                "category": "UTILITY",
                "has_pdf": False,
                "doc_title": doc_title,
                "raw_text": raw_text,
                "mock_text": mock_text,
                "rendered_text": mock_text,
                "variables": [
                    {"code": "{{1}}", "name": "اسم المستلم", "example": "شركة النور الحديثة"},
                    {"code": "{{2}}", "name": "رقم الطلب / العملية", "example": f"{doc_title} #SO-2026-0155"},
                    {"code": "{{3}}", "name": "الحالة الجديدة للعملية", "example": "معتمد وجاهز للتنفيذ"},
                    {"code": "{{4}}", "name": "اسم المنشأة", "example": site_name},
                ]
            }

        elif template_name == "welcome_new_customer":
            raw_text = "مرحباً بك أ/ {{customer_name}} في منصتنا، يسعدنا انضمامك لعملاء {{company_name}} ونحن في خدمتك دائماً."
            mock_text = f"مرحباً بك أ/ أحمد إبراهيم في منصتنا، يسعدنا انضمامك لعملاء {site_name} ونحن في خدمتك دائماً."
            return {
                "title": f"معاينة {doc_title}",
                "template_name": template_name,
                "category": "MARKETING",
                "has_pdf": False,
                "doc_title": doc_title,
                "raw_text": raw_text,
                "mock_text": mock_text,
                "rendered_text": mock_text,
                "variables": [
                    {"code": "{{customer_name}}", "name": "اسم العميل المسجل", "example": "أحمد إبراهيم"},
                    {"code": "{{company_name}}", "name": "اسم المنشأة", "example": site_name},
                ]
            }

        elif template_name in ("otp_code", "otp_auth_code"):
            raw_text = "رمز التحقق الخاص بحسابك في النظام هو: {{1}}. الرمز صالح لمدة 10 دقائق. لا تشارك هذا الرمز مع أي شخص."
            mock_text = "رمز التحقق الخاص بحسابك في النظام هو: 849201. الرمز صالح لمدة 10 دقائق. لا تشارك هذا الرمز مع أي شخص."
            return {
                "title": f"معاينة {doc_title}",
                "template_name": template_name,
                "category": "AUTHENTICATION",
                "has_pdf": False,
                "doc_title": doc_title,
                "raw_text": raw_text,
                "mock_text": mock_text,
                "rendered_text": mock_text,
                "variables": [
                    {"code": "{{1}}", "name": "رمز التحقق (6 أرقام)", "example": "849201"},
                ]
            }

        elif template_name == "visit":
            raw_text = "مرحباً بك، نود تذكيركم بموعد الزيارة / الاجتماع المحدد معكم. ويسعدنا دائماً خدمتكم."
            mock_text = f"مرحباً بك، نود تذكيركم بموعد الزيارة / الاجتماع المحدد معكم من فريق {site_name}. ويسعدنا دائماً خدمتكم."
            return {
                "title": f"معاينة {doc_title}",
                "template_name": template_name,
                "category": "UTILITY",
                "has_pdf": False,
                "doc_title": doc_title,
                "raw_text": raw_text,
                "mock_text": mock_text,
                "rendered_text": mock_text,
                "variables": []
            }

        else:
            raw_text = "إشعار رسمي من النظام لحسابكم."
            mock_text = f"مرحباً بكم، إشعار رسمي من {site_name} بشأن {doc_title} لحسابكم. ويسعدنا دائماً خدمتكم."
            return {
                "title": f"معاينة {doc_title}",
                "template_name": template_name,
                "category": "UTILITY",
                "has_pdf": False,
                "doc_title": doc_title,
                "raw_text": raw_text,
                "mock_text": mock_text,
                "rendered_text": mock_text,
                "variables": []
            }

    # ==================== فحص التوقيع HMAC للـ Webhook ====================

    @classmethod
    def verify_webhook_signature(cls, payload_bytes: bytes, signature_header: str) -> bool:
        """
        التحقق الصارم من توقيع X-Hub-Signature-256 لمنع تزوير إشعارات الـ Webhook
        """
        if not signature_header or not signature_header.startswith("sha256="):
            return False

        config = cls.get_config()
        app_secret = config.get("app_secret")
        if not app_secret:
            logger.warning("WhatsApp Webhook: App Secret غير مهيأ للتحقق من التوقيع")
            return False

        expected_sig = signature_header.split("sha256=")[1].strip()
        calculated_sig = hmac.new(
            app_secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected_sig, calculated_sig)

    # ==================== تنزيل الوسائط ومطابقة الشركاء للـ Coexistence ====================

    @classmethod
    def match_partner_by_phone(cls, phone: str) -> Tuple[Optional[Any], Optional[Any], str]:
        """
        مطابقة رقم الهاتف بدقة مع العملاء والموردين
        يرجع (customer_obj, supplier_obj, display_name)
        """
        if not phone:
            return None, None, ""

        from django.db.models import Q
        normalized = cls.normalize_phone(phone)
        from customer.models import Customer
        from supplier.models import Supplier

        # 1. البحث في العملاء
        last_9 = normalized[-9:] if len(normalized) >= 9 else normalized
        cust_q = (
            Q(phone__icontains=last_9) |
            Q(phone_primary__icontains=last_9) |
            Q(phone_secondary__icontains=last_9)
        )
        customer = Customer.objects.filter(cust_q).first()
        if customer:
            return customer, None, customer.name

        # 2. البحث في الموردين
        supp_q = (
            Q(phone__icontains=last_9) |
            Q(secondary_phone__icontains=last_9) |
            Q(whatsapp__icontains=last_9)
        )
        supplier = Supplier.objects.filter(supp_q).first()
        if supplier:
            return None, supplier, supplier.name

        return None, None, ""

    @classmethod
    def download_inbound_media(cls, media_id: str, mime_type: str = None) -> Optional[Tuple[bytes, str]]:
        """
        تنزيل ملف وسائط وارد من خوادم Meta Graph API وحفظه في الذاكرة
        GET /v21.0/{media_id} -> GET url
        """
        if not cls.is_enabled() or not media_id:
            return None

        config = cls.get_config()
        token = config.get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{cls.GRAPH_API_BASE}/{media_id}"

        try:
            session = cls.get_session()
            meta_res = session.get(url, headers=headers, timeout=15)
            if meta_res.status_code != 200:
                logger.error(f"WhatsApp Media Download: فشل جلب رابط الميديا ({media_id}): {meta_res.text}")
                return None

            data = meta_res.json()
            download_url = data.get("url")
            raw_mime = data.get("mime_type") or mime_type or "application/octet-stream"

            if not download_url:
                return None

            # تنزيل الملف الفعلي
            bin_res = session.get(download_url, headers=headers, timeout=30)
            if bin_res.status_code != 200:
                logger.error(f"WhatsApp Media Download: فشل تنزيل الملف الثنائي: {bin_res.status_code}")
                return None

            ext_map = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp",
                "application/pdf": ".pdf",
                "audio/ogg": ".ogg",
                "audio/mpeg": ".mp3",
                "audio/mp4": ".m4a",
                "video/mp4": ".mp4",
                "text/plain": ".txt",
            }
            clean_mime = raw_mime.split(';')[0].strip().lower()
            ext = ext_map.get(clean_mime, ".bin")
            filename = f"wa_{media_id[:12]}_{timezone.now().strftime('%Y%m%d%H%M%S')}{ext}"
            return bin_res.content, filename

        except Exception as e:
            logger.exception(f"WhatsApp Media Download Exception: {e}")
            return None

