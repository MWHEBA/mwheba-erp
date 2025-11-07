"""
نماذج العقود
"""
from django import forms
from ..models import Contract
from datetime import timedelta


class ContractForm(forms.ModelForm):
    """نموذج العقود"""
    
    # حقل إضافي لمدة العقد
    DURATION_CHOICES = [
        ('', 'اختر المدة'),
        ('3', '3 أشهر'),
        ('6', '6 أشهر'),
        ('12', '1 سنة'),
        ('24', '2 سنة'),
        ('36', '3 سنوات'),
        ('custom', 'مدة مخصصة'),
    ]
    
    contract_duration = forms.ChoiceField(
        choices=DURATION_CHOICES,
        required=False,
        label='مدة العقد',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_contract_duration'})
    )
    
    class Meta:
        model = Contract
        fields = ['contract_number', 'employee', 'contract_type', 'job_title', 'department',
                  'biometric_user_id', 'start_date', 'end_date', 
                  'probation_period_months', 'basic_salary',
                  'has_annual_increase', 'annual_increase_percentage', 
                  'increase_frequency', 'increase_start_reference',
                  'auto_renew', 'terms_and_conditions', 'status', 'notes']
        widgets = {
            'contract_number': forms.TextInput(attrs={
                'class': 'form-control',
                'readonly': 'readonly',
                'style': 'background-color: #e9ecef;'
            }),
            'employee': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_employee',
                'data-placeholder': 'اختر الموظف'
            }),
            'contract_type': forms.Select(attrs={'class': 'form-select'}),
            'job_title': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'اختر الوظيفة'
            }),
            'department': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': 'اختر القسم'
            }),
            'biometric_user_id': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '',
                'min': '1'
            }),
            'start_date': forms.TextInput(attrs={
                'class': 'form-control',
                'id': 'id_start_date',
                'data-date-picker': '',
                'placeholder': 'اختر تاريخ البداية'
            }),
            'end_date': forms.TextInput(attrs={
                'class': 'form-control',
                'id': 'id_end_date',
                'data-date-picker': '',
                'placeholder': 'اختر تاريخ النهاية'
            }),
            'probation_period_months': forms.NumberInput(attrs={'class': 'form-control', 'value': '3'}),
            'basic_salary': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_basic_salary', 'step': '0.01'}),
            'has_annual_increase': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_has_annual_increase'}),
            'annual_increase_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
            'increase_frequency': forms.Select(attrs={'class': 'form-select'}),
            'increase_start_reference': forms.Select(attrs={'class': 'form-select'}),
            'auto_renew': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_auto_renew'}),
            'terms_and_conditions': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'contract_number': 'رقم العقد',
            'employee': 'الموظف',
            'contract_type': 'نوع العقد',
            'job_title': 'المسمى الوظيفي',
            'department': 'القسم',
            'biometric_user_id': 'رقم البصمة',
            'start_date': 'تاريخ البداية',
            'end_date': 'تاريخ النهاية',
            'probation_period_months': 'فترة التجربة (بالأشهر)',
            'basic_salary': 'الراتب الأساسي',
            'has_annual_increase': 'يستحق زيادة سنوية',
            'annual_increase_percentage': 'نسبة الزيادة السنوية الإجمالية (%)',
            'increase_frequency': 'عدد مرات التطبيق في السنة',
            'increase_start_reference': 'بداية احتساب الزيادة',
            'auto_renew': 'تجديد تلقائي',
            'terms_and_conditions': 'البنود والشروط',
            'status': 'الحالة',
            'notes': 'ملاحظات',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # إخفاء حقل الحالة دائماً (يتم التحكم فيه من خلال الأزرار)
        self.fields['status'].widget = forms.HiddenInput()
        self.fields['status'].label = ''  # إخفاء الـ label
        
        # إذا كان نموذج جديد، عرض الرقم المقترح
        if not self.instance.pk:
            next_number = self.generate_contract_number()
            self.fields['contract_number'].initial = next_number
            self.fields['contract_number'].widget.attrs['placeholder'] = f'الرقم المقترح: {next_number}'
            
            # تعيين الحالة الافتراضية كـ "مسودة"
            self.fields['status'].initial = 'draft'
            
            # نسخ بيانات الوظيفة من الموظف (إذا كان محدد)
            if 'employee' in self.data:
                try:
                    from .models import Employee
                    employee_id = self.data.get('employee')
                    if employee_id:
                        employee = Employee.objects.get(pk=employee_id)
                        if employee.job_title and not self.data.get('job_title'):
                            self.fields['job_title'].initial = employee.job_title
                        if employee.department and not self.data.get('department'):
                            self.fields['department'].initial = employee.department
                        
                        # جلب رقم البصمة من BiometricUserMapping
                        if not self.data.get('biometric_user_id'):
                            from hr.models import BiometricUserMapping
                            biometric_mapping = BiometricUserMapping.objects.filter(employee=employee, is_active=True).first()
                            if biometric_mapping:
                                self.fields['biometric_user_id'].initial = biometric_mapping.biometric_user_id
                except:
                    pass
            
            # إضافة help text للحقول الجديدة
            self.fields['job_title'].help_text = '<i class="fas fa-info-circle me-1"></i>سيتم نسخها من ملف الموظف تلقائياً'
            self.fields['department'].help_text = '<i class="fas fa-info-circle me-1"></i>سيتم نسخها من ملف الموظف تلقائياً'
            self.fields['biometric_user_id'].help_text = '<i class="fas fa-info-circle me-1"></i>اختياري - سيتم ربط الموظف بجهاز البصمة تلقائياً'
        else:
            # في حالة التعديل: منع تغيير الموظف وتاريخ البداية
            self.fields['employee'].disabled = True
            self.fields['employee'].widget.attrs['readonly'] = 'readonly'
            self.fields['employee'].widget.attrs['style'] = 'background-color: #e9ecef; pointer-events: none;'
            self.fields['employee'].help_text = '⚠️ لا يمكن تغيير الموظف بعد إنشاء العقد'
            
            self.fields['start_date'].disabled = True
            self.fields['start_date'].widget.attrs['readonly'] = 'readonly'
            self.fields['start_date'].widget.attrs['style'] = 'background-color: #e9ecef; pointer-events: none;'
            self.fields['start_date'].help_text = '⚠️ لا يمكن تغيير تاريخ البداية بعد إنشاء العقد'
            
            # منع تغيير الوظيفة والبصمة عند التعديل
            self.fields['job_title'].disabled = True
            self.fields['job_title'].widget.attrs['readonly'] = 'readonly'
            self.fields['job_title'].widget.attrs['style'] = 'background-color: #e9ecef; pointer-events: none;'
            self.fields['job_title'].help_text = '⚠️ لا يمكن تغيير الوظيفة. للترقية، استخدم خاصية التجديد'
            
            self.fields['department'].disabled = True
            self.fields['department'].widget.attrs['readonly'] = 'readonly'
            self.fields['department'].widget.attrs['style'] = 'background-color: #e9ecef; pointer-events: none;'
            self.fields['department'].help_text = '⚠️ لا يمكن تغيير القسم. للنقل، استخدم خاصية التجديد'
            
            # البصمة: عرض الرقم الحالي من BiometricUserMapping
            from hr.models import BiometricUserMapping
            biometric_mapping = BiometricUserMapping.objects.filter(employee=self.instance.employee, is_active=True).first()
            if biometric_mapping:
                self.fields['biometric_user_id'].disabled = True
                self.fields['biometric_user_id'].initial = biometric_mapping.biometric_user_id
                self.fields['biometric_user_id'].widget.attrs['readonly'] = 'readonly'
                self.fields['biometric_user_id'].widget.attrs['style'] = 'background-color: #e9ecef;'
                self.fields['biometric_user_id'].help_text = '⚠️ الموظف مربوط بالفعل برقم بصمة. للتغيير، اذهب لصفحة ربط البصمة'
    
    @staticmethod
    def generate_contract_number():
        """توليد رقم عقد تلقائي"""
        last_contract = Contract.objects.filter(
            contract_number__startswith='CON-'
        ).order_by('-contract_number').first()
        
        if last_contract:
            try:
                last_number = int(last_contract.contract_number.split('-')[1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = 1
        else:
            new_number = 1
        
        return f"CON-{new_number:04d}"
    
    def clean_employee(self):
        """منع تغيير الموظف في حالة التعديل"""
        employee = self.cleaned_data.get('employee')
        
        # إذا كان تعديل لعقد موجود
        if self.instance.pk:
            # التحقق من أن الموظف لم يتغير
            if employee != self.instance.employee:
                raise forms.ValidationError('لا يمكن تغيير الموظف بعد إنشاء العقد')
        
        return employee
    
    def clean_start_date(self):
        """منع تغيير تاريخ البداية في حالة التعديل"""
        start_date = self.cleaned_data.get('start_date')
        
        # إذا كان تعديل لعقد موجود
        if self.instance.pk:
            # التحقق من أن تاريخ البداية لم يتغير
            if start_date != self.instance.start_date:
                raise forms.ValidationError('لا يمكن تغيير تاريخ البداية بعد إنشاء العقد')
        
        return start_date
    
    def clean_contract_number(self):
        """التحقق من رقم العقد وتوليده تلقائياً إذا لزم الأمر"""
        contract_number = self.cleaned_data.get('contract_number')
        
        # إذا كان عقد جديد ولم يتم إدخال رقم، قم بتوليده
        if not contract_number:
            return self.generate_contract_number()
        
        return contract_number
    
    def clean_biometric_user_id(self):
        """التحقق من رقم البصمة"""
        biometric_id = self.cleaned_data.get('biometric_user_id')
        employee = self.cleaned_data.get('employee')
        status = self.cleaned_data.get('status')
        
        if not biometric_id:
            return biometric_id
        
        if employee:
            from hr.models import BiometricUserMapping, Contract
            
            # 1. التحقق من تفرد رقم البصمة (لا يمكن لموظفين مختلفين استخدام نفس الرقم)
            conflicting_mapping = BiometricUserMapping.objects.filter(
                biometric_user_id=str(biometric_id),
                is_active=True
            ).exclude(employee=employee).first()
            
            if conflicting_mapping:
                raise forms.ValidationError(
                    f'⚠️ رقم البصمة ({biometric_id}) مستخدم بالفعل من قبل موظف آخر: '
                    f'{conflicting_mapping.employee.get_full_name_ar()} ({conflicting_mapping.employee.employee_number}). '
                    f'يرجى اختيار رقم بصمة مختلف.'
                )
            
            # 2. التحقق من عدم وجود عقد ساري آخر برقم بصمة مختلف
            if status == 'active':
                # البحث عن عقود سارية أخرى لنفس الموظف
                other_active_contracts = Contract.objects.filter(
                    employee=employee,
                    status='active'
                )
                
                # استثناء العقد الحالي عند التعديل
                if self.instance.pk:
                    other_active_contracts = other_active_contracts.exclude(pk=self.instance.pk)
                
                # التحقق من تطابق أرقام البصمة
                for contract in other_active_contracts:
                    if contract.biometric_user_id and contract.biometric_user_id != biometric_id:
                        raise forms.ValidationError(
                            f'⚠️ يوجد عقد ساري آخر ({contract.contract_number}) '
                            f'برقم بصمة مختلف ({contract.biometric_user_id}). '
                            f'لا يمكن أن يكون للموظف عقدين ساريين بأرقام بصمة مختلفة. '
                            f'الحلول: (1) إنهاء العقد القديم أولاً، (2) استخدام نفس رقم البصمة ({contract.biometric_user_id})'
                        )
        
        return biometric_id
    
    def clean(self):
        """
        التحقق الشامل من البيانات
        - منع تداخل العقود
        - التأكد من صحة التواريخ
        - التحقق من بيانات الوظيفة
        """
        cleaned_data = super().clean()
        employee = cleaned_data.get('employee')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        job_title = cleaned_data.get('job_title')
        department = cleaned_data.get('department')
        
        # التحقق من التواريخ
        if start_date and end_date and end_date <= start_date:
            raise forms.ValidationError({
                'end_date': 'تاريخ النهاية يجب أن يكون بعد تاريخ البداية'
            })
        
        # التحقق من تداخل العقود (فقط للعقود الجديدة أو عند تغيير التواريخ)
        if employee and start_date:
            # الحالات المسموح بها للعقود المتداخلة
            allowed_statuses = ['expired', 'terminated', 'suspended', 'renewed']
            
            # البحث عن عقود متداخلة
            overlapping_contracts = Contract.objects.filter(
                employee=employee
            ).exclude(
                status__in=allowed_statuses
            )
            
            # استثناء العقد الحالي عند التعديل
            if self.instance.pk:
                overlapping_contracts = overlapping_contracts.exclude(pk=self.instance.pk)
            
            # التحقق من التداخل
            for contract in overlapping_contracts:
                # حالة 1: العقد الموجود مفتوح (بدون تاريخ نهاية)
                if not contract.end_date:
                    raise forms.ValidationError({
                        'start_date': f'⚠️ يوجد عقد ساري للموظف بدون تاريخ نهاية ({contract.contract_number}). '
                                     f'يجب إنهاء أو إيقاف العقد الحالي أولاً.'
                    })
                
                # حالة 2: العقد الجديد مفتوح (بدون تاريخ نهاية)
                if not end_date:
                    raise forms.ValidationError({
                        'end_date': f'⚠️ يوجد عقد ساري للموظف ({contract.contract_number}) '
                                   f'من {contract.start_date.strftime("%Y-%m-%d")} إلى {contract.end_date.strftime("%Y-%m-%d")}. '
                                   f'لا يمكن إنشاء عقد مفتوح. يجب إنهاء العقد الحالي أولاً.'
                    })
                
                # حالة 3: تداخل في الفترات الزمنية
                if start_date <= contract.end_date:
                    if not end_date or end_date >= contract.start_date:
                        error_message = (
                            f'يوجد تداخل مع عقد ساري ({contract.contract_number}) '
                            f'من {contract.start_date.strftime("%d/%m/%Y")} إلى {contract.end_date.strftime("%d/%m/%Y")}. '
                            f'الحلول المتاحة: '
                            f'(1) إنهاء أو إيقاف العقد الحالي أولاً، '
                            f'(2) استخدام خاصية التجديد من صفحة العقد، '
                            f'(3) تعديل تاريخ البداية ليكون بعد {contract.end_date.strftime("%d/%m/%Y")}'
                        )
                        raise forms.ValidationError({
                            'start_date': error_message
                        })
        
        # التحقق من بيانات الوظيفة (إلزامية للعقود الجديدة)
        if not self.instance.pk:  # عقد جديد
            if employee and not job_title:
                # محاولة نسخها من الموظف
                if employee.job_title:
                    cleaned_data['job_title'] = employee.job_title
                else:
                    raise forms.ValidationError({
                        'job_title': 'المسمى الوظيفي إلزامي. الموظف ليس لديه وظيفة محددة.'
                    })
            
            if employee and not department:
                # محاولة نسخها من الموظف
                if employee.department:
                    cleaned_data['department'] = employee.department
                else:
                    raise forms.ValidationError({
                        'department': 'القسم إلزامي. الموظف ليس لديه قسم محدد.'
                    })
        
        return cleaned_data
