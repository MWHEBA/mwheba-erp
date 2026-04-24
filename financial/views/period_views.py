"""
عروض الفترات المحاسبية
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone

# استيراد النماذج
try:
    from financial.models.journal_entry import AccountingPeriod
except ImportError as e:
    print(f"خطأ في استيراد AccountingPeriod: {e}")
    AccountingPeriod = None


@login_required
def accounting_periods_list(request):
    """عرض قائمة الفترات المحاسبية"""
    if AccountingPeriod is None:
        periods = []
        open_periods_count = 0
        closed_periods_count = 0
        current_period = None
        messages.warning(request, "نماذج الفترات المحاسبية غير متاحة حالياً.")
    else:
        try:
            periods = AccountingPeriod.objects.all().order_by("-start_date")
            
            # حساب الإحصائيات
            open_periods_count = periods.filter(status='open').count()
            closed_periods_count = periods.filter(status='closed').count()
            
            # البحث عن الفترة الحالية (الفترة المفتوحة الأحدث)
            current_period = periods.filter(status='open').first()
            
        except Exception as e:
            periods = []
            open_periods_count = 0
            current_period = None
            messages.error(request, f"خطأ في تحميل الفترات المحاسبية: {str(e)}")
    
    context = {
        "page_title": "الفترات المحاسبية",
        "page_subtitle": "إدارة الفترات المحاسبية وإغلاق الحسابات",
        "page_icon": "fas fa-calendar-alt",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "الإدارة المالية", "url": reverse("financial:chart_of_accounts_list"), "icon": "fas fa-money-bill-wave"},
            {"title": "الفترات المحاسبية", "active": True},
        ],
        "header_buttons": [
            {
                "url": reverse("financial:accounting_periods_create"),
                "icon": "fa-plus",
                "text": "إضافة فترة جديدة",
                "class": "btn-primary",
            }
        ],
        "periods": periods,
        "open_periods_count": open_periods_count,
        "closed_periods_count": closed_periods_count,
        "current_period": current_period,
    }
    return render(request, "financial/periods/accounting_periods_list.html", context)


@login_required
def accounting_periods_create(request):
    """إنشاء فترة محاسبية جديدة"""
    if AccountingPeriod is None:
        messages.error(request, "نماذج الفترات المحاسبية غير متاحة حالياً.")
        return redirect("financial:accounting_periods_list")
    
    if request.method == "POST":
        try:
            period = AccountingPeriod.objects.create(
                name=request.POST.get("name"),
                start_date=request.POST.get("start_date"),
                end_date=request.POST.get("end_date"),
                status=request.POST.get("status", "open"),
                created_by=request.user,
            )
            messages.success(request, f'تم إنشاء الفترة "{period.name}" بنجاح.')
            return redirect("financial:accounting_periods_list")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء إنشاء الفترة: {str(e)}")

    context = {
        "page_title": "إنشاء فترة محاسبية جديدة",
        "page_subtitle": "إدارة الفترات المحاسبية للنظام",
        "page_icon": "fas fa-plus-circle",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": "/dashboard/", "icon": "fas fa-home"},
            {"title": "النظام المالي", "url": "#", "icon": "fas fa-calculator"},
            {"title": "الفترات المحاسبية", "url": "/financial/accounting-periods/", "icon": "fas fa-calendar-alt"},
            {"title": "إنشاء فترة جديدة", "active": True},
        ],
    }
    return render(request, "financial/periods/accounting_periods_form.html", context)


@login_required
def accounting_periods_edit(request, pk):
    """تعديل فترة محاسبية"""
    if AccountingPeriod is None:
        messages.error(request, "نماذج الفترات المحاسبية غير متاحة حالياً.")
        return redirect("financial:accounting_periods_list")
    
    period = get_object_or_404(AccountingPeriod, pk=pk)

    if request.method == "POST":
        try:
            period.name = request.POST.get("name")
            period.start_date = request.POST.get("start_date")
            period.end_date = request.POST.get("end_date")
            period.status = request.POST.get("status", "open")
            period.save()
            messages.success(request, f'تم تحديث الفترة "{period.name}" بنجاح.')
            return redirect("financial:accounting_periods_list")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء تحديث الفترة: {str(e)}")

    context = {
        "period": period,
        "page_title": f"تعديل فترة: {period.name}",
        "page_subtitle": "إدارة الفترات المحاسبية للنظام",
        "page_icon": "fas fa-edit",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": "/dashboard/", "icon": "fas fa-home"},
            {"title": "النظام المالي", "url": "#", "icon": "fas fa-calculator"},
            {"title": "الفترات المحاسبية", "url": "/financial/accounting-periods/", "icon": "fas fa-calendar-alt"},
            {"title": f"تعديل: {period.name}", "active": True},
        ],
    }
    return render(request, "financial/periods/accounting_periods_form.html", context)


@login_required
def accounting_periods_close(request, pk):
    """إغلاق فترة محاسبية"""
    if AccountingPeriod is None:
        messages.error(request, "نماذج الفترات المحاسبية غير متاحة حالياً.")
        return redirect("financial:accounting_periods_list")
    
    period = get_object_or_404(AccountingPeriod, pk=pk)
    if request.method == "POST":
        period.status = "closed"
        period.closed_at = timezone.now()
        period.closed_by = request.user
        period.save()
        messages.success(request, f'تم إغلاق الفترة "{period.name}" بنجاح.')
        return redirect("financial:accounting_periods_list")

    context = {
        "period": period,
        "page_title": f"إغلاق فترة: {period.name}",
        "page_subtitle": "إغلاق الفترة المحاسبية ومنع التعديل",
        "page_icon": "fas fa-lock",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": "/dashboard/", "icon": "fas fa-home"},
            {"title": "النظام المالي", "url": "#", "icon": "fas fa-calculator"},
            {"title": "الفترات المحاسبية", "url": "/financial/accounting-periods/", "icon": "fas fa-calendar-alt"},
            {"title": f"إغلاق: {period.name}", "active": True},
        ],
    }
    return render(request, "financial/periods/accounting_periods_close.html", context)
