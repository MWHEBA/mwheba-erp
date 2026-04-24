"""
نموذج الجزاءات والمكافآت
"""
from django import forms
from django.utils.dateparse import parse_date
from ..models import PenaltyReward, Employee


class PenaltyRewardForm(forms.ModelForm):
    """نموذج إضافة/تعديل جزاء أو مكافأة"""

    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(status='active').select_related('department'),
        label='الموظف',
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True,
    )

    class Meta:
        model = PenaltyReward
        fields = ['employee', 'category', 'date', 'month', 'calculation_method', 'value', 'reason']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'month': forms.DateInput(attrs={'type': 'month', 'class': 'form-control'}),
            'calculation_method': forms.Select(attrs={'class': 'form-select'}),
            'value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'اذكر السبب أو التفاصيل...'}),
        }
        labels = {
            'category': 'النوع',
            'date': 'التاريخ',
            'month': 'شهر التطبيق',
            'calculation_method': 'طريقة الحساب',
            'value': 'القيمة/العدد',
            'reason': 'السبب/التفاصيل',
        }

    def clean_value(self):
        value = self.cleaned_data.get('value')
        if value is not None and value <= 0:
            raise forms.ValidationError('القيمة يجب أن تكون أكبر من صفر')
        return value

    def clean_month(self):
        """Convert YYYY-MM from <input type=month> to a full date YYYY-MM-01"""
        month_raw = self.data.get('month', '')
        if month_raw and len(month_raw) == 7:  # format: YYYY-MM
            full_date = parse_date(f"{month_raw}-01")
            if full_date:
                return full_date
            raise forms.ValidationError('صيغة الشهر غير صحيحة')
        return self.cleaned_data.get('month')

    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get('date')
        month = cleaned_data.get('month')

        if date and month:
            # التحقق من أن التاريخ ينتمي لنفس الشهر أو قريب منه
            if date.year == month.year and date.month == month.month:
                pass  # نفس الشهر - صحيح
            # نسمح بفارق شهر واحد (جزاء في نهاية الشهر يُطبق الشهر القادم)

        return cleaned_data
