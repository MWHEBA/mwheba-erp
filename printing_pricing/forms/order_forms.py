from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal

from ..models import PrintingOrder, PaperSpecification, PrintingSpecification
from client.models import Customer


class PrintingOrderForm(forms.ModelForm):
    """
    نموذج إنشاء وتحرير طلبات التسعير
    """
    
    class Meta:
        model = PrintingOrder
        fields = [
            'customer', 'title', 'description', 'order_type',
            'quantity', 'pages_count', 'copies_count',
            'width', 'height', 'priority', 'due_date',
            'is_rush_order', 'rush_fee', 'profit_margin', 'notes'
        ]
        
        widgets = {
            'customer': forms.Select(attrs={
                'class': 'form-select',
                'data-live-search': 'true'
            }),
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('عنوان الطلب')
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('وصف تفصيلي للطلب')
            }),
            'order_type': forms.Select(attrs={
                'class': 'form-select'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'step': '1'
            }),
            'pages_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'step': '1'
            }),
            'copies_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'step': '1'
            }),
            'width': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.1',
                'placeholder': _('العرض بالسنتيمتر')
            }),
            'height': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.1',
                'placeholder': _('الارتفاع بالسنتيمتر')
            }),
            'priority': forms.Select(attrs={
                'class': 'form-select'
            }),
            'due_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'is_rush_order': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'rush_fee': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'profit_margin': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': _('ملاحظات إضافية')
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # تخصيص استعلام العملاء
        self.fields['customer'].queryset = Customer.objects.filter(
            is_active=True
        ).order_by('name')
        
        # إضافة CSS classes
        for field_name, field in self.fields.items():
            if not field.widget.attrs.get('class'):
                field.widget.attrs['class'] = 'form-control'
        
        # تعيين القيم الافتراضية
        if not self.instance.pk:
            self.fields['profit_margin'].initial = Decimal('20.00')
            self.fields['pages_count'].initial = 1
            self.fields['copies_count'].initial = 1
            self.fields['priority'].initial = 'medium'

    def clean_quantity(self):
        """التحقق من الكمية"""
        quantity = self.cleaned_data.get('quantity')
        if quantity and quantity <= 0:
            raise ValidationError(_('الكمية يجب أن تكون أكبر من صفر'))
        return quantity

    def clean_pages_count(self):
        """التحقق من عدد الصفحات"""
        pages_count = self.cleaned_data.get('pages_count')
        if pages_count and pages_count <= 0:
            raise ValidationError(_('عدد الصفحات يجب أن يكون أكبر من صفر'))
        return pages_count

    def clean_profit_margin(self):
        """التحقق من هامش الربح"""
        profit_margin = self.cleaned_data.get('profit_margin')
        if profit_margin and (profit_margin < 0 or profit_margin > 100):
            raise ValidationError(_('هامش الربح يجب أن يكون بين 0 و 100'))
        return profit_margin

    def clean(self):
        """التحقق الشامل من النموذج"""
        cleaned_data = super().clean()
        
        # التحقق من الأبعاد
        width = cleaned_data.get('width')
        height = cleaned_data.get('height')
        
        if width and height:
            if width <= 0 or height <= 0:
                raise ValidationError(_('الأبعاد يجب أن تكون أكبر من صفر'))
        
        # التحقق من رسوم الاستعجال
        is_rush_order = cleaned_data.get('is_rush_order')
        rush_fee = cleaned_data.get('rush_fee')
        
        if is_rush_order and not rush_fee:
            cleaned_data['rush_fee'] = Decimal('0.00')
        
        return cleaned_data


class PaperSpecificationForm(forms.ModelForm):
    """
    نموذج مواصفات الورق
    """
    
    class Meta:
        model = PaperSpecification
        fields = [
            'paper_type_name', 'paper_weight', 'paper_size_name',
            'sheet_width', 'sheet_height', 'montage_count',
            'piece_size', 'sheet_cost'
        ]
        
        widgets = {
            'paper_type_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('نوع الورق')
            }),
            'paper_weight': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '50',
                'max': '500',
                'step': '10'
            }),
            'paper_size_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('مقاس الورق')
            }),
            'sheet_width': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.1'
            }),
            'sheet_height': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.1'
            }),
            'montage_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'step': '1'
            }),
            'piece_size': forms.Select(attrs={
                'class': 'form-control',
                'placeholder': _('اختر مقاس القطع')
            }),
            'sheet_cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            })
        }

    def clean_paper_weight(self):
        """التحقق من وزن الورق"""
        weight = self.cleaned_data.get('paper_weight')
        if weight and (weight < 50 or weight > 500):
            raise ValidationError(_('وزن الورق يجب أن يكون بين 50 و 500 جرام'))
        return weight

    def clean_montage_count(self):
        """التحقق من عدد القطع في الفرخ"""
        montage_count = self.cleaned_data.get('montage_count')
        if montage_count and montage_count <= 0:
            raise ValidationError(_('عدد القطع في الفرخ يجب أن يكون أكبر من صفر'))
        return montage_count


class PrintingSpecificationForm(forms.ModelForm):
    """
    نموذج مواصفات الطباعة
    """
    
    class Meta:
        model = PrintingSpecification
        fields = [
            'printing_type', 'colors_front', 'colors_back',
            'is_cmyk', 'has_spot_colors', 'spot_colors_count',
            'resolution_dpi', 'print_quality', 'special_requirements'
        ]
        
        widgets = {
            'printing_type': forms.Select(attrs={
                'class': 'form-select'
            }),
            'colors_front': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '10',
                'step': '1'
            }),
            'colors_back': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '10',
                'step': '1'
            }),
            'is_cmyk': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'has_spot_colors': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'spot_colors_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '5',
                'step': '1'
            }),
            'resolution_dpi': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '150',
                'max': '2400',
                'step': '50'
            }),
            'print_quality': forms.Select(attrs={
                'class': 'form-select'
            }),
            'special_requirements': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('متطلبات خاصة للطباعة')
            })
        }

    def clean_colors_front(self):
        """التحقق من عدد ألوان الوجه"""
        colors = self.cleaned_data.get('colors_front')
        if colors and colors < 0:
            raise ValidationError(_('عدد الألوان لا يمكن أن يكون سالباً'))
        return colors

    def clean_spot_colors_count(self):
        """التحقق من عدد الألوان الخاصة"""
        spot_colors = self.cleaned_data.get('spot_colors_count')
        has_spot_colors = self.cleaned_data.get('has_spot_colors')
        
        if has_spot_colors and not spot_colors:
            raise ValidationError(_('يجب تحديد عدد الألوان الخاصة'))
        
        if not has_spot_colors and spot_colors:
            return 0
            
        return spot_colors


class OrderSearchForm(forms.Form):
    """
    نموذج البحث في الطلبات
    """
    search_query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('البحث في رقم الطلب، العنوان، أو العميل')
        })
    )
    
    status = forms.ChoiceField(
        required=False,
        choices=[('', _('جميع الحالات'))] + PrintingOrder._meta.get_field('status').choices,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    order_type = forms.ChoiceField(
        required=False,
        choices=[('', _('جميع الأنواع'))] + PrintingOrder._meta.get_field('order_type').choices,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.filter(is_active=True),
        required=False,
        empty_label=_('جميع العملاء'),
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )


__all__ = [
    'PrintingOrderForm', 
    'PaperSpecificationForm', 
    'PrintingSpecificationForm',
    'OrderSearchForm'
]
