from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal

from ..models import OrderMaterial, PriceUnit


class OrderMaterialForm(forms.ModelForm):
    """
    نموذج إضافة وتحرير مواد الطلب
    """
    
    class Meta:
        model = OrderMaterial
        fields = [
            'material_type', 'material_name', 'quantity', 
            'unit', 'unit_cost', 'waste_percentage'
        ]
        
        widgets = {
            'material_type': forms.Select(
                choices=[
                    ('paper', _('ورق')),
                    ('ink', _('حبر')),
                    ('plates', _('زنكات')),
                    ('chemicals', _('كيماويات')),
                    ('packaging', _('تعبئة وتغليف')),
                    ('adhesive', _('مواد لاصقة')),
                    ('other', _('أخرى'))
                ],
                attrs={'class': 'form-select'}
            ),
            'material_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('اسم المادة')
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.001',
                'min': '0.001'
            }),
            'unit': forms.Select(attrs={
                'class': 'form-select'
            }),
            'unit_cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'waste_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '50',
                'value': '5.00'
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # تعيين القيم الافتراضية
        if not self.instance.pk:
            self.fields['waste_percentage'].initial = Decimal('5.00')
            self.fields['unit'].initial = PriceUnit.PIECE

    def clean_quantity(self):
        """التحقق من الكمية"""
        quantity = self.cleaned_data.get('quantity')
        if quantity and quantity <= 0:
            raise ValidationError(_('الكمية يجب أن تكون أكبر من صفر'))
        return quantity

    def clean_unit_cost(self):
        """التحقق من تكلفة الوحدة"""
        unit_cost = self.cleaned_data.get('unit_cost')
        if unit_cost and unit_cost < 0:
            raise ValidationError(_('تكلفة الوحدة لا يمكن أن تكون سالبة'))
        return unit_cost

    def clean_waste_percentage(self):
        """التحقق من نسبة الهالك"""
        waste_percentage = self.cleaned_data.get('waste_percentage')
        if waste_percentage and (waste_percentage < 0 or waste_percentage > 50):
            raise ValidationError(_('نسبة الهالك يجب أن تكون بين 0 و 50%'))
        return waste_percentage


class MaterialBulkForm(forms.Form):
    """
    نموذج إضافة مواد متعددة دفعة واحدة
    """
    materials_data = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 10,
            'placeholder': _(
                'أدخل بيانات المواد بالتنسيق التالي:\n'
                'نوع المادة | اسم المادة | الكمية | الوحدة | تكلفة الوحدة | نسبة الهالك\n'
                'مثال:\n'
                'ورق | ورق أبيض 80 جرام | 100 | فرخ | 2.50 | 5\n'
                'حبر | حبر أسود | 2 | كيلو | 150.00 | 2'
            )
        }),
        help_text=_('كل سطر يمثل مادة واحدة، افصل البيانات بعلامة |')
    )

    def clean_materials_data(self):
        """التحقق من بيانات المواد المتعددة"""
        data = self.cleaned_data.get('materials_data')
        if not data:
            raise ValidationError(_('يجب إدخال بيانات المواد'))
        
        lines = data.strip().split('\n')
        materials = []
        
        for i, line in enumerate(lines, 1):
            if not line.strip():
                continue
                
            parts = [part.strip() for part in line.split('|')]
            if len(parts) != 6:
                raise ValidationError(
                    _('السطر {}: يجب أن يحتوي على 6 عناصر مفصولة بـ |').format(i)
                )
            
            try:
                material_type, material_name, quantity, unit, unit_cost, waste_percentage = parts
                
                # التحقق من الكمية
                quantity = Decimal(quantity)
                if quantity <= 0:
                    raise ValidationError(_('السطر {}: الكمية يجب أن تكون أكبر من صفر').format(i))
                
                # التحقق من تكلفة الوحدة
                unit_cost = Decimal(unit_cost)
                if unit_cost < 0:
                    raise ValidationError(_('السطر {}: تكلفة الوحدة لا يمكن أن تكون سالبة').format(i))
                
                # التحقق من نسبة الهالك
                waste_percentage = Decimal(waste_percentage)
                if waste_percentage < 0 or waste_percentage > 50:
                    raise ValidationError(_('السطر {}: نسبة الهالك يجب أن تكون بين 0 و 50%').format(i))
                
                materials.append({
                    'material_type': material_type,
                    'material_name': material_name,
                    'quantity': quantity,
                    'unit': unit,
                    'unit_cost': unit_cost,
                    'waste_percentage': waste_percentage
                })
                
            except (ValueError, TypeError) as e:
                raise ValidationError(_('السطر {}: خطأ في تنسيق البيانات - {}').format(i, str(e)))
        
        if not materials:
            raise ValidationError(_('لم يتم العثور على مواد صالحة'))
        
        return materials


class MaterialSearchForm(forms.Form):
    """
    نموذج البحث في المواد
    """
    search_query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('البحث في اسم المادة')
        })
    )
    
    material_type = forms.ChoiceField(
        required=False,
        choices=[('', _('جميع الأنواع'))] + [
            ('paper', _('ورق')),
            ('ink', _('حبر')),
            ('plates', _('زنكات')),
            ('chemicals', _('كيماويات')),
            ('packaging', _('تعبئة وتغليف')),
            ('adhesive', _('مواد لاصقة')),
            ('other', _('أخرى'))
        ],
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    unit = forms.ChoiceField(
        required=False,
        choices=[('', _('جميع الوحدات'))] + PriceUnit.choices,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    cost_min = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': _('أقل تكلفة'),
            'step': '0.01'
        })
    )
    
    cost_max = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': _('أعلى تكلفة'),
            'step': '0.01'
        })
    )

    def clean(self):
        """التحقق من نطاق التكلفة"""
        cleaned_data = super().clean()
        cost_min = cleaned_data.get('cost_min')
        cost_max = cleaned_data.get('cost_max')
        
        if cost_min and cost_max and cost_min > cost_max:
            raise ValidationError(_('أقل تكلفة يجب أن تكون أصغر من أعلى تكلفة'))
        
        return cleaned_data


class MaterialCalculatorForm(forms.Form):
    """
    نموذج حاسبة تكلفة المواد
    """
    material_type = forms.ChoiceField(
        choices=[
            ('paper', _('ورق')),
            ('ink', _('حبر')),
            ('plates', _('زنكات')),
            ('chemicals', _('كيماويات')),
            ('packaging', _('تعبئة وتغليف')),
            ('adhesive', _('مواد لاصقة')),
            ('other', _('أخرى'))
        ],
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    quantity = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.001',
            'min': '0.001'
        })
    )
    
    unit = forms.ChoiceField(
        choices=PriceUnit.choices,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    unit_cost = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0'
        })
    )
    
    waste_percentage = forms.DecimalField(
        initial=Decimal('5.00'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0',
            'max': '50',
            'value': '5.00'
        })
    )
    
    def calculate_total_cost(self):
        """حساب التكلفة الإجمالية"""
        if self.is_valid():
            quantity = self.cleaned_data['quantity']
            unit_cost = self.cleaned_data['unit_cost']
            waste_percentage = self.cleaned_data['waste_percentage']
            
            base_cost = quantity * unit_cost
            waste_amount = base_cost * (waste_percentage / 100)
            total_cost = base_cost + waste_amount
            
            return {
                'base_cost': base_cost,
                'waste_amount': waste_amount,
                'total_cost': total_cost,
                'waste_percentage': waste_percentage
            }
        return None


__all__ = [
    'OrderMaterialForm',
    'MaterialBulkForm', 
    'MaterialSearchForm',
    'MaterialCalculatorForm'
]
