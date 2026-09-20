# -*- coding: utf-8 -*-
"""
Pricing Security Validator - محرك التدقيق السعري وحماية البيزنس
مسؤول عن:
1. التحقق من صلاحيات تعديل سعر الوحدة (sale.change_unit_price / change_quotation_price).
2. مطابقة أسعار البنود بأسعار الكتالوج الرسمي أو قائمة أسعار العميل O(1).
3. إلزام المطبوعات المخصصة برقم أمر تسعير معتمد، والخدمات المفتوحة بصلاحية صريحة.
4. فرض سقف الخصم الإجمالي للمندوب (sale.override_max_discount).
5. التحقق من السقف الائتماني للعميل عند البيع الآجل (sale.override_credit_limit).
6. قفل سعر الصرف للعملات الأجنبية وفق IAS 21 (financial.override_exchange_rate).
"""
import logging
from decimal import Decimal
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils.translation import gettext_lazy as _

from product.models.product_core import Product

logger = logging.getLogger(__name__)


class PricingSecurityValidator:
    """
    محرك التدقيق السعري والحوكمة المؤسسية الموحد لطبقة الخدمات
    """

    MAX_SALES_REP_DISCOUNT_PERCENT = Decimal("5.00")

    @classmethod
    def can_change_price(cls, user, doc_type="sale") -> bool:
        """
        فحص هل يملك المستخدم صلاحية تعديل السعر للمستند المعني
        """
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or getattr(user, "is_admin", False):
            return True

        if doc_type == "sale":
            return user.has_perm("sale.change_unit_price")
        elif doc_type == "quotation":
            return user.has_perm("sale.change_quotation_price") or user.has_perm("sale.change_unit_price")
        elif doc_type == "sales_order":
            return user.has_perm("sale.change_sales_order_price") or user.has_perm("sale.change_unit_price")

        return user.has_perm("sale.change_unit_price")

    @classmethod
    def validate_document_pricing(
        cls,
        user,
        items_data,
        customer=None,
        price_list=None,
        currency=None,
        exchange_rate=None,
        discount=Decimal("0.00"),
        discount_type="fixed",
        payment_method="credit",
        total_amount=None,
        subtotal=None,
        doc_type="sale",
    ):
        """
        التدقيق السعري والائتماني الشامل على مستوى المستند بالكامل
        """
        if not user or not user.is_authenticated:
            raise PermissionDenied(_("المستخدم غير مسجل الدخول."))

        is_admin_or_super = user.is_superuser or getattr(user, "is_admin", False)
        has_price_perm = cls.can_change_price(user, doc_type=doc_type)

        # 1. التدقيق السعري لبنود الفاتورة O(1)
        cls._validate_items_pricing(
            user=user,
            items_data=items_data,
            has_price_perm=has_price_perm,
            price_list=price_list,
            customer=customer,
        )

        # 2. حوكمة الخصم الإجمالي للفاتورة
        cls._validate_discount_cap(
            user=user,
            discount=discount,
            discount_type=discount_type,
            subtotal=subtotal,
            is_admin=is_admin_or_super,
        )

        # 3. حوكمة السقف الائتماني للعميل عند البيع الآجل
        if doc_type == "sale" and payment_method == "credit":
            cls._validate_credit_limit(
                user=user,
                customer=customer,
                total_amount=total_amount or subtotal or Decimal("0.00"),
                currency=currency,
                exchange_rate=exchange_rate,
                is_admin=is_admin_or_super,
            )

        # 4. قفل سعر الصرف للعملات الأجنبية وفق IAS 21
        if currency and not getattr(currency, "is_functional", True) and exchange_rate is not None:
            cls._validate_exchange_rate(
                user=user,
                currency=currency,
                provided_rate=exchange_rate,
                is_admin=is_admin_or_super,
            )

    @classmethod
    def _validate_items_pricing(cls, user, items_data, has_price_perm, price_list, customer):
        """
        فحص أسعار كل بند ومقارنته بالسعر المعتمد دفعة واحدة O(1) لمنع ثغرات التلاعب
        """
        if has_price_perm:
            # المستخدم لديه الصلاحية الصريحة لتعديل الأسعار
            return

        # استخراج كافة معرفات المنتجات لجلبها دفعة واحدة O(1) ومنع N+1 queries
        product_ids = []
        for it in items_data:
            pid = it.get("product_id") or getattr(it.get("product"), "id", None)
            if pid:
                try:
                    product_ids.append(int(pid))
                except (ValueError, TypeError):
                    pass

        if not product_ids:
            return

        products_dict = Product.objects.in_bulk(product_ids)

        # جلب أسعار قائمة الأسعار دفعة واحدة إذا تم تحديد قائمة أسعار
        price_list_items_dict = {}
        if price_list:
            from sale.models import PriceListItem
            p_list_id = price_list.id if hasattr(price_list, "id") else price_list
            pl_qs = PriceListItem.objects.filter(
                price_list_id=p_list_id,
                product_id__in=product_ids,
                is_active=True,
            )
            for pli in pl_qs:
                price_list_items_dict[pli.product_id] = pli.unit_price

        # فحص كل بند على حدة
        for it in items_data:
            pid = it.get("product_id") or getattr(it.get("product"), "id", None)
            if not pid or int(pid) not in products_dict:
                continue

            product = products_dict[int(pid)]
            entered_price = Decimal(str(it.get("unit_price", 0)))
            item_qty = Decimal(str(it.get("quantity", 1)))

            # الحالة أ: خدمة إعلانية مفتوحة (Agency Open Service)
            if product.is_service and (product.selling_price is None or product.selling_price == Decimal("0.00")):
                if not user.has_perm("sale.add_open_price_service"):
                    raise ValidationError(
                        _(
                            "الصنف الخدمي '%(name)s' ذو تسعير حر ويتطلب صلاحية صريحة (sale.add_open_price_service)."
                        )
                        % {"name": product.name}
                    )
                continue

            # الحالة ب: مطبوعات مخصصة مرتبطة بأمر تسعير معتمد
            printing_order_id = it.get("printing_order_id") or it.get("printing_order")
            if printing_order_id:
                try:
                    from printing_pricing.models import PrintingOrder
                    p_order = PrintingOrder.objects.filter(id=printing_order_id).first()
                    if p_order and p_order.final_price:
                        # احتساب سعر الوحدة من أمر التسعير
                        expected_order_price = (p_order.final_price / item_qty).quantize(Decimal("0.01")) if item_qty > 0 else p_order.final_price
                        if abs(entered_price - expected_order_price) > Decimal("0.05") and abs(entered_price - p_order.final_price) > Decimal("0.05"):
                            raise ValidationError(
                                _(
                                    "سعر البند '%(name)s' (%(entered)s ج.م) لا يطابق سعر أمر التسعير المعتمد (%(expected)s ج.م)."
                                )
                                % {
                                    "name": product.name,
                                    "entered": entered_price,
                                    "expected": expected_order_price,
                                }
                            )
                        continue
                except Exception as e:
                    logger.warning(f"تعذر التحقق من أمر التسعير {printing_order_id}: {e}")

            # الحالة ج: قائمة أسعار العميل المعتمدة
            if int(pid) in price_list_items_dict:
                approved_price = price_list_items_dict[int(pid)]
            else:
                # الحالة د: السعر الرسمي المسجل ببطاقة الصنف
                approved_price = product.selling_price or Decimal("0.00")

            # السماح بهامش فرق ضئيل جداً لتفادي مشاكل التقريب (0.01)
            if abs(entered_price - approved_price) > Decimal("0.01"):
                raise ValidationError(
                    _(
                        "غير مصرح لك بتغيير سعر بيع الصنف '%(name)s' "
                        "(السعر المعتمد: %(approved)s ج.م، السعر المدخل: %(entered)s ج.م). "
                        "يتطلب صلاحية تعديل الأسعار."
                    )
                    % {
                        "name": product.name,
                        "approved": approved_price,
                        "entered": entered_price,
                    }
                )

    @classmethod
    def _validate_discount_cap(cls, user, discount, discount_type, subtotal, is_admin):
        """
        حوكمة الخصم الإجمالي ومنع الالتفاف على الأسعار بالخصومات غير المصرح بها
        """
        if is_admin or user.has_perm("sale.apply_special_discount") or user.has_perm("sale.override_max_discount"):
            return

        discount_val = Decimal(str(discount or 0))
        if discount_val <= Decimal("0.00"):
            return

        subtotal_val = Decimal(str(subtotal or 0))
        if discount_type == "percentage":
            disc_percent = discount_val
        else:
            if subtotal_val > Decimal("0.00"):
                disc_percent = (discount_val / subtotal_val) * Decimal("100.00")
            else:
                disc_percent = Decimal("0.00")

        if disc_percent > cls.MAX_SALES_REP_DISCOUNT_PERCENT:
            raise ValidationError(
                _(
                    "نسبة الخصم الإجمالي (%(disc).1f%%) تتجاوز الحد الأقصى المسموح به لمندوب المبيعات (%(max).1f%%). "
                    "يتطلب اعتماد المشرف أو صلاحية تجاوز سقف الخصم (sale.override_max_discount)."
                )
                % {
                    "disc": disc_percent,
                    "max": cls.MAX_SALES_REP_DISCOUNT_PERCENT,
                }
            )

    @classmethod
    def _validate_credit_limit(cls, user, customer, total_amount, currency, exchange_rate, is_admin):
        """
        حوكمة البيع الآجل والسقف الائتماني للعميل
        """
        if is_admin or user.has_perm("sale.override_credit_limit"):
            return

        if not customer:
            return

        credit_limit = getattr(customer, "credit_limit", Decimal("0.00")) or Decimal("0.00")
        if credit_limit <= Decimal("0.00"):
            # العميل ليس لديه سقف ائتماني محدد (0 تعني غير مقيد أو نقدي حسب سياسة الشركة)
            return

        current_balance = getattr(customer, "balance", Decimal("0.00")) or Decimal("0.00")
        rate = Decimal(str(exchange_rate or 1.0))
        sale_functional_total = Decimal(str(total_amount or 0)) * rate

        projected_balance = current_balance + sale_functional_total

        if projected_balance > credit_limit:
            raise ValidationError(
                _(
                    "البيع الآجل يتجاوز الحد الائتماني للعميل '%(cust)s'. "
                    "الرصيد المتوقع: %(proj).2f ج.م، الحد المسموح: %(limit).2f ج.م. "
                    "يتطلب اعتماد المدير المالي أو صلاحية تجاوز سقف الائتمان (sale.override_credit_limit)."
                )
                % {
                    "cust": customer.name,
                    "proj": projected_balance,
                    "limit": credit_limit,
                }
            )

    @classmethod
    def _validate_exchange_rate(cls, user, currency, provided_rate, is_admin):
        """
        حوكمة وتثبيت سعر الصرف للعملات الأجنبية وفق معيار IAS 21
        """
        if is_admin or user.has_perm("financial.override_exchange_rate") or user.has_perm("sale.override_exchange_rate"):
            return

        try:
            from financial.services.exchange_rate_service import ExchangeRateService
            official_rate = Decimal(str(ExchangeRateService.get_exchange_rate(currency) or 1.0))
            provided = Decimal(str(provided_rate or 1.0))

            if abs(provided - official_rate) > Decimal("0.0001"):
                raise ValidationError(
                    _(
                        "غير مصرح لك بتعديل سعر الصرف لعملة '%(code)s' "
                        "(السعر الرسمي المعتمد: %(official)s، السعر المدخل: %(provided)s). "
                        "يتطلب صلاحية مالية صريحة (financial.override_exchange_rate)."
                    )
                    % {
                        "code": getattr(currency, "code", str(currency)),
                        "official": official_rate,
                        "provided": provided,
                    }
                )
        except ValidationError:
            raise
        except Exception as e:
            logger.warning(f"تعذر التحقق من سعر الصرف: {e}")
