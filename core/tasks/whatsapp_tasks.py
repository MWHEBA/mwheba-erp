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
