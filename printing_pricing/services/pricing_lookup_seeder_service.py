"""
خدمة البذر البرمجية المركزية لتثبيت ومزامنة كافة جداول تسعير المطبوعات
Pricing Lookup Seeder Service - MWHEBA ERP
تضمن بذر كافة البيانات الاسترشادية والتشغيلية بالمفاتيح الطبيعية (Natural Keys)
دون أي اعتماد على أرقام الـ PKs وبشكل Idempotent آمن تماماً.
"""
import logging
from decimal import Decimal
from django.db import transaction
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class PricingLookupSeederService:
    """
    خدمة مركزية لتغذية وبذر كافة جداول التكويد والإعدادات لموديول التسعير
    """

    # 1. أنواع وخامات الورق
    PAPER_TYPES = [
        {
            "name": "كوشيه",
            "description": "ورق كوشيه عالي الجودة للطباعة الملونة والبروشورات والمجلات",
            "sort_order": 10,
            "is_default": True,
            "override_sheets_per_pack": None,
        },
        {
            "name": "طبع",
            "description": "ورق أوفست للطباعة العادية والمراسلات وكتب القراءة",
            "sort_order": 20,
            "is_default": False,
            "override_sheets_per_pack": None,
        },
        {
            "name": "بريستول كرتون",
            "description": "ورق كرتون مصقول للأغلفة والكروت الشخصية والعلب الخفيفة",
            "sort_order": 30,
            "is_default": False,
            "override_sheets_per_pack": None,
        },
        {
            "name": "دوبلكس",
            "description": "كرتون دوبلكس ظهر رمادي أو أبيض للعلب والتغليف الصناعي",
            "sort_order": 40,
            "is_default": False,
            "override_sheets_per_pack": 100,
        },
        {
            "name": "ستيكر لاصق",
            "description": "ورق لاصق شيتات (ورقي / بلاستيك) للملصقات والعلب",
            "sort_order": 50,
            "is_default": False,
            "override_sheets_per_pack": 100,
        },
        {
            "name": "كرافت تغليف",
            "description": "ورق بني طبيعي عالي التحمل للشنط والتغليف الصديق للبيئة",
            "sort_order": 60,
            "is_default": False,
            "override_sheets_per_pack": None,
        },
        {
            "name": "كربون NCR فواتير",
            "description": "ورق مكربن ذاتي النسخ لدفاتر الفواتير والإيصالات والعقود",
            "sort_order": 70,
            "is_default": False,
            "override_sheets_per_pack": 500,
        },
        {
            "name": "فبريانو",
            "description": "ورق قطني مميز بملمس محبب لشهادات التقدير والمطبوعات الفاخرة",
            "sort_order": 80,
            "is_default": False,
            "override_sheets_per_pack": None,
        },
        {
            "name": "كونكورد",
            "description": "ورق فاخر علامة مائية للمراسلات الرسمية والشركات الكبرى",
            "sort_order": 90,
            "is_default": False,
            "override_sheets_per_pack": None,
        },
    ]

    # 2. مقاسات الفروخ الخام
    PAPER_SIZES = [
        {
            "name": "فرخ كامل",
            "width": Decimal("70.00"),
            "height": Decimal("100.00"),
            "description": "المقاس القياسي العالمي للفروخ التجارية (70×100 سم)",
            "sort_order": 10,
            "is_default": True,
        },
        {
            "name": "فرخ جاير",
            "width": Decimal("66.00"),
            "height": Decimal("88.00"),
            "description": "مقاس جاير أوفست اقتصادي بدون هادر للكتب والمجلات A4/A5",
            "sort_order": 20,
            "is_default": False,
        },
        {
            "name": "فرخ طبع جاير",
            "width": Decimal("60.00"),
            "height": Decimal("85.00"),
            "description": "مقاس طبع جاير للكتب المدرسية والمذكرات B5",
            "sort_order": 30,
            "is_default": False,
        },
    ]

    # 3. أوزان الورق وسعات الرزم القياسية
    PAPER_WEIGHTS = [
        {"gsm": 70,  "name": "70 جرام",  "sheets_per_pack": 500, "sort_order": 10,  "is_default": False, "description": "ورق خفيف لمتن الكتب ودفاتر الفواتير NCR"},
        {"gsm": 80,  "name": "80 جرام",  "sheets_per_pack": 500, "sort_order": 20,  "is_default": False, "description": "ورق طبع ومراسلات رسمي للمستندات والخطابات"},
        {"gsm": 100, "name": "100 جرام", "sheets_per_pack": 250, "sort_order": 40,  "is_default": False, "description": "ورق طبع أوفست فاخر أو كوشيه متوسط"},
        {"gsm": 115, "name": "115 جرام", "sheets_per_pack": 250, "sort_order": 50,  "is_default": False, "description": "كوشيه مجلات ونشرات دعائية"},
        {"gsm": 135, "name": "135 جرام", "sheets_per_pack": 250, "sort_order": 60,  "is_default": False, "description": "كوشيه ممتاز للبروشورات والفلايرات الدعائية"},
        {"gsm": 150, "name": "150 جرام", "sheets_per_pack": 250, "sort_order": 70,  "is_default": True,  "description": "الجراماج القياسي للمطبوعات التجارية والفلايرات والكتالوجات"},
        {"gsm": 170, "name": "170 جرام", "sheets_per_pack": 250, "sort_order": 80,  "is_default": False, "description": "كوشيه متين للمطويات الفاخرة وبروفايلات الشركات"},
        {"gsm": 200, "name": "200 جرام", "sheets_per_pack": 250, "sort_order": 90,  "is_default": False, "description": "كوشيه نصف مقوى لأغلفة الكتيبات والمجلدات"},
        {"gsm": 250, "name": "250 جرام", "sheets_per_pack": 125, "sort_order": 100, "is_default": False, "description": "كرتون / كوشيه سميك للأغلفة والفولدرات الخفيفة"},
        {"gsm": 300, "name": "300 جرام", "sheets_per_pack": 125, "sort_order": 110, "is_default": False, "description": "الجراماج الشائع للكروت الشخصية والفولدرات والعلب"},
        {"gsm": 350, "name": "350 جرام", "sheets_per_pack": 100, "sort_order": 120, "is_default": False, "description": "كوشيه / بريستول فاخر فائق المتانة للكروت الفاخرة والتغليف"},
    ]

    # 4. مناشئ الورق
    PAPER_ORIGINS = [
        {"code": "EG", "name": "مصري",    "sort_order": 10,  "is_default": True,  "description": "ورق مصري إنتاج قنا وإدفو ومصر للورق"},
        {"code": "DE", "name": "ألماني",   "sort_order": 20,  "is_default": False, "description": "ورق ألماني ممتاز عالي النقاء"},
        {"code": "FI", "name": "فنلندي",  "sort_order": 30,  "is_default": False, "description": "ورق فنلندي فائق الجودة للأعمال الفاخرة"},
        {"code": "ID", "name": "إندونيسي", "sort_order": 40,  "is_default": False, "description": "ورق أوفست وكوشيه إندونيسي (Tjiwi Kimia / APP)"},
        {"code": "CN", "name": "صيني",    "sort_order": 50,  "is_default": False, "description": "ورق صيني اقتصادي للطباعة والكرتون"},
        {"code": "KR", "name": "كوري",    "sort_order": 60,  "is_default": False, "description": "كوشيه ودوبلكس كوري عالي اللمعان"},
        {"code": "IT", "name": "إيطالي",   "sort_order": 70,  "is_default": False, "description": "ورق فبريانو ومواد تشطيب إيطالية"},
        {"code": "AT", "name": "نمساوي",  "sort_order": 80,  "is_default": False, "description": "ورق أوفست نمساوي خالي من الأحماض"},
        {"code": "SE", "name": "سويدي",   "sort_order": 90,  "is_default": False, "description": "ورق كرافت وخامات سويدية عالية الشد"},
        {"code": "FR", "name": "فرنسي",   "sort_order": 100, "is_default": False, "description": "ورق فرنسي للمطبوعات التحريرية والفنية"},
        {"code": "TR", "name": "تركي",    "sort_order": 110, "is_default": False, "description": "ورق وخامات تجليد واستيكر تركي"},
        {"code": "IN", "name": "هندي",    "sort_order": 120, "is_default": False, "description": "ورق دوبلكس وكرافت هندي تجاري"},
    ]

    # 5. ماكينات الطباعة (أوفست وديجيتال)
    PRINTING_MACHINES = [
        # ماكينات أوفست
        {
            "code": "sm52",
            "name": "هايدلبرج SM 52",
            "machine_category": "offset",
            "manufacturer": "Heidelberg",
            "max_sheet_size": "37×52",
            "colors_capacity": 4,
            "is_color": True,
            "description": "ماكينة أوفست ربع فرخ 4 لون للأعمال التجارية السريعة والكروت والفلايرات",
            "sort_order": 10,
            "is_default": False,
        },
        {
            "code": "sm74",
            "name": "هايدلبرج SM 74",
            "machine_category": "offset",
            "manufacturer": "Heidelberg",
            "max_sheet_size": "53×74",
            "colors_capacity": 4,
            "is_color": True,
            "description": "ماكينة أوفست نصف فرخ 4 لون القياسية للمطبوعات التجارية والبروشورات",
            "sort_order": 20,
            "is_default": True,
        },
        {
            "code": "cd102",
            "name": "هايدلبرج CD 102",
            "machine_category": "offset",
            "manufacturer": "Heidelberg",
            "max_sheet_size": "72×102",
            "colors_capacity": 4,
            "is_color": True,
            "description": "ماكينة أوفست فرخ كامل 4 لون للإنتاج الضخم والكتب والتغليف",
            "sort_order": 30,
            "is_default": False,
        },
        {
            "code": "ls40",
            "name": "كوموري Lithrone 40",
            "machine_category": "offset",
            "manufacturer": "Komori",
            "max_sheet_size": "72×103",
            "colors_capacity": 4,
            "is_color": True,
            "description": "ماكينة أوفست يابانية فرخ كامل سرعة فائقة وجودة استثنائية",
            "sort_order": 40,
            "is_default": False,
        },
        {
            "code": "ryobi_524",
            "name": "ريوبي 524",
            "machine_category": "offset",
            "manufacturer": "Ryobi",
            "max_sheet_size": "37×52",
            "colors_capacity": 4,
            "is_color": True,
            "description": "ماكينة أوفست يابانية ربع فرخ اقتصادية للأعمال الصغيرة والمتوسطة",
            "sort_order": 50,
            "is_default": False,
        },
        # ماكينات ديجيتال
        {
            "code": "indigo_7900",
            "name": "إنديجو HP Indigo 7900",
            "machine_category": "digital",
            "manufacturer": "HP",
            "max_sheet_size": "33×48",
            "colors_capacity": 4,
            "print_quality": "2438×2438 DPI",
            "is_color": True,
            "description": "ماكينة ديجيتال أحبار سائلة ElectroInk تضاهي جودة الأوفست",
            "sort_order": 60,
            "is_default": True,
        },
        {
            "code": "xerox_280",
            "name": "زيروكس Versant 280",
            "machine_category": "digital",
            "manufacturer": "Xerox",
            "max_sheet_size": "33×66",
            "colors_capacity": 4,
            "print_quality": "2400×2400 DPI",
            "is_color": True,
            "description": "ماكينة ديجيتال تجارية سريعة للكميات المتوسطة والبانوراما",
            "sort_order": 70,
            "is_default": False,
        },
        {
            "code": "canon_c910",
            "name": "كانون imagePRESS C910",
            "machine_category": "digital",
            "manufacturer": "Canon",
            "max_sheet_size": "33×48",
            "colors_capacity": 4,
            "print_quality": "2400×2400 DPI",
            "is_color": True,
            "description": "ماكينة ديجيتال احترافية متعددة الوسائط ودقيقة التسجيل",
            "sort_order": 80,
            "is_default": False,
        },
        {
            "code": "konicaminolta_c4080",
            "name": "كونيكا مينولتا AccurioPress C4080",
            "machine_category": "digital",
            "manufacturer": "Konica Minolta",
            "max_sheet_size": "33×76",
            "colors_capacity": 4,
            "print_quality": "3600×2400 DPI",
            "is_color": True,
            "description": "ماكينة ديجيتال قوية للمطبوعات الثقيلة والشيتات الطويلة",
            "sort_order": 90,
            "is_default": False,
        },
    ]

    # 6. شيتات التشغيل وزنكات CTP
    MACHINE_DIMENSIONS = [
        # شيتات تشغيل الأوفست
        {
            "code": "quarter_sheet",
            "name": "ربع فرخ",
            "dimension_type": "sheet",
            "width": Decimal("35.00"),
            "height": Decimal("50.00"),
            "description": "مقاس ربع فرخ للأعمال الصغيرة وماكينات SM52 والريوبي",
            "sort_order": 10,
            "is_default": False,
        },
        {
            "code": "half_sheet",
            "name": "نصف فرخ",
            "dimension_type": "sheet",
            "width": Decimal("50.00"),
            "height": Decimal("70.00"),
            "description": "مقاس نصف فرخ القياسي للأعمال المتوسطة وماكينات SM74",
            "sort_order": 20,
            "is_default": True,
        },
        {
            "code": "full_sheet",
            "name": "فرخ كامل",
            "dimension_type": "sheet",
            "width": Decimal("70.00"),
            "height": Decimal("100.00"),
            "description": "مقاس فرخ كامل للأعمال الكبيرة والإنتاج الضخم وماكينات CD102",
            "sort_order": 30,
            "is_default": False,
        },
        # شيتات تشغيل الديجيتال
        {
            "code": "digital_a3",
            "name": "A3 ديجيتال (29.7×42)",
            "dimension_type": "sheet",
            "width": Decimal("29.70"),
            "height": Decimal("42.00"),
            "description": "مقاس A3 للبوسترات والكتيبات المفتوحة",
            "sort_order": 80,
            "is_default": False,
        },
        {
            "code": "digital_super_a3_plus",
            "name": "سوبر A3 بلس ديجيتال (33×48.8)",
            "dimension_type": "sheet",
            "width": Decimal("33.00"),
            "height": Decimal("48.80"),
            "description": "مقاس شيت ماكينات إنديجو وكانون وزيروكس الموسع",
            "sort_order": 100,
            "is_default": False,
        },
        {
            "code": "digital_panorama",
            "name": "بانوراما ديجيتال (33×66)",
            "dimension_type": "sheet",
            "width": Decimal("33.00"),
            "height": Decimal("66.00"),
            "description": "مقاس الشيت الطويل للبروشورات 3 بوابة والمطويات البانورامية",
            "sort_order": 110,
            "is_default": False,
        },
        # زنكات CTP للطباعة الأوفست
        {
            "code": "plate_sm52",
            "name": "زنكة ربع فرخ",
            "dimension_type": "plate",
            "width": Decimal("45.90"),
            "height": Decimal("52.50"),
            "description": "زنكة CTP ألومنيوم حرارية لماكينة هايدلبرج SM52",
            "sort_order": 120,
            "is_default": False,
        },
        {
            "code": "plate_sm74",
            "name": "زنكة نصف فرخ",
            "dimension_type": "plate",
            "width": Decimal("60.50"),
            "height": Decimal("74.50"),
            "description": "زنكة CTP ألومنيوم حرارية لماكينة هايدلبرج SM74 القياسية",
            "sort_order": 130,
            "is_default": True,
        },
        {
            "code": "plate_cd102",
            "name": "زنكة فرخ كامل",
            "dimension_type": "plate",
            "width": Decimal("79.00"),
            "height": Decimal("103.00"),
            "description": "زنكة CTP ألومنيوم حرارية لماكينة هايدلبرج CD102 فرخ كامل",
            "sort_order": 140,
            "is_default": False,
        },
    ]

    # 7. مقاسات القص المستخرجة من الفروخ (Piece Sizes)
    PIECE_SIZES = [
        # مقاسات مقصوصة من فرخ 70×100
        {"name": "فرخ كامل", "parent_sheet": "70×100", "width": Decimal("70.00"), "height": Decimal("100.00"), "pieces_per_sheet": 1,  "sort_order": 10, "is_default": False},
        {"name": "نصف فرخ",   "parent_sheet": "70×100", "width": Decimal("50.00"), "height": Decimal("70.00"),  "pieces_per_sheet": 2,  "sort_order": 20, "is_default": True},
        {"name": "ربع فرخ",   "parent_sheet": "70×100", "width": Decimal("35.00"), "height": Decimal("50.00"),  "pieces_per_sheet": 4,  "sort_order": 30, "is_default": False},
        {"name": "ثمن فرخ",   "parent_sheet": "70×100", "width": Decimal("25.00"), "height": Decimal("35.00"),  "pieces_per_sheet": 8,  "sort_order": 40, "is_default": False},
        {"name": "مقاس 30×40",        "parent_sheet": "70×100", "width": Decimal("30.00"), "height": Decimal("40.00"),  "pieces_per_sheet": 5,  "sort_order": 50, "is_default": False},
        {"name": "مقاس 20×30",        "parent_sheet": "70×100", "width": Decimal("20.00"), "height": Decimal("30.00"),  "pieces_per_sheet": 11, "sort_order": 60, "is_default": False},
        # مقاسات مقصوصة من فرخ جاير 66×88
        {"name": "فرخ جاير",  "parent_sheet": "66×88",  "width": Decimal("66.00"), "height": Decimal("88.00"), "pieces_per_sheet": 1,  "sort_order": 70, "is_default": False},
        {"name": "نصف جاير",  "parent_sheet": "66×88",  "width": Decimal("44.00"), "height": Decimal("66.00"), "pieces_per_sheet": 2,  "sort_order": 80, "is_default": False},
        {"name": "ربع جاير",  "parent_sheet": "66×88",  "width": Decimal("33.00"), "height": Decimal("44.00"), "pieces_per_sheet": 4,  "sort_order": 90, "is_default": False},
        # مقاسات مقصوصة من فرخ طبع جاير 60×85
        {"name": "فرخ طبع جاير", "parent_sheet": "60×85", "width": Decimal("60.00"), "height": Decimal("85.00"), "pieces_per_sheet": 1,  "sort_order": 100, "is_default": False},
        {"name": "نصف طبع جاير","parent_sheet": "60×85", "width": Decimal("42.50"), "height": Decimal("60.00"), "pieces_per_sheet": 2,  "sort_order": 110, "is_default": False},
        {"name": "ربع طبع جاير (30×42.5)","parent_sheet": "60×85", "width": Decimal("30.00"), "height": Decimal("42.50"), "pieces_per_sheet": 4,  "sort_order": 120, "is_default": False},
    ]

    # 8. خدمات التغطية (Coating)
    COATING_TYPES = [
        {"name": "سلوفان لامع",    "unit_rate": Decimal("0.35"), "setup_cost": Decimal("100.00"), "minimum_charge": Decimal("100.00"), "make_ready_waste_sheets": 15, "sort_order": 10, "is_default": True,  "description": "سلوفان حراري لامع براق لحماية المطبوعات وإبراز الألوان"},
        {"name": "سلوفان مط",       "unit_rate": Decimal("0.40"), "setup_cost": Decimal("100.00"), "minimum_charge": Decimal("100.00"), "make_ready_waste_sheets": 15, "sort_order": 20, "is_default": False, "description": "سلوفان حراري مطفي أنيق وراقي للمطبوعات الفاخرة"},
        {"name": "ورنيش UV",          "unit_rate": Decimal("0.50"), "setup_cost": Decimal("120.00"), "minimum_charge": Decimal("120.00"), "make_ready_waste_sheets": 20, "sort_order": 60, "is_default": False, "description": "طبقة ورنيش يوفي فائق اللمعان والصلابة على كامل الفرخ"},
    ]

    # 9. خدمات التشطيب (Finishing)
    FINISHING_TYPES = [
        {"name": "قص وتقطيع",       "unit_rate": Decimal("15.00"), "setup_cost": Decimal("30.00"),  "minimum_charge": Decimal("30.00"),  "tooling_cost": Decimal("0.00"),   "make_ready_waste_sheets": 5,  "sort_order": 10, "is_default": True,  "description": "طهارة وقص المطبوع بالمقص الكمبيوتر إلى المقاس النهائي"},
        {"name": "ريجة", "unit_rate": Decimal("25.00"), "setup_cost": Decimal("50.00"),  "minimum_charge": Decimal("50.00"),  "tooling_cost": Decimal("0.00"),   "make_ready_waste_sheets": 10, "sort_order": 20, "is_default": False, "description": "تحديد خطوط الطي في الورق السميك لمنع تشقق الطباعة"},
        {"name": "فورمة تكسير", "unit_rate": Decimal("40.00"), "setup_cost": Decimal("80.00"),  "minimum_charge": Decimal("80.00"),  "tooling_cost": Decimal("250.00"), "make_ready_waste_sheets": 25, "sort_order": 30, "is_default": False, "description": "قص هندسي خاص للعلب والفولدرات بواسطة اسطمبة ليزر خشبية"},
        {"name": "بصمة", "unit_rate": Decimal("60.00"), "setup_cost": Decimal("120.00"), "minimum_charge": Decimal("120.00"), "tooling_cost": Decimal("180.00"), "make_ready_waste_sheets": 20, "sort_order": 40, "is_default": False, "description": "تذهيب أو تفضيض حراري لشعارات ونصوص المطبوع بكليشيه زنك"},
        {"name": "كوفراج","unit_rate": Decimal("45.00"), "setup_cost": Decimal("100.00"), "minimum_charge": Decimal("100.00"), "tooling_cost": Decimal("150.00"), "make_ready_waste_sheets": 15, "sort_order": 50, "is_default": False, "description": "بروز مجسم للشعار أو الاسم بدون لون بكليشيه مخصص"},
        {"name": "كوفراج مع بصمة",  "unit_rate": Decimal("90.00"), "setup_cost": Decimal("180.00"), "minimum_charge": Decimal("180.00"), "tooling_cost": Decimal("300.00"), "make_ready_waste_sheets": 25, "sort_order": 70, "is_default": False, "description": "بصمة دهبي مجسمة بارزة في نفس الوقت بكليشيه ثنائي"},
        {"name": "سبوت UV","unit_rate": Decimal("70.00"), "setup_cost": Decimal("150.00"), "minimum_charge": Decimal("150.00"), "tooling_cost": Decimal("120.00"), "make_ready_waste_sheets": 20, "sort_order": 80, "is_default": False, "description": "ورنيش لامع على أجزاء محددة كالشعار والصور فوق السلوفان المط"},
        {"name": "شرشرة",     "unit_rate": Decimal("15.00"), "setup_cost": Decimal("30.00"),  "minimum_charge": Decimal("30.00"),  "tooling_cost": Decimal("0.00"),   "make_ready_waste_sheets": 5,  "sort_order": 90, "is_default": False, "description": "تخريم دوسيهات 2 أو 4 خرم أو خط تقطيع مشرشر لدفاتر الإيصالات"},
    ]

    # 10. خدمات التقفيل والتجليد (Packaging)
    PACKAGING_TYPES = [
        {"name": "تدبيس حصان", "unit_rate": Decimal("30.00"), "setup_cost": Decimal("60.00"),  "minimum_charge": Decimal("60.00"),  "sort_order": 10, "is_default": True,  "description": "تدبيس كتيبات ومجلات من المنتصف بدبوسين معدنيين"},
        {"name": "تقفيل سلك",    "unit_rate": Decimal("80.00"), "setup_cost": Decimal("100.00"), "minimum_charge": Decimal("100.00"), "sort_order": 30, "is_default": False, "description": "تجليد سلك معدني حلزوني للبلوك نوت والتقاويم وبروفايلات الشركات"},
        {"name": "بشر غراء", "unit_rate": Decimal("90.00"), "setup_cost": Decimal("150.00"), "minimum_charge": Decimal("150.00"), "sort_order": 40, "is_default": False, "description": "تجليد حراري بكعب مربع للكتب والروايات والكتالوجات الكبيرة"},
        {"name": "تقفيل هارد كفر", "unit_rate": Decimal("250.00"),"setup_cost": Decimal("300.00"), "minimum_charge": Decimal("300.00"), "sort_order": 50, "is_default": False, "description": "تجليد كتب فاخرة ومصاحف وأجندات بكرتون مقوى مكسو بالسلوفان أو الجلد"},
        {"name": "تقفيل علب وفولدرات",    "unit_rate": Decimal("35.00"), "setup_cost": Decimal("60.00"),  "minimum_charge": Decimal("60.00"),  "sort_order": 70, "is_default": False, "description": "لصق جانبي أو قاع أوتوماتيك للعلب وجيوب الفولدرات"},
    ]

    # 11. المنتجات والمقاسات التجارية
    PRODUCT_TYPES = [
        {
            "name": "مطبوع مفرود (كروت / فلاير)",
            "base_archetype": "flyer",
            "sort_order": 10,
            "is_default": True,
            "description": "كروت شخصية، فلايرات، بروشورات، بوسترات، أظرف، ستيكر شيتات",
        },
        {
            "name": "مطبوع مع داخلي (كتالوج / بلوك نوت)",
            "base_archetype": "catalog",
            "sort_order": 20,
            "is_default": False,
            "description": "كتالوجات، كتب، مجلات، مذكرات، بروفايلات شركات، بلوك نوت (غلاف + صفحات داخلية)",
        },
        {
            "name": "مطبوع مع فورمة تكسير",
            "base_archetype": "folder",
            "sort_order": 30,
            "is_default": False,
            "description": "فولدرات شركات بجيب، علب كرتون، منتجات باكيج وتغليف مع اسطمبة تكسير",
        },
        {
            "name": "دفاتر مكربن",
            "base_archetype": "invoice",
            "sort_order": 40,
            "is_default": False,
            "description": "دفاتر فواتير، إيصالات، عقود مكربنة NCR، أذون مخازن متعددة الصور",
        },
    ]

    PRODUCT_SIZES = [
        {"name": "A4",            "width": Decimal("21.00"), "height": Decimal("29.70"), "sort_order": 10, "is_default": True,  "description": "مقاس A4 القياسي (21×29.7 سم) للمستندات والبروشورات والكتالوجات"},
        {"name": "A5",       "width": Decimal("14.80"), "height": Decimal("21.00"), "sort_order": 20, "is_default": False, "description": "مقاس A5 (14.8×21 سم) للفلايرات والكتيبات الدعائية"},
        {"name": "A3",  "width": Decimal("29.70"), "height": Decimal("42.00"), "sort_order": 30, "is_default": False, "description": "مقاس A3 (29.7×42 سم) للبوسترات والمطويات الكبيرة"},
        {"name": "A6",      "width": Decimal("10.50"), "height": Decimal("14.80"), "sort_order": 40, "is_default": False, "description": "مقاس A6 (10.5×14.8 سم) للبلوك نوت والمذكرات الجيب"},
        {"name": "كارت شخصي",       "width": Decimal("9.00"),  "height": Decimal("5.00"),  "sort_order": 50, "is_default": False, "description": "مقاس الكروت الشخصية وبزنس كارد القياسي (9×5 سم)"},
    ]

    # =========================================================================
    # دوال التنفيذ الفعلية (Execution Methods)
    # =========================================================================

    @classmethod
    def seed_paper_types(cls) -> tuple[int, int]:
        from printing_pricing.models import PaperType
        created, updated = 0, 0
        for item in cls.PAPER_TYPES:
            _, is_new = PaperType.objects.update_or_create(
                name=item["name"],
                defaults=item
            )
            if is_new:
                created += 1
            else:
                updated += 1
        return created, updated

    @classmethod
    def seed_paper_sizes(cls) -> tuple[int, int]:
        from printing_pricing.models import PaperSize
        created, updated = 0, 0
        for item in cls.PAPER_SIZES:
            _, is_new = PaperSize.objects.update_or_create(
                name=item["name"],
                defaults=item
            )
            if is_new:
                created += 1
            else:
                updated += 1
        return created, updated

    @classmethod
    def seed_paper_weights(cls) -> tuple[int, int]:
        from printing_pricing.models import PaperWeight
        created, updated = 0, 0
        for item in cls.PAPER_WEIGHTS:
            _, is_new = PaperWeight.objects.update_or_create(
                gsm=item["gsm"],
                defaults=item
            )
            if is_new:
                created += 1
            else:
                updated += 1
        return created, updated

    @classmethod
    def seed_paper_origins(cls) -> tuple[int, int]:
        from printing_pricing.models import PaperOrigin
        created, updated = 0, 0
        for item in cls.PAPER_ORIGINS:
            _, is_new = PaperOrigin.objects.update_or_create(
                code=item["code"],
                defaults=item
            )
            if is_new:
                created += 1
            else:
                updated += 1
        return created, updated

    @classmethod
    def seed_piece_sizes(cls) -> tuple[int, int]:
        from printing_pricing.models import PaperSize, PieceSize
        created, updated = 0, 0
        
        # خريطة البحث عن الفروخ الخام بالأبعاد الرقمية الصريحة لمنع أي تباين في الترميز
        sheet_70_100 = PaperSize.objects.filter(width=Decimal("70.00"), height=Decimal("100.00")).first()
        sheet_66_88  = PaperSize.objects.filter(width=Decimal("66.00"), height=Decimal("88.00")).first()
        sheet_60_85  = PaperSize.objects.filter(width=Decimal("60.00"), height=Decimal("85.00")).first()

        for item in cls.PIECE_SIZES:
            parent_sheet = None
            if item["parent_sheet"] == "70×100":
                parent_sheet = sheet_70_100
            elif item["parent_sheet"] == "66×88":
                parent_sheet = sheet_66_88
            elif item["parent_sheet"] == "60×85":
                parent_sheet = sheet_60_85

            defaults = {
                "paper_type": parent_sheet,
                "width": item["width"],
                "height": item["height"],
                "pieces_per_sheet": item["pieces_per_sheet"],
                "sort_order": item["sort_order"],
                "is_default": item["is_default"],
                "is_active": True,
            }
            _, is_new = PieceSize.objects.update_or_create(
                name=item["name"],
                defaults=defaults
            )
            if is_new:
                created += 1
            else:
                updated += 1
        return created, updated

    @classmethod
    def seed_printing_machines(cls) -> tuple[int, int]:
        from printing_pricing.models import PrintingMachine
        created, updated = 0, 0
        for item in cls.PRINTING_MACHINES:
            _, is_new = PrintingMachine.objects.update_or_create(
                code=item["code"],
                defaults=item
            )
            if is_new:
                created += 1
            else:
                updated += 1
        return created, updated

    @classmethod
    def seed_machine_dimensions(cls) -> tuple[int, int]:
        from printing_pricing.models import MachineDimension
        created, updated = 0, 0
        for item in cls.MACHINE_DIMENSIONS:
            _, is_new = MachineDimension.objects.update_or_create(
                code=item["code"],
                defaults=item
            )
            if is_new:
                created += 1
            else:
                updated += 1
        return created, updated

    @classmethod
    def seed_postpress(cls) -> tuple[int, int]:
        from printing_pricing.models import CoatingType, FinishingType, PackagingType
        created, updated = 0, 0
        
        # التغطية
        for item in cls.COATING_TYPES:
            _, is_new = CoatingType.objects.update_or_create(
                name=item["name"],
                defaults=item
            )
            if is_new: created += 1
            else: updated += 1

        # التشطيب
        for item in cls.FINISHING_TYPES:
            _, is_new = FinishingType.objects.update_or_create(
                name=item["name"],
                defaults=item
            )
            if is_new: created += 1
            else: updated += 1

        # التقفيل
        for item in cls.PACKAGING_TYPES:
            _, is_new = PackagingType.objects.update_or_create(
                name=item["name"],
                defaults=item
            )
            if is_new: created += 1
            else: updated += 1

        return created, updated

    @classmethod
    def seed_products(cls) -> tuple[int, int]:
        from printing_pricing.models import ProductType, ProductSize
        created, updated = 0, 0
        
        for item in cls.PRODUCT_TYPES:
            _, is_new = ProductType.objects.update_or_create(
                name=item["name"],
                defaults=item
            )
            if is_new: created += 1
            else: updated += 1

        for item in cls.PRODUCT_SIZES:
            _, is_new = ProductSize.objects.update_or_create(
                name=item["name"],
                defaults=item
            )
            if is_new: created += 1
            else: updated += 1

        return created, updated

    @classmethod
    def seed_all(cls) -> dict:
        """
        تشغيل حزمة التثبيت بالكامل لكافة جداول وإعدادات التسعير
        داخل معاملة ذرية واحدة (Atomic Transaction).
        """
        with transaction.atomic():
            logger.info("بدء بذر وتحديث جداول وإعدادات تسعير المطبوعات...")
            results = {}
            total_created = 0
            total_updated = 0

            steps = [
                ("paper_types", cls.seed_paper_types),
                ("paper_sizes", cls.seed_paper_sizes),
                ("paper_weights", cls.seed_paper_weights),
                ("paper_origins", cls.seed_paper_origins),
                ("piece_sizes", cls.seed_piece_sizes),
                ("printing_machines", cls.seed_printing_machines),
                ("machine_dimensions", cls.seed_machine_dimensions),
                ("postpress", cls.seed_postpress),
                ("products", cls.seed_products),
            ]

            for key, func in steps:
                c, u = func()
                results[key] = {"created": c, "updated": u}
                total_created += c
                total_updated += u

            summary = f"{total_created} جديد، {total_updated} محدث"
            logger.info(f"✅ اكتمل بذر جداول تسعير المطبوعات بنجاح ({summary}).")
            return {
                "success": True,
                "total_created": total_created,
                "total_updated": total_updated,
                "summary": summary,
                "details": results,
            }
