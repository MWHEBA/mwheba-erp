"""
نماذج الرواتب
"""
from django import forms
from ..models import Payroll, Department


class PayrollForm(forms.ModelForm):
    """نموذج قسيمة الراتب"""
    
    class Meta:
        model = Payroll
        fields = ['employee', 'month', 'contract', 'bonus', 'other_deductions', 
                  'payment_method', 'notes']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'month': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'month',
                'data-month-picker': True,
                'placeholder': 'اختر الشهر...'
            }),
            'contract': forms.Select(attrs={'class': 'form-select'}),
            'bonus': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'other_deductions': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


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
