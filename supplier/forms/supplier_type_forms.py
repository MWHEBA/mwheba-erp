"""
نماذج إدارة أنواع الموردين
"""
from django import forms
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
import re

from ..models import SupplierTypeSettings


class SupplierTypeSettingsForm(forms.ModelForm):
    """نموذج إضافة/تعديل إعدادات نوع المورد"""
    
    class Meta:
        model = SupplierTypeSettings
        fields = [
            'name', 'code', 'description', 'icon', 'color', 
            'display_order', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اسم نوع المورد',
                'required': True
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'الرمز (بالإنجليزية)',
                'pattern': '[a-zA-Z0-9_]+',
                'title': 'أحرف إنجليزية وأرقام وشرطة سفلية فقط',
                'required': True
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'وصف مختصر لنوع المورد',
                'rows': 3
            }),
            'icon': forms.Select(attrs={
                'class': 'form-select',
            }),
            'color': forms.TextInput(attrs={
                'type': 'color',
                'class': 'form-control form-control-color',
                'title': 'اختر لون النوع'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '1'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        icon_choices = [('', 'اختر أيقونة')] + self.get_icon_choices()
        self.fields['icon'].choices = icon_choices
        self.fields['icon'].required = True
        if not self.instance.pk:
            self.fields['color'].initial = '#007bff'
            self.fields['display_order'].initial = self.get_next_display_order()
            self.fields['is_active'].initial = True
            self.fields['icon'].initial = 'fas fa-truck'
    
    def get_icon_choices(self):
        return [
            ('fas fa-truck', '🚚 شاحنة'),
            ('fas fa-print', '🖨️ طابعة'),
            ('fas fa-file-alt', '📄 ورق'),
            ('fas fa-desktop', '🖥️ كمبيوتر'),
            ('fas fa-cut', '✂️ قص'),
            ('fas fa-layer-group', '📚 طبقات'),
            ('fas fa-box', '📦 صندوق'),
            ('fas fa-paint-brush', '🎨 فرشاة'),
            ('fas fa-bullhorn', '📢 مكبر صوت'),
            ('fas fa-bolt', '⚡ ليزر'),
            ('fas fa-crosshairs', '🎯 ليزر دقيق'),
            ('fas fa-burn', '🔥 ليزر حرق'),
            ('fas fa-cut', '✂️ ليزر قطع'),
            ('fas fa-gift', '🎁 هدية'),
            ('fas fa-ellipsis-h', '⋯ أخرى'),
            ('fas fa-cog', '⚙️ إعدادات'),
            ('fas fa-tools', '🔧 أدوات'),
            ('fas fa-industry', '🏭 صناعة'),
            ('fas fa-palette', '🎨 ألوان'),
            ('fas fa-camera', '📷 كاميرا'),
            ('fas fa-scissors', '✂️ مقص'),
            ('fas fa-hammer', '🔨 مطرقة'),
            ('fas fa-wrench', '🔧 مفتاح'),
        ]
    
    def get_next_display_order(self):
        from django.db.models import Max
        last_order = SupplierTypeSettings.objects.aggregate(
            max_order=Max('display_order')
        )['max_order']
        return (last_order or 0) + 1
    
    def clean_code(self):
        code = self.cleaned_data.get('code')
        if not code:
            return code
        
        if not re.match(r'^[a-zA-Z0-9_]+$', code):
            raise ValidationError(
                _("يجب أن يحتوي الرمز على أحرف إنجليزية وأرقام وشرطة سفلية فقط")
            )
        
        queryset = SupplierTypeSettings.objects.filter(code=code)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        
        if queryset.exists():
            raise ValidationError(_("هذا الرمز مستخدم بالفعل"))
        
        return code.lower()
    
    def clean_color(self):
        color = self.cleaned_data.get('color')
        if not color:
            return color
        
        if not re.match(r'^#[0-9A-Fa-f]{6}$', color):
            raise ValidationError(
                _("يجب أن يكون اللون بصيغة HEX صحيحة (مثل: #007bff)")
            )
        
        return color.upper()
    
    def clean_name(self):
        name = self.cleaned_data.get('name')
        if not name:
            raise ValidationError(_("اسم النوع مطلوب"))
        
        if len(name.strip()) < 2:
            raise ValidationError(_("يجب أن يكون اسم النوع أكثر من حرفين"))
        
        return name.strip()


class SupplierTypeReorderForm(forms.Form):
    """نموذج إعادة ترتيب أنواع الموردين"""
    
    type_ids = forms.CharField(
        widget=forms.HiddenInput(),
        help_text=_("قائمة معرفات الأنواع مرتبة")
    )
    
    def clean_type_ids(self):
        """التحقق من صحة معرفات الأنواع"""
        type_ids_str = self.cleaned_data.get('type_ids')
        if not type_ids_str:
            raise ValidationError(_("قائمة الأنواع مطلوبة"))
        
        try:
            type_ids = [int(id_str) for id_str in type_ids_str.split(',')]
        except ValueError:
            raise ValidationError(_("معرفات الأنواع غير صحيحة"))
        
        # التحقق من وجود جميع الأنواع
        existing_count = SupplierTypeSettings.objects.filter(
            id__in=type_ids
        ).count()
        
        if existing_count != len(type_ids):
            raise ValidationError(_("بعض الأنواع غير موجودة"))
        
        return type_ids


class SupplierTypeDeleteForm(forms.Form):
    """نموذج حذف نوع المورد مع التحقق من الأمان"""
    
    confirm_delete = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        label=_("أؤكد رغبتي في حذف هذا النوع")
    )
    
    def __init__(self, supplier_type_settings, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.supplier_type_settings = supplier_type_settings
    
    def clean_confirm_delete(self):
        """التحقق من إمكانية الحذف"""
        confirm = self.cleaned_data.get('confirm_delete')
        
        if not confirm:
            raise ValidationError(_("يجب تأكيد الحذف"))
        
        # التحقق من أن النوع ليس نوع نظام
        if self.supplier_type_settings.is_system:
            raise ValidationError(
                _("لا يمكن حذف أنواع النظام الأساسية")
            )
        
        # التحقق من عدم وجود موردين مرتبطين
        if self.supplier_type_settings.suppliers_count > 0:
            raise ValidationError(
                _("لا يمكن حذف النوع لأنه مرتبط بـ {} مورد").format(
                    self.supplier_type_settings.suppliers_count
                )
            )
        
        return confirm


class SupplierTypeBulkActionForm(forms.Form):
    """نموذج العمليات المجمعة على أنواع الموردين"""
    
    ACTION_CHOICES = [
        ('activate', _('تفعيل')),
        ('deactivate', _('إلغاء تفعيل')),
        ('delete', _('حذف')),
    ]
    
    selected_types = forms.CharField(
        widget=forms.HiddenInput(),
        help_text=_("معرفات الأنواع المحددة")
    )
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select'
        }),
        label=_("العملية")
    )
    
    def clean_selected_types(self):
        """التحقق من الأنواع المحددة"""
        selected_str = self.cleaned_data.get('selected_types')
        if not selected_str:
            raise ValidationError(_("يجب تحديد أنواع للعمل عليها"))
        
        try:
            selected_ids = [int(id_str) for id_str in selected_str.split(',')]
        except ValueError:
            raise ValidationError(_("معرفات الأنواع غير صحيحة"))
        
        # التحقق من وجود الأنواع
        existing_types = SupplierTypeSettings.objects.filter(
            id__in=selected_ids
        )
        
        if existing_types.count() != len(selected_ids):
            raise ValidationError(_("بعض الأنواع المحددة غير موجودة"))
        
        return existing_types
    
    def clean(self):
        """التحقق من صحة العملية"""
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        selected_types = cleaned_data.get('selected_types')
        
        if action == 'delete' and selected_types:
            # التحقق من أن الأنواع المحددة ليست أنواع نظام
            system_types = selected_types.filter(is_system=True)
            if system_types.exists():
                raise ValidationError(
                    _("لا يمكن حذف أنواع النظام: {}").format(
                        ', '.join(system_types.values_list('name', flat=True))
                    )
                )
            
            # التحقق من عدم وجود موردين مرتبطين
            types_with_suppliers = []
            for supplier_type in selected_types:
                if supplier_type.suppliers_count > 0:
                    types_with_suppliers.append(
                        f"{supplier_type.name} ({supplier_type.suppliers_count} مورد)"
                    )
            
            if types_with_suppliers:
                raise ValidationError(
                    _("لا يمكن حذف الأنواع التالية لأنها مرتبطة بموردين: {}").format(
                        ', '.join(types_with_suppliers)
                    )
                )
        
        return cleaned_data
