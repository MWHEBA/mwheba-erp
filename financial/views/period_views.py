"""
عروض الفترات المحاسبية والسنوات المالية مع دعم معالجات الإغلاق المعمارية
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator

from financial.models.fiscal_year import FiscalYear
from financial.models.journal_entry import AccountingPeriod
from financial.models.closing_engine_models import FiscalYearClosingRun, PeriodModuleLock, ClosingRule
from financial.forms.period_forms import FiscalYearForm, AccountingPeriodForm, PeriodForceCloseForm, PeriodReopenForm
from financial.services.fiscal_year_closing_service import FiscalYearClosingService
from financial.services.period_control_service import PeriodControlService


@login_required
def accounting_periods_list(request):
    """عرض قائمة الفترات المحاسبية مع الدعم الكامل لـ AJAX doSearch و SSR Pagination و stats-card"""
    periods_qs = AccountingPeriod.objects.select_related('fiscal_year').all().order_by("-start_date")

    # تطبيق التصفية والبحث
    fiscal_year_id = request.GET.get('fiscal_year')
    status_filter = request.GET.get('status')
    search_query = request.GET.get('search')

    if fiscal_year_id:
        periods_qs = periods_qs.filter(fiscal_year_id=fiscal_year_id)
    if status_filter:
        periods_qs = periods_qs.filter(status=status_filter)
    if search_query:
        periods_qs = periods_qs.filter(name__icontains=search_query)

    # حساب الإحصائيات لكروت الإحصائيات .stats-card
    open_periods_count = AccountingPeriod.objects.filter(status='open').count()
    closed_periods_count = AccountingPeriod.objects.filter(status__in=['closed', 'hard_closed']).count()
    soft_closed_count = AccountingPeriod.objects.filter(status='soft_closed').count()
    active_fiscal_year = FiscalYear.objects.filter(status='open').first()
    current_period = AccountingPeriod.objects.filter(status='open').first()

    # الترقيم SSR Pagination
    paginator = Paginator(periods_qs, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    fiscal_years = FiscalYear.objects.all().order_by('-start_date')

    context = {
        "page_title": "الفترات المحاسبية",
        "page_subtitle": "إدارة الفترات المحاسبية والإغلاق المالي المؤسسي",
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
            },
            {
                "url": reverse("financial:fiscal_years_list"),
                "icon": "fa-calendar",
                "text": "إدارة السنوات المالية",
                "class": "btn-outline-secondary",
            }
        ],
        "periods": page_obj,
        "page_obj": page_obj,
        "fiscal_years": fiscal_years,
        "open_periods_count": open_periods_count,
        "closed_periods_count": closed_periods_count,
        "soft_closed_count": soft_closed_count,
        "current_period": current_period,
        "active_fiscal_year": active_fiscal_year,
    }

    # إذا كان الطلب أياكس AJAX doSearch
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        table_html = render_to_string('financial/periods/partials/periods_table_partial.html', context, request=request)
        pagination_html = render_to_string('partials/pagination.html', {'page_obj': page_obj}, request=request)
        return JsonResponse({
            'table_html': table_html,
            'pagination_html': pagination_html,
            'open_count': open_periods_count,
            'closed_count': closed_periods_count,
        })

    return render(request, "financial/periods/accounting_periods_list.html", context)


@login_required
def accounting_periods_create(request):
    """إنشاء فترة محاسبية جديدة"""
    if request.method == "POST":
        form = AccountingPeriodForm(request.POST)
        if form.is_valid():
            period = form.save(commit=False)
            period.created_by = request.user
            period.save()
            messages.success(request, f'تم إنشاء الفترة المحاسبية "{period.name}" بنجاح.')
            return redirect("financial:accounting_periods_list")
    else:
        form = AccountingPeriodForm()

    context = {
        "form": form,
        "page_title": "إنشاء فترة محاسبية جديدة",
        "page_subtitle": "إضافة فترة محاسبية جديدة للنظام",
        "page_icon": "fas fa-plus-circle",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "الإدارة المالية", "url": reverse("financial:chart_of_accounts_list"), "icon": "fas fa-money-bill-wave"},
            {"title": "الفترات المحاسبية", "url": reverse("financial:accounting_periods_list"), "icon": "fas fa-calendar-alt"},
            {"title": "إنشاء فترة جديدة", "active": True},
        ],
    }
    return render(request, "financial/periods/accounting_periods_form.html", context)


@login_required
def accounting_periods_edit(request, pk):
    """تعديل فترة محاسبية"""
    period = get_object_or_404(AccountingPeriod, pk=pk)
    if request.method == "POST":
        form = AccountingPeriodForm(request.POST, instance=period)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تحديث الفترة "{period.name}" بنجاح.')
            return redirect("financial:accounting_periods_list")
    else:
        form = AccountingPeriodForm(instance=period)

    context = {
        "form": form,
        "period": period,
        "page_title": f"تعديل فترة: {period.name}",
        "page_subtitle": "إدارة الفترات المحاسبية للنظام",
        "page_icon": "fas fa-edit",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "الإدارة المالية", "url": reverse("financial:chart_of_accounts_list"), "icon": "fas fa-money-bill-wave"},
            {"title": "الفترات المحاسبية", "url": reverse("financial:accounting_periods_list"), "icon": "fas fa-calendar-alt"},
            {"title": f"تعديل: {period.name}", "active": True},
        ],
    }
    return render(request, "financial/periods/accounting_periods_form.html", context)


@login_required
def accounting_period_wizard(request, pk):
    """معالج الإغلاق التفاعلي خطوة-بخطوة للفترة المحاسبية"""
    period = get_object_or_404(AccountingPeriod, pk=pk)
    module_locks = PeriodModuleLock.objects.filter(period=period)

    context = {
        "period": period,
        "module_locks": module_locks,
        "page_title": f"معالج إغلاق الفترة: {period.name}",
        "page_subtitle": "فحص وتأمين موديولات الفترة قبل القفل التام",
        "page_icon": "fas fa-magic",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "الفترات المحاسبية", "url": reverse("financial:accounting_periods_list"), "icon": "fas fa-calendar-alt"},
            {"title": f"معالج إغلاق: {period.name}", "active": True},
        ],
    }
    return render(request, "financial/periods/accounting_period_wizard.html", context)


@login_required
def accounting_periods_close(request, pk):
    """إغلاق فترة محاسبية مع الأتمتة التلقائية لتقييم العملات وحماية المسودات"""
    period = get_object_or_404(AccountingPeriod, pk=pk)
    if request.method == "POST":
        from financial.services.period_control_service import PeriodControlService
        try:
            PeriodControlService.close_period(period.id, user=request.user)
            messages.success(request, f'تم إغلاق الفترة "{period.name}" بنجاح مع أتمتة ترحيل فروق تقييم العملة (IAS 21).')
        except Exception as e:
            messages.error(request, f'تعذر إغلاق الفترة: {str(e)}')
        return redirect("financial:accounting_periods_list")

    context = {
        "period": period,
        "page_title": f"إغلاق فترة: {period.name}",
        "page_subtitle": "تأكيد إغلاق الفترة المحاسبية ومنع التعديل",
        "page_icon": "fas fa-lock",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "الفترات المحاسبية", "url": reverse("financial:accounting_periods_list"), "icon": "fas fa-calendar-alt"},
            {"title": f"إغلاق: {period.name}", "active": True},
        ],
    }
    return render(request, "financial/periods/accounting_periods_close.html", context)


@login_required
def fiscal_years_list(request):
    """عرض إدارة السنوات المالية الموحدة بأسلوب AGENTS.md مع دعم AJAX doSearch الإحصائيات"""
    fiscal_years_qs = FiscalYear.objects.all().order_by("-start_date")

    status_filter = request.GET.get('status')
    search_query = request.GET.get('search')

    if status_filter:
        fiscal_years_qs = fiscal_years_qs.filter(status=status_filter)
    if search_query:
        fiscal_years_qs = fiscal_years_qs.filter(name__icontains=search_query)

    # حساب الإحصائيات لكروت .stats-card
    total_years_count = FiscalYear.objects.count()
    open_years_count = FiscalYear.objects.filter(status='open').count()
    closed_years_count = FiscalYear.objects.filter(status='closed').count()
    active_year = FiscalYear.objects.filter(status='open').first()

    paginator = Paginator(fiscal_years_qs, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "page_title": "السنوات المالية",
        "page_subtitle": "إدارة الإقفالات السنوية وحسابات الأرباح المرحلة",
        "page_icon": "fas fa-calendar-check",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "الإدارة المالية", "url": reverse("financial:chart_of_accounts_list"), "icon": "fas fa-money-bill-wave"},
            {"title": "السنوات المالية", "active": True},
        ],
        "header_buttons": [
            {
                "url": reverse("financial:fiscal_years_create"),
                "icon": "fa-plus",
                "text": "إضافة سنة مالية جديدة",
                "class": "btn-primary",
            }
        ],
        "fiscal_years": page_obj,
        "page_obj": page_obj,
        "total_years_count": total_years_count,
        "open_years_count": open_years_count,
        "closed_years_count": closed_years_count,
        "active_year_code": active_year.year_code if active_year else None,
    }

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        table_html = render_to_string('financial/periods/partials/fiscal_years_table_partial.html', context, request=request)
        pagination_html = render_to_string('partials/pagination.html', {'page_obj': page_obj}, request=request)
        return JsonResponse({
            'table_html': table_html,
            'pagination_html': pagination_html,
            'open_count': open_years_count,
            'closed_count': closed_years_count,
        })

    return render(request, "financial/periods/fiscal_years_list.html", context)


@login_required
def fiscal_years_create(request):
    """إنشاء سنة مالية جديدة"""
    if request.method == "POST":
        form = FiscalYearForm(request.POST)
        if form.is_valid():
            fy = form.save()
            # توليد 12 فترة شهرية تلقائياً عبر الخدمة
            PeriodControlService.create_fiscal_year_with_periods(
                year_code=fy.year_code,
                name=fy.name,
                start_date=fy.start_date,
                end_date=fy.end_date
            )
            messages.success(request, f'تم إنشاء السنة المالية "{fy.name}" وتوليد فتراتها الشهرية تلقائياً.')
            return redirect("financial:fiscal_years_list")
    else:
        form = FiscalYearForm()

    context = {
        "form": form,
        "page_title": "إنشاء سنة مالية جديدة",
        "page_subtitle": "إضافة سنة مالية مع توليد الفترات الشهرية تلقائياً",
        "page_icon": "fas fa-plus-circle",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "السنوات المالية", "url": reverse("financial:fiscal_years_list"), "icon": "fas fa-calendar-check"},
            {"title": "إنشاء سنة مالية جديدة", "active": True},
        ],
    }
    return render(request, "financial/periods/fiscal_year_form.html", context)


@login_required
def fiscal_year_wizard(request, pk):
    """معالج الإغلاق السنوي التفاعلي"""
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)

    if request.method == "POST":
        try:
            closing_run = FiscalYearClosingService.execute_fiscal_year_close(fiscal_year.id, request.user)
            messages.success(request, f'تم إغلاق السنة المالية "{fiscal_year.name}" وتوليد قيد التصفية بنجاح.')
            return redirect("financial:fiscal_years_list")
        except Exception as e:
            messages.error(request, f"خطأ أثناء تنفيذ الإغلاق السنوي: {str(e)}")

    context = {
        "fiscal_year": fiscal_year,
        "page_title": f"معالج إغلاق السنة المالية: {fiscal_year.name}",
        "page_subtitle": "تصفية حسابات قائمة الدخل وتوليد قيد التصفية المعتمد",
        "page_icon": "fas fa-file-invoice-dollar",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "السنوات المالية", "url": reverse("financial:fiscal_years_list"), "icon": "fas fa-calendar-check"},
            {"title": f"إغلاق: {fiscal_year.name}", "active": True},
        ],
    }
    return render(request, "financial/periods/fiscal_year_wizard.html", context)
