"""
Views محسنة لحسابات التسعير
Enhanced Pricing Calculation Views
"""
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from .simple_calculation_service import SimplePricingCalculator


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def enhanced_paper_price_api(request):
    """API محسن لحساب سعر الورق"""
    try:
        data = json.loads(request.body)

        # استخراج المعاملات
        paper_type_id = data.get("paper_type")
        paper_size_id = data.get("paper_size")
        weight = data.get("weight")
        quantity = data.get("quantity", 1)
        supplier_id = data.get("supplier")
        origin = data.get("origin", "LOCAL")

        # التحقق من المعاملات المطلوبة
        if not all([paper_type_id, paper_size_id, weight, quantity]):
            return JsonResponse(
                {
                    "success": False,
                    "error": "معاملات مفقودة: paper_type, paper_size, weight, quantity مطلوبة",
                }
            )

        # حساب التكلفة
        result = SimplePricingCalculator.calculate_paper_cost(
            paper_type_id=int(paper_type_id),
            paper_size_id=int(paper_size_id),
            weight=int(weight),
            quantity=int(quantity),
            supplier_id=int(supplier_id) if supplier_id else None,
        )

        return JsonResponse(result)

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "بيانات JSON غير صحيحة"})
    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"خطأ في حساب سعر الورق: {str(e)}"}
        )


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def enhanced_press_price_api(request):
    """API محسن لحساب سعر الطباعة"""
    try:
        data = json.loads(request.body)

        # استخراج المعاملات
        press_type = data.get("press_type", "digital")
        colors = data.get("colors", 1)
        quantity = data.get("quantity", 1)
        paper_size_id = data.get("paper_size")
        supplier_id = data.get("supplier")

        # التحقق من المعاملات المطلوبة
        if not all([quantity, paper_size_id]):
            return JsonResponse(
                {
                    "success": False,
                    "error": "معاملات مفقودة: quantity, paper_size مطلوبة",
                }
            )

        if press_type == "digital":
            # حساب تكلفة الطباعة الرقمية
            result = SimplePricingCalculator.calculate_digital_printing_cost(
                paper_size_id=int(paper_size_id),
                color_type=int(colors),
                quantity=int(quantity),
                supplier_id=int(supplier_id) if supplier_id else None,
            )
        else:
            # طباعة أوفست - حساب تكلفة الزنكات
            plate_size_id = data.get("plate_size", 1)
            plate_quantity = data.get("plate_quantity", 4)

            result = SimplePricingCalculator.calculate_plate_cost(
                plate_size_id=int(plate_size_id),
                quantity=int(plate_quantity),
                supplier_id=int(supplier_id) if supplier_id else None,
            )

        return JsonResponse(result)

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "بيانات JSON غير صحيحة"})
    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"خطأ في حساب سعر الطباعة: {str(e)}"}
        )


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def enhanced_plate_price_api(request):
    """API محسن لحساب سعر الزنكات"""
    try:
        data = json.loads(request.body)

        # استخراج المعاملات
        plate_size_id = data.get("plate_size")
        quantity = data.get("quantity", 1)
        supplier_id = data.get("supplier")

        # التحقق من المعاملات المطلوبة
        if not all([plate_size_id, quantity]):
            return JsonResponse(
                {
                    "success": False,
                    "error": "معاملات مفقودة: plate_size, quantity مطلوبة",
                }
            )

        # حساب التكلفة
        result = SimplePricingCalculator.calculate_plate_cost(
            plate_size_id=int(plate_size_id),
            quantity=int(quantity),
            supplier_id=int(supplier_id) if supplier_id else None,
        )

        return JsonResponse(result)

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "بيانات JSON غير صحيحة"})
    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"خطأ في حساب سعر الزنكات: {str(e)}"}
        )


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def enhanced_total_cost_api(request):
    """API محسن لحساب التكلفة الإجمالية"""
    try:
        data = json.loads(request.body)

        # إعداد بيانات الورق
        paper_data = None
        if all(
            key in data for key in ["paper_type", "paper_size", "weight", "quantity"]
        ):
            paper_data = {
                "paper_type_id": int(data["paper_type"]),
                "paper_size_id": int(data["paper_size"]),
                "weight": int(data["weight"]),
                "quantity": int(data["quantity"]),
                "supplier_id": int(data["supplier"]) if data.get("supplier") else None,
            }

        # إعداد بيانات الطباعة
        printing_data = None
        if "press_type" in data:
            printing_data = {
                "press_type": data["press_type"],
                "paper_size_id": int(data.get("paper_size", 1)),
                "colors": int(data.get("colors", 1)),
                "quantity": int(data.get("quantity", 1)),
                "supplier_id": int(data.get("supplier"))
                if data.get("supplier")
                else None,
            }

            if data["press_type"] == "offset":
                printing_data.update(
                    {
                        "plate_size_id": int(data.get("plate_size", 1)),
                        "plate_quantity": int(data.get("plate_quantity", 4)),
                    }
                )

        # حساب التكلفة الإجمالية
        result = SimplePricingCalculator.calculate_total_project_cost(
            paper_data=paper_data, printing_data=printing_data
        )

        # إضافة تفاصيل إضافية للاستجابة
        if result["success"]:
            breakdown = result.get("cost_breakdown", {})

            # استخراج التكاليف الفردية للتوافق مع النظام القديم
            paper_cost = breakdown.get("paper", {}).get("total_cost", 0)
            press_cost = breakdown.get("printing", {}).get("total_cost", 0)
            plate_cost = 0  # سيتم حسابها ضمن press_cost للأوفست

            result.update(
                {
                    "paper_cost": paper_cost,
                    "press_cost": press_cost,
                    "plate_cost": plate_cost,
                    "subtotal": result["subtotal"],
                }
            )

        return JsonResponse(result)

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "بيانات JSON غير صحيحة"})
    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"خطأ في حساب التكلفة الإجمالية: {str(e)}"}
        )


@login_required
def enhanced_suppliers_by_service_api(request):
    """API للحصول على الموردين حسب نوع الخدمة"""
    try:
        service_type = request.GET.get("service_type", "paper")

        suppliers = SimplePricingCalculator.get_available_suppliers_for_service(
            service_type
        )

        return JsonResponse({"success": True, "data": suppliers})

    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"خطأ في جلب الموردين: {str(e)}"}
        )


@login_required
def pricing_calculator_test_api(request):
    """API لاختبار حاسبة التسعير"""
    try:
        # اختبار سريع للتأكد من عمل النظام
        test_paper = SimplePricingCalculator.calculate_paper_cost(
            paper_type_id=1, paper_size_id=1, weight=80, quantity=100
        )

        test_digital = SimplePricingCalculator.calculate_digital_printing_cost(
            paper_size_id=1, color_type="BW", quantity=100
        )

        return JsonResponse(
            {
                "success": True,
                "message": "حاسبة التسعير تعمل بشكل صحيح",
                "test_results": {
                    "paper_calculation": test_paper["success"],
                    "digital_printing_calculation": test_digital["success"],
                },
            }
        )

    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"خطأ في اختبار حاسبة التسعير: {str(e)}"}
        )
