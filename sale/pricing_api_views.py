"""
Pricing API Views - FIN-SAL-004
واجهات البرمجة اللحظية لتقييم سلة المبيعات وقوائم الأسعار والخصومات
"""
import json
import logging
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from sale.services.pricing_service import PricingService

logger = logging.getLogger(__name__)


@login_required
@require_POST
def evaluate_cart_api(request):
    """
    API سريع لتقييم بنود السلة بالكامل دفعة واحدة وإرجاع الأسعار والخصومات والضرائب الموزعة نسبياً
    POST /sales/api/pricing/evaluate-cart/
    """
    try:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except Exception:
            payload = request.POST

        items = payload.get("items", [])
        customer_id = payload.get("customer_id")
        price_list_id = payload.get("price_list_id")
        currency_id = payload.get("currency_id")
        currency = payload.get("currency")
        from financial.services.exchange_rate_service import ExchangeRateService
        from financial.models import Currency
        func_curr = ExchangeRateService.get_functional_currency()
        default_code = func_curr.code if func_curr else "EGP"

        if currency_id and not currency:
            try:
                c_obj = Currency.objects.filter(pk=int(currency_id)).first()
                if c_obj:
                    currency = c_obj.code
            except Exception:
                pass

        if not currency or str(currency).isdigit():
            if str(currency).isdigit():
                try:
                    c_obj = Currency.objects.filter(pk=int(currency)).first()
                    currency = c_obj.code if c_obj else default_code
                except Exception:
                    currency = default_code
            else:
                currency = default_code

        exchange_rate = payload.get("exchange_rate")
        header_discount = Decimal(str(payload.get("header_discount", 0) or 0))
        header_discount_type = payload.get("header_discount_type", "fixed")
        vat_active = bool(payload.get("vat_active", True))
        vat_rate = Decimal(str(payload.get("vat_rate", 14) or 14))
        wht_active = bool(payload.get("wht_active", False))
        wht_rate = Decimal(str(payload.get("wht_rate", 1) or 1))

        if exchange_rate:
            try:
                exchange_rate = Decimal(str(exchange_rate))
                if exchange_rate <= Decimal("0"):
                    exchange_rate = Decimal("1.000000")
            except Exception:
                exchange_rate = None

        if customer_id:
            try:
                customer_id = int(customer_id)
            except (ValueError, TypeError):
                customer_id = None

        if price_list_id:
            try:
                price_list_id = int(price_list_id)
            except (ValueError, TypeError):
                price_list_id = None

        cart_result = PricingService.evaluate_cart_pricing(
            items=items,
            customer_id=customer_id,
            price_list_id=price_list_id,
            currency=currency,
            exchange_rate=exchange_rate,
            header_discount=header_discount,
            header_discount_type=header_discount_type,
            vat_active=vat_active,
            vat_rate=vat_rate,
            wht_active=wht_active,
            wht_rate=wht_rate
        )

        # تحويل كائنات الـ Decimal إلى أرقام float للعرض في JSON
        def sanitize_decimal(val):
            if isinstance(val, Decimal):
                return float(val)
            elif isinstance(val, dict):
                return {k: sanitize_decimal(v) for k, v in val.items()}
            elif isinstance(val, list):
                return [sanitize_decimal(v) for v in val]
            return val

        clean_response = sanitize_decimal(cart_result)
        clean_response["success"] = True
        clean_response["lines"] = clean_response.get("items", [])
        can_view_profit_margin = getattr(request.user, 'can_view_profit_margin', True)
        for line in clean_response["lines"]:
            if "discount" not in line:
                line["discount"] = line.get("applied_discount", 0)
            if not can_view_profit_margin:
                line.pop("cost_price", None)
                line.pop("is_below_cost", None)
                if isinstance(line.get("price_snapshot"), dict):
                    line["price_snapshot"].pop("cost_price", None)
        return JsonResponse(clean_response)

    except Exception as e:
        logger.error(f"Error in evaluate_cart_api: {str(e)}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)
