"""
نماذج الأذونات
"""
from django import forms
from ..models import PermissionRequest, PermissionType, Employee


class PermissionRequestForm(forms.ModelForm):
    """نموذج طلب إذن - نفس نمط LeaveRequestForm"""
    
    # إضافة حقل اختيار الموظف (للـ HR فقط)
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(status='active'),
        label='الموظف',
        widget=forms.Select(attrs={'class': 'form-select select2-employee'}),
        required=True
    )
    
    class Meta:
        model = PermissionRequest
        fields = ['employee', 'permission_type', 'date', 'start_time', 'end_time', 'reason', 'is_extra', 'deduction_hours', 'is_deduction_exempt']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select select2-employee'}),
            'permission_type': forms.Select(attrs={'class': 'form-select select2-permission-type'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'اذكر سبب الإذن...'}),
            'is_extra': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'deduction_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25', 'min': '0'}),
            'is_deduction_exempt': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'employee': 'الموظف',
            'permission_type': 'نوع الإذن',
            'date': 'التاريخ',
            'start_time': 'وقت البداية',
            'end_time': 'وقت النهاية',
            'reason': 'السبب',
            'is_extra': 'إذن إضافي',
            'deduction_hours': 'ساعات الخصم',
            'is_deduction_exempt': 'معفي من الخصم',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # فقط الأنواع النشطة
        self.fields['permission_type'].queryset = PermissionType.objects.filter(is_active=True)
    
    def clean(self):
        """التحقق - نفس نمط LeaveRequestForm.clean()"""
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        
        if start_time and end_time:
            if end_time <= start_time:
                raise forms.ValidationError('وقت النهاية يجب أن يكون بعد وقت البداية')
        
        return cleaned_data
