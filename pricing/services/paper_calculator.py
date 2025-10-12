"""
خدمة حسابات الورق المتخصصة
"""
from decimal import Decimal
from ..models import PaperType, PaperSize
from supplier.models import PaperServiceDetails


class PaperCalculatorService:
    """خدمة حسابات الورق"""

    @staticmethod
    def calculate_paper_cost(
        supplier_id, paper_type_id, paper_size_id, weight, quantity, origin="local"
    ):
        """حساب تكلفة الورق"""
        try:
            # البحث عن خدمة الورق
            paper_service = PaperServiceDetails.find_paper_service(
                supplier_id=supplier_id,
                paper_type_id=paper_type_id,
                paper_size_id=paper_size_id,
                weight=weight,
                origin=origin,
            )

            if not paper_service:
                return {"success": False, "error": "لم يتم العثور على سعر للورق المحدد"}

            # حساب التكلفة حسب نوع الورقة
            if paper_service.sheet_type == "sheet":
                cost = quantity * paper_service.price_per_sheet
                unit_type = "ورقة"
                unit_price = paper_service.price_per_sheet
            else:  # roll
                # حساب الوزن المطلوب
                paper_size = PaperSize.objects.get(id=paper_size_id)
                paper_area = paper_size.width * paper_size.height / 10000  # متر مربع
                weight_needed = quantity * paper_area * weight / 1000  # كيلو
                cost = weight_needed * paper_service.price_per_kg
                unit_type = "كيلو"
                unit_price = paper_service.price_per_kg

            return {
                "success": True,
                "total_cost": float(cost),
                "unit_price": float(unit_price),
                "unit_type": unit_type,
                "sheet_type": paper_service.sheet_type,
                "origin": paper_service.origin,
                "minimum_quantity": paper_service.minimum_quantity,
                "supplier_name": paper_service.supplier.name,
                "paper_type_name": paper_service.paper_type.name,
                "paper_size_name": paper_service.paper_size.name,
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في حساب تكلفة الورق: {str(e)}"}

    @staticmethod
    def calculate_sheets_needed(
        quantity, has_internal_content=False, internal_pages=0, waste_percentage=5
    ):
        """حساب عدد الأوراق المطلوبة مع الهدر"""
        sheets = quantity

        # إضافة أوراق المحتوى الداخلي
        if has_internal_content and internal_pages > 0:
            sheets += quantity * internal_pages

        # إضافة نسبة الهدر
        waste_factor = Decimal(str(waste_percentage)) / Decimal("100.0")
        sheets_with_waste = sheets * (Decimal("1.0") + waste_factor)

        return int(sheets_with_waste)

    @staticmethod
    def get_paper_weight_options():
        """الحصول على خيارات أوزان الورق الشائعة"""
        return [
            {"value": 70, "label": "70 جرام"},
            {"value": 80, "label": "80 جرام"},
            {"value": 90, "label": "90 جرام"},
            {"value": 100, "label": "100 جرام"},
            {"value": 120, "label": "120 جرام"},
            {"value": 150, "label": "150 جرام"},
            {"value": 200, "label": "200 جرام"},
            {"value": 250, "label": "250 جرام"},
            {"value": 300, "label": "300 جرام"},
            {"value": 350, "label": "350 جرام"},
        ]

    @staticmethod
    def get_paper_origins():
        """الحصول على خيارات منشأ الورق"""
        return [
            {"value": "local", "label": "محلي"},
            {"value": "imported", "label": "مستورد"},
        ]

    @staticmethod
    def calculate_paper_area(width, height):
        """حساب مساحة الورق بالمتر المربع"""
        return (width * height) / 10000

    @staticmethod
    def calculate_paper_weight_kg(area_m2, quantity, weight_gsm):
        """حساب وزن الورق بالكيلوجرام"""
        return (area_m2 * quantity * weight_gsm) / 1000

    @staticmethod
    def get_paper_suppliers_by_type(paper_type_id, paper_size_id=None, weight=None):
        """الحصول على الموردين حسب نوع الورق"""
        try:
            filters = {"paper_type_id": paper_type_id, "is_active": True}

            if paper_size_id:
                filters["paper_size_id"] = paper_size_id
            if weight:
                filters["weight"] = weight

            services = PaperServiceDetails.objects.filter(**filters).select_related(
                "supplier"
            )

            suppliers = []
            for service in services:
                suppliers.append(
                    {
                        "id": service.supplier.id,
                        "name": service.supplier.name,
                        "price_per_sheet": float(service.price_per_sheet),
                        "price_per_kg": float(service.price_per_kg),
                        "sheet_type": service.sheet_type,
                        "origin": service.origin,
                        "minimum_quantity": service.minimum_quantity,
                    }
                )

            return {"success": True, "suppliers": suppliers}

        except Exception as e:
            return {"success": False, "error": f"خطأ في جلب موردي الورق: {str(e)}"}
