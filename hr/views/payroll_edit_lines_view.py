"""
View لتعديل بنود قسيمة الراتب
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db import transaction
from decimal import Decimal
import json

from ..models import Payroll, PayrollLine
from ..decorators import can_process_payroll


@login_required
@can_process_payroll
def payroll_edit_lines(request, pk):
    """تعديل بنود قسيمة الراتب"""
    payroll = get_object_or_404(Payroll, pk=pk)

    # التحقق من الحالة - يمكن التعديل فقط قبل الاعتماد
    if payroll.status not in ['draft', 'calculated']:
        messages.error(request, 'لا يمكن تعديل قسيمة معتمدة أو مدفوعة')
        return redirect('hr:payroll_detail', pk=pk)

    if request.method == 'POST':
        try:
            with transaction.atomic():
                lines_data = json.loads(request.POST.get('lines_data', '[]'))

                # نحفظ البنود الأصلية (قبل الحذف) عشان نعرف إيه اللي اتعدل
                original_lines = {
                    line.code: line.amount
                    for line in payroll.lines.all()
                    if not line.code.startswith('NEW_')
                }

                # حذف جميع البنود القديمة
                payroll.lines.all().delete()

                total_earnings = payroll.basic_salary
                total_deductions = Decimal('0')

                for line_data in lines_data:
                    amount = Decimal(str(line_data['amount']))
                    code = line_data['code']
                    is_new = code.startswith('NEW_')

                    # تحديد المصدر
                    source = line_data.get('source', 'adjustment')
                    if is_new:
                        source = 'adjustment'

                    # تحديد is_manual و is_modified من البيانات المرسلة أو من المقارنة
                    is_manual = line_data.get('is_manual', is_new)
                    is_modified = line_data.get('is_modified', False)

                    # تأكيد: البنود الجديدة دايماً manual
                    if is_new:
                        is_manual = True
                        is_modified = False

                    # نحفظ البند بـ rate=0 عشان save() يحتفظ بالـ amount كما هو
                    PayrollLine.objects.create(
                        payroll=payroll,
                        code=code,
                        name=line_data['name'],
                        component_type=line_data['type'],
                        source=source,
                        amount=amount,
                        rate=Decimal('0'),
                        quantity=Decimal('1'),
                        order=line_data['order'],
                        is_manual=is_manual,
                        is_modified=is_modified,
                    )

                    if line_data['type'] == 'earning':
                        # BASIC_SALARY محفوظ في payroll.basic_salary — لا نضيفه مرة ثانية
                        if code not in ('INSURABLE_SALARY', 'BASIC_SALARY'):
                            total_earnings += amount
                    else:
                        total_deductions += amount

                # تحديث إجماليات القسيمة
                payroll.gross_salary = total_earnings
                payroll.total_deductions = total_deductions
                payroll.net_salary = total_earnings - total_deductions
                # force_save=True لتجاوز validation الـ net_salary السالب (المستخدم مسؤول عن القيم)
                payroll.save(force_save=True)

                # بناء ملخص التغييرات للـ audit
                changes_summary = []
                new_lines = {line_data['code']: Decimal(str(line_data['amount'])) for line_data in lines_data}
                
                # البنود المعدلة
                for code, old_amount in original_lines.items():
                    if code in new_lines:
                        new_amount = new_lines[code]
                        if old_amount != new_amount:
                            line_name = next((l['name'] for l in lines_data if l['code'] == code), code)
                            changes_summary.append(f'{line_name}: {old_amount} ← {new_amount}')
                    else:
                        # بند محذوف
                        changes_summary.append(f'حذف: {code}')
                
                # البنود الجديدة
                for code, amount in new_lines.items():
                    if code not in original_lines:
                        line_name = next((l['name'] for l in lines_data if l['code'] == code), code)
                        changes_summary.append(f'إضافة: {line_name} ({amount})')
                
                changes_text = ' | '.join(changes_summary) if changes_summary else 'لا توجد تغييرات'

                from hr.services.payroll_audit_service import PayrollAuditService
                PayrollAuditService.log_lines_edited(payroll, request.user, changes_summary=changes_text)

                messages.success(request, 'تم تحديث بنود القسيمة بنجاح')
                return redirect('hr:payroll_detail', pk=pk)

        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء التحديث: {str(e)}')

    # جلب البنود الحالية — نبعت source في data-source عشان JS يعرف إيه اللي اتعدل
    lines = payroll.lines.order_by('order')
    earnings = lines.filter(component_type='earning').exclude(code='BASIC_SALARY').exclude(code='INSURABLE_SALARY')
    deductions = lines.filter(component_type='deduction')

    context = {
        'payroll': payroll,
        'earnings': earnings,
        'deductions': deductions,
        'page_title': 'تعديل بنود القسيمة',
        'page_subtitle': f'{payroll.employee.get_full_name_ar()} - {payroll.month.strftime("%Y-%m")}',
        'page_icon': 'fas fa-edit',
        'header_buttons': [
            {
                'url': reverse('hr:payroll_detail', kwargs={'pk': payroll.pk}),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'قسائم الرواتب', 'url': reverse('hr:payroll_list'), 'icon': 'fas fa-money-bill-wave'},
            {'title': 'تعديل البنود', 'active': True},
        ],
    }
    return render(request, 'hr/payroll/edit_lines.html', context)
