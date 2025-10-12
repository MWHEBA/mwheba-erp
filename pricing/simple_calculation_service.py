"""
خدمة حسابات التسعير المبسطة
Simple Pricing Calculation Service - متوافقة مع البنية الحالية
"""
from django.db import models
from decimal import Decimal
from .models import VATSetting
from supplier.models import (
    PaperServiceDetails,
    PlateServiceDetails,
    DigitalPrintingDetails,
)
from supplier.models import Supplier


class SimplePricingCalculator:
    """حاسبة التسعير المبسطة - متوافقة مع البنية الحالية"""

    @staticmethod
    def calculate_paper_cost(
        paper_type_id, paper_size_id, weight, quantity, supplier_id=None
    ):
        """حساب تكلفة الورق - مبسط"""
        try:
            # البحث عن أفضل خدمة ورق متاحة
            query = PaperServiceDetails.objects.filter(
                paper_type_id=paper_type_id,
                paper_size_id=paper_size_id,
                weight=weight,
                is_active=True,
            )

            if supplier_id:
                query = query.filter(supplier_id=supplier_id)

            # ترتيب حسب السعر (الأرخص أولاً)
            paper_service = query.order_by("price_per_sheet").first()

            if not paper_service:
                # البحث بدون تحديد الوزن بالضبط (أقرب وزن)
                query = PaperServiceDetails.objects.filter(
                    paper_type_id=paper_type_id,
                    paper_size_id=paper_size_id,
                    is_active=True,
                )

                if supplier_id:
                    query = query.filter(supplier_id=supplier_id)

                paper_service = query.order_by("price_per_sheet").first()

            if not paper_service:
                return {"success": False, "error": "لم يتم العثور على خدمة ورق مناسبة"}

            # حساب التكلفة
            unit_cost = float(paper_service.price_per_sheet)
            total_cost = unit_cost * quantity

            # التحقق من الحد الأدنى للكمية
            if quantity < paper_service.minimum_quantity:
                # تطبيق رسوم إضافية للكميات الصغيرة
                small_quantity_fee = unit_cost * 0.1  # 10% رسوم إضافية
                unit_cost += small_quantity_fee
                total_cost = unit_cost * quantity

            return {
                "success": True,
                "unit_cost": round(unit_cost, 2),
                "total_cost": round(total_cost, 2),
                "quantity": quantity,
                "supplier_name": paper_service.supplier.name,
                "weight": paper_service.weight,
                "price_per_sheet": float(paper_service.price_per_sheet),
                "minimum_quantity": paper_service.minimum_quantity,
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في حساب تكلفة الورق: {str(e)}"}

    @staticmethod
    def calculate_digital_printing_cost(
        paper_size_id, color_type, quantity, supplier_id=None
    ):
        """حساب تكلفة الطباعة الرقمية - مبسط"""
        try:
            # تحديد نوع اللون
            if isinstance(color_type, int):
                color_type = "COLOR" if color_type > 1 else "BW"

            # البحث عن خدمة الطباعة الرقمية
            query = DigitalPrintingDetails.objects.filter(
                paper_size_id=paper_size_id, color_type=color_type, is_active=True
            )

            if supplier_id:
                query = query.filter(supplier_id=supplier_id)

            # ترتيب حسب السعر (الأرخص أولاً)
            digital_service = query.order_by("price_per_copy").first()

            if not digital_service:
                return {
                    "success": False,
                    "error": f"لم يتم العثور على خدمة طباعة رقمية {color_type}",
                }

            # حساب التكلفة
            unit_cost = float(digital_service.price_per_copy)
            total_cost = unit_cost * quantity

            # تطبيق تكلفة إعداد إذا كانت الكمية أقل من الحد الأدنى
            setup_cost = 0
            if quantity < digital_service.minimum_quantity:
                setup_cost = 25.0  # تكلفة إعداد افتراضية
                total_cost += setup_cost

            return {
                "success": True,
                "unit_cost": round(unit_cost, 2),
                "setup_cost": round(setup_cost, 2),
                "total_cost": round(total_cost, 2),
                "quantity": quantity,
                "supplier_name": digital_service.supplier.name,
                "color_type": "ملون" if color_type == "COLOR" else "أبيض وأسود",
                "price_per_copy": float(digital_service.price_per_copy),
                "minimum_quantity": digital_service.minimum_quantity,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"خطأ في حساب تكلفة الطباعة الرقمية: {str(e)}",
            }

    @staticmethod
    def calculate_plate_cost(plate_size_id, quantity, supplier_id=None):
        """حساب تكلفة الزنكات - مبسط"""
        try:
            # تكلفة ثابتة للزنكات (تقديرية حسب الحجم)
            size_costs = {
                1: 20.0,  # صغير
                2: 30.0,  # متوسط
                3: 45.0,  # كبير
                4: 65.0,  # كبير جداً
            }

            base_cost_per_plate = size_costs.get(plate_size_id, 25.0)
            setup_cost = 50.0  # تكلفة إعداد

            unit_cost = base_cost_per_plate
            total_cost = (unit_cost * quantity) + setup_cost

            return {
                "success": True,
                "unit_cost": round(unit_cost, 2),
                "setup_cost": round(setup_cost, 2),
                "total_cost": round(total_cost, 2),
                "quantity": quantity,
                "supplier_name": "خدمة الزنكات",
                "plate_size": f"مقاس {plate_size_id}",
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في حساب تكلفة الزنكات: {str(e)}"}

    @staticmethod
    def calculate_total_project_cost(paper_data, printing_data, finishing_data=None):
        """حساب التكلفة الإجمالية للمشروع - مبسط"""
        try:
            total_cost = 0
            cost_breakdown = {}

            # حساب تكلفة الورق
            if paper_data:
                paper_result = SimplePricingCalculator.calculate_paper_cost(
                    **paper_data
                )
                if paper_result["success"]:
                    total_cost += paper_result["total_cost"]
                    cost_breakdown["paper"] = paper_result
                else:
                    return paper_result

            # حساب تكلفة الطباعة
            if printing_data:
                press_type = printing_data.get("press_type", "digital")

                if press_type == "digital":
                    printing_result = (
                        SimplePricingCalculator.calculate_digital_printing_cost(
                            paper_size_id=printing_data.get("paper_size_id"),
                            color_type=printing_data.get("colors", 1),
                            quantity=printing_data.get("quantity", 1),
                            supplier_id=printing_data.get("supplier_id"),
                        )
                    )
                else:
                    # طباعة أوفست - تحتاج زنكات
                    printing_result = SimplePricingCalculator.calculate_plate_cost(
                        plate_size_id=printing_data.get("plate_size_id", 1),
                        quantity=printing_data.get("plate_quantity", 4),
                        supplier_id=printing_data.get("supplier_id"),
                    )

                if printing_result["success"]:
                    total_cost += printing_result["total_cost"]
                    cost_breakdown["printing"] = printing_result
                else:
                    return printing_result

            # حساب ضريبة القيمة المضافة
            try:
                vat_setting = VATSetting.objects.filter(is_enabled=True).first()
                vat_rate = float(vat_setting.percentage) if vat_setting else 15.0
            except:
                vat_rate = 15.0

            vat_amount = total_cost * (vat_rate / 100)
            final_total = total_cost + vat_amount

            return {
                "success": True,
                "subtotal": round(total_cost, 2),
                "vat_rate": vat_rate,
                "vat_amount": round(vat_amount, 2),
                "total_cost": round(final_total, 2),
                "cost_breakdown": cost_breakdown,
                # للتوافق مع النظام القديم
                "paper_cost": cost_breakdown.get("paper", {}).get("total_cost", 0),
                "press_cost": cost_breakdown.get("printing", {}).get("total_cost", 0),
                "plate_cost": 0,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"خطأ في حساب التكلفة الإجمالية: {str(e)}",
            }

    @staticmethod
    def get_available_suppliers_for_service(service_type):
        """الحصول على الموردين المتاحين لخدمة معينة - مبسط"""
        try:
            if service_type == "paper":
                supplier_ids = (
                    PaperServiceDetails.objects.filter(is_active=True)
                    .values_list("supplier_id", flat=True)
                    .distinct()
                )
            elif service_type == "digital_printing":
                supplier_ids = (
                    DigitalPrintingDetails.objects.filter(is_active=True)
                    .values_list("supplier_id", flat=True)
                    .distinct()
                )
            else:
                return []

            suppliers = Supplier.objects.filter(
                id__in=supplier_ids, is_active=True
            ).values("id", "name")

            return list(suppliers)

        except Exception as e:
            return []
