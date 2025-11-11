"""
نماذج بنود الراتب للعقود
"""
from django import forms
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError
from hr.models import ContractSalaryComponent, Contract, SalaryComponentTemplate
from decimal import Decimal


class ContractSalaryComponentForm(forms.ModelForm):
    """نموذج إضافة/تعديل بند راتب في العقد"""
    
    # حقل اختياري لاختيار قالب
    template = forms.ModelChoiceField(
        queryset=SalaryComponentTemplate.objects.filter(is_active=True),
        required=False,
        label='اختر من القوالب (اختياري)',
        widget=forms.Select(attrs={
            'class': 'form-select template-select',
        }),
        empty_label='-- اختر قالب --'
    )
    
    class Meta:
        model = ContractSalaryComponent
        fields = [
            'template', 'code', 'name', 'component_type', 
            'calculation_method', 'amount', 'percentage', 'formula',
            'is_basic', 'is_taxable', 'is_fixed', 'affects_overtime', 
            'show_in_payslip', 'order', 'notes'
        ]
        
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: HOUSING',
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: بدل السكن',
            }),
            'component_type': forms.Select(attrs={
                'class': 'form-select',
            }),
            'calculation_method': forms.Select(attrs={
                'class': 'form-select calculation-method',
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control amount-field',
                'placeholder': '0',
                'step': '0.01',
            }),
            'percentage': forms.NumberInput(attrs={
                'class': 'form-control percentage-field',
                'placeholder': '0',
                'step': '0.01',
            }),
            'formula': forms.TextInput(attrs={
                'class': 'form-control formula-field',
                'placeholder': 'مثال: BASIC * 0.1',
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
            'order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'value': 100
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'ملاحظات (اختياري)'
            })
        }
        
        labels = {
            'code': 'الكود',
            'name': 'اسم البند',
            'component_type': 'النوع',
            'calculation_method': 'طريقة الحساب',
            'amount': 'المبلغ الثابت',
            'percentage': 'النسبة المئوية',
            'formula': 'الصيغة الحسابية',
            'is_basic': 'راتب أساسي',
            'is_taxable': 'خاضع للضريبة',
            'is_fixed': 'ثابت شهرياً',
            'affects_overtime': 'يؤثر على الإضافي',
            'show_in_payslip': 'يظهر في قسيمة الراتب',
            'order': 'الترتيب',
            'notes': 'ملاحظات'
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # جعل الحقول الافتراضية اختيارية
        self.fields['amount'].required = False
        self.fields['percentage'].required = False
        self.fields['formula'].required = False
        self.fields['notes'].required = False
    
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
        
        return cleaned_data


# Inline Formset لإضافة بنود متعددة في نموذج العقد
ContractSalaryComponentFormSet = inlineformset_factory(
    Contract,
    ContractSalaryComponent,
    form=ContractSalaryComponentForm,
    extra=1,  # عدد النماذج الفارغة الإضافية
    can_delete=True,  # السماح بالحذف
    min_num=0,  # الحد الأدنى للبنود (0 = اختياري)
    validate_min=False,
)
