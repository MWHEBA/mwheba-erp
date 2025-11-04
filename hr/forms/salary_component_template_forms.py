"""
نماذج قوالب مكونات الراتب
"""
from django import forms
from hr.models import SalaryComponentTemplate


class SalaryComponentTemplateForm(forms.ModelForm):
    """نموذج قالب مكون الراتب"""
    
    class Meta:
        model = SalaryComponentTemplate
        fields = ['name', 'component_type', 'formula', 'default_amount', 'description', 'order', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اسم البند'
            }),
            'component_type': forms.Select(attrs={
                'class': 'form-select'
            }),
            'formula': forms.TextInput(attrs={
                'class': 'form-control component-formula',
                'placeholder': 'مثال: basic * 0.25'
            }),
            'default_amount': forms.TextInput(attrs={
                'class': 'form-control smart-float',
                'placeholder': '0'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف البند (اختياري)'
            }),
            'order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
        labels = {
            'name': 'اسم البند',
            'component_type': 'النوع',
            'formula': 'الصيغة الحسابية',
            'default_amount': 'المبلغ الافتراضي',
            'description': 'الوصف',
            'order': 'الترتيب',
            'is_active': 'نشط'
        }
    
    def clean(self):
        """التحقق من أن المستخدم أدخل صيغة أو مبلغ، ليس الاثنين معاً"""
        cleaned_data = super().clean()
        formula = cleaned_data.get('formula')
        default_amount = cleaned_data.get('default_amount')
        
        # إذا كان الاثنين فارغين
        if not formula and not default_amount:
            raise forms.ValidationError('يجب إدخال صيغة حسابية أو مبلغ افتراضي')
        
        # إذا كان الاثنين ممتلئين
        if formula and default_amount:
            raise forms.ValidationError('لا يمكن إدخال صيغة حسابية ومبلغ افتراضي معاً. اختر واحداً فقط')
        
        return cleaned_data
