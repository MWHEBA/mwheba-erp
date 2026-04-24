"""
نماذج الإجازات
"""
from django import forms
from ..models import Leave, Employee, LeaveType


class LeaveRequestForm(forms.ModelForm):
    """نموذج طلب إجازة - HR يطلب نيابة عن الموظف"""

    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(status='active', is_insurance_only=False),
        label='الموظف',
        widget=forms.Select(attrs={'class': 'form-select select2-employee'}),
        required=True
    )

    leave_type = forms.ModelChoiceField(
        queryset=LeaveType.objects.filter(is_active=True).order_by('category', 'name_ar'),
        label='نوع الإجازة',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_leave_type'}),
        required=True,
        empty_label='اختر نوع الإجازة'
    )

    class Meta:
        model = Leave
        fields = ['employee', 'leave_type', 'start_date', 'end_date', 'reason', 'attachment']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'اكتب سبب الإجازة...'}),
            'attachment': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date:
            if end_date < start_date:
                raise forms.ValidationError('تاريخ النهاية يجب أن يكون بعد تاريخ البداية')

        return cleaned_data
