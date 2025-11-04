"""
نماذج ماكينات البصمة
"""
from django import forms
from ..models import BiometricDevice


class BiometricDeviceForm(forms.ModelForm):
    """نموذج ماكينات البصمة"""
    
    class Meta:
        model = BiometricDevice
        fields = ['device_name', 'device_code', 'device_type', 'serial_number', 'ip_address', 
                  'port', 'location', 'department', 'timezone', 'status', 'is_active']
        widgets = {
            'device_name': forms.TextInput(attrs={'class': 'form-control'}),
            'device_code': forms.TextInput(attrs={'class': 'form-control'}),
            'device_type': forms.Select(attrs={'class': 'form-select'}),
            'serial_number': forms.TextInput(attrs={'class': 'form-control'}),
            'ip_address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '192.168.1.100'}),
            'port': forms.NumberInput(attrs={'class': 'form-control', 'value': '4370'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'timezone': forms.TextInput(attrs={'class': 'form-control', 'value': 'Africa/Cairo'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'device_name': 'اسم الجهاز',
            'device_code': 'كود الجهاز',
            'device_type': 'نوع الجهاز',
            'serial_number': 'الرقم التسلسلي',
            'ip_address': 'عنوان IP',
            'port': 'المنفذ',
            'location': 'الموقع',
            'department': 'القسم',
            'timezone': 'المنطقة الزمنية',
            'status': 'الحالة',
            'is_active': 'نشط',
        }
