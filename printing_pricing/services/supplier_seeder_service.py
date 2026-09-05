"""
خدمة تهيئة وبذر أنواع الموردين وخدمات التسعير لموديول الطباعة
Pricing Supplier Seeder Service - MWHEBA ERP
"""
import logging
from django.db import transaction
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class PricingSupplierSeederService:
    """
    خدمة مركزية لتثبيت ومزامنة أنواع الموردين المتخصصة بالطباعة
    وأنواع خدمات التسعير في النظام بضمان عدم التكرار (Idempotent).
    """

    PRINTING_SUPPLIER_TYPES = [
        {
            "code": "paper_supplier",
            "name": _("مخزن ورق"),
            "description": _("تجار وموردي الورق، الكرتون، الدوبلكس، الكوشيه، وخامات التغليف"),
            "icon": "fas fa-scroll",
            "color": "#20c997",
            "display_order": 10,
            "is_active": True,
            "is_system": False,
            "is_service_provider": False,
        },
        {
            "code": "offset_press",
            "name": _("مطبعة أوفست"),
            "description": _("مطابع تجارية ومقاولين باطن (سحبات الماكينات وتكلفة الـ 1000 طبعة)"),
            "icon": "fas fa-print",
            "color": "#0d6efd",
            "display_order": 11,
            "is_active": True,
            "is_system": False,
            "is_service_provider": True,
        },
        {
            "code": "digital_center",
            "name": _("مطبعة ديجيتال"),
            "description": _("مراكز الطباعة الرقمية للكميات الصغيرة، العينات، والطباعة الفورية"),
            "icon": "fas fa-desktop",
            "color": "#6610f2",
            "display_order": 12,
            "is_active": True,
            "is_system": False,
            "is_service_provider": True,
        },
        {
            "code": "ctp_center",
            "name": _("مكتب فصل ألوان"),
            "description": _("مراكز تجهيز وتخريج ألواح الزنك الحرارية وUV لمقاسات الماكينات المختلفة"),
            "icon": "fas fa-layer-group",
            "color": "#fd7e14",
            "display_order": 13,
            "is_active": True,
            "is_system": False,
            "is_service_provider": True,
        },
        {
            "code": "finishing_workshop",
            "name": _("ورشة خدمات طباعة"),
            "description": _("خدمات ما بعد الطباعة: سلفنة، ورنيش UV، دايكت، ريجة، وتجليد (دبوس/سلك/غراء/كرتنة)"),
            "icon": "fas fa-cut",
            "color": "#e83e8c",
            "display_order": 14,
            "is_active": True,
            "is_system": False,
            "is_service_provider": True,
        },
        {
            "code": "printing_supplies",
            "name": _("مورد خامات طباعة"),
            "description": _("موردي الأحبار، الكيماويات، محاليل الترطيب، ومستلزمات الصيانة والتشغيل"),
            "icon": "fas fa-tint",
            "color": "#0dcaf0",
            "display_order": 15,
            "is_active": True,
            "is_system": False,
            "is_service_provider": False,
        },
    ]

    PRINTING_SERVICE_TYPES = [
        {
            "code": "paper",
            "name": _("ورق"),
            "category": "printing",
            "icon": "fas fa-scroll",
            "description": _("خدمات توريد الورق بأنواعه وأوزانه ومقاساته المختلفة"),
            "attribute_schema": {
                "paper_type":      {"type": "select", "source": "PaperType",   "required": True,  "label": "نوع الورق"},
                "gsm":             {"type": "select", "source": "PaperWeight", "required": True,  "label": "الوزن (جم)"},
                "sheet_size":      {"type": "select", "source": "PaperSize",   "required": True,  "label": "مقاس الفرخ"},
                "origin":          {"type": "select", "source": "PaperOrigin", "required": False, "label": "المنشأ"},
                "price_per_sheet": {"type": "decimal",                         "required": True,  "label": "سعر الفرخ (ج.م)"}
            },
            "is_active": True,
            "order": 1,
        },
        {
            "code": "offset_printing",
            "name": _("طباعة أوفست"),
            "category": "printing",
            "icon": "fas fa-print",
            "description": _("خدمات الطباعة بماكينات الأوفست"),
            "attribute_schema": {
                "machine_type":         {"type": "select",  "source": "OffsetMachineType", "required": True,  "label": "نوع الماكينة"},
                "sheet_size":           {"type": "select",  "source": "OffsetSheetSize",   "required": True,  "label": "مقاس الفرخ"},
                "max_colors":           {"type": "integer", "min": 1, "max": 8,            "required": True,  "label": "عدد الألوان"}
            },
            "is_active": True,
            "order": 2,
        },
        {
            "code": "digital_printing",
            "name": _("طباعة ديجيتال"),
            "category": "printing",
            "icon": "fas fa-desktop",
            "description": _("خدمات الطباعة الرقمية"),
            "attribute_schema": {
                "machine_type":         {"type": "select",  "source": "DigitalMachineType", "required": True,  "label": "نوع الماكينة"},
                "min_quantity":         {"type": "integer",                                 "required": False, "label": "الحد الأدنى للكمية"}
            },
            "is_active": True,
            "order": 3,
        },
        {
            "code": "ctp_plates",
            "name": _("زنكات CTP"),
            "category": "printing",
            "icon": "fas fa-layer-group",
            "description": _("خدمات تصنيع وتظهير الزنكات للطباعة الأوفست"),
            "attribute_schema": {
                "plate_size":      {"type": "select",  "source": "PlateSize", "required": True,  "label": "مقاس الزنكة"},
                "plate_type":      {"type": "select",  "options": ["عادي", "UV", "حساس"], "required": True,  "label": "نوع الزنكة"}
            },
            "is_active": True,
            "order": 4,
        },
        {
            "code": "finishing",
            "name": _("خدمات تشطيب"),
            "category": "printing",
            "icon": "fas fa-cut",
            "description": _("خدمات القص والريجة والتكسير والتثقيب"),
            "attribute_schema": {
                "finishing_type": {"type": "select",  "source": "FinishingType", "required": True,  "label": "نوع التشطيب"}
            },
            "is_active": True,
            "order": 5,
        },
        {
            "code": "coating",
            "name": _("تغطية"),
            "category": "printing",
            "icon": "fas fa-layer-group",
            "description": _("خدمات التغطية واللمنيشن والبلاستيك"),
            "attribute_schema": {
                "coating_type":   {"type": "select",  "source": "CoatingType", "required": True,  "label": "نوع التغطية"}
            },
            "is_active": True,
            "order": 6,
        },
        {
            "code": "packaging",
            "name": _("تقفيل وتجليد"),
            "category": "printing",
            "icon": "fas fa-book",
            "description": _("خدمات التقفيل بالدبوس والسلك والتجليد"),
            "attribute_schema": {
                "packaging_type": {"type": "select",  "source": "PackagingType", "required": True,  "label": "نوع التقفيل"},
                "price_per_1000": {"type": "decimal",                            "required": True,  "label": "سعر كل 1000 قطعة (ج.م)"},
                "setup_cost":     {"type": "decimal",                            "required": False, "label": "تكلفة الإعداد (ج.م)"}
            },
            "is_active": True,
            "order": 7,
        },
    ]

    SUPPLIER_TYPE_SERVICE_MAP = {
        "paper_supplier": ["paper"],
        "offset_press": ["offset_printing", "ctp_plates"],
        "digital_center": ["digital_printing"],
        "ctp_center": ["ctp_plates"],
        "finishing_workshop": ["finishing", "coating", "packaging"],
        "printing_supplies": [],
    }

    @classmethod
    def seed_supplier_types(cls, created_by=None):
        """
        تثبيت أنواع الموردين الخاصة بالطباعة في جدول SupplierTypeSettings
        ومزامنتها مع جدول SupplierType (بأمان تام دون تكرار).
        """
        from supplier.models import SupplierTypeSettings

        created_count = 0
        updated_count = 0

        for item in cls.PRINTING_SUPPLIER_TYPES:
            code = item["code"]
            defaults = {
                "name": str(item["name"]),
                "description": str(item["description"]),
                "icon": item["icon"],
                "color": item["color"],
                "display_order": item["display_order"],
                "is_active": item["is_active"],
                "is_system": item["is_system"],
                "is_service_provider": item["is_service_provider"],
            }
            if created_by:
                defaults["created_by"] = created_by

            obj, created = SupplierTypeSettings.objects.get_or_create(
                code=code,
                defaults=defaults,
            )

            if created:
                created_count += 1
                logger.info(f"تم إنشاء نوع مورد جديد: {obj.name} ({code})")
            else:
                updated_count += 1
                new_name = str(item["name"])
                if obj.name != new_name:
                    obj.name = new_name
                    obj.save(update_fields=["name"])

            # مزامنة السجل مع SupplierType القديم
            obj.sync_with_supplier_type()

        logger.info(f"اكتمل بذر أنواع الموردين: {created_count} جديد، {updated_count} موجود مسبقاً.")
        return created_count

    @classmethod
    def seed_service_types(cls):
        """
        تثبيت والتأكد من وجود خدمات التسعير السبعة في جدول ServiceType.
        """
        from supplier.models import ServiceType

        created_count = 0
        for item in cls.PRINTING_SERVICE_TYPES:
            code = item["code"]
            defaults = {
                "name": str(item["name"]),
                "category": item["category"],
                "icon": item["icon"],
                "description": str(item["description"]),
                "attribute_schema": item["attribute_schema"],
                "is_active": item["is_active"],
                "order": item["order"],
            }

            obj, created = ServiceType.objects.get_or_create(
                code=code,
                defaults=defaults,
            )
            if created:
                created_count += 1
                logger.info(f"تم إنشاء نوع خدمة تسعير جديد: {obj.name} ({code})")
            else:
                # إذا كانت الخدمة موجودة ولكن تنقصها الـ attribute_schema
                if not obj.attribute_schema and item["attribute_schema"]:
                    obj.attribute_schema = item["attribute_schema"]
                    obj.save(update_fields=["attribute_schema"])

        logger.info(f"اكتمل فحص أنواع خدمات التسعير: {created_count} جديد.")
        return created_count

    @classmethod
    def seed_all(cls, user=None):
        """
        تشغيل حزمة التثبيت بالكامل لمعالجة أنواع الموردين وخدمات التسعير
        داخل معاملة ذرية واحدة (Atomic Transaction).
        """
        with transaction.atomic():
            supp_count = cls.seed_supplier_types(created_by=user)
            serv_count = cls.seed_service_types()
            logger.info(f"✅ اكتمل تثبيت بيئة الموردين لموديول التسعير ({supp_count} أنواع موردين، {serv_count} خدمات).")
            return {
                "supplier_types_created": supp_count,
                "service_types_created": serv_count,
            }

    @classmethod
    def get_recommended_services(cls, supplier_type_code):
        """
        إرجاع قائمة رموز الخدمات الموصى بها لنوع مورد محدد
        """
        return cls.SUPPLIER_TYPE_SERVICE_MAP.get(supplier_type_code, [])
