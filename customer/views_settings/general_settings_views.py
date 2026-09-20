"""عروض إعدادات العملاء والترقيم والائتمان العامة"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from ..models import CustomerGeneralSettings
from ..forms_settings.general_settings_forms import CustomerGeneralSettingsForm


@login_required
@require_http_methods(["GET", "POST"])
def customer_general_settings_view(request):
    """عرض وتعديل إعدادات العملاء العامة والترقيم التلقائي وسياسة الائتمان"""
    settings_obj = CustomerGeneralSettings.get_settings()
    
    if request.method == "POST":
        form = CustomerGeneralSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({
                    "success": True,
                    "message": _("تم حفظ إعدادات العملاء العامة بنجاح"),
                })
            messages.success(request, _("تم حفظ إعدادات العملاء العامة بنجاح"))
            return redirect(reverse("customer:settings_index") + "?tab=credit_policy")
        else:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({
                    "success": False,
                    "errors": form.errors,
                    "message": _("يرجى تصحيح الأخطاء الواردة في النموذج"),
                }, status=400)
            messages.error(request, _("يرجى تصحيح الأخطاء الواردة في النموذج"))
    else:
        form = CustomerGeneralSettingsForm(instance=settings_obj)
        
    context = {
        "form": form,
        "settings_obj": settings_obj,
        "active_menu": "customers",
        "active_submenu": "customer_settings",
        "page_title": _("إعدادات العملاء وسياسات الائتمان"),
        "page_subtitle": _("إدارة بادئة الترقيم والحدود الائتمانية وفترات السماح"),
        "page_icon": "fas fa-shield-alt",
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": _("العملاء"), "url": reverse("customer:customer_list"), "icon": "fas fa-users"},
            {"title": _("إعدادات العملاء"), "url": reverse("customer:settings_index"), "icon": "fas fa-cog"},
            {"title": _("سياسات الائتمان والترقيم"), "active": True},
        ],
    }
    return render(request, "customer/settings/credit_policy/form.html", context)
