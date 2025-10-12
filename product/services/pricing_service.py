from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from decimal import Decimal
from typing import Optional, List, Dict, Any
import logging

from product.models import Product, SupplierProductPrice, PriceHistory
from supplier.models import Supplier

logger = logging.getLogger(__name__)
User = get_user_model()


class PricingService:
    """
    خدمة إدارة أسعار المنتجات حسب الموردين
    """

    @staticmethod
    def update_supplier_price(
        product: Product,
        supplier: Supplier,
        new_price: Decimal,
        user: User,
        reason: str = "manual_update",
        purchase_reference: Optional[str] = None,
        purchase_quantity: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> Optional[SupplierProductPrice]:
        """
        تحديث سعر منتج لمورد معين مع تسجيل التاريخ
        """
        try:
            with transaction.atomic():
                # الحصول على أو إنشاء سعر المورد
                supplier_price, created = SupplierProductPrice.objects.get_or_create(
                    product=product,
                    supplier=supplier,
                    defaults={
                        "cost_price": new_price,
                        "created_by": user,
                        "is_default": not SupplierProductPrice.objects.filter(
                            product=product
                        ).exists(),
                        "notes": notes,
                    },
                )

                # إذا كان السعر موجود وتغير، سجل التغيير في التاريخ
                if not created and supplier_price.cost_price != new_price:
                    PriceHistory.objects.create(
                        supplier_product_price=supplier_price,
                        old_price=supplier_price.cost_price,
                        new_price=new_price,
                        change_reason=reason,
                        purchase_reference=purchase_reference,
                        notes=notes,
                        changed_by=user,
                    )

                    # تحديث السعر
                    supplier_price.cost_price = new_price

                # تحديث معلومات آخر شراء إذا كان السبب شراء جديد
                if reason == "purchase" and purchase_quantity:
                    supplier_price.last_purchase_date = timezone.now().date()
                    supplier_price.last_purchase_quantity = purchase_quantity

                # تحديث الملاحظات إذا تم توفيرها
                if notes:
                    supplier_price.notes = notes

                supplier_price.save()

                # تحديث سعر التكلفة الرئيسي للمنتج إذا كان هذا المورد افتراضي
                if supplier_price.is_default:
                    PricingService._update_product_main_cost_price(product, new_price)

                logger.info(
                    f"تم تحديث سعر المنتج {product.name} للمورد {supplier.name} إلى {new_price}"
                )
                return supplier_price

        except Exception as e:
            logger.error(f"خطأ في تحديث سعر المورد: {e}")
            return None

    @staticmethod
    def set_default_supplier(product: Product, supplier: Supplier, user: User) -> bool:
        """
        تعيين مورد كافتراضي لمنتج معين
        """
        try:
            with transaction.atomic():
                # التأكد من وجود سعر للمورد
                supplier_price = SupplierProductPrice.objects.filter(
                    product=product, supplier=supplier, is_active=True
                ).first()

                if not supplier_price:
                    logger.warning(
                        f"لا يوجد سعر للمنتج {product.name} عند المورد {supplier.name}"
                    )
                    return False

                # إلغاء الافتراضي من جميع الموردين الآخرين
                SupplierProductPrice.objects.filter(
                    product=product, is_default=True
                ).exclude(pk=supplier_price.pk).update(is_default=False)

                # تعيين المورد الجديد كافتراضي
                supplier_price.is_default = True
                supplier_price.save()

                # تحديث المورد الافتراضي في نموذج المنتج
                product.default_supplier = supplier
                product.save(update_fields=["default_supplier"])

                # تحديث سعر التكلفة الرئيسي
                PricingService._update_product_main_cost_price(
                    product, supplier_price.cost_price
                )

                logger.info(
                    f"تم تعيين {supplier.name} كمورد افتراضي للمنتج {product.name}"
                )
                return True

        except Exception as e:
            logger.error(f"خطأ في تعيين المورد الافتراضي: {e}")
            return False

    @staticmethod
    def get_price_comparison(product: Product) -> List[Dict[str, Any]]:
        """
        الحصول على مقارنة أسعار جميع الموردين لمنتج معين
        """
        try:
            supplier_prices = (
                SupplierProductPrice.objects.filter(product=product, is_active=True)
                .select_related("supplier")
                .order_by("-is_default", "cost_price")
            )

            comparison = []
            main_price = product.cost_price or Decimal("0")

            for sp in supplier_prices:
                price_diff = (
                    sp.cost_price - main_price if main_price > 0 else Decimal("0")
                )
                price_diff_percent = (
                    (price_diff / main_price * 100) if main_price > 0 else Decimal("0")
                )

                comparison.append(
                    {
                        "supplier": sp.supplier,
                        "price": sp.cost_price,
                        "is_default": sp.is_default,
                        "last_purchase_date": sp.last_purchase_date,
                        "last_purchase_quantity": sp.last_purchase_quantity,
                        "price_difference": price_diff,
                        "price_difference_percent": price_diff_percent,
                        "days_since_last_purchase": sp.days_since_last_purchase,
                        "notes": sp.notes,
                    }
                )

            return comparison

        except Exception as e:
            logger.error(f"خطأ في الحصول على مقارنة الأسعار: {e}")
            return []

    @staticmethod
    def get_price_history(
        product: Product, supplier: Optional[Supplier] = None, limit: int = 50
    ) -> List[PriceHistory]:
        """
        الحصول على تاريخ تغيير الأسعار لمنتج معين
        """
        try:
            query = PriceHistory.objects.select_related(
                "supplier_product_price__product",
                "supplier_product_price__supplier",
                "changed_by",
            ).filter(supplier_product_price__product=product)

            if supplier:
                query = query.filter(supplier_product_price__supplier=supplier)

            return list(query.order_by("-change_date")[:limit])

        except Exception as e:
            logger.error(f"خطأ في الحصول على تاريخ الأسعار: {e}")
            return []

    @staticmethod
    def bulk_update_prices(
        updates: List[Dict[str, Any]], user: User, reason: str = "bulk_update"
    ) -> Dict[str, int]:
        """
        تحديث أسعار متعددة دفعة واحدة

        updates: قائمة من القواميس تحتوي على:
        - product_id: معرف المنتج
        - supplier_id: معرف المورد
        - new_price: السعر الجديد
        - notes: ملاحظات (اختياري)
        """
        results = {"success": 0, "failed": 0, "errors": []}

        for update_data in updates:
            try:
                product = Product.objects.get(pk=update_data["product_id"])
                supplier = Supplier.objects.get(pk=update_data["supplier_id"])
                new_price = Decimal(str(update_data["new_price"]))
                notes = update_data.get("notes", "")

                result = PricingService.update_supplier_price(
                    product=product,
                    supplier=supplier,
                    new_price=new_price,
                    user=user,
                    reason=reason,
                    notes=notes,
                )

                if result:
                    results["success"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].append(
                        f"فشل تحديث {product.name} - {supplier.name}"
                    )

            except (Product.DoesNotExist, Supplier.DoesNotExist) as e:
                results["failed"] += 1
                results["errors"].append(f"منتج أو مورد غير موجود: {e}")
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"خطأ في التحديث: {e}")

        return results

    @staticmethod
    def get_cheapest_suppliers(
        product: Product, limit: int = 5
    ) -> List[SupplierProductPrice]:
        """
        الحصول على أرخص الموردين لمنتج معين
        """
        try:
            return list(
                SupplierProductPrice.objects.filter(product=product, is_active=True)
                .select_related("supplier")
                .order_by("cost_price")[:limit]
            )

        except Exception as e:
            logger.error(f"خطأ في الحصول على أرخص الموردين: {e}")
            return []

    @staticmethod
    def get_supplier_products_summary(supplier: Supplier) -> Dict[str, Any]:
        """
        الحصول على ملخص منتجات مورد معين
        """
        try:
            supplier_prices = SupplierProductPrice.objects.filter(
                supplier=supplier, is_active=True
            ).select_related("product")

            total_products = supplier_prices.count()
            default_products = supplier_prices.filter(is_default=True).count()
            from django.db.models import Avg

            avg_price = supplier_prices.aggregate(avg_price=Avg("cost_price"))[
                "avg_price"
            ] or Decimal("0")

            recent_purchases = supplier_prices.filter(
                last_purchase_date__isnull=False
            ).order_by("-last_purchase_date")[:5]

            return {
                "total_products": total_products,
                "default_products": default_products,
                "average_price": avg_price,
                "recent_purchases": list(recent_purchases),
            }

        except Exception as e:
            logger.error(f"خطأ في الحصول على ملخص المورد: {e}")
            return {}

    @staticmethod
    def _update_product_main_cost_price(product: Product, new_price: Decimal):
        """
        تحديث سعر التكلفة الرئيسي للمنتج (دالة داخلية)
        """
        try:
            if product.cost_price != new_price:
                Product.objects.filter(pk=product.pk).update(cost_price=new_price)
                logger.info(
                    f"تم تحديث سعر التكلفة الرئيسي للمنتج {product.name} إلى {new_price}"
                )
        except Exception as e:
            logger.error(f"خطأ في تحديث سعر التكلفة الرئيسي: {e}")

    @staticmethod
    def sync_purchase_prices(purchase_items: List[Any], user: User) -> Dict[str, int]:
        """
        مزامنة أسعار المنتجات من فاتورة شراء
        """
        results = {"updated": 0, "created": 0, "errors": []}

        try:
            for item in purchase_items:
                try:
                    # تحديث سعر المنتج للمورد
                    supplier_price = PricingService.update_supplier_price(
                        product=item.product,
                        supplier=item.purchase.supplier,
                        new_price=item.unit_price,
                        user=user,
                        reason="purchase",
                        purchase_reference=item.purchase.number,
                        purchase_quantity=item.quantity,
                        notes=f"تحديث تلقائي من فاتورة شراء {item.purchase.number}",
                    )

                    if supplier_price:
                        results["updated"] += 1
                    else:
                        results["created"] += 1

                except Exception as e:
                    results["errors"].append(f"خطأ في تحديث {item.product.name}: {e}")

            return results

        except Exception as e:
            logger.error(f"خطأ في مزامنة أسعار الشراء: {e}")
            return {"updated": 0, "created": 0, "errors": [str(e)]}

    @staticmethod
    def bulk_update_prices(price_updates, user, reason="bulk_update"):
        """تحديث أسعار متعددة"""
        try:
            results = {"updated": 0, "created": 0, "errors": []}

            for update in price_updates:
                try:
                    supplier_price = SupplierProductPrice.objects.get(
                        id=update["supplier_price_id"]
                    )

                    old_price = supplier_price.cost_price
                    supplier_price.cost_price = update["new_price"]
                    supplier_price.save()

                    # إنشاء تاريخ تغيير السعر
                    PriceHistory.objects.create(
                        supplier_product_price=supplier_price,
                        old_price=old_price,
                        new_price=update["new_price"],
                        change_reason=reason,
                        changed_by=user,
                    )

                    results["updated"] += 1

                except Exception as e:
                    results["errors"].append(f"خطأ في تحديث السعر: {e}")

            return results

        except Exception as e:
            logger.error(f"خطأ في التحديث المتعدد للأسعار: {e}")
            return {"updated": 0, "created": 0, "errors": [str(e)]}

    @staticmethod
    def get_price_comparison(product):
        """مقارنة أسعار المنتج من جميع الموردين"""
        try:
            prices = (
                SupplierProductPrice.objects.filter(product=product)
                .select_related("supplier")
                .order_by("cost_price")
            )

            if not prices.exists():
                return {
                    "product": product,
                    "prices": [],
                    "lowest_price": None,
                    "highest_price": None,
                    "default_supplier": None,
                }

            price_list = []
            for price in prices:
                price_list.append(
                    {
                        "supplier": price.supplier,
                        "cost_price": price.cost_price,
                        "is_default": price.is_default,
                    }
                )

            default_supplier = prices.filter(is_default=True).first()

            return {
                "product": product,
                "prices": price_list,
                "lowest_price": prices.first().cost_price,
                "highest_price": prices.last().cost_price,
                "default_supplier": default_supplier.supplier
                if default_supplier
                else None,
            }

        except Exception as e:
            logger.error(f"خطأ في مقارنة الأسعار: {e}")
            return {"product": product, "prices": [], "error": str(e)}
