"""
نماذج بنود الراتب للموظفين
"""
from django import forms
from django.core.exceptions import ValidationError
from hr.models import SalaryComponent, SalaryComponentTemplate
from datetime import date
from calendar import monthrange
import re
import uuid


# ==================== النظام الموحد الجديد ====================

def generate_unique_code(name, employee, exclude_pk=None):
    """توليد كود فريد للبند"""
    if not name:
        return f"COMP_{date.today().strftime('%Y%m%d_%H%M%S')}"
    
    # تنظيف الاسم وتحويله لكود
    base_code = re.sub(r'[^a-zA-Z0-9]', '_', name.upper())[:45]
    counter = 1
    code = base_code
    
    while SalaryComponent.objects.filter(
        employee=employee, 
        code=code
    ).exclude(pk=exclude_pk).exists():
        code = f"{base_code}_{counter}"
        counter += 1
        if counter > 999:
            code = f"{base_code}_{str(uuid.uuid4())[:8]}"
            break
    
    return code


class UnifiedSalaryComponentForm(forms.ModelForm):
    """نموذج موحد لإضافة وتعديل بنود الراتب"""
    
    
    # حقل نوع الإضافة السريعة
    quick_type = forms.ChoiceField(
        choices=[
            ('template', 'من قالب'),
            ('custom', 'مخصص سريع')
        ],
        initial='template',
        widget=forms.HiddenInput(),
        required=False
    )
    
    # حقل نوع المدة
    DURATION_TYPE_CHOICES = [
        ('permanent', 'دائم'),
        ('one_time', 'مرة واحدة'),
        ('fixed_period', 'محدد بمدة')
    ]
    
    duration_type = forms.ChoiceField(
        choices=DURATION_TYPE_CHOICES,
        initial='permanent',
        label='نوع المدة',
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'id_duration_type'
        }),
        required=False
    )
    
    # حقل اختيار القالب (للوضع السريع)
    template = forms.ModelChoiceField(
        queryset=SalaryComponentTemplate.objects.filter(is_active=True),
        required=False,
        label='اختر القالب',
        widget=forms.Select(attrs={
            'class': 'form-select template-selector',
            'id': 'id_template_select'
        }),
        empty_label='-- اختر قالب جاهز --'
    )
    
    # حقل المبلغ المخصص (للقوالب)
    custom_amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        label='المبلغ المخصص',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'اتركه فارغاً لاستخدام المبلغ الافتراضي',
            'id': 'id_custom_amount'
        }),
        help_text='اختياري - سيتم استخدام المبلغ الافتراضي من القالب إذا تُرك فارغاً'
    )
    

    class Meta:
        model = SalaryComponent
        fields = [
            'quick_type', 'duration_type', 'template', 'custom_amount',
            'name', 'code', 'component_type', 'calculation_method', 
            'amount', 'formula', 'effective_from', 'effective_to', 'order'
        ]
        
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: بدل السكن',
                'id': 'id_name'
            }),
            'code': forms.HiddenInput(attrs={
                'id': 'id_code'
            }),
            'component_type': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_component_type'
            }),
            'calculation_method': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_calculation_method'
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
                'id': 'id_amount'
            }),
            'formula': forms.TextInput(attrs={
                'class': 'form-control component-formula',
                'placeholder': 'مثال: basic * 0.25',
                'id': 'id_formula'
            }),
            'effective_from': forms.DateInput(attrs={
                'class': 'form-control datepicker',
                'id': 'id_effective_from'
            }),
            'effective_to': forms.DateInput(attrs={
                'class': 'form-control datepicker',
                'id': 'id_effective_to'
            }),
            'order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'value': 100,
                'id': 'id_order'
            })
        }
        
        labels = {
            'name': 'اسم البند',
            'code': 'كود البند',
            'component_type': 'نوع البند',
            'calculation_method': 'طريقة الحساب',
            'amount': 'المبلغ',
            'formula': 'الصيغة المحاسبية',
            'effective_from': 'ساري من',
            'order': 'الترتيب'
        }

    def __init__(self, *args, **kwargs):
        self.employee = kwargs.pop('employee', None)
        self.contract = kwargs.pop('contract', None)
        self.is_edit = kwargs.pop('is_edit', False)
        
        super().__init__(*args, **kwargs)
        
        # تعيين القيم الافتراضية
        if not self.is_edit:
            self.fields['effective_from'].initial = date.today()
        
        # تحديد الحقول المطلوبة حسب الوضع
        self._update_required_fields()
        
        # إضافة CSS classes للتصميم
        self._add_css_classes()
    
    def _update_required_fields(self):
        """تحديث الحقول المطلوبة حسب الوضع"""
        # تحديد الوضع الحالي
        quick_type = self.data.get('quick_type', 'template')
        
        if quick_type == 'template':
            # وضع القالب - القالب مطلوب فقط
            self.fields['template'].required = True
            self.fields['name'].required = False
            self.fields['component_type'].required = False
            self.fields['calculation_method'].required = False
            self.fields['code'].required = False
        else:  # custom
            # الوضع المخصص - الحقول الأساسية مطلوبة
            self.fields['template'].required = False
            self.fields['name'].required = True
            self.fields['component_type'].required = True
            self.fields['calculation_method'].required = True
            self.fields['code'].required = False  # الكود اختياري دائماً
    
    def _add_css_classes(self):
        """إضافة CSS classes للتصميم"""
        for field_name, field in self.fields.items():
            if hasattr(field.widget, 'attrs'):
                # إضافة class أساسي لجميع الحقول
                current_class = field.widget.attrs.get('class', '')
                if 'form-control' not in current_class and 'form-select' not in current_class and 'form-check-input' not in current_class:
                    field.widget.attrs['class'] = f"{current_class} form-control".strip()
                
                # إضافة tabindex="-1" لجميع الحقول لمنع مشكلة aria-hidden
                field.widget.attrs['tabindex'] = '-1'
    
    def clean(self):
        """التحقق الشامل من صحة البيانات"""
        cleaned_data = super().clean()
        
        # كشف الصيغ الحسابية أولاً
        self._detect_and_handle_formulas(cleaned_data)
        
        form_mode = cleaned_data.get('form_mode', 'quick')
        quick_type = cleaned_data.get('quick_type', 'template')
        
        if form_mode == 'quick':
            if quick_type == 'template':
                self._validate_template_mode(cleaned_data)
            else:
                self._validate_quick_custom_mode(cleaned_data)
        else:
            self._validate_advanced_mode(cleaned_data)
        
        # التحقق من صحة التواريخ
        self._validate_dates(cleaned_data)
        
        return cleaned_data
    
    def _detect_and_handle_formulas(self, cleaned_data):
        """كشف ومعالجة الصيغ الحسابية"""
        # التحقق من البيانات الخام أولاً (قبل التحويل)
        raw_amount = self.data.get('amount', '').strip()
        formula_field = cleaned_data.get('formula', '').strip()
        
        # إذا كان المستخدم كتب صيغة في حقل المبلغ
        if raw_amount and self._is_formula(raw_amount):
            # نقل الصيغة من حقل المبلغ إلى حقل الصيغة
            cleaned_data['formula'] = raw_amount
            cleaned_data['amount'] = 0  # مبلغ افتراضي
            cleaned_data['calculation_method'] = 'formula'
        
        # إذا كان هناك صيغة في الحقل المخصص لها
        elif formula_field and self._is_formula(formula_field):
            cleaned_data['calculation_method'] = 'formula'
    
    def _validate_dates(self, cleaned_data):
        """التحقق من صحة التواريخ"""
        effective_from = cleaned_data.get('effective_from')
        effective_to = cleaned_data.get('effective_to')
        duration_type = cleaned_data.get('duration_type', 'permanent')
        
        # التحقق من أن "ساري حتى" أكبر من "ساري من" للمدة المحددة
        if duration_type == 'fixed_period' and effective_from and effective_to:
            if effective_to <= effective_from:
                raise ValidationError({
                    'effective_to': 'يجب أن يكون تاريخ الانتهاء بعد تاريخ البداية بيوم واحد على الأقل'
                })
    
    def _validate_template_mode(self, cleaned_data):
        """التحقق من الوضع السريع - من قالب"""
        template = cleaned_data.get('template')
        if not template:
            raise ValidationError('يجب اختيار قالب في الوضع السريع')
        
        # التحقق من عدم وجود بند بنفس القالب للموظف
        if self.employee and not self.is_edit:
            existing = SalaryComponent.objects.filter(
                employee=self.employee,
                template=template
            ).exists()
            
            if existing:
                raise ValidationError(f'يوجد بالفعل بند من قالب "{template.name}" لهذا الموظف')
    
    def _validate_quick_custom_mode(self, cleaned_data):
        """التحقق من الوضع السريع - مخصص"""
        name = cleaned_data.get('name')
        component_type = cleaned_data.get('component_type')
        calculation_method = cleaned_data.get('calculation_method')
        
        if not name:
            raise ValidationError('اسم البند مطلوب في الوضع المخصص')
        if not component_type:
            raise ValidationError('نوع البند مطلوب في الوضع المخصص')
        if not calculation_method:
            raise ValidationError('طريقة الحساب مطلوبة في الوضع المخصص')
        
        self._validate_calculation_fields(cleaned_data)
    
    def _validate_advanced_mode(self, cleaned_data):
        """التحقق من الوضع المتقدم"""
        name = cleaned_data.get('name')
        component_type = cleaned_data.get('component_type')
        calculation_method = cleaned_data.get('calculation_method')
        
        if not name:
            raise ValidationError('اسم البند مطلوب')
        if not component_type:
            raise ValidationError('نوع البند مطلوب')
        if not calculation_method:
            raise ValidationError('طريقة الحساب مطلوبة')
        
        self._validate_calculation_fields(cleaned_data)
    
    def _validate_calculation_fields(self, cleaned_data):
        """التحقق من حقول الحساب"""
        calculation_method = cleaned_data.get('calculation_method')
        amount = cleaned_data.get('amount')
        formula = cleaned_data.get('formula', '').strip()
        
        # كشف الصيغ الحسابية تلقائياً
        if formula and self._is_formula(formula):
            # إذا كان هناك صيغة، غير طريقة الحساب تلقائياً
            cleaned_data['calculation_method'] = 'formula'
            calculation_method = 'formula'
        
        if calculation_method == 'fixed':
            if not amount or amount <= 0:
                raise ValidationError('المبلغ مطلوب ويجب أن يكون أكبر من صفر للمبلغ الثابت')
        elif calculation_method == 'formula':
            if not formula:
                raise ValidationError('الصيغة الحسابية مطلوبة عند اختيار طريقة الحساب بالصيغة')
            
            # التحقق من وجود عقد نشط للصيغ الحسابية
            if self.employee and not self.contract:
                raise ValidationError('لا يمكن استخدام الصيغ الحسابية بدون عقد نشط للموظف')
            
            # التحقق من صحة الصيغة
            if not self._validate_formula(formula):
                raise ValidationError('الصيغة الحسابية غير صحيحة. استخدم متغيرات مثل: basic, gross, days')
    
    def _is_formula(self, text):
        """كشف ما إذا كان النص صيغة حسابية"""
        if not text:
            return False
        
        # البحث عن متغيرات أو عمليات حسابية
        formula_indicators = ['basic', 'gross', 'days', '*', '/', '+', '-', '(', ')']
        text_lower = text.lower()
        
        return any(indicator in text_lower for indicator in formula_indicators)
    
    def _validate_formula(self, formula):
        """التحقق من صحة الصيغة الحسابية"""
        if not formula:
            return False
        
        try:
            # تنظيف الصيغة
            formula_clean = formula.upper().strip()
            
            # التحقق من وجود متغيرات صحيحة
            valid_vars = ['BASIC', 'GROSS', 'DAYS']
            has_valid_var = any(var in formula_clean for var in valid_vars)
            
            if not has_valid_var:
                return False
            
            # التحقق من الأحرف المسموحة
            allowed_chars = set('0123456789.+-*/() BASICGROSDAYS')
            if not all(c in allowed_chars for c in formula_clean):
                return False
            
            # محاولة تقييم الصيغة مع قيم تجريبية
            test_formula = formula_clean
            test_replacements = {
                'BASIC': '5000',
                'GROSS': '6000', 
                'DAYS': '30'
            }
            
            for var, value in test_replacements.items():
                test_formula = test_formula.replace(var, value)
            
            # تقييم آمن
            result = eval(test_formula, {"__builtins__": {}}, {})
            return isinstance(result, (int, float)) and result >= 0
            
        except:
            return False
    
    
    def save(self, commit=True):
        """حفظ البند حسب النوع المختار"""
        quick_type = self.cleaned_data.get('quick_type', 'template')
        
        if quick_type == 'template':
            return self._save_from_template(commit)
        else:
            return self._save_custom(commit)
    
    def _save_from_template(self, commit=True):
        """حفظ البند من قالب"""
        template = self.cleaned_data['template']
        custom_amount = self.cleaned_data.get('custom_amount')
        effective_from = self.cleaned_data.get('effective_from', date.today())
        
        # إنشاء البند من القالب باستخدام SalaryComponentService
        from hr.services import SalaryComponentService
        component = SalaryComponentService.create_from_template(
            employee=self.employee,
            template=template,
            effective_from=effective_from,
            contract=self.contract,
            custom_amount=custom_amount
        )
        
        # تطبيق الملاحظات إذا تم إدخالها
        notes = self.cleaned_data.get('notes')
        if notes:
            component.notes = notes
            if commit:
                component.save()
        
        return component
    
    def _save_custom(self, commit=True):
        """حفظ البند المخصص"""
        component = super().save(commit=False)
        
        # ربط بالموظف والعقد
        component.employee = self.employee
        component.contract = self.contract
        
        # توليد كود فريد إذا لم يكن موجود
        if not component.code:
            component.code = generate_unique_code(
                component.name, 
                self.employee, 
                exclude_pk=component.pk
            )
        
        # تحديد المصدر
        component.source = 'adjustment'  # تعديل افتراضي
        component.is_from_contract = False
        
        # معالجة نوع المدة
        duration_type = self.cleaned_data.get('duration_type', 'permanent')
        if duration_type == 'one_time':
            # لمرة واحدة - تحديد نهاية الشهر
            start_date = component.effective_from or date.today()
            last_day = monthrange(start_date.year, start_date.month)[1]
            component.effective_to = date(start_date.year, start_date.month, last_day)
        elif duration_type == 'permanent':
            # دائم - بدون تاريخ نهاية
            component.effective_to = None
        elif duration_type == 'fixed_period':
            # محدد بمدة - استخدام التاريخ المحدد من المستخدم
            effective_to = self.cleaned_data.get('effective_to')
            if effective_to:
                component.effective_to = effective_to
            else:
                # إذا لم يحدد تاريخ نهاية، اجعله لمدة شهر
                start_date = component.effective_from or date.today()
                from calendar import monthrange
                last_day = monthrange(start_date.year, start_date.month)[1]
                component.effective_to = date(start_date.year, start_date.month, last_day)
        
        if commit:
            component.save()
        
        return component
    
    def get_preview_data(self):
        """إنشاء بيانات المعاينة للبند"""
        quick_type = self.data.get('quick_type', 'template')
        
        
        preview = {
            'name': '',
            'component_type': '',
            'amount': 0,
            'calculation_method': '',
            'formula': '',
            'effective_from': '',
            'notes': ''
        }
        
        if quick_type == 'template':
            template_id = self.data.get('template')
            if template_id:
                try:
                    template = SalaryComponentTemplate.objects.get(id=template_id)
                    preview['name'] = template.name
                    preview['component_type'] = template.get_component_type_display()
                    
                    # التحقق من المبلغ المخصص أولاً
                    custom_amount = self.data.get('custom_amount')
                    
                    if custom_amount and str(custom_amount).strip():
                        try:
                            custom_amount_float = float(custom_amount)
                            if custom_amount_float > 0:
                                preview['amount'] = custom_amount_float
                                preview['calculation_method'] = 'مبلغ ثابت (مخصص)'
                            else:
                                raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
                        except (ValueError, TypeError):
                            custom_amount = None
                    
                    if not custom_amount or not str(custom_amount).strip():
                        # استخدام القالب
                        if template.formula and self.contract and self.contract.basic_salary:
                            # حساب المبلغ من الصيغة
                            try:
                                calculated_amount = template.get_calculated_amount(self.contract.basic_salary)
                                preview['amount'] = float(calculated_amount)
                                preview['calculation_method'] = 'صيغة حسابية'
                                preview['formula'] = template.formula
                            except Exception:
                                preview['amount'] = float(template.default_amount)
                                preview['calculation_method'] = 'مبلغ ثابت (افتراضي)'
                        else:
                            # استخدام المبلغ الافتراضي
                            preview['amount'] = float(template.default_amount)
                            if template.formula:
                                preview['calculation_method'] = 'صيغة حسابية (بدون راتب أساسي)'
                                preview['formula'] = template.formula
                            else:
                                preview['calculation_method'] = 'مبلغ ثابت'
                    
                    # إضافة معلومات إضافية
                    if template.description:
                        preview['notes'] = template.description
                        
                except SalaryComponentTemplate.DoesNotExist:
                    pass
        else:
            # الوضع المخصص
            preview['name'] = self.data.get('name', '')
            component_type = self.data.get('component_type', '')
            if component_type:
                preview['component_type'] = dict(SalaryComponent.COMPONENT_TYPE_CHOICES).get(component_type, '')
            
            calculation_method = self.data.get('calculation_method', '')
            if calculation_method:
                preview['calculation_method'] = dict(SalaryComponent.CALCULATION_METHOD_CHOICES).get(calculation_method, '')
                
                if calculation_method == 'fixed':
                    amount = self.data.get('amount')
                    if amount:
                        preview['amount'] = float(amount)
        
        preview['effective_from'] = self.data.get('effective_from', '')
        
        return preview
