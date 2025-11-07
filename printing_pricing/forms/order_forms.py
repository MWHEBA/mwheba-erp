"""
نماذج الطلبات المحسنة للنظام الجديد
Enhanced order forms for the new system
"""

from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from ..models import (
    PaperType, ProductType, ProductSize, PrintDirection, PrintSide,
    CoatingType, FinishingType, PrintingOrder, PaperSpecification, PrintingSpecification
)
from supplier.models import Supplier, PaperServiceDetails
from client.models import Customer
from users.models import User


class PricingOrderForm(forms.ModelForm):
    """نموذج طلب التسعير المحسن"""

    # خيارات نوع التقفيل
    BINDING_TYPES = [
        ("staple", _("تدبيس")),
        ("wire", _("سلك")),
        ("sewing", _("خياطة")),
        ("glue", _("تغرية")),
        ("spiral", _("سبيرال")),
        ("none", _("بدون")),
    ]

    # خيارات جهة التقفيل
    BINDING_SIDES = [
        ("arabic", _("عربي")),
        ("english", _("انجليزي")),
        ("top", _("أعلى")),
    ]

    # حقول إضافية للمقاسات المخصصة
    custom_size_width = forms.DecimalField(
        label=_("العرض المخصص (سم)"),
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "step": "0.1",
            "placeholder": "21.0"
        }),
    )

    custom_size_height = forms.DecimalField(
        label=_("الطول المخصص (سم)"),
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "step": "0.1",
            "placeholder": "29.7"
        }),
    )

    # حقول المقاس المفتوح
    open_size_width = forms.DecimalField(
        label=_("عرض المقاس المفتوح (سم)"),
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "step": "0.1"
        }),
    )

    open_size_height = forms.DecimalField(
        label=_("طول المقاس المفتوح (سم)"),
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "step": "0.1"
        }),
    )

    # حقول التقفيل
    binding_type = forms.ChoiceField(
        label=_("نوع التقفيل"),
        choices=BINDING_TYPES,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    binding_side = forms.ChoiceField(
        label=_("جهة التقفيل"),
        choices=BINDING_SIDES,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    # حقول الورق المتقدمة
    paper_supplier = forms.ModelChoiceField(
        label=_("مورد الورق"),
        queryset=Supplier.objects.none(),  # سيتم تحديثه في __init__
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    paper_sheet_type = forms.ChoiceField(
        label=_("مقاس الفرخ"),
        choices=[],
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    paper_origin = forms.ChoiceField(
        label=_("بلد المنشأ"),
        required=False,
        choices=[("", "---------")],
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    paper_weight = forms.ChoiceField(
        label=_("جرام الورق"),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    paper_price = forms.DecimalField(
        label=_("سعر الورق"),
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "step": "0.01"
        }),
    )

    # حقول الزنكات
    zinc_plates_count = forms.IntegerField(
        label=_("عدد الزنكات"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    # حقول المحتوى الداخلي
    internal_page_count = forms.IntegerField(
        label=_("عدد صفحات الداخل"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    # حقول التصميم
    design_price = forms.DecimalField(
        label=_("سعر التصميم"),
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "step": "0.01"
        }),
    )
    class Meta:
        from printing_pricing.models import PrintingOrder
        model = PrintingOrder
        fields = [
            "client",
            "title",
            "description",
            "quantity",
            "product_type",
            "paper_type",
            "product_size",
            "supplier",
            "press",
            "colors_front",
            "colors_back",
            "print_sides",
            "print_direction",
            "coating_type",
            "coating_service",
            "has_internal_content",
            "material_cost",
            "printing_cost",
            "finishing_cost",
            "extra_cost",
            "sale_price",
            "status",
        ]
        widgets = {
            "client": forms.Select(attrs={
                "class": "form-control select2",
                "data-placeholder": "اختر العميل...",
            }),
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "عنوان الطلب"
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "وصف الطلب (اختياري)"
            }),
            "quantity": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "1"
            }),
            "has_internal_content": forms.CheckboxInput(attrs={
                "class": "form-check-input"
            }),
            "colors_front": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0",
                "max": "10"
            }),
            "colors_back": forms.NumberInput(attrs={
                "class": "form-control", 
                "min": "0",
                "max": "10"
            }),
            "material_cost": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01"
            }),
            "printing_cost": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01"
            }),
            "finishing_cost": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01"
            }),
            "extra_cost": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01"
            }),
            "profit_margin": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01"
            }),
            "sale_price": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01"
            }),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        
        # إضافة فئات CSS لجميع الحقول
        for field_name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = "form-control"

        # ربط نوع المنتج بالإعدادات
        try:
            self.fields["product_type"].queryset = ProductType.objects.filter(
                is_active=True
            ).order_by("name")
            self.fields["product_type"].empty_label = "اختر نوع المنتج"
        except:
            pass

        # ربط مقاس المنتج بالإعدادات
        try:
            self.fields["product_size"].queryset = ProductSize.objects.filter(
                is_active=True
            ).order_by("name")
            self.fields["product_size"].empty_label = "اختر مقاس المنتج"
        except:
            pass

        # ربط نوع الورق بالإعدادات
        try:
            self.fields["paper_type"].queryset = PaperType.objects.filter(
                is_active=True
            ).order_by("name")
            self.fields["paper_type"].empty_label = "اختر نوع الورق"
            
            # تعيين قيمة افتراضية
            if not self.instance.pk and not self.initial.get("paper_type"):
                default_paper_type = PaperType.objects.filter(
                    is_active=True, is_default=True
                ).first()
                if default_paper_type:
                    self.initial["paper_type"] = default_paper_type.pk
        except Exception as e:
            print(f"خطأ في تحديد نوع الورق الافتراضي: {e}")

        # ربط اتجاه الطباعة
        try:
            self.fields["print_direction"].queryset = PrintDirection.objects.filter(
                is_active=True
            ).order_by("name")
        except:
            pass

        # ربط جوانب الطباعة
        try:
            self.fields["print_sides"].queryset = PrintSide.objects.filter(
                is_active=True
            ).order_by("name")
        except:
            pass

        # ربط أنواع التغطية
        try:
            self.fields["coating_type"].queryset = CoatingType.objects.filter(
                is_active=True
            ).order_by("name")
        except:
            pass

        # إعداد موردي الورق
        try:
            paper_suppliers = Supplier.objects.filter(
                is_active=True,
                id__in=PaperServiceDetails.objects.filter(
                    service__is_active=True
                ).values_list("service__supplier_id", flat=True).distinct(),
            ).distinct()
            self.fields["paper_supplier"].queryset = paper_suppliers
        except:
            pass

        # جعل الحقول الاختيارية
        optional_fields = [
            "product_type", "paper_type", "product_size", "print_direction",
            "coating_type", "coating_service", "supplier", "press",
            "description", "paper_supplier", "paper_sheet_type", 
            "paper_origin", "paper_weight", "paper_price",
            "zinc_plates_count", "internal_page_count", "design_price",
            "custom_size_width", "custom_size_height",
            "open_size_width", "open_size_height"
        ]
        
        for field in optional_fields:
            if field in self.fields:
                self.fields[field].required = False

        # تعيين المستخدم المنشئ
        if user and not self.instance.pk:
            self.initial["created_by"] = user

    def clean(self):
        """التحقق من صحة البيانات المدخلة"""
        cleaned_data = super().clean()
        
        # التحقق من نوع الورق
        paper_type = cleaned_data.get("paper_type")
        if paper_type in ['', 'undefined', 'null', 'None']:
            cleaned_data["paper_type"] = None
        
        # التحقق من جوانب الطباعة والألوان
        print_sides = cleaned_data.get("print_sides")
        colors_front = cleaned_data.get("colors_front")
        colors_back = cleaned_data.get("colors_back")
        
        if print_sides:
            try:
                sides_count = getattr(print_sides, "sides_count", None)
                
                if sides_count == 2:  # وجهين
                    if colors_front is None:
                        self.add_error("colors_front", 
                                     _("يجب تحديد عدد ألوان الوجه الأمامي"))
                    if colors_back is None:
                        self.add_error("colors_back", 
                                     _("يجب تحديد عدد ألوان الوجه الخلفي"))
                elif sides_count == 1:  # وجه واحد
                    if colors_front is None:
                        self.add_error("colors_front", 
                                     _("يجب تحديد عدد ألوان الوجه الأمامي"))
                    cleaned_data["colors_back"] = 0
            except Exception as e:
                print(f"خطأ في التحقق من جوانب الطباعة: {e}")

        # التحقق من قيم الألوان
        if colors_front is not None and colors_front < 0:
            self.add_error("colors_front", _("عدد الألوان يجب أن يكون موجباً"))

        if colors_back is not None and colors_back < 0:
            self.add_error("colors_back", _("عدد الألوان يجب أن يكون موجباً"))

        # التحقق من الكمية
        quantity = cleaned_data.get("quantity")
        if quantity is not None and quantity <= 0:
            self.add_error("quantity", _("الكمية يجب أن تكون أكبر من صفر"))

        return cleaned_data

    def clean_custom_size_width(self):
        """التحقق من العرض المخصص"""
        width = self.cleaned_data.get('custom_size_width')
        if width is not None and width <= 0:
            raise ValidationError(_('العرض يجب أن يكون أكبر من صفر'))
        return width

    def clean_custom_size_height(self):
        """التحقق من الطول المخصص"""
        height = self.cleaned_data.get('custom_size_height')
        if height is not None and height <= 0:
            raise ValidationError(_('الطول يجب أن يكون أكبر من صفر'))
        return height


# ==================== نموذج البحث في الطلبات ====================

class OrderSearchForm(forms.Form):
    """نموذج البحث في طلبات التسعير"""

    search = forms.CharField(
        label=_("البحث"),
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": _("البحث في رقم الطلب أو العنوان أو العميل..."),
        }),
    )

    client = forms.ModelChoiceField(
        label=_("العميل"),
        queryset=Customer.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-control select2"}),
        empty_label=_("جميع العملاء")
    )

    status = forms.ChoiceField(
        label=_("الحالة"),
        required=False,
        choices=[("", _("جميع الحالات"))],  # سيتم تحديثها في __init__
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    date_from = forms.DateField(
        label=_("من تاريخ"),
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "data-date-picker": True,
            "placeholder": "من تاريخ..."
        }),
    )

    date_to = forms.DateField(
        label=_("إلى تاريخ"),
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "data-date-picker": True,
            "placeholder": "إلى تاريخ..."
        }),
    )

    order_type = forms.ChoiceField(
        label=_("نوع الطلب"),
        required=False,
        choices=[("", _("جميع الأنواع"))],  # سيتم تحديثها في __init__
        widget=forms.Select(attrs={"class": "form-control"}),
    )


# ==================== النماذج الإضافية من الملف القديم ====================

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
        """التحقق من عدد ألوان الوجه الأمامي"""
        colors = self.cleaned_data.get('colors_front')
        if colors and colors < 0:
            raise ValidationError(_('عدد الألوان يجب أن يكون موجباً'))
        return colors

    def clean_colors_back(self):
        """التحقق من عدد ألوان الوجه الخلفي"""
        colors = self.cleaned_data.get('colors_back')
        if colors and colors < 0:
            raise ValidationError(_('عدد الألوان يجب أن يكون موجباً'))
        return colors

    def clean_spot_colors_count(self):
        """التحقق من عدد الألوان الخاصة"""
        spot_colors = self.cleaned_data.get('spot_colors_count')
        has_spot_colors = self.cleaned_data.get('has_spot_colors')
        
        if has_spot_colors and (not spot_colors or spot_colors <= 0):
            raise ValidationError(_('يجب تحديد عدد الألوان الخاصة'))
        
        return spot_colors


# ==================== التوافق مع النظام القديم ====================

# الاحتفاظ بالنموذج القديم للتوافق مع النظام القديم
PrintingOrderForm = PricingOrderForm


__all__ = [
    'PricingOrderForm',
    'PrintingOrderForm',  # للتوافق مع النظام القديم
    'PaperSpecificationForm', 
    'PrintingSpecificationForm',
    'OrderSearchForm'
]
