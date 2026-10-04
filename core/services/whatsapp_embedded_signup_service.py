# -*- coding: utf-8 -*-
"""
خدمة التسجيل المضمن وإدارة حسابات مزود الحلول التكنولوجية (Meta Tech Provider Embedded Signup)
MWHEBA ERP — Production-Grade Embedded Signup & Onboarding Service
"""
import logging
import requests
from typing import Dict, Any, Optional
from django.conf import settings
from django.db import transaction

from ..models import WhatsAppAccount, SystemSetting
from .whatsapp_service import WhatsAppService

logger = logging.getLogger('core.services.whatsapp.embedded_signup')


class WhatsAppEmbeddedSignupService:
    """
    محرك التسجيل المضمن التلقائي بنقرة واحدة (1-Click Embedded Signup)
    والربط اليدوي المباشر مع دعم التشفير والتعايش المتوازي (Coexistence)
    """

    @classmethod
    def exchange_code_for_token(cls, code: str, app_id: str = None, app_secret: str = None) -> Dict[str, Any]:
        """
        استبدال كود المصادقة قصير الأجل (OAuth Code) بتوكن وصول دائم
        GET /v21.0/oauth/access_token
        """
        if not code:
            return {"success": False, "error": "كود المصادقة مفقود"}

        if not app_id:
            app_id = SystemSetting.get_setting("whatsapp_app_id", "").strip() or getattr(settings, 'WHATSAPP_APP_ID', '').strip()
        if not app_secret:
            app_secret = SystemSetting.get_setting("whatsapp_app_secret", "").strip() or getattr(settings, 'WHATSAPP_APP_SECRET', '').strip()

        if not app_id or not app_secret:
            return {"success": False, "error": "معرف التطبيق (App ID) أو السر (App Secret) غير مهيأ في النظام"}

        url = f"{WhatsAppService.GRAPH_API_BASE}/oauth/access_token"
        params = {
            "client_id": app_id,
            "client_secret": app_secret,
            "code": code,
        }

        try:
            session = WhatsAppService.get_session()
            response = session.get(url, params=params, timeout=15)
            data = response.json()

            if response.status_code == 200 and "access_token" in data:
                return {
                    "success": True,
                    "access_token": data["access_token"],
                    "token_type": data.get("token_type", "bearer"),
                    "raw_response": data
                }
            else:
                error_info = data.get("error", {})
                error_msg = error_info.get("message", "فشل استبدال كود المصادقة")
                logger.error(f"Embedded Signup OAuth Code Exchange Failed: {error_msg} | Data: {data}")
                return {"success": False, "error": error_msg, "raw_error": error_info}
        except Exception as exc:
            logger.exception("Exception during Embedded Signup OAuth Code Exchange")
            return {"success": False, "error": str(exc)}

    @classmethod
    def subscribe_app_to_waba(cls, waba_id: str, access_token: str) -> Dict[str, Any]:
        """
        ربط واشتراك تطبيق الـ ERP بـ Webhooks حساب WABA لاستلام الإشعارات
        POST /v21.0/{waba_id}/subscribed_apps
        """
        if not waba_id or not access_token:
            return {"success": False, "error": "بيانات WABA ID أو Access Token غير متوفرة"}

        url = f"{WhatsAppService.GRAPH_API_BASE}/{waba_id}/subscribed_apps"
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            session = WhatsAppService.get_session()
            response = session.post(url, headers=headers, timeout=15)
            data = response.json()

            if response.status_code == 200 and data.get("success"):
                return {"success": True, "data": data}
            else:
                error_msg = data.get("error", {}).get("message", "فشل الاشتراك في أحداث WABA")
                logger.warning(f"Subscribed Apps Warning: {error_msg} | Data: {data}")
                return {"success": False, "error": error_msg, "data": data}
        except Exception as exc:
            logger.exception("Exception during subscribed_apps registration")
            return {"success": False, "error": str(exc)}

    @classmethod
    def get_phone_number_details(cls, phone_number_id: str, access_token: str) -> Dict[str, Any]:
        """
        الاستعلام عن تفاصيل رقم الهاتف من Meta (الاسم المعتمد، الجودة، والرقم الظاهر)
        GET /v21.0/{phone_number_id}?fields=display_phone_number,verified_name,quality_rating,code_verification_status
        """
        if not phone_number_id or not access_token:
            return {"success": False, "error": "بيانات Phone Number ID أو Access Token غير متوفرة"}

        url = f"{WhatsAppService.GRAPH_API_BASE}/{phone_number_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {
            "fields": "display_phone_number,verified_name,quality_rating,code_verification_status,status"
        }

        try:
            session = WhatsAppService.get_session()
            response = session.get(url, headers=headers, params=params, timeout=15)
            data = response.json()

            if response.status_code == 200:
                return {
                    "success": True,
                    "display_phone_number": data.get("display_phone_number", ""),
                    "verified_name": data.get("verified_name", ""),
                    "quality_rating": data.get("quality_rating", "GREEN"),
                    "status": data.get("status", "CONNECTED"),
                    "data": data
                }
            else:
                error_msg = data.get("error", {}).get("message", "فشل جلب تفاصيل رقم الهاتف")
                return {"success": False, "error": error_msg}
        except Exception as exc:
            logger.exception("Exception fetching phone number details from Meta")
            return {"success": False, "error": str(exc)}

    @classmethod
    def register_phone_number_safely(cls, phone_number_id: str, access_token: str,
                                      pin: str = "123456", is_coexistence: bool = True) -> Dict[str, Any]:
        """
        تسجيل الرقم السحابي مع الحماية التامة لجلسة تطبيق الموبايل (Coexistence Registration Guard)
        في وضع التعايش (is_coexistence=True) يتم تخطي تسجيل الـ PIN نهائياً لمنع قطع جلسة الهاتف
        """
        if is_coexistence:
            logger.info(f"Coexistence Mode Active for phone {phone_number_id}: Skipping PIN registration to preserve mobile app session.")
            return {
                "success": True,
                "skipped": True,
                "message": "تم تخطي تسجيل الـ PIN للحفاظ على جلسة تطبيق الموبايل (وضع التعايش المتوازي)"
            }

        if not phone_number_id or not access_token:
            return {"success": False, "error": "بيانات رقم الهاتف أو التوكن غير مكتملة"}

        url = f"{WhatsAppService.GRAPH_API_BASE}/{phone_number_id}/register"
        headers = {"Authorization": f"Bearer {access_token}"}
        payload = {
            "messaging_product": "whatsapp",
            "pin": pin
        }

        try:
            session = WhatsAppService.get_session()
            response = session.post(url, headers=headers, json=payload, timeout=15)
            data = response.json()

            if response.status_code == 200 and data.get("success"):
                return {"success": True, "skipped": False, "data": data}
            else:
                error_msg = data.get("error", {}).get("message", "فشل تسجيل الرقم السحابي")
                return {"success": False, "error": error_msg, "data": data}
        except Exception as exc:
            logger.exception("Exception during phone registration")
            return {"success": False, "error": str(exc)}

    @classmethod
    @transaction.atomic
    def complete_onboarding(cls, phone_number_id: str, access_token: str, waba_id: str = "",
                            app_id: str = "", account_name: str = "", company_name: str = "",
                            is_coexistence: bool = True, is_default: bool = False,
                            notes: str = "") -> Dict[str, Any]:
        """
        إكمال عملية الربط الشاملة وحفظ حساب WhatsAppAccount مشفراً في قاعدة البيانات
        مع مزامنة تفاصيل الرقم من Meta والاشتراك في أحداث الـ Webhook
        """
        if not phone_number_id or not access_token:
            return {"success": False, "error": "معرف رقم الهاتف ورمز الوصول مطلوبان"}

        # 1. الاستعلام عن تفاصيل الرقم من Meta
        phone_meta = cls.get_phone_number_details(phone_number_id, access_token)
        display_phone = phone_meta.get("display_phone_number", "")
        verified_name = phone_meta.get("verified_name", "")
        quality_rating = phone_meta.get("quality_rating", "GREEN")
        account_status = 'CONNECTED' if phone_meta.get("success") else 'CONNECTED'

        # 2. الاشتراك في أحداث Webhooks للـ WABA إن توفر
        if waba_id:
            cls.subscribe_app_to_waba(waba_id, access_token)

        # 3. التحقق والتسجيل الآمن
        cls.register_phone_number_safely(phone_number_id, access_token, is_coexistence=is_coexistence)

        # 4. حفظ أو تحديث الحساب مشفراً بـ AES-256
        account, created = WhatsAppAccount.objects.get_or_create(
            phone_number_id=phone_number_id,
            defaults={
                "name": account_name or verified_name or display_phone or f"حساب {phone_number_id}",
                "company_name": company_name or verified_name,
                "waba_id": waba_id,
                "display_phone_number": display_phone,
                "verified_name": verified_name,
                "app_id": app_id,
                "is_coexistence": is_coexistence,
                "is_default": is_default,
                "account_status": account_status,
                "quality_rating": quality_rating,
                "daily_limit_tier": 'TIER_250' if is_coexistence else 'TIER_1K',
                "notes": notes,
            }
        )

        account.access_token = access_token
        if account_name:
            account.name = account_name
        if company_name:
            account.company_name = company_name
        if waba_id:
            account.waba_id = waba_id
        if display_phone:
            account.display_phone_number = display_phone
        if verified_name:
            account.verified_name = verified_name
        if app_id:
            account.app_id = app_id
        account.is_coexistence = is_coexistence
        if is_default:
            account.is_default = True
        account.account_status = account_status
        account.quality_rating = quality_rating
        account.save()

        # تفريغ كاش الجلسة لإعادة البناء الفوري بالحساب الجديد
        WhatsAppService.reset_session()

        return {
            "success": True,
            "created": created,
            "account_id": account.id,
            "account": account,
            "message": "تم ربط وتشفير حساب الواتساب بنجاح"
        }
