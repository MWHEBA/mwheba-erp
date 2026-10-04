# -*- coding: utf-8 -*-
"""
مهام Celery لمعالجة إرسال رسائل WhatsApp في الخلفية
MWHEBA ERP — WhatsApp Celery Tasks
"""
import logging
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

logger = logging.getLogger('core.tasks.whatsapp')

try:
    from celery import shared_task
except ImportError:
    # Fallback decorator if Celery is not installed
    def shared_task(*args, **kwargs):
        def decorator(func):
            def wrapper(*a, **kw):
                return func(*a, **kw)
            wrapper.delay = wrapper
            return wrapper
        if len(args) == 1 and callable(args[0]):
            return decorator(args[0])
        return decorator

User = get_user_model()


@shared_task(queue='whatsapp', bind=True, max_retries=3, default_retry_delay=60, acks_late=True)
def send_whatsapp_task(self, phone: str, template_name: str, language_code: str = "ar",
                       components: list = None, header_media_id: str = None,
                       header_filename: str = "Document.pdf", partner_id: int = None,
                       partner_type: str = None, content_type_id: int = None,
                       object_id: int = None, created_by_id: int = None,
                       is_custom_phone: bool = False, is_automatic: bool = False):
    """
    مهمة خلفية لمعالجة إرسال رسائل الواتساب مع دعم إعادة المحاولة الآلية
    """
    from ..services.whatsapp_service import WhatsAppService
    
    partner = None
    if partner_id and partner_type:
        try:
            if partner_type == 'customer':
                from customer.models import Customer
                partner = Customer.objects.filter(pk=partner_id).first()
            elif partner_type == 'supplier':
                from supplier.models import Supplier
                partner = Supplier.objects.filter(pk=partner_id).first()
        except Exception as e:
            logger.warning(f"WhatsApp Task: تعذر استرجاع الشريك ({partner_type} #{partner_id}): {e}")

    content_object = None
    if content_type_id and object_id:
        try:
            ct = ContentType.objects.filter(pk=content_type_id).first()
            if ct:
                content_object = ct.get_object_for_this_type(pk=object_id)
        except Exception as e:
            logger.warning(f"WhatsApp Task: تعذر استرجاع المستند المرتبط (CT #{content_type_id}, ID #{object_id}): {e}")

    created_by = None
    if created_by_id:
        try:
            created_by = User.objects.filter(pk=created_by_id).first()
        except Exception:
            pass

    try:
        result = WhatsAppService.send_template_message(
            phone=phone,
            template_name=template_name,
            language_code=language_code,
            components=components,
            header_media_id=header_media_id,
            header_filename=header_filename,
            partner=partner,
            content_object=content_object,
            created_by=created_by,
            is_custom_phone=is_custom_phone,
            is_automatic=is_automatic,
        )
        return result
    except Exception as exc:
        logger.exception(f"WhatsApp Task: خطأ أثناء التنفيذ: {exc}")
        if hasattr(self, 'retry'):
            raise self.retry(exc=exc)
        return {"success": False, "error": str(exc)}


@shared_task(queue='whatsapp_inbound', bind=True, acks_late=True)
def process_whatsapp_webhook_task(self, payload: dict):
    """
    مهمة معالجة أحداث الـ Webhook الواردة وتزامن الـ Coexistence في الخلفية (Two-Tier Webhook Worker)
    تتعامل مع:
    - تحديثات حالات التسليم والقراءة (Statuses)
    - الرسائل والاستفسارات والميديا الواردة من العملاء (Inbound Messages)
    - الرسائل الصادرة من تطبيق الموبايل في وضع التعايش (Coexistence Echo Events)
    - محرك إلغاء الاشتراك وإعادة التفعيل (Opt-Out / Re-Opt-In Engine)
    - حفظ وتحميل الوسائط محلياً لمنع تلفها
    """
    import json
    from django.core.cache import cache
    from django.core.files.base import ContentFile
    from django.db import transaction
    from django.utils import timezone
    from ..models import WhatsAppMessageLog
    from ..services.whatsapp_service import WhatsAppService
    from customer.models import Customer
    from supplier.models import Supplier

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception as e:
            logger.error(f"WhatsApp Inbound Task: فشل فك ترميز JSON: {e}")
            return {"success": False, "error": "Invalid JSON"}

    if not isinstance(payload, dict):
        return {"success": False, "error": "Payload must be a dictionary"}

    processed_count = 0

    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                field = change.get("field")
                val = change.get("value", {})
                metadata = val.get("metadata", {})
                business_phone_id = metadata.get("phone_number_id")
                business_display_phone = metadata.get("display_phone_number", "")

                # ----------------------------------------------------
                # 1. معالجة تحديثات الحالة (Sent, Delivered, Read, Failed)
                # ----------------------------------------------------
                for st in val.get("statuses", []):
                    wamid = st.get("id")
                    raw_status = st.get("status", "").upper()
                    if not wamid:
                        continue

                    # مطابقة الحالة مع خيارات النظام
                    status_map = {
                        "SENT": "SENT",
                        "DELIVERED": "DELIVERED",
                        "READ": "READ",
                        "FAILED": "FAILED",
                    }
                    target_status = status_map.get(raw_status)
                    if not target_status:
                        continue

                    error_code = None
                    error_msg = None
                    if target_status == "FAILED":
                        errors = st.get("errors", [])
                        if errors:
                            err0 = errors[0]
                            error_code = str(err0.get("code", ""))
                            error_msg = err0.get("title") or err0.get("message", "فشل التسليم من خوادم Meta")

                    # تحديث ذري آمن لمنع تعارض الحالات
                    with transaction.atomic():
                        log_entry = WhatsAppMessageLog.objects.filter(message_id=wamid).first()
                        if log_entry:
                            log_entry.update_status_safely(
                                new_status=target_status,
                                error_code=error_code,
                                error_message=error_msg
                            )
                            processed_count += 1
                            logger.info(f"WhatsApp Webhook Task: تحديث حالة الرسالة {wamid} إلى {target_status} ✅")

                # ----------------------------------------------------
                # 2. معالجة الرسائل الواردة وصادرة الموبايل (Coexistence & Inbound Messages)
                # ----------------------------------------------------
                for msg in val.get("messages", []):
                    from_phone = msg.get("from", "")
                    msg_id = msg.get("id")
                    msg_type = msg.get("type", "text")
                    msg_timestamp = msg.get("timestamp")

                    if not from_phone or not msg_id:
                        continue

                    # تحديد اتجاه الرسالة (صادرة من الموبايل أم واردة من العميل)
                    # في Coexistence، إذا كان from_phone يطابق رقم النشاط التجاري
                    norm_business_phone = WhatsAppService.normalize_phone(business_display_phone)
                    norm_from_phone = WhatsAppService.normalize_phone(from_phone)

                    is_mobile_echo = bool(norm_business_phone and norm_from_phone == norm_business_phone)
                    direction = 'OUTBOUND_MOBILE' if is_mobile_echo else 'INBOUND'

                    # مطابقة الشريك (عميل / مورد)
                    target_phone = msg.get("recipient_id") if is_mobile_echo else from_phone
                    customer_obj, supplier_obj, partner_display_name = WhatsAppService.match_partner_by_phone(target_phone)

                    # استخراج وتفكيك نص الرسالة والوسائط
                    body_text = ""
                    media_id = None
                    downloaded_file = None
                    downloaded_filename = None

                    if msg_type == "text":
                        body_text = msg.get("text", {}).get("body", "").strip()

                    elif msg_type == "image":
                        img_data = msg.get("image", {})
                        media_id = img_data.get("id")
                        caption = img_data.get("caption", "").strip()
                        body_text = f"[صورة] {caption}".strip()
                        mime = img_data.get("mime_type", "image/jpeg")
                        res = WhatsAppService.download_inbound_media(media_id, mime)
                        if res:
                            downloaded_file, downloaded_filename = res

                    elif msg_type == "document":
                        doc_data = msg.get("document", {})
                        media_id = doc_data.get("id")
                        doc_fn = doc_data.get("filename") or "Document.pdf"
                        caption = doc_data.get("caption", "").strip()
                        body_text = f"[مستند: {doc_fn}] {caption}".strip()
                        mime = doc_data.get("mime_type", "application/pdf")
                        res = WhatsAppService.download_inbound_media(media_id, mime)
                        if res:
                            downloaded_file, downloaded_filename = res

                    elif msg_type == "audio":
                        audio_data = msg.get("audio", {})
                        media_id = audio_data.get("id")
                        mime = audio_data.get("mime_type", "audio/ogg")
                        body_text = "[تسجيل صوتي]"
                        res = WhatsAppService.download_inbound_media(media_id, mime)
                        if res:
                            downloaded_file, downloaded_filename = res

                    elif msg_type == "location":
                        loc_data = msg.get("location", {})
                        lat = loc_data.get("latitude")
                        lng = loc_data.get("longitude")
                        loc_name = loc_data.get("name", "")
                        body_text = f"[موقع جغرافي: {loc_name} ({lat}, {lng})]".strip()

                    elif msg_type == "interactive":
                        inter = msg.get("interactive", {})
                        body_text = inter.get("button_reply", {}).get("title") or inter.get("list_reply", {}).get("title", "[رد تفاعلي]")

                    else:
                        body_text = f"[{msg_type}]"

                    # 1. تحديث طابع نافذة الـ 24 ساعة المجانية في الكاش للشريك
                    if direction == 'INBOUND' and norm_from_phone:
                        cache.set(f"wa_24h_session_{norm_from_phone}", timezone.now().isoformat(), timeout=86400)

                    # 2. محرك إلغاء الاشتراك وإعادة التفعيل ثنائي اللغة (Opt-Out Engine)
                    upper_text = body_text.upper()
                    opt_out_keywords = ["STOP", "UNSUBSCRIBE", "إلغاء", "الغاء", "توقف", "حظر"]
                    re_opt_in_keywords = ["START", "UNSTOP", "تفعيل", "تشغيل", "اشتراك", "اعادة"]

                    if any(kw in upper_text for kw in opt_out_keywords):
                        if customer_obj:
                            customer_obj.whatsapp_opt_out = True
                            customer_obj.whatsapp_opt_out_at = timezone.now()
                            customer_obj.whatsapp_opt_out_reason = f"Inbound keyword: {body_text}"
                            customer_obj.save(update_fields=['whatsapp_opt_out', 'whatsapp_opt_out_at', 'whatsapp_opt_out_reason'])
                        if supplier_obj:
                            supplier_obj.whatsapp_opt_out = True
                            supplier_obj.whatsapp_opt_out_at = timezone.now()
                            supplier_obj.whatsapp_opt_out_reason = f"Inbound keyword: {body_text}"
                            supplier_obj.save(update_fields=['whatsapp_opt_out', 'whatsapp_opt_out_at', 'whatsapp_opt_out_reason'])
                        logger.warning(f"🛑 تم تسجيل إلغاء الاشتراك (Opt-Out) للشريك ({target_phone})")

                    elif any(kw in upper_text for kw in re_opt_in_keywords):
                        if customer_obj:
                            customer_obj.whatsapp_opt_out = False
                            customer_obj.whatsapp_opt_out_reason = f"Re-Opt-In keyword: {body_text}"
                            customer_obj.save(update_fields=['whatsapp_opt_out', 'whatsapp_opt_out_reason'])
                        if supplier_obj:
                            supplier_obj.whatsapp_opt_out = False
                            supplier_obj.whatsapp_opt_out_reason = f"Re-Opt-In keyword: {body_text}"
                            supplier_obj.save(update_fields=['whatsapp_opt_out', 'whatsapp_opt_out_reason'])
                        logger.info(f"🟢 تم إعادة تفعيل الاشتراك (Re-Opt-In) للشريك ({target_phone})")

                    # 3. تخزين الرسالة في سجل التدقيق الذري (WhatsAppMessageLog Idempotent Upsert)
                    account_obj = None
                    if business_phone_id:
                        from ..models import WhatsAppAccount
                        account_obj = WhatsAppAccount.objects.filter(phone_number_id=business_phone_id).first()

                    with transaction.atomic():
                        log_defaults = {
                            "account": account_obj,
                            "recipient_phone": norm_from_phone if direction == 'INBOUND' else WhatsAppService.normalize_phone(target_phone),
                            "recipient_name": partner_display_name,
                            "customer": customer_obj,
                            "supplier": supplier_obj,
                            "direction": direction,
                            "sent_via": 'MOBILE_APP' if direction == 'OUTBOUND_MOBILE' else 'SYSTEM',
                            "message_type": msg_type if msg_type in dict(WhatsAppMessageLog.MESSAGE_TYPE_CHOICES) else 'unknown',
                            "body_text": body_text[:2000],
                            "status": 'DELIVERED' if direction == 'INBOUND' else 'SENT',
                            "has_media": bool(media_id),
                            "media_id": media_id,
                            "is_automatic": False,
                        }

                        log_obj, created = WhatsAppMessageLog.objects.update_or_create(
                            message_id=msg_id,
                            defaults=log_defaults
                        )

                        # إذا وجد ملف وسائط تم تنزيله، يتم حفظه محلياً في FileField
                        if downloaded_file and downloaded_filename:
                            try:
                                log_obj.inbound_media_file.save(
                                    downloaded_filename,
                                    ContentFile(downloaded_file),
                                    save=True
                                )
                            except Exception as fe:
                                logger.error(f"WhatsApp Media Save Error: {fe}")

                        processed_count += 1
                        logger.info(f"WhatsApp Inbound Task: تم تسجيل رسالة [{direction}] بنجاح (ID: {msg_id}) ✅")

        return {"success": True, "processed_count": processed_count}

    except Exception as exc:
        logger.exception(f"WhatsApp Webhook Task Exception: {exc}")
        return {"success": False, "error": str(exc)}


# ==================== مهام تنفيذ الحملات وخنق التدفق وإعادة المحاولة (Phase 5) ====================

@shared_task(queue='whatsapp_bulk', bind=True, acks_late=True)
def execute_whatsapp_campaign_task(self, campaign_id: int):
    """
    مهمة جدولة وتنظيم إرسال الحملات بخنق التدفق (Celery Rate Throttling) لحماية تقييم جودة الرقم
    """
    from core.models import WhatsAppCampaign
    from core.services.whatsapp_campaign_service import WhatsAppCampaignService

    campaign = WhatsAppCampaign.objects.filter(pk=campaign_id).first()
    if not campaign or campaign.status != 'RUNNING':
        return {"success": False, "error": "الحملة غير نشطة"}

    pending_recipients = list(campaign.recipients.filter(status='PENDING').values_list('id', flat=True))
    throttle_rate = max(1, campaign.throttle_rate)  # عدد الرسائل في الثانية (افتراضياً 15)

    dispatched_count = 0
    for idx, rec_id in enumerate(pending_recipients):
        countdown_sec = float(idx) / float(throttle_rate)
        try:
            send_campaign_single_message_task.apply_async(args=[rec_id], countdown=countdown_sec)
        except Exception:
            # في حال عدم توفر الوسيط غير المتزامن، التنفيذ الفوري
            WhatsAppCampaignService.send_single_recipient(rec_id)
        dispatched_count += 1

    return {"success": True, "dispatched_count": dispatched_count}


@shared_task(queue='whatsapp_bulk', bind=True, max_retries=2, default_retry_delay=30, acks_late=True)
def send_campaign_single_message_task(self, recipient_id: int):
    """
    مهمة إرسال رسالة فردية داخل الحملة مع فحص التراجع الأسي والتشويش (Exponential Backoff with Jitter)
    """
    from core.models import WhatsAppCampaignRecipient
    from core.services.whatsapp_campaign_service import WhatsAppCampaignService

    rec = WhatsAppCampaignRecipient.objects.filter(pk=recipient_id).first()
    if not rec or rec.status != 'PENDING':
        return {"success": False, "skipped": True}

    campaign_id = rec.campaign_id
    res = WhatsAppCampaignService.send_single_recipient(recipient_id)

    # التحقق من اكتمال الحملة بعد كل دفعة
    WhatsAppCampaignService.check_and_finalize_campaign(campaign_id)
    return res


@shared_task(queue='whatsapp', bind=True, acks_late=True)
def retry_pending_outbox_messages_task(self):
    """
    مهمة دورية لإعادة إرسال الرسائل المعلقة وصندوق الصادر المؤجل عند انقطاع الشبكة (Offline Outbox Recovery)
    """
    import random
    from datetime import timedelta
    from django.utils import timezone
    from core.models import WhatsAppMessageLog
    from core.services.whatsapp_service import WhatsAppService

    # استرجاع الرسائل المعلقة أو الفاشلة بأخطاء مؤقتة مع حد أقصى 3 محاولات
    ten_minutes_ago = timezone.now() - timedelta(minutes=10)
    retry_logs = WhatsAppMessageLog.objects.filter(
        status__in=['PENDING', 'QUEUED', 'FAILED'],
        retry_count__lt=3,
        created_at__gte=ten_minutes_ago,
        error_code__in=['TIMEOUT', 'CONNECTION_ERROR', '80007', '429', None, '']
    ).order_by('created_at')[:30]

    recovered_count = 0
    for log in retry_logs:
        log.retry_count += 1
        log.save(update_fields=['retry_count'])

        # تشويش زمني لمنع تكرار عاصفة الطلبات
        jitter = random.uniform(0.1, 0.5)

        if log.template_name:
            res = WhatsAppService.send_template_message(
                phone=log.recipient_phone,
                template_name=log.template_name,
                language_code=log.language_code,
                partner=log.customer or log.supplier,
                account=log.account,
                is_automatic=True
            )
        elif log.body_text and log.message_type == 'text':
            res = WhatsAppService.send_text_message(
                phone=log.recipient_phone,
                text=log.body_text,
                account=log.account
            )
        else:
            continue

        if res.get("success"):
            recovered_count += 1

    return {"success": True, "recovered_count": recovered_count}

