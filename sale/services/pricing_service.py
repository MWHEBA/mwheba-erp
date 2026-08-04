from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import models
from django.utils import timezone
from sale.models.pricing import PriceList, PriceListItem, DiscountRule, PricingAuditLog
from product.models.product_core import Product
from financial.services.exchange_rate_service import ExchangeRateService


class PricingService:
    """
    FIN-SAL-004: Enterprise Sales Pricing Engine Service
    سلطة التسعير المركزية لحساب السعر النهائي والخصم وتوثيق تتبع الأسعار لجميع معاملات المبيعات
    """

    @classmethod
    def get_sales_price(
        cls,
        product_id: int,
        customer_id: Optional[int] = None,
        quantity: Decimal = Decimal("1.0000"),
        price_list_id: Optional[int] = None,
        as_of_date=None,
        currency: str = "EGP"
    ) -> Dict[str, Any]:
        """
        الحصول على لقطة تسعير المبيعات الحاكمة للمنتج
        """
        product = Product.objects.get(pk=product_id)
        as_of_date = as_of_date or timezone.now().date()
        base_price = product.selling_price or Decimal("0.00")
        target_currency = currency

        # 1. Price List Resolution
        if price_list_id:
            try:
                price_list = PriceList.objects.get(
                    pk=price_list_id,
                    is_active=True,
                    effective_from__lte=as_of_date
                )
                if price_list.effective_to and price_list.effective_to < as_of_date:
                    pass
                else:
                    target_currency = price_list.currency
                    item = PriceListItem.objects.filter(
                        price_list=price_list,
                        product=product,
                        min_quantity__lte=quantity,
                        is_active=True,
                        effective_date__lte=as_of_date
                    ).order_by("-min_quantity").first()

                    if item:
                        base_price = item.unit_price
            except PriceList.DoesNotExist:
                pass

        # 2. Discount Resolution
        rules = DiscountRule.objects.filter(
            is_active=True,
            effective_date__lte=as_of_date
        )
        if customer_id:
            rules = rules.filter(models.Q(customer_id=customer_id) | models.Q(customer__isnull=True))
        else:
            rules = rules.filter(customer__isnull=True)

        if product.category_id:
            rules = rules.filter(models.Q(category_id=product.category_id) | models.Q(category__isnull=True))
        else:
            rules = rules.filter(category__isnull=True)

        best_rule = rules.order_by("-priority", "-discount_percentage").first()
        disc_pct = best_rule.discount_percentage if best_rule else Decimal("0.00")

        # 3. Currency Conversion (IAS 21 Spot Rate)
        rate = Decimal("1.000000")
        if target_currency != "EGP":
            rate = ExchangeRateService.get_spot_rate(target_currency, as_of_date)

        disc_amount = (base_price * (disc_pct / Decimal("100.00"))).quantize(Decimal("0.01"))
        final_price = (base_price - disc_amount).quantize(Decimal("0.01"))
        func_price = (final_price * rate).quantize(Decimal("0.01"))

        return {
            "product_id": product_id,
            "base_price": base_price,
            "discount_percentage": disc_pct,
            "discount_amount": disc_amount,
            "final_price": final_price,
            "currency": target_currency,
            "exchange_rate": rate,
            "functional_price": func_price
        }

    @classmethod
    def update_product_price(
        cls,
        product_id: int,
        new_price: Decimal,
        price_list_id: Optional[int] = None,
        user=None,
        reason: str = ""
    ) -> PricingAuditLog:
        """
        تحديث سعر المنتج وتسجيل كائن التدقيق المحوكم PricingAuditLog
        """
        product = Product.objects.get(pk=product_id)
        old_price = product.selling_price or Decimal("0.00")

        if price_list_id:
            item = PriceListItem.objects.filter(price_list_id=price_list_id, product=product).first()
            if item:
                old_price = item.unit_price
                item.unit_price = new_price
                item.save()
        else:
            product.selling_price = new_price
            product.save()

        audit = PricingAuditLog.objects.create(
            product=product,
            price_list_id=price_list_id,
            old_price=old_price,
            new_price=new_price,
            changed_by=user,
            reason=reason
        )
        return audit
