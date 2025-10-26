import logging

logger = logging.getLogger(__name__)
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q, Avg, Min, Max, Count
from django.contrib import messages
from django.urls import reverse
from decimal import Decimal
import json

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
    LaserServiceDetails,
    VIPGiftDetails,
)


@login_required
def price_comparison(request):
    """صفحة مقارنة الأسعار"""

    # الحصول على المعاملات
    category_code = request.GET.get("category")
    quantity = request.GET.get("quantity", 100)
    try:
        quantity = int(quantity)
    except (ValueError, TypeError):
        quantity = 100

    # الحصول على التصنيفات
    categories = SupplierType.objects.filter(is_active=True).order_by("display_order")
    selected_category = None
    services = []

    if category_code:
        try:
            selected_category = SupplierType.objects.get(
                code=category_code, is_active=True
            )
            services = (
                SpecializedService.objects.filter(
                    category=selected_category, is_active=True, supplier__is_active=True
                )
                .select_related("supplier", "category")
                .prefetch_related("price_tiers")
            )

            # إضافة حسابات الأسعار لكل خدمة
            for service in services:
                service.calculated_price = service.get_price_for_quantity(quantity)
                service.total_cost = service.get_total_cost(quantity)
                service.applicable_tier = service.get_applicable_tier(quantity)
                service.discount_percentage = service.get_discount_percentage(quantity)
                service.savings = 0  # سيتم حسابها من الشرائح السعرية

            # ترتيب حسب السعر الإجمالي
            services = sorted(services, key=lambda x: x.total_cost)

        except SupplierType.DoesNotExist:
            messages.error(request, "فئة الخدمة المحددة غير موجودة")

    context = {
        "categories": categories,
        "selected_category": selected_category,
        "services": services,
        "quantity": quantity,
        "page_title": "مقارنة الأسعار",
        "page_icon": "fas fa-balance-scale",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "الموردين",
                "url": reverse("supplier:supplier_list"),
                "icon": "fas fa-truck",
            },
            {"title": "مقارنة الأسعار", "active": True},
        ],
    }

    return render(request, "supplier/price_comparison.html", context)


@login_required
def service_calculator(request):
    """حاسبة الخدمات المتقدمة"""

    service_id = request.GET.get("service_id")
    quantity = request.GET.get("quantity", 100)

    try:
        quantity = int(quantity)
    except (ValueError, TypeError):
        quantity = 100

    service = None
    calculation_result = None

    if service_id:
        try:
            service = SpecializedService.objects.select_related(
                "supplier", "category"
            ).get(id=service_id, is_active=True)
            calculation_result = service.get_price_breakdown(quantity)
        except SpecializedService.DoesNotExist:
            messages.error(request, "الخدمة المحددة غير موجودة")

    # الحصول على جميع الخدمات للاختيار
    services = SpecializedService.objects.filter(is_active=True).select_related(
        "supplier", "category"
    )

    context = {
        "services": services,
        "selected_service": service,
        "quantity": quantity,
        "calculation_result": calculation_result,
        "page_title": "حاسبة الخدمات",
        "page_icon": "fas fa-calculator",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "الموردين",
                "url": reverse("supplier:supplier_list"),
                "icon": "fas fa-truck",
            },
            {"title": "حاسبة الخدمات", "active": True},
        ],
    }

    return render(request, "supplier/service_calculator.html", context)


@login_required
def ajax_calculate_price(request):
    """حساب السعر عبر AJAX"""

    if request.method != "POST":
        return JsonResponse({"error": "طريقة الطلب غير صحيحة"}, status=405)

    try:
        data = json.loads(request.body)
        service_id = data.get("service_id")
        quantity = int(data.get("quantity", 1))

        service = SpecializedService.objects.get(id=service_id, is_active=True)
        result = service.get_price_breakdown(quantity)

        # تحويل Decimal إلى float للـ JSON
        for key, value in result.items():
            if isinstance(value, Decimal):
                result[key] = float(value)

        # إضافة معلومات الشريحة
        if result["tier"]:
            result["tier_info"] = {
                "name": result["tier"].tier_name,
                "range": result["tier"].get_quantity_range_display(),
                "discount": float(result["tier"].discount_percentage),
            }
        else:
            result["tier_info"] = None

        return JsonResponse({"success": True, "result": result})

    except (SpecializedService.DoesNotExist, ValueError, json.JSONDecodeError) as e:
        return JsonResponse({"error": "خطأ في العملية"}, status=400)


@login_required
def supplier_services_comparison(request, supplier_id):
    """مقارنة خدمات مورد واحد"""

    supplier = get_object_or_404(Supplier, id=supplier_id, is_active=True)
    quantity = request.GET.get("quantity", 100)

    try:
        quantity = int(quantity)
    except (ValueError, TypeError):
        quantity = 100

    # الحصول على خدمات المورد
    services = supplier.specialized_services.filter(is_active=True).select_related(
        "category"
    )

    # حساب الأسعار لكل خدمة
    for service in services:
        service.calculated_price = service.get_price_for_quantity(quantity)
        service.total_cost = service.get_total_cost(quantity)
        service.applicable_tier = service.get_applicable_tier(quantity)
        service.discount_percentage = service.get_discount_percentage(quantity)

    # تجميع الخدمات حسب الفئة
    services_by_category = {}
    for service in services:
        category_name = service.category.name
        if category_name not in services_by_category:
            services_by_category[category_name] = []
        services_by_category[category_name].append(service)

    context = {
        "supplier": supplier,
        "services_by_category": services_by_category,
        "quantity": quantity,
        "total_services": services.count(),
        "page_title": f"خدمات {supplier.name}",
        "page_icon": "fas fa-list",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "الموردين",
                "url": reverse("supplier:supplier_list"),
                "icon": "fas fa-truck",
            },
            {
                "title": supplier.name,
                "url": reverse("supplier:supplier_detail", args=[supplier.id]),
                "icon": "fas fa-user",
            },
            {"title": "مقارنة الخدمات", "active": True},
        ],
    }

    return render(request, "supplier/supplier_services_comparison.html", context)


@login_required
def category_analysis(request, category_code):
    """تحليل فئة خدمة معينة"""

    category = get_object_or_404(SupplierType, code=category_code, is_active=True)

    # الحصول على جميع الخدمات في هذه الفئة
    services = SpecializedService.objects.filter(
        category=category, is_active=True, supplier__is_active=True
    ).select_related("supplier")

    # إحصائيات الفئة
    stats = {
        "total_services": services.count(),
        "total_suppliers": services.values("supplier").distinct().count(),
        "avg_setup_cost": services.aggregate(avg=Avg("setup_cost"))["avg"] or 0,
    }

    # تحليل الشرائح السعرية
    services_with_tiers = services.filter(price_tiers__isnull=False).distinct()
    tier_stats = {
        "services_with_tiers": services_with_tiers.count(),
        "total_tiers": ServicePriceTier.objects.filter(
            service__in=services, is_active=True
        ).count(),
    }

    # أفضل 5 خدمات (أقل تكلفة إعداد)
    best_services = services.order_by("setup_cost")[:5]

    # توزيع الموردين حسب النوع من الإعدادات الديناميكية
    supplier_types_distribution = {}
    for service in services:
        supplier_type = service.supplier.get_primary_type_display()
        supplier_types_distribution[supplier_type] = (
            supplier_types_distribution.get(supplier_type, 0) + 1
        )

    context = {
        "category": category,
        "services": services,
        "stats": stats,
        "tier_stats": tier_stats,
        "best_services": best_services,
        "supplier_types_distribution": supplier_types_distribution,
        "page_title": f"تحليل فئة {category.name}",
        "page_icon": category.icon,
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "الموردين",
                "url": reverse("supplier:supplier_list"),
                "icon": "fas fa-truck",
            },
            {
                "title": "مقارنة الأسعار",
                "url": reverse("supplier:price_comparison"),
                "icon": "fas fa-balance-scale",
            },
            {"title": f"تحليل {category.name}", "active": True},
        ],
    }

    return render(request, "supplier/category_analysis.html", context)


@login_required
def bulk_price_calculator(request):
    """حاسبة الأسعار المجمعة"""

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            calculations = []

            for item in data.get("items", []):
                service_id = item.get("service_id")
                quantity = int(item.get("quantity", 1))

                try:
                    service = SpecializedService.objects.get(
                        id=service_id, is_active=True
                    )
                    result = service.get_price_breakdown(quantity)

                    # تحويل Decimal إلى float
                    for key, value in result.items():
                        if isinstance(value, Decimal):
                            result[key] = float(value)

                    result["service_name"] = service.name
                    result["supplier_name"] = service.supplier.name
                    calculations.append(result)

                except SpecializedService.DoesNotExist:
                    continue

            # حساب الإجماليات
            total_cost = sum(calc["total"] for calc in calculations)
            total_savings = sum(calc["savings"] for calc in calculations)

            return JsonResponse(
                {
                    "success": True,
                    "calculations": calculations,
                    "summary": {
                        "total_cost": total_cost,
                        "total_savings": total_savings,
                        "items_count": len(calculations),
                    },
                }
            )

        except (json.JSONDecodeError, ValueError) as e:
            return JsonResponse({"error": "خطأ في العملية"}, status=400)

    # GET request - عرض الصفحة
    services = SpecializedService.objects.filter(is_active=True).select_related(
        "supplier", "category"
    )

    context = {
        "services": services,
        "page_title": "حاسبة الأسعار المجمعة",
        "page_icon": "fas fa-calculator",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "الموردين",
                "url": reverse("supplier:supplier_list"),
                "icon": "fas fa-truck",
            },
            {"title": "حاسبة الأسعار المجمعة", "active": True},
        ],
    }

    return render(request, "supplier/bulk_price_calculator.html", context)


# ===== إدارة الخدمات المتخصصة =====


@login_required
def add_specialized_service(request, supplier_id):
    """إضافة خدمة متخصصة جديدة للمورد"""

    from .models import Supplier, SupplierType, SpecializedService
    from django import forms

    supplier = get_object_or_404(Supplier, pk=supplier_id)

    class SpecializedServiceForm(forms.ModelForm):
        class Meta:
            model = SpecializedService
            fields = ["name", "category", "description", "setup_cost", "is_active"]
            widgets = {
                "name": forms.TextInput(attrs={"class": "form-control"}),
                "category": forms.Select(attrs={"class": "form-control"}),
                "description": forms.Textarea(
                    attrs={"class": "form-control", "rows": 3}
                ),
                "setup_cost": forms.NumberInput(
                    attrs={"class": "form-control", "step": "0.01"}
                ),
            }

    if request.method == "POST":
        form = SpecializedServiceForm(request.POST)
        if form.is_valid():
            service = form.save(commit=False)
            service.supplier = supplier
            service.save()
            messages.success(request, f'تم إضافة الخدمة "{service.name}" بنجاح')
            return redirect("supplier:supplier_services_detail", pk=supplier.pk)
    else:
        form = SpecializedServiceForm()

    context = {
        "form": form,
        "supplier": supplier,
        "page_title": f"إضافة خدمة متخصصة - {supplier.name}",
        "page_icon": "fas fa-plus-circle",
    }

    return render(request, "supplier/services/add_specialized_service.html", context)


@login_required
def edit_specialized_service(request, supplier_id, service_id):
    """تعديل خدمة متخصصة"""

    from .models import Supplier, SpecializedService
    from django import forms

    supplier = get_object_or_404(Supplier, pk=supplier_id)
    service = get_object_or_404(SpecializedService, pk=service_id, supplier=supplier)

    class SpecializedServiceForm(forms.ModelForm):
        class Meta:
            model = SpecializedService
            fields = ["name", "category", "description", "setup_cost", "is_active"]
            widgets = {
                "name": forms.TextInput(attrs={"class": "form-control"}),
                "category": forms.Select(attrs={"class": "form-control"}),
                "description": forms.Textarea(
                    attrs={"class": "form-control", "rows": 3}
                ),
                "setup_cost": forms.NumberInput(
                    attrs={"class": "form-control", "step": "0.01"}
                ),
            }

    if request.method == "POST":
        form = SpecializedServiceForm(request.POST, instance=service)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تحديث الخدمة "{service.name}" بنجاح')
            return redirect("supplier:supplier_services_detail", pk=supplier.pk)
    else:
        form = SpecializedServiceForm(instance=service)

    context = {
        "form": form,
        "supplier": supplier,
        "service": service,
        "page_title": f"تعديل الخدمة - {service.name}",
        "page_icon": "fas fa-edit",
    }

    return render(request, "supplier/services/edit_specialized_service.html", context)


