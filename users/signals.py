from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from users.models import ActivityLog
from core.middleware.current_user import get_current_user, get_current_request
from utils.logs import get_client_ip
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

# List of models to monitor for audit logging (in string format to avoid early/circular imports)
MONITORED_MODELS = [
    'client.Customer',
    'supplier.Supplier',
    'product.Product',
    'sale.Sale',
    'purchase.Purchase',
    'users.User',
    'users.Role',
]

def log_model_change(sender, instance, created=None, deleted=False, **kwargs):
    """
    Common handler for model save and delete events to create ActivityLog entries.
    """
    user = get_current_user()
    if not user or not user.is_authenticated:
        return

    request = get_current_request()
    ip_address = get_client_ip(request) if request else None
    user_agent = request.META.get('HTTP_USER_AGENT', '') if request else None

    model_name = sender.__name__
    
    # Arabic translations for display
    model_translations = {
        'Customer': 'عميل',
        'Supplier': 'مورد',
        'Product': 'منتج',
        'Sale': 'فاتورة بيع',
        'Purchase': 'فاتورة شراء',
        'User': 'مستخدم',
        'Role': 'دور/صلاحية',
    }
    
    model_display = model_translations.get(model_name, model_name)
    
    if deleted:
        action_type = 'حذف'
        action_verb = 'حذف'
    elif created:
        action_type = 'إنشاء'
        action_verb = 'إنشاء'
    else:
        action_type = 'تعديل'
        action_verb = 'تعديل'
        
    action_desc = f"{action_type} {model_display}"
    
    # Try to extract a friendly representation/name of the instance
    instance_name = ""
    if hasattr(instance, 'get_full_name') and instance.get_full_name():
        instance_name = instance.get_full_name()
    elif hasattr(instance, 'name') and instance.name:
        instance_name = instance.name
    elif hasattr(instance, 'username') and instance.username:
        instance_name = instance.username
    elif hasattr(instance, 'invoice_number') and instance.invoice_number:
        instance_name = instance.invoice_number
    elif hasattr(instance, 'id'):
        instance_name = f"#{instance.id}"
        
    description = f"تم {action_verb} {model_display}: {instance_name}"
    
    try:
        ActivityLog.objects.create(
            user=user,
            action=action_desc,
            model_name=model_name,
            object_id=instance.id if hasattr(instance, 'id') else None,
            ip_address=ip_address,
            user_agent=user_agent,
            extra_data={
                'description': description,
                'instance_repr': str(instance),
            }
        )
    except Exception as e:
        logger.error(f"Error creating ActivityLog in signals: {e}", exc_info=True)


def save_callback(sender, instance, created, **kwargs):
    log_model_change(sender, instance, created=created, deleted=False, **kwargs)


def delete_callback(sender, instance, **kwargs):
    log_model_change(sender, instance, created=None, deleted=True, **kwargs)


def connect_signals():
    """
    Dynamically resolve and connect signals for monitored models.
    """
    from django.apps import apps
    for model_str in MONITORED_MODELS:
        try:
            model = apps.get_model(model_str)
            post_save.connect(save_callback, sender=model, dispatch_uid=f"activity_log_save_{model_str}")
            post_delete.connect(delete_callback, sender=model, dispatch_uid=f"activity_log_delete_{model_str}")
        except Exception as e:
            logger.error(f"Error connecting signals for {model_str}: {e}")


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    if not user or not user.is_authenticated:
        return
    
    ip_address = get_client_ip(request) if request else None
    user_agent = request.META.get('HTTP_USER_AGENT', '') if request else None
    
    try:
        ActivityLog.objects.create(
            user=user,
            action="تسجيل دخول",
            model_name="User",
            object_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            extra_data={
                'description': f"تم تسجيل دخول المستخدم {user.get_full_name() or user.username} بنجاح",
            }
        )
    except Exception as e:
        logger.error(f"Error logging user login: {e}", exc_info=True)


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    if not user or not user.is_authenticated:
        return
        
    ip_address = get_client_ip(request) if request else None
    user_agent = request.META.get('HTTP_USER_AGENT', '') if request else None
    
    try:
        ActivityLog.objects.create(
            user=user,
            action="تسجيل خروج",
            model_name="User",
            object_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            extra_data={
                'description': f"تم تسجيل خروج المستخدم {user.get_full_name() or user.username} بنجاح",
            }
        )
    except Exception as e:
        logger.error(f"Error logging user logout: {e}", exc_info=True)


@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request, **kwargs):
    username = credentials.get('username')
    if not username:
        return
        
    ip_address = get_client_ip(request) if request else None
    user_agent = request.META.get('HTTP_USER_AGENT', '') if request else None
    
    try:
        user = User.objects.get(username=username)
        ActivityLog.objects.create(
            user=user,
            action="فشل تسجيل دخول",
            model_name="User",
            object_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            extra_data={
                'description': f"محاولة تسجيل دخول فاشلة للمستخدم {user.get_full_name() or user.username}",
            }
        )
    except User.DoesNotExist:
        # Since 'user' field in ActivityLog is not nullable, we cannot log failed attempts of non-existent usernames.
        pass
    except Exception as e:
        logger.error(f"Error logging failed login: {e}", exc_info=True)
