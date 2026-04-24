"""
Views معالجة الرواتب المتكاملة
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.urls import reverse
from datetime import date, timedelta
from ..models import Employee, Payroll, AttendanceSummary, Contract
from ..services.attendance_summary_service import AttendanceSummaryService
from utils.helpers import arabic_date_format
import logging

logger = logging.getLogger(__name__)

__all__ = [
    'integrated_payroll_dashboard',
    'process_monthly_payrolls',
    'calculate_single_payroll',
    'payroll_recalculate',
]


@login_required
@permission_required('hr.can_process_payroll', raise_exception=True)
def integrated_payroll_dashboard(request):
    """لوحة تحكم معالجة الرواتب المتكاملة"""
    
    # الشهر الحالي أو المختار
    selected_month = request.GET.get('month')
    if selected_month:
        try:
            month_date = date.fromisoformat(selected_month + '-01')
        except:
            month_date = date.today().replace(day=1)
    else:
        month_date = date.today().replace(day=1)
    
    # إحصائيات الموظفين
    active_employees = Employee.objects.filter(status='active', is_insurance_only=False)
    total_employees = active_employees.count()
    
    # حساب ملخصات الحضور تلقائياً للشهر الحالي (مرة واحدة عند عدم وجود بيانات)
    attendance_summaries = AttendanceSummary.objects.filter(month=month_date)
    if total_employees and not attendance_summaries.exists():
        try:
            AttendanceSummaryService.calculate_all_summaries_for_month(month_date)
            attendance_summaries = AttendanceSummary.objects.filter(month=month_date)
        except Exception as e:
            logger.error(f"فشل التحديث التلقائي لملخصات الحضور لشهر {month_date}: {str(e)}")
            messages.error(request, 'فشل التحديث التلقائي لملخصات الحضور لهذا الشهر، برجاء المراجعة.')
    
    # إحصائيات ملخصات الحضور
    calculated_summaries = attendance_summaries.filter(is_calculated=True).count()
    approved_summaries = attendance_summaries.filter(is_approved=True).count()
    
    # إحصائيات الرواتب
    payrolls = Payroll.objects.filter(month=month_date)
    calculated_payrolls = payrolls.filter(status__in=['calculated', 'approved', 'paid']).count()
    approved_payrolls = payrolls.filter(status__in=['approved', 'paid']).count()
    paid_payrolls = payrolls.filter(status='paid').count()
    
    # الموظفين المتبقيين
    processed_employee_ids = payrolls.values_list('employee_id', flat=True)
    remaining_employees = active_employees.exclude(id__in=processed_employee_ids)
    
    from django.db.models import OuterRef, Subquery, Exists
    attendance_subquery = AttendanceSummary.objects.filter(
        employee=OuterRef('pk'),
        month=month_date
    )
    contract_subquery = Contract.objects.filter(
        employee=OuterRef('pk'),
        status='active'
    )
    remaining_employees = remaining_employees.annotate(
        attendance_is_approved=Subquery(attendance_subquery.values('is_approved')[:1]),
        attendance_summary_id=Subquery(attendance_subquery.values('id')[:1]),
        has_active_contract=Exists(contract_subquery)
    )
    
    # إحصائيات مالية — استخدام property من الـ model لاستبعاد INSURABLE_SALARY
    from decimal import Decimal
    from django.db.models import Sum

    payrolls_list = list(payrolls)
    total_gross = sum(p.correct_gross_salary for p in payrolls_list)
    total_net = sum(p.correct_net_salary for p in payrolls_list)
    total_deductions = payrolls.aggregate(total=Sum('total_deductions'))['total'] or 0
    
    # إعداد قائمة الأشهر المتاحة (آخر 12 شهر)
    arabic_months = [
        "يناير", "فبراير", "مارس", "إبريل", "مايو", "يونيو",
        "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"
    ]
    
    available_months = []
    today = date.today()
    for i in range(12):
        # حساب الشهر بطريقة صحيحة بدون timedelta
        month_num = (today.month - 1 - i) % 12 + 1
        year_offset = (today.month - 1 - i) // 12
        month = date(today.year + year_offset, month_num, 1)
        # تنسيق الشهر بالعربي
        month_name = arabic_months[month.month - 1]
        arabic_label = f"{month_name} {month.year}"
        available_months.append({
            'value': month.strftime('%Y-%m'),
            'date_obj': month,
            'label': arabic_label
        })
    
    context = {
        'page_title': 'لوحة معالجة الرواتب',
        'page_subtitle': f'معالجة رواتب شهر {arabic_date_format(month_date).split(" ", 1)[1]}',
        'page_icon': 'fas fa-calculator',
        'month_selector': {
            'current_month': month_date,
            'available_months': available_months
        },
        'header_buttons': [
            *([{
                'url': reverse('hr:payroll_list'),
                'icon': 'fa-list',
                'text': 'قائمة الرواتب',
                'class': 'btn-outline-primary'
            }] if not (hasattr(request.user, 'role') and request.user.role and request.user.role.name == 'hr') else []),
            {
                'onclick': 'submitIntegratedPayroll()',
                'icon': 'fa-play',
                'text': 'معالجة رواتب الشهر',
                'class': 'btn-success',
                'id': 'process-payrolls-header-btn'
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users'},
            {'title': 'الرواتب', 'url': reverse('hr:payroll_list'), 'icon': 'fas fa-money-check-alt'},
            {'title': 'معالجة الرواتب', 'active': True}
        ],
        'current_month': month_date,
        'month_date': month_date,
        'available_months': available_months,
        'total_employees': total_employees,
        'employees_with_contracts': active_employees.filter(contracts__status='active').distinct().count(),
        'employees_without_contracts': total_employees - active_employees.filter(contracts__status='active').distinct().count(),
        'attendance_summaries_count': attendance_summaries.count(),
        'calculated_summaries': calculated_summaries,
        'approved_summaries': approved_summaries,
        'attendance_pending_approval_count': attendance_summaries.filter(is_calculated=True, is_approved=False).count(),
        'attendance_approved_count': attendance_summaries.filter(is_approved=True).count(),
        'payrolls_count': payrolls.count(),
        'calculated_payrolls': calculated_payrolls,
        'approved_payrolls': approved_payrolls,
        'paid_payrolls': paid_payrolls,
        'remaining_employees': remaining_employees,
        'remaining_employees_count': remaining_employees.count(),
        'total_gross': total_gross,
        'total_net': total_net,
        'total_deductions': total_deductions,
        'processing_percentage': (calculated_payrolls / total_employees * 100) if total_employees > 0 else 0,
    }
    
    return render(request, 'hr/payroll/dashboard.html', context)


@login_required
@permission_required('hr.can_process_payroll', raise_exception=True)
@require_POST
def process_monthly_payrolls(request):
    """معالجة رواتب الشهر"""
    from hr.services.payroll_gateway_service import HRPayrollGatewayService
    
    month_str = request.POST.get('month')
    if not month_str:
        month_date = date.today().replace(day=1)
    else:
        try:
            month_date = date.fromisoformat(month_str + '-01')
        except (ValueError, TypeError):
            messages.error(request, 'تاريخ غير صحيح')
            return redirect('hr:integrated_payroll_dashboard')
    
    # معالجة الرواتب عبر Gateway
    service = HRPayrollGatewayService()
    results = service.process_monthly_payrolls(
        month=month_date,
        processed_by=request.user,
        use_integrated=True
    )

    # ✅ تسجيل audit للرواتب المحسوبة
    from hr.services.payroll_audit_service import PayrollAuditService
    for item in results.get('success', []):
        PayrollAuditService.log_calculated(item['payroll'], request.user)
    
    success_count = len(results['success'])
    failed_count = len(results['failed'])

    if failed_count > 0:
        messages.warning(
            request,
            f'تم معالجة {success_count} راتب بنجاح. {failed_count} موظف يحتاج مراجعة — راجع قائمة الموظفين المتبقيين.'
        )
    else:
        messages.success(request, f'تم معالجة {success_count} راتب بنجاح.')
    
    url = reverse('hr:integrated_payroll_dashboard') + f'?month={month_date.strftime("%Y-%m")}'
    return redirect(url)


@login_required
@permission_required('hr.can_process_payroll', raise_exception=True)
def calculate_single_payroll(request, employee_id):
    """حساب راتب موظف واحد"""
    from hr.services.payroll_gateway_service import HRPayrollGatewayService
    
    employee = get_object_or_404(Employee, id=employee_id)
    month_str = request.GET.get('month')
    
    try:
        month_date = date.fromisoformat(month_str + '-01')
    except:
        messages.error(request, 'تاريخ غير صحيح')
        return redirect('hr:integrated_payroll_dashboard')
    
    try:
        # استخدام Gateway Service
        service = HRPayrollGatewayService()
        payroll = service.calculate_employee_payroll(
            employee=employee,
            month=month_date,
            processed_by=request.user,
            use_integrated=True
        )
        
        messages.success(
            request,
            f'تم حساب راتب {employee.get_full_name_ar()} بنجاح. '
            f'صافي الراتب: {payroll.correct_net_salary}'
        )

        # ✅ تسجيل audit للحساب الأول
        from hr.services.payroll_audit_service import PayrollAuditService
        PayrollAuditService.log_calculated(payroll, request.user)
        
        return redirect('hr:payroll_detail', pk=payroll.id)
        
    except Exception as e:
        logger.error(f"فشل حساب راتب {employee.get_full_name_ar()}: {str(e)}")
        messages.error(request, f'فشل حساب الراتب: {str(e)}')
        url = reverse('hr:integrated_payroll_dashboard') + f'?month={month_date.strftime("%Y-%m")}'
        return redirect(url)


@login_required
@require_POST
@permission_required('hr.can_process_payroll', raise_exception=True)
def payroll_recalculate(request, pk):
    """إعادة حساب قسيمة راتب موجودة"""
    from django.db import transaction
    from hr.services.payroll_gateway_service import HRPayrollGatewayService
    from governance.models import IdempotencyRecord

    payroll = get_object_or_404(Payroll, pk=pk)

    if payroll.status in ['approved', 'paid']:
        messages.error(request, 'لا يمكن إعادة حساب قسيمة معتمدة أو مدفوعة')
        return redirect('hr:payroll_detail', pk=pk)

    month = payroll.month
    # Refresh employee from DB to get current department (employee may have transferred)
    from hr.models import Employee
    employee = Employee.objects.select_related(
        'department__financial_subcategory__parent_category'
    ).get(pk=payroll.employee_id)

    try:
        with transaction.atomic():
            # حفظ البنود المعدلة يدوياً قبل الحذف
            manual_lines = list(
                payroll.lines.filter(source='adjustment').values(
                    'code', 'name', 'component_type', 'amount', 'order', 'description',
                    'is_manual', 'is_modified'
                )
            )

            # Rollback any advance installments linked to this payroll before deleting it
            from hr.models import AdvanceInstallment, Advance
            from decimal import Decimal

            installments_to_rollback = AdvanceInstallment.objects.filter(
                payroll=payroll
            ).select_related('advance')

            for installment in installments_to_rollback:
                adv = installment.advance
                adv.paid_installments = max(0, adv.paid_installments - 1)
                adv.remaining_amount = min(adv.amount, adv.remaining_amount + installment.amount)
                # Restore status if it was marked completed/in_progress due to this installment
                if adv.status == 'completed':
                    adv.status = 'in_progress'
                if adv.paid_installments == 0 and adv.status == 'in_progress':
                    adv.status = 'paid'
                adv.save(update_fields=['paid_installments', 'remaining_amount', 'status', 'completed_at'])

            # حذف الـ idempotency record عشان الـ Gateway يسمح بإعادة الحساب
            idempotency_key = f'PAYROLL:{employee.id}:{month.year}:{month.month:02d}:create'
            IdempotencyRecord.objects.filter(idempotency_key=idempotency_key).delete()

            # حذف القسيمة القديمة (والبنود تتحذف cascade)
            payroll.delete()

            # إعادة الحساب بنفس طريقة calculate_single_payroll
            service = HRPayrollGatewayService()
            new_payroll = service.calculate_employee_payroll(
                employee=employee,
                month=month,
                processed_by=request.user,
                use_integrated=True,
            )

            # إعادة إضافة البنود المعدلة يدوياً على القسيمة الجديدة
            if manual_lines:
                from hr.models import PayrollLine
                for line in manual_lines:
                    PayrollLine.objects.create(
                        payroll=new_payroll,
                        code=line['code'],
                        name=line['name'],
                        component_type=line['component_type'],
                        source='adjustment',
                        amount=line['amount'],
                        rate=Decimal('0'),
                        quantity=Decimal('1'),
                        order=line['order'],
                        description=line['description'] or '',
                        is_manual=line.get('is_manual', True),
                        is_modified=line.get('is_modified', False),
                    )
                # إعادة حساب الإجماليات بعد إضافة البنود اليدوية
                new_payroll.calculate_totals_from_lines()
                new_payroll.save(force_save=True)

        manual_note = f' (تم الاحتفاظ بـ {len(manual_lines)} بند يدوي)' if manual_lines else ''
        messages.success(request, f'تم إعادة حساب القسيمة بنجاح. صافي الراتب: {new_payroll.correct_net_salary} ج.م{manual_note}')

        # ✅ تسجيل audit للإعادة الحساب
        from hr.services.payroll_audit_service import PayrollAuditService
        PayrollAuditService.log_recalculated(new_payroll, request.user)

        return redirect('hr:payroll_detail', pk=new_payroll.pk)

    except Exception as e:
        logger.error(f"فشل إعادة حساب القسيمة {pk}: {str(e)}", exc_info=True)
        messages.error(request, f'فشل إعادة الحساب: {str(e)}')
        return redirect('hr:payroll_list')
