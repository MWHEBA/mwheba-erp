"""
نماذج الرواتب
"""
from django import forms
from ..models import Payroll, Department


class PayrollForm(forms.ModelForm):
    """نموذج قسيمة الراتب"""
    
    # Override payment_method field to use dynamic choices
    payment_method = forms.ChoiceField(
        required=False,
        label='طريقة الدفع',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    class Meta:
        model = Payroll
        fields = ['employee', 'month', 'contract', 'financial_category', 'bonus', 
                  'other_deductions', 'payment_method', 'notes']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'month': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'month',
                'data-month-picker': True,
                'placeholder': 'اختر الشهر...'
            }),
            'contract': forms.Select(attrs={'class': 'form-select'}),
            'financial_category': forms.Select(attrs={
                'class': 'form-select',
                'required': False
            }),
            'bonus': forms.NumberInput(attrs={'class': 'form-control', 'step': '1'}),
            'other_deductions': forms.NumberInput(attrs={'class': 'form-control', 'step': '1'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # تعيين التصنيف الافتراضي "رواتب" إذا لم يكن محدداً
        if not self.instance.pk and not self.initial.get('financial_category'):
            from financial.models import FinancialCategory
            try:
                salaries_category = FinancialCategory.objects.get(code='salaries', is_active=True)
                self.fields['financial_category'].initial = salaries_category.id
            except FinancialCategory.DoesNotExist:
                pass
        
        # تحميل حسابات الدفع ديناميكياً
        try:
            from financial.models import ChartOfAccounts
            from django.db import models
            # البحث عن الحسابات النقدية والبنكية
            payment_accounts = ChartOfAccounts.objects.filter(
                is_active=True
            ).filter(
                models.Q(is_cash_account=True) | models.Q(is_bank_account=True)
            ).order_by('code')
            
            choices = [('', 'اختر حساب الدفع')]
            for account in payment_accounts:
                choices.append((account.code, f"{account.name} ({account.code})"))
            
            self.fields['payment_method'].choices = choices
            
            # MIGRATION SUPPORT: Handle old database values when editing existing records
            if self.instance and self.instance.pk and self.instance.payment_method:
                if self.instance.payment_method == 'cash':
                    # Legacy value: convert to default cash account
                    default_cash = ChartOfAccounts.objects.filter(code='10100', is_active=True).first()
                    if default_cash:
                        self.initial['payment_method'] = default_cash.code
                elif self.instance.payment_method == 'bank_transfer':
                    # Legacy value: convert to default bank account
                    default_bank = ChartOfAccounts.objects.filter(code='10200', is_active=True).first()
                    if default_bank:
                        self.initial['payment_method'] = default_bank.code
                else:
                    # Already an account code - use as is
                    self.initial['payment_method'] = self.instance.payment_method
        except Exception:
            # في حالة فشل التحميل، استخدم الخيارات الافتراضية
            self.fields['payment_method'].choices = [
                ('', 'اختر طريقة الدفع'),
                ('cash', 'نقداً'),
                ('bank_transfer', 'تحويل بنكي'),
            ]


class PayrollProcessForm(forms.Form):
    """نموذج معالجة رواتب الشهر"""
    
    month = forms.CharField(
        label='الشهر',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'data-month-picker': True,
            'placeholder': 'اختر الشهر...',
            'required': True
        })
    )
    
    department = forms.ModelChoiceField(
        label='القسم',
        queryset=Department.objects.filter(is_active=True),
        required=False,
        empty_label='جميع الأقسام',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # تعيين الشهر الحالي كقيمة افتراضية
        if not self.is_bound:
            from datetime import date
            current_month = date.today().strftime('%Y-%m')
            self.fields['month'].initial = current_month
