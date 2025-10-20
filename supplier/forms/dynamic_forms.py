from django import forms
from django.utils.translation import gettext_lazy as _
from decimal import Decimal

from ..models import (
    SpecializedService,
    SupplierType,
    ServicePriceTier,
    PaperServiceDetails,
    DigitalPrintingDetails,
    FinishingServiceDetails,
    OffsetPrintingDetails,
    PlateServiceDetails,
    OutdoorPrintingDetails,
    LaserServiceDetails,
    VIPGiftDetails,
)


class ServiceFormFactory:
    """مصنع النماذج الديناميكية حسب نوع الخدمة"""

    @staticmethod
    def get_form_for_category(category_code, *args, **kwargs):
        """إرجاع النموذج المناسب حسب نوع الخدمة"""
        form_mapping = {
            "paper": PaperServiceForm,
            "offset_printing": OffsetPrintingForm,
            "digital_printing": DigitalPrintingForm,
            "finishing": FinishingServiceForm,
            "plates": PlateServiceForm,
            "outdoor": OutdoorPrintingForm,
            "laser": LaserServiceForm,
            "vip_gifts": VIPGiftForm,
            "packaging": GenericServiceForm,
            "other": GenericServiceForm,
        }

        form_class = form_mapping.get(category_code, GenericServiceForm)
        return form_class(*args, **kwargs)

    @staticmethod
    def convert_legacy_sheet_size(old_value):
        """تحويل قيم مقاسات الورق القديمة للجديدة"""
        legacy_mapping = {
            "full_70x100": "70.00x100.00",
            "half_50x70": "50.00x70.00", 
            "quarter_35x50": "35.00x50.00",
            "a3": "29.70x42.00",
            "a4": "21.00x29.70",
            "custom": "custom"
        }
        return legacy_mapping.get(old_value, old_value)

    @staticmethod
    def convert_legacy_paper_type(old_value):
        """تحويل قيم أنواع الورق القديمة للجديدة"""
        try:
            from printing_pricing.models.settings_models import PaperType
            # البحث عن نوع الورق بالاسم
            paper_type = PaperType.objects.filter(name__icontains=old_value, is_active=True).first()
            if paper_type:
                return paper_type.name
        except ImportError:
            pass
        
        # تطبيع القيم القديمة المعروفة
        type_mapping = {
            'coated': 'كوشيه',
            'offset': 'طبع',
        }
        return type_mapping.get(old_value, old_value)

    @staticmethod
    def normalize_legacy_data(paper_type=None, sheet_size=None, country_of_origin=None):
        """تطبيع البيانات القديمة لتتطابق مع المرجعية"""
        normalized = {}
        
        # تطبيع نوع الورق
        if paper_type:
            normalized['paper_type'] = ServiceFormFactory.convert_legacy_paper_type(paper_type)
        
        # تطبيع مقاس الورق
        if sheet_size:
            normalized['sheet_size'] = ServiceFormFactory.convert_legacy_sheet_size(sheet_size)
        
        # تطبيع منشأ الورق (يبقى كما هو لأنه يستخدم الكود)
        if country_of_origin:
            normalized['country_of_origin'] = country_of_origin
        
        return normalized

    @staticmethod
    def validate_data(paper_type=None, gsm=None, sheet_size=None, country_of_origin=None):
        """التحقق من صحة البيانات مقابل المرجعية"""
        errors = []
        
        try:
            from printing_pricing.models.settings_models import PaperType, PaperWeight, PaperOrigin, PaperSize
            
            # التحقق من نوع الورق
            if paper_type:
                valid_types = [pt.name for pt in PaperType.objects.filter(is_active=True)]
                if paper_type not in valid_types:
                    errors.append(f"نوع الورق '{paper_type}' غير موجود في المرجعية")
            
            # التحقق من الوزن
            if gsm:
                valid_weights = [pw.gsm for pw in PaperWeight.objects.filter(is_active=True)]
                if gsm not in valid_weights:
                    errors.append(f"وزن الورق '{gsm}' غير موجود في المرجعية")
            
            # التحقق من المقاس
            if sheet_size and sheet_size != 'custom':
                valid_sizes = [f"{ps.width}x{ps.height}" for ps in PaperSize.objects.filter(is_active=True)]
                if sheet_size not in valid_sizes:
                    errors.append(f"مقاس الورق '{sheet_size}' غير موجود في المرجعية")
            
            # التحقق من المنشأ
            if country_of_origin:
                valid_origins = [po.code for po in PaperOrigin.objects.filter(is_active=True)]
                if country_of_origin not in valid_origins:
                    errors.append(f"منشأ الورق '{country_of_origin}' غير موجود في المرجعية")
        
        except ImportError:
            errors.append("لا يمكن الوصول لنماذج المرجعية")
        
        return errors

    @staticmethod
    def get_unified_paper_choices():
        """جلب خيارات الورق الموحدة من المرجعية الوحيدة"""
        try:
            from printing_pricing.models.settings_models import PaperType, PaperWeight, PaperOrigin, PaperSize

            return {
                "paper_types": [
                    (pt.name, pt.name) 
                    for pt in PaperType.objects.filter(is_active=True).order_by("name")
                ],
                "paper_weights": [
                    (pw.gsm, f"{pw.name} ({pw.gsm} جم)") 
                    for pw in PaperWeight.objects.filter(is_active=True).order_by("gsm")
                ],
                "sheet_sizes": [
                    (f"{ps.width}x{ps.height}", str(ps)) 
                    for ps in PaperSize.objects.filter(is_active=True).order_by("name")
                ],
                "paper_origins": [
                    (po.code, f"{po.name} ({po.code})") 
                    for po in PaperOrigin.objects.filter(is_active=True).order_by("name")
                ]
            }
        except ImportError:
            # في حالة عدم وجود النماذج، استخدم خيارات افتراضية
            return {
                "paper_types": [("كوشيه", "كوشيه"), ("طبع", "طبع")],
                "paper_weights": [(80, "80 جرام"), (120, "120 جرام")],
                "sheet_sizes": [("70x100", "فرخ كامل"), ("50x70", "نصف فرخ")],
                "paper_origins": [("EG", "مصر"), ("CN", "الصين")]
            }

    @staticmethod
    def get_unified_offset_choices():
        """جلب خيارات الأوفست الموحدة من المرجعية الوحيدة"""
        try:
            from printing_pricing.models.settings_models import OffsetMachineType, OffsetSheetSize

            return {
                "machine_types": [
                    (mt.code, str(mt)) 
                    for mt in OffsetMachineType.objects.filter(is_active=True).order_by("manufacturer", "name")
                ],
                "sheet_sizes": [
                    (ss.code, str(ss)) 
                    for ss in OffsetSheetSize.objects.filter(is_active=True).order_by("width_cm", "height_cm")
                ]
            }
        except ImportError:
            # في حالة عدم وجود النماذج، استخدم خيارات افتراضية
            return {
                "machine_types": [
                    ("sm52", "هايدلبرج - SM52"),
                    ("gto52", "هايدلبرج - GTO52")
                ],
                "sheet_sizes": [
                    ("quarter_sheet", "ربع فرخ (35×50 سم)"),
                    ("half_sheet", "نصف فرخ (50×70 سم)"),
                    ("full_sheet", "فرخ كامل (70×100 سم)")
                ]
            }

    @staticmethod
    def convert_legacy_machine_type(old_value):
        """تحويل أنواع ماكينات الأوفست القديمة للجديدة"""
        legacy_mapping = {
            'heidelberg_sm52': 'sm52',
            'heidelberg_sm74': 'sm74',
            'heidelberg_sm102': 'sm102',
            'komori_ls40': 'ls40',
            'komori_ls29': 'ls29',
            'ryobi_524': 'ryobi_524',
            'ryobi_520': 'ryobi_520',
            'ryobi_750': 'ryobi_750',
            'gto_52': 'gto52',
            'other': 'other'
        }
        return legacy_mapping.get(old_value, old_value)

    @staticmethod
    def convert_legacy_offset_sheet_size(old_value):
        """تحويل مقاسات الأوفست القديمة للجديدة"""
        legacy_mapping = {
            "35x50": "quarter_sheet",
            "50x70": "half_sheet", 
            "70x100": "full_sheet",
            "custom": "custom"
        }
        return legacy_mapping.get(old_value, old_value)

    @staticmethod
    def normalize_legacy_offset_data(machine_type=None, sheet_size=None):
        """تطبيع بيانات الأوفست القديمة لتتطابق مع المرجعية"""
        normalized = {}
        
        # تطبيع نوع الماكينة
        if machine_type:
            normalized['machine_type'] = ServiceFormFactory.convert_legacy_machine_type(machine_type)
        
        # تطبيع مقاس الماكينة
        if sheet_size:
            normalized['sheet_size'] = ServiceFormFactory.convert_legacy_offset_sheet_size(sheet_size)
        
        return normalized

    @staticmethod
    def validate_offset_data(machine_type=None, sheet_size=None):
        """التحقق من صحة بيانات الأوفست مقابل المرجعية"""
        errors = []
        
        try:
            from printing_pricing.models.settings_models import OffsetMachineType, OffsetSheetSize
            
            # التحقق من نوع الماكينة
            if machine_type:
                if not OffsetMachineType.objects.filter(code=machine_type, is_active=True).exists():
                    errors.append(f"نوع الماكينة '{machine_type}' غير موجود في المرجعية")
            
            # التحقق من مقاس الماكينة
            if sheet_size:
                if not OffsetSheetSize.objects.filter(code=sheet_size, is_active=True).exists():
                    errors.append(f"مقاس الماكينة '{sheet_size}' غير موجود في المرجعية")
                    
        except ImportError:
            # في حالة عدم وجود النماذج، لا نتحقق
            pass
        
        return errors

    @staticmethod
    def get_unified_ctp_choices():
        """جلب خيارات الزنكات CTP الموحدة من المرجعية الوحيدة"""
        try:
            from printing_pricing.models.settings_models import PlateSize

            return {
                "plate_sizes": [
                    (f"{ps.width}x{ps.height}", str(ps)) 
                    for ps in PlateSize.objects.filter(is_active=True).order_by("name")
                ]
            }
        except ImportError:
            # في حالة عدم وجود النماذج، استخدم خيارات افتراضية
            return {
                "plate_sizes": [
                    ("35.00x50.00", "ربع فرخ (35×50 سم)"),
                    ("50.00x70.00", "نصف فرخ (50×70 سم)"),
                    ("70.00x100.00", "فرخ كامل (70×100 سم)")
                ]
            }

    @staticmethod
    def convert_legacy_plate_size(old_value):
        """تحويل مقاسات الزنكات القديمة للجديدة"""
        legacy_mapping = {
            "quarter_sheet": "35.00x50.00",
            "half_sheet": "50.00x70.00", 
            "full_sheet": "70.00x100.00",
            "35x50": "35.00x50.00",
            "50x70": "50.00x70.00",
            "70x100": "70.00x100.00",
            "custom": "custom"
        }
        return legacy_mapping.get(old_value, old_value)

    @staticmethod
    def normalize_legacy_ctp_data(plate_size=None):
        """تطبيع بيانات الزنكات القديمة لتتطابق مع المرجعية"""
        normalized = {}
        
        # تطبيع مقاس الزنك
        if plate_size:
            normalized['plate_size'] = ServiceFormFactory.convert_legacy_plate_size(plate_size)
        
        return normalized

    @staticmethod
    def validate_ctp_data(plate_size=None):
        """التحقق من صحة بيانات الزنكات مقابل المرجعية"""
        errors = []
        
        try:
            from printing_pricing.models.settings_models import PlateSize
            
            # التحقق من مقاس الزنك
            if plate_size and plate_size != 'custom':
                valid_sizes = [f"{ps.width}x{ps.height}" for ps in PlateSize.objects.filter(is_active=True)]
                if plate_size not in valid_sizes:
                    errors.append(f"مقاس الزنك '{plate_size}' غير موجود في المرجعية")
                    
        except ImportError:
            # في حالة عدم وجود النماذج، لا نتحقق
            pass
        
        return errors

    @staticmethod
    def get_form_choices_for_category(category_code):
        """جلب خيارات النموذج لتصنيف معين"""

        # للورق، استخدم النظام الموحد
        if category_code == "paper":
            return ServiceFormFactory.get_unified_paper_choices()

        # للطباعة الأوفست، استخدم النظام الموحد
        elif category_code == "offset_printing":
            return ServiceFormFactory.get_unified_offset_choices()

        # للزنكات CTP، استخدم النظام الموحد
        elif category_code == "plates":
            return ServiceFormFactory.get_unified_ctp_choices()

        # للطباعة الديجيتال، استخدم البيانات من الإعدادات
        if category_code == "digital_printing":
            try:
                from printing_pricing.models.settings_models import DigitalMachineType, DigitalSheetSize

                # أنواع الماكينات من الإعدادات
                machine_types = DigitalMachineType.objects.filter(
                    is_active=True
                ).order_by("manufacturer", "name")
                machine_choices = [
                    (machine.code, str(machine))  # استخدام __str__ method من النموذج
                    for machine in machine_types
                ]

                # مقاسات الماكينات من الإعدادات
                sheet_sizes = DigitalSheetSize.objects.filter(is_active=True).order_by(
                    "width_cm", "height_cm"
                )
                size_choices = [
                    (
                        size.code,
                        f"{size.name} ({int(size.width_cm)}×{int(size.height_cm)})",
                    )
                    for size in sheet_sizes
                ]

                return {
                    "machine_types": machine_choices,
                    "paper_sizes": size_choices,  # تغيير الاسم ليطابق template
                }
            except ImportError:
                # في حالة عدم وجود النماذج، استخدم الخيارات الافتراضية
                pass


        # الخيارات الافتراضية للتصنيفات الأخرى
        choices_mapping = {
            "offset_printing": {
                "machine_types": OffsetPrintingDetails.MACHINE_TYPE_CHOICES,
                "sheet_sizes": OffsetPrintingDetails.SHEET_SIZE_CHOICES,
            },
            "digital_printing": {
                "machine_types": DigitalPrintingDetails.MACHINE_TYPE_CHOICES,
                "paper_sizes": DigitalPrintingDetails.PAPER_SIZE_CHOICES,
            },
            "finishing": {
                "finishing_types": FinishingServiceDetails.FINISHING_TYPE_CHOICES,
                "calculation_methods": FinishingServiceDetails.CALCULATION_METHOD_CHOICES,
            },
            # تم إزالة plates - يستخدم النظام الموحد الآن
            "outdoor": {
                "material_types": OutdoorPrintingDetails.MATERIAL_TYPE_CHOICES,
                "printing_types": OutdoorPrintingDetails.PRINTING_TYPE_CHOICES,
            },
            "laser": {
                "laser_types": LaserServiceDetails.LASER_TYPE_CHOICES,
                "service_types": LaserServiceDetails.SERVICE_TYPE_CHOICES,
                "material_types": LaserServiceDetails.MATERIAL_TYPE_CHOICES,
            },
            "vip_gifts": {
                "gift_categories": VIPGiftDetails.GIFT_CATEGORY_CHOICES,
                "customization_types": VIPGiftDetails.CUSTOMIZATION_TYPE_CHOICES,
            },
        }

        return choices_mapping.get(category_code, {})


class BaseServiceForm(forms.Form):
    """النموذج الأساسي لجميع الخدمات"""

    # الحقول الأساسية المشتركة
    name = forms.CharField(
        label=_("اسم الخدمة"),
        max_length=255,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "أدخل اسم الخدمة"}
        ),
    )

    description = forms.CharField(
        label=_("وصف الخدمة"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "وصف تفصيلي للخدمة",
            }
        ),
    )

    is_active = forms.BooleanField(
        label=_("نشط"),
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class PaperServiceForm(BaseServiceForm):
    """نموذج خدمات الورق"""

    paper_type = forms.ChoiceField(
        label=_("نوع الورق"),
        choices=[],  # سيتم تحديثها ديناميكياً
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    gsm = forms.ChoiceField(
        label=_("وزن الورق (جرام)"),
        choices=[],  # سيتم تحديثها ديناميكياً
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    sheet_size = forms.ChoiceField(
        label=_("مقاس الفرخ"),
        choices=[],  # سيتم تحديثها ديناميكياً
        widget=forms.Select(
            attrs={"class": "form-select", "onchange": "toggleCustomSize(this)"}
        ),
    )

    custom_width = forms.DecimalField(
        label=_("العرض المخصص (سم)"),
        max_digits=8,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
    )

    custom_height = forms.DecimalField(
        label=_("الارتفاع المخصص (سم)"),
        max_digits=8,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
    )

    country_of_origin = forms.ChoiceField(
        label=_("بلد المنشأ"),
        choices=[],  # سيتم تحديثها ديناميكياً
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    brand = forms.CharField(
        label=_("الماركة"),
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "مثال: UPM"}
        ),
    )

    price_per_sheet = forms.DecimalField(
        label=_("سعر الفرخ"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # استخدام النظام الموحد لجلب جميع الخيارات من المرجعية الوحيدة
        unified_choices = ServiceFormFactory.get_unified_paper_choices()
        
        # تحديث خيارات أنواع الورق
        self.fields["paper_type"].choices = [("", "-- اختر نوع الورق --")] + unified_choices["paper_types"]
        
        # تحديث خيارات أوزان الورق
        self.fields["gsm"].choices = [("", "-- اختر وزن الورق --")] + unified_choices["paper_weights"]
        
        # تحديث خيارات مقاسات الورق مع إضافة المقاس المخصص
        size_choices = [("", "-- اختر مقاس الفرخ --")] + unified_choices["sheet_sizes"]
        size_choices.append(("custom", "مقاس مخصص"))
        self.fields["sheet_size"].choices = size_choices
        
        # تحديث خيارات منشأ الورق
        self.fields["country_of_origin"].choices = [("", "-- اختر المنشأ --")] + unified_choices["paper_origins"]


class OffsetPrintingForm(BaseServiceForm):
    """نموذج خدمات الطباعة الأوفست"""

    machine_type = forms.ChoiceField(
        label=_("نوع الماكينة"),
        choices=[],  # سيتم تحديثها ديناميكياً
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    sheet_size = forms.ChoiceField(
        label=_("مقاس الماكينة"),
        choices=[],  # سيتم تحديثها ديناميكياً
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # استخدام النظام الموحد لجلب خيارات الأوفست
        unified_choices = ServiceFormFactory.get_unified_offset_choices()
        
        # تحديث خيارات أنواع الماكينات
        self.fields["machine_type"].choices = [("", "-- اختر نوع الماكينة --")] + unified_choices["machine_types"]
        
        # تحديث خيارات مقاسات الماكينات  
        self.fields["sheet_size"].choices = [("", "-- اختر مقاس الماكينة --")] + unified_choices["sheet_sizes"]

    max_colors = forms.IntegerField(
        label=_("عدد الألوان"),
        initial=4,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": "1", "max": "8"}
        ),
    )

    impression_cost_per_1000 = forms.DecimalField(
        label=_("سعر التراج (لكل 1000)"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    special_impression_cost = forms.DecimalField(
        label=_("سعر التراج مخصوص"),
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    break_impression_cost = forms.DecimalField(
        label=_("سعر كسر التراج"),
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )


class DigitalPrintingForm(BaseServiceForm):
    """نموذج خدمات الطباعة الديجيتال مبسط"""

    machine_type = forms.ChoiceField(
        label=_("نوع الماكينة"),
        choices=[],  # سيتم تحديثها ديناميكياً
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    paper_size = forms.ChoiceField(
        label=_("مقاس الماكينة"),
        choices=[],  # سيتم تحديثها ديناميكياً
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # تحديث خيارات أنواع الماكينات من الإعدادات
        try:
            from printing_pricing.models.settings_models import DigitalMachineType

            machine_types = DigitalMachineType.objects.filter(is_active=True).order_by(
                "manufacturer", "name"
            )
            self.fields["machine_type"].choices = [
                (machine.code, str(machine))  # استخدام __str__ method من النموذج
                for machine in machine_types
            ]
        except ImportError:
            # في حالة عدم وجود النموذج، استخدم الخيارات الافتراضية
            self.fields[
                "machine_type"
            ].choices = DigitalPrintingDetails.MACHINE_TYPE_CHOICES

        # تحديث خيارات مقاسات الماكينات من الإعدادات
        try:
            from printing_pricing.models.settings_models import DigitalSheetSize

            sheet_sizes = DigitalSheetSize.objects.filter(is_active=True).order_by(
                "width_cm", "height_cm"
            )
            self.fields["paper_size"].choices = [
                (size.code, f"{size.name} ({int(size.width_cm)}×{int(size.height_cm)})")
                for size in sheet_sizes
            ]
        except ImportError:
            # في حالة عدم وجود النموذج، استخدم الخيارات الافتراضية
            self.fields[
                "paper_size"
            ].choices = DigitalPrintingDetails.PAPER_SIZE_CHOICES

    # الشرائح السعرية إجبارية للطباعة الديجيتال
    has_price_tiers = forms.BooleanField(
        label=_("استخدام شرائح سعرية"),
        initial=True,
        required=True,
        widget=forms.HiddenInput(),  # مخفي لأنه إجباري
    )


class FinishingServiceForm(BaseServiceForm):
    """نموذج خدمات الطباعة (التشطيب)"""

    finishing_type = forms.ChoiceField(
        label=_("نوع الخدمة"),
        choices=FinishingServiceDetails.FINISHING_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    calculation_method = forms.ChoiceField(
        label=_("طريقة الحساب"),
        choices=FinishingServiceDetails.CALCULATION_METHOD_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    price_per_unit = forms.DecimalField(
        label=_("سعر الوحدة"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    setup_time_minutes = forms.IntegerField(
        label=_("وقت التجهيز (دقائق)"),
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
    )

    turnaround_time_hours = forms.IntegerField(
        label=_("وقت التسليم (ساعات)"),
        initial=24,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
    )


class PlateServiceForm(BaseServiceForm):
    """نموذج خدمات الزنكات"""

    plate_size = forms.ChoiceField(
        label=_("مقاس الزنك"),
        choices=[],  # سيتم تحديثها ديناميكياً
        widget=forms.Select(
            attrs={"class": "form-select", "onchange": "toggleCustomSize(this)"}
        ),
    )

    custom_width_cm = forms.DecimalField(
        label=_("العرض المخصص (سم)"),
        max_digits=8,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
    )

    custom_height_cm = forms.DecimalField(
        label=_("الارتفاع المخصص (سم)"),
        max_digits=8,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
    )

    price_per_plate = forms.DecimalField(
        label=_("سعر الزنك الواحد"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    set_price = forms.DecimalField(
        label=_("سعر الطقم (4 زنكات)"),
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # استخدام النظام الموحد لجلب خيارات الزنكات
        unified_choices = ServiceFormFactory.get_unified_ctp_choices()
        
        # تحديث خيارات مقاسات الزنكات مع إضافة المقاس المخصص
        size_choices = [("", "-- اختر مقاس الزنك --")] + unified_choices["plate_sizes"]
        size_choices.append(("custom", "مقاس مخصص"))
        self.fields["plate_size"].choices = size_choices


class OutdoorPrintingForm(BaseServiceForm):
    """نموذج خدمات الأوت دور"""

    material_type = forms.ChoiceField(
        label=_("نوع المادة"),
        choices=OutdoorPrintingDetails.MATERIAL_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    printing_type = forms.ChoiceField(
        label=_("نوع الطباعة"),
        choices=OutdoorPrintingDetails.PRINTING_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    max_width_cm = forms.DecimalField(
        label=_("أقصى عرض (سم)"),
        max_digits=8,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
    )

    price_per_sqm = forms.DecimalField(
        label=_("سعر المتر المربع"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    min_order_sqm = forms.DecimalField(
        label=_("الحد الأدنى (متر مربع)"),
        max_digits=8,
        decimal_places=2,
        initial=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
    )


class LaserServiceForm(BaseServiceForm):
    """نموذج خدمات الليزر"""

    laser_type = forms.ChoiceField(
        label=_("نوع الليزر"),
        choices=LaserServiceDetails.LASER_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    service_type = forms.ChoiceField(
        label=_("نوع الخدمة"),
        choices=LaserServiceDetails.SERVICE_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    material_type = forms.ChoiceField(
        label=_("نوع المادة"),
        choices=LaserServiceDetails.MATERIAL_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    max_width_cm = forms.DecimalField(
        label=_("أقصى عرض (سم)"),
        max_digits=8,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
    )

    max_height_cm = forms.DecimalField(
        label=_("أقصى ارتفاع (سم)"),
        max_digits=8,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
    )

    price_per_minute = forms.DecimalField(
        label=_("سعر الدقيقة"),
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    price_per_piece = forms.DecimalField(
        label=_("سعر القطعة"),
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )


class VIPGiftForm(BaseServiceForm):
    """نموذج خدمات الهدايا المميزة"""

    gift_category = forms.ChoiceField(
        label=_("فئة الهدية"),
        choices=VIPGiftDetails.GIFT_CATEGORY_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    customization_type = forms.ChoiceField(
        label=_("نوع التخصيص"),
        choices=VIPGiftDetails.CUSTOMIZATION_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    product_name = forms.CharField(
        label=_("اسم المنتج"),
        max_length=200,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "مثال: قلم ذهبي محفور"}
        ),
    )

    brand = forms.CharField(
        label=_("الماركة"),
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "مثال: Parker"}
        ),
    )

    customization_cost = forms.DecimalField(
        label=_("تكلفة التخصيص"),
        max_digits=10,
        decimal_places=2,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    packaging_cost = forms.DecimalField(
        label=_("تكلفة التغطية"),
        max_digits=10,
        decimal_places=2,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )


class GenericServiceForm(BaseServiceForm):
    """نموذج عام للخدمات الأخرى"""

    service_details = forms.CharField(
        label=_("تفاصيل الخدمة"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "أدخل تفاصيل الخدمة",
            }
        ),
    )

    price_per_unit = forms.DecimalField(
        label=_("سعر الوحدة"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    unit_type = forms.CharField(
        label=_("نوع الوحدة"),
        max_length=50,
        initial="قطعة",
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "مثال: قطعة، متر، ساعة"}
        ),
    )


# نموذج الشرائح السعرية
class PriceTierForm(forms.ModelForm):
    """نموذج الشريحة السعرية"""

    class Meta:
        model = ServicePriceTier
        fields = [
            "tier_name",
            "min_quantity",
            "max_quantity",
            "price_per_unit",
            "discount_percentage",
        ]
        widgets = {
            "tier_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "مثال: 1-100"}
            ),
            "min_quantity": forms.NumberInput(
                attrs={"class": "form-control", "min": "1"}
            ),
            "max_quantity": forms.NumberInput(
                attrs={"class": "form-control", "min": "1"}
            ),
            "price_per_unit": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
            "discount_percentage": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "max": "100"}
            ),
        }
