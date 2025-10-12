"""
نظام تسجيل الحقول المركزي للخدمات المتخصصة
يحتوي على تعريف جميع حقول الخدمات وخصائصها
"""

# تسجيل مركزي لجميع حقول الخدمات
FIELD_REGISTRY = {
    'offset_printing': {
        # الحقول الأساسية
        'name': {
            'db_field': 'name',
            'input_type': 'text',
            'required': True,
            'readonly': True,
            'auto_generated': True
        },
        'description': {
            'db_field': 'description',
            'input_type': 'textarea',
            'required': False
        },
        'setup_cost': {
            'db_field': 'setup_cost',
            'input_type': 'number',
            'required': False,
            'validation': 'positive_number',
            'step': '0.01'
        },
        'is_active': {
            'db_field': 'is_active',
            'input_type': 'checkbox',
            'required': False,
            'default': True
        },
        
        # حقول تفاصيل الأوفست
        'machine_type': {
            'db_field': 'offset_details.machine_type',
            'input_type': 'select',
            'required': True,
            'choices_source': 'machine_types'
        },
        'sheet_size': {
            'db_field': 'offset_details.sheet_size',
            'input_type': 'select',
            'required': True,
            'choices_source': 'sheet_sizes'
        },
        'max_colors': {
            'db_field': 'offset_details.max_colors',
            'input_type': 'number',
            'required': True,
            'min': 1,
            'max': 8,
            'default': 4
        },
        'impression_cost_per_1000': {
            'db_field': 'offset_details.impression_cost_per_1000',
            'input_type': 'number',
            'required': True,
            'validation': 'positive_number',
            'step': '0.01'
        },
        'special_impression_cost': {
            'db_field': 'offset_details.special_impression_cost',
            'input_type': 'number',
            'required': False,
            'validation': 'positive_number',
            'step': '0.01'
        },
        'break_impression_cost': {
            'db_field': 'offset_details.break_impression_cost',
            'input_type': 'number',
            'required': False,
            'validation': 'positive_number',
            'step': '0.01'
        }
    },
    
    'digital_printing': {
        # الحقول الأساسية
        'name': {
            'db_field': 'name',
            'input_type': 'text',
            'required': True,
            'readonly': True,
            'auto_generated': True
        },
        'description': {
            'db_field': 'description',
            'input_type': 'textarea',
            'required': False
        },
        'is_active': {
            'db_field': 'is_active',
            'input_type': 'checkbox',
            'required': False,
            'default': True
        },
        
        # حقول تفاصيل الطباعة الديجيتال
        'machine_type': {
            'db_field': 'digital_details.machine_type',
            'input_type': 'select',
            'required': True,
            'choices_source': 'digital_machine_types'
        },
        'paper_size': {
            'db_field': 'digital_details.paper_size',
            'input_type': 'select',
            'required': True,
            'choices_source': 'digital_paper_sizes'
        },
    },
    
    'plates': {
        # الحقول الأساسية
        'name': {
            'db_field': 'name',
            'input_type': 'text',
            'required': True,
            'readonly': True,
            'auto_generated': True
        },
        'is_active': {
            'db_field': 'is_active',
            'input_type': 'checkbox',
            'required': False,
            'default': True
        },
        
        # حقول تفاصيل الألواح
        'plate_size': {
            'db_field': 'plate_details.plate_size',
            'input_type': 'select',
            'required': True,
            'choices_source': 'plate_sizes'
        },
        'custom_width_cm': {
            'db_field': 'plate_details.custom_width_cm',
            'input_type': 'number',
            'required': False,
            'validation': 'positive_number',
            'step': '0.1'
        },
        'custom_height_cm': {
            'db_field': 'plate_details.custom_height_cm',
            'input_type': 'number',
            'required': False,
            'validation': 'positive_number',
            'step': '0.1'
        },
        'price_per_plate': {
            'db_field': 'plate_details.price_per_plate',
            'input_type': 'number',
            'required': True,
            'validation': 'positive_number',
            'step': '0.01'
        },
        'set_price': {
            'db_field': 'plate_details.set_price',
            'input_type': 'number',
            'required': False,
            'validation': 'positive_number',
            'step': '0.01'
        }
    }
}

# خيارات الحقول المختلفة
FIELD_CHOICES = {
    'machine_types': [
        ('heidelberg_sm52', 'Heidelberg SM52'),
        ('heidelberg_sm74', 'Heidelberg SM74'),
        ('heidelberg_sm102', 'Heidelberg SM102'),
        ('komori_ls40', 'Komori LS40'),
        ('komori_ls29', 'Komori LS29'),
        ('ryobi_520', 'Ryobi 520'),
        ('ryobi_750', 'Ryobi 750'),
        ('other', 'أخرى')
    ],
    
    'sheet_sizes': [
        ('35x50', '35×50 سم'),
        ('50x70', '50×70 سم'),
        ('70x100', '70×100 سم'),
        ('custom', 'مقاس مخصوص')
    ],
    
    'digital_machine_types': [
        ('laser_mono', 'ليزر أبيض وأسود'),
        ('laser_color', 'ليزر ملون'),
        ('inkjet_large', 'نفث حبر كبير'),
        ('inkjet_small', 'نفث حبر صغير'),
        ('offset_digital', 'أوفست ديجيتال'),
        ('production_printer', 'طابعة إنتاج'),
        ('canon_imagepress_c165', 'Canon imagePRESS C165'),
        ('xerox_versant', 'Xerox Versant'),
        ('hp_indigo', 'HP Indigo'),
        ('konica_bizhub', 'Konica Bizhub'),
        ('ricoh_pro', 'Ricoh Pro')
    ],
    
    'paper_handling_types': [
        ('sheet_fed', 'تغذية أوراق'),
        ('roll_fed', 'تغذية لفائف'),
        ('both', 'كلاهما')
    ],
    
    'digital_paper_sizes': [
        ('a4', 'A4 (21×29.7 سم)'),
        ('a3', 'A3 (29×42 سم)'),
        ('a3_plus', 'A3+ (32×45 سم)'),
        ('sra3', 'SRA3 (32×45 سم)'),
        ('a2', 'A2 (42×59.4 سم)'),
        ('a1', 'A1 (59.4×84.1 سم)'),
        ('a0', 'A0 (84.1×118.9 سم)'),
        ('custom', 'مقاس مخصص')
    ],
    
    'plate_sizes': [
        ('quarter_sheet', 'ربع (35×50 سم)'),
        ('half_sheet', 'نص (50×70 سم)'),
        ('full_sheet', 'فرخ (70×100 سم)'),
        ('custom', 'مقاس مخصوص')
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
    return FIELD_CHOICES.get(choices_source, [])

def get_db_field_path(service_type, field_name):
    """
    جلب مسار الحقل في قاعدة البيانات
    """
    field_config = get_field_config(service_type, field_name)
    if field_config:
        return field_config.get('db_field')
    return None
