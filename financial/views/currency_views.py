"""
currency_views.py - مناظر إدارة العملات، أسعار الصرف، ومقومات إعادة التقييم الدوري (IAS 21)
"""

import logging
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from financial.models.currency import Currency, ExchangeRate
from financial.services.exchange_rate_service import ExchangeRateService
from financial.services.fx_revaluation_service import FXRevaluationService

logger = logging.getLogger("financial.views.currency")


def format_clean_rate(val):
    if val is None:
        return None
    try:
        dec = Decimal(str(val))
        norm = dec.normalize()
        val_str = f"{norm:f}"
        if "." in val_str:
            val_str = val_str.rstrip("0").rstrip(".")
        return val_str
    except Exception:
        return str(val)


@login_required
def currency_list(request):
    """عرض قائمة العملات المعتمدة بالمؤسسة"""
    currencies = Currency.objects.all().order_by("-is_functional", "code")
    func_curr = ExchangeRateService.get_functional_currency()
    base_code = func_curr.code if func_curr else "EGP"

    today = timezone.now().date()
    for c in currencies:
        if c.is_functional:
            c.current_rate = Decimal("1")
            c.current_rate_display = "1"
            c.latest_rate_date = None
            c.age_days = 0
            c.age_status = "functional"
        else:
            try:
                rate_val = ExchangeRateService.get_rate(c.code, base_code)
                c.current_rate = rate_val
                c.current_rate_display = format_clean_rate(rate_val)
                latest_rate = ExchangeRate.objects.filter(
                    from_currency__code=c.code,
                    to_currency__code=base_code
                ).order_by("-effective_date", "-created_at").first()
                if latest_rate:
                    c.latest_rate_date = latest_rate.effective_date
                    c.age_days = (today - latest_rate.effective_date).days
                    if c.age_days <= 1:
                        c.age_status = "recent"
                    elif c.age_days <= 7:
                        c.age_status = "medium"
                    else:
                        c.age_status = "old"
                else:
                    c.latest_rate_date = None
                    c.age_days = 999
                    c.age_status = "old"
            except Exception:
                c.current_rate = None
                c.current_rate_display = None
                c.latest_rate_date = None
                c.age_days = 999
                c.age_status = "old"

    from django.urls import reverse
    header_buttons = [
        {
            "text": _("أسعار الصرف"),
            "icon": "fa-history",
            "url": reverse("financial:exchange_rate_list"),
            "class": "btn-outline-info"
        },
        {
            "text": _("تحديث الأسعار"),
            "icon": "fa-sync-alt",
            "onclick": "syncLiveExchangeRates()",
            "class": "btn-outline-primary"
        },
        {
            "text": _("إضافة عملة"),
            "icon": "fa-plus",
            "toggle": "modal",
            "target": "#quickAddCurrencyModal",
            "class": "btn-primary"
        }
    ]

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": "/", "icon": "fa-home"},
        {"title": _("الإدارة المالية"), "url": "#", "icon": "fa-landmark"},
        {"title": _("دليل العملات وأسعار الصرف"), "active": True}
    ]

    existing_codes = list(currencies.values_list("code", flat=True))

    return render(request, "financial/currency/currency_list.html", {
        "page_title": _("دليل العملات وأسعار الصرف"),
        "page_subtitle": _("إدارة العملات المعتمدة، أسعار الصرف الرسمية، وإعادة التقييم الدوري (IAS 21)"),
        "page_icon": "fas fa-coins",
        "header_buttons": header_buttons,
        "breadcrumb_items": breadcrumb_items,
        "currencies": currencies,
        "existing_codes": existing_codes,
        "base_currency": func_curr
    })


@login_required
def currency_create(request):
    """إضافة عملة"""
    if request.method == "POST":
        code = request.POST.get("code", "").strip().upper()
        name = request.POST.get("name", "").strip()
        symbol = request.POST.get("symbol", "").strip()

        if code and name and symbol:
            curr = Currency.objects.filter(code=code).first()
            if curr:
                messages.warning(request, f"العملة ({code} - {curr.name}) مسجلة بالفعل في دليل العملات المعتمدة!")
            else:
                Currency.objects.create(code=code, name=name, symbol=symbol, is_active=True)
                messages.success(request, f"تمت إضافة العملة ({code} - {name}) بنجاح.")
        else:
            messages.error(request, _("جميع البيانات مطلوبة."))
    return redirect("financial:currency_list")


@login_required
def currency_update(request, code):
    """تعديل بيانات العملة"""
    currency = get_object_or_404(Currency, code=code)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        symbol = request.POST.get("symbol", "").strip()
        is_active = request.POST.get("is_active") == "on" or request.POST.get("is_active") == "true"

        if name and symbol:
            currency.name = name
            currency.symbol = symbol
            if not currency.is_functional:
                currency.is_active = is_active
            currency.save()
            messages.success(request, _("تم تحديث بيانات العملة بنجاح."))
        else:
            messages.error(request, _("جميع البيانات مطلوبة."))
    return redirect("financial:currency_list")


@login_required
def currency_toggle_active(request, code):
    """تغيير حالة تفعيل العملة (تفعيل / تعطيل)"""
    currency = get_object_or_404(Currency, code=code)
    if currency.is_functional:
        messages.error(request, _("لا يمكن تعطيل العملة الأساسية الوظيفية للمؤسسة."))
    else:
        currency.is_active = not currency.is_active
        currency.save()
        status_txt = _("نشطة") if currency.is_active else _("معطلة")
        messages.success(request, f"تم تغيير حالة العملة {currency.code} إلى {status_txt}.")
    return redirect("financial:currency_list")


@login_required
def exchange_rate_list(request):
    """السجل التاريخي لأسعار الصرف"""
    rates = ExchangeRate.objects.select_related("from_currency", "to_currency", "created_by").all().order_by("-effective_date", "-created_at")
    currencies = Currency.objects.filter(is_active=True).order_by("-is_functional", "code")
    func_curr = ExchangeRateService.get_functional_currency()

    from django.urls import reverse
    header_buttons = [
        {
            "text": _("دليل العملات"),
            "icon": "fa-arrow-right",
            "url": reverse("financial:currency_list"),
            "class": "btn-outline-secondary"
        },
        {
            "text": _("تسجيل سعر صرف جديد"),
            "icon": "fa-plus",
            "toggle": "modal",
            "target": "#addRateModal",
            "class": "btn-primary"
        }
    ]

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": "/", "icon": "fa-home"},
        {"title": _("الإدارة المالية"), "url": "#", "icon": "fa-landmark"},
        {"title": _("دليل العملات"), "url": reverse("financial:currency_list")},
        {"title": _("أسعار الصرف"), "active": True}
    ]

    return render(request, "financial/currency/exchange_rate_list.html", {
        "page_title": _("السجل التاريخي لأسعار الصرف"),
        "page_subtitle": _("تتبع وتوثيق أسعار الصرف اليومية الرسمية وسجل التغييرات المحوكم"),
        "page_icon": "fas fa-history",
        "header_buttons": header_buttons,
        "breadcrumb_items": breadcrumb_items,
        "currencies": currencies,
        "base_currency": func_curr,
        "rates": rates
    })


@login_required
def exchange_rate_create(request):
    """إدخال سعر صرف جديد"""
    if request.method == "POST":
        from_code = request.POST.get("from_code", "").strip().upper()
        to_code = request.POST.get("to_code", "").strip().upper()
        rate_val = request.POST.get("rate")
        eff_date = request.POST.get("effective_date") or timezone.now().date()

        if from_code and to_code and rate_val:
            try:
                rate_dec = Decimal(rate_val)
                ExchangeRateService.set_rate(from_code, to_code, rate_dec, date=eff_date, source="MANUAL", user=request.user)
                messages.success(request, _("تم تسجيل سعر الصرف بنجاح."))
            except Exception as e:
                messages.error(request, f"{_('تعذر تسجیل سعر الصرف')}: {str(e)}")
        else:
            messages.error(request, _("يرجى إكمال حقول سعر الصرف."))
    return redirect("financial:exchange_rate_list")


@login_required
def api_sync_exchange_rates(request):
    """API لمزامنة أسعار الصرف الرسمية من البنك المركزي المصري (CBE API)"""
    if request.method == "POST":
        from financial.services.exchange_rate_sync_service import ExchangeRateSyncService
        res = ExchangeRateSyncService.sync_official_cbe_rates(user=request.user)
        return JsonResponse(res)
    return JsonResponse({"status": "ERROR", "message": _("طلب غير صالح")}, status=400)


@login_required
def fx_revaluation_view(request):
    """معالج إعادة التقييم الدوري لفروق أسعار الصرف غير المحققة (IAS 21)"""
    if request.method == "POST":
        closing_date = request.POST.get("closing_date") or timezone.now().date()
        res = FXRevaluationService.post_period_end_revaluation(as_of_date=closing_date, user=request.user)
        if res.get("status") == "POSTED":
            messages.success(request, f"{_('تم ترحيل قيد التقييم الدوري بنجاح. القيد رقم')} #{res['journal_entry_id']}")
        else:
            messages.info(request, res.get("message", _("لا توجد فروق تقييم مرحلة.")))
        return redirect("financial:fx_revaluation")

    preview_data = FXRevaluationService.calculate_open_items_revaluation()
    from django.urls import reverse
    header_buttons = [
        {
            "text": _("دليل العملات"),
            "icon": "fa-arrow-right",
            "url": reverse("financial:currency_list"),
            "class": "btn-outline-secondary"
        }
    ]

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": "/", "icon": "fa-home"},
        {"title": _("الإدارة المالية"), "url": "#", "icon": "fa-landmark"},
        {"title": _("دليل العملات"), "url": reverse("financial:currency_list")},
        {"title": _("إعادة التقييم الدوري (IAS 21)"), "active": True}
    ]

    return render(request, "financial/currency/fx_revaluation_form.html", {
        "page_title": _("معالج تقييم العملة غير المحقق الدوري (IAS 21)"),
        "page_subtitle": _("إعادة تقييم الفواتير والذمم والبنود المفتوحة بسعر إقفال نهاية الفترة وتوليد قيود التسوية"),
        "page_icon": "fas fa-calculator",
        "header_buttons": header_buttons,
        "breadcrumb_items": breadcrumb_items,
        "preview": preview_data
    })
