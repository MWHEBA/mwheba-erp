"""
نظام تحميل البيانات الموحد للخدمات المتخصصة
يوفر واجهة موحدة لتحميل وحفظ بيانات جميع أنواع الخدمات
"""

from django.shortcuts import get_object_or_404
from .models import SpecializedService
from .field_registry import (
    FIELD_REGISTRY,
    get_field_config,
    get_service_fields,
    get_field_choices,
)


class ServiceDataLoader:
    """
    فئة تحميل البيانات الموحدة للخدمات
    """

    def __init__(self, service_type):
        self.service_type = service_type
        self.field_config = get_service_fields(service_type)

    def load_service_data(self, service_id):
        """
        تحميل بيانات خدمة معينة
        """
        service = get_object_or_404(SpecializedService, id=service_id)

        # التأكد من أن نوع الخدمة صحيح
        if service.category.code != self.service_type:
            raise ValueError(
                f"Service type mismatch: expected {self.service_type}, got {service.category.code}"
            )

        # جمع البيانات من جميع المصادر
        data = {}

        for field_name, field_config in self.field_config.items():
            db_field = field_config["db_field"]
            value = self._get_field_value(service, db_field)
            data[field_name] = value

        # إضافة الشرائح السعرية (فقط للخدمات التي تدعمها)
        if self.service_type in ["digital_printing", "offset_printing"]:
            price_tiers = []
            for tier in service.price_tiers.all().order_by("min_quantity"):
                price_tiers.append(
                    {
                        "id": tier.id,
                        "tier_name": tier.tier_name,
                        "min_quantity": tier.min_quantity,
                        "max_quantity": tier.max_quantity,
                        "price_per_unit": float(tier.price_per_unit),
                        "floor_price": float(tier.floor_price)
                        if tier.floor_price
                        else None,
                        "discount_percentage": float(tier.discount_percentage),
                    }
                )

            data["price_tiers"] = price_tiers

        return data

    def _get_field_value(self, service, db_field_path):
        """
        جلب قيمة حقل من مسار قاعدة البيانات
        """
        try:
            # تقسيم المسار (مثل: offset_details.machine_type)
            path_parts = db_field_path.split(".")

            # البدء من كائن الخدمة
            current_obj = service

            # التنقل عبر المسار
            for part in path_parts:
                if hasattr(current_obj, part):
                    current_obj = getattr(current_obj, part)
                else:
                    return None

            return current_obj

        except Exception:
            return None

    def save_service_data(self, service_id, data):
        """
        حفظ بيانات خدمة معينة
        """
        service = get_object_or_404(SpecializedService, id=service_id)

        # التأكد من أن نوع الخدمة صحيح
        if service.category.code != self.service_type:
            raise ValueError(
                f"Service type mismatch: expected {self.service_type}, got {service.category.code}"
            )

        # حفظ البيانات في الحقول المناسبة
        for field_name, value in data.items():
            if field_name in self.field_config:
                field_config = self.field_config[field_name]
                db_field = field_config["db_field"]
                self._set_field_value(service, db_field, value)

        # حفظ الخدمة الأساسية
        service.save()

        # حفظ التفاصيل المتخصصة
        self._save_related_details(service)

    def _set_field_value(self, service, db_field_path, value):
        """
        تعيين قيمة حقل في مسار قاعدة البيانات
        """
        try:
            path_parts = db_field_path.split(".")

            if len(path_parts) == 1:
                # حقل مباشر في الخدمة
                setattr(service, path_parts[0], value)
            else:
                # حقل في كائن متعلق
                related_obj_name = path_parts[0]
                field_name = path_parts[1]

                # جلب الكائن المتعلق
                if hasattr(service, related_obj_name):
                    related_obj = getattr(service, related_obj_name)
                    if related_obj:
                        setattr(related_obj, field_name, value)

        except Exception as e:
            print(f"Error setting field {db_field_path}: {e}")

    def _save_related_details(self, service):
        """
        حفظ التفاصيل المتعلقة بالخدمة
        """
        try:
            if self.service_type == "offset_printing" and hasattr(
                service, "offset_details"
            ):
                service.offset_details.save()
            elif self.service_type == "digital_printing" and hasattr(
                service, "digital_details"
            ):
                service.digital_details.save()
            elif self.service_type == "plates" and hasattr(service, "plate_details"):
                service.plate_details.save()
        except Exception as e:
            print(f"Error saving related details: {e}")

    def get_field_mapping(self):
        """
        إرجاع خريطة الحقول للواجهة الأمامية
        """
        mapping = {}

        for field_name, field_config in self.field_config.items():
            mapping[field_name] = {
                "input_type": field_config.get("input_type"),
                "required": field_config.get("required", False),
                "readonly": field_config.get("readonly", False),
                "validation": field_config.get("validation"),
                "choices": self._get_field_choices(field_config),
                "attributes": self._get_field_attributes(field_config),
            }

        return mapping

    def _get_field_choices(self, field_config):
        """
        جلب خيارات الحقل إذا كان من نوع select
        """
        if field_config.get("input_type") == "select":
            choices_source = field_config.get("choices_source")
            if choices_source:
                return get_field_choices(choices_source)
        return []

    def _get_field_attributes(self, field_config):
        """
        جلب خصائص HTML للحقل
        """
        attributes = {}

        # إضافة الخصائص المختلفة
        if "min" in field_config:
            attributes["min"] = field_config["min"]
        if "max" in field_config:
            attributes["max"] = field_config["max"]
        if "step" in field_config:
            attributes["step"] = field_config["step"]
        if "default" in field_config:
            attributes["default"] = field_config["default"]

        return attributes

    @staticmethod
    def get_loader_for_service(service_id):
        """
        إنشاء loader مناسب لخدمة معينة
        """
        service = get_object_or_404(SpecializedService, id=service_id)
        service_type = service.category.code
        return ServiceDataLoader(service_type)

    @staticmethod
    def validate_field_value(service_type, field_name, value):
        """
        التحقق من صحة قيمة حقل
        """
        field_config = get_field_config(service_type, field_name)
        if not field_config:
            return False, "Field not found"

        # التحقق من الحقول المطلوبة
        if field_config.get("required", False) and not value:
            return False, "Field is required"

        # التحقق من نوع البيانات
        validation = field_config.get("validation")
        if validation == "positive_number":
            try:
                num_value = float(value)
                if num_value < 0:
                    return False, "Value must be positive"
            except (ValueError, TypeError):
                return False, "Value must be a number"

        return True, "Valid"
