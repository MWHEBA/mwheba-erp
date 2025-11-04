"""
نماذج الرواتب
"""
from django import forms
from ..models import Payroll, Department


class PayrollForm(forms.ModelForm):
    """نموذج كشف الراتب"""
    
    class Meta:
        model = Payroll
        fields = ['employee', 'month', 'salary', 'bonus', 'other_deductions', 
                  'payment_method', 'notes']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'month': forms.DateInput(attrs={'type': 'month', 'class': 'form-control'}),
            'salary': forms.Select(attrs={'class': 'form-select'}),
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
            'type': 'month',
            'class': 'form-control',
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
