from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone
from decimal import Decimal
from .models import StockMovement, Stock, Product, ProductImage
from sale.models import Sale
from purchase.models import Purchase

# استيراد آمن للنماذج المحسنة
try:
    from .models.warehouse import ProductStock
    from .models.inventory_movement import InventoryMovement
    from .services.inventory_service import InventoryService
    from core.services.notification_service import NotificationService
except ImportError:
    ProductStock = InventoryMovement = InventoryService = NotificationService = None


@receiver(pre_save, sender=Product)
def ensure_unique_sku(sender, instance, **kwargs):
    """
    التأكد من أن الـ كود المنتج فريد وإنشاءه تلقائيًا إذا لم يتم توفيره
    """
    if not instance.sku:
        # إنشاء كود المنتج فريد من اسم المنتج والوقت
        timestamp = timezone.now().strftime("%y%m%d%H%M")
        base_slug = slugify(instance.name)[:10]
        instance.sku = f"{base_slug}-{timestamp}"


@receiver(post_save, sender=ProductImage)
def ensure_single_primary_image(sender, instance, created, **kwargs):
    """
    التأكد من وجود صورة رئيسية واحدة فقط لكل منتج
    """
    if instance.is_primary:
        # إذا تم تعيين هذه الصورة كصورة رئيسية، قم بإلغاء تعيين أي صور أخرى كصور رئيسية
        ProductImage.objects.filter(product=instance.product, is_primary=True).exclude(
            pk=instance.pk
        ).update(is_primary=False)
    else:
        # إذا لم تكن هناك صورة رئيسية للمنتج، قم بتعيين أول صورة كصورة رئيسية
        if not ProductImage.objects.filter(
            product=instance.product, is_primary=True
        ).exists():
            instance.is_primary = True
            instance.save()


@receiver(post_save, sender=StockMovement)
def update_stock_on_movement(sender, instance, created, **kwargs):
    """
    تحديث المخزون بعد حفظ حركة المخزون بنجاح

    هذا هو المكان الصحيح لتحديث المخزون (Django Best Practice)
    Signal يضمن تحديث المخزون فقط بعد حفظ الحركة بنجاح
    """
    if created:
        # تحقق من flag لتجنب التحديث المزدوج
        if hasattr(instance, "_skip_update") and instance._skip_update:
            return

        # الحصول على المخزون الحالي أو إنشاء واحد جديد
        stock, created_stock = Stock.objects.get_or_create(
            product=instance.product,
            warehouse=instance.warehouse,
            defaults={"quantity": Decimal("0")},
        )

        # تحديث المخزون بناءً على نوع الحركة
        if instance.movement_type == "in":
            stock.quantity += Decimal(instance.quantity)
        elif instance.movement_type == "out":
            stock.quantity = max(
                Decimal("0"), stock.quantity - Decimal(instance.quantity)
            )
        elif instance.movement_type == "transfer" and instance.destination_warehouse:
            # خفض المخزون من المخزن المصدر
            stock.quantity = max(
                Decimal("0"), stock.quantity - Decimal(instance.quantity)
            )

            # زيادة المخزون في المخزن الوجهة
            dest_stock, dest_created = Stock.objects.get_or_create(
                product=instance.product,
                warehouse=instance.destination_warehouse,
                defaults={"quantity": Decimal("0")},
            )
            dest_stock.quantity += Decimal(instance.quantity)
            dest_stock.save()
        elif instance.movement_type == "adjustment":
            stock.quantity = Decimal(instance.quantity)

        # حفظ التغييرات
        stock.save()

        # فحص تنبيهات المخزون المنخفض للنظام المحسن
        if ProductStock and NotificationService:
            try:
                # البحث عن ProductStock المحسن
                enhanced_stock = ProductStock.objects.filter(
                    product=instance.product, warehouse=instance.warehouse
                ).first()

                if enhanced_stock and enhanced_stock.is_low_stock:
                    # إنشاء تنبيه فوري
                    _create_low_stock_alert(instance.product, enhanced_stock)
            except Exception as e:
                # تسجيل الخطأ بدون إيقاف العملية
                print(f"خطأ في فحص تنبيه المخزون المنخفض: {e}")

        # فحص تنبيهات المخزون للنظام القديم
        elif (
            instance.product.min_stock > 0
            and stock.quantity <= instance.product.min_stock
        ):
            _create_legacy_low_stock_alert(instance.product, stock)


@receiver(post_delete, sender=StockMovement)
def revert_stock_on_movement_delete(sender, instance, **kwargs):
    """
    إلغاء تأثير حركة المخزون عند حذفها
    """
    try:
        # البحث عن سجل المخزون المرتبط
        stock = Stock.objects.get(
            product=instance.product, warehouse=instance.warehouse
        )

        if instance.movement_type == "in":
            # إلغاء تأثير الإضافة - خفض المخزون
            stock.quantity = max(
                Decimal("0"), stock.quantity - Decimal(instance.quantity)
            )
        elif instance.movement_type == "out":
            # إلغاء تأثير السحب - زيادة المخزون
            stock.quantity += Decimal(instance.quantity)
        elif instance.movement_type == "transfer":
            # إلغاء تأثير التحويل
            stock.quantity += Decimal(instance.quantity)

            # معالجة المخزن المستلم إذا كان موجودًا
            if instance.destination_warehouse:
                try:
                    dest_stock = Stock.objects.get(
                        product=instance.product,
                        warehouse=instance.destination_warehouse,
                    )
                    dest_stock.quantity = max(
                        Decimal("0"), dest_stock.quantity - Decimal(instance.quantity)
                    )
                    dest_stock.save()
                except Stock.DoesNotExist:
                    pass

        # حفظ التغييرات على المخزون
        stock.save()
    except Stock.DoesNotExist:
        # إذا لم يكن هناك سجل مخزون، فلا يوجد شيء للتعديل
        pass


@receiver(post_delete, sender=Sale)
def handle_sale_delete(sender, instance, **kwargs):
    """
    معالجة حذف فاتورة المبيعات
    """
    # لا نقوم بإعادة تعيين الرقم التسلسلي عند الحذف
    pass


@receiver(post_delete, sender=Purchase)
def handle_purchase_delete(sender, instance, **kwargs):
    """
    معالجة حذف فاتورة المشتريات
    """
    # لا نقوم بإعادة تعيين الرقم التسلسلي عند الحذف
    pass


@receiver(post_delete, sender=StockMovement)
def handle_stock_movement_delete(sender, instance, **kwargs):
    """
    معالجة حذف حركة المخزون
    """
    # لا نقوم بإعادة تعيين الرقم التسلسلي عند الحذف
    pass


def _create_low_stock_alert(product, stock):
    """
    إنشاء تنبيه مخزون منخفض للنظام المحسن
    """
    if not NotificationService:
        return

    try:
        from django.contrib.auth import get_user_model
        from django.db import models

        User = get_user_model()

        # الحصول على المستخدمين المخولين
        authorized_users = User.objects.filter(
            models.Q(groups__name__in=["مدير مخزون", "مدير", "Admin"])
            | models.Q(is_superuser=True),
            is_active=True,
        ).distinct()

        # تحديد نوع التنبيه
        if stock.is_out_of_stock:
            alert_type = "نفد"
            notification_type = "danger"
        else:
            alert_type = "منخفض"
            notification_type = "warning"

        title = f"تنبيه مخزون {alert_type}: {product.name}"
        message = (
            f"المنتج '{product.name}' في المخزن '{stock.warehouse.name}' {alert_type}.\n"
            f"الكمية الحالية: {stock.quantity} {product.unit.symbol}\n"
            f"الحد الأدنى: {stock.min_stock_level} {product.unit.symbol}\n"
            f"يُرجى إعادة التزويد فوراً."
        )

        # إنشاء تنبيه لجميع المستخدمين المخولين
        for user in authorized_users:
            NotificationService.create_notification(
                user=user,
                title=title,
                message=message,
                notification_type=notification_type,
                related_model="Product",
                related_id=product.id,
                link_url=f"/products/{product.id}/"
            )

    except Exception as e:
        print(f"خطأ في إنشاء تنبيه المخزون المنخفض: {e}")


def _create_legacy_low_stock_alert(product, stock):
    """
    إنشاء تنبيه مخزون منخفض للنظام القديم
    """
    try:
        from django.contrib.auth import get_user_model
        from django.db import models
        from core.models import Notification

        User = get_user_model()

        # الحصول على المستخدمين المخولين
        authorized_users = User.objects.filter(
            models.Q(groups__name__in=["مدير مخزون", "مدير", "Admin"])
            | models.Q(is_superuser=True),
            is_active=True,
        ).distinct()

        # تحديد نوع التنبيه
        if stock.quantity == 0:
            alert_type = "نفد"
            notification_type = "danger"
        else:
            alert_type = "منخفض"
            notification_type = "warning"

        title = f"تنبيه مخزون {alert_type}: {product.name}"
        message = (
            f"المنتج '{product.name}' {alert_type} في المخزون.\n"
            f"الكمية الحالية: {stock.quantity} {product.unit.symbol}\n"
            f"الحد الأدنى: {product.min_stock} {product.unit.symbol}\n"
            f"يُرجى إعادة التزويد فوراً."
        )

        # إنشاء تنبيه لجميع المستخدمين المخولين
        for user in authorized_users:
            Notification.objects.create(
                user=user, title=title, message=message, type=notification_type
            )

    except Exception as e:
        print(f"خطأ في إنشاء تنبيه المخزون القديم: {e}")


# Signal للنظام المحسن
if InventoryMovement:

    @receiver(post_save, sender=InventoryMovement)
    def handle_enhanced_inventory_movement(sender, instance, created, **kwargs):
        """
        معالجة حركات المخزون المحسنة مع تنبيهات فورية
        """
        if created and instance.is_approved:
            # فحص تنبيهات المخزون المنخفض
            try:
                stock = ProductStock.objects.get(
                    product=instance.product, warehouse=instance.warehouse
                )

                if stock.is_low_stock or stock.is_out_of_stock:
                    _create_low_stock_alert(instance.product, stock)

            except ProductStock.DoesNotExist:
                pass
            except Exception as e:
                print(f"خطأ في معالجة حركة المخزون المحسنة: {e}")
