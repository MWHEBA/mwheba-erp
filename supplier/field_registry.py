"""
نظام تسجيل الحقول المركزي للخدمات المتخصصة
يحتوي على تعريف جميع حقول الخدمات وخصائصها
"""

# تسجيل مركزي لجميع حقول الخدمات
FIELD_REGISTRY = {
    "offset_printing": {
        # الحقول الأساسية
        "name": {
            "db_field": "name",
            "input_type": "text",
            "required": True,
            "readonly": True,
            "auto_generated": True,
        },
        "description": {
            "db_field": "description",
            "input_type": "textarea",
            "required": False,
        },
        "setup_cost": {
            "db_field": "setup_cost",
            "input_type": "number",
            "required": False,
            "validation": "positive_number",
            "step": "0.01",
        },
        "is_active": {
            "db_field": "is_active",
            "input_type": "checkbox",
            "required": False,
            "default": True,
        },
        # حقول تفاصيل الأوفست
        "machine_type": {
            "db_field": "offset_details.machine_type",
            "input_type": "select",
            "required": True,
            "choices_source": "machine_types",
        },
        "sheet_size": {
            "db_field": "offset_details.sheet_size",
            "input_type": "select",
            "required": True,
            "choices_source": "offset_sheet_sizes",
        },
        "max_colors": {
            "db_field": "offset_details.max_colors",
            "input_type": "number",
            "required": True,
            "min": 1,
            "max": 8,
            "default": 4,
        },
        "impression_cost_per_1000": {
            "db_field": "offset_details.impression_cost_per_1000",
            "input_type": "number",
            "required": True,
            "validation": "positive_number",
            "step": "0.01",
        },
        "special_impression_cost": {
            "db_field": "offset_details.special_impression_cost",
            "input_type": "number",
            "required": False,
            "validation": "positive_number",
            "step": "0.01",
        },
        "break_impression_cost": {
            "db_field": "offset_details.break_impression_cost",
            "input_type": "number",
            "required": False,
            "validation": "positive_number",
            "step": "0.01",
        },
    },
    "digital_printing": {
        # الحقول الأساسية
        "name": {
            "db_field": "name",
            "input_type": "text",
            "required": True,
            "readonly": True,
            "auto_generated": True,
        },
        "description": {
            "db_field": "description",
            "input_type": "textarea",
            "required": False,
        },
        "is_active": {
            "db_field": "is_active",
            "input_type": "checkbox",
            "required": False,
            "default": True,
        },
        # حقول تفاصيل الطباعة الديجيتال
        "machine_type": {
            "db_field": "digital_details.machine_type",
            "input_type": "select",
            "required": True,
            "choices_source": "digital_machine_types",
        },
        "paper_size": {
            "db_field": "digital_details.paper_size",
            "input_type": "select",
            "required": True,
            "choices_source": "digital_paper_sizes",
        },
    },
    "paper": {
        # الحقول الأساسية
        "name": {
            "db_field": "name",
            "input_type": "text",
            "required": True,
            "readonly": True,
            "auto_generated": True,
        },
        "description": {
            "db_field": "description",
            "input_type": "textarea",
            "required": False,
        },
        "is_active": {
            "db_field": "is_active",
            "input_type": "checkbox",
            "required": False,
            "default": True,
        },
        # حقول تفاصيل الورق
        "paper_type": {
            "db_field": "paper_details.paper_type",
            "input_type": "select",
            "required": True,
            "choices_source": "paper_types",
        },
        "gsm": {
            "db_field": "paper_details.gsm",
            "input_type": "select",
            "required": True,
            "choices_source": "paper_weights",
        },
        "sheet_size": {
            "db_field": "paper_details.sheet_size",
            "input_type": "select",
            "required": True,
            "choices_source": "sheet_sizes",
        },
        "custom_width": {
            "db_field": "paper_details.custom_width",
            "input_type": "number",
            "required": False,
            "step": "0.1",
            "validation": "positive_number",
        },
        "custom_height": {
            "db_field": "paper_details.custom_height",
            "input_type": "number",
            "required": False,
            "step": "0.1",
            "validation": "positive_number",
        },
        "country_of_origin": {
            "db_field": "paper_details.country_of_origin",
            "input_type": "select",
            "required": False,
            "choices_source": "paper_origins",
        },
        "brand": {
            "db_field": "paper_details.brand",
            "input_type": "text",
            "required": False,
        },
        "price_per_sheet": {
            "db_field": "paper_details.price_per_sheet",
            "input_type": "number",
            "required": True,
            "step": "0.01",
            "validation": "positive_number",
        },
    },
    "plates": {
        # الحقول الأساسية
        "name": {
            "db_field": "name",
            "input_type": "text",
            "required": True,
            "readonly": True,
            "auto_generated": True,
        },
        "is_active": {
            "db_field": "is_active",
            "input_type": "checkbox",
            "required": False,
            "default": True,
        },
        # حقول تفاصيل الألواح
        "plate_size": {
            "db_field": "plate_details.plate_size",
            "input_type": "select",
            "required": True,
            "choices_source": "plate_sizes",
        },
        "custom_width_cm": {
            "db_field": "plate_details.custom_width_cm",
            "input_type": "number",
            "required": False,
            "validation": "positive_number",
            "step": "0.1",
        },
        "custom_height_cm": {
            "db_field": "plate_details.custom_height_cm",
            "input_type": "number",
            "required": False,
            "validation": "positive_number",
            "step": "0.1",
        },
        "price_per_plate": {
            "db_field": "plate_details.price_per_plate",
            "input_type": "number",
            "required": True,
            "validation": "positive_number",
            "step": "0.01",
        },
        "set_price": {
            "db_field": "plate_details.set_price",
            "input_type": "number",
            "required": False,
            "validation": "positive_number",
            "step": "0.01",
        },
    },
    "coating": {
        # الحقول الأساسية
        "name": {
            "db_field": "name",
            "input_type": "text",
            "required": True,
            "readonly": True,
            "auto_generated": True,
        },
        "description": {
            "db_field": "description",
            "input_type": "textarea",
            "required": False,
        },
        "setup_cost": {
            "db_field": "setup_cost",
            "input_type": "number",
            "required": False,
            "validation": "positive_number",
            "step": "0.01",
        },
        "is_active": {
            "db_field": "is_active",
            "input_type": "checkbox",
            "required": False,
            "default": True,
        },
        # حقول تفاصيل التغطية
        "coating_type": {
            "db_field": "finishing_details.finishing_type",
            "input_type": "select",
            "required": True,
            "choices_source": "coating_types",
        },
        "calculation_method": {
            "db_field": "finishing_details.calculation_method",
            "input_type": "select",
            "required": True,
            "choices_source": "calculation_methods",
        },
        "base_price": {
            "db_field": "finishing_details.price_per_unit",
            "input_type": "number",
            "required": True,
            "validation": "positive_number",
            "step": "0.01",
        },
        "setup_time_minutes": {
            "db_field": "finishing_details.setup_time_minutes",
            "input_type": "number",
            "required": False,
            "validation": "positive_number",
            "default": 30,
        },
        "turnaround_time_hours": {
            "db_field": "finishing_details.turnaround_time_hours",
            "input_type": "number",
            "required": False,
            "validation": "positive_number",
            "default": 6,
        },
    },
}

# خيارات الحقول المختلفة
FIELD_CHOICES = {
    "machine_types": [
        ("heidelberg_sm52", "Heidelberg SM52"),
        ("heidelberg_sm74", "Heidelberg SM74"),
        ("heidelberg_sm102", "Heidelberg SM102"),
        ("komori_ls40", "Komori LS40"),
        ("komori_ls29", "Komori LS29"),
        ("ryobi_520", "Ryobi 520"),
        ("ryobi_750", "Ryobi 750"),
        ("other", "أخرى"),
    ],
    "sheet_sizes": [
        ("35x50", "35×50 سم"),
        ("50x70", "50×70 سم"),
        ("70x100", "70×100 سم"),
        ("custom", "مقاس مخصوص"),
    ],
    "digital_machine_types": [
        ("laser_mono", "ليزر أبيض وأسود"),
        ("laser_color", "ليزر ملون"),
        ("inkjet_large", "نفث حبر كبير"),
        ("inkjet_small", "نفث حبر صغير"),
        ("offset_digital", "أوفست ديجيتال"),
        ("production_printer", "طابعة إنتاج"),
        ("canon_imagepress_c165", "Canon imagePRESS C165"),
        ("xerox_versant", "Xerox Versant"),
        ("hp_indigo", "HP Indigo"),
        ("konica_bizhub", "Konica Bizhub"),
        ("ricoh_pro", "Ricoh Pro"),
    ],
    "paper_handling_types": [
        ("sheet_fed", "تغذية أوراق"),
        ("roll_fed", "تغذية لفائف"),
        ("both", "كلاهما"),
    ],
    "digital_paper_sizes": [
        ("a4", "A4 (21×29.7 سم)"),
        ("a3", "A3 (29×42 سم)"),
        ("a3_plus", "A3+ (32×45 سم)"),
        ("sra3", "SRA3 (32×45 سم)"),
        ("a1", "A1 (59.4×84.1 سم)"),
        ("a0", "A0 (84.1×118.9 سم)"),
        ("custom", "مقاس مخصص"),
    ],
    # خيارات الورق - سيتم جلبها من النظام الموحد
    "paper_types": [],  # سيتم ملؤها ديناميكياً من pricing app
    "paper_weights": [],  # سيتم ملؤها ديناميكياً من pricing app
    "paper_origins": [],  # سيتم ملؤها ديناميكياً من pricing app
    "plate_sizes": [],  # سيتم ملؤها ديناميكياً من pricing app
    
    # خيارات التغطية
    "coating_types": [],  # سيتم ملؤها ديناميكياً من CoatingType model
    "calculation_methods": [
        ("per_piece", "بالقطعة"),
        ("per_thousand", "بالألف"),
        ("per_square_meter", "بالمتر المربع"),
        ("per_sheet", "بالفرخ"),
        ("per_hour", "بالساعة"),
    ]
}


def get_field_config(service_type, field_name):
    """
    جلب تكوين حقل معين
    """
    if service_type not in FIELD_REGISTRY:
        return None

    return FIELD_REGISTRY[service_type].get(field_name)


def get_service_fields(service_type):
    """
    جلب جميع حقول نوع خدمة معين
    """
    return FIELD_REGISTRY.get(service_type, {})


def get_field_choices(choices_source):
    """
    جلب خيارات حقل معين
    """
    # للورق، استخدم النظام الموحد
    if choices_source in ["paper_types", "paper_weights", "paper_origins", "sheet_sizes"]:
        try:
            from .forms.dynamic_forms import ServiceFormFactory
            unified_choices = ServiceFormFactory.get_unified_paper_choices()
            return unified_choices.get(choices_source, [])
        except ImportError:
            pass
    
    # للأوفست، استخدم النظام الموحد
    elif choices_source in ["machine_types", "offset_sheet_sizes"]:
        try:
            from .forms.dynamic_forms import ServiceFormFactory
            unified_choices = ServiceFormFactory.get_unified_offset_choices()
            if choices_source == "machine_types":
                return unified_choices.get("machine_types", [])
            elif choices_source == "offset_sheet_sizes":
                return unified_choices.get("sheet_sizes", [])
        except ImportError:
            pass
    
    # للزنكات، استخدم النظام الموحد
    elif choices_source == "plate_sizes":
        try:
            from .forms.dynamic_forms import ServiceFormFactory
            unified_choices = ServiceFormFactory.get_unified_ctp_choices()
            return unified_choices.get("plate_sizes", [])
        except ImportError:
            pass
    
    # للتغطية، جلب من CoatingType model
    elif choices_source == "coating_types":
        try:
            from printing_pricing.models.settings_models import CoatingType
            coating_types = CoatingType.objects.filter(is_active=True).order_by('name')
            return [(ct.id, ct.name) for ct in coating_types]
        except ImportError:
            pass
    
    return FIELD_CHOICES.get(choices_source, [])


def get_db_field_path(service_type, field_name):
    """
    جلب مسار الحقل في قاعدة البيانات
    """
    field_config = get_field_config(service_type, field_name)
    if field_config:
        return field_config.get("db_field")
    return None
