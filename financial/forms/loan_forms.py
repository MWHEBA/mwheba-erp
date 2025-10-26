from django import forms
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal

from ..models.loan_transactions import Loan, LoanPayment
from ..models.chart_of_accounts import ChartOfAccounts


class LoanForm(forms.ModelForm):
    """
    نموذج إضافة/تعديل قرض
    """
    
    class Meta:
        model = Loan
        fields = [
            # 'loan_number',  # تم إزالته - يتم توليده تلقائياً
            'loan_type',
            'lender_type',
            'lender_name',
            'principal_amount',
            'interest_rate',
            'start_date',
            'duration_months',
            'payment_frequency',
            'loan_account',
            'bank_account',
            'interest_expense_account',
            'description',
            'notes',
        ]
        widgets = {
            'loan_type': forms.Select(attrs={'class': 'form-select'}),
            'lender_type': forms.Select(attrs={'class': 'form-select'}),
            'lender_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: البنك الأهلي المصري'
            }),
            'principal_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0.01'
            }),
            'interest_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0.00',
                'max': '100.00'
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'duration_months': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '12',
                'min': '1'
            }),
            'payment_frequency': forms.Select(attrs={'class': 'form-select'}),
            'loan_account': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'اختر حساب القرض (خصوم)'
            }),
            'bank_account': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'اختر الحساب البنكي'
            }),
            'interest_expense_account': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'اختر حساب مصروف الفوائد'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف القرض والغرض منه'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'ملاحظات إضافية (اختياري)'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # تخصيص خيارات الحسابات
        # حساب القرض - خصوم طويلة/قصيرة الأجل
        self.fields['loan_account'].queryset = ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True,
            account_type__category__in=['liability']
        ).order_by('code')
        
        # الحساب البنكي - أصول نقدية
        self.fields['bank_account'].queryset = ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True,
            account_type__category='asset'
        ).filter(
            models.Q(is_cash_account=True) | 
            models.Q(is_bank_account=True)
        ).order_by('code')
        
        # حساب مصروف الفوائد
        self.fields['interest_expense_account'].queryset = ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True,
            account_type__category='expense'
        ).order_by('code')
        
        # جعل حساب الفوائد اختياري إذا كان معدل الفائدة صفر
        self.fields['interest_expense_account'].required = False

    def clean(self):
        cleaned_data = super().clean()
        interest_rate = cleaned_data.get('interest_rate')
        interest_expense_account = cleaned_data.get('interest_expense_account')
        
        # التحقق من حساب الفوائد إذا كان معدل الفائدة أكبر من صفر
        if interest_rate and interest_rate > 0 and not interest_expense_account:
            raise ValidationError({
                'interest_expense_account': _('حساب مصروف الفوائد مطلوب عند وجود فائدة على القرض')
            })
        
        return cleaned_data


class LoanPaymentForm(forms.ModelForm):
    """
    نموذج سداد قسط قرض
    """
    
    class Meta:
        model = LoanPayment
        fields = [
            'loan',
            'actual_payment_date',
            'principal_amount',
            'interest_amount',
            'payment_account',
            'notes',
        ]
        widgets = {
            'loan': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'اختر القرض'
            }),
            'actual_payment_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'principal_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0.00'
            }),
            'interest_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0.00'
            }),
            'payment_account': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'اختر حساب الدفع'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'ملاحظات (اختياري)'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # تخصيص خيارات القروض - فقط القروض النشطة
        self.fields['loan'].queryset = Loan.objects.filter(
            status='active'
        ).order_by('-start_date')
        
        # حسابات الدفع - نقدية وبنكية فقط
        self.fields['payment_account'].queryset = ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True,
            account_type__category='asset'
        ).filter(
            models.Q(is_cash_account=True) | 
            models.Q(is_bank_account=True)
        ).order_by('code')

    def clean(self):
        cleaned_data = super().clean()
        loan = cleaned_data.get('loan')
        principal_amount = cleaned_data.get('principal_amount', Decimal('0.00'))
        
        if loan and principal_amount:
            # التحقق من عدم تجاوز الرصيد المتبقي
            if principal_amount > loan.remaining_balance:
                raise ValidationError({
                    'principal_amount': _(
                        f'المبلغ يتجاوز الرصيد المتبقي ({loan.remaining_balance})'
                    )
                })
        
        return cleaned_data


class QuickLoanPaymentForm(forms.Form):
    """
    نموذج سريع لسداد قسط (من لوحة التحكم)
    """
    
    loan = forms.ModelChoiceField(
        queryset=Loan.objects.filter(status='active'),
        label=_('القرض'),
        widget=forms.Select(attrs={
            'class': 'form-select',
            'required': True
        })
    )
    
    payment_date = forms.DateField(
        label=_('تاريخ الدفع'),
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'required': True
        })
    )
    
    amount = forms.DecimalField(
        label=_('المبلغ الإجمالي'),
        max_digits=15,
        decimal_places=2,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '0.00',
            'step': '0.01',
            'required': True
        })
    )
    
    payment_account = forms.ModelChoiceField(
        queryset=ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True,
            account_type__category='asset'
        ).filter(
            models.Q(is_cash_account=True) | 
            models.Q(is_bank_account=True)
        ),
        label=_('حساب الدفع'),
        widget=forms.Select(attrs={
            'class': 'form-select',
            'required': True
        })
    )
    
    notes = forms.CharField(
        label=_('ملاحظات'),
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'ملاحظات (اختياري)'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        loan = cleaned_data.get('loan')
        amount = cleaned_data.get('amount')
        
        if loan and amount:
            if amount > loan.remaining_balance:
                raise ValidationError({
                    'amount': _(
                        f'المبلغ يتجاوز الرصيد المتبقي ({loan.remaining_balance})'
                    )
                })
        
        return cleaned_data
