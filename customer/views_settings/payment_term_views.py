"""عروض إدارة شروط الدفع والائتمان المعيارية"""
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from ..models import PaymentTerm
from ..forms_settings.payment_term_forms import PaymentTermForm, PaymentTermDeleteForm


@login_required
def payment_term_list(request):
    """عرض قائمة شروط الدفع"""
    terms = PaymentTerm.objects.all().order_by("days", "name")
    
    stats = {
        "terms_total": PaymentTerm.objects.count(),
        "terms_active": PaymentTerm.objects.filter(is_active=True).count(),
        "terms_credit": PaymentTerm.objects.filter(is_credit=True).count(),
    }
    
    context = {
        "terms": terms,
        "stats": stats,
        "active_menu": "customers",
        "active_submenu": "customer_settings",
        "page_title": _("شروط الدفع المعيارية"),
        "page_subtitle": _("إدارة فترات السداد والائتمان ونسب خصم تعجيل الدفع في النظام"),
        "page_icon": "fas fa-file-contract",
    }
    return render(request, "customer/settings/payment_terms/list.html", context)


@login_required
def payment_term_create(request):
    """إضافة شرط دفع جديد"""
    if request.method == "POST":
        form = PaymentTermForm(request.POST)
        if form.is_valid():
            term = form.save()
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({
                    "success": True,
                    "message": _("تمت إضافة شرط الدفع بنجاح"),
                    "payment_term": {
                        "id": term.id,
                        "name": term.name,
                        "code": term.code,
                        "days": term.days,
                    }
                })
            messages.success(request, _("تمت إضافة شرط الدفع بنجاح"))
            return redirect("customer:settings_index")
        else:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors}, status=400)
    else:
        form = PaymentTermForm()
    
    context = {
        "form": form,
        "title": _("إضافة شرط دفع معياري جديد"),
        "action_url": reverse("customer:payment_term_create"),
    }
    return render(request, "customer/settings/payment_terms/form_modal.html", context)


@login_required
def payment_term_edit(request, pk):
    """تعديل شرط دفع"""
    term = get_object_or_404(PaymentTerm, pk=pk)
    
    if request.method == "POST":
        form = PaymentTermForm(request.POST, instance=term)
        if form.is_valid():
            term = form.save()
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({
                    "success": True,
                    "message": _("تم تحديث شرط الدفع بنجاح"),
                    "payment_term": {
                        "id": term.id,
                        "name": term.name,
                        "code": term.code,
                    }
                })
            messages.success(request, _("تم تحديث شرط الدفع بنجاح"))
            return redirect("customer:settings_index")
        else:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors}, status=400)
    else:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.GET.get("format") == "json" or "application/json" in request.headers.get("Accept", ""):
            return JsonResponse({
                "success": True,
                "data": {
                    "id": term.id,
                    "name": term.name,
                    "code": term.code,
                    "days": term.days,
                    "is_credit": term.is_credit,
                    "discount_percentage": str(term.discount_percentage),
                    "discount_days": term.discount_days,
                    "is_default": term.is_default,
                    "is_active": term.is_active,
                }
            })
        form = PaymentTermForm(instance=term)
    
    context = {
        "form": form,
        "term": term,
        "title": _("تعديل شرط الدفع: %(name)s") % {"name": term.name},
        "action_url": reverse("customer:payment_term_edit", kwargs={"pk": term.pk}),
    }
    return render(request, "customer/settings/payment_terms/form_modal.html", context)


@login_required
@require_POST
def payment_term_delete(request, pk):
    """حذف شرط دفع بشكل آمن"""
    term = get_object_or_404(PaymentTerm, pk=pk)
    
    # فحص الارتباطات
    form = PaymentTermDeleteForm(term, {"confirm": True})
    if not form.is_valid():
        err_msg = form.errors.get("__all__", [_("لا يمكن حذف هذا الشرط لوجود سجلات مرتبطة به.")])[0]
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": False, "message": str(err_msg)}, status=400)
        messages.error(request, err_msg)
        return redirect("customer:settings_index")
        
    term_name = term.name
    term.delete()
    
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": True, "message": _("تم حذف شرط الدفع '%(name)s' بنجاح") % {"name": term_name}})
        
    messages.success(request, _("تم حذف شرط الدفع '%(name)s' بنجاح") % {"name": term_name})
    return redirect("customer:settings_index")


@login_required
@require_POST
def payment_term_toggle_status(request, pk):
    """تبديل حالة تفعيل شرط الدفع AJAX"""
    term = get_object_or_404(PaymentTerm, pk=pk)
    try:
        new_status = not term.is_active
        if request.body:
            try:
                data = json.loads(request.body)
                if "is_active" in data:
                    new_status = bool(data.get("is_active"))
            except Exception:
                pass
        term.is_active = new_status
        term.save(update_fields=["is_active"])
        return JsonResponse({
            "success": True,
            "is_active": term.is_active,
            "message": _("تم تغيير حالة شرط الدفع بنجاح")
        })
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)



@login_required
@require_POST
def payment_term_quick_add(request):
    """إضافة سريعة لشرط دفع من داخل شاشات المبيعات أو العملاء (Quick Add Modal AJAX)"""
    name = request.POST.get("name", "").strip()
    days = int(request.POST.get("days", 0) or 0)
    if not name:
        return JsonResponse({"success": False, "message": _("يرجى إدخال اسم شرط الدفع")}, status=400)
    
    term, created = PaymentTerm.objects.get_or_create(
        name=name,
        defaults={"days": days, "is_active": True}
    )
    return JsonResponse({
        "success": True,
        "message": _("تم إنشاء شرط الدفع بنجاح"),
        "term": {
            "id": term.id,
            "name": term.name,
            "days": term.days,
        },
        "data": {
            "id": term.id,
            "text": f"{term.name} ({term.days} {str(_('يوم'))})",
            "name": term.name,
            "days": term.days,
        }
    })
