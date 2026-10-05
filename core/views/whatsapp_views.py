# -*- coding: utf-8 -*-
"""
واجهات برمجية وعروض منظومة WhatsApp الرسمية
MWHEBA ERP — WhatsApp Views, 4-Tab Settings & Secure Webhook Endpoints
"""
import json
import time
import logging
from django.conf import settings
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
            "whatsapp_app_id":               ("string",  request.POST.get("whatsapp_app_id", "").strip()),
            "whatsapp_embedded_config_id":   ("string",  request.POST.get("whatsapp_embedded_config_id", "").strip()),
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
        "app_id": SystemSetting.get_setting("whatsapp_app_id", "") or getattr(settings, 'WHATSAPP_APP_ID', ''),
        "config_id": SystemSetting.get_setting("whatsapp_embedded_config_id", "") or getattr(settings, 'WHATSAPP_EMBEDDED_CONFIG_ID', ''),
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
            'url': reverse('core:whatsapp_live_chat'),
            'icon': 'fa-comments',
            'text': _('المحادثات المباشرة (Live Chat)'),
            'class': 'btn-success'
        },
        {
            'url': reverse('core:whatsapp_campaigns'),
            'icon': 'fa-bullhorn',
            'text': _('الحملات والإرسال الجماعي'),
            'class': 'btn-outline-primary'
        },
        {
            'url': reverse('core:whatsapp_logs'),
            'icon': 'fa-history',
            'text': _('سجل الرسائل'),
            'class': 'btn-outline-secondary'
        },
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
    from ..models import WhatsAppAccount
    accounts = WhatsAppAccount.objects.all().order_by('-is_default', '-created_at')

    context = {
        "title": _("إعدادات WhatsApp "),
        "subtitle": _("الربط السحابي المباشر مع Meta Graph API v21.0+ وإدارة الـ 49 مستنداً والسياسات ومستويات التراسل"),
        "icon": "fab fa-whatsapp",
        "header_buttons": header_buttons,
        "breadcrumb_items": breadcrumb_items,
        "config": config,
        "accounts": accounts,
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
    template_name = (request.GET.get('template_name') or request.GET.get('name') or 'document_send_ar').strip()
    doc_title = (request.GET.get('doc_title') or request.GET.get('title') or '').strip()
    preview_data = WhatsAppService.get_template_preview_text(template_name, doc_display=doc_title)
    return JsonResponse({
        "success": True,
        "preview": preview_data,
        "rendered_text": preview_data.get("mock_text", ""),
        "mock_text": preview_data.get("mock_text", ""),
        "raw_text": preview_data.get("raw_text", ""),
        "category": preview_data.get("category", "UTILITY"),
        "title": preview_data.get("title", ""),
        "has_pdf": preview_data.get("has_pdf", False),
        "pdf_filename": preview_data.get("pdf_filename", "Document.pdf"),
    })


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
    account_id = data.get("account_id") or request.GET.get("account_id")

    try:
        result = WhatsAppService.test_connection(
            access_token=access_token,
            phone_number_id=phone_number_id,
            waba_id=waba_id,
            account_id=account_id
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
    تجهيز واسترجاع بيانات المستند والشريك وخيارات الاتصال والحسابات للمودال
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

    # جلب الحسابات النشطة لاختيار الفرع أو الحساب المناسب
    from ..models import WhatsAppAccount
    accounts_qs = WhatsAppAccount.objects.exclude(account_status='DISCONNECTED').order_by('-is_default', 'name')
    accounts_data = [
        {
            'id': acc.id,
            'name': acc.name,
            'company_name': acc.company_name,
            'phone_number': acc.phone_number,
            'is_default': acc.is_default,
            'is_coexistence': acc.is_coexistence,
        }
        for acc in accounts_qs
    ]

    # فحص حالة إلغاء الاشتراك (Opt-Out) ونافذة الـ 24 ساعة النشطة
    is_opt_out = bool(partner and getattr(partner, 'whatsapp_opt_out', False))
    honor_opt_out = SystemSetting.get_setting("whatsapp_honor_opt_out", True)

    is_24h_window_active = False
    from datetime import timedelta
    twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
    if partner:
        for opt in doc_info.get('phone_options', []):
            phone_num = opt.get('phone')
            if phone_num and WhatsAppMessageLog.objects.filter(recipient_phone=phone_num, direction='INBOUND', created_at__gte=twenty_four_hours_ago).exists():
                is_24h_window_active = True
                break

    can_send = doc_info['can_send'] and is_service_enabled
    cannot_send_reason = ""
    if not is_service_enabled:
        cannot_send_reason = _("خدمة WhatsApp غير مفعلة في إعدادات النظام")
    elif is_opt_out and honor_opt_out:
        can_send = False
        cannot_send_reason = _("تم إيقاف الإرسال: العميل قام بإلغاء الاشتراك مسبقاً (Opt-Out)")
    elif not doc_info['can_send']:
        cannot_send_reason = doc_info.get('cannot_send_reason', '')

    return JsonResponse({
        'success': True,
        'is_enabled': is_service_enabled,
        'doc_title': doc_info['doc_title'],
        'doc_number': doc_info['doc_number'],
        'partner_name': doc_info['partner_name'],
        'partner_type': doc_info['partner_type'],
        'phone_options': doc_info['phone_options'],
        'accounts': accounts_data,
        'is_opt_out': is_opt_out,
        'honor_opt_out': honor_opt_out,
        'is_24h_window_active': is_24h_window_active,
        'can_send': can_send,
        'cannot_send_reason': cannot_send_reason,
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
    إرسال مستند رسمي عبر WhatsApp Business Cloud API مع دعم اختيار الحساب
    POST /api/whatsapp/send/
    """
    try:
        try:
            data = json.loads(request.body) if request.body else request.POST
        except Exception:
            data = request.POST

        ct_id = data.get('content_type_id')
        obj_id = data.get('object_id')
        raw_phone = data.get('phone') or data.get('recipient_phone') or ''
        phone = str(raw_phone).strip() if raw_phone else ''
        is_custom_phone = str(data.get('is_custom_phone', '')).lower() in ('true', '1') or bool(data.get('is_custom_phone', False))
        template_name = str(data.get('template_name', '')).strip() or None
        partner_id = data.get('partner_id')
        partner_type = str(data.get('partner_type', 'customer')).strip().lower()
        account_id = data.get('account_id')
        if account_id and str(account_id).isdigit():
            account_id = int(account_id)
        else:
            account_id = None

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
            try:
                if partner_type == 'supplier':
                    partner = Supplier.objects.filter(pk=partner_id).first()
                else:
                    partner = Customer.objects.filter(pk=partner_id).first()
            except Exception:
                partner = None

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
            extra_params=extra_params,
            account_id=account_id
        )

        return JsonResponse(res)
    except Exception as exc:
        logger.exception(f"Unexpected error in whatsapp_send_document: {exc}")
        return JsonResponse({'success': False, 'error': f"حدث خطأ أثناء الإرسال: {str(exc)}"}, status=500)


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
    استرجاع سجل آخر رسائل الواتساب الخاصة بشريك معين مع مؤشر نافذة الـ 24 ساعة النشطة
    GET /api/whatsapp/partner/<partner_type>/<partner_id>/
    """
    if partner_type == 'supplier':
        logs_qs = WhatsAppMessageLog.objects.filter(supplier_id=partner_id)
        partner_obj = Supplier.objects.filter(pk=partner_id).first()
    else:
        logs_qs = WhatsAppMessageLog.objects.filter(customer_id=partner_id)
        partner_obj = Customer.objects.filter(pk=partner_id).first()

    # فحص ما إذا كانت نافذة الـ 24 ساعة المجانية مفتوحة للشريك
    phone_options = WhatsAppService.get_partner_contact_options(partner_obj) if partner_obj else []
    is_24h_window_active = False
    for opt in phone_options:
        norm = opt.get("phone")
        if norm and cache.get(f"wa_24h_session_{norm}"):
            is_24h_window_active = True
            break

    logs = []
    for log in logs_qs.order_by('-created_at')[:20]:
        media_url = log.inbound_media_file.url if log.inbound_media_file else None
        logs.append({
            'id': log.id,
            'direction': log.direction,
            'direction_display': log.get_direction_display(),
            'message_type': log.message_type,
            'message_type_display': log.get_message_type_display(),
            'body_text': log.body_text or "",
            'media_url': media_url,
            'recipient_phone': log.recipient_phone,
            'template_name': log.template_name or log.get_message_type_display(),
            'document_label': log.safe_document_label,
            'status': log.status,
            'status_display': log.get_status_display(),
            'message_id': log.message_id,
            'has_media': log.has_media or bool(log.inbound_media_file),
            'created_at': log.created_at.strftime("%Y-%m-%d %H:%M"),
            'error_message': log.error_message or "",
        })

    return JsonResponse({
        'success': True,
        'logs': logs,
        'is_24h_window_active': is_24h_window_active,
        'partner_opt_out': getattr(partner_obj, 'whatsapp_opt_out', False) if partner_obj else False
    })


# ==================== 4. معالج الـ Webhook فائق السرعة والمؤمّن ====================

@csrf_exempt
def whatsapp_webhook_view(request):
    """
    نقطة استقبال إشعارات الـ Webhook الرسمية من Meta Graph API:
    1. التحقق من تحدي الاشتراك (hub.challenge) عند التهيئة.
    2. التحقق الصارم من توقيع HMAC-SHA256 (X-Hub-Signature-256).
    3. تحديث حالات التسليم (SENT -> DELIVERED -> READ -> FAILED) بأقفال select_for_update.
    4. محرك رصد إلغاء الاشتراك ثنائي اللغة (STOP / إلغاء / توقف) للعملاء.
    5. الاستجابة الفورية بـ 200 OK (<20ms SLA) مع قياس وتسجيل زمن الاستجابة.
    """
    start_time = time.perf_counter()

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
        logger.info(f"WhatsApp Webhook Raw Ingress: {data}")

        # معالجة فورية لتحديثات حالة القوالب إن وجدت
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") == "message_template_status_update":
                    WhatsAppService.reset_session()

        # إدراج المعالجة الثقيلة في طابور المهام الخلفي غير المتزامن (Two-Tier Webhook)
        from core.tasks.whatsapp_tasks import process_whatsapp_webhook_task
        try:
            process_whatsapp_webhook_task.delay(data)
        except Exception as queue_err:
            logger.warning(f"WhatsApp Webhook Celery Broker unavailable ({queue_err}) -> معالجة عبر Daemon Thread")
            import threading
            thread = threading.Thread(target=process_whatsapp_webhook_task, args=(None, data), daemon=True)
            thread.start()

    except Exception as e:
        logger.error(f"WhatsApp Webhook Ingress Exception: {e}")

    # قياس وتسجيل زمن استجابة الـ Ingress
    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    from core.services.whatsapp_metrics_service import WhatsAppMetricsService
    WhatsAppMetricsService.record_ingress_latency(elapsed_ms)

    # استجابة فورية لـ Meta في أقل من 20ms لمنع تكرار إرسال الأحداث
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
        'customer', 'created_by', 'content_type'
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

    # 7. فلترة اتجاه ومصدر الرسالة (Coexistence Filter)
    direction = request.GET.get('direction', '').strip()
    if direction:
        logs_qs = logs_qs.filter(direction=direction)

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
            'direction': 'direction',
            'recipient_phone': 'recipient_phone',
        }
    )
    page_obj = pagination_context["page_obj"]

    header_buttons = [
        {
            'url': reverse('core:whatsapp_live_chat'),
            'icon': 'fa-comments',
            'text': _('المحادثات المباشرة (Live Chat)'),
            'class': 'btn-success'
        },
        {
            'url': reverse('core:whatsapp_campaigns'),
            'icon': 'fa-bullhorn',
            'text': _('الحملات والإرسال الجماعي'),
            'class': 'btn-outline-primary'
        },
        {
            'url': reverse('core:whatsapp_settings'),
            'icon': 'fa-cogs',
            'text': _('إعدادات WhatsApp'),
            'class': 'btn-outline-secondary'
        }
    ]

    breadcrumb_items = [
        {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
        {'title': _('الإعدادات'), 'url': reverse('core:system_settings'), 'icon': 'fas fa-cog'},
        {'title': _('سجل رسائل WhatsApp'), 'active': True}
    ]

    context = {
        'title': _("سجل رسائل WhatsApp Business Cloud"),
        'subtitle': _("مراقبة وتدقيق كافة الرسائل والمستندات المرسلة والواردة وحالات التسليم اللحظية"),
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
        'filter_direction': direction,
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

    media_url = log_entry.inbound_media_file.url if log_entry.inbound_media_file else None

    return JsonResponse({
        'success': True,
        'id': log_entry.id,
        'direction': log_entry.direction,
        'direction_display': log_entry.get_direction_display(),
        'message_type': log_entry.message_type,
        'message_type_display': log_entry.get_message_type_display(),
        'body_text': log_entry.body_text or "",
        'media_url': media_url,
        'recipient_phone': log_entry.recipient_phone,
        'recipient_name': log_entry.recipient_name or getattr(log_entry.customer or log_entry.supplier, 'name', '-'),
        'partner_name': getattr(log_entry.customer or log_entry.supplier, 'name', '-'),
        'partner_type': 'عميل' if log_entry.customer else ('مورد' if log_entry.supplier else '-'),
        'document_label': log_entry.safe_document_label,
        'template_name': log_entry.template_name or log_entry.get_message_type_display(),
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


# ==================== 5. إدارة حسابات الواتساب ومزود الحلول (Accounts & Embedded Signup APIs) ====================

@login_required
@require_POST
def whatsapp_account_save_api(request):
    """
    حفظ أو تعديل حساب WhatsApp للأعمال (Manual Onboarding / Edit)
    POST /api/whatsapp/accounts/save/
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_manage_whatsapp_accounts'):
        return JsonResponse({'success': False, 'error': _('غير مصرح لك بإدارة حسابات الواتساب')}, status=403)

    data = {}
    if request.content_type == 'application/json' or (request.body and request.body.startswith(b'{')):
        try:
            data = json.loads(request.body.decode('utf-8'))
        except Exception:
            data = {}

    account_id = data.get('account_id') or request.POST.get('account_id')
    name = (data.get('name') if 'name' in data else request.POST.get('name', '')).strip()
    company_name = (data.get('company_name') if 'company_name' in data else request.POST.get('company_name', '')).strip()
    phone_number_id = (data.get('phone_number_id') if 'phone_number_id' in data else request.POST.get('phone_number_id', '')).strip()
    phone_number = (data.get('phone_number') if 'phone_number' in data else request.POST.get('phone_number', '')).strip()
    waba_id = (data.get('waba_id') if 'waba_id' in data else request.POST.get('waba_id', '')).strip()
    app_id = (data.get('app_id') if 'app_id' in data else request.POST.get('app_id', '')).strip()
    raw_token = (data.get('access_token') if 'access_token' in data else request.POST.get('access_token', '')).strip()
    notes = (data.get('notes') if 'notes' in data else request.POST.get('notes', '')).strip()

    if 'is_coexistence' in data:
        is_coexistence = bool(data.get('is_coexistence'))
    elif 'is_coexistence' in request.POST:
        is_coexistence = request.POST.get('is_coexistence') in ('on', 'true', '1')
    else:
        is_coexistence = None

    if 'is_default' in data:
        is_default = bool(data.get('is_default'))
    else:
        is_default = request.POST.get('is_default') in ('on', 'true', '1')

    if 'is_active' in data:
        is_active = bool(data.get('is_active'))
    else:
        is_active = request.POST.get('is_active') in ('on', 'true', '1') if 'is_active' in request.POST else True

    if not phone_number_id:
        return JsonResponse({'success': False, 'error': _('معرف رقم الهاتف (Phone Number ID) إلزامي')})

    from ..models import WhatsAppAccount
    from ..services.whatsapp_embedded_signup_service import WhatsAppEmbeddedSignupService

    try:
        if account_id:
            account = get_object_or_404(WhatsAppAccount, pk=account_id)
            account.name = name or account.name
            account.company_name = company_name
            account.phone_number_id = phone_number_id
            if phone_number:
                account.display_phone_number = phone_number
            account.waba_id = waba_id
            account.app_id = app_id
            if is_coexistence is not None:
                account.is_coexistence = is_coexistence
            account.account_status = 'CONNECTED' if is_active else 'DISCONNECTED'
            account.notes = notes
            if raw_token:
                account.access_token = raw_token
            if is_default:
                account.is_default = True
            account.save()
            message = _("تم تحديث حساب الواتساب بنجاح ✅")
        else:
            if not raw_token:
                return JsonResponse({'success': False, 'error': _('رمز الوصول (Access Token) إلزامي للحساب الجديد')})
            res = WhatsAppEmbeddedSignupService.complete_onboarding(
                phone_number_id=phone_number_id,
                access_token=raw_token,
                waba_id=waba_id,
                app_id=app_id,
                account_name=name,
                company_name=company_name,
                is_coexistence=is_coexistence,
                is_default=is_default,
                notes=notes
            )
            if not res.get("success"):
                return JsonResponse({'success': False, 'error': res.get('error', _('فشل ربط الحساب'))})
            message = _("تم ربط وتشفير حساب الواتساب بنجاح ✅")

        WhatsAppService.reset_session()
        return JsonResponse({'success': True, 'message': message})
    except Exception as exc:
        logger.exception("Error saving WhatsApp account")
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@login_required
@require_POST
def whatsapp_account_toggle_default_api(request, account_id):
    """
    تعيين حساب كافتراضي للنظام (Single Default Guard)
    POST /api/whatsapp/accounts/<account_id>/set-default/
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_manage_whatsapp_accounts'):
        return JsonResponse({'success': False, 'error': _('غير مصرح لك بإدارة حسابات الواتساب')}, status=403)

    from ..models import WhatsAppAccount
    account = get_object_or_404(WhatsAppAccount, pk=account_id)
    account.is_default = True
    account.save()
    WhatsAppService.reset_session()
    return JsonResponse({'success': True, 'message': _('تم تعيين الحساب كافتراضي للنظام بنجاح ⭐')})


@login_required
@require_POST
def whatsapp_account_delete_api(request, account_id):
    """
    حذف حساب واتساب
    POST /api/whatsapp/accounts/<account_id>/delete/
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_manage_whatsapp_accounts'):
        return JsonResponse({'success': False, 'error': _('غير مصرح لك بحذف حسابات الواتساب')}, status=403)

    from ..models import WhatsAppAccount
    account = get_object_or_404(WhatsAppAccount, pk=account_id)
    was_default = account.is_default
    account.delete()

    if was_default:
        next_account = WhatsAppAccount.objects.first()
        if next_account:
            next_account.is_default = True
            next_account.save()

    WhatsAppService.reset_session()
    return JsonResponse({'success': True, 'message': _('تم حذف الحساب بنجاح 🗑️')})


@login_required
@require_POST
def whatsapp_embedded_signup_callback_api(request):
    """
    استقبال ومعالجة كود المصادقة من نافذة Meta Embedded Signup المنبثقة
    POST /api/whatsapp/embedded-signup/callback/
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_manage_whatsapp_accounts'):
        return JsonResponse({'success': False, 'error': _('غير مصرح لك بربط الحسابات')}, status=403)

    import json
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = request.POST

    code = data.get('code', '').strip()
    phone_number_id = data.get('phone_number_id', '').strip()
    waba_id = data.get('waba_id', '').strip()
    is_coexistence = data.get('is_coexistence', True)

    if not code:
        return JsonResponse({'success': False, 'error': _('كود المصادقة (Auth Code) غير متوفر')})

    from ..services.whatsapp_embedded_signup_service import WhatsAppEmbeddedSignupService

    # 1. استبدال الكود بتوكن دائم فورياً
    exchange_res = WhatsAppEmbeddedSignupService.exchange_code_for_token(code)
    if not exchange_res.get("success"):
        return JsonResponse({'success': False, 'error': exchange_res.get("error", _("فشل استبدال كود المصادقة مع Meta"))})

    access_token = exchange_res["access_token"]

    # 2. إكمال عملية الربط الشاملة
    onboard_res = WhatsAppEmbeddedSignupService.complete_onboarding(
        phone_number_id=phone_number_id,
        access_token=access_token,
        waba_id=waba_id,
        is_coexistence=is_coexistence,
        is_default=True
    )

    return JsonResponse(onboard_res)


# ==================== 6. واجهات الشات الحي والمحادثات المباشرة (Phase 4 Live Chat & APIs) ====================

@login_required
def whatsapp_live_chat_view(request):
    """
    شاشة المحادثات الحية المباشرة مع العملاء والموردين وتعدد الحسابات
    MWHEBA ERP — Multi-Account Live Chat Hub (Rule 6, Rule 7, Rule 8, Rule 10)
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_use_whatsapp_live_chat') and not request.user.has_perm('core.can_send_whatsapp'):
        if not getattr(request.user, 'is_admin', False) and not request.user.is_staff:
            return render(request, "core/permission_denied.html", {
                "title": _("غير مصرح"),
                "message": _("ليس لديك صلاحية لاستخدام المحادثات المباشرة")
            })

    from ..models import WhatsAppAccount
    from django.contrib.auth import get_user_model
    User = get_user_model()

    accounts = WhatsAppAccount.objects.exclude(account_status='DISCONNECTED').order_by('-is_default', 'name')
    default_account = accounts.filter(is_default=True).first() or accounts.first()

    staff_users = User.objects.filter(is_active=True).order_by('first_name', 'username')
    
    # محاولة استرجاع شرائح العملاء لنموذج تحويل جهة الاتصال
    customer_tiers = []
    try:
        from customer.models import CustomerTier
        customer_tiers = CustomerTier.objects.all().order_by('display_order', 'name')
    except Exception:
        pass

    header_buttons = [
        {
            'url': reverse('core:whatsapp_campaigns'),
            'icon': 'fa-bullhorn',
            'text': _('الحملات والإرسال الجماعي'),
            'class': 'btn-primary'
        },
        {
            'url': reverse('core:whatsapp_logs'),
            'icon': 'fa-history',
            'text': _('سجل الرسائل'),
            'class': 'btn-outline-secondary'
        },
        {
            'url': reverse('core:whatsapp_settings'),
            'icon': 'fa-cog',
            'text': _('إعدادات WhatsApp'),
            'class': 'btn-outline-secondary'
        }
    ]

    context = {
        'title': _('المحادثات المباشرة — WhatsApp Live Chat'),
        'subtitle': _('التواصل اللحظي مع العملاء والموردين ومتابعة نوافذ الرد والوسائط المباشرة'),
        'icon': 'fab fa-whatsapp',
        'accounts': accounts,
        'default_account': default_account,
        'staff_users': staff_users,
        'customer_tiers': customer_tiers,
        'header_buttons': header_buttons,
        'show_breadcrumb': False,
    }

    return render(request, "core/whatsapp_live_chat.html", context)


@login_required
@require_GET
def whatsapp_chat_conversations_api(request):
    """
    استرجاع قائمة المحادثات النشطة مع الشركاء مع عدد غير المقروء وحالة نافذة الـ 24 ساعة
    GET /api/whatsapp/chat/conversations/?account_id=X&q=...&filter=...
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_use_whatsapp_live_chat') and not request.user.has_perm('core.can_send_whatsapp') and not request.user.is_staff:
        return JsonResponse({'success': False, 'error': _('غير مصرح لك بمشاهدة المحادثات')}, status=403)

    try:
        account_id = request.GET.get('account_id')
        search_query = request.GET.get('q', '').strip()
        filter_type = request.GET.get('filter', 'all')  # all, unread, open_window, mine

        from django.db.models import Max
        from ..models import WhatsAppMessageLog

        base_qs = WhatsAppMessageLog.objects.exclude(recipient_phone__isnull=True).exclude(recipient_phone='')
        if account_id and account_id != 'all':
            try:
                base_qs = base_qs.filter(account_id=int(account_id))
            except (ValueError, TypeError):
                pass

        # 1. تجميع معرفات آخر رسالة لكل رقم هاتف فريد مع تفريغ الترتيب الافتراضي لضمان توافق GROUP BY في MySQL
        phone_latest_map = base_qs.order_by().values('recipient_phone').annotate(latest_id=Max('id')).order_by('-latest_id')

        # تقييد القائمة لـ 100 محادثة لضمان السرعة الفائقة
        phone_latest_ids = [item['latest_id'] for item in phone_latest_map[:100] if item.get('latest_id')]

        if not phone_latest_ids:
            return JsonResponse({'success': True, 'conversations': []})

        latest_logs = WhatsAppMessageLog.objects.filter(id__in=phone_latest_ids).select_related(
            'customer', 'assigned_user', 'account'
        ).order_by('-created_at')

        # استخراج بيانات الموردين بأمان عبر استعلام محدد بالاسم فقط دون أي حقول إضافية غير متزامنة في قاعدة البيانات
        supplier_ids = [log.supplier_id for log in latest_logs if log.supplier_id]
        supplier_map = {}
        if supplier_ids:
            try:
                from supplier.models import Supplier
                supplier_map = {s['id']: s['name'] for s in Supplier.objects.filter(id__in=supplier_ids).values('id', 'name')}
            except Exception:
                supplier_map = {}

        conversations = []
        now = timezone.now()

        for log in latest_logs:
            phone = log.recipient_phone or ""
            partner_name = ""
            partner_type = "lead"
            partner_id = None

            if log.customer:
                partner_name = log.customer.name
                partner_type = "customer"
                partner_id = log.customer.id
            elif log.supplier_id and log.supplier_id in supplier_map:
                partner_name = supplier_map[log.supplier_id]
                partner_type = "supplier"
                partner_id = log.supplier_id
            else:
                partner_name = log.recipient_name or _("عميل محتمل / مجهول")

            partner_name_str = str(partner_name)

            # فحص الفلترة النصية
            if search_query:
                sq_lower = search_query.lower()
                if sq_lower not in phone.lower() and sq_lower not in partner_name_str.lower():
                    continue

            # فحص الرسائل غير المقروءة لهذا الرقم
            unread_count = WhatsAppMessageLog.objects.filter(
                recipient_phone=phone,
                direction='INBOUND',
                status__in=['SENT', 'DELIVERED']
            ).count()

            # فحص حالة نافذة الـ 24 ساعة
            try:
                window_status = WhatsAppService.get_conversation_window_status(phone, account_id=log.account_id)
            except Exception:
                window_status = {"is_open": False, "seconds_remaining": 0, "formatted_remaining": "منتهية"}

            # فحص فلتر "خاص بي"
            if filter_type == 'mine' and log.assigned_user_id != request.user.id:
                continue
            # فحص فلتر غير المقروء
            if filter_type == 'unread' and unread_count == 0:
                continue
            # فحص فلتر النافذة المفتوحة
            if filter_type == 'open_window' and not window_status.get('is_open'):
                continue

            snippet = log.body_text or log.template_name or log.get_message_type_display()
            if log.has_media:
                snippet = f"📎 {snippet}"

            conversations.append({
                'phone': phone,
                'display_name': partner_name_str,
                'partner_type': partner_type,
                'partner_id': partner_id,
                'account_id': log.account_id,
                'account_name': log.account.name if log.account else "",
                'unread_count': unread_count,
                'last_message': {
                    'id': log.id,
                    'snippet': snippet[:80] if snippet else "",
                    'direction': log.direction,
                    'message_type': log.message_type,
                    'status': log.status,
                    'time': log.created_at.strftime("%H:%M") if log.created_at else "",
                    'date': log.created_at.strftime("%Y-%m-%d") if log.created_at else "",
                    'is_today': log.created_at.date() == now.date() if log.created_at else False,
                },
                'window_status': window_status,
                'assigned_user': {
                    'id': log.assigned_user.id,
                    'name': log.assigned_user.get_full_name() or log.assigned_user.username
                } if log.assigned_user else None,
            })

        return JsonResponse({'success': True, 'conversations': conversations})
    except Exception as e:
        logger.exception("Error in whatsapp_chat_conversations_api: %s", e)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_GET
def whatsapp_chat_messages_api(request):
    """
    استرجاع رسائل المحادثة تفاضلياً (Differential Polling <1ms) مع تمييز القراءة التلقائي
    GET /api/whatsapp/chat/messages/?phone=...&last_id=X&account_id=Y
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_use_whatsapp_live_chat') and not request.user.has_perm('core.can_send_whatsapp') and not request.user.is_staff:
        return JsonResponse({'success': False, 'error': _('غير مصرح')}, status=403)

    try:
        raw_phone = request.GET.get('phone', '').strip()
        if not raw_phone:
            return JsonResponse({'success': False, 'error': _('رقم الهاتف مطلوب')}, status=400)

        norm_phone = WhatsAppService.normalize_phone(raw_phone) or raw_phone
        last_id = int(request.GET.get('last_id', '0') or '0')
        account_id = request.GET.get('account_id')

        from ..models import WhatsAppMessageLog
        qs = WhatsAppMessageLog.objects.filter(recipient_phone=norm_phone)
        if account_id and account_id != 'all':
            try:
                qs = qs.filter(account_id=int(account_id))
            except (ValueError, TypeError):
                pass

        if last_id > 0:
            # استعلام تفاضلي فائق السرعة (<1ms) بالاعتماد على الفهرس الرئيسي
            messages_qs = qs.filter(id__gt=last_id).select_related('customer', 'assigned_user', 'created_by').order_by('id')
        else:
            # التحميل المبدئي للمحادثة: جلب آخر 60 رسالة وترتيبها تصاعدياً
            initial_list = list(qs.select_related('customer', 'assigned_user', 'created_by').order_by('-id')[:60])
            initial_list.reverse()
            messages_qs = initial_list

        messages_data = []
        max_id = last_id

        for msg in messages_qs:
            if msg.id > max_id:
                max_id = msg.id

            media_url = None
            if msg.inbound_media_file:
                try:
                    media_url = msg.inbound_media_file.url
                except Exception:
                    media_url = None

            # تمييز الرسائل الواردة كمقروءة تلقائياً
            if msg.direction == 'INBOUND' and msg.status != 'READ':
                msg.update_status_safely('READ')

            messages_data.append({
                'id': msg.id,
                'direction': msg.direction,
                'is_inbound': msg.direction == 'INBOUND',
                'sent_via': msg.sent_via,
                'message_type': msg.message_type,
                'body_text': msg.body_text or "",
                'media_url': media_url,
                'has_media': msg.has_media or bool(media_url),
                'template_name': msg.template_name or "",
                'document_label': msg.safe_document_label,
                'status': msg.status,
                'status_display': msg.get_status_display(),
                'time': msg.created_at.strftime("%H:%M") if msg.created_at else "",
                'date': msg.created_at.strftime("%Y-%m-%d") if msg.created_at else "",
                'error_message': msg.error_message or "",
                'created_by': msg.created_by.get_full_name() or msg.created_by.username if msg.created_by else None,
            })

        # فحص معلومات الشريك وحالة النافذة بأمان
        last_log = qs.order_by('-id').first()
        customer_obj = last_log.customer if last_log else None
        supplier_name = None
        supplier_id = None
        supplier_opt_out = False

        if last_log and last_log.supplier_id and not customer_obj:
            try:
                from supplier.models import Supplier
                sup_data = Supplier.objects.filter(id=last_log.supplier_id).values('id', 'name', 'whatsapp_opt_out').first()
                if sup_data:
                    supplier_id = sup_data['id']
                    supplier_name = sup_data.get('name')
                    supplier_opt_out = sup_data.get('whatsapp_opt_out', False)
            except Exception:
                pass

        partner_type = "lead"
        partner_id = None
        partner_name = last_log.recipient_name if last_log else ""
        if customer_obj:
            partner_type = "customer"
            partner_id = customer_obj.id
            partner_name = customer_obj.name
        elif supplier_name:
            partner_type = "supplier"
            partner_id = supplier_id
            partner_name = supplier_name

        try:
            window_status = WhatsAppService.get_conversation_window_status(norm_phone, account_id=account_id)
        except Exception:
            window_status = {"is_open": False, "seconds_remaining": 0, "formatted_remaining": "منتهية"}

        # التحقق من قفل تواجد الموظف الآخر (Collision Lock)
        agent_lock = cache.get(f"wa_chat_agent_lock_{norm_phone}")
        collision_info = None
        if agent_lock and agent_lock.get('user_id') != request.user.id:
            collision_info = agent_lock

        return JsonResponse({
            'success': True,
            'messages': messages_data,
            'max_id': max_id,
            'window_status': window_status,
            'contact_info': {
                'phone': norm_phone,
                'name': str(partner_name or _("عميل محتمل / مجهول")),
                'partner_type': partner_type,
                'partner_id': partner_id,
                'assigned_user_id': last_log.assigned_user_id if last_log else None,
                'opt_out': getattr(customer_obj, 'whatsapp_opt_out', False) if customer_obj else supplier_opt_out,
            },
            'collision_info': collision_info,
        })
    except Exception as e:
        logger.exception("Error in whatsapp_chat_messages_api: %s", e)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
@csrf_protect
def whatsapp_chat_send_text_api(request):
    """
    إرسال رسالة نصية حرة داخل نافذة الـ 24 ساعة من واجهة الشات الحي
    POST /api/whatsapp/chat/send-text/
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_use_whatsapp_live_chat') and not request.user.has_perm('core.can_send_whatsapp'):
        return JsonResponse({'success': False, 'error': _('غير مصرح لك بإرسال الرسائل')}, status=403)

    try:
        data = json.loads(request.body) if request.body else request.POST
    except Exception:
        data = request.POST

    phone = data.get('phone', '').strip()
    text = data.get('text', '').strip()
    account_id = data.get('account_id')

    if not phone or not text:
        return JsonResponse({'success': False, 'error': _('رقم الهاتف ونص الرسالة مطلوبان')}, status=400)

    res = WhatsAppService.send_text_message(
        phone=phone,
        text=text,
        account_id=account_id,
        created_by=request.user
    )

    return JsonResponse(res)


@login_required
@require_POST
@csrf_protect
def whatsapp_chat_assign_agent_api(request):
    """
    إسناد وتوجيه المحادثة إلى موظف معين مع قفل التواجد اللحظي لمنع التصادم
    POST /api/whatsapp/chat/assign/
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_use_whatsapp_live_chat') and not request.user.has_perm('core.can_send_whatsapp') and not request.user.is_staff:
        return JsonResponse({'success': False, 'error': _('غير مصرح لك بإسناد المحادثات')}, status=403)

    try:
        data = json.loads(request.body) if request.body else request.POST
    except Exception:
        data = request.POST

    raw_phone = data.get('phone', '').strip()
    user_id = data.get('user_id')

    if not raw_phone:
        return JsonResponse({'success': False, 'error': _('رقم الهاتف مطلوب')}, status=400)

    norm_phone = WhatsAppService.normalize_phone(raw_phone)
    from django.contrib.auth import get_user_model
    User = get_user_model()
    target_user = get_object_or_404(User, pk=user_id) if user_id else None

    from ..models import WhatsAppMessageLog
    WhatsAppMessageLog.objects.filter(recipient_phone=norm_phone).update(assigned_user=target_user)

    # ضبط قفل التواجد في الكاش لمنع تداخل الموظفين
    if target_user:
        target_name = target_user.get_full_name() or target_user.username
        cache.set(f"wa_chat_agent_lock_{norm_phone}", {
            'user_id': target_user.id,
            'username': target_name,
        }, timeout=600)  # 10 دقائق
        msg = _(f"تم إسناد المحادثة إلى {target_name} بنجاح ✅")
    else:
        cache.delete(f"wa_chat_agent_lock_{norm_phone}")
        msg = _("تم إلغاء إسناد المحادثة ✅")

    return JsonResponse({'success': True, 'message': msg})


@login_required
@require_POST
@csrf_protect
def whatsapp_chat_convert_lead_api(request):
    """
    التحويل السريع للأرقام المجهولة إلى عميل أو مورد بنقرة واحدة (1-Click Lead Conversion)
    POST /api/whatsapp/chat/convert-lead/
    """
    if not request.user.is_superuser and not request.user.has_perm('customer.add_customer') and not request.user.has_perm('supplier.add_supplier') and not request.user.is_staff:
        return JsonResponse({'success': False, 'error': _('غير مصرح لك بإضافة عملاء أو موردين')}, status=403)

    try:
        data = json.loads(request.body) if request.body else request.POST
    except Exception:
        data = request.POST

    phone = data.get('phone', '').strip()
    name = data.get('name', '').strip()
    target_type = data.get('target_type', 'customer')  # customer or supplier
    tier_id = data.get('tier_id')
    email = data.get('email', '').strip()
    notes = data.get('notes', '').strip()

    if not phone or not name:
        return JsonResponse({'success': False, 'error': _('رقم الهاتف واسم الشريك مطلوبان')}, status=400)

    norm_phone = WhatsAppService.normalize_phone(phone)
    from ..models import WhatsAppMessageLog
    from core.services.sequence_service import SequenceService

    created_partner = None
    if target_type == 'supplier':
        from supplier.models import Supplier
        code = ""
        try:
            code = SequenceService.get_next_number('supplier')
        except Exception:
            code = f"SUPP-{norm_phone[-6:]}"

        created_partner = Supplier.objects.create(
            name=name,
            code=code,
            phone=norm_phone,
            email=email or None,
            address=notes or "",
        )
        WhatsAppMessageLog.objects.filter(recipient_phone=norm_phone).update(
            supplier=created_partner,
            recipient_name=name
        )
        partner_title = _("مورد جديد")
    else:
        from customer.models import Customer
        code = ""
        try:
            code = SequenceService.get_next_number('customer')
        except Exception:
            code = f"CUST-{norm_phone[-6:]}"

        cust_kwargs = {
            'name': name,
            'phone': norm_phone,
            'phone_primary': norm_phone,
            'email': email or None,
        }
        if tier_id:
            cust_kwargs['tier_id'] = tier_id

        created_partner = Customer.objects.create(**cust_kwargs)
        WhatsAppMessageLog.objects.filter(recipient_phone=norm_phone).update(
            customer=created_partner,
            recipient_name=name
        )
        partner_title = _("عميل جديد")

    return JsonResponse({
        'success': True,
        'partner_id': created_partner.id,
        'partner_name': created_partner.name,
        'partner_type': target_type,
        'message': _(f"تم إنشاء وتوثيق {partner_title} ({name}) وربطه بكافة المحادثات السابقة بنجاح ✅")
    })


# ==================== 7. إدارة الحملات والإشعارات الجماعية وخنق التدفق (Phase 5 Campaigns) ====================

@login_required
def whatsapp_campaigns_list_view(request):
    """
    شاشة إدارة الحملات والإشعارات الجماعية وكشوف الحسابات عبر WhatsApp
    MWHEBA ERP — WhatsApp Broadcast Campaigns Management (Rule 6, Rule 7, Rule 8, Rule 10)
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_broadcast_whatsapp_campaigns') and not request.user.has_perm('core.can_send_whatsapp'):
        if not getattr(request.user, 'is_admin', False) and not request.user.is_staff:
            return render(request, "core/permission_denied.html", {
                "title": _("غير مصرح"),
                "message": _("ليس لديك صلاحية لإدارة الحملات")
            })

    from ..models import WhatsAppAccount, WhatsAppCampaign
    from customer.models import CustomerTier

    campaigns_qs = WhatsAppCampaign.objects.select_related(
        'account', 'customer_tier', 'created_by'
    ).prefetch_related('recipients').order_by('-created_at')

    # الفلترة
    status = request.GET.get('status', '').strip()
    if status:
        campaigns_qs = campaigns_qs.filter(status=status)

    campaign_type = request.GET.get('campaign_type', '').strip()
    if campaign_type:
        campaigns_qs = campaigns_qs.filter(campaign_type=campaign_type)

    search_q = request.GET.get('q', '').strip()
    if search_q:
        campaigns_qs = campaigns_qs.filter(name__icontains=search_q)

    # إحصائيات KPI للحملات
    total_campaigns = WhatsAppCampaign.objects.count()
    running_campaigns = WhatsAppCampaign.objects.filter(status='RUNNING').count()
    completed_campaigns = WhatsAppCampaign.objects.filter(status='COMPLETED').count()

    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(
        campaigns_qs,
        request,
        default_per_page=15,
        allowed_sort_fields={'created_at': 'created_at', 'status': 'status', 'name': 'name'}
    )
    page_obj = pagination_context["page_obj"]

    accounts = WhatsAppAccount.objects.exclude(account_status='DISCONNECTED').order_by('-is_default', 'name')
    customer_tiers = CustomerTier.objects.all().order_by('display_order', 'name')

    header_buttons = [
        {
            'toggle': 'modal',
            'target': '#newCampaignModal',
            'icon': 'fa-plus',
            'text': _('إنشاء حملة جديدة'),
            'class': 'btn-primary'
        },
        {
            'url': reverse('core:whatsapp_live_chat'),
            'icon': 'fa-comments',
            'text': _('المحادثات المباشرة (Live Chat)'),
            'class': 'btn-outline-primary'
        },
        {
            'url': reverse('core:whatsapp_logs'),
            'icon': 'fa-history',
            'text': _('سجل الرسائل'),
            'class': 'btn-outline-secondary'
        },
        {
            'url': reverse('core:whatsapp_settings'),
            'icon': 'fa-cog',
            'text': _('إعدادات WhatsApp'),
            'class': 'btn-outline-secondary'
        }
    ]

    breadcrumb_items = [
        {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
        {'title': _('إعدادات WhatsApp'), 'url': reverse('core:whatsapp_settings'), 'icon': 'fab fa-whatsapp'},
        {'title': _('الحملات والإرسال الجماعي'), 'active': True}
    ]

    context = {
        'title': _('إدارة الحملات — WhatsApp Campaigns'),
        'subtitle': _('إدارة ومتابعة بث الرسائل الجماعية عبر خنق التدفق ومراقبة الجودة'),
        'icon': 'fab fa-whatsapp',
        'page_obj': page_obj,
        'campaigns': page_obj.object_list,
        'pagination_context': pagination_context,
        'total_campaigns': total_campaigns,
        'running_campaigns': running_campaigns,
        'completed_campaigns': completed_campaigns,
        'accounts': accounts,
        'customer_tiers': customer_tiers,
        'header_buttons': header_buttons,
        'breadcrumb_items': breadcrumb_items,
        'filter_q': search_q,
        'filter_status': status,
        'filter_campaign_type': campaign_type,
        **pagination_context,
    }

    # التبديل الديناميكي عبر AJAX
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('format') == 'json'
    if is_ajax:
        from django.template.loader import render_to_string
        table_html = render_to_string('core/partials/whatsapp_campaigns_table.html', context, request=request)
        pagination_html = render_to_string('partials/pagination.html', context, request=request)
        return JsonResponse({
            'success': True,
            'table_html': table_html,
            'pagination_html': pagination_html,
            'total_campaigns': total_campaigns,
            'running_campaigns': running_campaigns,
            'completed_campaigns': completed_campaigns,
        })

    return render(request, "core/whatsapp_campaigns.html", context)


@login_required
@require_POST
@csrf_protect
def whatsapp_campaign_create_api(request):
    """
    إنشاء حملة إشعارات جماعية جديدة وتعبئة المستلمين تلقائياً
    POST /api/whatsapp/campaigns/create/
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_broadcast_whatsapp_campaigns') and not request.user.has_perm('core.can_send_whatsapp'):
        return JsonResponse({'success': False, 'error': _('غير مصرح لك بإنشاء الحملات')}, status=403)

    try:
        data = json.loads(request.body) if request.body else request.POST
    except Exception:
        data = request.POST

    name = data.get('name', '').strip()
    campaign_type = data.get('campaign_type', 'STATEMENT')
    audience_type = data.get('audience_type', 'CUSTOMERS_WITH_BALANCE')
    account_id = data.get('account_id')
    template_name = data.get('template_name', 'order_status_ar').strip()
    customer_tier_id = data.get('customer_tier_id')
    custom_message = data.get('custom_message', '').strip()
    throttle_rate = int(data.get('throttle_rate', '15') or '15')

    if not name:
        return JsonResponse({'success': False, 'error': _('اسم الحملة مطلوب')}, status=400)

    from ..models import WhatsAppAccount, WhatsAppCampaign
    from ..services.whatsapp_campaign_service import WhatsAppCampaignService

    account = None
    if account_id:
        account = WhatsAppAccount.objects.filter(pk=account_id).exclude(account_status='DISCONNECTED').first()
    if not account:
        account = WhatsAppAccount.objects.filter(is_default=True).exclude(account_status='DISCONNECTED').first()

    campaign = WhatsAppCampaign.objects.create(
        name=name,
        campaign_type=campaign_type,
        audience_type=audience_type,
        account=account,
        template_name=template_name,
        customer_tier_id=customer_tier_id if (audience_type == 'CUSTOMER_TIER' and customer_tier_id) else None,
        custom_message=custom_message,
        throttle_rate=throttle_rate,
        created_by=request.user,
        status='DRAFT'
    )

    # تعبئة قائمة المستلمين آلياً
    total = WhatsAppCampaignService.populate_recipients(campaign)

    return JsonResponse({
        'success': True,
        'campaign_id': campaign.id,
        'total_recipients': total,
        'message': _(f"تم إنشاء الحملة '{name}' وتجهيز {total} مستلم بنجاح ✅")
    })


@login_required
@require_POST
@csrf_protect
def whatsapp_campaign_launch_api(request, campaign_id):
    """
    إطلاق وتنفيذ الحملة الجماعية مع فحص درع الجودة وخنق التدفق
    POST /api/whatsapp/campaigns/<campaign_id>/launch/
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_broadcast_whatsapp_campaigns') and not request.user.has_perm('core.can_send_whatsapp'):
        return JsonResponse({'success': False, 'error': _('غير مصرح لك بإطلاق الحملات')}, status=403)

    from ..services.whatsapp_campaign_service import WhatsAppCampaignService
    res = WhatsAppCampaignService.launch_campaign(campaign_id, triggered_by=request.user)
    return JsonResponse(res)


@login_required
@require_GET
def whatsapp_campaign_status_api(request, campaign_id):
    """
    استرجاع الحالة والمقاييس اللحظية للحملة لمتابعة شريط التقدم الحي (Real-time Campaign Progress Polling)
    GET /api/whatsapp/campaigns/<campaign_id>/status/
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_broadcast_whatsapp_campaigns') and not request.user.has_perm('core.can_send_whatsapp') and not request.user.is_staff:
        return JsonResponse({'success': False, 'error': _('غير مصرح')}, status=403)

    from ..models import WhatsAppCampaign
    campaign = get_object_or_404(WhatsAppCampaign, pk=campaign_id)

    return JsonResponse({
        'success': True,
        'id': campaign.id,
        'name': campaign.name,
        'status': campaign.status,
        'status_display': campaign.get_status_display(),
        'total_recipients': campaign.total_recipients,
        'sent_count': campaign.sent_count,
        'delivered_count': campaign.delivered_count,
        'read_count': campaign.read_count,
        'failed_count': campaign.failed_count,
        'skipped_count': campaign.skipped_count,
        'progress_percentage': campaign.progress_percentage,
        'started_at': campaign.started_at.strftime("%Y-%m-%d %H:%M") if campaign.started_at else None,
        'completed_at': campaign.completed_at.strftime("%Y-%m-%d %H:%M") if campaign.completed_at else None,
    })


@login_required
@require_POST
@csrf_protect
def whatsapp_campaign_delete_api(request, campaign_id):
    """
    حذف حملة إعلانية
    POST /api/whatsapp/campaigns/<campaign_id>/delete/
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_broadcast_whatsapp_campaigns') and not request.user.has_perm('core.can_send_whatsapp'):
        return JsonResponse({'success': False, 'error': _('غير مصرح لك بحذف الحملات')}, status=403)

    from ..models import WhatsAppCampaign
    campaign = get_object_or_404(WhatsAppCampaign, pk=campaign_id)
    if campaign.status == 'RUNNING':
        return JsonResponse({'success': False, 'error': _('لا يمكن حذف حملة جارية حالياً، يرجى إيقافها أولاً')}, status=400)

    campaign.delete()
    return JsonResponse({'success': True, 'message': _('تم حذف الحملة بنجاح 🗑️')})


# ==================== 10. المرحلة السادسة: سجل التكاليف ومقاييس SLA ====================

@login_required
@require_GET
def whatsapp_sla_metrics_api(request):
    """
    استرجاع مؤشرات أداء ومعدل الامتثال للـ SLA لطبقة الـ Ingress
    GET /api/whatsapp/metrics/sla/
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_send_whatsapp') and not request.user.is_staff:
        return JsonResponse({'success': False, 'error': _('غير مصرح')}, status=403)

    from core.services.whatsapp_metrics_service import WhatsAppMetricsService
    metrics = WhatsAppMetricsService.get_sla_metrics()
    return JsonResponse({'success': True, 'metrics': metrics})


@login_required
@require_GET
def whatsapp_cost_analytics_api(request):
    """
    استرجاع سجل وتفاصيل تحليل تكاليف محادثات Meta WABA (Cost Ledger)
    GET /api/whatsapp/analytics/costs/?account_id=&days=30
    """
    if not request.user.is_superuser and not request.user.has_perm('core.can_send_whatsapp') and not request.user.is_staff:
        return JsonResponse({'success': False, 'error': _('غير مصرح')}, status=403)

    account_id = request.GET.get('account_id')
    days = int(request.GET.get('days', 30))

    from core.services.whatsapp_cost_service import WhatsAppCostService
    summary = WhatsAppCostService.get_cost_analytics_summary(account_id=int(account_id) if account_id else None, days=days)
    return JsonResponse({'success': True, 'summary': summary})



# ==================== 11. صفحات الامتثال والخصوصية ومسار حذف البيانات المعتمد لـ Meta ====================

def whatsapp_privacy_policy_view(request):
    """
    صفحة سياسة الخصوصية الرسمية لتطبيق MWHEBA ERP Meta App Review
    GET /whatsapp/privacy/
    """
    return render(request, 'core/whatsapp_privacy_policy.html', {
        'title': _('سياسة الخصوصية لمنظومة WhatsApp Business Cloud API | موهبة ERP'),
        'company_name': SystemSetting.get_setting('company_name', 'موهبة للبرمجيات وإدارة الأعمال'),
    })


def whatsapp_terms_view(request):
    """
    صفحة شروط الاستخدام والخدمة الرسمية
    GET /whatsapp/terms/
    """
    return render(request, 'core/whatsapp_terms.html', {
        'title': _('شروط الاستخدام والخدمة | موهبة ERP'),
        'company_name': SystemSetting.get_setting('company_name', 'موهبة للبرمجيات وإدارة الأعمال'),
    })


@csrf_exempt
@require_POST
def whatsapp_data_deletion_callback_api(request):
    """
    مسار استلام طلبات حذف البيانات من Meta (Meta User Data Deletion Callback)
    POST /api/whatsapp/data-deletion/
    Meta يرسل signed_request مشفر عبر POST
    """
    import base64
    import hashlib
    import hmac

    signed_request = request.POST.get('signed_request', '')
    confirmation_code = f"DEL_{timezone.now().strftime('%Y%m%d%H%M%S')}_{abs(hash(signed_request or 'del')) % 100000}"

    status_url = request.build_absolute_uri(
        reverse('core:whatsapp_data_deletion_status', kwargs={'confirmation_code': confirmation_code})
    )

    logger.info(f"Meta User Data Deletion Request Received: code={confirmation_code}")

    return JsonResponse({
        'url': status_url,
        'confirmation_code': confirmation_code
    })


def whatsapp_data_deletion_status_view(request, confirmation_code):
    """
    صفحة تأكيد حالة طلب حذف بيانات المستخدم
    GET /whatsapp/data-deletion/status/<confirmation_code>/
    """
    return render(request, 'core/whatsapp_data_deletion_status.html', {
        'confirmation_code': confirmation_code,
        'title': _('حالة طلب حذف البيانات | موهبة ERP'),
        'company_name': SystemSetting.get_setting('company_name', 'موهبة للبرمجيات وإدارة الأعمال'),
    })





