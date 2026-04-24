"""
نموذج الإجازات الرسمية
"""
from django import forms
from ..models import OfficialHoliday


class OfficialHolidayForm(forms.ModelForm):
    class Meta:
        model = OfficialHoliday
        fields = ['name', 'start_date', 'end_date', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: عيد الأضحى'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'data-date-picker': True}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'data-date-picker': True}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError('تاريخ النهاية يجب أن يكون بعد أو يساوي تاريخ البداية')
        return cleaned_data
