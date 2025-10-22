from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Supplier, SpecializedService, SupplierType, SupplierTypeSettings
from django.contrib import messages
import json
import logging

# إعداد logger
logger = logging.getLogger(__name__)

# استيراد النظام الجديد
from .service_data_loader import ServiceDataLoader
from .field_registry import get_service_fields, get_field_choices

from .models import (
    Supplier,
    SupplierType,
    SpecializedService,
    ServicePriceTier,
    PaperServiceDetails,
    DigitalPrintingDetails,
    FinishingServiceDetails,
    OffsetPrintingDetails,
    PlateServiceDetails,
    OutdoorPrintingDetails,
)

# استيراد ServiceFormFactory مع معالجة الأخطاء
try:
    from .forms.dynamic_forms import ServiceFormFactory
except ImportError:
    # في حالة عدم وجود الملف، إنشاء ServiceFormFactory بسيط
    class ServiceFormFactory:
        @staticmethod
        def get_form_for_category(category_code, *args, **kwargs):
            return None

        @staticmethod
        def get_form_choices_for_category(category_code):
            return get_field_choices(category_code)


# API لتحميل النماذج
@login_required
def get_category_form_api(request):
    """API لجلب نموذج التصنيف"""
    try:
        category_code = request.GET.get("category")
        supplier_id = request.GET.get("supplier_id")

        if not category_code:
            return JsonResponse({"error": "نوع التصنيف مطلوب"}, status=400)

        category = SupplierType.objects.get(code=category_code, is_active=True)

        # تحديد template النموذج - المسارات الجديدة المنظمة
        template_map = {
            "paper": "supplier/forms/paper_form.html",
            "offset_printing": "supplier/forms/offset_form.html",
            "digital_printing": "supplier/forms/digital_form.html",
            "finishing": "supplier/forms/finishing_form.html",
            "plates": "supplier/forms/plates_form.html",
            "packaging": "supplier/forms/packaging_form.html",
            "coating": "supplier/forms/coating_form.html",
        }

        template_name = template_map.get(category_code)
        if not template_name:
            return JsonResponse({"error": "نوع التصنيف غير مدعوم"}, status=400)

        # إضافة خيارات النموذج حسب النوع من قاعدة البيانات
        form_choices = {}

        if category_code == "offset_printing":
            # استخدام النظام الموحد لجلب بيانات الأوفست
            from .forms.dynamic_forms import ServiceFormFactory
            form_choices.update(ServiceFormFactory.get_unified_offset_choices())

        elif category_code == "digital_printing":
            # جلب أنواع ماكينات الديجيتال من الإعدادات
            try:
                from printing_pricing.models.settings_models import DigitalMachineType, DigitalSheetSize

                machine_types = DigitalMachineType.objects.filter(
                    is_active=True
                ).order_by("name")
                paper_sizes = DigitalSheetSize.objects.filter(is_active=True).order_by(
                    "name"
                )

                if machine_types.exists() and paper_sizes.exists():
                    form_choices.update(
                        {
                            "machine_types": [
                                (mt.code if mt.code else f"mt_{mt.id}", mt.name)
                                for mt in machine_types
                            ],
                            "paper_sizes": [
                                (
                                    ps.code if ps.code else f"ps_{ps.id}",
                                    f"{ps.name} ({int(ps.width_cm)}×{int(ps.height_cm)} سم)",
                                )
                                for ps in paper_sizes
                            ],
                        }
                    )
                else:
                    # لا توجد بيانات في قاعدة البيانات - استخدام field_registry
                    form_choices.update(
                        {
                            "machine_types": get_field_choices("digital_machine_types"),
                            "paper_sizes": get_field_choices("digital_paper_sizes"),
                        }
                    )

            except Exception as e:
                # خطأ في جلب البيانات - استخدام field_registry كـ fallback
                print(f"ERROR in digital_printing: {e}")
                form_choices.update(
                    {
                        "machine_types": get_field_choices("digital_machine_types"),
                        "paper_sizes": get_field_choices("digital_paper_sizes"),
                    }
                )

        elif category_code == "plates":
            # إعداد خيارات مقاسات الزنك
            form_choices.update(
                {
                    "plate_sizes": [
                        ("quarter_sheet", "ربع (35×50 سم)"),
                        ("half_sheet", "نص (50×70 سم)"),
                        ("full_sheet", "فرخ (70×100 سم)"),
                        ("custom", "مقاس مخصوص"),
                    ]
                }
            )

        elif category_code == "paper":
            # استخدام النظام الموحد لجلب بيانات الورق
            from .forms.dynamic_forms import ServiceFormFactory
            form_choices.update(ServiceFormFactory.get_unified_paper_choices())

        elif category_code == "finishing":
            # إعداد خيارات خدمات التشطيب
            form_choices.update(
                {
                    "finishing_types": [
                        ("cutting", "قص"),
                        ("folding", "طي"),
                        ("binding", "تجليد"),
                        ("lamination", "تقفيل"),
                        ("varnish", "ورنيش"),
                    ]
                }
            )

        elif category_code == "packaging":
            # إعداد خيارات خدمات التقفيل
            form_choices.update(
                {
                    "packaging_types": [
                        ("lamination", "تقفيل"),
                        ("cellophane", "سيلوفان"),
                        ("shrink_wrap", "تغليف حراري"),
                        ("box_packaging", "تعبئة في صناديق"),
                        ("custom_packaging", "تعبئة مخصصة"),
                    ]
                }
            )

        elif category_code == "coating":
            # جلب أنواع التغطية من الإعدادات
            try:
                from printing_pricing.models.settings_models import CoatingType
                
                coating_types = CoatingType.objects.filter(is_active=True).order_by('name')
                
                if coating_types.exists():
                    form_choices.update(
                        {
                            "coating_types": [
                                (ct.id, ct.name) for ct in coating_types
                            ]
                        }
                    )
                else:
                    # بيانات افتراضية في حالة عدم وجود بيانات
                    form_choices.update(
                        {
                            "coating_types": [
                                ("varnish", "ورنيش"),
                                ("uv_coating", "طلاء UV"),
                                ("aqueous_coating", "طلاء مائي"),
                                ("spot_uv", "UV نقطي"),
                                ("matte_coating", "طلاء مطفي"),
                            ]
                        }
                    )
            except Exception as e:
                # في حالة الخطأ، استخدام البيانات الافتراضية
                print(f"ERROR in coating types: {e}")
                form_choices.update(
                    {
                        "coating_types": [
                            ("varnish", "ورنيش"),
                            ("uv_coating", "طلاء UV"),
                            ("aqueous_coating", "طلاء مائي"),
                            ("spot_uv", "UV نقطي"),
                            ("matte_coating", "طلاء مطفي"),
                        ]
                    }
                )

        # إعداد البيانات للنموذج
        context = {
            "category": category,
            "supplier_id": supplier_id,
            "form_choices": form_choices,
        }

        # رندر النموذج
        html = render_to_string(template_name, context, request=request)

        return JsonResponse(
            {
                "success": True,
                "html": html,
                "category_name": category.name,
                "category_code": category_code,
            }
        )

    except SupplierType.DoesNotExist:
        return JsonResponse({"error": "التصنيف المحدد غير موجود"}, status=404)
    except Exception as e:
        import traceback

        error_details = traceback.format_exc()
        print(f"ERROR in get_category_form_api: {error_details}")
        return JsonResponse({"error": f"خطأ في الخادم: {str(e)}"}, status=500)


# ===== النظام الجديد الموحد =====


@login_required
def get_service_data_universal(request, service_id):
    """
    API موحد لجلب بيانات أي خدمة
    """
    try:
        # إنشاء loader مناسب للخدمة
        loader = ServiceDataLoader.get_loader_for_service(service_id)

        # تحميل البيانات
        service_data = loader.load_service_data(service_id)

        # جلب خريطة الحقول
        field_mapping = loader.get_field_mapping()

        return JsonResponse(
            {
                "success": True,
                "service_data": service_data,
                "field_mapping": field_mapping,
                "service_type": loader.service_type,
            }
        )

    except Exception as e:
        return JsonResponse({"error": f"خطأ في جلب البيانات: {str(e)}"}, status=500)


@login_required
def save_service_data_universal(request):
    """
    API موحد لحفظ بيانات أي خدمة جديدة
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST method required"}, status=405)

    import time
    from django.db import OperationalError
    
    # محاولة حفظ البيانات مع إعادة المحاولة في حالة قفل قاعدة البيانات
    max_retries = 3
    retry_delay = 0.1  # 100ms
    
    for attempt in range(max_retries):
        try:
            with transaction.atomic():
                data = json.loads(request.body)
                supplier_id = data.get("supplier_id")
                service_type = data.get("service_type")
                
                # التحقق من البيانات الأساسية
                if not supplier_id or not service_type:
                    return JsonResponse(
                        {"error": "بيانات المورد ونوع الخدمة مطلوبة"}, status=400
                    )

                # التحقق من وجود المورد والتصنيف
                supplier = get_object_or_404(Supplier, id=supplier_id)
                category = get_object_or_404(SupplierType, code=service_type)

                # إنشاء الخدمة الأساسية
                service = SpecializedService.objects.create(
                    supplier=supplier,
                    category=category,
                    name=data.get("name", ""),
                    description=data.get("description", ""),
                    setup_cost=data.get("setup_cost", 0),
                    is_active=data.get("is_active", True),
                )

                # إنشاء التفاصيل المتخصصة
                _create_service_details(service, service_type)

                # حفظ التفاصيل المتخصصة بالبيانات الفعلية
                _save_category_details(service, service_type, data)

                # حفظ الشرائح السعرية إذا وجدت
                if data.get("price_tiers"):
                    _save_price_tiers(service, data["price_tiers"])

                return JsonResponse(
                    {
                        "success": True,
                        "service_id": service.id,
                        "service_name": service.name,
                        "message": "تم حفظ الخدمة بنجاح",
                        "redirect_url": reverse(
                            "supplier:supplier_detail", args=[supplier_id]
                        ),
                    }
                )

        except OperationalError as e:
            if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                # انتظار قصير ثم إعادة المحاولة
                time.sleep(retry_delay * (attempt + 1))
                continue
            else:
                return JsonResponse({"error": f"خطأ في قاعدة البيانات: {str(e)}"}, status=500)
        except Exception as e:
            return JsonResponse({"error": f"خطأ في حفظ البيانات: {str(e)}"}, status=500)
    
    return JsonResponse({"error": "فشل في حفظ البيانات بعد عدة محاولات"}, status=500)


@login_required
def update_service_data_universal(request, service_id):
    """
    API موحد لتحديث بيانات أي خدمة
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST method required"}, status=405)

    import time
    from django.db import OperationalError
    
    # محاولة تحديث البيانات مع إعادة المحاولة في حالة قفل قاعدة البيانات
    max_retries = 3
    retry_delay = 0.1  # 100ms
    
    for attempt in range(max_retries):
        try:
            with transaction.atomic():
                data = json.loads(request.body)

                # إنشاء loader مناسب للخدمة
                loader = ServiceDataLoader.get_loader_for_service(service_id)

                # حفظ البيانات
                loader.save_service_data(service_id, data)

                # تحديث الشرائح السعرية إذا وجدت
                service = get_object_or_404(SpecializedService, id=service_id)
                if data.get("price_tiers") is not None:
                    # حذف الشرائح القديمة وإنشاء جديدة
                    service.price_tiers.all().delete()
                    if data["price_tiers"]:
                        _save_price_tiers(service, data["price_tiers"])

                return JsonResponse(
                    {
                        "success": True,
                        "service_id": service.id,
                        "service_name": service.name,
                        "message": "تم تحديث الخدمة بنجاح",
                        "redirect_url": reverse(
                            "supplier:supplier_detail", args=[service.supplier.id]
                        ),
                    }
                )

        except OperationalError as e:
            if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                # انتظار قصير ثم إعادة المحاولة
                time.sleep(retry_delay * (attempt + 1))
                continue
            else:
                return JsonResponse({"error": f"خطأ في قاعدة البيانات: {str(e)}"}, status=500)
        except Exception as e:
            return JsonResponse({"error": f"خطأ في تحديث البيانات: {str(e)}"}, status=500)
    
    return JsonResponse({"error": "فشل في تحديث البيانات بعد عدة محاولات"}, status=500)


@login_required
def get_field_mapping_api(request, service_type):
    """
    API لجلب خريطة الحقول لنوع خدمة معين
    """
    try:
        loader = ServiceDataLoader(service_type)
        field_mapping = loader.get_field_mapping()

        return JsonResponse(
            {
                "success": True,
                "field_mapping": field_mapping,
                "service_type": service_type,
            }
        )

    except Exception as e:
        return JsonResponse({"error": f"خطأ في جلب خريطة الحقول: {str(e)}"}, status=500)


def _create_service_details(service, service_type):
    """
    إنشاء التفاصيل المتخصصة للخدمة
    """
    if service_type == "offset_printing":
        OffsetPrintingDetails.objects.create(
            service=service,
            machine_type="",
            sheet_size="",
            max_colors=4,
            impression_cost_per_1000=0,
            special_impression_cost=0,
            break_impression_cost=0,
        )
    elif service_type == "digital_printing":
        DigitalPrintingDetails.objects.create(
            service=service,
            machine_type="laser_mono",
            machine_model="",
            paper_handling="sheet_fed",
            paper_size="a4",
            price_per_page_bw=0,
            price_per_page_color=0,
        )
    elif service_type == "plates":
        PlateServiceDetails.objects.create(
            service=service, plate_size="", price_per_plate=0
        )
    elif service_type == "paper":
        PaperServiceDetails.objects.create(
            service=service,
            paper_type="",
            gsm=80,  # قيمة افتراضية
            sheet_size="",
            custom_width=None,
            custom_height=None,
            country_of_origin="",
            brand="",
            price_per_sheet=0,
        )
    elif service_type == "packaging":
        # إنشاء تفاصيل التقفيل كخدمة تشطيب
        FinishingServiceDetails.objects.create(
            service=service,
            finishing_type="lamination",
            calculation_method="per_piece",
            price_per_unit=0,
            setup_time_minutes=15,
            turnaround_time_hours=4,
        )
    elif service_type == "coating":
        # إنشاء تفاصيل التغطية كخدمة تشطيب - بدون قيم افتراضية
        # سيتم تحديث البيانات لاحقاً في _save_category_details
        FinishingServiceDetails.objects.create(
            service=service,
            finishing_type="varnish",  # مؤقت - سيتم تحديثه
            calculation_method="per_piece",  # مؤقت - سيتم تحديثه
            price_per_unit=0,
            setup_time_minutes=30,
            turnaround_time_hours=6,
        )


@login_required
def delete_specialized_service_api(request, service_id):
    """API لحذف الخدمة المتخصصة"""
    if request.method != "DELETE":
        return JsonResponse({"error": "DELETE method required"}, status=405)

    try:
        service = get_object_or_404(SpecializedService, id=service_id)
        service_name = service.name
        supplier_id = service.supplier.id

        service.delete()

        return JsonResponse(
            {
                "success": True,
                "message": f'تم حذف الخدمة "{service_name}" بنجاح',
                "supplier_id": supplier_id,
            }
        )

    except Exception as e:
        return JsonResponse({"error": f"خطأ في حذف الخدمة: {str(e)}"}, status=500)


def get_service_details_api(request, service_id):
    """API لجلب تفاصيل الخدمة للتعديل"""
    # التحقق من تسجيل الدخول
    if not request.user.is_authenticated:
        return JsonResponse({"error": "تسجيل الدخول مطلوب"}, status=401)

    try:
        service = get_object_or_404(SpecializedService, id=service_id)
        category_code = service.category.code

        service_data = {
            "id": service.id,
            "name": service.name,
            "description": service.description,
            "setup_cost": float(service.setup_cost),
            "is_active": service.is_active,
            "category_code": category_code,
            "category_name": service.category.name,
        }

        # التفاصيل المتخصصة
        if category_code == "digital_printing" and hasattr(service, "digital_details"):
            details = service.digital_details
            service_data.update(
                {
                    "machine_type": details.machine_type,
                    "machine_model": details.machine_model,
                    "paper_handling": details.paper_handling,
                    "paper_size": details.paper_size,
                    "price_per_page_bw": float(details.price_per_page_bw),
                    "price_per_page_color": float(details.price_per_page_color),
                }
            )
        elif category_code == "offset_printing" and hasattr(service, "offset_details"):
            details = service.offset_details
            service_data.update(
                {
                    "machine_type": details.machine_type,
                    "sheet_size": details.sheet_size,
                    "max_colors": details.max_colors,
                    "impression_cost_per_1000": float(details.impression_cost_per_1000),
                    "special_impression_cost": float(details.special_impression_cost),
                    "break_impression_cost": float(details.break_impression_cost),
                }
            )
        elif category_code == "plates" and hasattr(service, "plate_details"):
            details = service.plate_details
            service_data.update(
                {
                    "plate_size": details.plate_size,
                    "price_per_plate": float(details.price_per_plate),
                    "set_price": float(details.set_price)
                    if details.set_price
                    else None,
                }
            )
        elif category_code == "paper" and hasattr(service, "paper_details"):
            details = service.paper_details
            
            # تحويل القيم القديمة للجديدة
            from .forms.dynamic_forms import ServiceFormFactory
            converted_sheet_size = ServiceFormFactory.convert_legacy_sheet_size(details.sheet_size)
            converted_paper_type = ServiceFormFactory.convert_legacy_paper_type(details.paper_type)
            
            service_data.update(
                {
                    "paper_type": converted_paper_type,
                    "gsm": details.gsm,
                    "sheet_size": converted_sheet_size,
                    "custom_width": float(details.custom_width) if details.custom_width else None,
                    "custom_height": float(details.custom_height) if details.custom_height else None,
                    "country_of_origin": details.country_of_origin,
                    "brand": details.brand,
                    "price_per_sheet": float(details.price_per_sheet),
                }
            )
        elif category_code == "packaging" and hasattr(service, "finishing_details"):
            details = service.finishing_details
            service_data.update(
                {
                    "packaging_type": details.finishing_type,
                    "calculation_method": details.calculation_method,
                    "price_per_unit": float(details.price_per_unit),
                    "setup_time_minutes": details.setup_time_minutes,
                    "turnaround_time_hours": details.turnaround_time_hours,
                }
            )
        elif category_code == "coating" and hasattr(service, "finishing_details"):
            details = service.finishing_details
            service_data.update(
                {
                    "coating_type": details.finishing_type,
                    "calculation_method": details.calculation_method,
                    "price_per_unit": float(details.price_per_unit),
                    "setup_time_minutes": details.setup_time_minutes,
                    "turnaround_time_hours": details.turnaround_time_hours,
                }
            )

        # الشرائح السعرية
        price_tiers = []
        tiers_queryset = service.price_tiers.all().order_by("min_quantity")

        for tier in tiers_queryset:
            tier_data = {
                "id": tier.id,
                "tier_name": tier.tier_name,
                "min_quantity": tier.min_quantity,
                "max_quantity": tier.max_quantity,
                "price_per_unit": float(tier.price_per_unit),
                "floor_price": float(tier.floor_price) if tier.floor_price else None,
                "discount_percentage": float(tier.discount_percentage),
            }
            price_tiers.append(tier_data)

        service_data["price_tiers"] = price_tiers

        return JsonResponse({"success": True, "service_data": service_data})

    except Exception as e:
        return JsonResponse({"error": f"خطأ في جلب البيانات: {str(e)}"}, status=500)


# دوال مساعدة لحفظ التفاصيل المتخصصة
def _save_category_details(service, category_code, data):
    """حفظ التفاصيل المتخصصة حسب نوع الخدمة"""

    if category_code == "paper":
        # دالة مساعدة لتحويل القيم الآمن
        def safe_float(value, default=0):
            if value is None or value == "" or value == "None":
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default

        def safe_int(value, default=0):
            if value is None or value == "" or value == "None":
                return default
            try:
                return int(value)
            except (ValueError, TypeError):
                return default

        # تحديث التفاصيل الموجودة بدلاً من إنشاء جديدة
        paper_details = service.paper_details
        
        
        paper_details.paper_type = data.get("paper_type", "")
        paper_details.gsm = safe_int(data.get("gsm"), 80)
        paper_details.sheet_size = data.get("sheet_size", "")
        paper_details.custom_width = safe_float(data.get("custom_width"))
        paper_details.custom_height = safe_float(data.get("custom_height"))
        paper_details.country_of_origin = data.get("country_of_origin", "")
        paper_details.brand = data.get("brand", "")
        paper_details.price_per_sheet = safe_float(data.get("price_per_sheet"))
        paper_details.save()

    elif category_code == "offset_printing":
        # التحقق من الحقول المطلوبة
        machine_type = data.get("machine_type")
        sheet_size = data.get("sheet_size")
        impression_cost = data.get("impression_cost_per_1000", 0)

        if not machine_type or not sheet_size:
            raise ValueError("نوع الماكينة ومقاس الفرخ مطلوبان")

        # دالة مساعدة لتحويل القيم الآمن
        def safe_float(value, default=0):
            if value is None or value == "" or value == "None":
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default

        def safe_int(value, default=0):
            if value is None or value == "" or value == "None":
                return default
            try:
                return int(value)
            except (ValueError, TypeError):
                return default

        # تحديث التفاصيل الموجودة بدلاً من إنشاء جديدة
        offset_details = service.offset_details
        
        offset_details.machine_type = machine_type
        offset_details.sheet_size = sheet_size
        offset_details.max_colors = safe_int(data.get("max_colors"), 4)
        offset_details.impression_cost_per_1000 = safe_float(impression_cost)
        offset_details.special_impression_cost = safe_float(data.get("special_impression_cost"))
        offset_details.break_impression_cost = safe_float(data.get("break_impression_cost"))
        offset_details.setup_cost = safe_float(data.get("setup_cost"))
        offset_details.has_uv_coating = data.get("has_uv_coating", False)
        offset_details.has_aqueous_coating = data.get("has_aqueous_coating", False)
        offset_details.save()

        # تحديث اسم الخدمة تلقائياً (للخدمات الجديدة والمحدثة)
        def should_update_name():
            """تحديد ما إذا كان يجب تحديث اسم الخدمة"""
            # إذا كان الاسم فارغ، حدثه
            if not service.name or service.name.strip() == "":
                return True
            
            # إذا كان الاسم يحتوي على نمط الاسم التلقائي، حدثه
            auto_name_patterns = [
                "ماكينة", "خدمة أوفست", "لون", "SM", "GTO", "LS", "ريوبي", "كوموري", "هايدلبرج"
            ]
            return any(pattern in service.name for pattern in auto_name_patterns)
        
        if should_update_name():
            try:
                machine_display = offset_details.get_machine_type_display()
                size_display = offset_details.get_sheet_size_display()
                colors = offset_details.max_colors
                
                if machine_display and size_display:
                    # استخراج اسم الماكينة فقط (بدون الشركة)
                    machine_name = machine_display.split(' - ')[-1] if ' - ' in machine_display else machine_display
                    # تبسيط اسم المقاس
                    size_simple = size_display.split(' (')[0] if ' (' in size_display else size_display
                    
                    new_name = f"ماكينة {size_simple} - {colors} لون - {machine_name}"
                    
                    # تحديث الاسم فقط إذا تغير
                    if service.name != new_name:
                        service.name = new_name
                        service.save()
            except Exception as e:
                # في حالة فشل إنشاء الاسم، استخدم اسم افتراضي
                if not service.name or service.name.strip() == "":
                    service.name = f"خدمة أوفست - {machine_type}"
                    service.save()

    elif category_code == "plates":
        # دالة مساعدة لتحويل القيم الآمن
        def safe_float(value, default=0):
            if value is None or value == "" or value == "None":
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default

        # تحديث التفاصيل الموجودة بدلاً من إنشاء جديدة
        plate_details = service.plate_details
        
        # استخدام النظام الموحد لتطبيع البيانات
        from .forms.dynamic_forms import ServiceFormFactory
        normalized_data = ServiceFormFactory.normalize_legacy_ctp_data(
            plate_size=data.get("plate_size")
        )
        
        plate_details.plate_size = normalized_data.get("plate_size", data.get("plate_size", ""))
        plate_details.custom_width_cm = safe_float(data.get("custom_width_cm"))
        plate_details.custom_height_cm = safe_float(data.get("custom_height_cm"))
        plate_details.price_per_plate = safe_float(data.get("price_per_plate"))
        plate_details.set_price = safe_float(data.get("set_price"))
        plate_details.save()

        # تحديث اسم الخدمة تلقائياً
        if not service.name or service.name.strip() == "":
            plate_size_display = plate_details.plate_size
            if plate_size_display == "35.00x50.00":
                size_name = "ربع فرخ"
            elif plate_size_display == "50.00x70.00":
                size_name = "نصف فرخ"
            elif plate_size_display == "70.00x100.00":
                size_name = "فرخ كامل"
            elif plate_size_display == "custom":
                size_name = "مقاس مخصص"
            else:
                size_name = plate_size_display
            
            service.name = f"زنك CTP - {size_name}"
            service.save()

    elif category_code == "packaging":
        # دالة مساعدة لتحويل القيم الآمن
        def safe_float(value, default=0):
            if value is None or value == "" or value == "None":
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default

        def safe_int(value, default=0):
            if value is None or value == "" or value == "None":
                return default
            try:
                return int(value)
            except (ValueError, TypeError):
                return default

        # تحديث التفاصيل الموجودة بدلاً من إنشاء جديدة
        finishing_details = service.finishing_details
        
        finishing_details.finishing_type = data.get("packaging_type", "lamination")
        finishing_details.calculation_method = data.get("calculation_method", "per_piece")
        finishing_details.price_per_unit = safe_float(data.get("price_per_unit"))
        finishing_details.setup_time_minutes = safe_int(data.get("setup_time_minutes"), 15)
        finishing_details.turnaround_time_hours = safe_int(data.get("turnaround_time_hours"), 4)
        finishing_details.save()

        # تحديث اسم الخدمة تلقائياً
        if not service.name or service.name.strip() == "":
            packaging_type_display = dict([
                ("lamination", "تقفيل"),
                ("cellophane", "سيلوفان"),
                ("shrink_wrap", "تغليف حراري"),
                ("box_packaging", "تعبئة في صناديق"),
                ("custom_packaging", "تعبئة مخصصة"),
            ]).get(finishing_details.finishing_type, finishing_details.finishing_type)
            
            service.name = f"خدمة {packaging_type_display}"
            service.save()

    elif category_code == "coating":
        # دالة مساعدة لتحويل القيم الآمن
        def safe_float(value, default=0):
            if value is None or value == "" or value == "None":
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default

        def safe_int(value, default=0):
            if value is None or value == "" or value == "None":
                return default
            try:
                return int(value)
            except (ValueError, TypeError):
                return default

        # تحديث التفاصيل الموجودة بدلاً من إنشاء جديدة
        finishing_details = service.finishing_details
        
        # استخدام البيانات الفعلية من النموذج بدون قيم افتراضية خاطئة
        print(f"DEBUG: coating data received: {data}")  # للتشخيص
        print(f"DEBUG: all keys in data: {list(data.keys())}")  # للتشخيص
        
        coating_type = data.get("coating_type")
        if not coating_type or str(coating_type).strip() == "":
            # محاولة البحث عن أسماء بديلة للحقل
            coating_type = data.get("finishing_type") or data.get("type")
            if not coating_type or str(coating_type).strip() == "":
                raise ValueError(f"نوع التغطية مطلوب. البيانات المستلمة: {data}")
            
        calculation_method = data.get("calculation_method")
        if not calculation_method or str(calculation_method).strip() == "":
            raise ValueError(f"طريقة الحساب مطلوبة. البيانات المستلمة: calculation_method='{calculation_method}'")
            
        finishing_details.finishing_type = coating_type
        finishing_details.calculation_method = calculation_method
        # استخدام base_price من النموذج
        finishing_details.price_per_unit = safe_float(data.get("base_price", data.get("price_per_unit", 0)))
        finishing_details.setup_time_minutes = safe_int(data.get("setup_time_minutes"), 30)
        finishing_details.turnaround_time_hours = safe_int(data.get("turnaround_time_hours"), 6)
        finishing_details.save()

        # تحديث اسم الخدمة تلقائياً
        if not service.name or service.name.strip() == "":
            # محاولة جلب اسم نوع التغطية من CoatingType model
            try:
                from printing_pricing.models.settings_models import CoatingType
                coating_type_obj = CoatingType.objects.get(id=coating_type)
                coating_type_display = coating_type_obj.name
            except (CoatingType.DoesNotExist, ValueError):
                # في حالة عدم وجود النوع، استخدام قاموس الأسماء الافتراضية
                coating_type_display = dict([
                    ("varnish", "ورنيش"),
                    ("uv_coating", "طلاء UV"),
                    ("aqueous_coating", "طلاء مائي"),
                    ("spot_uv", "UV نقطي"),
                    ("matte_coating", "طلاء مطفي"),
                ]).get(coating_type, coating_type)
            
            service.name = f"خدمة {coating_type_display}"
            service.save()


def _save_price_tiers(service, tiers_data):
    """حفظ الشرائح السعرية"""
    for tier_data in tiers_data:
        ServicePriceTier.objects.create(
            service=service,
            tier_name=tier_data.get("tier_name", ""),
            min_quantity=tier_data.get("min_quantity"),
            max_quantity=tier_data.get("max_quantity"),
            price_per_unit=tier_data.get("price_per_unit"),
            floor_price=tier_data.get("floor_price"),
            discount_percentage=tier_data.get("discount_percentage", 0),
        )


class SupplierTypesStylesAPIView(View):
    """API لجلب أنماط أنواع الموردين (الأيقونات والألوان)"""
    
    def get(self, request):
        try:
            # جلب الأنواع النشطة مع إعداداتها
            supplier_types = SupplierType.objects.filter(
                settings__is_active=True
            ).select_related('settings').order_by('settings__display_order', 'name')
            
            types_data = []
            for supplier_type in supplier_types:
                if supplier_type.settings:
                    types_data.append({
                        'id': supplier_type.id,
                        'code': supplier_type.code,
                        'name': supplier_type.settings.name,  # استخدام الاسم الديناميكي
                        'icon': supplier_type.settings.icon,
                        'color': supplier_type.settings.color,
                        'description': supplier_type.settings.description or ''
                    })
            
            return JsonResponse({
                'success': True,
                'types': types_data,
                'total_count': len(types_data)
            })
            
        except Exception as e:
            logger.error(f"خطأ في جلب أنماط أنواع الموردين: {e}")
            return JsonResponse({
                'success': False,
                'error': 'فشل في جلب أنماط أنواع الموردين'
            }, status=500)
