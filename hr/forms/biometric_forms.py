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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from hr.models import Employee

        # Get employees who already have an active mapping (exclude current instance when editing)
        mapped_employee_ids = BiometricUserMapping.objects.filter(is_active=True)
        if self.instance and self.instance.pk:
            mapped_employee_ids = mapped_employee_ids.exclude(employee=self.instance.employee)
        mapped_employee_ids = mapped_employee_ids.values_list('employee_id', flat=True)

        # Filter: active employees only, excluding those with an active mapping
        self.fields['employee'].queryset = Employee.objects.filter(
            status='active'
        ).exclude(
            id__in=mapped_employee_ids
        ).order_by('employee_number')

    class Meta:
        model = BiometricUserMapping
        fields = ['employee', 'biometric_user_id', 'device', 'is_active', 'notes']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'biometric_user_id': forms.TextInput(attrs={'class': 'form-control'}),
            'device': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'employee': 'الموظف',
            'biometric_user_id': 'معرف البصمة',
            'device': 'الماكينة (اختياري)',
            'is_active': 'نشط',
            'notes': 'ملاحظات',
        }


class BulkMappingForm(forms.Form):
    """نموذج الاستيراد الجماعي من CSV"""
    csv_file = forms.FileField(
        label='ملف CSV',
        help_text='يجب أن يحتوي الملف على الأعمدة: employee_number, biometric_user_id, device_code (اختياري)',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.csv'})
    )
    skip_errors = forms.BooleanField(
        required=False,
        initial=True,
        label='تخطي الأخطاء',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    def process_csv(self):
        """معالجة ملف CSV وإنشاء الربط"""
        csv_file = self.cleaned_data['csv_file']
        skip_errors = self.cleaned_data.get('skip_errors', True)
        
        # قراءة الملف مع معالجة encoding مختلفة
        try:
            file_data = csv_file.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                csv_file.seek(0)
                file_data = csv_file.read().decode('utf-8')
            except UnicodeDecodeError:
                csv_file.seek(0)
                file_data = csv_file.read().decode('latin-1')
        
        # إزالة BOM إذا كان موجود في بداية الملف
        file_data = file_data.lstrip('\ufeff')
        
        # محاولة اكتشاف الـ delimiter تلقائياً
        sniffer = csv.Sniffer()
        try:
            sample = file_data[:1024]
            dialect = sniffer.sniff(sample)
            csv_reader = csv.DictReader(io.StringIO(file_data), dialect=dialect)
        except:
            # استخدام الـ delimiter الافتراضي
            csv_reader = csv.DictReader(io.StringIO(file_data))
        
        stats = {
            'created': 0,
            'updated': 0,
            'errors': [],
            'skipped': 0
        }
        
        # تنظيف أسماء الأعمدة من BOM
        if csv_reader.fieldnames:
            csv_reader.fieldnames = [field.lstrip('\ufeff').strip() for field in csv_reader.fieldnames]
        
        # التحقق من وجود الأعمدة المطلوبة
        fieldnames = csv_reader.fieldnames
        if not fieldnames or 'employee_number' not in fieldnames or 'biometric_user_id' not in fieldnames:
            stats['errors'].append(f'الملف يجب أن يحتوي على الأعمدة: employee_number, biometric_user_id, device_code (اختياري). الأعمدة الموجودة: {fieldnames}')
            return stats
        
        for row_num, row in enumerate(csv_reader, start=2):
            try:
                # قراءة البيانات وتنظيفها (إزالة المسافات والأحرف الخاصة والـ BOM)
                employee_number = str(row.get('employee_number', '')).lstrip('\ufeff').strip()
                biometric_user_id = str(row.get('biometric_user_id', '')).lstrip('\ufeff').strip()
                device_code = str(row.get('device_code', '')).lstrip('\ufeff').strip()
                
                # تخطي السطور الفاضية تماماً
                if not employee_number and not biometric_user_id and not device_code:
                    stats['skipped'] += 1
                    continue
                
                # التحقق من البيانات الأساسية المطلوبة
                if not employee_number or not biometric_user_id:
                    error_msg = f'السطر {row_num}: بيانات ناقصة (employee_number="{employee_number or "فارغ"}", biometric_user_id="{biometric_user_id or "فارغ"}")'
                    stats['errors'].append(error_msg)
                    if not skip_errors:
                        break
                    continue
                
                # البحث عن الموظف
                try:
                    employee = Employee.objects.get(employee_number=employee_number)
                except Employee.DoesNotExist:
                    error_msg = f'السطر {row_num}: الموظف "{employee_number}" غير موجود في النظام'
                    stats['errors'].append(error_msg)
                    if not skip_errors:
                        break
                    continue
                
                # البحث عن الماكينة إذا كان device_code موجود
                device = None
                if device_code:
                    try:
                        device = BiometricDevice.objects.get(device_code=device_code, is_active=True)
                    except BiometricDevice.DoesNotExist:
                        error_msg = f'السطر {row_num}: الماكينة "{device_code}" غير موجودة أو غير نشطة'
                        stats['errors'].append(error_msg)
                        if not skip_errors:
                            break
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
                error_msg = f'السطر {row_num}: خطأ غير متوقع - {str(e)}'
                stats['errors'].append(error_msg)
                if not skip_errors:
                    break
        
        return stats
