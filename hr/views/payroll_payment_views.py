"""
Views لدفع الرواتب
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db.models import Q
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
            # الحصول على حساب الدفع
            payment_account = ChartOfAccounts.objects.get(id=payment_account_id)
            
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
            logger.exception(f"خطأ في دفع الراتب {pk}: {str(e)}")
            error_message = f'حدث خطأ: {str(e)}'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_message})
            messages.error(request, error_message)
    
    # الحصول على حسابات الصناديق والبنوك
    payment_accounts = ChartOfAccounts.objects.filter(
        Q(is_cash_account=True) | Q(is_bank_account=True),
        is_active=True
    ).order_by('name')
    
    context = {
        'payroll': payroll,
        'payment_accounts': payment_accounts,
        'page_title': f'دفع راتب {payroll.employee.get_full_name_ar()}',
        'page_subtitle': f'شهر {payroll.month.strftime("%Y-%m")}',
        'page_icon': 'fas fa-money-bill-wave',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
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
            # الحصول على حساب الدفع
            payment_account = ChartOfAccounts.objects.get(id=payment_account_id)
            
            # دفع جميع الرواتب
            paid_count = 0
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
                    logger.error(f"فشل دفع راتب {payroll.pk}: {str(e)}")
            
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
                        journal_entry = PayrollService.create_monthly_payroll_journal_entry(
                            month=month_date,
                            paid_payrolls=paid_payrolls,
                            created_by=request.user
                        )
                        
                        messages.success(
                            request,
                            f'تم دفع {paid_count} راتب بنجاح وإنشاء القيد المحاسبي رقم {journal_entry.id}'
                        )
                    else:
                        messages.success(request, f'تم دفع {paid_count} راتب بنجاح')
                except Exception as e:
                    logger.exception(f"خطأ في إنشاء القيد المحاسبي: {str(e)}")
                    messages.warning(
                        request,
                        f'تم دفع {paid_count} راتب بنجاح لكن فشل إنشاء القيد المحاسبي: {str(e)}'
                    )
            else:
                messages.success(request, f'تم دفع {paid_count} راتب بنجاح')
            
            return redirect('hr:payroll_run_detail', month=month)
            
        except ChartOfAccounts.DoesNotExist:
            messages.error(request, 'حساب الدفع غير موجود')
        except Exception as e:
            logger.exception(f"خطأ في دفع رواتب الشهر {month}: {str(e)}")
            messages.error(request, f'حدث خطأ: {str(e)}')
    
    # الحصول على حسابات الصناديق والبنوك
    payment_accounts = ChartOfAccounts.objects.filter(
        Q(is_cash_account=True) | Q(is_bank_account=True),
        is_active=True
    ).order_by('name')
    
    # حساب الإجماليات
    from decimal import Decimal
    total_gross = sum(p.gross_salary or Decimal('0') for p in approved_payrolls)
    total_net = sum(p.net_salary or Decimal('0') for p in approved_payrolls)
    total_deductions = sum(p.total_deductions or Decimal('0') for p in approved_payrolls)
    
    context = {
        'month': month,
        'month_date': month_date,
        'approved_payrolls': approved_payrolls,
        'payment_accounts': payment_accounts,
        'total_gross': total_gross,
        'total_net': total_net,
        'total_deductions': total_deductions,
        'page_title': f'دفع رواتب شهر {month_date.strftime("%B %Y")}',
        'page_subtitle': f'{approved_payrolls.count()} راتب معتمد',
        'page_icon': 'fas fa-money-check-alt',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'معالجة الرواتب', 'url': reverse('hr:payroll_list'), 'icon': 'fas fa-money-check-alt'},
            {'title': 'دفع رواتب الشهر', 'active': True},
        ],
    }
    
    return render(request, 'hr/payroll/pay_all_form.html', context)
