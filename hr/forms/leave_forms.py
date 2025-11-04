"""
نماذج الإجازات
"""
from django import forms
from ..models import Leave


class LeaveRequestForm(forms.ModelForm):
    """نموذج طلب إجازة"""
    
    class Meta:
        model = Leave
        fields = ['leave_type', 'start_date', 'end_date', 'reason', 'attachment']
        widgets = {
            'leave_type': forms.Select(attrs={'class': 'form-select'}),
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
