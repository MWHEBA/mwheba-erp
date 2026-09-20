from functools import wraps
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from core.models import SystemModule

def check_work_orders_enabled(view_func):
    """
    Decorator للتحقق من تفعيل موديول أوامر الشغل في إعدادات النظام
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        is_ajax = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.headers.get('Accept') == 'application/json'
            or request.GET.get('precheck') == '1'
            or request.GET.get('ajax') == '1'
        )
        try:
            module = SystemModule.objects.get(code='work_orders')
            if not module.is_enabled:
                msg = _("تطبيق إدارة أوامر الشغل غير مفعل حالياً في إعدادات النظام. يرجى تفعيله من إدارة التطبيقات.")
                if is_ajax:
                    from django.http import JsonResponse
                    return JsonResponse({'success': False, 'error': 'module_disabled', 'message': str(msg)}, status=403)
                return render(request, "core/permission_denied.html", {
                    "title": _("تطبيق غير مفعل"),
                    "message": msg
                }, status=403)
        except SystemModule.DoesNotExist:
            msg = _("تطبيق إدارة أوامر الشغل غير مثبت في النظام.")
            if is_ajax:
                from django.http import JsonResponse
                return JsonResponse({'success': False, 'error': 'module_missing', 'message': str(msg)}, status=403)
            return render(request, "core/permission_denied.html", {
                "title": _("تطبيق غير موجود"),
                "message": msg
            }, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped_view
