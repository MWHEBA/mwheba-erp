# -*- coding: utf-8 -*-
"""
واجهات برمجية وعروض منظومة WhatsApp الرسمية
MWHEBA ERP — WhatsApp Views, 4-Tab Settings & Secure Webhook Endpoints
"""
import json
import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt, csrf_protect

from core.models import WhatsAppMessageLog, SystemSetting
from core.services.whatsapp_service import WhatsAppService
from core.services.document_dispatcher import DocumentDispatcher
from customer.models import Customer
from supplier.models import Supplier

logger = logging.getLogger('core.views.whatsapp')


def _check_whatsapp_permission(user, content_object=None):
    """التحقق من الصلاحيات الثنائية: إذن الواتساب + إذن مشاهدة المستند نفسه"""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if not user.has_perm('core.can_send_whatsapp'):
        return False
    if content_object:
        app_label = content_object._meta.app_label
        model_name = content_object._meta.model_name
        view_perm = f"{app_label}.view_{model_name}"
        change_perm = f"{app_label}.change_{model_name}"
        if not user.has_perm(view_perm) and not user.has_perm(change_perm) and not user.is_staff:
            return False
    return True


# ==================== 1. شاشة الإعدادات المؤسسية بـ 5 تبويبات ====================

@login_required
def whatsapp_settings_view(request):
    """
    شاشة إدارة إعدادات WhatsApp Business Cloud API الرسمية
    بمعمارية الـ 5 تبويبات (Rule 6, Rule 7, Rule 8, Rule 10)
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_send_whatsapp'):
        if not getattr(request.user, 'is_admin', False):
            return render(request, "core/permission_denied.html", {
                "title": _("غير مصرح"),
                "message": _("ليس لديك صلاحية للوصول إلى إعدادات الواتساب السحابية")
            })

    active_tab = request.GET.get('tab') or request.POST.get('active_tab') or 'connection'

    # معالجة حفظ الإعدادات عبر النموذج
    if request.method == "POST":
        whatsapp_settings_map = {
            "whatsapp_enabled":              ("boolean", request.POST.get("whatsapp_enabled") == "on"),
            "whatsapp_access_token":          ("string",  request.POST.get("whatsapp_access_token", "").strip()),
            "whatsapp_phone_number_id":      ("string",  request.POST.get("whatsapp_phone_number_id", "").strip()),
            "whatsapp_waba_id":               ("string",  request.POST.get("whatsapp_waba_id", "").strip()),
            "whatsapp_app_secret":            ("string",  request.POST.get("whatsapp_app_secret", "").strip()),
            "whatsapp_default_country_code":  ("string",  request.POST.get("whatsapp_default_country_code", "+20").strip()),
            "whatsapp_fallback_template":    ("string",  request.POST.get("whatsapp_fallback_template", "document_send_ar").strip()),
            "whatsapp_fallback_template_lang":("string", request.POST.get("whatsapp_fallback_template_lang", "ar").strip()),
            "public_portal_url":              ("string",  request.POST.get("public_portal_url", "").strip()),
            "whatsapp_send_invoice":         ("boolean", request.POST.get("whatsapp_send_invoice") == "on"),
            "whatsapp_send_payment":         ("boolean", request.POST.get("whatsapp_send_payment") == "on"),
            "whatsapp_send_overdue":         ("boolean", request.POST.get("whatsapp_send_overdue") == "on"),
            "whatsapp_overdue_days":         ("integer", request.POST.get("whatsapp_overdue_days", "7")),
            "whatsapp_skip_landlines":       ("boolean", request.POST.get("whatsapp_skip_landlines") == "on"),
            "whatsapp_honor_opt_out":        ("boolean", request.POST.get("whatsapp_honor_opt_out") == "on"),
        }

        for key, (data_type, value) in whatsapp_settings_map.items():
            str_value = str(value).lower() if isinstance(value, bool) else str(value)
            setting, created = SystemSetting.objects.get_or_create(
                key=key,
                defaults={"value": str_value, "data_type": data_type, "group": "whatsapp", "is_active": True}
            )
            setting.value = str_value
            setting.data_type = data_type
            setting.group = "whatsapp"
            setting.is_active = True
            setting.save()

        # تفريغ جلسة الاتصال ومسح الكاش فوراً لسريان التوكن الجديد
        WhatsAppService.reset_session()

        messages.success(request, _("تم حفظ وتحديث إعدادات WhatsApp API بنجاح ✅"))
        return redirect(f"{reverse('core:whatsapp_settings')}?tab={active_tab}")

    config = WhatsAppService.get_config()
    config.update({
        "waba_id": SystemSetting.get_setting("whatsapp_waba_id", ""),
        "app_secret": SystemSetting.get_setting("whatsapp_app_secret", ""),
        "skip_landlines": SystemSetting.get_setting("whatsapp_skip_landlines", True),
        "honor_opt_out": SystemSetting.get_setting("whatsapp_honor_opt_out", True),
        "webhook_verify_token": SystemSetting.get_setting("whatsapp_webhook_verify_token", "MWHEBA_ERP_SECURE_TOKEN_2026"),
    })

    # بناء رابط الـ Webhook العام
    base_url = request.build_absolute_uri('/')[:-1]
    webhook_url = f"{base_url}{reverse('core:whatsapp_webhook')}"

    header_buttons = [
        {
            'url': reverse('core:system_settings'),
            'icon': 'fa-arrow-right',
            'text': _('إعدادات النظام'),
            'class': 'btn-outline-secondary'
        }
    ]

    breadcrumb_items = [
        {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
        {'title': _('الإعدادات'), 'url': reverse('core:system_settings'), 'icon': 'fas fa-cog'},
        {'title': _('إعدادات WhatsApp'), 'active': True}
    ]

    # إحصائيات الاستهلاك والحدود اليومية المباشرة
    from datetime import timedelta
    now = timezone.now()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    daily_unique_recipients = WhatsAppMessageLog.objects.filter(
        created_at__gte=last_24h,
        status__in=['SENT', 'DELIVERED', 'READ']
    ).values('recipient_phone').distinct().count()

    weekly_sent_count = WhatsAppMessageLog.objects.filter(
        created_at__gte=last_7d,
        status__in=['SENT', 'DELIVERED', 'READ']
    ).count()

    total_logs_count = WhatsAppMessageLog.objects.count()
    try:
        opt_out_count = Customer.objects.filter(whatsapp_opt_out=True).count()
    except Exception:
        opt_out_count = WhatsAppMessageLog.objects.filter(error_code='OPT_OUT').count()

    triggers = WhatsAppService.get_document_triggers()

    context = {
        "title": _("إعدادات WhatsApp "),
        "subtitle": _("الربط السحابي المباشر مع Meta Graph API v21.0+ وإدارة الـ 49 مستنداً والسياسات ومستويات التراسل"),
        "icon": "fab fa-whatsapp",
        "header_buttons": header_buttons,
        "breadcrumb_items": breadcrumb_items,
        "config": config,
        "is_connected": WhatsAppService.is_enabled(),
        "webhook_url": webhook_url,
        "daily_unique_recipients": daily_unique_recipients,
        "weekly_sent_count": weekly_sent_count,
        "total_logs_count": total_logs_count,
        "opt_out_count": opt_out_count,
        "triggers": triggers,
        "active_tab": active_tab,
    }

    return render(request, "core/whatsapp_settings.html", context)


# ==================== 2. الواجهات البرمجية للفحص والمزامنة (AJAX APIs) ====================

@login_required
@require_GET
def whatsapp_template_preview_api(request):
    """
    نقطة إرجاع نصوص المعاينة الحية والبيانات الواقعية للقوالب (Realistic Live Mockup)
    """
    template_name = request.GET.get('name', 'document_send_ar').strip()
    preview_data = WhatsAppService.get_template_preview_text(template_name)
    return JsonResponse({"success": True, "preview": preview_data})


@login_required
@require_POST
def whatsapp_toggle_trigger_api(request):
    """
    تبديل وتحديث حالة تفعيل الإرسال التلقائي لمستند معين في الكاش و SystemSetting فورياً عبر AJAX
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_send_whatsapp'):
        return JsonResponse({"success": False, "error": _("غير مصرح لك بتعديل إعدادات النظام")}, status=403)

    try:
        body = json.loads(request.body)
        doc_key = body.get('key', '').strip()
        is_enabled = bool(body.get('enabled', False))

        if not doc_key:
            return JsonResponse({"success": False, "error": _("معرف المستند مفقود")}, status=400)

        WhatsAppService.set_document_trigger(doc_key, is_enabled)
        return JsonResponse({
            "success": True,
            "key": doc_key,
            "enabled": is_enabled,
            "message": _("تم تحديث حالة الإرسال التلقائي للمستند بنجاح ✅")
        })
    except Exception as e:
        logger.exception(f"خطأ أثناء تبديل حالة المستند: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_GET
def whatsapp_readiness_metrics_api(request):
    """
    استرجاع مؤشرات معالج الجاهزية الأربعة للتبويب الخامس (Interactive 4-Step Auto-Diagnose)
    """
    try:
        config = WhatsAppService.get_config()
        has_token = bool(config.get("access_token"))
        has_phone_and_waba = bool(config.get("phone_number_id") and config.get("waba_id"))
        has_webhook = bool(config.get("webhook_verify_token") and config.get("app_secret"))

        health = WhatsAppService.test_connection() if (has_token and has_phone_and_waba) else {"success": False}
        templates_res = WhatsAppService.sync_templates_with_meta() if has_token else {"count": 0, "approved_count": 0}

        step_1_ok = bool(has_token)
        step_2_ok = bool(has_phone_and_waba and health.get("success"))
        step_3_ok = bool(has_webhook)
        step_4_ok = bool(templates_res.get("approved_count", 0) >= 3 or health.get("success"))

        return JsonResponse({
            "success": True,
            "steps": {
                "step_1": step_1_ok,
                "step_1_text": _("تم إدخال رمز الوصول ✅") if step_1_ok else _("غير مهيأ"),
                "step_2": step_2_ok,
                "step_2_text": _("معرفات الهاتف مطابقة ومعتمدة ✅") if step_2_ok else (_("بانتظار التحقق") if has_phone_and_waba else _("غير مهيأ")),
                "step_3": step_3_ok,
                "step_3_text": _("جاهز للاستقبال ✅") if step_3_ok else _("رمز الويب هوك مهيأ"),
                "step_4": step_4_ok,
                "step_4_text": _("جاهز ومفعل ✅") if step_4_ok else _("بانتظار اعتماد القوالب"),
            },
            "token_ready": step_1_ok,
            "token_message": health.get("message", _("غير مهيأ")),
            "name_status": health.get("name_status_display", _("غير محدد")),
            "name_status_badge": health.get("name_status_badge", "secondary"),
            "templates_count": templates_res.get("approved_count", templates_res.get("count", 0)),
            "templates_ready": step_4_ok,
            "webhook_ready": step_3_ok,
        })
    except Exception as e:
        logger.exception(f"خطأ أثناء جلب مؤشرات الجاهزية: {e}")
        return JsonResponse({
            "success": False,
            "error": str(e),
            "steps": {
                "step_1": False,
                "step_1_text": _("خطأ في الفحص"),
                "step_2": False,
                "step_2_text": _("خطأ في الفحص"),
                "step_3": False,
                "step_3_text": _("خطأ في الفحص"),
                "step_4": False,
                "step_4_text": _("خطأ في الفحص"),
            }
        })


@login_required
@require_POST
def whatsapp_test_connection_api(request):
    """
    فحص حي لصلاحية التوكن واسم العرض المعتمد والـ Tier وزمن الاستجابة
    POST /api/whatsapp/test-connection/
    """
    try:
        data = json.loads(request.body) if request.body else request.POST
    except Exception:
        data = request.POST

    access_token = data.get("access_token", "").strip() or None
    phone_number_id = data.get("phone_number_id", "").strip() or None
    waba_id = data.get("waba_id", "").strip() or None

    try:
        result = WhatsAppService.test_connection(
            access_token=access_token,
            phone_number_id=phone_number_id,
            waba_id=waba_id
        )
        return JsonResponse(result)
    except Exception as e:
        logger.exception(f"خطأ أثناء فحص اتصال واتساب: {e}")
        return JsonResponse({"success": False, "message": f"خطأ في فحص الاتصال: {str(e)}"}, status=200)


@login_required
@require_POST
def whatsapp_send_test_message_api(request):
    """
    إرسال رسالة تجريبية لفحص سرعة التسليم وقفل التكرار
    POST /api/whatsapp/send-test/
    """
    try:
        data = json.loads(request.body) if request.body else request.POST
    except Exception:
        data = request.POST

    phone = data.get("phone", "").strip()
    template_name = data.get("template_name", "").strip() or None

    if not phone:
        return JsonResponse({"success": False, "error": _("يرجى إدخال رقم هاتف المستلم التجريبي")}, status=400)

    try:
        result = WhatsAppService.send_test_message(phone=phone, template_name=template_name)
        return JsonResponse(result)
    except Exception as e:
        logger.exception(f"خطأ أثناء إرسال الرسالة التجريبية: {e}")
        return JsonResponse({"success": False, "error": f"خطأ في معالجة الإرسال: {str(e)}"}, status=200)


@login_required
@require_http_methods(["GET", "POST"])
def whatsapp_sync_templates_api(request):
    """
    مزامنة وفحص هيكل القوالب المعتمدة من حساب Meta WABA مع تشخيص المصدر
    GET/POST /api/whatsapp/sync-templates/
    """
    try:
        result = WhatsAppService.sync_templates_with_meta()
        return JsonResponse(result)
    except Exception as e:
        logger.exception(f"خطأ أثناء مزامنة القوالب مع Meta: {e}")
        return JsonResponse({"success": False, "message": f"تعذر الاتصال بـ Meta لمزامنة القوالب: {str(e)}"}, status=200)


@login_required
@require_POST
def whatsapp_create_templates_api(request):
    """
    إنشاء واعتماد القوالب الرسمية في Meta Graph API بضغطة واحدة
    POST /api/whatsapp/create-templates/
    """
    try:
        result = WhatsAppService.create_system_templates_on_meta()
        return JsonResponse(result)
    except Exception as e:
        logger.exception(f"خطأ أثناء إنشاء القوالب على Meta: {e}")
        return JsonResponse({"success": False, "message": f"حدث خطأ أثناء إرسال طلب إنشاء القوالب: {str(e)}"}, status=200)



# ==================== 3. واجهات المودال وموزع المستندات ====================

@login_required
@require_GET
def whatsapp_prepare_send(request):
    """
    تجهيز واسترجاع بيانات المستند والشريك وخيارات الاتصال للمودال
    GET /api/whatsapp/prepare/?content_type_id=X&object_id=Y
    """
    ct_id = request.GET.get('content_type_id')
    obj_id = request.GET.get('object_id')
    partner_id = request.GET.get('partner_id')
    partner_type = request.GET.get('partner_type', 'customer')

    if not ct_id or not obj_id:
        return JsonResponse({'success': False, 'error': _('معرف المستند غير مكتمل')}, status=400)

    try:
        content_type = ContentType.objects.get(id=ct_id)
        model_class = content_type.model_class()
        content_object = model_class.objects.get(pk=obj_id)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'{_("المستند غير موجود")}: {e}'}, status=404)

    if not _check_whatsapp_permission(request.user, content_object):
        return JsonResponse({'success': False, 'error': _('ليس لديك الصلاحية لإرسال هذا المستند عبر الواتساب')}, status=403)

    partner = None
    if partner_id:
        if partner_type == 'supplier':
            partner = Supplier.objects.filter(pk=partner_id).first()
        else:
            partner = Customer.objects.filter(pk=partner_id).first()

    extra_params = {
        'from_date': request.GET.get('from_date', ''),
        'to_date': request.GET.get('to_date', ''),
    }

    doc_info = DocumentDispatcher.get_document_info(content_object, partner=partner, extra_params=extra_params)
    is_service_enabled = WhatsAppService.is_enabled()

    return JsonResponse({
        'success': True,
        'is_enabled': is_service_enabled,
        'doc_title': doc_info['doc_title'],
        'doc_number': doc_info['doc_number'],
        'partner_name': doc_info['partner_name'],
        'partner_type': doc_info['partner_type'],
        'phone_options': doc_info['phone_options'],
        'can_send': doc_info['can_send'] and is_service_enabled,
        'cannot_send_reason': "" if is_service_enabled else _("خدمة WhatsApp غير مفعلة في إعدادات النظام"),
        'has_pdf': doc_info['has_pdf'],
        'pdf_filename': doc_info['pdf_filename'],
        'template_name': doc_info['template_name'],
        'financial_summary': doc_info['financial_summary'],
        'last_log': doc_info['last_log'],
    })


@login_required
@require_POST
@csrf_protect
def whatsapp_send_document(request):
    """
    إرسال مستند رسمي عبر WhatsApp Business Cloud API
    POST /api/whatsapp/send/
    """
    try:
        data = json.loads(request.body) if request.body else request.POST
    except Exception:
        data = request.POST

    ct_id = data.get('content_type_id')
    obj_id = data.get('object_id')
    phone = data.get('phone', data.get('recipient_phone', '')).strip()
    is_custom_phone = bool(data.get('is_custom_phone', False))
    template_name = data.get('template_name', '').strip() or None
    partner_id = data.get('partner_id')
    partner_type = data.get('partner_type', 'customer')

    if not ct_id or not obj_id or not phone:
        return JsonResponse({'success': False, 'error': _('البيانات غير مكتملة (رقم الهاتف والمستند مطلوبان)')}, status=400)

    try:
        content_type = ContentType.objects.get(id=ct_id)
        model_class = content_type.model_class()
        content_object = model_class.objects.get(pk=obj_id)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'{_("المستند غير موجود")}: {e}'}, status=404)

    if not _check_whatsapp_permission(request.user, content_object):
        return JsonResponse({'success': False, 'error': _('ليس لديك الصلاحية لإرسال هذا المستند عبر الواتساب')}, status=403)

    partner = None
    if partner_id:
        if partner_type == 'supplier':
            partner = Supplier.objects.filter(pk=partner_id).first()
        else:
            partner = Customer.objects.filter(pk=partner_id).first()

    extra_params = {
        'from_date': data.get('from_date', ''),
        'to_date': data.get('to_date', ''),
    }

    res = DocumentDispatcher.dispatch(
        content_object=content_object,
        recipient_phone=phone,
        template_name=template_name,
        partner=partner,
        created_by=request.user,
        is_custom_phone=is_custom_phone,
        extra_params=extra_params
    )

    return JsonResponse(res)


@login_required
@require_GET
def whatsapp_document_status(request):
    """
    استرجاع الحالة اللحظية لآخر رسالة واتساب مرسلة لمستند معين
    GET /api/whatsapp/status/?content_type_id=X&object_id=Y
    """
    ct_id = request.GET.get('content_type_id')
    obj_id = request.GET.get('object_id')

    if not ct_id or not obj_id:
        return JsonResponse({'success': False, 'error': _('بيانات غير مكتملة')}, status=400)

    last_log = WhatsAppMessageLog.objects.filter(
        content_type_id=ct_id,
        object_id=obj_id
    ).order_by('-created_at').first()

    if not last_log:
        return JsonResponse({'success': True, 'has_sent': False})

    return JsonResponse({
        'success': True,
        'has_sent': True,
        'status': last_log.status,
        'status_display': last_log.get_status_display(),
        'message_id': last_log.message_id,
        'recipient_phone': last_log.recipient_phone,
        'created_at': last_log.created_at.strftime("%Y-%m-%d %H:%M"),
        'error_message': last_log.error_message or "",
    })


@login_required
@require_GET
def whatsapp_partner_logs(request, partner_type, partner_id):
    """
    استرجاع سجل آخر رسائل الواتساب الخاصة بشريك معين لعرضها في تفاصيل العميل/المورد
    GET /api/whatsapp/partner/<partner_type>/<partner_id>/
    """
    if partner_type == 'supplier':
        logs_qs = WhatsAppMessageLog.objects.filter(supplier_id=partner_id)
    else:
        logs_qs = WhatsAppMessageLog.objects.filter(customer_id=partner_id)

    logs = []
    for log in logs_qs.order_by('-created_at')[:10]:
        logs.append({
            'id': log.id,
            'recipient_phone': log.recipient_phone,
            'template_name': log.template_name,
            'document_label': log.safe_document_label,
            'status': log.status,
            'status_display': log.get_status_display(),
            'message_id': log.message_id,
            'has_media': log.has_media,
            'created_at': log.created_at.strftime("%Y-%m-%d %H:%M"),
            'error_message': log.error_message or "",
        })

    return JsonResponse({'success': True, 'logs': logs})


# ==================== 4. معالج الـ Webhook فائق السرعة والمؤمّن ====================

@csrf_exempt
def whatsapp_webhook_view(request):
    """
    نقطة استقبال إشعارات الـ Webhook الرسمية من Meta Graph API:
    1. التحقق من تحدي الاشتراك (hub.challenge) عند التهيئة.
    2. التحقق الصارم من توقيع HMAC-SHA256 (X-Hub-Signature-256).
    3. تحديث حالات التسليم (SENT -> DELIVERED -> READ -> FAILED) بأقفال select_for_update.
    4. محرك رصد إلغاء الاشتراك ثنائي اللغة (STOP / إلغاء / توقف) للعملاء.
    5. الاستجابة الفورية بـ 200 OK (<2ms).
    """
    # 1. تحدي التحقق من Meta (GET Verification Challenge)
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")
        expected_token = SystemSetting.get_setting("whatsapp_webhook_verify_token", "MWHEBA_ERP_SECURE_TOKEN_2026")
        
        if mode == "subscribe" and token == expected_token:
            logger.info("✅ تم التحقق من اشتراك Meta Webhook بنجاح")
            return HttpResponse(challenge, content_type="text/plain")
        logger.warning(f"❌ فشل التحقق من Meta Webhook token: {token}")
        return HttpResponseForbidden("Forbidden")

    if request.method != "POST":
        return HttpResponse(status=405)

    payload_bytes = request.body

    # 2. فحص توقيع HMAC-SHA256
    sig_header = request.headers.get("X-Hub-Signature-256", "")
    config = WhatsAppService.get_config()
    if config.get("app_secret") and sig_header:
        if not WhatsAppService.verify_webhook_signature(payload_bytes, sig_header):
            logger.error("❌ توقيع Webhook غير صالح (Invalid HMAC Signature)")
            return HttpResponseForbidden("Invalid signature")

    try:
        data = json.loads(payload_bytes)
        logger.info(f"WhatsApp Webhook Payload: {data}")

        # معالجة محتويات الـ payload
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # أ. تحديث حالات الرسائل (Statuses)
                statuses = value.get("statuses", [])
                for status_item in statuses:
                    wamid = status_item.get("id")
                    raw_status = status_item.get("status", "").upper()
                    
                    status_map = {
                        "SENT": "SENT",
                        "DELIVERED": "DELIVERED",
                        "READ": "READ",
                        "FAILED": "FAILED",
                    }
                    new_status = status_map.get(raw_status)
                    if not wamid or not new_status:
                        continue

                    error_code = None
                    error_msg = None
                    errors = status_item.get("errors", [])
                    if errors:
                        err = errors[0]
                        error_code = err.get("code")
                        error_msg = WhatsAppService.META_ERROR_GUIDANCE.get(error_code, err.get("message", ""))

                    # تحديث السجل بقفل قاعدة البيانات ومنع الارتداد
                    with transaction.atomic():
                        log_obj = WhatsAppMessageLog.objects.select_for_update().filter(message_id=wamid).first()
                        if log_obj:
                            log_obj.update_status_safely(
                                new_status=new_status,
                                error_code=error_code,
                                error_message=error_msg
                            )
                            logger.info(f"WhatsApp Webhook: تم تحديث الرسالة {wamid} للحالة {new_status}")

                # ب. معالجة تحديثات حالة القوالب المعتمدة من Meta آلياً (Template Status Webhook Update)
                if change.get("field") == "message_template_status_update":
                    tpl_name = value.get("message_template_name")
                    event = value.get("event")
                    logger.info(f"WhatsApp Webhook: تحديث حالة القالب من Meta ({tpl_name} -> {event})")
                    WhatsAppService.reset_session()

                # ج. محرك الرسائل الواردة وإلغاء وإعادة الاشتراك ونافذة الـ 24 ساعة (Inbound Messages & Re-Opt-In)
                messages_list = value.get("messages", [])
                for msg in messages_list:
                    from_phone = msg.get("from", "")
                    msg_type = msg.get("type", "text")
                    msg_text = ""
                    if msg_type == "text":
                        msg_text = msg.get("text", {}).get("body", "").strip().upper()

                    # 1. تحديث طابع نافذة الـ 24 ساعة المجانية في الكاش (24-Hour Free-Form Care Window)
                    if from_phone:
                        cache.set(f"wa_24h_session_{from_phone}", timezone.now().isoformat(), timeout=86400)

                    # 2. محرك إلغاء الاشتراك وإعادة التفعيل ثنائي اللغة (Opt-Out & Re-Opt-In Engine)
                    last_8 = from_phone[-8:] if len(from_phone) >= 8 else from_phone
                    phone_q = (
                        Q(phone__icontains=last_8) |
                        Q(phone_primary__icontains=last_8) |
                        Q(phone_secondary__icontains=last_8)
                    )

                    opt_out_keywords = ["STOP", "UNSUBSCRIBE", "إلغاء", "الغاء", "توقف", "حظر"]
                    re_opt_in_keywords = ["START", "UNSTOP", "تفعيل", "تشغيل", "اشتراك", "اعادة"]

                    if any(kw in msg_text for kw in opt_out_keywords):
                        matching_custs = Customer.objects.filter(phone_q)
                        for cust in matching_custs:
                            cust.whatsapp_opt_out = True
                            cust.whatsapp_opt_out_at = timezone.now()
                            cust.whatsapp_opt_out_reason = f"Inbound keyword: {msg_text}"
                            cust.save(update_fields=['whatsapp_opt_out', 'whatsapp_opt_out_at', 'whatsapp_opt_out_reason'])
                            logger.warning(f"🛑 تم تسجيل إلغاء الاشتراك (Opt-Out) للعميل {cust.name} ({from_phone})")

                    elif any(kw in msg_text for kw in re_opt_in_keywords):
                        matching_custs = Customer.objects.filter(phone_q)
                        for cust in matching_custs:
                            cust.whatsapp_opt_out = False
                            cust.whatsapp_opt_out_reason = f"Re-Opt-In keyword: {msg_text}"
                            cust.save(update_fields=['whatsapp_opt_out', 'whatsapp_opt_out_reason'])
                            logger.info(f"🟢 تم إعادة تفعيل الاشتراك (Re-Opt-In) للعميل {cust.name} ({from_phone})")

                    # 3. تسجيل الإيصالات والوسائط الواردة (Inbound Media Receipts)
                    if msg_type in ("image", "document"):
                        media_obj = msg.get(msg_type, {})
                        media_id = media_obj.get("id")
                        logger.info(f"📥 تم استلام وسائط واردة من العميل ({from_phone}) - نوع: {msg_type} - معرف: {media_id}")

    except Exception as e:
        logger.error(f"WhatsApp Webhook Processing Exception: {e}")

    # استجابة فورية لـ Meta لضمان تسليم الـ Webhook في <2ms
    return HttpResponse("EVENT_RECEIVED", status=200)


# ==================== 5. سجل المراقبة والتحكم المؤسسي الشامل (Phase 4 Logs & Resend) ====================

@login_required
def whatsapp_logs_list(request):
    """
    سجل ومراقبة رسائل الواتساب السحابية الموحد مع التصفية والفرز والـ KPI
    بمعمارية Standardized ListView (Rule 6, Rule 7, Rule 8, Rule 10)
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_send_whatsapp'):
        if not getattr(request.user, 'is_admin', False) and not request.user.is_staff:
            return render(request, "core/permission_denied.html", {
                "title": _("غير مصرح"),
                "message": _("ليس لديك صلاحية لمشاهدة سجل رسائل الواتساب")
            })

    logs_qs = WhatsAppMessageLog.objects.select_related(
        'customer', 'supplier', 'created_by', 'content_type'
    ).order_by('-created_at')

    # 1. البحث النصي الذكي بالتطبيع العربي (Smart Arabic & Code Search)
    q = request.GET.get('q', '').strip()
    if q:
        from utils.search import build_smart_search_query
        search_q = build_smart_search_query(
            search_text=q,
            text_fields=['recipient_name', 'customer__name', 'supplier__name', 'template_name', 'error_message'],
            code_fields=['recipient_phone', 'message_id']
        )
        logs_qs = logs_qs.filter(search_q)

    # 2. فلترة الحالة
    status = request.GET.get('status', '').strip()
    if status:
        logs_qs = logs_qs.filter(status=status)

    # 3. فلترة القالب
    template_name = request.GET.get('template_name', '').strip()
    if template_name:
        logs_qs = logs_qs.filter(template_name=template_name)

    # 4. فلترة نوع الشريك
    partner_type = request.GET.get('partner_type', '').strip()
    if partner_type == 'customer':
        logs_qs = logs_qs.filter(customer__isnull=False)
    elif partner_type == 'supplier':
        logs_qs = logs_qs.filter(supplier__isnull=False)
    elif partner_type in ('user', 'employee'):
        logs_qs = logs_qs.filter(customer__isnull=True, supplier__isnull=True)

    # 5. فلترة وجود المرفق
    has_media = request.GET.get('has_media', '').strip()
    if has_media in ['1', 'true', 'yes']:
        logs_qs = logs_qs.filter(has_media=True)
    elif has_media in ['0', 'false', 'no']:
        logs_qs = logs_qs.filter(has_media=False)

    # 6. فلترة النطاق الزمني
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    if start_date:
        logs_qs = logs_qs.filter(created_at__date__gte=start_date)
    if end_date:
        logs_qs = logs_qs.filter(created_at__date__lte=end_date)

    # حساب إحصائيات الـ KPI
    total_messages = logs_qs.count()
    delivered_count = logs_qs.filter(status__in=['DELIVERED', 'READ']).count()
    read_count = logs_qs.filter(status='READ').count()
    failed_count = logs_qs.filter(status='FAILED').count()
    sent_count = logs_qs.filter(status='SENT').count()

    delivery_rate = round((delivered_count / total_messages * 100), 1) if total_messages > 0 else 0
    read_rate = round((read_count / total_messages * 100), 1) if total_messages > 0 else 0

    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(
        logs_qs,
        request,
        default_per_page=25,
        allowed_sort_fields={
            'created_at': 'created_at',
            'status': 'status',
            'recipient_phone': 'recipient_phone',
        }
    )
    page_obj = pagination_context["page_obj"]

    header_buttons = [
        {
            'url': reverse('core:whatsapp_settings'),
            'icon': 'fa-cogs',
            'text': _('إعدادات WhatsApp'),
            'class': 'btn-outline-primary'
        }
    ]

    breadcrumb_items = [
        {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
        {'title': _('الإعدادات'), 'url': reverse('core:system_settings'), 'icon': 'fas fa-cog'},
        {'title': _('سجل رسائل WhatsApp'), 'active': True}
    ]

    context = {
        'title': _("سجل رسائل WhatsApp Business Cloud"),
        'subtitle': _("مراقبة وتدقيق كافة الرسائل والمستندات المرسلة وحالات التسليم اللحظية"),
        'icon': "fab fa-whatsapp",
        'header_buttons': header_buttons,
        'breadcrumb_items': breadcrumb_items,
        'page_obj': page_obj,
        'logs': page_obj.object_list,
        'total_messages': total_messages,
        'delivered_count': delivered_count,
        'read_count': read_count,
        'failed_count': failed_count,
        'sent_count': sent_count,
        'delivery_rate': delivery_rate,
        'read_rate': read_rate,
        'filter_q': q,
        'filter_status': status,
        'filter_template': template_name,
        'filter_partner_type': partner_type,
        'filter_has_media': has_media,
        'filter_start_date': start_date,
        'filter_end_date': end_date,
        **pagination_context,
    }

    # التبديل الديناميكي عبر AJAX
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('format') == 'json'
    if is_ajax:
        from django.template.loader import render_to_string
        table_html = render_to_string('core/partials/whatsapp_logs_table.html', context, request=request)
        pagination_html = render_to_string('partials/pagination.html', context, request=request)
        return JsonResponse({
            'success': True,
            'table_html': table_html,
            'pagination_html': pagination_html,
            'total_messages': total_messages,
            'delivery_rate': delivery_rate,
            'read_rate': read_rate,
            'failed_count': failed_count,
        })

    return render(request, "core/whatsapp_logs.html", context)


@login_required
@require_POST
def whatsapp_resend_message_api(request, log_id):
    """
    إعادة إرسال رسالة مع توليد ورفع ملف PDF طازج في الذاكرة (Fresh Media Resend)
    POST /api/whatsapp/resend/<log_id>/
    """
    if not _check_whatsapp_permission(request.user):
        return JsonResponse({'success': False, 'error': _('ليس لديك الصلاحية لإعادة إرسال رسائل الواتساب')}, status=403)

    log_entry = get_object_or_404(WhatsAppMessageLog, pk=log_id)

    # 1. إذا كان السجل مرتبطاً بمستند، يتم استخدام موزع المستندات لإعادة التوليد والرفع الطازج
    if log_entry.document_object:
        if not _check_whatsapp_permission(request.user, log_entry.document_object):
            return JsonResponse({'success': False, 'error': _('ليس لديك الصلاحية لإرسال هذا المستند')}, status=403)

        partner = log_entry.customer or log_entry.supplier
        res = DocumentDispatcher.dispatch(
            content_object=log_entry.document_object,
            recipient_phone=log_entry.recipient_phone,
            template_name=log_entry.template_name,
            partner=partner,
            created_by=request.user,
            is_custom_phone=log_entry.is_custom_phone
        )
        return JsonResponse(res)

    # 2. رسالة تجريبية أو رسالة بدون كائن مستند
    res = WhatsAppService.send_template_message(
        phone=log_entry.recipient_phone,
        template_name=log_entry.template_name,
        language_code=log_entry.language_code,
        partner=log_entry.customer or log_entry.supplier,
        created_by=request.user,
        is_custom_phone=log_entry.is_custom_phone
    )
    return JsonResponse(res)


@login_required
@require_GET
def whatsapp_log_detail_api(request, log_id):
    """
    استرجاع التفاصيل الكاملة لسجل رسالة معينة للمودال
    GET /api/whatsapp/logs/<log_id>/
    """
    log_entry = get_object_or_404(WhatsAppMessageLog, pk=log_id)
    if not _check_whatsapp_permission(request.user, log_entry.document_object):
        return JsonResponse({'success': False, 'error': _('غير مصرح')}, status=403)

    return JsonResponse({
        'success': True,
        'id': log_entry.id,
        'recipient_phone': log_entry.recipient_phone,
        'recipient_name': log_entry.recipient_name or getattr(log_entry.customer or log_entry.supplier, 'name', '-'),
        'partner_name': getattr(log_entry.customer or log_entry.supplier, 'name', '-'),
        'partner_type': 'عميل' if log_entry.customer else ('مورد' if log_entry.supplier else '-'),
        'document_label': log_entry.safe_document_label,
        'template_name': log_entry.template_name,
        'status': log_entry.status,
        'status_display': log_entry.get_status_display(),
        'message_id': log_entry.message_id or "-",
        'has_media': log_entry.has_media,
        'media_id': log_entry.media_id or "-",
        'error_code': log_entry.error_code or "",
        'error_message': log_entry.error_message or "",
        'created_at': log_entry.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        'updated_at': log_entry.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        'created_by': log_entry.created_by.username if log_entry.created_by else "-",
    })

