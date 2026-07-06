from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from core.models import SystemModule

def check_work_orders_enabled(view_func):
    """
    Decorator للتحقق من تفعيل موديول أوامر الشغل في إعدادات النظام
    """
    def _wrapped_view(request, *args, **kwargs):
        try:
            module = SystemModule.objects.get(code='work_orders')
            if not module.is_enabled:
                return render(request, "core/permission_denied.html", {
                    "title": _("تطبيق غير مفعل"),
                    "message": _("تطبيق إدارة أوامر الشغل غير مفعل حالياً في إعدادات النظام. يرجى تفعيله من إدارة التطبيقات.")
                })
        except SystemModule.DoesNotExist:
            return render(request, "core/permission_denied.html", {
                "title": _("تطبيق غير موجود"),
                "message": _("تطبيق إدارة أوامر الشغل غير مثبت في النظام.")
            })
        return view_func(request, *args, **kwargs)
    return _wrapped_view
