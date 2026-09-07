from decimal import Decimal
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


class FlexibleChoiceField(forms.ChoiceField):
    """حقل خيارات مرن يقبل الخيارات الديناميكية ويتفادى أخطاء الاختيارات غير المتاحة للحقول الاختيارية"""
    def validate(self, value):
        if value in self.empty_values:
            if self.required:
                raise ValidationError(self.error_messages['required'], code='required')
            return
        if not self.valid_value(value):
            if not self.required:
                return
            raise ValidationError(
                self.error_messages['invalid_choice'],
                code='invalid_choice',
                params={'value': value},
            )


class FlexibleModelChoiceField(forms.ModelChoiceField):
    """حقل اختيار من النموذج يقبل الخيارات المخصصة مثل custom أو القيم النصية بمرونة ودون استثناءات فنية"""
    def to_python(self, value):
        if value in self.empty_values or value in ['', 'custom', 'undefined', 'null', 'None']:
            return None
        if isinstance(value, str) and not value.isdigit():
            try:
                # 1. البحث بالاسم المطابق
                obj = self.queryset.filter(name__iexact=value).first()
                if obj:
                    return obj
                # 2. البحث بالتصنيف الأساسي base_archetype (مثل ProductType)
                if hasattr(self.queryset.model, 'base_archetype'):
                    obj = self.queryset.filter(base_archetype=value).first()
                    if obj:
                        return obj
                    obj = self.queryset.model.objects.filter(base_archetype=value).first()
                    if obj:
                        return obj
                # 3. البحث بالاسم على مستوى الجدول كاملاً
                obj = self.queryset.model.objects.filter(name__iexact=value).first()
                if obj:
                    return obj
            except Exception:
                pass
            if not self.required:
                return None
        try:
            return super().to_python(value)
        except ValidationError:
            try:
                obj = self.queryset.model.objects.filter(pk=value).first()
                if obj:
                    return obj
            except Exception:
                pass
            if not self.required:
                return None
            raise


class PricingOrderForm(forms.ModelForm):
    """نموذج طلب التسعير المحسن"""

    # خيارات نوع الطباعة المتوافقة مع بنر ومتر مسطح
    COVER_PRINTING_TYPES = [
        ('offset', _('أوفست')),
        ('digital', _('ديجيتال')),
        ('digital_banner', _('ديجيتال بنر ومتر مسطح')),
        ('screen', _('سلك سكرين')),
        ('none', _('بدون طباعة')),
    ]

    # خيارات نوع التقفيل المعيارية المتوافقة 100% مع النموذج وقوالب العرض
    BINDING_TYPES = [
        ("staple", _("دبوس فرنسي سرج")),
        ("perfect_binding", _("غراء حراري كعب مربع (PUR)")),
        ("hardcover", _("كرتون مقوى فاخر (Hardcover)")),
        ("wire_o", _("سلك لولبي دبل")),
        ("pad_glue", _("بلوك تكعيب غراء من أعلى (نوت بوك / روشتات)")),
        ("sewing_binding", _("خياطة ملازم وتجليد فاخر")),
        # خيارات توافقية قديمة
        ("glue", _("غراء حراري")),
        ("wire", _("سلك")),
        ("spiral", _("سبيرال")),
        ("sewing", _("خياطة")),
        ("none", _("بدون تجليد")),
    ]

    # خيارات جهة التقفيل
    BINDING_SIDES = [
        ("arabic", _("عربي")),
        ("english", _("انجليزي")),
        ("top", _("أعلى")),
    ]

    # حقول العميل ومقاس ونوع المطبوع المرنة
    customer = FlexibleModelChoiceField(
        label=_("العميل المسجل"),
        queryset=Customer.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-control select2"}),
    )

    product_type = FlexibleModelChoiceField(
        label=_("نوع المطبوع"),
        queryset=ProductType.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-control select2"}),
    )

    product_size = FlexibleModelChoiceField(
        label=_("مقاس المطبوع"),
        queryset=ProductSize.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-control select2"}),
    )

    cover_printing_type = FlexibleChoiceField(
        label=_("نوع الطباعة"),
        choices=COVER_PRINTING_TYPES,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

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

    # حقل هامش الربح المحمي
    profit_margin = forms.DecimalField(
        label=_("هامش الربح (%)"),
        required=False,
        max_digits=12,
        decimal_places=4,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01"
        }),
    )

    # حقول التقفيل
    binding_type = FlexibleChoiceField(
        label=_("نوع التقفيل"),
        choices=BINDING_TYPES,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    binding_side = FlexibleChoiceField(
        label=_("جهة التقفيل"),
        choices=BINDING_SIDES,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    # حقول الورق المرنة المتوافقة مع ديناميكية AJAX
    paper_type = FlexibleModelChoiceField(
        label=_("نوع الورق"),
        queryset=PaperType.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-control select2"}),
    )

    paper_supplier = FlexibleModelChoiceField(
        label=_("مورد الورق"),
        queryset=Supplier.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    inner_paper_supplier = FlexibleModelChoiceField(
        label=_("مورد ورق الداخلي"),
        queryset=Supplier.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    paper_sheet_type = forms.CharField(
        label=_("مقاس الفرخ"),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    paper_origin = forms.CharField(
        label=_("بلد المنشأ"),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    paper_weight = forms.CharField(
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

    # حقول تفاصيل الورق والمونتاج
    sheet_size = forms.CharField(
        label=_("مقاس الفرخ"),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    piece_size = forms.CharField(
        label=_("مقاس الشيت"),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    montage_count = forms.IntegerField(
        label=_("المونتاج"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    imposition_orientation = forms.CharField(
        label=_("توجيه المونتاج"),
        required=False,
        initial="auto",
        widget=forms.HiddenInput(),
    )

    waste_sheets = forms.IntegerField(
        label=_("أفرخ الهالك"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    sheets_per_pack = forms.IntegerField(
        label=_("سعة الرزمة"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    # حقول الزنكات والطباعة الأوفست
    zinc_plates_count = forms.IntegerField(
        label=_("عدد الزنكات"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    plate_price = forms.DecimalField(
        label=_("سعر الزنكة"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    press_rate = forms.DecimalField(
        label=_("سعر التراج"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    cover_offset_supplier = FlexibleModelChoiceField(
        label=_("مطبعة الأوفست"),
        queryset=Supplier.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    cover_ctp_supplier = FlexibleModelChoiceField(
        label=_("مكتب فصل زنكات CTP"),
        queryset=Supplier.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    cover_digital_supplier = FlexibleModelChoiceField(
        label=_("مركز الطباعة الديجيتال"),
        queryset=Supplier.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    press_bed_size = forms.CharField(
        label=_("مقاس ماكينة الأوفست"),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    cover_press_machine = forms.CharField(
        label=_("ماكينة الأوفست"),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    plate_count_front = forms.IntegerField(
        label=_("زنكات الوجه"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    plate_count_back = forms.IntegerField(
        label=_("زنكات الظهر"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    plates_option = forms.CharField(
        label=_("خيار الزنكات"),
        required=False,
        widget=forms.HiddenInput(),
    )

    is_plates_archived = forms.BooleanField(
        label=_("الزنكات موجودة مسبقاً"),
        required=False,
        widget=forms.CheckboxInput(),
    )

    digital_sheet_price = forms.DecimalField(
        label=_("سعر طبعة الديجيتال"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    banner_sqm_price = forms.DecimalField(
        label=_("سعر المتر المربع"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    screen_colors_count = forms.IntegerField(
        label=_("ألوان الشابلونة"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    # حقول تفاصيل الداخلي والتجليد
    internal_page_count = forms.IntegerField(
        label=_("عدد صفحات الداخل"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    pages_count = forms.IntegerField(
        label=_("إجمالي عدد الصفحات"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    inner_sheet_size = forms.CharField(
        label=_("مقاس فرخ الداخلي"),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    inner_sheet_price = forms.DecimalField(
        label=_("سعر فرخ الداخلي"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    inner_offset_supplier = FlexibleModelChoiceField(
        label=_("مطبعة أوفست الداخلي"),
        queryset=Supplier.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    inner_ctp_supplier = FlexibleModelChoiceField(
        label=_("مكتب فصل زنكات الداخلي"),
        queryset=Supplier.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    inner_press_rate = forms.DecimalField(
        label=_("سعر تراج الداخلي"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    inner_plate_price = forms.DecimalField(
        label=_("سعر زنكة الداخلي"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    inner_press_bed_size = forms.CharField(
        label=_("مقاس زنك الداخلي"),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    color_signatures_count = forms.IntegerField(
        label=_("ملازم ملونة"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    bw_signatures_count = forms.IntegerField(
        label=_("ملازم نصوص"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    # حقول التكلفة والسايدبار
    material_cost = forms.DecimalField(
        label=_("تكلفة الخامات"),
        required=False,
        widget=forms.HiddenInput(),
    )

    printing_cost = forms.DecimalField(
        label=_("تكلفة الطباعة"),
        required=False,
        widget=forms.HiddenInput(),
    )

    finishing_cost = forms.DecimalField(
        label=_("تكلفة التشطيب"),
        required=False,
        widget=forms.HiddenInput(),
    )

    extra_cost = forms.DecimalField(
        label=_("انتقالات"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
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

        # ضبط حقل هامش الربح
        if "profit_margin" in self.fields:
            self.fields["profit_margin"].required = False
            if not self.instance.pk and not self.initial.get("profit_margin"):
                self.initial["profit_margin"] = Decimal("30.00")

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

        # ربط نوع الورق بالخامات المسجلة والمتاحة لدى الموردين
        try:
            from printing_pricing.views.order_views import get_active_paper_types
            active_types = get_active_paper_types()
            if self.instance and getattr(self.instance, 'paper_type_id', None):
                self.fields["paper_type"].queryset = PaperType.objects.filter(
                    Q(id=self.instance.paper_type_id) | Q(id__in=active_types.values_list('id', flat=True))
                ).distinct().order_by('sort_order', 'name')
            else:
                self.fields["paper_type"].queryset = active_types
            self.fields["paper_type"].empty_label = "اختر نوع الورق"
            
            # تعيين قيمة افتراضية
            if not self.instance.pk and not self.initial.get("paper_type"):
                default_paper_type = active_types.filter(
                    is_default=True
                ).first() or active_types.filter(name__icontains='كوشيه').first() or active_types.first()
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
                (o.name, o.name) for o in active_origins
            ] + [
                (str(o.id), o.name) for o in active_origins
            ] + [
                ("قياسي / غير محدد", _("قياسي / غير محدد")),
                ("قياسي / عام", _("قياسي / عام")),
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
            from printing_pricing.views.order_views import get_active_paper_suppliers
            active_suppliers = get_active_paper_suppliers()
            if active_suppliers and hasattr(active_suppliers, 'exists') and active_suppliers.exists():
                self.fields["paper_supplier"].queryset = active_suppliers
                if "inner_paper_supplier" in self.fields:
                    self.fields["inner_paper_supplier"].queryset = active_suppliers
            else:
                self.fields["paper_supplier"].queryset = Supplier.objects.filter(is_active=True)
                if "inner_paper_supplier" in self.fields:
                    self.fields["inner_paper_supplier"].queryset = Supplier.objects.filter(is_active=True)
        except Exception:
            self.fields["paper_supplier"].queryset = Supplier.objects.filter(is_active=True)
            if "inner_paper_supplier" in self.fields:
                self.fields["inner_paper_supplier"].queryset = Supplier.objects.filter(is_active=True)

        # جعل الحقول الهيكلية والفرعية اختيارية لتفادي أخطاء الحقول غير النشطة حسب نمط التشغيل
        optional_fields = [
            "product_type", "paper_type", "product_size", "print_direction",
            "coating_type", "coating_service", "supplier", "press",
            "description", "paper_supplier", "inner_paper_supplier", "paper_sheet_type", 
            "paper_origin", "paper_weight", "paper_price",
            "zinc_plates_count", "internal_page_count", "design_price",
            "custom_size_width", "custom_size_height",
            "open_size_width", "open_size_height",
            "order_type", "open_direction", "print_orientation", "cover_printing_type", "print_sides_mode",
            "digital_color_mode", "spot_colors_front", "spot_colors_back",
            "inner_printing_type", "inner_print_sides_mode", "inner_color_mode",
            "inner_spot_colors", "inner_color_pages", "inner_bw_pages",
            "inner_signatures_count", "binding_type", "spine_thickness",
            "inner_paper_type", "inner_paper_weight", "inner_coating_type",
            "ncr_sets_count", "ncr_book_capacity", "ncr_serial_start", "ncr_serial_end",
            "folder_pocket_type", "folder_card_slit", "folder_pocket_height",
            "design_service_type", "design_fee", "sales_commission_rate",
            "status", "profit_margin", "final_price", "sales_rep", "work_order", "currency"
        ]
        
        for field in optional_fields:
            if field in self.fields:
                self.fields[field].required = False

        # تأمين مرونة حقول الخيارات الاختيارية ضد أخطاء الاختيار غير المتاح
        for field_name, field in self.fields.items():
            if isinstance(field, forms.ChoiceField) and not isinstance(field, forms.ModelChoiceField):
                original_validate = field.validate
                def make_flexible_validate(f, orig_val):
                    def flexible_validate(value):
                        if value in f.empty_values:
                            if f.required:
                                raise ValidationError(f.error_messages['required'], code='required')
                            return
                        if not f.valid_value(value):
                            if not f.required:
                                return
                            orig_val(value)
                    return flexible_validate
                field.validate = make_flexible_validate(field, original_validate)

        # تعيين المستخدم المنشئ
        if user and not self.instance.pk:
            self.initial["created_by"] = user

    def clean(self):
        """التحقق من صحة البيانات المدخلة وتأمين قيم افتراضية متوافقة مع قاعدة البيانات"""
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

        # التحقق من وصف الطلب
        title = cleaned_data.get("title")
        if not title or not str(title).strip():
            self.add_error("title", _("يرجى إدخال وصف أو عنوان للطلب."))

        # استنتاج order_type تلقائياً من نوع المطبوع product_type
        order_type = cleaned_data.get("order_type")
        product_type = cleaned_data.get("product_type")
        if not order_type:
            if product_type and hasattr(product_type, 'base_archetype'):
                from ..models import OrderType
                archetype = product_type.base_archetype
                valid_types = [c[0] for c in OrderType.choices]
                if archetype in valid_types:
                    order_type = archetype
                elif archetype == 'catalog':
                    order_type = 'catalog'
                elif archetype == 'folder':
                    order_type = 'folder'
                elif archetype == 'invoice':
                    order_type = 'invoice'
                else:
                    order_type = 'flyer'
            else:
                order_type = 'flyer'
            cleaned_data["order_type"] = order_type

        # التحقق من جوانب الطباعة والألوان بطريقة ديناميكية مرنة
        cover_printing_type = cleaned_data.get("cover_printing_type") or "offset"
        print_sides = cleaned_data.get("print_sides_mode") or cleaned_data.get("print_sides") or "single"
        colors_front = cleaned_data.get("colors_front")
        colors_back = cleaned_data.get("colors_back")
        
        if cover_printing_type == 'none':
            cleaned_data["colors_front"] = 0
            cleaned_data["colors_back"] = 0
        else:
            if print_sides:
                sides_str = str(print_sides).lower()
                if 'double' in sides_str or 'work_sheet' in sides_str or 'وجهين' in sides_str or 'قلب' in sides_str:
                    if colors_front is None:
                        cleaned_data["colors_front"] = 4
                    if colors_back is None:
                        cleaned_data["colors_back"] = 4
                elif 'single' in sides_str or 'واحد' in sides_str:
                    if colors_front is None:
                        cleaned_data["colors_front"] = 4
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

        # قراءة صفحات الديجيتال البديلة للداخلي من POST إن وجدت
        if not cleaned_data.get("inner_color_pages"):
            dig_color = self.data.get("digital_inner_color_pages")
            if dig_color and str(dig_color).isdigit():
                cleaned_data["inner_color_pages"] = int(dig_color)
        if not cleaned_data.get("inner_bw_pages"):
            dig_bw = self.data.get("digital_inner_bw_pages")
            if dig_bw and str(dig_bw).isdigit():
                cleaned_data["inner_bw_pages"] = int(dig_bw)

        # قيم افتراضية آمنة للحقول الهيكلية لتفادي أخطاء NOT NULL في قاعدة البيانات
        defaults_map = {
            "open_direction": "right",
            "digital_color_mode": "4_0",
            "spot_colors_front": 0,
            "spot_colors_back": 0,
            "cover_printing_type": "offset",
            "print_sides_mode": "single",
            "inner_printing_type": "offset",
            "inner_print_sides_mode": "work_sheet",
            "inner_color_mode": "all_color",
            "inner_spot_colors": 0,
            "inner_color_pages": 0,
            "inner_bw_pages": 0,
            "inner_signatures_count": 0,
            "binding_type": "staple",
            "spine_thickness": Decimal("0.00"),
            "inner_paper_type": "couche",
            "inner_paper_weight": "135",
            "inner_coating_type": "none",
            "ncr_sets_count": 2,
            "ncr_book_capacity": 50,
            "ncr_serial_start": 1001,
            "ncr_serial_end": 1000,
            "folder_pocket_type": "same_sheet",
            "folder_card_slit": True,
            "folder_pocket_height": Decimal("7.50"),
            "design_service_type": "CUSTOMER_READY",
            "design_fee": Decimal("0.00"),
            "sales_commission_rate": Decimal("0.00"),
            "status": "draft",
        }
        for fname, default_val in defaults_map.items():
            if cleaned_data.get(fname) is None or cleaned_data.get(fname) == '':
                cleaned_data[fname] = default_val

        return cleaned_data

    def clean_binding_type(self):
        """التحقق من نوع التجليد ومواءمة القيم التوافقية القديمة"""
        btype = self.cleaned_data.get('binding_type')
        if not btype:
            return 'staple'
        legacy_map = {
            'glue': 'perfect_binding',
            'wire': 'wire_o',
            'spiral': 'wire_o',
            'sewing': 'sewing_binding',
            'none': 'staple',
        }
        return legacy_map.get(btype, btype)

    def clean_cover_printing_type(self):
        """التحقق من نوع الطباعة ومواءمة النمط الخاص ببنر الديجيتال"""
        c_type = self.cleaned_data.get('cover_printing_type')
        if c_type == 'digital_banner':
            return 'digital'
        return c_type or 'offset'

    def clean_product_type(self):
        """التحقق من نوع المطبوع ومواءمة التصنيف التشغيلي بمرونة كاملة"""
        pt = self.cleaned_data.get('product_type')
        if not pt:
            raw_val = self.data.get('product_type')
            if raw_val and isinstance(raw_val, str) and not raw_val.isdigit():
                pt = ProductType.objects.filter(base_archetype=raw_val).first()
        if not pt:
            order_type = self.cleaned_data.get('order_type') or self.data.get('order_type') or 'flyer'
            pt = ProductType.objects.filter(base_archetype=order_type).first()
        return pt

    def clean_product_size(self):
        """التحقق من مقاس المطبوع مع قبول المقاس المخصص كقيمة فارغة"""
        psize = self.cleaned_data.get('product_size')
        if psize == 'custom' or str(psize) == 'custom':
            return None
        return psize

    def clean_folder_pocket_height(self):
        """التحقق من ارتفاع الجيب وتفادي تجاوز السعة الرقمية"""
        val = self.cleaned_data.get('folder_pocket_height')
        if val is None or val == '':
            return Decimal('7.50')
        try:
            dec_val = Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            return min(Decimal('99.99'), max(Decimal('0.00'), dec_val))
        except Exception:
            return Decimal('7.50')

    def clean_sales_commission_rate(self):
        """التحقق من نسبة عمولة المبيعات وتفادي تجاوز السعة الرقمية"""
        val = self.cleaned_data.get('sales_commission_rate')
        if val is None or val == '':
            return Decimal('0.00')
        try:
            dec_val = Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            return min(Decimal('100.00'), max(Decimal('0.00'), dec_val))
        except Exception:
            return Decimal('0.00')

    def clean_spine_thickness(self):
        """التحقق من سمك الكعب وتفادي تجاوز السعة الرقمية"""
        val = self.cleaned_data.get('spine_thickness')
        if val is None or val == '':
            return Decimal('0.00')
        try:
            return Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception:
            return Decimal('0.00')

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

    def clean_profit_margin(self):
        """التحقق من هامش الربح وحماية قيد NOT NULL وتفادي تجاوز السعة الرقمية"""
        margin = self.cleaned_data.get('profit_margin')
        if margin is None or margin == '':
            if self.instance and self.instance.pk and self.instance.profit_margin is not None:
                return self.instance.profit_margin
            return Decimal('30.00')
        try:
            margin = Decimal(str(margin)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception:
            return Decimal('30.00')
            
        if margin < Decimal('0.00'):
            raise ValidationError(_("لا يمكن أن يكون هامش الربح سالباً"))
        if margin > Decimal('500.00'):
            raise ValidationError(_("أقصى هامش ربح مسموح به هو 500%"))
        return margin

    def save(self, commit=True):
        """حفظ الطلب داخل معاملة ذرية مع مزامنة الحقول التوافقية"""
        with transaction.atomic():
            instance = super().save(commit=False)
            
            # مزامنة final_price و sale_price بأمان في حال وجود الحقل
            if hasattr(instance, 'sale_price'):
                sale_price_val = getattr(instance, 'sale_price', None)
                if not instance.final_price and sale_price_val:
                    instance.final_price = sale_price_val
                elif not sale_price_val and instance.final_price:
                    setattr(instance, 'sale_price', instance.final_price)
                
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


