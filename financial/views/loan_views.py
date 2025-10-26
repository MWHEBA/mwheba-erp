from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Q, Count
from django.utils import timezone
from decimal import Decimal

from ..models.loan_transactions import Loan, LoanPayment
from ..models.chart_of_accounts import ChartOfAccounts
from ..models.journal_entry import JournalEntry, JournalEntryLine
from ..forms.loan_forms import LoanForm, LoanPaymentForm, QuickLoanPaymentForm


@login_required
def loans_dashboard(request):
    """
    لوحة تحكم القروض - نظرة عامة على جميع القروض
    """
    # إحصائيات القروض
    active_loans = Loan.objects.filter(status='active')
    
    total_loans = active_loans.aggregate(
        total=Sum('principal_amount')
    )['total'] or Decimal('0.00')
    
    total_paid = Decimal('0.00')
    for loan in active_loans:
        total_paid += loan.total_paid
    
    remaining_balance = total_loans - total_paid
    
    # عدد القروض
    loans_count = {
        'active': active_loans.count(),
        'completed': Loan.objects.filter(status='completed').count(),
        'total': Loan.objects.count(),
    }
    
    # الأقساط القادمة (خلال 30 يوم)
    upcoming_payments = LoanPayment.objects.filter(
        loan__status='active',
        status='scheduled',
        scheduled_date__lte=timezone.now().date() + timezone.timedelta(days=30),
        scheduled_date__gte=timezone.now().date()
    ).order_by('scheduled_date')[:5]
    
    # الأقساط المتأخرة
    overdue_payments = LoanPayment.objects.filter(
        loan__status='active',
        status='scheduled',
        scheduled_date__lt=timezone.now().date()
    ).order_by('scheduled_date')
    
    # آخر المعاملات
    recent_payments = LoanPayment.objects.filter(
        status='completed'
    ).order_by('-actual_payment_date')[:10]
    
    context = {
        'total_loans': total_loans,
        'total_paid': total_paid,
        'remaining_balance': remaining_balance,
        'loans_count': loans_count,
        'active_loans': active_loans,
        'upcoming_payments': upcoming_payments,
        'overdue_payments': overdue_payments,
        'overdue_count': overdue_payments.count(),
        'recent_payments': recent_payments,
        'quick_payment_form': QuickLoanPaymentForm(),
        'page_title': 'إدارة القروض',
        'page_icon': 'fas fa-hand-holding-usd',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'النظام المالي', 'url': '#', 'icon': 'fas fa-calculator'},
            {'title': 'إدارة القروض', 'active': True},
        ],
    }
    
    return render(request, 'financial/loans/dashboard.html', context)


@login_required
def loans_list(request):
    """
    قائمة جميع القروض
    """
    # الفلترة
    status_filter = request.GET.get('status', 'all')
    lender_type_filter = request.GET.get('lender_type', 'all')
    
    loans = Loan.objects.all().order_by('-start_date')
    
    if status_filter != 'all':
        loans = loans.filter(status=status_filter)
    
    if lender_type_filter != 'all':
        loans = loans.filter(lender_type=lender_type_filter)
    
    context = {
        'loans': loans,
        'status_filter': status_filter,
        'lender_type_filter': lender_type_filter,
        'page_title': 'قائمة القروض',
        'page_icon': 'fas fa-list',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'إدارة القروض', 'url': reverse('financial:loans_dashboard'), 'icon': 'fas fa-hand-holding-usd'},
            {'title': 'قائمة القروض', 'active': True},
        ],
    }
    
    return render(request, 'financial/loans/loans_list.html', context)


@login_required
def loan_detail(request, pk):
    """
    تفاصيل قرض معين
    """
    loan = get_object_or_404(Loan, pk=pk)
    
    # جدول السداد
    payments = loan.payments.all().order_by('payment_number')
    
    # الإحصائيات
    completed_payments = payments.filter(status='completed')
    scheduled_payments = payments.filter(status='scheduled')
    overdue_payments = payments.filter(status='overdue')
    
    # حسابات الدفع (البنوك والخزن)
    payment_accounts = ChartOfAccounts.objects.filter(
        is_active=True,
        is_leaf=True,
        account_type__category='asset'
    ).filter(
        Q(is_cash_account=True) | Q(is_bank_account=True)
    )
    
    context = {
        'loan': loan,
        'payments': payments,
        'completed_payments': completed_payments,
        'scheduled_payments': scheduled_payments,
        'overdue_payments': overdue_payments,
        'payment_accounts': payment_accounts,
        'today': timezone.now().date(),
        'page_title': f'تفاصيل القرض - {loan.loan_number}',
        'page_icon': 'fas fa-file-invoice-dollar',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'إدارة القروض', 'url': reverse('financial:loans_dashboard'), 'icon': 'fas fa-hand-holding-usd'},
            {'title': f'القرض {loan.loan_number}', 'active': True},
        ],
    }
    
    return render(request, 'financial/loans/loan_detail.html', context)


@login_required
def loan_create(request):
    """
    إضافة قرض جديد
    """
    if request.method == 'POST':
        form = LoanForm(request.POST)
        if form.is_valid():
            try:
                loan = form.save(commit=False)
                loan.created_by = request.user
                loan.save()
                
                # إنشاء القيد المحاسبي لاستلام القرض
                journal_entry = create_loan_receipt_entry(loan, request.user)
                loan.initial_journal_entry = journal_entry
                loan.save()
                
                # إنشاء جدول السداد
                create_payment_schedule(loan)
                
                messages.success(request, f'تم إضافة القرض {loan.loan_number} بنجاح')
                return redirect('financial:loan_detail', pk=loan.pk)
            except Exception as e:
                messages.error(request, f'خطأ في إضافة القرض: {str(e)}')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = LoanForm()
    
    context = {
        'form': form,
        'page_title': 'إضافة قرض جديد',
        'page_icon': 'fas fa-plus-circle',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'إدارة القروض', 'url': reverse('financial:loans_dashboard'), 'icon': 'fas fa-hand-holding-usd'},
            {'title': 'إضافة قرض جديد', 'active': True},
        ],
    }
    
    return render(request, 'financial/loans/loan_form.html', context)


@login_required
@require_http_methods(["POST"])
def loan_payment_create(request):
    """
    سداد قسط من قرض
    """
    if request.method == 'POST':
        form = QuickLoanPaymentForm(request.POST)
        if form.is_valid():
            try:
                loan = form.cleaned_data['loan']
                payment_date = form.cleaned_data['payment_date']
                amount = form.cleaned_data['amount']
                payment_account = form.cleaned_data['payment_account']
                notes = form.cleaned_data.get('notes', '')
                
                # حساب توزيع المبلغ على الأصل والفائدة
                monthly_payment = loan.calculate_monthly_payment()
                
                # حساب الفائدة والأصل
                if loan.interest_rate > 0:
                    interest_amount = (loan.remaining_balance * loan.interest_rate) / (Decimal('100') * Decimal('12'))
                    principal_amount = amount - interest_amount
                else:
                    interest_amount = Decimal('0.00')
                    principal_amount = amount
                
                # إنشاء سجل الدفعة
                payment_number = loan.payments.count() + 1
                payment = LoanPayment.objects.create(
                    loan=loan,
                    payment_number=payment_number,
                    scheduled_date=payment_date,
                    actual_payment_date=payment_date,
                    principal_amount=principal_amount,
                    interest_amount=interest_amount,
                    payment_account=payment_account,
                    status='completed',
                    notes=notes,
                    paid_by=request.user
                )
                
                # إنشاء القيد المحاسبي
                journal_entry = create_loan_payment_entry(payment, request.user)
                payment.journal_entry = journal_entry
                payment.save()
                
                # تحديث حالة القرض إذا تم السداد بالكامل
                if loan.remaining_balance <= 0:
                    loan.status = 'completed'
                    loan.save()
                
                messages.success(request, f'تم سداد القسط بنجاح. المبلغ: {amount}')
                
                # معالجة AJAX
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': f'تم سداد القسط بنجاح',
                        'redirect_url': reverse('financial:loan_detail', kwargs={'pk': loan.pk})
                    })
                
                return redirect('financial:loan_detail', pk=loan.pk)
            except Exception as e:
                error_message = f'خطأ في سداد القسط: {str(e)}'
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': error_message
                    })
                
                messages.error(request, error_message)
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors,
                    'message': 'يرجى تصحيح الأخطاء في النموذج'
                })
    
    return redirect('financial:loans_dashboard')


def create_loan_receipt_entry(loan, user):
    """
    إنشاء القيد المحاسبي لاستلام القرض
    
    من حـ/ البنك (أصول)
        إلى حـ/ القروض (خصوم)
    """
    # إنشاء القيد المحاسبي
    journal_entry = JournalEntry.objects.create(
        entry_type='automatic',
        date=loan.start_date,
        description=f"استلام قرض من {loan.lender_name}",
        created_by=user,
        status='posted'  # تم التصحيح: استخدام status بدلاً من is_posted
    )
    
    # السطر الأول: مدين - البنك (استلام المال)
    JournalEntryLine.objects.create(
        journal_entry=journal_entry,
        account=loan.bank_account,
        debit=loan.principal_amount,
        credit=Decimal('0.00'),
        description=f"استلام قرض {loan.loan_number}"
    )
    
    # السطر الثاني: دائن - القرض (الالتزام)
    JournalEntryLine.objects.create(
        journal_entry=journal_entry,
        account=loan.loan_account,
        debit=Decimal('0.00'),
        credit=loan.principal_amount,
        description=f"قرض من {loan.lender_name}"
    )
    
    return journal_entry


def create_loan_payment_entry(payment, user):
    """
    إنشاء القيد المحاسبي لسداد قسط القرض
    
    من مذكورين:
        حـ/ القروض (خصوم) - أصل القسط
        حـ/ فوائد القروض (مصروف) - الفوائد
            إلى حـ/ البنك (أصول)
    """
    loan = payment.loan
    # إنشاء القيد المحاسبي
    journal_entry = JournalEntry.objects.create(
        entry_type='automatic',
        date=payment.actual_payment_date,
        description=f"سداد قسط القرض {loan.loan_number} - قسط رقم {payment.payment_number}",
        created_by=user,
        status='posted'  # تم التصحيح: استخدام status بدلاً من is_posted
    )
    
    # السطر الأول: مدين - القرض (تخفيض الالتزام)
    JournalEntryLine.objects.create(
        journal_entry=journal_entry,
        account=loan.loan_account,
        debit=payment.principal_amount,
        credit=Decimal('0.00'),
        description=f"أصل القسط {payment.payment_number}"
    )
    
    # السطر الثاني: مدين - مصروف الفوائد (إذا وجد)
    if payment.interest_amount > 0 and loan.interest_expense_account:
        JournalEntryLine.objects.create(
            journal_entry=journal_entry,
            account=loan.interest_expense_account,
            debit=payment.interest_amount,
            credit=Decimal('0.00'),
            description=f"فوائد القسط {payment.payment_number}"
        )
    
    # السطر الثالث: دائن - البنك (الدفع)
    JournalEntryLine.objects.create(
        journal_entry=journal_entry,
        account=payment.payment_account,
        debit=Decimal('0.00'),
        credit=payment.amount,
        description=f"سداد قسط {payment.payment_number}"
    )
    
    return journal_entry


def create_payment_schedule(loan):
    """
    إنشاء جدول السداد للقرض
    """
    monthly_payment = loan.calculate_monthly_payment()
    current_date = loan.start_date
    remaining_principal = loan.principal_amount
    
    for i in range(1, loan.duration_months + 1):
        # حساب تاريخ القسط
        if loan.payment_frequency == 'monthly':
            payment_date = current_date + timezone.timedelta(days=30 * i)
        elif loan.payment_frequency == 'quarterly':
            payment_date = current_date + timezone.timedelta(days=90 * i)
        elif loan.payment_frequency == 'semi_annual':
            payment_date = current_date + timezone.timedelta(days=180 * i)
        else:  # annual
            payment_date = current_date + timezone.timedelta(days=365 * i)
        
        # حساب الفائدة والأصل
        if loan.interest_rate > 0:
            interest_amount = (remaining_principal * loan.interest_rate) / (Decimal('100') * Decimal('12'))
            principal_amount = monthly_payment - interest_amount
        else:
            interest_amount = Decimal('0.00')
            principal_amount = monthly_payment
        
        # التأكد من عدم تجاوز الرصيد المتبقي في القسط الأخير
        if i == loan.duration_months:
            principal_amount = remaining_principal
        
        # إنشاء سجل القسط
        LoanPayment.objects.create(
            loan=loan,
            payment_number=i,
            scheduled_date=payment_date,
            principal_amount=principal_amount,
            interest_amount=interest_amount,
            status='scheduled'
        )
        
        remaining_principal -= principal_amount


@login_required
def get_loan_balance(request):
    """
    API لجلب رصيد قرض معين
    """
    loan_id = request.GET.get('loan_id')
    
    if not loan_id:
        return JsonResponse({'error': 'معرف القرض مطلوب'}, status=400)
    
    try:
        loan = Loan.objects.get(pk=loan_id)
        
        return JsonResponse({
            'success': True,
            'loan_number': loan.loan_number,
            'principal_amount': float(loan.principal_amount),
            'total_paid': float(loan.total_paid),
            'remaining_balance': float(loan.remaining_balance),
            'monthly_payment': float(loan.calculate_monthly_payment()),
        })
    except Loan.DoesNotExist:
        return JsonResponse({'error': 'القرض غير موجود'}, status=404)
