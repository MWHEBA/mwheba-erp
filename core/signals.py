"""
إشارات Django لإنشاء إشعارات تلقائية عند الأحداث المختلفة
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .services.notification_service import NotificationService
from .models import SystemSetting

User = get_user_model()


# ==================== إشعارات المبيعات ====================

@receiver(post_save, sender='sale.Sale')
def notify_new_sale(sender, instance, created, **kwargs):
    """
    إنشاء إشعار عند إنشاء فاتورة بيع جديدة
    """
    if created:
        # جلب المستخدمين المخولين (المحاسبين والمدراء)
        authorized_users = User.objects.filter(
            Q(user_type__in=['admin', 'accountant']) | Q(is_superuser=True),
            is_active=True
        ).distinct()
        
        # إنشاء إشعار لكل مستخدم مخول
        for user in authorized_users:
            NotificationService.create_notification(
                user=user,
                title=f"فاتورة بيع جديدة #{instance.number}",
                message=f"تم إنشاء فاتورة بيع جديدة للعميل {instance.customer.name} بقيمة {instance.total} {SystemSetting.get_currency_symbol()}",
                notification_type="new_invoice",
                related_model="Sale",
                related_id=instance.id,
                link_url=f"/sales/{instance.id}/"
            )


@receiver(post_save, sender='sale.SalePayment')
def notify_payment_received(sender, instance, created, **kwargs):
    """
    إنشاء إشعار عند استلام دفعة
    """
    if created:
        # جلب المستخدمين المخولين
        authorized_users = User.objects.filter(
            Q(user_type__in=['admin', 'accountant']) | Q(is_superuser=True),
            is_active=True
        ).distinct()
        
        for user in authorized_users:
            NotificationService.create_notification(
                user=user,
                title=f"دفعة مستلمة - فاتورة #{instance.sale.number}",
                message=f"تم استلام دفعة بقيمة {instance.amount} {SystemSetting.get_currency_symbol()} من العميل {instance.sale.customer.name}",
                notification_type="payment_received",
                related_model="Sale",
                related_id=instance.sale.id,
                link_url=f"/sales/{instance.sale.id}/"
            )


@receiver(post_save, sender='sale.SaleReturn')
def notify_sale_return(sender, instance, created, **kwargs):
    """
    إنشاء إشعار عند طلب إرجاع مبيعات
    """
    if created:
        # جلب المستخدمين المخولين
        authorized_users = User.objects.filter(
            Q(user_type__in=['admin', 'accountant', 'inventory_manager']) | Q(is_superuser=True),
            is_active=True
        ).distinct()
        
        for user in authorized_users:
            NotificationService.create_notification(
                user=user,
                title=f"طلب إرجاع - فاتورة #{instance.sale.number}",
                message=f"تم إنشاء طلب إرجاع للعميل {instance.sale.customer.name} بقيمة {instance.total_amount} {SystemSetting.get_currency_symbol()}",
                notification_type="return_request",
                related_model="Sale",
                related_id=instance.sale.id,
                link_url=f"/sales/{instance.sale.id}/"
            )


# ==================== إشعارات المشتريات ====================

@receiver(post_save, sender='purchase.Purchase')
def notify_new_purchase(sender, instance, created, **kwargs):
    """
    إنشاء إشعار عند إنشاء فاتورة شراء جديدة
    """
    if created:
        # جلب المستخدمين المخولين
        authorized_users = User.objects.filter(
            Q(user_type__in=['admin', 'accountant']) | Q(is_superuser=True),
            is_active=True
        ).distinct()
        
        for user in authorized_users:
            NotificationService.create_notification(
                user=user,
                title=f"فاتورة شراء جديدة #{instance.number}",
                message=f"تم إنشاء فاتورة شراء جديدة من المورد {instance.supplier.name} بقيمة {instance.total} {SystemSetting.get_currency_symbol()}",
                notification_type="new_invoice",
                related_model="Purchase",
                related_id=instance.id,
                link_url=f"/purchases/{instance.id}/"
            )


@receiver(post_save, sender='purchase.PurchasePayment')
def notify_purchase_payment(sender, instance, created, **kwargs):
    """
    إنشاء إشعار عند سداد دفعة للمورد
    """
    if created:
        # جلب المستخدمين المخولين
        authorized_users = User.objects.filter(
            Q(user_type__in=['admin', 'accountant']) | Q(is_superuser=True),
            is_active=True
        ).distinct()
        
        for user in authorized_users:
            NotificationService.create_notification(
                user=user,
                title=f"دفعة مسددة - فاتورة #{instance.purchase.number}",
                message=f"تم سداد دفعة بقيمة {instance.amount} {SystemSetting.get_currency_symbol()} للمورد {instance.purchase.supplier.name}",
                notification_type="success",
                related_model="Purchase",
                related_id=instance.purchase.id,
                link_url=f"/purchases/{instance.purchase.id}/"
            )


@receiver(post_save, sender='purchase.PurchaseReturn')
def notify_purchase_return(sender, instance, created, **kwargs):
    """
    إنشاء إشعار عند إرجاع مشتريات
    """
    if created:
        # جلب المستخدمين المخولين
        authorized_users = User.objects.filter(
            Q(user_type__in=['admin', 'accountant', 'inventory_manager']) | Q(is_superuser=True),
            is_active=True
        ).distinct()
        
        for user in authorized_users:
            NotificationService.create_notification(
                user=user,
                title=f"إرجاع مشتريات - فاتورة #{instance.purchase.number}",
                message=f"تم إرجاع مشتريات للمورد {instance.purchase.supplier.name} بقيمة {instance.total_amount} {SystemSetting.get_currency_symbol()}",
                notification_type="warning",
                related_model="Purchase",
                related_id=instance.purchase.id,
                link_url=f"/purchases/{instance.purchase.id}/"
            )


# ==================== إشعارات العملاء ====================

@receiver(post_save, sender='client.Customer')
def notify_new_customer(sender, instance, created, **kwargs):
    """
    إنشاء إشعار عند إضافة عميل جديد
    """
    if created:
        # جلب المستخدمين المخولين
        authorized_users = User.objects.filter(
            Q(user_type__in=['admin', 'sales_rep']) | Q(is_superuser=True),
            is_active=True
        ).distinct()
        
        for user in authorized_users:
            NotificationService.create_notification(
                user=user,
                title=f"عميل جديد: {instance.name}",
                message=f"تم إضافة عميل جديد: {instance.name} - {instance.phone_primary or 'لا يوجد هاتف'}",
                notification_type="success",
                related_model="Customer",
                related_id=instance.id,
                link_url=f"/client/{instance.id}/detail/"
            )


# ==================== إشعارات الموردين ====================

@receiver(post_save, sender='supplier.Supplier')
def notify_new_supplier(sender, instance, created, **kwargs):
    """
    إنشاء إشعار عند إضافة مورد جديد
    """
    if created:
        # جلب المستخدمين المخولين
        authorized_users = User.objects.filter(
            Q(user_type__in=['admin', 'accountant']) | Q(is_superuser=True),
            is_active=True
        ).distinct()
        
        for user in authorized_users:
            NotificationService.create_notification(
                user=user,
                title=f"مورد جديد: {instance.name}",
                message=f"تم إضافة مورد جديد: {instance.name} - {instance.phone or 'لا يوجد هاتف'}",
                notification_type="success",
                related_model="Supplier",
                related_id=instance.id,
                link_url=f"/supplier/{instance.id}/detail/"
            )


# ==================== إشعارات المنتجات والمخزون ====================

@receiver(post_save, sender='product.Product')
def notify_new_product(sender, instance, created, **kwargs):
    """
    إنشاء إشعار عند إضافة منتج جديد
    """
    if created:
        # جلب المستخدمين المخولين
        authorized_users = User.objects.filter(
            Q(user_type__in=['admin', 'inventory_manager']) | Q(is_superuser=True),
            is_active=True
        ).distinct()
        
        for user in authorized_users:
            code = getattr(instance, 'code', None) or getattr(instance, 'sku', 'غير محدد')
            NotificationService.create_notification(
                user=user,
                title=f"منتج جديد: {instance.name}",
                message=f"تم إضافة منتج جديد: {instance.name} - الكود: {code}",
                notification_type="info",
                related_model="Product",
                related_id=instance.id,
                link_url=f"/products/{instance.id}/"
            )


# ==================== إشعارات المستخدمين ====================

@receiver(post_save, sender=User)
def notify_new_user(sender, instance, created, **kwargs):
    """
    إنشاء إشعار عند إضافة مستخدم جديد
    """
    if created:
        # إشعار للمدراء فقط
        admin_users = User.objects.filter(
            Q(is_superuser=True) | Q(user_type='admin'),
            is_active=True
        ).exclude(id=instance.id).distinct()
        
        for user in admin_users:
            NotificationService.create_notification(
                user=user,
                title=f"مستخدم جديد: {instance.get_full_name() or instance.username}",
                message=f"تم إضافة مستخدم جديد: {instance.get_full_name() or instance.username} - النوع: {instance.get_user_type_display()}",
                notification_type="info",
                link_url="/users/users/"
            )
        
        # إشعار ترحيبي للمستخدم الجديد
        NotificationService.create_notification(
            user=instance,
            title="مرحباً بك في موهبة ERP",
            message=f"مرحباً {instance.get_full_name() or instance.username}، تم إنشاء حسابك بنجاح. يمكنك الآن البدء في استخدام النظام.",
            notification_type="success",
            link_url="/"
        )
