"""
نماذج الحضور
"""
from django import forms
from ..models import Attendance, Shift


class AttendanceForm(forms.ModelForm):
    """نموذج تسجيل الحضور"""
    
    class Meta:
        model = Attendance
        fields = ['employee', 'date', 'shift', 'check_in', 'check_out', 'notes']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'shift': forms.Select(attrs={'class': 'form-select'}),
            'check_in': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'check_out': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class ShiftForm(forms.ModelForm):
    """نموذج الورديات"""
    
    class Meta:
        model = Shift
        fields = ['name', 'shift_type', 'start_time', 'end_time', 'grace_period_in', 'grace_period_out', 'work_hours', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: الوردية الصباحية'}),
            'shift_type': forms.Select(attrs={'class': 'form-select'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'grace_period_in': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'grace_period_out': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'work_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'min': '0'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': 'اسم الوردية',
            'shift_type': 'نوع الوردية',
            'start_time': 'وقت البداية',
            'end_time': 'وقت النهاية',
            'grace_period_in': 'فترة السماح للحضور (دقائق)',
            'grace_period_out': 'فترة السماح للانصراف (دقائق)',
            'work_hours': 'ساعات العمل',
            'is_active': 'نشط',
        }
