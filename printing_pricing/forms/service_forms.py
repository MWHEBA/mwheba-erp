from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal

from ..models import OrderService, PriceUnit


class OrderServiceForm(forms.ModelForm):
    """
    نموذج إضافة وتحرير خدمات الطلب
    """
    
    class Meta:
        model = OrderService
        fields = [
            'service_category', 'service_name', 'service_description',
            'quantity', 'unit', 'unit_price', 'setup_cost',
            'is_optional', 'execution_time'
        ]
        
        widgets = {
            'service_category': forms.Select(attrs={
                'class': 'form-select'
            }),
            'service_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('اسم الخدمة')
            }),
            'service_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('وصف تفصيلي للخدمة')
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.001',
                'min': '0.001'
            }),
            'unit': forms.Select(attrs={
                'class': 'form-select'
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'setup_cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'value': '0.00'
            }),
            'is_optional': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'execution_time': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'step': '1',
                'placeholder': _('بالساعات')
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # تعيين القيم الافتراضية
        if not self.instance.pk:
            self.fields['setup_cost'].initial = Decimal('0.00')
            self.fields['unit'].initial = PriceUnit.PIECE

    def clean_quantity(self):
        """التحقق من الكمية"""
        quantity = self.cleaned_data.get('quantity')
        if quantity and quantity <= 0:
            raise ValidationError(_('الكمية يجب أن تكون أكبر من صفر'))
        return quantity

    def clean_unit_price(self):
        """التحقق من سعر الوحدة"""
        unit_price = self.cleaned_data.get('unit_price')
        if unit_price and unit_price < 0:
            raise ValidationError(_('سعر الوحدة لا يمكن أن يكون سالباً'))
        return unit_price

    def clean_setup_cost(self):
        """التحقق من تكلفة الإعداد"""
        setup_cost = self.cleaned_data.get('setup_cost')
        if setup_cost and setup_cost < 0:
            raise ValidationError(_('تكلفة الإعداد لا يمكن أن تكون سالبة'))
        return setup_cost

    def clean_execution_time(self):
        """التحقق من وقت التنفيذ"""
        execution_time = self.cleaned_data.get('execution_time')
        if execution_time and execution_time <= 0:
            raise ValidationError(_('وقت التنفيذ يجب أن يكون أكبر من صفر'))
        return execution_time


class PrintingServiceForm(forms.Form):
    """
    نموذج خدمات الطباعة المتخصص
    """
    printing_type = forms.ChoiceField(
        choices=[
            ('offset', _('أوفست')),
            ('digital', _('رقمية')),
            ('screen', _('سلك سكرين')),
            ('flexo', _('فلكسو')),
            ('letterpress', _('ليتر برس')),
            ('inkjet', _('نفث حبر')),
            ('laser', _('ليزر'))
        ],
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    colors_front = forms.IntegerField(
        min_value=0,
        max_value=10,
        initial=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'max': '10'
        })
    )
    
    colors_back = forms.IntegerField(
        min_value=0,
        max_value=10,
        initial=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'max': '10'
        })
    )
    
    has_spot_colors = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    spot_colors_count = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=5,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'max': '5'
        })
    )
    
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '1'
        })
    )
    
    plates_cost_per_color = forms.DecimalField(
        initial=Decimal('50.00'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'value': '50.00'
        })
    )
    
    printing_cost_per_thousand = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01'
        })
    )

    def clean(self):
        """التحقق الشامل من النموذج"""
        cleaned_data = super().clean()
        
        has_spot_colors = cleaned_data.get('has_spot_colors')
        spot_colors_count = cleaned_data.get('spot_colors_count')
        
        if has_spot_colors and not spot_colors_count:
            raise ValidationError(_('يجب تحديد عدد الألوان الخاصة'))
        
        if not has_spot_colors:
            cleaned_data['spot_colors_count'] = 0
        
        return cleaned_data

    def calculate_printing_cost(self):
        """حساب تكلفة الطباعة"""
        if self.is_valid():
            data = self.cleaned_data
            
            # حساب تكلفة الزنكات
            total_colors = data['colors_front'] + data['colors_back'] + (data['spot_colors_count'] or 0)
            plates_cost = total_colors * data['plates_cost_per_color']
            
            # حساب تكلفة الطباعة
            thousands = (data['quantity'] / 1000)
            printing_cost = thousands * data['printing_cost_per_thousand']
            
            total_cost = plates_cost + printing_cost
            
            return {
                'plates_cost': plates_cost,
                'printing_cost': printing_cost,
                'total_cost': total_cost,
                'total_colors': total_colors,
                'thousands': thousands
            }
        return None


class FinishingServiceForm(forms.Form):
    """
    نموذج خدمات الطباعة
    """
    FINISHING_CHOICES = [
        ('finishing', _('خدمات الطباعة')),  # قص، ريجة، تكسير
        ('packaging', _('خدمات التقفيل')),  # دبوس، بشر، سلك، تجليد
        ('coating', _('تغطية')),
    ]
    
    finishing_type = forms.ChoiceField(
        choices=FINISHING_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '1'
        })
    )
    
    unit = forms.ChoiceField(
        choices=PriceUnit.choices,
        initial=PriceUnit.PIECE,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    unit_price = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0'
        })
    )
    
    setup_cost = forms.DecimalField(
        initial=Decimal('0.00'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0',
            'value': '0.00'
        })
    )
    
    complexity_factor = forms.DecimalField(
        initial=Decimal('1.00'),
        min_value=Decimal('0.5'),
        max_value=Decimal('3.0'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.1',
            'min': '0.5',
            'max': '3.0',
            'value': '1.00'
        }),
        help_text=_('معامل التعقيد (0.5 = بسيط، 1.0 = عادي، 3.0 = معقد جداً)')
    )

    def calculate_finishing_cost(self):
        """حساب تكلفة خدمات الطباعة"""
        if self.is_valid():
            data = self.cleaned_data
            
            base_cost = data['quantity'] * data['unit_price']
            complexity_cost = base_cost * data['complexity_factor']
            total_cost = complexity_cost + data['setup_cost']
            
            return {
                'base_cost': base_cost,
                'complexity_cost': complexity_cost,
                'setup_cost': data['setup_cost'],
                'total_cost': total_cost,
                'complexity_factor': data['complexity_factor']
            }
        return None


class ServiceBulkForm(forms.Form):
    """
    نموذج إضافة خدمات متعددة دفعة واحدة
    """
    services_data = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 10,
            'placeholder': _(
                'أدخل بيانات الخدمات بالتنسيق التالي:\n'
                'فئة الخدمة | اسم الخدمة | الكمية | الوحدة | سعر الوحدة | تكلفة الإعداد | اختيارية\n'
                'مثال:\n'
                'طباعة | طباعة رقمية ملونة | 1000 | قطعة | 0.50 | 25.00 | لا\n'
                'تشطيبات | تقطيع | 1000 | قطعة | 0.05 | 10.00 | نعم'
            )
        }),
        help_text=_('كل سطر يمثل خدمة واحدة، افصل البيانات بعلامة |')
    )

    def clean_services_data(self):
        """التحقق من بيانات الخدمات المتعددة"""
        data = self.cleaned_data.get('services_data')
        if not data:
            raise ValidationError(_('يجب إدخال بيانات الخدمات'))
        
        lines = data.strip().split('\n')
        services = []
        
        for i, line in enumerate(lines, 1):
            if not line.strip():
                continue
                
            parts = [part.strip() for part in line.split('|')]
            if len(parts) != 7:
                raise ValidationError(
                    _('السطر {}: يجب أن يحتوي على 7 عناصر مفصولة بـ |').format(i)
                )
            
            try:
                category, name, quantity, unit, unit_price, setup_cost, is_optional = parts
                
                # التحقق من الكمية
                quantity = Decimal(quantity)
                if quantity <= 0:
                    raise ValidationError(_('السطر {}: الكمية يجب أن تكون أكبر من صفر').format(i))
                
                # التحقق من سعر الوحدة
                unit_price = Decimal(unit_price)
                if unit_price < 0:
                    raise ValidationError(_('السطر {}: سعر الوحدة لا يمكن أن يكون سالباً').format(i))
                
                # التحقق من تكلفة الإعداد
                setup_cost = Decimal(setup_cost)
                if setup_cost < 0:
                    raise ValidationError(_('السطر {}: تكلفة الإعداد لا يمكن أن تكون سالبة').format(i))
                
                # تحويل الخدمة الاختيارية
                is_optional = is_optional.lower() in ['نعم', 'yes', 'true', '1']
                
                services.append({
                    'service_category': category,
                    'service_name': name,
                    'quantity': quantity,
                    'unit': unit,
                    'unit_price': unit_price,
                    'setup_cost': setup_cost,
                    'is_optional': is_optional
                })
                
            except (ValueError, TypeError) as e:
                raise ValidationError(_('السطر {}: خطأ في تنسيق البيانات - {}').format(i, str(e)))
        
        if not services:
            raise ValidationError(_('لم يتم العثور على خدمات صالحة'))
        
        return services


__all__ = [
    'OrderServiceForm',
    'PrintingServiceForm',
    'FinishingServiceForm',
    'ServiceBulkForm'
]
