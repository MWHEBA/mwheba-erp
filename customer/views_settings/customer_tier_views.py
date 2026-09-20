"""عروض إدارة الشرائح والتصنيفات التجارية للعملاء"""
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from ..models import CustomerTier, PaymentTerm
from ..forms_settings.customer_tier_forms import (
    CustomerTierForm,
    CustomerTierReorderForm,
    CustomerTierDeleteForm,
)


@login_required
def customer_tier_list(request):
    """عرض قائمة الشرائح التجارية للعملاء"""
    tiers = CustomerTier.objects.all().order_by("display_order", "name")
    
    stats = {
        "tiers_total": CustomerTier.objects.count(),
        "tiers_active": CustomerTier.objects.filter(is_active=True).count(),
        "tiers_system": CustomerTier.objects.filter(is_system=True).count(),
    }
    
    context = {
        "tiers": tiers,
        "stats": stats,
        "active_menu": "customers",
        "active_submenu": "customer_settings",
        "page_title": _("الشرائح التجارية للعملاء"),
        "page_subtitle": _("إدارة وتصنيف شرائح العملاء وسياسات التسعير والائتمان الافتراضية"),
        "page_icon": "fas fa-users",
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": _("العملاء"), "url": reverse("customer:customer_list"), "icon": "fas fa-users"},
            {"title": _("الشرائح التجارية"), "active": True},
        ],
    }
    return render(request, "customer/settings/tiers/list.html", context)


@login_required
def customer_tier_create(request):
    """إضافة شريحة تجارية جديدة"""
    if request.method == "POST":
        form = CustomerTierForm(request.POST)
        if form.is_valid():
            tier = form.save()
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({
                    "success": True,
                    "message": _("تمت إضافة الشريحة التجارية بنجاح"),
                    "tier": {
                        "id": tier.id,
                        "name": tier.name,
                        "code": tier.code,
                        "color": tier.color,
                        "icon": tier.icon,
                    }
                })
            messages.success(request, _("تمت إضافة الشريحة التجارية بنجاح"))
            return redirect("customer:settings_index")
        else:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors}, status=400)
    else:
        form = CustomerTierForm()
    
    context = {
        "form": form,
        "title": _("إضافة شريحة تجارية جديدة"),
        "action_url": reverse("customer:tier_create"),
    }
    return render(request, "customer/settings/tiers/form_modal.html", context)


@login_required
def customer_tier_edit(request, pk):
    """تعديل شريحة تجارية"""
    tier = get_object_or_404(CustomerTier, pk=pk)
    
    if request.method == "POST":
        form = CustomerTierForm(request.POST, instance=tier)
        if form.is_valid():
            tier = form.save()
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({
                    "success": True,
                    "message": _("تم تحديث الشريحة التجارية بنجاح"),
                    "tier": {
                        "id": tier.id,
                        "name": tier.name,
                        "code": tier.code,
                    }
                })
            messages.success(request, _("تم تحديث الشريحة التجارية بنجاح"))
            return redirect("customer:settings_index")
        else:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors}, status=400)
    else:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.GET.get("format") == "json" or "application/json" in request.headers.get("Accept", ""):
            return JsonResponse({
                "success": True,
                "data": {
                    "id": tier.id,
                    "name": tier.name,
                    "code": tier.code,
                    "display_order": tier.display_order,
                    "description": tier.description,
                    "default_price_list": tier.default_price_list_id,
                    "discount_percentage": str(tier.discount_percentage),
                    "default_payment_term": tier.default_payment_term_id,
                    "default_credit_limit": str(tier.default_credit_limit),
                    "default_risk_category": tier.default_risk_category,
                    "is_active": tier.is_active,
                }
            })
        form = CustomerTierForm(instance=tier)
    
    context = {
        "form": form,
        "tier": tier,
        "title": _("تعديل الشريحة: %(name)s") % {"name": tier.name},
        "action_url": reverse("customer:tier_edit", kwargs={"pk": tier.pk}),
    }
    return render(request, "customer/settings/tiers/form_modal.html", context)


@login_required
@require_POST
def customer_tier_delete(request, pk):
    """حذف شريحة تجارية بشكل آمن"""
    tier = get_object_or_404(CustomerTier, pk=pk)
    
    if tier.is_system:
        messages.error(request, _("لا يمكن حذف شريحة نظامية أساسية."))
        return redirect("customer:settings_index")
        
    if tier.customers.exists():
        messages.error(request, _("لا يمكن حذف هذه الشريحة لوجود عملاء مرتبطين بها."))
        return redirect("customer:settings_index")
        
    tier_name = tier.name
    tier.delete()
    
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": True, "message": _("تم حذف الشريحة '%(name)s' بنجاح") % {"name": tier_name}})
        
    messages.success(request, _("تم حذف الشريحة '%(name)s' بنجاح") % {"name": tier_name})
    return redirect("customer:settings_index")


@login_required
@require_POST
def customer_tier_reorder(request):
    """إعادة ترتيب الشرائح التجارية عبر السحب والإفلات AJAX"""
    try:
        data = json.loads(request.body)
        ordered_ids = data.get("ordered_ids", [])
        
        with transaction.atomic():
            for index, tier_id in enumerate(ordered_ids):
                CustomerTier.objects.filter(id=tier_id).update(display_order=index)
                
        return JsonResponse({"success": True, "message": _("تم تحديث ترتيب الشرائح بنجاح")})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
def customer_tier_toggle_status(request, pk):
    """تبديل حالة تفعيل الشريحة التجارية AJAX"""
    tier = get_object_or_404(CustomerTier, pk=pk)
    try:
        new_status = not tier.is_active
        if request.body:
            try:
                data = json.loads(request.body)
                if "is_active" in data:
                    new_status = bool(data.get("is_active"))
            except Exception:
                pass
        tier.is_active = new_status
        tier.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({
            "success": True,
            "is_active": tier.is_active,
            "message": _("تم تغيير حالة الشريحة بنجاح")
        })
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)



@login_required
def api_customer_tier_info(request, pk):
    """API endpoint لجلب البيانات المالية والتسعيرية للشريحة لتعبئتها في فورم العميل"""
    tier = get_object_or_404(CustomerTier, pk=pk, is_active=True)
    tier_dict = {
        "tier_id": tier.id,
        "id": tier.id,
        "name": tier.name,
        "code": tier.code,
        "default_price_list_id": tier.default_price_list_id or "",
        "default_price_list_name": tier.default_price_list.name if tier.default_price_list else "",
        "default_payment_term_id": tier.default_payment_term_id or "",
        "default_payment_term_name": tier.default_payment_term.name if tier.default_payment_term else "",
        "default_credit_limit": str(tier.default_credit_limit),
        "default_risk_category": tier.default_risk_category,
        "discount_percentage": str(tier.discount_percentage),
    }
    return JsonResponse({
        "success": True,
        "tier": tier_dict,
        "data": tier_dict,
    })


# Alias for backward compatibility
customer_tier_api_info = api_customer_tier_info

