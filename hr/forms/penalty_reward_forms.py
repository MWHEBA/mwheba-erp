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

    # Override month as CharField to accept YYYY-MM from <input type="month">
    month = forms.CharField(
        label='شهر التطبيق',
        required=True,
        widget=forms.TextInput(attrs={'type': 'month', 'class': 'form-control'}),
    )

    class Meta:
        model = PenaltyReward
        fields = ['employee', 'category', 'month', 'calculation_method', 'value', 'reason']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'calculation_method': forms.Select(attrs={'class': 'form-select'}),
            'value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'اذكر السبب أو التفاصيل...'}),
        }
        labels = {
            'category': 'النوع',
            'date': 'التاريخ',
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
        month_raw = self.cleaned_data.get('month', '').strip()
        # Handle YYYY-MM format from <input type="month">
        if month_raw and len(month_raw) == 7:
            full_date = parse_date(f"{month_raw}-01")
            if full_date:
                return full_date
        # Handle full date string YYYY-MM-DD (e.g. when editing existing record)
        if month_raw and len(month_raw) == 10:
            full_date = parse_date(month_raw)
            if full_date:
                from datetime import date
                return date(full_date.year, full_date.month, 1)
        raise forms.ValidationError('صيغة الشهر غير صحيحة')

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
