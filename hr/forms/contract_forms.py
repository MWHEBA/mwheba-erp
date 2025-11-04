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
        fields = ['contract_number', 'employee', 'start_date', 'end_date', 
                  'probation_period_months', 'basic_salary',
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
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
                'id': 'id_start_date'
            }),
            'end_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
                'id': 'id_end_date'
            }),
            'probation_period_months': forms.NumberInput(attrs={'class': 'form-control', 'value': '3'}),
            'basic_salary': forms.TextInput(attrs={'class': 'form-control smart-float', 'id': 'id_basic_salary'}),
            'auto_renew': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_auto_renew'}),
            'terms_and_conditions': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'contract_number': 'رقم العقد',
            'employee': 'الموظف',
            'start_date': 'تاريخ البداية',
            'end_date': 'تاريخ النهاية',
            'probation_period_months': 'فترة التجربة (بالأشهر)',
            'basic_salary': 'الراتب الأساسي',
            'auto_renew': 'تجديد تلقائي',
            'terms_and_conditions': 'البنود والشروط',
            'status': 'الحالة',
            'notes': 'ملاحظات',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # إذا كان نموذج جديد، عرض الرقم المقترح وإخفاء حقل الحالة
        if not self.instance.pk:
            next_number = self.generate_contract_number()
            self.fields['contract_number'].initial = next_number
            self.fields['contract_number'].widget.attrs['placeholder'] = f'الرقم المقترح: {next_number}'
            
            # إخفاء حقل الحالة في الإنشاء (سيتم تعيينها تلقائياً كـ "مسودة")
            self.fields['status'].widget = forms.HiddenInput()
            self.fields['status'].initial = 'draft'
    
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
    
    def clean_contract_number(self):
        """التحقق من رقم العقد وتوليده تلقائياً إذا لزم الأمر"""
        contract_number = self.cleaned_data.get('contract_number')
        
        # إذا كان عقد جديد ولم يتم إدخال رقم، قم بتوليده
        if not contract_number:
            return self.generate_contract_number()
        
        return contract_number
