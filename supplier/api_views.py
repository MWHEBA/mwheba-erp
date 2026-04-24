import json
import logging
from decimal import Decimal

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.core.exceptions import ValidationError

from .models import (
    Supplier,
    SupplierType,
)

logger = logging.getLogger(__name__)

# Note: Most API views have been removed as part of supplier categories cleanup
# The following API views have been removed:
# - get_category_form_api
# - SupplierTypesStylesAPIView
# - get_service_data_universal
# - save_service_data_universal
# - update_service_data_universal
# - get_field_mapping_api
# - delete_specialized_service_api
# - get_suppliers_by_service_type
# - get_supplier_coating_services

@login_required
@require_http_methods(["GET"])
def supplier_list_api(request):
    """
    API لإرجاع قائمة الموردين النشطين
    """
    try:
        suppliers = Supplier.objects.filter(is_active=True).order_by("name")

        suppliers_data = []
        for supplier in suppliers:
            suppliers_data.append(
                {
                    "id": supplier.id,
                    "name": supplier.name,
                    "code": supplier.code,
                    "phone": supplier.phone,
                    "balance": float(supplier.balance) if supplier.balance else 0,
                }
            )

        return JsonResponse({"success": True, "suppliers": suppliers_data})

    except Exception as e:
        logger.error(f"Error in supplier_list_api: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في تحميل الموردين"}
        )


@login_required
@require_http_methods(["GET"])
def supplier_types_styles_api(request):
    """
    API لإرجاع أنماط أنواع الموردين (الأيقونات والألوان)
    """
    try:
        supplier_types = SupplierType.objects.filter(is_active=True).order_by("display_order", "name")
        
        types_data = []
        for supplier_type in supplier_types:
            types_data.append({
                "id": supplier_type.id,
                "name": supplier_type.name,
                "icon": supplier_type.icon or "fas fa-box",
                "color": supplier_type.color or "#6c757d",
                "description": supplier_type.description or "",
            })
        
        return JsonResponse({"success": True, "types": types_data})
    
    except Exception as e:
        logger.error(f"Error in supplier_types_styles_api: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في تحميل أنماط أنواع الموردين"}
        )