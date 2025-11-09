"""
✅ Real-Time Permission Checker Middleware
التحقق من الصلاحيات من قاعدة البيانات في كل request مع Cache
"""
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


class RealTimePermissionMiddleware(MiddlewareMixin):
    """
    ✅ Middleware للتحقق من الصلاحيات من قاعدة البيانات
    
    الميزات:
    - التحقق من الصلاحيات في كل request
    - استخدام Cache لمدة دقيقة واحدة لتحسين الأداء
    - تحديث تلقائي عند تغيير الصلاحيات
    """
    
    def process_request(self, request):
        """معالجة الطلب والتحقق من الصلاحيات"""
        
        # فقط للمستخدمين المسجلين
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return None
        
        try:
            # استخدام Cache لتحسين الأداء
            cache_key = f'user_permissions_{request.user.id}'
            permissions = cache.get(cache_key)
            
            if permissions is None:
                # جلب الصلاحيات من قاعدة البيانات
                permissions = list(request.user.get_all_permissions())
                groups = list(request.user.groups.values_list('name', flat=True))
                
                # تخزين في Cache لمدة دقيقة واحدة
                cache_data = {
                    'permissions': permissions,
                    'groups': groups,
                    'is_staff': request.user.is_staff,
                    'is_superuser': request.user.is_superuser,
                }
                cache.set(cache_key, cache_data, 60)  # Cache لمدة دقيقة
                
                logger.debug(
                    f"Permissions loaded from DB for user {request.user.username}: "
                    f"{len(permissions)} permissions, {len(groups)} groups"
                )
            else:
                logger.debug(f"Permissions loaded from cache for user {request.user.username}")
            
            # إضافة الصلاحيات للـ request
            request.user_permissions = permissions if isinstance(permissions, list) else permissions.get('permissions', [])
            request.user_groups = permissions.get('groups', []) if isinstance(permissions, dict) else []
            
        except Exception as e:
            logger.error(f"Error in RealTimePermissionMiddleware: {str(e)}")
            # في حالة الخطأ، لا نمنع الـ request
            request.user_permissions = []
            request.user_groups = []
        
        return None


def clear_user_permissions_cache(user_id):
    """
    ✅ دالة مساعدة لحذف Cache الصلاحيات عند التحديث
    
    استخدام:
    from core.middleware.permission_checker import clear_user_permissions_cache
    clear_user_permissions_cache(user.id)
    """
    cache_key = f'user_permissions_{user_id}'
    cache.delete(cache_key)
    logger.info(f"Cleared permissions cache for user {user_id}")


def clear_all_permissions_cache():
    """
    ✅ حذف Cache جميع المستخدمين
    يُستخدم عند تحديث صلاحيات عامة
    """
    # ملاحظة: هذا يتطلب معرفة جميع user IDs
    # للتطبيق الكامل، يُنصح باستخدام Cache Pattern مختلف
    logger.info("Clearing all permissions cache (not implemented - use signals)")
