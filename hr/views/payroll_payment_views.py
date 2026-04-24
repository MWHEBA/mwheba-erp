"""
Views لدفع الرواتب
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse
from datetime import datetime
import logging

from ..models import Payroll
from ..services.payroll_service import PayrollService
from ..decorators import can_pay_payroll
from financial.models import ChartOfAccounts

logger = logging.getLogger(__name__)


@login_required
@can_pay_payroll
def payroll_pay(request, pk):
    """دفع قسيمة راتب واحدة"""
    payroll = get_object_or_404(Payroll, pk=pk)
    
    # التحقق من الحالة
    if payroll.status != 'approved':
        error_message = 'يجب اعتماد قسيمة الراتب أولاً قبل الدفع'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': error_message})
        messages.error(request, error_message)
        return redirect('hr:payroll_detail', pk=pk)
    
    if request.method == 'POST':
        payment_account_id = request.POST.get('payment_account')
        payment_reference = request.POST.get('payment_reference', '')
        
        try:
            # الحصول على حساب الدفع - يدعم البحث بالـ id أو الـ code
            try:
                payment_account = ChartOfAccounts.objects.get(id=payment_account_id)
            except (ChartOfAccounts.DoesNotExist, ValueError):
                payment_account = ChartOfAccounts.objects.get(code=payment_account_id)
            
            # دفع الراتب
            PayrollService.pay_payroll(
                payroll=payroll,
                paid_by=request.user,
                payment_account=payment_account,
                payment_reference=payment_reference
            )
            
            success_message = f'تم دفع راتب {payroll.employee.get_full_name_ar()} بنجاح'
            
            # إرجاع JSON للطلبات AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': success_message})
            
            messages.success(request, success_message)
            return redirect('hr:payroll_detail', pk=pk)
            
        except ChartOfAccounts.DoesNotExist:
            error_message = 'حساب الدفع غير موجود'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_message})
            messages.error(request, error_message)
        except ValueError as e:
            error_message = str(e)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_message})
            messages.error(request, error_message)
        except Exception as e:
            # معالجة أخطاء التحقق المالي
            from financial.exceptions import FinancialValidationError
            
            if isinstance(e, FinancialValidationError):
                error_message = str(e)
                logger.warning(f"فشل التحقق المالي لدفع الراتب {pk}: {error_message}")
            else:
                logger.exception(f"خطأ في دفع الراتب {pk}: {str(e)}")
                error_message = f'حدث خطأ: {str(e)}'
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_message})
            messages.error(request, error_message)
    
    # Note: payment_accounts متاح تلقائياً من context processor
    context = {
        'payroll': payroll,
        'correct_net_salary': payroll.correct_net_salary,
        'correct_gross_salary': payroll.correct_gross_salary,
        'page_title': f'دفع راتب {payroll.employee.get_full_name_ar()}',
        'page_subtitle': f'شهر {payroll.month.strftime("%Y-%m")}',
        'page_icon': 'fas fa-money-bill-wave',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'قسائم الرواتب', 'url': reverse('hr:payroll_list'), 'icon': 'fas fa-money-bill-wave'},
            {'title': 'دفع راتب', 'active': True},
        ],
    }
    
    # إذا كان طلب AJAX، إرجاع المودال فقط
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'hr/payroll/payment_modal.html', context)
    
    return render(request, 'hr/payroll/pay_form.html', context)


@login_required
@can_pay_payroll
def payroll_run_pay_all(request, month):
    """دفع جميع رواتب الشهر المعتمدة"""
    # تحويل month (YYYY-MM) إلى تاريخ
    try:
        month_date = datetime.strptime(month, '%Y-%m').date()
    except ValueError:
        messages.error(request, 'صيغة الشهر غير صحيحة')
        return redirect('hr:payroll_list')
    
    # الحصول على الرواتب المعتمدة وغير المدفوعة
    approved_payrolls = Payroll.objects.filter(
        month=month_date,
        status='approved'
    ).select_related('employee')
    
    if not approved_payrolls.exists():
        messages.warning(request, 'لا توجد رواتب معتمدة للدفع في هذا الشهر')
        return redirect('hr:payroll_run_detail', month=month)
    
    if request.method == 'POST':
        payment_account_id = request.POST.get('payment_account')
        payment_reference = request.POST.get('payment_reference', '')
        create_journal = request.POST.get('create_journal') == 'on'
        
        try:
            # الحصول على حساب الدفع - يدعم البحث بالـ id أو الـ code
            try:
                payment_account = ChartOfAccounts.objects.get(id=payment_account_id)
            except (ChartOfAccounts.DoesNotExist, ValueError):
                payment_account = ChartOfAccounts.objects.get(code=payment_account_id)
            
            # دفع جميع الرواتب
            paid_count = 0
            failed_count = 0
            validation_errors = []
            
            for payroll in approved_payrolls:
                try:
                    PayrollService.pay_payroll(
                        payroll=payroll,
                        paid_by=request.user,
                        payment_account=payment_account,
                        payment_reference=f"{payment_reference}-{payroll.employee.employee_number}" if payment_reference else ''
                    )
                    paid_count += 1
                except Exception as e:
                    # معالجة أخطاء التحقق المالي
                    from financial.exceptions import FinancialValidationError
                    
                    if isinstance(e, FinancialValidationError):
                        error_msg = f"{payroll.employee.get_full_name_ar()}: {str(e)}"
                        validation_errors.append(error_msg)
                        logger.warning(f"فشل التحقق المالي لدفع راتب {payroll.pk}: {str(e)}")
                    else:
                        logger.error(f"فشل دفع راتب {payroll.pk}: {str(e)}")
                    
                    failed_count += 1
            
            # عرض رسائل النجاح والفشل
            if paid_count > 0:
                messages.success(request, f'تم دفع {paid_count} راتب بنجاح')
            
            if failed_count > 0:
                messages.warning(request, f'فشل دفع {failed_count} راتب')
                
                # عرض أول 3 أخطاء تحقق مالي
                for error_msg in validation_errors[:3]:
                    messages.error(request, error_msg)
                
                if len(validation_errors) > 3:
                    messages.info(request, f'وهناك {len(validation_errors) - 3} أخطاء أخرى')
            
            # إنشاء القيد المحاسبي العام إذا طُلب
            journal_entry = None
            if create_journal and paid_count > 0:
                try:
                    paid_payrolls = Payroll.objects.filter(
                        month=month_date,
                        status='paid',
                        journal_entry__isnull=True  # فقط الرواتب التي لم يتم إنشاء قيد لها
                    )
                    
                    if paid_payrolls.exists():
                        # استخدام PayrollAccountingService بدلاً من الطريقة القديمة
                        from hr.services.payroll_accounting_service import PayrollAccountingService
                        accounting_service = PayrollAccountingService()
                        
                        # إنشاء قيد لكل راتب
                        created_entries = []
                        for payroll in paid_payrolls:
                            try:
                                entry = accounting_service.create_payroll_journal_entry(
                                    payroll=payroll,
                                    created_by=request.user
                                )
                                created_entries.append(entry)
                            except Exception as e:
                                logger.error(f"فشل إنشاء قيد لراتب {payroll.id}: {e}")
                        
                        if created_entries:
                            messages.success(
                                request,
                                f'تم إنشاء {len(created_entries)} قيد محاسبي'
                            )
                except Exception as e:
                    logger.exception(f"خطأ في إنشاء القيد المحاسبي: {str(e)}")
                    messages.warning(
                        request,
                        f'فشل إنشاء القيد المحاسبي: {str(e)}'
                    )
            
            return redirect('hr:payroll_run_detail', month=month)
            
        except ChartOfAccounts.DoesNotExist:
            messages.error(request, 'حساب الدفع غير موجود')
        except Exception as e:
            logger.exception(f"خطأ في دفع رواتب الشهر {month}: {str(e)}")
            messages.error(request, f'حدث خطأ: {str(e)}')
    
    # الحصول على حسابات الصناديق والبنوك
    # Note: payment_accounts متاح تلقائياً من context processor
    
    # حساب الإجماليات — استخدام property من الـ model
    from decimal import Decimal
    total_gross = sum(p.correct_gross_salary for p in approved_payrolls)
    total_net = sum(p.correct_net_salary for p in approved_payrolls)
    total_deductions = sum(p.total_deductions or Decimal('0') for p in approved_payrolls)

    # إضافة correct_net و correct_gross لكل payroll
    payrolls_with_correct = []
    for p in approved_payrolls:
        p._correct_net = p.correct_net_salary
        p._correct_gross = p.correct_gross_salary
        payrolls_with_correct.append(p)

    context = {
        'month': month,
        'month_date': month_date,
        'approved_payrolls': payrolls_with_correct,
        'total_gross': total_gross,
        'total_net': total_net,
        'total_deductions': total_deductions,
        'page_title': f'دفع رواتب شهر {month_date.strftime("%B %Y")}',
        'page_subtitle': f'{approved_payrolls.count()} راتب معتمد',
        'page_icon': 'fas fa-money-check-alt',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'معالجة الرواتب', 'url': reverse('hr:payroll_list'), 'icon': 'fas fa-money-check-alt'},
            {'title': 'دفع رواتب الشهر', 'active': True},
        ],
    }
    
    return render(request, 'hr/payroll/pay_all_form.html', context)


# ============================================
# payroll_print (moved from integrated_payroll_views)
# ============================================

@login_required
def payroll_print(request, pk):
    """طباعة قسيمة راتب"""
    from ..models import AttendanceSummary
    
    payroll = get_object_or_404(
        Payroll.objects.select_related('employee', 'contract', 'processed_by', 'approved_by'),
        pk=pk
    )
    
    # التحقق من الصلاحيات
    if not request.user.has_perm('hr.can_view_all_salaries'):
        if not hasattr(request.user, 'employee_profile') or request.user.employee_profile != payroll.employee:
            messages.error(request, 'ليس لديك صلاحية لعرض هذه القسيمة')
            return redirect('hr:payroll_list')
    
    # جلب بنود القسيمة
    payroll_lines_earnings = payroll.lines.filter(
        component_type='earning'
    ).exclude(code='INSURABLE_SALARY').order_by('order')
    payroll_lines_deductions = payroll.lines.filter(component_type='deduction').order_by('order')
    insurable_salary_line = payroll.lines.filter(code='INSURABLE_SALARY').first()
    
    # جلب ملخص الحضور
    attendance_summary = AttendanceSummary.objects.filter(
        employee=payroll.employee,
        month=payroll.month
    ).first()
    
    context = {
        'payroll': payroll,
        'payroll_lines_earnings': payroll_lines_earnings,
        'payroll_lines_deductions': payroll_lines_deductions,
        'insurable_salary_line': insurable_salary_line,
        'attendance_summary': attendance_summary,
        'company_name': 'Corporate ERP',
        'company_logo': None,
        'correct_net_salary': payroll.correct_net_salary,
        'correct_gross_salary': payroll.correct_gross_salary,
    }
    
    return render(request, 'hr/payroll/print.html', context)
