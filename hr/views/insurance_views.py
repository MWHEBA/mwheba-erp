"""
Views إدارة دفعات تأمين الموظفين الخارجيين
"""
from .base_imports import *
from ..models import Employee, InsurancePayment
from ..models.salary_component import SalaryComponent
from ..services.insurance_payment_service import InsurancePaymentService
from ..decorators import hr_manager_required
from core.models import SystemSetting
from financial.models import ChartOfAccounts

__all__ = [
    'employee_add_insurance_component',
    'insurance_payment_list',
    'insurance_payment_generate',
    'insurance_payment_pay',
]


@login_required
@hr_manager_required
@require_POST
def employee_add_insurance_component(request, pk):
    """إضافة بند التأمين للموظف الخارجي وحساب المبلغ تلقائياً"""
    from decimal import Decimal

    employee = get_object_or_404(Employee, pk=pk, is_insurance_only=True)

    insurable_salary = Decimal(request.POST.get('insurable_salary', '0') or '0')
    difference_amount = Decimal(request.POST.get('difference_amount', '0') or '0')
    
    if insurable_salary <= 0:
        messages.error(request, 'الأجر التأميني يجب أن يكون أكبر من صفر')
        return redirect('hr:employee_detail', pk=pk)

    emp_share = Decimal(str(SystemSetting.get_setting('hr_insurance_employee_share', 0) or 0))
    employer_share = Decimal(str(SystemSetting.get_setting('hr_insurance_employer_share', 0) or 0))

    if emp_share + employer_share <= 0:
        messages.error(request, 'يرجى تحديد نسب التأمينات في الإعدادات أولاً')
        return redirect('hr:hr_settings')

    total = (insurable_salary * (emp_share + employer_share) / 100).quantize(Decimal('0.01'))
    total += difference_amount

    SalaryComponent.objects.update_or_create(
        employee=employee,
        code='INSURANCE_TOTAL',
        defaults={
            'name': 'إجمالي التأمين الاجتماعي',
            'component_type': 'deduction',
            'calculation_method': 'fixed',
            'amount': total,
            'is_active': True,
            'is_recurring': True,
            'source': 'personal',
            'effective_from': employee.hire_date,
            'order': 100,
        }
    )

    # حفظ الأجر التأميني كمرجع
    SalaryComponent.objects.update_or_create(
        employee=employee,
        code='INSURABLE_SALARY',
        defaults={
            'name': 'الأجر التأميني (مرجع)',
            'component_type': 'earning',
            'calculation_method': 'fixed',
            'amount': insurable_salary,
            'is_active': True,
            'is_recurring': True,
            'source': 'personal',
            'effective_from': employee.hire_date,
            'order': 99,
        }
    )

    messages.success(request, f'تم إضافة بند التأمين بقيمة {total} ج.م شهرياً')
    return redirect('hr:employee_detail', pk=pk)


@login_required
def insurance_payment_list(request):
    """قائمة دفعات التأمين الشهرية"""
    from datetime import date

    # فلتر الشهر - الشهر الحالي افتراضياً
    from datetime import date
    from core.models import SystemSetting
    current_month_str = date.today().strftime('%Y-%m')
    month_str = request.GET.get('month', current_month_str)
    selected_month = None
    payments = InsurancePayment.objects.select_related(
        'employee', 'payment_account', 'received_by'
    ).order_by('-month', 'employee__name')

    try:
        from datetime import datetime
        selected_month = datetime.strptime(month_str, '%Y-%m').date().replace(day=1)
        payments = payments.filter(month=selected_month)
    except ValueError:
        pass

    # جلب نسب التأمين من الإعدادات
    from decimal import Decimal
    emp_share = Decimal(str(SystemSetting.get_setting('hr_insurance_employee_share', 0) or 0))
    employer_share = Decimal(str(SystemSetting.get_setting('hr_insurance_employer_share', 0) or 0))

    # جلب الأجر التأميني لكل موظف من SalaryComponent (INSURABLE_SALARY)
    from ..models.salary_component import SalaryComponent
    emp_ids = [p.employee_id for p in payments]

    insurable_components = SalaryComponent.objects.filter(
        employee_id__in=emp_ids, code='INSURABLE_SALARY', is_active=True
    ).values('employee_id', 'amount')
    insurable_salary_map = {c['employee_id']: c['amount'] for c in insurable_components}

    # fallback: حساب من INSURANCE_TOTAL لو INSURABLE_SALARY مش موجود
    total_components = SalaryComponent.objects.filter(
        employee_id__in=emp_ids, code='INSURANCE_TOTAL', is_active=True
    ).values('employee_id', 'amount')
    total_component_map = {c['employee_id']: c['amount'] for c in total_components}

    # إحصائيات
    total_pending = payments.filter(status='pending').count()
    total_paid = payments.filter(status='paid').count()

    table_headers = [
        {'key': 'employee_name', 'label': 'الموظف', 'format': 'html', 'class': 'text-center'},
        {'key': 'month_display', 'label': 'الشهر', 'class': 'text-center'},
        {'key': 'insurable_salary', 'label': 'الأجر التأميني', 'class': 'text-center'},
        {'key': 'shares_display', 'label': 'النسب (موظف / شركة)', 'class': 'text-center'},
        {'key': 'total_amount_display', 'label': 'القيمة المستحقة', 'format': 'html', 'class': 'text-center'},
        {'key': 'status_display', 'label': 'الحالة', 'format': 'html', 'class': 'text-center'},
        {'key': 'payment_date_display', 'label': 'تاريخ الدفع', 'class': 'text-center'},
        {'key': 'actions', 'label': 'الإجراءات', 'class': 'text-center'},
    ]

    table_data = []
    for p in payments:
        actions = []
        if p.status == 'pending':
            actions.append({
                'onclick': f'openPayModal({p.pk}, "{p.employee.get_full_name_ar()}", {p.total_amount})',
                'icon': 'fas fa-cash-register',
                'label': 'تسجيل دفع',
                'class': 'btn-outline-success btn-sm'
            })
        else:
            if p.journal_entry:
                actions.append({
                    'url': reverse('financial:journal_entries_detail', kwargs={'pk': p.journal_entry.pk}),
                    'icon': 'fas fa-eye',
                    'label': 'القيد',
                    'class': 'btn-outline-info btn-sm'
                })

        # الأجر التأميني - من INSURABLE_SALARY أو محسوب من INSURANCE_TOTAL كـ fallback
        insurable_salary = insurable_salary_map.get(p.employee_id)
        if insurable_salary is None:
            total_rate = emp_share + employer_share
            total_comp = total_component_map.get(p.employee_id, Decimal('0'))
            insurable_salary = (total_comp / total_rate * 100).quantize(Decimal('0.01')) if total_rate > 0 else Decimal('0')

        from utils.templatetags.utils_extras import currency_format
        table_data.append({
            'id': p.pk,
            'employee_name': f'<strong>{p.employee.get_full_name_ar()}</strong>',
            'month_display': p.month.strftime('%Y-%m'),
            'insurable_salary': f'{currency_format(insurable_salary)} ج.م',
            'shares_display': f'{emp_share}% / {employer_share}%',
            'total_amount_display': f'<strong>{currency_format(p.total_amount)} ج.م</strong>',
            'status_display': (
                '<span class="badge bg-warning text-dark">لم يُدفع</span>'
                if p.status == 'pending'
                else '<span class="badge bg-success">مدفوع</span>'
            ),
            'payment_date_display': p.payment_date.strftime('%Y-%m-%d') if p.payment_date else '—',
            'actions': actions,
        })

    # حسابات الدفع
    payment_accounts = ChartOfAccounts.objects.filter(
        is_active=True, is_leaf=True
    ).filter(
        models.Q(is_cash_account=True) | models.Q(is_bank_account=True)
    ).order_by('code')

    context = {
        'table_headers': table_headers,
        'table_data': table_data,
        'total_pending': total_pending,
        'total_paid': total_paid,
        'selected_month': month_str,
        'payment_accounts': payment_accounts,
        'page_title': 'دفعات التأمين',
        'page_subtitle': 'متابعة دفعات تأمين الموظفين الخارجيين',
        'page_icon': 'fas fa-shield-alt',
        'header_buttons': [
            {
                'onclick': 'openGenerateModal()',
                'icon': 'fa-magic',
                'text': 'توليد دفعات',
                'class': 'btn-primary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'دفعات التأمين', 'active': True},
        ],
    }
    return render(request, 'hr/insurance/payment_list.html', context)


@login_required
@hr_manager_required
@require_POST
def insurance_payment_generate(request):
    """توليد دفعات التأمين لشهر معين"""
    from datetime import datetime

    month_str = request.POST.get('month', '')
    if not month_str:
        messages.error(request, 'يرجى تحديد الشهر')
        return redirect('hr:insurance_payment_list')

    try:
        month = datetime.strptime(month_str, '%Y-%m').date().replace(day=1)
    except ValueError:
        messages.error(request, 'صيغة الشهر غير صحيحة')
        return redirect('hr:insurance_payment_list')

    created, skipped = InsurancePaymentService.generate_monthly_payments(month)

    if created:
        messages.success(request, f'تم توليد {len(created)} دفعة لشهر {month_str}')
    if skipped:
        messages.info(request, f'{len(skipped)} موظف لديهم دفعات مسبقاً لهذا الشهر')
    if not created and not skipped:
        messages.warning(request, 'لا يوجد موظفون تأمين فقط نشطون')

    return redirect(f"{reverse('hr:insurance_payment_list')}?month={month_str}")


@login_required
@hr_manager_required
@require_POST
def insurance_payment_pay(request, pk):
    """تسجيل دفع دفعة تأمين"""
    from datetime import datetime

    payment = get_object_or_404(InsurancePayment, pk=pk)

    payment_account_id = request.POST.get('payment_account')
    payment_date_str = request.POST.get('payment_date', '')

    if not payment_account_id:
        messages.error(request, 'يرجى اختيار حساب الاستلام')
        return redirect('hr:insurance_payment_list')

    payment_account = get_object_or_404(
        ChartOfAccounts, pk=payment_account_id, is_active=True
    )

    payment_date = None
    if payment_date_str:
        try:
            payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    try:
        InsurancePaymentService.record_payment(
            insurance_payment=payment,
            payment_account=payment_account,
            received_by=request.user,
            payment_date=payment_date,
        )
        messages.success(
            request,
            f'تم تسجيل دفع تأمين {payment.employee.get_full_name_ar()} بمبلغ {payment.total_amount} ج.م'
        )
    except ValueError as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f'حدث خطأ: {str(e)}')

    month_str = payment.month.strftime('%Y-%m')
    return redirect(f"{reverse('hr:insurance_payment_list')}?month={month_str}")
