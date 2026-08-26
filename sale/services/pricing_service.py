import hashlib
from decimal import Decimal
from typing import Dict, Any, Optional, List
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

from sale.models.pricing import PriceList, PriceListItem, DiscountRule, PricingAuditLog
from product.models.product_core import Product, Unit
from financial.services.exchange_rate_service import ExchangeRateService


class PricingService:
    """
    FIN-SAL-004: Enterprise Sales Pricing Engine Service
    سلطة التسعير المركزية لحساب السعر المرجعي والخصم وتوثيق تتبع الأسعار لجميع معاملات المبيعات
    """

    @classmethod
    def _normalize_date(cls, d):
        """ضمان تحويل أي مدخل تاريخ إلى كائن datetime.date صحيح لتفادي أخطاء المقارنة مع النصوص"""
        if not d:
            return timezone.localdate()
        if hasattr(d, 'date') and callable(d.date):
            return d.date()
        from datetime import date
        if isinstance(d, date):
            return d
        if isinstance(d, str):
            try:
                from django.utils.dateparse import parse_date, parse_datetime
                parsed = parse_date(d)
                if parsed:
                    return parsed
                parsed_dt = parse_datetime(d)
                if parsed_dt:
                    return parsed_dt.date()
            except Exception:
                pass
        return timezone.localdate()

    @classmethod
    def get_pricing_context_cache(
        cls,
        customer_id: Optional[int] = None,
        price_list_id: Optional[int] = None,
        as_of_date=None
    ) -> Dict[str, Any]:
        """
        جلب وتجهيز كاش قواعد الأسعار والخصومات في استعلامين مجمعين فقط (2 SQL Queries Prefetch)
        """
        as_of_date = cls._normalize_date(as_of_date)
        
        # 1. جلب بنود قائمة الأسعار المحددة
        pl_items_map = {}
        price_list_currency = "EGP"
        if price_list_id:
            try:
                pl = PriceList.objects.get(
                    pk=price_list_id,
                    is_active=True
                )
                pl_eff_from = pl.effective_from.date() if hasattr(pl.effective_from, 'date') else pl.effective_from
                pl_eff_to = pl.effective_to.date() if hasattr(pl.effective_to, 'date') else pl.effective_to
                if not (pl_eff_from and pl_eff_from > as_of_date) and not (pl_eff_to and pl_eff_to < as_of_date):
                    price_list_currency = pl.currency
                    items_qs = PriceListItem.objects.filter(
                        price_list_id=price_list_id,
                        is_active=True
                    ).order_by("product_id", "-min_quantity")
                    for it in items_qs:
                        it_date = it.effective_date.date() if hasattr(it.effective_date, 'date') else it.effective_date
                        if not it_date or it_date <= as_of_date:
                            pl_items_map.setdefault(it.product_id, []).append({
                                "unit_price": it.unit_price,
                                "min_quantity": it.min_quantity
                            })
            except PriceList.DoesNotExist:
                pass

        # 2. جلب قواعد الخصم السارية
        rules_qs = DiscountRule.objects.filter(is_active=True)
        if customer_id:
            rules_qs = rules_qs.filter(models.Q(customer_id=customer_id) | models.Q(customer__isnull=True))
        else:
            rules_qs = rules_qs.filter(customer__isnull=True)

        rules_list = []
        for r in rules_qs.select_related("product", "category", "customer"):
            r_eff = r.effective_date.date() if hasattr(r.effective_date, 'date') else r.effective_date
            r_exp = r.expiry_date.date() if hasattr(r.expiry_date, 'date') else r.expiry_date
            if (not r_eff or r_eff <= as_of_date) and (not r_exp or r_exp >= as_of_date):
                rules_list.append(r)

        # حساب الـ version_hash
        hash_seed = f"{customer_id}_{price_list_id}_{len(pl_items_map)}_{len(rules_list)}_{as_of_date}"
        version_hash = hashlib.md5(hash_seed.encode("utf-8")).hexdigest()[:12]

        return {
            "price_list_id": price_list_id,
            "price_list_currency": price_list_currency,
            "price_list_items": pl_items_map,
            "discount_rules": rules_list,
            "version_hash": version_hash,
            "as_of_date": as_of_date
        }

    @classmethod
    def get_sales_price(
        cls,
        product_id: int,
        customer_id: Optional[int] = None,
        quantity: Decimal = Decimal("1.0000"),
        price_list_id: Optional[int] = None,
        unit_id: Optional[int] = None,
        as_of_date=None,
        currency: str = "EGP",
        exchange_rate: Optional[Decimal] = None,
        context_cache: Optional[Dict[str, Any]] = None,
        category_quantity_map: Optional[Dict[int, Decimal]] = None
    ) -> Dict[str, Any]:
        """
        الحصول على لقطة تسعير المبيعات الحاكمة للمنتج متضمنة السعر المرجعي والخصم التجاري المستحق
        """
        product = Product.objects.select_related("unit", "category").get(pk=product_id)
        as_of_date = cls._normalize_date(as_of_date)
        base_price = product.selling_price or Decimal("0.00")
        cost_price = product.cost_price or Decimal("0.00")
        target_currency = currency

        # 1. معامل تحويل وحدة القياس (UoM Conversion)
        uom_factor = Decimal("1.0000")
        if unit_id and product.unit_id and unit_id != product.unit_id:
            try:
                sale_unit = Unit.objects.get(pk=unit_id)
                # إذا كانت وحدة البيع تحتوي على معامل تحويل بالنسبة للوحدة الأساسية
                if hasattr(sale_unit, 'conversion_factor') and sale_unit.conversion_factor:
                    uom_factor = Decimal(str(sale_unit.conversion_factor))
            except Exception:
                pass

        # 2. تحديد السعر من قائمة الأسعار (Price List Resolution)
        matched_pl_item = False
        pl_currency = "EGP"

        if context_cache and "price_list_items" in context_cache:
            pl_currency = context_cache.get("price_list_currency", "EGP")
            cached_items = list(context_cache["price_list_items"].get(product_id, []))
            cached_items.sort(key=lambda x: Decimal(str(x["min_quantity"])), reverse=True)
            for it in cached_items:
                if quantity >= Decimal(str(it["min_quantity"])):
                    base_price = it["unit_price"]
                    matched_pl_item = True
                    break
        elif price_list_id:
            try:
                price_list = PriceList.objects.get(
                    pk=price_list_id,
                    is_active=True
                )
                pl_eff_from = price_list.effective_from.date() if hasattr(price_list.effective_from, 'date') else price_list.effective_from
                pl_eff_to = price_list.effective_to.date() if hasattr(price_list.effective_to, 'date') else price_list.effective_to
                if not (pl_eff_from and pl_eff_from > as_of_date) and not (pl_eff_to and pl_eff_to < as_of_date):
                    pl_currency = price_list.currency
                    items_qs = list(PriceListItem.objects.filter(
                        price_list=price_list,
                        product=product,
                        is_active=True
                    ))
                    items_qs.sort(key=lambda x: Decimal(str(x.min_quantity)), reverse=True)

                    for item in items_qs:
                        it_date = item.effective_date.date() if hasattr(item.effective_date, 'date') else item.effective_date
                        if (not it_date or it_date <= as_of_date) and quantity >= Decimal(str(item.min_quantity)):
                            base_price = item.unit_price
                            matched_pl_item = True
                            break
            except PriceList.DoesNotExist:
                pass

        # تطبيق معامل وحدة القياس على السعر المرجعي
        base_price = (base_price * uom_factor).quantize(Decimal("0.01"))
        cost_price = (cost_price * uom_factor).quantize(Decimal("0.01"))

        # 3. تحويل العملة IAS 21 بسعر صرف الفاتورة
        func_curr = ExchangeRateService.get_functional_currency()
        func_code = func_curr.code if func_curr else "EGP"

        rate = exchange_rate
        if rate is None or rate <= Decimal("0"):
            if target_currency != func_code:
                rate = ExchangeRateService.get_rate(target_currency, func_code, as_of_date)
            else:
                rate = Decimal("1.000000")

        # تحويل السعر لعملة الفاتورة إن كانت قائمة الأسعار أو الكتالوج بعملة مختلفة
        if matched_pl_item:
            if pl_currency != target_currency and rate > Decimal("0"):
                # إذا كانت قائمة الأسعار بالجنيه والفاتورة بالدولار: السعر بالدولار = السعر بالجنيه / سعر الصرف
                if pl_currency == func_code and target_currency != func_code:
                    base_price = (base_price / rate).quantize(Decimal("0.01"))
                elif pl_currency != func_code and target_currency == func_code:
                    base_price = (base_price * rate).quantize(Decimal("0.01"))
        else:
            if target_currency != func_code and rate > Decimal("0"):
                base_price = (base_price / rate).quantize(Decimal("0.01"))
                cost_price = (cost_price / rate).quantize(Decimal("0.01"))

        # 4. مطابقة قواعد الخصم (Discount Rule Matching & Tie-Breaking)
        rules_list = []
        if context_cache and "discount_rules" in context_cache:
            rules_list = context_cache["discount_rules"]
        else:
            rq = DiscountRule.objects.filter(is_active=True)
            if customer_id:
                rq = rq.filter(models.Q(customer_id=customer_id) | models.Q(customer__isnull=True))
            else:
                rq = rq.filter(customer__isnull=True)
            rules_list = []
            for r in rq.select_related("product", "category", "customer"):
                r_eff = r.effective_date.date() if hasattr(r.effective_date, 'date') else r.effective_date
                r_exp = r.expiry_date.date() if hasattr(r.expiry_date, 'date') else r.expiry_date
                if (not r_eff or r_eff <= as_of_date) and (not r_exp or r_exp >= as_of_date):
                    rules_list.append(r)

        matched_rules = []
        cat_id = product.category_id

        # حساب الكمية المقارنة لفحص شروط الفئة
        effective_category_qty = quantity
        if category_quantity_map and cat_id in category_quantity_map:
            effective_category_qty = category_quantity_map[cat_id]

        for rule in rules_list:
            # 1. مطابقة الصنف
            if rule.product_id and rule.product_id != product_id:
                continue
            # 2. مطابقة الفئة
            if rule.category_id and rule.category_id != cat_id:
                continue
            # 3. مطابقة العميل
            if rule.customer_id and rule.customer_id != customer_id:
                continue
            # 4. فحص شرط الكمية أو القيمة
            if rule.rule_type == "TIERED_QUANTITY":
                check_qty = effective_category_qty if rule.aggregation_type == "CATEGORY_TOTAL" else quantity
                if check_qty < rule.min_order_amount:
                    continue

            # حساب القيمة النقدية المقدرة للخصم للمقارنة (Tie-Breaking)
            calculated_discount_val = Decimal("0.00")
            if rule.rule_type in ("PERCENTAGE", "TIERED_QUANTITY"):
                calculated_discount_val = (base_price * (rule.discount_percentage / Decimal("100.00"))).quantize(Decimal("0.01"))
            elif rule.rule_type == "FIXED_AMOUNT":
                calculated_discount_val = rule.value

            matched_rules.append({
                "rule": rule,
                "priority": rule.priority,
                "calculated_discount_val": calculated_discount_val,
                "specificity": (3 if rule.product_id else (2 if rule.category_id else (1 if rule.customer_id else 0)))
            })

        best_match = None
        if matched_rules:
            # الترتيب: الأولوية أولاً، ثم التخصيص الأكثر دقة (صنف > فئة > عميل)، ثم القيمة النقدية الأكبر للخصم
            matched_rules.sort(
                key=lambda x: (x["priority"], x["specificity"], x["calculated_discount_val"]),
                reverse=True
            )
            best_match = matched_rules[0]

        disc_pct = Decimal("0.00")
        disc_amount = Decimal("0.00")
        rule_id = None
        rule_name = ""

        if best_match:
            r = best_match["rule"]
            rule_id = r.id
            rule_name = r.rule_name
            if r.rule_type in ("PERCENTAGE", "TIERED_QUANTITY"):
                disc_pct = r.discount_percentage
                disc_amount = (base_price * (disc_pct / Decimal("100.00"))).quantize(Decimal("0.01"))
            elif r.rule_type == "FIXED_AMOUNT":
                disc_amount = min(base_price, r.value.quantize(Decimal("0.01")))
                if base_price > Decimal("0"):
                    disc_pct = ((disc_amount / base_price) * Decimal("100.00")).quantize(Decimal("0.01"))

        final_price = max(Decimal("0.00"), base_price - disc_amount).quantize(Decimal("0.01"))
        func_price = (final_price * rate).quantize(Decimal("0.01"))
        is_below_cost = (final_price < cost_price) and (cost_price > Decimal("0"))

        return {
            "product_id": product_id,
            "product_name": product.name,
            "sku": getattr(product, "sku", ""),
            "base_price": base_price,
            "cost_price": cost_price,
            "discount_percentage": disc_pct,
            "discount_amount": disc_amount,
            "final_price": final_price,
            "rule_id": rule_id,
            "rule_name": rule_name,
            "currency": target_currency,
            "exchange_rate": rate,
            "functional_price": func_price,
            "is_below_cost": is_below_cost,
            "price_snapshot": {
                "base_price": str(base_price),
                "discount_amount": str(disc_amount),
                "discount_percentage": str(disc_pct),
                "rule_id": rule_id,
                "rule_name": rule_name,
                "price_list_id": price_list_id,
                "uom_factor": str(uom_factor),
                "calculated_at": str(timezone.now())
            }
        }

    @classmethod
    def evaluate_cart_pricing(
        cls,
        items: List[Dict[str, Any]],
        customer_id: Optional[int] = None,
        price_list_id: Optional[int] = None,
        as_of_date=None,
        currency: str = "EGP",
        exchange_rate: Optional[Decimal] = None,
        header_discount: Decimal = Decimal("0.00"),
        header_discount_type: str = "fixed",
        vat_active: bool = True,
        vat_rate: Decimal = Decimal("14.00"),
        wht_active: bool = False,
        wht_rate: Decimal = Decimal("1.00"),
        max_discount_threshold_pct: Decimal = Decimal("30.00")
    ) -> Dict[str, Any]:
        """
        تقييم سلة بنود المبيعات بالكامل دفعة واحدة مع التوزيع النسبي للخصومات وحساب وعاء الفاتورة الإلكترونية ETA
        """
        as_of_date = cls._normalize_date(as_of_date)
        context_cache = cls.get_pricing_context_cache(customer_id, price_list_id, as_of_date)

        # 1. تجميع كميات الفئات المشتركة
        product_ids = [int(it.get("product_id") or it.get("product")) for it in items if (it.get("product_id") or it.get("product"))]
        products_dict = {p.id: p for p in Product.objects.filter(id__in=product_ids).select_related("category")}

        category_qty_map = {}
        for it in items:
            p_id = int(it.get("product_id") or it.get("product"))
            qty = Decimal(str(it.get("quantity") or 1))
            prod = products_dict.get(p_id)
            if prod and prod.category_id:
                category_qty_map[prod.category_id] = category_qty_map.get(prod.category_id, Decimal("0.00")) + qty

        # 2. تقييم كل بند في السلة
        evaluated_items = []
        subtotal = Decimal("0.00")
        total_line_discounts = Decimal("0.00")
        has_below_cost_warning = False

        for it in items:
            p_id = int(it.get("product_id") or it.get("product"))
            qty = Decimal(str(it.get("quantity") or 1))
            u_id = it.get("unit_id")
            manual_discount = Decimal(str(it.get("manual_discount") or it.get("discount") or 0))

            price_info = cls.get_sales_price(
                product_id=p_id,
                customer_id=customer_id,
                quantity=qty,
                price_list_id=price_list_id,
                unit_id=u_id,
                as_of_date=as_of_date,
                currency=currency,
                exchange_rate=exchange_rate,
                context_cache=context_cache,
                category_quantity_map=category_qty_map
            )

            # إذا وضع المندوب خصماً يدوياً أكبر من الخصم المعتمد في السياسة
            applied_line_discount = max(price_info["discount_amount"] * qty, manual_discount)
            line_gross = (price_info["base_price"] * qty).quantize(Decimal("0.01"))
            line_net = max(Decimal("0.00"), line_gross - applied_line_discount).quantize(Decimal("0.01"))

            if price_info["is_below_cost"]:
                has_below_cost_warning = True

            subtotal += line_gross
            total_line_discounts += applied_line_discount

            evaluated_items.append({
                "product_id": p_id,
                "product_name": price_info["product_name"],
                "sku": price_info["sku"],
                "quantity": qty,
                "unit_id": u_id,
                "unit_price": price_info["base_price"],
                "cost_price": price_info["cost_price"],
                "policy_discount_amount": price_info["discount_amount"],
                "policy_discount_percentage": price_info["discount_percentage"],
                "applied_discount": applied_line_discount,
                "rule_id": price_info["rule_id"],
                "rule_name": price_info["rule_name"],
                "line_total": line_net,
                "is_below_cost": price_info["is_below_cost"],
                "price_snapshot": price_info["price_snapshot"]
            })

        # 3. احتساب وتوزيع خصم الفاتورة الإجمالي (ETA Proportional Distribution)
        net_after_line_discounts = max(Decimal("0.00"), subtotal - total_line_discounts)
        actual_header_discount = Decimal("0.00")

        if header_discount_type == "percentage":
            actual_header_discount = (net_after_line_discounts * (header_discount / Decimal("100.00"))).quantize(Decimal("0.01"))
        else:
            actual_header_discount = min(net_after_line_discounts, header_discount.quantize(Decimal("0.01")))

        taxable_base = max(Decimal("0.00"), net_after_line_discounts - actual_header_discount)

        # فحص سقف الخصم التراكمي الإجمالي
        total_all_discounts = total_line_discounts + actual_header_discount
        discount_percentage_overall = ((total_all_discounts / subtotal) * Decimal("100.00")).quantize(Decimal("0.01")) if subtotal > 0 else Decimal("0.00")
        is_exceeding_max_discount = discount_percentage_overall > max_discount_threshold_pct

        # 4. حساب ضريبة القيمة المضافة (14% VAT) وضريبة الخصم والإضافة (1% WHT)
        vat_amount = Decimal("0.00")
        if vat_active and vat_rate > Decimal("0"):
            vat_amount = (taxable_base * (vat_rate / Decimal("100.00"))).quantize(Decimal("0.01"))

        wht_amount = Decimal("0.00")
        if wht_active and wht_rate > Decimal("0"):
            wht_amount = (taxable_base * (wht_rate / Decimal("100.00"))).quantize(Decimal("0.01"))

        final_invoice_total = (taxable_base + vat_amount - wht_amount).quantize(Decimal("0.01"))

        return {
            "items": evaluated_items,
            "subtotal": subtotal,
            "total_line_discounts": total_line_discounts,
            "header_discount": actual_header_discount,
            "total_all_discounts": total_all_discounts,
            "discount_percentage_overall": discount_percentage_overall,
            "is_exceeding_max_discount": is_exceeding_max_discount,
            "taxable_base": taxable_base,
            "vat_active": vat_active,
            "vat_rate": vat_rate,
            "vat_amount": vat_amount,
            "wht_active": wht_active,
            "wht_rate": wht_rate,
            "wht_amount": wht_amount,
            "total": final_invoice_total,
            "currency": currency,
            "exchange_rate": exchange_rate or Decimal("1.000000"),
            "has_below_cost_warning": has_below_cost_warning,
            "version_hash": context_cache.get("version_hash", "")
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
                PriceListItem.objects.create(
                    price_list_id=price_list_id,
                    product=product,
                    unit_price=new_price,
                    min_quantity=Decimal("1.0000"),
                    is_active=True
                )
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
