import logging
from decimal import Decimal
from datetime import date, datetime
from django.db import models
from django.db.models import Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone

from financial.models.tax import (
    TaxCode,
    TaxJurisdiction,
    TaxRule,
    TaxExemptionCertificate,
    TaxDeterminationAudit,
    TaxEvent,
    TaxCalculationLine,
    TaxTransactionSnapshot,
    TaxExemptionSnapshot,
    TaxReversal,
)
from financial.forms.tax_forms import (
    TaxCodeForm,
    TaxRuleForm,
    TaxExemptionCertificateForm,
    TaxAccountMappingForm,
)
from financial.services.tax_service import TaxDeterminationService
from financial.services.vat_settlement_service import VATSettlementService

logger = logging.getLogger("financial.views.tax_views")


# ==========================================
# 1. Tax Codes Management (CRUD)
# ==========================================

@login_required
def tax_code_list(request):
    """عرض قائمة أكواد الضرائب مع الإحصائيات وبحث الـ AJAX"""
    tax_codes_qs = TaxCode.objects.all().order_by('code')

    search_query = request.GET.get('search', '').strip()
    tax_type_filter = request.GET.get('tax_type', '').strip()

    if search_query:
        from utils.search import smart_search_filter
        tax_codes_qs = smart_search_filter(
            tax_codes_qs,
            search_query,
            text_fields=['name', 'description'],
            code_fields=['code']
        )
    if tax_type_filter:
        tax_codes_qs = tax_codes_qs.filter(tax_type=tax_type_filter)

    total_count = TaxCode.objects.count()
    active_count = TaxCode.objects.filter(is_active=True).count()
    vat_count = TaxCode.objects.filter(tax_type="VAT").count()
    wht_count = TaxCode.objects.filter(tax_type="WITHHOLDING").count()

    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(tax_codes_qs, request)
    page_obj = pagination_context["page_obj"]

    return render(request, 'financial/tax_code_list.html', {
        'page_obj': page_obj,
        'tax_codes': page_obj.object_list,
        **pagination_context,
        'total_count': total_count,
        'active_count': active_count,
        'vat_count': vat_count,
        'wht_count': wht_count,
        'page_title': _("أكواد وتصنيفات الضرائب"),
        'page_subtitle': _("إدارة الرموز الضريبية والنسب المعيارية وفق مصلحة الضرائب المصرية"),
        'page_icon': "fas fa-percent",
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة المالية'), 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fa-calculator'},
            {'title': _('أكواد الضرائب'), 'active': True}
        ],
        'header_buttons': [
            {
                'url': reverse('financial:tax_code_create'),
                'icon': 'fa-plus',
                'text': _('إضافة كود ضريبة'),
                'class': 'btn-primary'
            },
            {
                'url': reverse('financial:tax_rules_list'),
                'icon': 'fa-gavel',
                'text': _('قواعد وسياسات الضرائب'),
                'class': 'btn-outline-secondary'
            },
            {
                'url': reverse('financial:tax_exemptions_list'),
                'icon': 'fa-id-card',
                'text': _('شهادات الإعفاء'),
                'class': 'btn-outline-secondary'
            },
            {
                'url': reverse('financial:tax_audit_list'),
                'icon': 'fa-shield-alt',
                'text': _('سجل التدقيق والفحص'),
                'class': 'btn-outline-secondary'
            }
        ]
    })


@login_required
def tax_code_create(request):
    """إضافة كود ضريبة جديد"""
    if request.method == "POST":
        form = TaxCodeForm(request.POST)
        if form.is_valid():
            tax_code = form.save()
            messages.success(request, _(f"تم إنشاء كود الضريبة '{tax_code.name}' بنجاح."))
            return redirect('financial:tax_code_list')
    else:
        form = TaxCodeForm()

    return render(request, 'financial/tax_code_form.html', {
        'form': form,
        'page_title': _("إضافة كود ضريبة جديد"),
        'page_subtitle': _("تعريف كود ضريبة جديد ونسبته وقابليته للخصم"),
        'page_icon': "fas fa-plus-circle",
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('أكواد الضرائب'), 'url': reverse('financial:tax_code_list'), 'icon': 'fa-percent'},
            {'title': _('إضافة كود ضريبة'), 'active': True}
        ]
    })


@login_required
def tax_code_update(request, pk):
    """تعديل كود ضريبة"""
    tax_code = get_object_or_404(TaxCode, pk=pk)
    if request.method == "POST":
        form = TaxCodeForm(request.POST, instance=tax_code)
        if form.is_valid():
            tax_code = form.save()
            messages.success(request, _(f"تم تحديث كود الضريبة '{tax_code.name}' بنجاح."))
            return redirect('financial:tax_code_list')
    else:
        form = TaxCodeForm(instance=tax_code)

    return render(request, 'financial/tax_code_form.html', {
        'form': form,
        'tax_code': tax_code,
        'page_title': _(f"تعديل كود الضريبة: {tax_code.name}"),
        'page_subtitle': _("تحديث بيانات ونسبة الضريبة"),
        'page_icon': "fas fa-edit",
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('أكواد الضرائب'), 'url': reverse('financial:tax_code_list'), 'icon': 'fa-percent'},
            {'title': tax_code.name, 'active': True}
        ]
    })


@login_required
@require_POST
def tax_code_delete(request, pk):
    """حذف كود ضريبة"""
    tax_code = get_object_or_404(TaxCode, pk=pk)
    tax_code.delete()
    messages.success(request, _("تم حذف كود الضريبة بنجاح."))
    return redirect('financial:tax_code_list')


@login_required
def tax_seed_presets(request):
    """توليد واسترجاع أكواد الضرائب المصرية القياسية بضغطة زر"""
    created_count = TaxDeterminationService.seed_egyptian_tax_presets()
    messages.success(request, _(f"تم توليد وتحديث {created_count} من أكواد الضرائب المصرية القياسية بنجاح."))
    return redirect('financial:tax_code_list')


# ==========================================
# 2. Tax Rules Configuration
# ==========================================

@login_required
def tax_rules_list(request):
    """عرض قائمة قواعد احتساب وسياسات الضرائب التلقائية"""
    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(rules_qs, request)
    page_obj = pagination_context["page_obj"]

    return render(request, 'financial/tax_rules_list.html', {
        'page_obj': page_obj,
        'rules': page_obj.object_list,
        **pagination_context,
        'page_title': _("قواعد احتساب الضرائب"),
        'page_subtitle': _("تحديد سياسات التطبيق التلقائي والأولويات حسب النطاق"),
        'page_icon': "fas fa-gavel",
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة المالية'), 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fa-calculator'},
            {'title': _('قواعد الضرائب'), 'active': True}
        ],
        'header_buttons': [
            {
                'url': reverse('financial:tax_rule_create'),
                'icon': 'fa-plus',
                'text': _('إضافة قاعدة جديدة'),
                'class': 'btn-primary'
            },
            {
                'url': reverse('financial:tax_code_list'),
                'icon': 'fa-percent',
                'text': _('أكواد الضرائب'),
                'class': 'btn-outline-secondary'
            },
            {
                'url': reverse('financial:tax_exemptions_list'),
                'icon': 'fa-id-card',
                'text': _('شهادات الإعفاء'),
                'class': 'btn-outline-secondary'
            }
        ]
    })


@login_required
def tax_rule_create(request):
    """إضافة قاعدة ضريبية جديدة"""
    if request.method == "POST":
        form = TaxRuleForm(request.POST)
        if form.is_valid():
            rule = form.save()
            messages.success(request, _(f"تم إنشاء القاعدة الضريبية '{rule.name}' بنجاح."))
            return redirect('financial:tax_rules_list')
    else:
        form = TaxRuleForm()

    return render(request, 'financial/tax_rule_form.html', {
        'form': form,
        'page_title': _("إضافة قاعدة ضريبية جديدة"),
        'page_subtitle': _("تحديد النطاق والأولوية وكود الضريبة المرتبط"),
        'page_icon': "fas fa-plus-circle",
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('قواعد الضرائب'), 'url': reverse('financial:tax_rules_list'), 'icon': 'fa-gavel'},
            {'title': _('إضافة قاعدة'), 'active': True}
        ]
    })


@login_required
def tax_rule_update(request, pk):
    """تعديل قاعدة ضريبية"""
    rule = get_object_or_404(TaxRule, pk=pk)
    if request.method == "POST":
        form = TaxRuleForm(request.POST, instance=rule)
        if form.is_valid():
            rule = form.save()
            messages.success(request, _(f"تم تحديث القاعدة الضريبية '{rule.name}' بنجاح."))
            return redirect('financial:tax_rules_list')
    else:
        form = TaxRuleForm(instance=rule)

    return render(request, 'financial/tax_rule_form.html', {
        'form': form,
        'rule': rule,
        'page_title': _(f"تعديل القاعدة: {rule.name}"),
        'page_subtitle': _("تحديث معايير وأولوية التطبيق"),
        'page_icon': "fas fa-edit",
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('قواعد الضرائب'), 'url': reverse('financial:tax_rules_list'), 'icon': 'fa-gavel'},
            {'title': rule.name, 'active': True}
        ]
    })


@login_required
@require_POST
def tax_rule_delete(request, pk):
    """حذف قاعدة ضريبية"""
    rule = get_object_or_404(TaxRule, pk=pk)
    rule.delete()
    messages.success(request, _("تم حذف القاعدة الضريبية بنجاح."))
    return redirect('financial:tax_rules_list')


# ==========================================
# 3. Tax Exemption Certificates
# ==========================================

@login_required
def tax_exemptions_list(request):
    """عرض قائمة شهادات الإعفاء الضريبي المحوكمة"""
    exemptions_qs = TaxExemptionCertificate.objects.select_related(
        'customer', 'supplier', 'tax_code'
    ).all().order_by('-valid_to')
    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(exemptions_qs, request)
    page_obj = pagination_context["page_obj"]

    return render(request, 'financial/tax_exemptions_list.html', {
        'page_obj': page_obj,
        'exemptions': page_obj.object_list,
        **pagination_context,
        'page_title': _("شهادات الإعفاء الضريبي"),
        'page_subtitle': _("إدارة شهادات الإعفاء للعملاء والموردين ومتابعة السقف المالي"),
        'page_icon': "fas fa-id-card",
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة المالية'), 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fa-calculator'},
            {'title': _('شهادات الإعفاء'), 'active': True}
        ],
        'header_buttons': [
            {
                'url': reverse('financial:tax_exemption_create'),
                'icon': 'fa-plus',
                'text': _('إضافة شهادة إعفاء'),
                'class': 'btn-primary'
            },
            {
                'url': reverse('financial:tax_code_list'),
                'icon': 'fa-percent',
                'text': _('أكواد الضرائب'),
                'class': 'btn-outline-secondary'
            },
            {
                'url': reverse('financial:tax_rules_list'),
                'icon': 'fa-gavel',
                'text': _('قواعد وسياسات الضرائب'),
                'class': 'btn-outline-secondary'
            }
        ]
    })


@login_required
def tax_exemption_create(request):
    """إضافة شهادة إعفاء جديدة"""
    if request.method == "POST":
        form = TaxExemptionCertificateForm(request.POST)
        if form.is_valid():
            cert = form.save()
            messages.success(request, _(f"تم تسجيل شهادة الإعفاء رقم '{cert.certificate_number}' بنجاح."))
            return redirect('financial:tax_exemptions_list')
    else:
        form = TaxExemptionCertificateForm()

    return render(request, 'financial/tax_exemption_form.html', {
        'form': form,
        'page_title': _("إضافة شهادة إعفاء ضريبي"),
        'page_subtitle': _("توثيق سبب الإعفاء والسقف المالي وتواريخ السريان"),
        'page_icon': "fas fa-plus-circle",
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('شهادات الإعفاء'), 'url': reverse('financial:tax_exemptions_list'), 'icon': 'fa-id-card'},
            {'title': _('إضافة شهادة'), 'active': True}
        ]
    })


@login_required
def tax_exemption_update(request, pk):
    """تعديل شهادة إعفاء"""
    cert = get_object_or_404(TaxExemptionCertificate, pk=pk)
    if request.method == "POST":
        form = TaxExemptionCertificateForm(request.POST, instance=cert)
        if form.is_valid():
            cert = form.save()
            messages.success(request, _(f"تم تحديث شهادة الإعفاء '{cert.certificate_number}' بنجاح."))
            return redirect('financial:tax_exemptions_list')
    else:
        form = TaxExemptionCertificateForm(instance=cert)

    return render(request, 'financial/tax_exemption_form.html', {
        'form': form,
        'cert': cert,
        'page_title': _(f"تعديل شهادة الإعفاء: {cert.certificate_number}"),
        'page_subtitle': _("تحديث الحالة والسقف المالي"),
        'page_icon': "fas fa-edit",
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('شهادات الإعفاء'), 'url': reverse('financial:tax_exemptions_list'), 'icon': 'fa-id-card'},
            {'title': cert.certificate_number, 'active': True}
        ]
    })


@login_required
@require_POST
def tax_exemption_delete(request, pk):
    """حذف شهادة إعفاء"""
    cert = get_object_or_404(TaxExemptionCertificate, pk=pk)
    cert.delete()
    messages.success(request, _("تم حذف شهادة الإعفاء بنجاح."))
    return redirect('financial:tax_exemptions_list')


# ==========================================
# 4. Tax Determination Audit Explorer
# ==========================================

@login_required
def tax_audit_list(request):
    """مستكشف سجل الفحص والتدقيق الضريبي المحوكم مع فحص SHA-256"""
    audits_qs = TaxDeterminationAudit.objects.select_related(
        'tax_code', 'customer', 'supplier', 'journal_entry'
    ).prefetch_related('snapshots', 'exemption_snapshots').all().order_by('-created_at')

    # Filters
    search = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()
    doc_type_filter = request.GET.get('doc_type', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if search:
        audits_qs = audits_qs.filter(document_number__icontains=search)
    if status_filter:
        audits_qs = audits_qs.filter(audit_status=status_filter)
    if doc_type_filter:
        audits_qs = audits_qs.filter(document_type=doc_type_filter)
    if date_from:
        audits_qs = audits_qs.filter(created_at__date__gte=date_from)
    if date_to:
        audits_qs = audits_qs.filter(created_at__date__lte=date_to)

    # Calculate stats
    total_taxable_sum = TaxDeterminationAudit.objects.aggregate(s=models.Sum('taxable_amount'))['s'] or Decimal("0.00")
    total_functional_tax = TaxDeterminationAudit.objects.aggregate(s=models.Sum('functional_tax_amount'))['s'] or Decimal("0.00")
    posted_count = TaxDeterminationAudit.objects.filter(audit_status="POSTED").count()
    reversed_count = TaxDeterminationAudit.objects.filter(audit_status="REVERSED").count()

    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(audits_qs, request)
    page_obj = pagination_context["page_obj"]

    return render(request, 'financial/tax_audit_list.html', {
        'page_obj': page_obj,
        'audits': page_obj.object_list,
        **pagination_context,
        'total_taxable_sum': total_taxable_sum,
        'total_functional_tax': total_functional_tax,
        'posted_count': posted_count,
        'reversed_count': reversed_count,
        'page_title': _("مستكشف سجل الفحص والتدقيق الضريبي"),
        'page_subtitle': _("سجل الإثبات الضريبي المشفر Canonical SHA-256 المحمي من التعديل"),
        'page_icon': "fas fa-shield-alt",
        'header_buttons': [
            {
                'url': reverse('financial:tax_events_list'),
                'icon': 'fa-stream',
                'text': _('سجل الأحداث الضريبية'),
                'class': 'btn-outline-secondary'
            },
            {
                'url': reverse('financial:tax_code_list'),
                'icon': 'fa-percent',
                'text': _('أكواد الضرائب'),
                'class': 'btn-outline-secondary'
            }
        ],
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة المالية'), 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fa-calculator'},
            {'title': _('سجل الفحص الضريبي'), 'active': True}
        ]
    })


@login_required
def tax_audit_verify_ajax(request, pk):
    """فحص سلامة وتطابق البصمة المشفرة SHA-256 لسجل التدقيق عبر الـ AJAX"""
    try:
        is_valid = TaxDeterminationService.verify_audit_integrity(pk)
        audit = TaxDeterminationAudit.objects.get(pk=pk)
        return JsonResponse({
            "status": "success",
            "is_valid": is_valid,
            "audit_id": pk,
            "hash": audit.audit_hash,
            "message": _("البصمة الرقمية سليمة ومطابقة للبيانات الأصلية بنسبة 100%.") if is_valid else _("تحذير: عدم تطابق في البصمة الرقمية المشفرة!")
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
def tax_events_list(request):
    """عرض سجل الأحداث الضريبية المستقل Domain Events"""
    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(events_qs, request)
    page_obj = pagination_context["page_obj"]

    return render(request, 'financial/tax_events_list.html', {
        'page_obj': page_obj,
        'events': page_obj.object_list,
        **pagination_context,
        'page_title': _("سجل الأحداث الضريبية"),
        'page_subtitle': _("تتبع الأحداث الضريبية المستقلة والتسويات المرتبطة بالـ UUID"),
        'page_icon': "fas fa-stream",
        'header_buttons': [
            {
                'url': reverse('financial:tax_audit_list'),
                'icon': 'fa-shield-alt',
                'text': _('سجل الفحص والتدقيق'),
                'class': 'btn-outline-secondary'
            },
            {
                'url': reverse('financial:tax_code_list'),
                'icon': 'fa-percent',
                'text': _('أكواد الضرائب'),
                'class': 'btn-outline-secondary'
            }
        ],
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة المالية'), 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fa-calculator'},
            {'title': _('سجل الأحداث الضريبية'), 'active': True}
        ]
    })


# ==========================================
# 5. Tax Return Reports & Monthly Settlement
# ==========================================

@login_required
def tax_return_vat_report(request):
    """تقرير إقرار ضريبة القيمة المضافة (نموذج 10 المصري) وقيد المقاصة والتسوية"""
    today = timezone.now().date()
    month_str = request.GET.get('month', today.strftime('%Y-%m'))

    try:
        period_date = datetime.strptime(month_str, '%Y-%m').date()
    except ValueError:
        period_date = today

    import calendar
    first_weekday, last_day = calendar.monthrange(period_date.year, period_date.month)
    start_date = date(period_date.year, period_date.month, 1)
    end_date = date(period_date.year, period_date.month, last_day)

    summary = VATSettlementService.get_monthly_tax_summary(start_date, end_date)

    return render(request, 'financial/tax_return_vat_report.html', {
        'summary': summary,
        'month_str': month_str,
        'start_date': start_date,
        'end_date': end_date,
        'page_title': _("إقرار ضريبة القيمة المضافة (نموذج 10)"),
        'page_subtitle': _("التسوية الشهرية لضريبة المخرجات والمدخلات وصافي الالتزام المستحق لمصلحة الضرائب المصرية"),
        'page_icon': "fas fa-file-invoice-dollar",
        'header_buttons': [
            {
                'url': reverse('financial:tax_withholding_report'),
                'icon': 'fa-receipt',
                'text': _('نموذج 41 (خصم وتحصيل)'),
                'class': 'btn-outline-primary'
            },
            {
                'text': _('طباعة الإقرار'),
                'icon': 'fa-print',
                'class': 'btn-outline-secondary',
                'onclick': 'window.print()',
            }
        ],
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة المالية'), 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fa-calculator'},
            {'title': _('إقرار القيمة المضافة'), 'active': True}
        ]
    })


@login_required
@require_POST
def tax_post_vat_settlement(request):
    """توليد قيد التسوية والمقاصة الشهرية لضريبة القيمة المضافة بضغطة زر"""
    month_str = request.POST.get('month')
    try:
        period_date = datetime.strptime(month_str, '%Y-%m').date()
        import calendar
        first_weekday, last_day = calendar.monthrange(period_date.year, period_date.month)
        start_date = date(period_date.year, period_date.month, 1)
        end_date = date(period_date.year, period_date.month, last_day)

        entry = VATSettlementService.post_monthly_vat_settlement(start_date, end_date, user=request.user)
        messages.success(request, _(f"تم إنشاء وترحيل قيد المقاصة والتسوية الضريبية رقم '{entry.number}' لشهر {month_str} بنجاح."))
    except Exception as e:
        messages.error(request, _(f"فشل توليد قيد التسوية الضريبية: {str(e)}"))

    return redirect(f"{reverse('financial:tax_return_vat_report')}?month={month_str}")


@login_required
def tax_withholding_report(request):
    """كشف الخصم والتحصيل تحت حساب الضريبة (نموذج 41 ضرائب)"""
    today = timezone.now().date()
    quarter = request.GET.get('quarter', 'Q1')
    year = int(request.GET.get('year', today.year))

    quarter_months = {
        'Q1': (1, 3),
        'Q2': (4, 6),
        'Q3': (7, 9),
        'Q4': (10, 12),
    }
    sm, em = quarter_months.get(quarter, (1, 3))
    import calendar
    first_weekday, last_day = calendar.monthrange(year, em)
    start_date = date(year, sm, 1)
    end_date = date(year, em, last_day)

    wht_audits = TaxDeterminationAudit.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
        tax_code__tax_type="WITHHOLDING"
    ).select_related('supplier', 'tax_code').order_by('-created_at')

    total_wht_base = sum(a.taxable_amount for a in wht_audits)
    total_wht_amount = sum(a.functional_tax_amount for a in wht_audits)

    return render(request, 'financial/tax_withholding_report.html', {
        'wht_audits': wht_audits,
        'quarter': quarter,
        'year': year,
        'start_date': start_date,
        'end_date': end_date,
        'total_wht_base': total_wht_base,
        'total_wht_amount': total_wht_amount,
        'page_title': _("كشف الخصم والتحصيل (نموذج 41 ضرائب)"),
        'page_subtitle': _("كشف التعاملات مع الموردين الخاضعة للخصم تحت حساب الضريبة المجهز للإرسال للـ ETA"),
        'page_icon': "fas fa-receipt",
        'header_buttons': [
            {
                'url': reverse('financial:tax_return_vat_report'),
                'icon': 'fa-file-invoice-dollar',
                'text': _('نموذج 10 (إقرار القيمة المضافة)'),
                'class': 'btn-outline-primary'
            },
            {
                'text': _('طباعة نموذج 41'),
                'icon': 'fa-print',
                'class': 'btn-outline-secondary',
                'onclick': 'window.print()',
            }
        ],
        'breadcrumb_items': [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('الإدارة المالية'), 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fa-calculator'},
            {'title': _('نموذج 41 خصم وتحصيل'), 'active': True}
        ]
    })


@login_required
def api_calculate_tax(request):
    """نقطة نهاية الـ API السريعة لحساب الضريبة اللحظية لبنود الفواتير بالـ AJAX"""
    try:
        import json
        data = json.loads(request.body)
        doc_type = data.get("document_type", "SalesInvoice")
        lines = data.get("lines", [])
        customer_id = data.get("customer_id")
        supplier_id = data.get("supplier_id")
        is_tax_inclusive = data.get("is_tax_inclusive", False)

        from customer.models import Customer
        from supplier.models import Supplier
        cust = Customer.objects.filter(pk=customer_id).first() if customer_id else None
        supp = Supplier.objects.filter(pk=supplier_id).first() if supplier_id else None

        res = TaxDeterminationService.calculate_tax(
            document_type=doc_type,
            document_id=0,
            customer=cust,
            supplier=supp,
            lines=lines,
            is_tax_inclusive=is_tax_inclusive
        )

        return JsonResponse({
            "status": "success",
            "subtotal": str(res.subtotal),
            "taxable_amount": str(res.taxable_amount),
            "tax_amount": str(res.tax_amount),
            "total_amount": str(res.total_amount),
            "line_decisions": res.line_decisions
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
