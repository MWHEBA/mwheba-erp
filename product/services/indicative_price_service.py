# -*- coding: utf-8 -*-
"""
Product Indicative Price Domain Service
خدمة إدارة وإنشاء الأسعار الاسترشادية للمنتجات بالعملات الأجنبية
"""
import logging
from decimal import Decimal
from product.models.product_currency_price import ProductCurrencyPrice

logger = logging.getLogger(__name__)


class IndicativePriceService:
    """
    خدمة محوكمة لإنشاء وحفظ الأسعار الاسترشادية للمنتجات بالعملات الأجنبية
    تتأكد من عدم المساس بالأسعار القائمة (create_if_missing logic)
    """

    @classmethod
    def create_if_missing(cls, product, currency, price, price_type="selling", user=None):
        """
        إنشاء السعر الاسترشادي المبدئي للمنتج بالعملة الأجنبية فقط وحصرياً إذا لم يكن مسجلاً مسبقاً
        
        Args:
            product: كائن المنتج (Product)
            currency: كائن العملة (Currency)
            price: السعر المدخل (Decimal/float)
            price_type: نوع السعر ('selling' للمبيعات وعروض الأسعار، 'cost' للمشتريات)
            user: المستخدم المنفذ
        """
        if not product or not currency or currency.is_functional:
            return None

        try:
            num_price = Decimal(str(price or 0).replace(",", ""))
        except (TypeError, ValueError):
            return None

        if num_price <= Decimal("0"):
            return None

        try:
            defaults = {
                "created_by": user,
                "updated_by": user,
            }
            if price_type == "cost":
                defaults["indicative_cost_price"] = num_price
            else:
                defaults["indicative_selling_price"] = num_price

            cp_obj, created = ProductCurrencyPrice.objects.get_or_create(
                product=product,
                currency=currency,
                defaults=defaults,
            )

            if created:
                logger.info(
                    f"✅ تم إنشاء سعر استرشادي أولي للمنتج {product.id} بالعملة {currency.code}: {num_price} ({price_type})"
                )
                return cp_obj
            else:
                # إذا كان السجل موجوداً مسبقاً، نحدث فقط إذا كان السعر الخاص بهذا النوع مفقوداً (None أو 0)
                updated = False
                if price_type == "cost" and (cp_obj.indicative_cost_price is None or cp_obj.indicative_cost_price <= Decimal("0")):
                    cp_obj.indicative_cost_price = num_price
                    updated = True
                elif price_type == "selling" and (cp_obj.indicative_selling_price is None or cp_obj.indicative_selling_price <= Decimal("0")):
                    cp_obj.indicative_selling_price = num_price
                    updated = True

                if updated:
                    if user:
                        cp_obj.updated_by = user
                    cp_obj.save()
                    logger.info(
                        f"✅ تم تعيين السعر الاسترشادي المفقود للمنتج {product.id} بالعملة {currency.code}: {num_price} ({price_type})"
                    )

                return cp_obj

        except Exception as e:
            logger.error(f"❌ خطأ أثناء معالجة السعر الاسترشادي للمنتج {product.id}: {str(e)}")
            return None
