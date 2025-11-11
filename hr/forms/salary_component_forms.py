"""
نماذج بنود الراتب للموظفين
"""
from django import forms
from django.core.exceptions import ValidationError
from hr.models import SalaryComponent, SalaryComponentTemplate, Employee, Contract
from decimal import Decimal


class SalaryComponentForm(forms.ModelForm):
    """نموذج إضافة/تعديل بند راتب"""
    
    # حقل اختياري لاختيار قالب
    template = forms.ModelChoiceField(
        queryset=SalaryComponentTemplate.objects.filter(is_active=True),
        required=False,
        label='اختر من القوالب (اختياري)',
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'id_template_select'
        }),
        empty_label='-- اختر قالب أو أدخل بيانات مخصصة --'
    )
    
    class Meta:
        model = SalaryComponent
        fields = [
            'template', 'name', 'component_type', 
            'calculation_method', 'amount', 'percentage', 'formula',
            'show_in_payslip', 'is_active', 'effective_from', 'effective_to',
            'order', 'notes'
        ]
        
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: بدل السكن',
                'required': True
            }),
            'component_type': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'calculation_method': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_calculation_method',
                'required': True
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
                'id': 'id_amount'
            }),
            'percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
                'id': 'id_percentage'
            }),
            'formula': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: BASIC * 0.1',
                'id': 'id_formula'
            }),
            'is_basic': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_taxable': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_fixed': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'affects_overtime': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'show_in_payslip': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'effective_from': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'effective_to': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'value': 100
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'ملاحظات إضافية (اختياري)'
            })
        }
        
        labels = {
            'name': 'اسم البند',
            'component_type': 'النوع',
            'calculation_method': 'طريقة الحساب',
            'amount': 'المبلغ الثابت',
            'percentage': 'النسبة المئوية',
            'formula': 'الصيغة الحسابية',
            'show_in_payslip': 'يظهر في قسيمة الراتب',
            'is_active': 'نشط',
            'effective_from': 'ساري من',
            'effective_to': 'ساري حتى',
            'order': 'الترتيب',
            'notes': 'ملاحظات'
        }
    
    def __init__(self, *args, **kwargs):
        self.employee = kwargs.pop('employee', None)
        self.contract = kwargs.pop('contract', None)
        super().__init__(*args, **kwargs)
        
        # إذا كان تعديل، إخفاء حقل القالب
        if self.instance.pk:
            self.fields.pop('template', None)
            
            # إذا كان البند منسوخ من العقد، جعل الحقول للقراءة فقط
            if self.instance.is_from_contract:
                for field_name in ['name', 'component_type', 'calculation_method', 
                                   'amount', 'percentage', 'formula']:
                    if field_name in self.fields:
                        self.fields[field_name].disabled = True
                        self.fields[field_name].help_text = 'هذا البند منسوخ من العقد ولا يمكن تعديله'
        
        # جعل الحقول الافتراضية اختيارية
        self.fields['amount'].required = False
        self.fields['percentage'].required = False
        self.fields['formula'].required = False
        self.fields['effective_to'].required = False
        self.fields['notes'].required = False
    
    def _generate_code(self, name):
        """توليد كود تلقائي من الاسم"""
        import re
        # تحويل الاسم لكود (حروف إنجليزية فقط)
        code = re.sub(r'[^a-zA-Z0-9]', '_', name.upper())
        
        # التأكد من عدم التكرار
        if self.employee:
            base_code = code
            counter = 1
            while SalaryComponent.objects.filter(
                employee=self.employee,
                code=code
            ).exclude(pk=self.instance.pk if self.instance.pk else None).exists():
                code = f"{base_code}_{counter}"
                counter += 1
        
        return code
    
    def clean(self):
        """التحقق من صحة البيانات"""
        cleaned_data = super().clean()
        calculation_method = cleaned_data.get('calculation_method')
        amount = cleaned_data.get('amount')
        percentage = cleaned_data.get('percentage')
        formula = cleaned_data.get('formula')
        
        # التحقق حسب طريقة الحساب
        if calculation_method == 'fixed':
            if not amount:
                raise ValidationError({
                    'amount': 'المبلغ الثابت مطلوب عند اختيار طريقة الحساب "ثابت"'
                })
        
        elif calculation_method == 'percentage':
            if not percentage:
                raise ValidationError({
                    'percentage': 'النسبة المئوية مطلوبة عند اختيار طريقة الحساب "نسبة"'
                })
            
            if percentage < 0 or percentage > 100:
                raise ValidationError({
                    'percentage': 'النسبة يجب أن تكون بين 0 و 100'
                })
        
        elif calculation_method == 'formula':
            if not formula:
                raise ValidationError({
                    'formula': 'الصيغة الحسابية مطلوبة عند اختيار طريقة الحساب "صيغة"'
                })
        
        # التحقق من التواريخ
        effective_from = cleaned_data.get('effective_from')
        effective_to = cleaned_data.get('effective_to')
        
        if effective_from and effective_to:
            if effective_to < effective_from:
                raise ValidationError({
                    'effective_to': 'تاريخ الانتهاء يجب أن يكون بعد تاريخ البداية'
                })
        
        return cleaned_data
    
    def save(self, commit=True):
        """حفظ البند"""
        instance = super().save(commit=False)
        
        # ربط بالموظف والعقد
        if self.employee:
            instance.employee = self.employee
        
        if self.contract:
            instance.contract = self.contract
        
        # توليد الكود تلقائياً من الاسم
        if not instance.code:
            instance.code = self._generate_code(instance.name)
        
        # إذا تم اختيار قالب، نسخ البيانات منه
        template = self.cleaned_data.get('template')
        if template and not self.instance.pk:
            if not instance.name:
                instance.name = template.name
            if template.formula and not instance.formula:
                instance.formula = template.formula
            if template.default_amount and not instance.amount:
                instance.amount = template.default_amount
        
        if commit:
            instance.save()
        
        return instance


class SalaryComponentQuickForm(forms.ModelForm):
    """نموذج سريع لإضافة بند من قالب"""
    
    template = forms.ModelChoiceField(
        queryset=SalaryComponentTemplate.objects.filter(is_active=True),
        required=True,
        label='القالب',
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    class Meta:
        model = SalaryComponent
        fields = ['template', 'amount', 'effective_from']
        
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'المبلغ (اختياري - سيستخدم المبلغ الافتراضي من القالب)'
            }),
            'effective_from': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            })
        }
        
        labels = {
            'amount': 'المبلغ المخصص',
            'effective_from': 'ساري من'
        }
    
    def __init__(self, *args, **kwargs):
        self.employee = kwargs.pop('employee', None)
        self.contract = kwargs.pop('contract', None)
        super().__init__(*args, **kwargs)
        
        self.fields['amount'].required = False
    
    def save(self, commit=True):
        """إنشاء البند من القالب"""
        from hr.services import SalaryComponentService
        
        template = self.cleaned_data['template']
        amount = self.cleaned_data.get('amount')
        effective_from = self.cleaned_data.get('effective_from')
        
        # استخدام Service لإنشاء البند
        component = SalaryComponentService.create_from_template(
            employee=self.employee,
            template=template,
            effective_from=effective_from,
            custom_amount=amount
        )
        
        return component
