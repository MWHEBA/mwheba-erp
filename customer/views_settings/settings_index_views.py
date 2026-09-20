"""عروض الصفحة الرئيسية الموحدة لإعدادات العملاء"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from ..models import CustomerTier, PaymentTerm, CustomerGeneralSettings, Customer
from ..forms_settings.general_settings_forms import CustomerGeneralSettingsForm


@login_required
def customer_settings_index(request):
    """عرض لوحة التحكم الموحدة لجميع إعدادات العملاء (الشرائح، شروط الدفع، سياسة الائتمان)"""
    active_tab = request.GET.get("tab", "tiers")
    
    tiers = CustomerTier.objects.all().order_by("display_order", "name")
    payment_terms = PaymentTerm.objects.all().order_by("-is_default", "name")
    general_settings = CustomerGeneralSettings.get_settings()
    general_settings_form = CustomerGeneralSettingsForm(instance=general_settings)
    
    context = {
        "active_tab": active_tab,
        "tiers": tiers,
        "payment_terms": payment_terms,
        "general_settings": general_settings,
        "general_settings_form": general_settings_form,
        "active_menu": "customers",
        "active_submenu": "customer_settings",
        "page_title": _("إعدادات العملاء"),
        "page_subtitle": _("إدارة الشرائح التجارية، شروط الدفع، وسياسات الرقابة الائتمانية والترقيم"),
        "page_icon": "fas fa-cogs",
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": _("العملاء"), "url": reverse("customer:customer_list"), "icon": "fas fa-users"},
            {"title": _("إعدادات العملاء"), "active": True},
        ],
    }
    return render(request, "customer/settings/index.html", context)
