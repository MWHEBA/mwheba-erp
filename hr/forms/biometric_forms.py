"""
نماذج ماكينات البصمة
"""
from django import forms
from ..models import BiometricDevice, BiometricUserMapping, Employee
import csv
import io


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


class BiometricUserMappingForm(forms.ModelForm):
    """نموذج ربط معرف البصمة بالموظف"""
    
    class Meta:
        model = BiometricUserMapping
        fields = ['employee', 'biometric_user_id', 'device', 'is_active']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'biometric_user_id': forms.TextInput(attrs={'class': 'form-control'}),
            'device': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'employee': 'الموظف',
            'biometric_user_id': 'معرف البصمة',
            'device': 'الماكينة (اختياري)',
            'is_active': 'نشط',
        }


class BulkMappingForm(forms.Form):
    """نموذج الاستيراد الجماعي من CSV"""
    csv_file = forms.FileField(
        label='ملف CSV',
        help_text='يجب أن يحتوي الملف على الأعمدة: employee_number, biometric_user_id',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.csv'})
    )
    device = forms.ModelChoiceField(
        queryset=BiometricDevice.objects.filter(is_active=True),
        required=False,
        label='الماكينة (اختياري)',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def process_csv(self):
        """معالجة ملف CSV وإنشاء الربط"""
        csv_file = self.cleaned_data['csv_file']
        device = self.cleaned_data.get('device')
        
        # قراءة الملف
        file_data = csv_file.read().decode('utf-8-sig')
        csv_reader = csv.DictReader(io.StringIO(file_data))
        
        stats = {
            'created': 0,
            'updated': 0,
            'errors': []
        }
        
        for row_num, row in enumerate(csv_reader, start=2):
            try:
                employee_number = row.get('employee_number', '').strip()
                biometric_user_id = row.get('biometric_user_id', '').strip()
                
                if not employee_number or not biometric_user_id:
                    stats['errors'].append(f'السطر {row_num}: بيانات ناقصة')
                    continue
                
                # البحث عن الموظف
                try:
                    employee = Employee.objects.get(employee_number=employee_number)
                except Employee.DoesNotExist:
                    stats['errors'].append(f'السطر {row_num}: الموظف {employee_number} غير موجود')
                    continue
                
                # إنشاء أو تحديث الربط
                mapping, created = BiometricUserMapping.objects.update_or_create(
                    employee=employee,
                    device=device,
                    defaults={
                        'biometric_user_id': biometric_user_id,
                        'is_active': True
                    }
                )
                
                if created:
                    stats['created'] += 1
                else:
                    stats['updated'] += 1
                    
            except Exception as e:
                stats['errors'].append(f'السطر {row_num}: {str(e)}')
        
        return stats
