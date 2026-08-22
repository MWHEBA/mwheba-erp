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
        suppliers = Supplier.objects.filter(is_active=True).select_related("default_currency", "default_payment_term", "primary_type").order_by("name")

        suppliers_data = []
        for supplier in suppliers:
            suppliers_data.append(
                {
                    "id": supplier.id,
                    "name": supplier.name,
                    "code": supplier.code,
                    "entity_type": supplier.entity_type,
                    "primary_type_name": supplier.primary_type.name if supplier.primary_type else "",
                    "tax_number": supplier.tax_number or "",
                    "national_id": supplier.national_id or "",
                    "phone": supplier.phone or "",
                    "payment_terms": supplier.payment_terms or (supplier.default_payment_term.name if supplier.default_payment_term else ""),
                    "default_currency_id": supplier.default_currency_id,
                    "default_currency_code": supplier.default_currency.code if supplier.default_currency else "",
                    "default_currency_symbol": supplier.default_currency.symbol if supplier.default_currency else "",
                    "credit_limit": float(supplier.credit_limit) if supplier.credit_limit else 0.0,
                    "is_preferred": supplier.is_preferred,
                    "balance": float(supplier.balance) if supplier.balance else 0.0,
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