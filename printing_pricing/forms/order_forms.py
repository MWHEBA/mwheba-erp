from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import (
    PaperType, PaperWeight, PaperSize, PaperOrigin, PlateSize,
    ProductType, ProductSize,
    CoatingType, FinishingType, PrintingOrder, PaperSpecification
)
from supplier.models import Supplier
from customer.models import Customer


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

    # حقول الورق
    paper_type = forms.ModelChoiceField(
        label=_("نوع الورق"),
        queryset=PaperType.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-control select2"}),
    )

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

    # حقول العميل اليدوي
    customer_name = forms.CharField(
        label=_("اسم العميل"),
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": _("اكتب اسم العميل يدوياً للتسعير السريع...")
        }),
    )

    # حقول ألوان الطباعة
    colors_front = forms.IntegerField(
        label=_("عدد ألوان الوجه الأمامي"),
        required=False,
        initial=4,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
    )
    colors_back = forms.IntegerField(
        label=_("عدد ألوان الوجه الخلفي"),
        required=False,
        initial=4,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
    )

    class Meta:
        from printing_pricing.models import PrintingOrder
        model = PrintingOrder
        fields = [
            "customer",
            "customer_name",
            "order_date",
            "due_date",
            "work_order",
            "currency",
            "title",
            "description",
            "order_type",
            "quantity",
            "product_type",
            "product_size",
            "width",
            "height",
            "print_orientation",
            "is_closed_size",
            "open_direction",
            "cover_printing_type",
            "print_sides_mode",
            "digital_color_mode",
            "spot_colors_front",
            "spot_colors_back",
            "inner_printing_type",
            "inner_print_sides_mode",
            "inner_color_mode",
            "inner_spot_colors",
            "inner_color_pages",
            "inner_bw_pages",
            "inner_signatures_count",
            "binding_type",
            "spine_thickness",
            "inner_paper_type",
            "inner_paper_weight",
            "inner_coating_type",
            "ncr_sets_count",
            "ncr_book_capacity",
            "ncr_serial_start",
            "ncr_serial_end",
            "folder_pocket_type",
            "folder_card_slit",
            "folder_pocket_height",
            "design_service_type",
            "design_fee",
            "sales_rep",
            "sales_commission_rate",
            "profit_margin",
            "final_price",
            "status",
        ]
        widgets = {
            "customer": forms.Select(attrs={
                "class": "form-control select2",
                "data-placeholder": "اختر العميل...",
            }),
            "work_order": forms.Select(attrs={
                "class": "form-control select2",
                "data-placeholder": "اختر أمر الشغل (اختياري)...",
            }),
            "currency": forms.Select(attrs={
                "class": "form-select",
            }),
            "design_service_type": forms.Select(attrs={
                "class": "form-select",
            }),
            "sales_rep": forms.Select(attrs={
                "class": "form-control select2",
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
            "design_fee": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01"
            }),
            "profit_margin": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01"
            }),
            "sales_commission_rate": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01"
            }),
            "final_price": forms.NumberInput(attrs={
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

        # ضبط حقل العميل والعميل اليدوي
        if "customer" in self.fields:
            self.fields["customer"].required = False
            self.fields["customer"].queryset = Customer.objects.filter(is_active=True).order_by("name")
            self.fields["customer"].empty_label = _("اختر العميل المسجل (اختياري)...")

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

        # ربط أوزان الورق بالإعدادات
        try:
            active_weights = PaperWeight.objects.filter(is_active=True).order_by("gsm")
            self.fields["paper_weight"].choices = [("", _("اختر وزن الورق"))] + [
                (str(w.gsm), f"{w.name} ({w.gsm} جم)") for w in active_weights
            ]
            if not self.instance.pk and not self.initial.get("paper_weight"):
                default_weight = active_weights.filter(is_default=True).first()
                if default_weight:
                    self.initial["paper_weight"] = str(default_weight.gsm)
                else:
                    self.initial["paper_weight"] = "300"
        except Exception as e:
            print(f"خطأ في تحديد وزن الورق الافتراضي: {e}")



        # ربط مناشئ الورق ديناميكياً
        try:
            active_origins = PaperOrigin.objects.filter(is_active=True).order_by("name")
            self.fields["paper_origin"].choices = [("", _("اختر المنشأ"))] + [
                (str(o.id), o.name) for o in active_origins
            ]
        except Exception:
            pass

        # ربط مقاسات الفرخ ديناميكياً
        try:
            active_sizes = PaperSize.objects.filter(is_active=True).order_by("name")
            self.fields["paper_sheet_type"].choices = [("", _("اختر مقاس الفرخ"))] + [
                (s.name, f"{s.name} ({s.width}×{s.height} سم)") for s in active_sizes
            ]
        except Exception:
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
            if HAS_PAPER_SERVICE_DETAILS and PaperServiceDetails is not None:
                paper_suppliers = Supplier.objects.filter(
                    is_active=True,
                    id__in=PaperServiceDetails.objects.filter(
                        service__is_active=True
                    ).values_list("service__supplier_id", flat=True).distinct(),
                ).distinct()
            else:
                paper_suppliers = Supplier.objects.filter(is_active=True)
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
        
        # التحقق من العميل (إما مسجل أو مكتوب يدوياً)
        customer = cleaned_data.get("customer")
        customer_name = cleaned_data.get("customer_name")
        if not customer and not customer_name:
            self.add_error("customer_name", _("يرجى اختيار العميل المسجل أو كتابة اسم العميل يدوياً."))

        # التحقق من جوانب الطباعة والألوان بطريقة ديناميكية مرنة
        print_sides = cleaned_data.get("print_sides_mode") or cleaned_data.get("print_sides")
        colors_front = cleaned_data.get("colors_front")
        colors_back = cleaned_data.get("colors_back")
        
        if print_sides:
            sides_str = str(print_sides).lower()
            if 'double' in sides_str or 'work_sheet' in sides_str or 'وجهين' in sides_str or 'قلب' in sides_str:
                if colors_front is None:
                    self.add_error("colors_front", _("يجب تحديد عدد ألوان الوجه الأمامي"))
                if colors_back is None:
                    self.add_error("colors_back", _("يجب تحديد عدد ألوان الوجه الخلفي"))
            elif 'single' in sides_str or 'واحد' in sides_str:
                if colors_front is None:
                    self.add_error("colors_front", _("يجب تحديد عدد ألوان الوجه الأمامي"))
                cleaned_data["colors_back"] = 0

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

    def clean_width(self):
        """التحقق من العرض الفعلي"""
        width = self.cleaned_data.get('width')
        if width is not None and width <= 0:
            raise ValidationError(_('العرض يجب أن يكون أكبر من صفر'))
        return width

    def clean_height(self):
        """التحقق من الارتفاع الفعلي"""
        height = self.cleaned_data.get('height')
        if height is not None and height <= 0:
            raise ValidationError(_('الارتفاع يجب أن يكون أكبر من صفر'))
        return height

    def clean_custom_size_width(self):
        """التحقق من العرض المخصص ومزامنته"""
        width = self.cleaned_data.get('custom_size_width')
        if width is not None and width <= 0:
            raise ValidationError(_('العرض يجب أن يكون أكبر من صفر'))
        return width

    def clean_custom_size_height(self):
        """التحقق من الطول المخصص ومزامنته"""
        height = self.cleaned_data.get('custom_size_height')
        if height is not None and height <= 0:
            raise ValidationError(_('الطول يجب أن يكون أكبر من صفر'))
        return height

    def save(self, commit=True):
        """حفظ الطلب داخل معاملة ذرية مع مزامنة الحقول التوافقية"""
        with transaction.atomic():
            instance = super().save(commit=False)
            
            # مزامنة final_price و sale_price
            if not instance.final_price and instance.sale_price:
                instance.final_price = instance.sale_price
            elif not instance.sale_price and instance.final_price:
                instance.sale_price = instance.final_price
                
            if commit:
                instance.save()
                self.save_m2m()
                
            return instance


# ==================== نموذج البحث في الطلبات ====================

class OrderSearchForm(forms.Form):
    """نموذج البحث في طلبات التسعير"""

    search = forms.CharField(
        label=_("بحث سريع"),
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control form-control-sm",
            "placeholder": _("رقم الطلب أو العنوان أو العميل..."),
        }),
    )

    customer = forms.ModelChoiceField(
        label=_("العميل"),
        queryset=Customer.objects.filter(is_active=True).order_by('name'),
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm select2-filter", "dir": "rtl"}),
        empty_label=_("جميع العملاء")
    )

    status = forms.ChoiceField(
        label=_("حالة الطلب"),
        required=False,
        choices=[("", _("جميع الحالات"))],
        widget=forms.Select(attrs={"class": "form-select form-select-sm select2-filter", "dir": "rtl"}),
    )

    order_type = forms.ChoiceField(
        label=_("نوع المطبوع"),
        required=False,
        choices=[("", _("جميع الأنواع"))],
        widget=forms.Select(attrs={"class": "form-select form-select-sm select2-filter", "dir": "rtl"}),
    )

    date_from = forms.DateField(
        label=_("من تاريخ"),
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control form-control-sm",
            "data-date-picker": "true",
            "placeholder": "YYYY-MM-DD"
        }),
    )

    date_to = forms.DateField(
        label=_("إلى تاريخ"),
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control form-control-sm",
            "data-date-picker": "true",
            "placeholder": "YYYY-MM-DD"
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from ..models.base import PricingStatus, OrderType
        self.fields['status'].choices = [("", _("جميع الحالات"))] + list(PricingStatus.choices)
        self.fields['order_type'].choices = [("", _("جميع الأنواع"))] + list(OrderType.choices)


__all__ = [
    'PricingOrderForm',
    'OrderSearchForm'
]


