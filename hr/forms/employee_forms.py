"""
نماذج الموظفين
"""
from django import forms
from ..models import Employee, Department, JobTitle


class EmployeeForm(forms.ModelForm):
    """نموذج إضافة/تعديل موظف"""
    
    class Meta:
        model = Employee
        fields = [
            'employee_number', 'name', 'national_id',
            'birth_date', 'gender', 'marital_status',
            'military_status', 'personal_email', 'work_email',
            'mobile_phone', 'home_phone', 'address', 'city', 'postal_code',
            'emergency_contact_name', 'emergency_contact_relation', 'emergency_contact_phone',
            'department', 'job_title', 'direct_manager', 'shift',
            'attendance_exempt', 'hire_date', 'employment_type', 'photo',
            'is_insurance_only'
        ]
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'hire_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'employee_number': forms.TextInput(attrs={
                'class': 'form-control', 
                'readonly': 'readonly',
                'style': 'background-color: var(--bg-secondary); cursor: not-allowed;'
            }),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '14'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'marital_status': forms.Select(attrs={'class': 'form-select'}),
            'military_status': forms.Select(attrs={'class': 'form-select'}),
            'personal_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'work_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'mobile_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'home_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact_name': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact_relation': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'job_title': forms.Select(attrs={'class': 'form-select'}),
            'direct_manager': forms.Select(attrs={'class': 'form-select'}),
            'shift': forms.Select(attrs={'class': 'form-select'}),
            'biometric_user_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم الموظف في جهاز البصمة'}),
            'employment_type': forms.Select(attrs={'class': 'form-select'}),
            'photo': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # التأكد من تطبيق الـ classes على جميع الحقول
        self.fields['department'].widget.attrs.update({'class': 'form-select'})
        self.fields['job_title'].widget.attrs.update({'class': 'form-select'})
        
        # جعل رقم الموظف اختياري للتوليد التلقائي
        self.fields['employee_number'].required = False
        
        # جعل الحقول التالية اختيارية
        self.fields['personal_email'].required = False
        self.fields['work_email'].required = False
        self.fields['address'].required = False
        self.fields['city'].required = False
        
        # الوردية مطلوبة دائماً
        self.fields['shift'].required = True
        
        # تعيين أول وردية نشطة كـ default للموظفين الجدد
        if not self.instance.pk and not self.initial.get('shift'):
            from ..models import Shift
            first_shift = Shift.objects.filter(is_active=True).order_by('id').first()
            if first_shift:
                self.fields['shift'].initial = first_shift.pk
        
        # تحديث placeholder للحقول الاختيارية
        self.fields['personal_email'].widget.attrs.update({'placeholder': 'البريد الشخصي (اختياري)'})
        self.fields['work_email'].widget.attrs.update({'placeholder': 'البريد الوظيفي (اختياري)'})
        self.fields['address'].widget.attrs.update({'placeholder': 'العنوان (اختياري)'})
        self.fields['city'].widget.attrs.update({'placeholder': 'المدينة (اختياري)'})
        
        # جعل رقم الموظف read-only دائماً (التأكد من تطبيقه)
        self.fields['employee_number'].widget.attrs.update({
            'readonly': 'readonly',
            'style': 'background-color: var(--bg-secondary); cursor: not-allowed;'
        })
        
        # إذا كان نموذج جديد، عرض الرقم المقترح
        if not self.instance.pk:
            next_number = self.generate_employee_number()
            self.fields['employee_number'].initial = next_number
            self.fields['employee_number'].widget.attrs['placeholder'] = f'الرقم المقترح: {next_number}'
            
            # تعيين تاريخ التعيين الافتراضي لليوم
            from datetime import date
            self.fields['hire_date'].initial = date.today()
    
    @staticmethod
    def generate_employee_number():
        """توليد رقم موظف تلقائي"""
        last_employee = Employee.objects.filter(
            employee_number__startswith='EMP-'
        ).order_by('-employee_number').first()
        
        if last_employee:
            try:
                last_number = int(last_employee.employee_number.split('-')[1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = 1
        else:
            new_number = 1
        
        return f"EMP-{new_number:02d}"
    
    def clean_national_id(self):
        """التحقق من صحة الرقم القومي وعدم تكراره"""
        national_id = self.cleaned_data.get('national_id')
        if national_id:
            # التحقق من الطول (14 رقم)
            if len(national_id) != 14:
                raise forms.ValidationError('الرقم القومي يجب أن يكون 14 رقم')
            
            # التحقق من أنه أرقام فقط
            if not national_id.isdigit():
                raise forms.ValidationError('الرقم القومي يجب أن يحتوي على أرقام فقط')
            
            # التحقق من عدم التكرار
            existing = Employee.objects.filter(national_id=national_id)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise forms.ValidationError('هذا الرقم القومي مستخدم بالفعل من قبل موظف آخر')
        
        return national_id
    
    def clean_work_email(self):
        """التحقق من عدم تكرار البريد الإلكتروني الوظيفي (إذا تم إدخاله)"""
        work_email = self.cleaned_data.get('work_email')
        if work_email:  # فقط إذا تم إدخال بريد إلكتروني
            # التحقق من عدم وجود البريد في موظف آخر
            existing = Employee.objects.filter(work_email=work_email)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise forms.ValidationError('هذا البريد الإلكتروني الوظيفي مستخدم بالفعل من قبل موظف آخر')
        
        return work_email
    
    def clean_personal_email(self):
        """التحقق من عدم تكرار البريد الإلكتروني الشخصي (إذا تم إدخاله)"""
        personal_email = self.cleaned_data.get('personal_email')
        if personal_email:  # فقط إذا تم إدخال بريد إلكتروني
            # التحقق من عدم وجود البريد في موظف آخر
            existing = Employee.objects.filter(personal_email=personal_email)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise forms.ValidationError('هذا البريد الإلكتروني الشخصي مستخدم بالفعل من قبل موظف آخر')
        
        return personal_email
    
    def clean_mobile_phone(self):
        """التحقق من صحة رقم الموبايل وعدم تكراره"""
        mobile_phone = self.cleaned_data.get('mobile_phone')
        if mobile_phone:
            import re
            
            # إزالة المسافات والشرطات
            mobile_phone = mobile_phone.replace(' ', '').replace('-', '')
            
            # تحويل الصيغ المختلفة إلى الصيغة المحلية
            # +201229609292 أو 201229609292 → 01229609292
            if mobile_phone.startswith('+20'):
                mobile_phone = '0' + mobile_phone[3:]
            elif mobile_phone.startswith('20') and len(mobile_phone) == 12:
                mobile_phone = '0' + mobile_phone[2:]
            
            # التحقق من الصيغة النهائية (11 رقم تبدأ بـ 01)
            if not re.match(r'^01[0-2,5]{1}[0-9]{8}$', mobile_phone):
                raise forms.ValidationError('رقم الموبايل غير صحيح. الصيغ المقبولة: 01xxxxxxxxx أو +2001xxxxxxxxx أو 2001xxxxxxxxx')
            
            # التحقق من عدم التكرار
            existing = Employee.objects.filter(mobile_phone=mobile_phone)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise forms.ValidationError('رقم الموبايل مستخدم بالفعل من قبل موظف آخر')
        
        return mobile_phone
    
    def clean_employee_number(self):
        """التأكد من عدم تغيير رقم الموظف عند التعديل"""
        employee_number = self.cleaned_data.get('employee_number')
        
        # إذا كان موظف موجود، استخدم الرقم الأصلي
        if self.instance.pk:
            return self.instance.employee_number
        
        # إذا كان موظف جديد ولم يتم إدخال رقم، قم بتوليده
        if not employee_number:
            return self.generate_employee_number()
        
        return employee_number


class DepartmentForm(forms.ModelForm):
    """نموذج إضافة/تعديل قسم"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from financial.models import FinancialSubcategory
            self.fields['financial_subcategory'].queryset = FinancialSubcategory.objects.filter(
                parent_category__code='salaries',
                is_active=True
            ).select_related('parent_category').order_by('display_order', 'name')
            self.fields['financial_subcategory'].empty_label = 'بدون تصنيف'
        except Exception:
            pass

    class Meta:
        model = Department
        fields = ['code', 'name_ar', 'name_en', 'description', 'parent', 'manager', 'financial_subcategory', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name_ar': forms.TextInput(attrs={'class': 'form-control'}),
            'name_en': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'manager': forms.Select(attrs={'class': 'form-select'}),
            'financial_subcategory': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class JobTitleForm(forms.ModelForm):
    """نموذج إضافة/تعديل مسمى وظيفي"""
    
    class Meta:
        model = JobTitle
        fields = ['code', 'title_ar', 'title_en', 'description', 'department', 
                  'responsibilities', 'requirements', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'readonly': 'readonly',
                'placeholder': 'سيتم توليده تلقائياً'
            }),
            'title_ar': forms.TextInput(attrs={'class': 'form-control'}),
            'title_en': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'responsibilities': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'requirements': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # جعل حقل الكود اختياري
        self.fields['code'].required = False
        
        # إذا كان نموذج جديد، عرض الكود المقترح
        if not self.instance.pk:
            self.fields['code'].initial = JobTitle.generate_code()
            self.fields['code'].widget.attrs['placeholder'] = f'الكود المقترح: {JobTitle.generate_code()}'
