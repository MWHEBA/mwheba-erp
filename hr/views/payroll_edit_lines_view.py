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
                # جلب البيانات من الـ POST
                lines_data = json.loads(request.POST.get('lines_data', '[]'))
                
                # حذف جميع البنود القديمة
                payroll.lines.all().delete()
                
                # إنشاء البنود الجديدة
                total_earnings = payroll.basic_salary  # البدء بالراتب الأساسي
                total_deductions = Decimal('0')
                
                for line_data in lines_data:
                    amount = Decimal(str(line_data['amount']))
                    
                    PayrollLine.objects.create(
                        payroll=payroll,
                        code=line_data['code'],
                        name=line_data['name'],
                        component_type=line_data['type'],
                        amount=amount,
                        order=line_data['order']
                    )
                    
                    if line_data['type'] == 'earning':
                        total_earnings += amount
                    else:
                        total_deductions += amount
                
                # تحديث إجماليات القسيمة
                payroll.gross_salary = total_earnings
                payroll.total_deductions = total_deductions
                payroll.net_salary = total_earnings - total_deductions
                payroll.save()
                
                messages.success(request, 'تم تحديث بنود القسيمة بنجاح')
                return redirect('hr:payroll_detail', pk=pk)
                
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء التحديث: {str(e)}')
    
    # جلب البنود الحالية
    lines = payroll.lines.order_by('order')
    earnings = lines.filter(component_type='earning')
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
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'قسائم الرواتب', 'url': reverse('hr:payroll_list'), 'icon': 'fas fa-money-bill-wave'},
            {'title': 'تعديل البنود', 'active': True},
        ],
    }
    return render(request, 'hr/payroll/edit_lines.html', context)
