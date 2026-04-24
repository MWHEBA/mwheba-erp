"""
نظام التنظيف التلقائي للبيانات المتقدم
Advanced Automatic Data Cleanup System
"""
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from django.db import transaction, connection
from django.apps import apps
from django.core.management.color import make_style
from django.conf import settings
import threading
from contextlib import contextmanager

# إعداد السجلات
logger = logging.getLogger(__name__)
style = make_style()


class DatabaseCleanupError(Exception):
    """خطأ في تنظيف قاعدة البيانات"""
    pass


class TestDataCleanupManager:
    """مدير تنظيف بيانات الاختبار المتقدم مع إدارة العلاقات والقيود"""
    
    def __init__(self):
        # ترتيب التنظيف حسب العلاقات (من التابع إلى الأساسي)
        self.cleanup_order = [
            # المعاملات والسجلات التابعة
            'financial.Transaction',
            'financial.JournalEntry',
            'financial.Payment',
            
            # سجلات المبيعات
            'sale.SalePayment',
            'sale.SaleItem',
            'sale.Sale',
            'sale.SaleReturn',
            'sale.SaleReturnItem',
            
            # سجلات المشتريات
            'purchase.PurchaseItem',
            'purchase.Purchase',
            'purchase.PurchaseReturn',
            
            # العملاء والموردين
            'client.Customer',
            'client.CustomerPayment',
            'supplier.Supplier',
            
            # الموظفين والموارد البشرية
            'hr.Employee',
            'hr.Department',
            'hr.JobTitle',
            'hr.Attendance',
            
            # المنتجات والمخزون
            'product.Product',
            'product.ProductBundle',
            'product.Category',
            'product.StockMovement',
            
            # المستخدمين (آخر شيء)
            'users.User'
        ]
        
        self.logger = logging.getLogger(__name__)
        self._cleanup_stats = {}
        self._start_time = None
        self._lock = threading.Lock()
    
    @contextmanager
    def cleanup_session(self, description="تنظيف بيانات الاختبار"):
        """جلسة تنظيف مع إدارة الأخطاء والإحصائيات"""
        self._start_time = time.time()
        self._cleanup_stats = {}
        
        self.logger.info(style.SUCCESS(f"بدء {description}..."))
        
        try:
            with transaction.atomic():
                yield self
                
        except Exception as e:
            self.logger.error(style.ERROR(f"خطأ في {description}: {e}"))
            raise DatabaseCleanupError(f"فشل في {description}: {e}")
            
        finally:
            duration = time.time() - self._start_time
            self.logger.info(style.SUCCESS(
                f"انتهى {description} في {duration:.2f} ثانية"
            ))
    
    def cleanup_all_test_data(self, force=False):
        """تنظيف جميع بيانات الاختبار مع التحقق من الأمان"""
        
        if not force and not self._is_test_environment():
            raise DatabaseCleanupError(
                "رفض تنظيف البيانات: لا يبدو أن هذه بيئة اختبار. "
                "استخدم force=True للتجاوز (خطر!)"
            )
        
        with self.cleanup_session("تنظيف جميع بيانات الاختبار"):
            total_deleted = 0
            
            # تعطيل فحص القيود الخارجية مؤقتاً
            with self._disable_foreign_key_checks():
                
                for model_name in self.cleanup_order:
                    try:
                        deleted_count = self._cleanup_model(model_name)
                        self._cleanup_stats[model_name] = deleted_count
                        total_deleted += deleted_count
                        
                        if deleted_count > 0:
                            self.logger.debug(
                                style.WARNING(f"تم حذف {deleted_count} سجل من {model_name}")
                            )
                            
                    except Exception as e:
                        self.logger.error(style.ERROR(f"خطأ في تنظيف {model_name}: {e}"))
                        self._cleanup_stats[model_name] = f"خطأ: {e}"
            
            # إعادة تعيين تسلسل المفاتيح الأساسية
            self._reset_sequences()
            
            self.logger.info(style.SUCCESS(
                f"تم تنظيف {total_deleted} سجل من {len(self.cleanup_order)} نموذج"
            ))
            
            return {
                'total_deleted': total_deleted,
                'models_processed': len(self.cleanup_order),
                'cleanup_stats': self._cleanup_stats.copy(),
                'duration': time.time() - self._start_time
            }
    
    def _cleanup_model(self, model_name):
        """تنظيف نموذج محدد مع معالجة الأخطاء"""
        try:
            app_label, model_name_only = model_name.split('.')
            model = apps.get_model(app_label, model_name_only)
            
            # عد السجلات قبل الحذف
            count_before = model.objects.count()
            
            if count_before > 0:
                # حذف جميع السجلات
                deleted_info = model.objects.all().delete()
                actual_deleted = deleted_info[0] if deleted_info else count_before
                
                self.logger.debug(f"تم حذف {actual_deleted} سجل من {model_name}")
                return actual_deleted
            else:
                self.logger.debug(f"لا توجد سجلات في {model_name}")
                return 0
                
        except LookupError:
            self.logger.warning(f"النموذج {model_name} غير موجود")
            return 0
        except Exception as e:
            self.logger.error(f"خطأ في تنظيف {model_name}: {e}")
            raise
    
    @contextmanager
    def _disable_foreign_key_checks(self):
        """تعطيل فحص القيود الخارجية مؤقتاً"""
        if connection.vendor == 'sqlite':
            # SQLite
            with connection.cursor() as cursor:
                cursor.execute('PRAGMA foreign_keys = OFF')
                try:
                    yield
                finally:
                    cursor.execute('PRAGMA foreign_keys = ON')
        
        elif connection.vendor == 'mysql':
            # MySQL
            with connection.cursor() as cursor:
                cursor.execute('SET FOREIGN_KEY_CHECKS = 0')
                try:
                    yield
                finally:
                    cursor.execute('SET FOREIGN_KEY_CHECKS = 1')
        
        elif connection.vendor == 'postgresql':
            # PostgreSQL - لا يدعم تعطيل القيود بشكل عام
            yield
        
        else:
            # قواعد بيانات أخرى
            yield
    
    def _reset_sequences(self):
        """إعادة تعيين تسلسل المفاتيح الأساسية"""
        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                # PostgreSQL
                cursor.execute("""
                    SELECT setval(pg_get_serial_sequence(quote_ident(schemaname)||'.'||quote_ident(tablename), 'id'), 1, false)
                    FROM pg_tables 
                    WHERE schemaname = 'public'
                """)
        
        elif connection.vendor == 'sqlite':
            with connection.cursor() as cursor:
                # SQLite
                cursor.execute("DELETE FROM sqlite_sequence")
    
    def cleanup_specific_models(self, model_names: List[str]):
        """تنظيف نماذج محددة فقط مع احترام ترتيب العلاقات"""
        
        # ترتيب النماذج المطلوبة حسب ترتيب التنظيف
        ordered_models = [
            model for model in self.cleanup_order 
            if model in model_names
        ]
        
        with self.cleanup_session(f"تنظيف النماذج المحددة: {ordered_models}"):
            total_deleted = 0
            
            with self._disable_foreign_key_checks():
                for model_name in ordered_models:
                    try:
                        deleted_count = self._cleanup_model(model_name)
                        self._cleanup_stats[model_name] = deleted_count
                        total_deleted += deleted_count
                    except Exception as e:
                        self._cleanup_stats[model_name] = f"خطأ: {e}"
            
            return {
                'total_deleted': total_deleted,
                'models_processed': len(ordered_models),
                'cleanup_stats': self._cleanup_stats.copy()
            }
    
    def cleanup_by_date_range(self, start_date, end_date, models=None):
        """تنظيف البيانات في نطاق تاريخي محدد"""
        
        if models is None:
            models = [
                'financial.Transaction',
                'sale.Sale',
                'purchase.Purchase',
                'hr.Attendance'
            ]
        
        with self.cleanup_session(f"تنظيف البيانات من {start_date} إلى {end_date}"):
            total_deleted = 0
            
            for model_name in models:
                try:
                    app_label, model_name_only = model_name.split('.')
                    model = apps.get_model(app_label, model_name_only)
                    
                    # البحث عن حقول التاريخ المناسبة
                    date_fields = self._get_date_fields(model)
                    
                    if date_fields:
                        date_field = date_fields[0]  # استخدام أول حقل تاريخ
                        
                        deleted_info = model.objects.filter(
                            **{f"{date_field}__range": [start_date, end_date]}
                        ).delete()
                        
                        deleted_count = deleted_info[0] if deleted_info else 0
                        self._cleanup_stats[model_name] = deleted_count
                        total_deleted += deleted_count
                        
                        if deleted_count > 0:
                            self.logger.info(
                                f"تم حذف {deleted_count} سجل من {model_name} "
                                f"في النطاق التاريخي {start_date} - {end_date}"
                            )
                    else:
                        self.logger.warning(f"لا توجد حقول تاريخ في {model_name}")
                        self._cleanup_stats[model_name] = "لا توجد حقول تاريخ"
                
                except Exception as e:
                    self.logger.error(f"خطأ في تنظيف {model_name}: {e}")
                    self._cleanup_stats[model_name] = f"خطأ: {e}"
            
            return {
                'total_deleted': total_deleted,
                'date_range': f"{start_date} - {end_date}",
                'cleanup_stats': self._cleanup_stats.copy()
            }
    
    def _get_date_fields(self, model):
        """الحصول على حقول التاريخ في النموذج"""
        date_fields = []
        
        for field in model._meta.get_fields():
            if hasattr(field, 'get_internal_type'):
                field_type = field.get_internal_type()
                if field_type in ['DateTimeField', 'DateField']:
                    date_fields.append(field.name)
        
        # ترتيب حسب الأولوية
        priority_fields = ['created_at', 'date', 'updated_at', 'date_joined']
        
        sorted_fields = []
        for priority_field in priority_fields:
            if priority_field in date_fields:
                sorted_fields.append(priority_field)
        
        # إضافة باقي الحقول
        for field in date_fields:
            if field not in sorted_fields:
                sorted_fields.append(field)
        
        return sorted_fields
    
    def cleanup_orphaned_records(self):
        """تنظيف السجلات اليتيمة (بدون علاقات صحيحة)"""
        
        with self.cleanup_session("تنظيف السجلات اليتيمة"):
            orphaned_stats = {}
            
            # البحث عن المبيعات بدون عملاء
            try:
                from sale.models import Sale
                orphaned_sales = Sale.objects.filter(customer__isnull=True)
                count = orphaned_sales.count()
                if count > 0:
                    orphaned_sales.delete()
                    orphaned_stats['sales_without_customers'] = count
                    self.logger.info(f"تم حذف {count} عملية بيع بدون عميل")
            except Exception as e:
                orphaned_stats['sales_without_customers'] = f"خطأ: {e}"
            
            # البحث عن المعاملات المالية بدون مرجع
            try:
                from financial.models import Transaction
                orphaned_transactions = Transaction.objects.filter(
                    reference_id__isnull=True,
                    transaction_type='income'
                )
                count = orphaned_transactions.count()
                if count > 0:
                    orphaned_transactions.delete()
                    orphaned_stats['income_without_reference'] = count
                    self.logger.info(f"تم حذف {count} معاملة دخل بدون مرجع")
            except Exception as e:
                orphaned_stats['income_without_reference'] = f"خطأ: {e}"
            
            # البحث عن المنتجات بدون فئة
            try:
                from product.models import Product
                orphaned_products = Product.objects.filter(category__isnull=True)
                count = orphaned_products.count()
                if count > 0:
                    orphaned_products.delete()
                    orphaned_stats['products_without_category'] = count
                    self.logger.info(f"تم حذف {count} منتج بدون فئة")
            except Exception as e:
                orphaned_stats['products_without_category'] = f"خطأ: {e}"
            
            return orphaned_stats
    
    def get_data_statistics(self):
        """الحصول على إحصائيات البيانات الحالية"""
        stats = {}
        total_records = 0
        
        for model_name in self.cleanup_order:
            try:
                app_label, model_name_only = model_name.split('.')
                model = apps.get_model(app_label, model_name_only)
                count = model.objects.count()
                stats[model_name] = count
                total_records += count
            except LookupError:
                stats[model_name] = "نموذج غير موجود"
            except Exception as e:
                stats[model_name] = f"خطأ: {e}"
        
        stats['_total_records'] = total_records
        stats['_timestamp'] = datetime.now().isoformat()
        
        return stats
    
    def validate_data_integrity(self):
        """التحقق من سلامة البيانات"""
        issues = []
        
        try:
            # التحقق من المبيعات بدون عملاء
            from sale.models import Sale
            sales_without_customers = Sale.objects.filter(customer__isnull=True).count()
            if sales_without_customers > 0:
                issues.append(f"يوجد {sales_without_customers} عملية بيع بدون عميل")
            
            # التحقق من المنتجات بدون فئة
            from product.models import Product
            products_without_category = Product.objects.filter(category__isnull=True).count()
            if products_without_category > 0:
                issues.append(f"يوجد {products_without_category} منتج بدون فئة")
            
            # التحقق من الموظفين بدون قسم
            from hr.models import Employee
            employees_without_department = Employee.objects.filter(department__isnull=True).count()
            if employees_without_department > 0:
                issues.append(f"يوجد {employees_without_department} موظف بدون قسم")
            
            # التحقق من المعاملات المالية بدون مرجع
            from financial.models import Transaction
            transactions_without_reference = Transaction.objects.filter(
                reference_id__isnull=True,
                transaction_type='income'
            ).count()
            if transactions_without_reference > 0:
                issues.append(f"يوجد {transactions_without_reference} معاملة دخل بدون مرجع")
        
        except Exception as e:
            issues.append(f"خطأ في التحقق من البيانات: {e}")
        
        if issues:
            self.logger.warning(style.WARNING(f"تم العثور على {len(issues)} مشكلة في البيانات:"))
            for issue in issues:
                self.logger.warning(style.WARNING(f"  - {issue}"))
        else:
            self.logger.info(style.SUCCESS("جميع بيانات الاختبار سليمة"))
        
        return issues
    
    def _is_test_environment(self):
        """التحقق من أن البيئة الحالية هي بيئة اختبار"""
        test_indicators = [
            # متغيرات البيئة
            getattr(settings, 'TESTING', False),
            'test' in getattr(settings, 'DATABASES', {}).get('default', {}).get('NAME', ''),
            ':memory:' in getattr(settings, 'DATABASES', {}).get('default', {}).get('NAME', ''),
            
            # إعدادات Django
            getattr(settings, 'DEBUG', False),
            'test' in str(settings.BASE_DIR).lower(),
        ]
        
        return any(test_indicators)
    
    def create_backup_before_cleanup(self):
        """إنشاء نسخة احتياطية قبل التنظيف"""
        if connection.vendor == 'sqlite':
            import shutil
            from django.conf import settings
            
            db_path = settings.DATABASES['default']['NAME']
            if db_path != ':memory:':
                backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(db_path, backup_path)
                self.logger.info(f"تم إنشاء نسخة احتياطية: {backup_path}")
                return backup_path
        
        self.logger.warning("لا يمكن إنشاء نسخة احتياطية لهذا النوع من قواعد البيانات")
        return None


# إنشاء مثيل عام من مدير التنظيف
cleanup_manager = TestDataCleanupManager()


# دوال مساعدة سريعة
def cleanup_test_data(force=False):
    """دالة سريعة لتنظيف بيانات الاختبار"""
    return cleanup_manager.cleanup_all_test_data(force=force)


def cleanup_specific_test_data(model_names):
    """دالة سريعة لتنظيف نماذج محددة"""
    return cleanup_manager.cleanup_specific_models(model_names)


def cleanup_by_date(start_date, end_date, models=None):
    """دالة سريعة لتنظيف البيانات بالتاريخ"""
    return cleanup_manager.cleanup_by_date_range(start_date, end_date, models)


def cleanup_orphaned_data():
    """دالة سريعة لتنظيف البيانات اليتيمة"""
    return cleanup_manager.cleanup_orphaned_records()


def get_test_data_stats():
    """دالة سريعة للحصول على إحصائيات البيانات"""
    return cleanup_manager.get_data_statistics()


def validate_test_data_integrity():
    """دالة سريعة للتحقق من سلامة البيانات"""
    return cleanup_manager.validate_data_integrity()


def safe_cleanup_with_backup():
    """تنظيف آمن مع إنشاء نسخة احتياطية"""
    backup_path = cleanup_manager.create_backup_before_cleanup()
    try:
        result = cleanup_manager.cleanup_all_test_data()
        result['backup_path'] = backup_path
        return result
    except Exception as e:
        logger.error(f"فشل التنظيف، النسخة الاحتياطية متوفرة في: {backup_path}")
        raise


# فئة مساعدة للاستخدام كـ Context Manager
class TestDataContext:
    """مدير سياق لإدارة بيانات الاختبار تلقائياً"""
    
    def __init__(self, auto_cleanup=True, create_backup=False):
        self.auto_cleanup = auto_cleanup
        self.create_backup = create_backup
        self.backup_path = None
        self.initial_stats = None
    
    def __enter__(self):
        if self.create_backup:
            self.backup_path = cleanup_manager.create_backup_before_cleanup()
        
        self.initial_stats = cleanup_manager.get_data_statistics()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.auto_cleanup:
            try:
                cleanup_manager.cleanup_all_test_data()
                logger.info("تم تنظيف بيانات الاختبار تلقائياً")
            except Exception as e:
                logger.error(f"فشل في التنظيف التلقائي: {e}")
        
        if exc_type is not None:
            logger.error(f"حدث خطأ في سياق الاختبار: {exc_val}")
    
    def get_stats_comparison(self):
        """مقارنة الإحصائيات قبل وبعد"""
        current_stats = cleanup_manager.get_data_statistics()
        
        comparison = {}
        for model_name in self.initial_stats:
            if model_name.startswith('_'):
                continue
                
            initial = self.initial_stats.get(model_name, 0)
            current = current_stats.get(model_name, 0)
            
            if isinstance(initial, int) and isinstance(current, int):
                comparison[model_name] = {
                    'initial': initial,
                    'current': current,
                    'difference': current - initial
                }
        
        return comparison


# دالة مساعدة للاستخدام السهل
def with_test_data(auto_cleanup=True, create_backup=False):
    """مُزخرف لإدارة بيانات الاختبار تلقائياً"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with TestDataContext(auto_cleanup, create_backup):
                return func(*args, **kwargs)
        return wrapper
    return decorator