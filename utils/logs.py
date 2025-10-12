import logging
import os
import json
import datetime
from django.conf import settings
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
from .models import SystemLog
from django.utils.translation import gettext_lazy as _

# إعداد السجلات
logger = logging.getLogger(__name__)


class SystemLogHandler:
    """
    معالج لتسجيل أحداث النظام
    """
    
    def __init__(self, log_file=None, log_level=logging.INFO):
        """
        تهيئة معالج السجلات
        
        المعلمات:
        log_file (str): مسار ملف السجل
        log_level (int): مستوى السجل
        """
        self.log_file = log_file or os.path.join(settings.BASE_DIR, 'logs', 'system.log')
        self.log_level = log_level
        
        # التأكد من وجود دليل السجلات
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        
        # إعداد معالج السجلات
        self.file_handler = logging.FileHandler(self.log_file)
        self.file_handler.setLevel(self.log_level)
        
        # تنسيق السجلات
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.file_handler.setFormatter(formatter)
        
        # إضافة المعالج إلى السجل
        logger.addHandler(self.file_handler)
    
    def log_action(self, action, user=None, model=None, object_id=None, details=None):
        """
        تسجيل إجراء في النظام
        
        المعلمات:
        action (str): الإجراء المنفذ
        user (User): المستخدم الذي نفذ الإجراء
        model (Model): نموذج البيانات الذي تم العمل عليه
        object_id (int): معرف الكائن
        details (dict): تفاصيل إضافية
        """
        log_entry = {
            'timestamp': timezone.now().isoformat(),
            'action': action,
            'user': user.username if user else 'system',
            'model': model.__name__ if model else None,
            'object_id': object_id,
            'details': details or {},
        }
        
        # تسجيل الإجراء كنص JSON
        logger.info(json.dumps(log_entry, cls=DjangoJSONEncoder))
        
        return log_entry


class SecurityLogHandler:
    """
    معالج لتسجيل أحداث الأمان
    """
    
    def __init__(self, log_file=None, log_level=logging.WARNING):
        """
        تهيئة معالج سجلات الأمان
        
        المعلمات:
        log_file (str): مسار ملف السجل
        log_level (int): مستوى السجل
        """
        self.log_file = log_file or os.path.join(settings.BASE_DIR, 'logs', 'security.log')
        self.log_level = log_level
        
        # التأكد من وجود دليل السجلات
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        
        # إعداد معالج السجلات
        self.file_handler = logging.FileHandler(self.log_file)
        self.file_handler.setLevel(self.log_level)
        
        # تنسيق السجلات
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        self.file_handler.setFormatter(formatter)
        
        # إنشاء سجل خاص
        self.security_logger = logging.getLogger('security')
        self.security_logger.setLevel(self.log_level)
        self.security_logger.addHandler(self.file_handler)
    
    def log_security_event(self, event_type, user=None, ip_address=None, details=None):
        """
        تسجيل حدث أمني
        
        المعلمات:
        event_type (str): نوع الحدث الأمني
        user (User): المستخدم المرتبط بالحدث
        ip_address (str): عنوان IP المصدر
        details (dict): تفاصيل إضافية
        """
        log_entry = {
            'timestamp': timezone.now().isoformat(),
            'event_type': event_type,
            'user': user.username if user else None,
            'ip_address': ip_address,
            'details': details or {},
        }
        
        # تسجيل الحدث الأمني
        self.security_logger.warning(json.dumps(log_entry, cls=DjangoJSONEncoder))
        
        return log_entry


class AuditLogHandler:
    """
    معالج لتسجيل سجلات التدقيق
    """
    
    def __init__(self, log_file=None, log_level=logging.INFO):
        """
        تهيئة معالج سجلات التدقيق
        
        المعلمات:
        log_file (str): مسار ملف السجل
        log_level (int): مستوى السجل
        """
        self.log_file = log_file or os.path.join(settings.BASE_DIR, 'logs', 'audit.log')
        self.log_level = log_level
        
        # التأكد من وجود دليل السجلات
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        
        # إعداد معالج السجلات
        self.file_handler = logging.FileHandler(self.log_file)
        self.file_handler.setLevel(self.log_level)
        
        # تنسيق السجلات
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        self.file_handler.setFormatter(formatter)
        
        # إنشاء سجل خاص
        self.audit_logger = logging.getLogger('audit')
        self.audit_logger.setLevel(self.log_level)
        self.audit_logger.addHandler(self.file_handler)
    
    def log_data_change(self, action, user, model, object_id, old_data=None, new_data=None):
        """
        تسجيل تغيير في البيانات
        
        المعلمات:
        action (str): الإجراء المنفذ (create, update, delete)
        user (User): المستخدم الذي نفذ الإجراء
        model (Model): نموذج البيانات الذي تم العمل عليه
        object_id (int): معرف الكائن
        old_data (dict): البيانات القديمة
        new_data (dict): البيانات الجديدة
        """
        log_entry = {
            'timestamp': timezone.now().isoformat(),
            'action': action,
            'user': user.username if user else 'system',
            'model': model.__name__ if model else None,
            'object_id': object_id,
            'old_data': old_data,
            'new_data': new_data,
        }
        
        # تسجيل تغيير البيانات
        self.audit_logger.info(json.dumps(log_entry, cls=DjangoJSONEncoder))
        
        return log_entry


def get_system_logs(start_date=None, end_date=None, action=None, user=None, limit=100):
    """
    استرجاع سجلات النظام
    
    المعلمات:
    start_date (datetime): تاريخ البداية
    end_date (datetime): تاريخ النهاية
    action (str): تصفية حسب الإجراء
    user (str): تصفية حسب المستخدم
    limit (int): الحد الأقصى للنتائج
    
    تُرجع: قائمة بسجلات النظام
    """
    if not start_date:
        start_date = timezone.now() - datetime.timedelta(days=30)
    
    if not end_date:
        end_date = timezone.now()
    
    log_file = os.path.join(settings.BASE_DIR, 'logs', 'system.log')
    
    if not os.path.exists(log_file):
        return []
    
    logs = []
    try:
        with open(log_file, 'r') as f:
            for line in f:
                try:
                    # استخراج التاريخ والرسالة من سطر السجل
                    parts = line.split(' - ', 3)
                    if len(parts) < 4:
                        continue
                    
                    timestamp_str, logger_name, level, message = parts
                    
                    # تحويل نص التاريخ إلى كائن datetime
                    timestamp = datetime.datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                    if timezone.is_naive(timestamp):
                        timestamp = timezone.make_aware(timestamp)
                    
                    # التحقق من نطاق التاريخ
                    if not (start_date <= timestamp <= end_date):
                        continue
                    
                    # محاولة تحليل رسالة JSON
                    try:
                        log_data = json.loads(message)
                        
                        # تطبيق المرشحات
                        if action and log_data.get('action') != action:
                            continue
                        
                        if user and log_data.get('user') != user:
                            continue
                        
                        logs.append(log_data)
                        
                        # التحقق من الحد
                        if len(logs) >= limit:
                            break
                    except:
                        # تخطي السطور التي لا يمكن تحليلها كـ JSON
                        continue
                
                except Exception as e:
                    # تخطي الأسطر التي لا يمكن معالجتها
                    continue
    except Exception as e:
        logger.error(f"خطأ في قراءة ملف السجل: {str(e)}")
    
    return logs


def get_security_logs(start_date=None, end_date=None, event_type=None, user=None, limit=100):
    """
    استرجاع سجلات الأمان
    
    المعلمات متشابهة مع get_system_logs
    """
    if not start_date:
        start_date = timezone.now() - datetime.timedelta(days=30)
    
    if not end_date:
        end_date = timezone.now()
    
    log_file = os.path.join(settings.BASE_DIR, 'logs', 'security.log')
    
    if not os.path.exists(log_file):
        return []
    
    logs = []
    try:
        with open(log_file, 'r') as f:
            for line in f:
                try:
                    # تحليل سطر السجل
                    parts = line.split(' - ', 2)
                    if len(parts) < 3:
                        continue
                    
                    timestamp_str, level, message = parts
                    
                    # تحويل نص التاريخ إلى كائن datetime
                    timestamp = datetime.datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                    if timezone.is_naive(timestamp):
                        timestamp = timezone.make_aware(timestamp)
                    
                    # التحقق من نطاق التاريخ
                    if not (start_date <= timestamp <= end_date):
                        continue
                    
                    # محاولة تحليل رسالة JSON
                    try:
                        log_data = json.loads(message)
                        
                        # تطبيق المرشحات
                        if event_type and log_data.get('event_type') != event_type:
                            continue
                        
                        if user and log_data.get('user') != user:
                            continue
                        
                        logs.append(log_data)
                        
                        # التحقق من الحد
                        if len(logs) >= limit:
                            break
                    except:
                        # تخطي السطور التي لا يمكن تحليلها كـ JSON
                        continue
                
                except Exception as e:
                    # تخطي الأسطر التي لا يمكن معالجتها
                    continue
    except Exception as e:
        logger.error(f"خطأ في قراءة ملف السجل: {str(e)}")
    
    return logs


def get_audit_logs(start_date=None, end_date=None, action=None, user=None, model=None, limit=100):
    """
    استرجاع سجلات التدقيق
    
    المعلمات:
    نفس المعلمات السابقة بالإضافة إلى:
    model (str): تصفية حسب النموذج
    """
    if not start_date:
        start_date = timezone.now() - datetime.timedelta(days=30)
    
    if not end_date:
        end_date = timezone.now()
    
    log_file = os.path.join(settings.BASE_DIR, 'logs', 'audit.log')
    
    if not os.path.exists(log_file):
        return []
    
    logs = []
    try:
        with open(log_file, 'r') as f:
            for line in f:
                try:
                    # تحليل سطر السجل
                    parts = line.split(' - ', 2)
                    if len(parts) < 3:
                        continue
                    
                    timestamp_str, level, message = parts
                    
                    # تحويل نص التاريخ إلى كائن datetime
                    timestamp = datetime.datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                    if timezone.is_naive(timestamp):
                        timestamp = timezone.make_aware(timestamp)
                    
                    # التحقق من نطاق التاريخ
                    if not (start_date <= timestamp <= end_date):
                        continue
                    
                    # محاولة تحليل رسالة JSON
                    try:
                        log_data = json.loads(message)
                        
                        # تطبيق المرشحات
                        if action and log_data.get('action') != action:
                            continue
                        
                        if user and log_data.get('user') != user:
                            continue
                        
                        if model and log_data.get('model') != model:
                            continue
                        
                        logs.append(log_data)
                        
                        # التحقق من الحد
                        if len(logs) >= limit:
                            break
                    except:
                        # تخطي السطور التي لا يمكن تحليلها كـ JSON
                        continue
                
                except Exception as e:
                    # تخطي الأسطر التي لا يمكن معالجتها
                    continue
    except Exception as e:
        logger.error(f"خطأ في قراءة ملف السجل: {str(e)}")
    
    return logs


def create_log(user=None, action=None, model_name=None, object_id=None, details=None, ip_address=None):
    """
    وظيفة لإنشاء سجل جديد للنظام لتتبع إجراءات المستخدمين
    
    المعاملات:
    - user: كائن المستخدم الحالي أو request يحتوي على user
    - action: الإجراء الذي تم تنفيذه (إنشاء، تعديل، حذف، إلخ)
    - model_name: اسم النموذج الذي تم العمل عليه (اختياري)
    - object_id: معرف الكائن الذي تم العمل عليه (اختياري)
    - details: تفاصيل إضافية عن الإجراء (اختياري)
    - ip_address: عنوان IP للمستخدم (اختياري، يتم استخدامه فقط إذا تم تمرير user مباشرة)
    """
    try:
        # التعامل مع حالة تمرير كائن request
        if hasattr(user, 'user'):
            request = user
            ip_address = get_client_ip(request)
            user = request.user
        
        # إذا كانت التفاصيل كائنًا معقدًا، قم بتحويلها إلى سلسلة نصية
        if details and not isinstance(details, str):
            try:
                details = json.dumps(details, ensure_ascii=False, default=str)
            except:
                details = str(details)
        
        # إنشاء السجل فقط إذا كان المستخدم موجودًا
        if user and hasattr(user, 'is_authenticated') and user.is_authenticated:
            SystemLog.objects.create(
                user=user,
                action=action,
                model_name=model_name,
                object_id=object_id,
                details=details,
                ip_address=ip_address
            )
        
        return True
    except Exception as e:
        # تسجيل الخطأ في السجل الخاص بالنظام
        print(f"Error creating log: {str(e)}")
        return False

def get_client_ip(request):
    """
    الحصول على عنوان IP للعميل من الطلب HTTP
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

# ثوابت لأنواع الإجراءات الشائعة
ACTION_CREATE = _("إنشاء")
ACTION_UPDATE = _("تعديل")
ACTION_DELETE = _("حذف")
ACTION_VIEW = _("عرض")
ACTION_LOGIN = _("تسجيل دخول")
ACTION_LOGOUT = _("تسجيل خروج")
ACTION_EXPORT = _("تصدير")
ACTION_IMPORT = _("استيراد")
ACTION_BACKUP = _("نسخ احتياطي")
ACTION_RESTORE = _("استعادة")
ACTION_APPROVE = _("موافقة")
ACTION_REJECT = _("رفض")
ACTION_CANCEL = _("إلغاء")
ACTION_PRINT = _("طباعة")
ACTION_STOCK_ADJUST = _("تعديل المخزون")

def get_logs(user_id=None, model_name=None, action=None, date_from=None, date_to=None, limit=100):
    """
    استرجاع سجلات النشاطات من قاعدة البيانات مع تطبيق مرشحات
    
    المعلمات:
    user_id (int): تصفية حسب المستخدم
    model_name (str): تصفية حسب النموذج
    action (str): تصفية حسب الإجراء
    date_from (str): تاريخ البداية (بصيغة YYYY-MM-DD)
    date_to (str): تاريخ النهاية (بصيغة YYYY-MM-DD)
    limit (int): الحد الأقصى للنتائج
    
    تُرجع: قائمة بسجلات النشاطات (لن تكون None أبدًا)
    """
    try:
        # بناء الاستعلام
        query = SystemLog.objects.all()
        
        # تطبيق المرشحات
        if user_id:
            query = query.filter(user_id=user_id)
        
        if model_name:
            query = query.filter(model_name=model_name)
        
        if action:
            query = query.filter(action=action)
        
        # تطبيق مرشحات التاريخ
        if date_from:
            try:
                from_date = datetime.datetime.strptime(date_from, '%Y-%m-%d').date()
                query = query.filter(timestamp__date__gte=from_date)
            except (ValueError, TypeError):
                pass
        
        if date_to:
            try:
                to_date = datetime.datetime.strptime(date_to, '%Y-%m-%d').date()
                query = query.filter(timestamp__date__lte=to_date)
            except (ValueError, TypeError):
                pass
        
        # ترتيب حسب التاريخ (الأحدث أولاً) وتطبيق الحد
        result = list(query.order_by('-timestamp')[:limit])
        return result
    except Exception as e:
        # تسجيل الخطأ وإعادة قائمة فارغة
        print(f"خطأ في الحصول على سجلات النظام: {str(e)}")
        return [] 