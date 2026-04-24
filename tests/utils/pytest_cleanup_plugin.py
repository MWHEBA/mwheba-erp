"""
إضافة pytest لتنظيف البيانات التلقائي
Pytest Plugin for Automatic Data Cleanup
"""
import pytest
import logging
from typing import Dict, Any
from .data_cleanup import cleanup_manager, TestDataContext

logger = logging.getLogger(__name__)


class CleanupPlugin:
    """إضافة pytest لإدارة تنظيف البيانات"""
    
    def __init__(self):
        self.cleanup_stats = {}
        self.test_data_contexts = {}
    
    @pytest.hookimpl(tryfirst=True)
    def pytest_configure(self, config):
        """تكوين الإضافة"""
        # تسجيل العلامات المخصصة
        config.addinivalue_line(
            "markers", 
            "cleanup_after: تنظيف البيانات بعد الاختبار"
        )
        config.addinivalue_line(
            "markers",
            "no_cleanup: عدم تنظيف البيانات بعد الاختبار"
        )
        config.addinivalue_line(
            "markers",
            "cleanup_before: تنظيف البيانات قبل الاختبار"
        )
        config.addinivalue_line(
            "markers",
            "preserve_data: الحفاظ على البيانات للاختبارات التالية"
        )
    
    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_setup(self, item):
        """إعداد قبل تشغيل كل اختبار"""
        
        # تنظيف قبل الاختبار إذا كان مطلوباً
        if item.get_closest_marker("cleanup_before"):
            logger.info(f"تنظيف البيانات قبل الاختبار: {item.name}")
            try:
                cleanup_manager.cleanup_all_test_data()
            except Exception as e:
                logger.error(f"فشل في تنظيف البيانات قبل {item.name}: {e}")
        
        # إنشاء سياق بيانات الاختبار
        auto_cleanup = not item.get_closest_marker("no_cleanup")
        create_backup = bool(item.get_closest_marker("preserve_data"))
        
        context = TestDataContext(
            auto_cleanup=False,  # سنتحكم في التنظيف يدوياً
            create_backup=create_backup
        )
        
        self.test_data_contexts[item.nodeid] = context
        context.__enter__()
    
    @pytest.hookimpl(trylast=True)
    def pytest_runtest_teardown(self, item, nextitem):
        """تنظيف بعد تشغيل كل اختبار"""
        
        context = self.test_data_contexts.get(item.nodeid)
        if context:
            try:
                # تنظيف البيانات إذا لم يكن ممنوعاً
                if not item.get_closest_marker("no_cleanup"):
                    if item.get_closest_marker("cleanup_after") or self._should_auto_cleanup(item):
                        logger.debug(f"تنظيف البيانات بعد الاختبار: {item.name}")
                        stats = cleanup_manager.cleanup_all_test_data()
                        self.cleanup_stats[item.nodeid] = stats
                
                # إنهاء السياق
                context.__exit__(None, None, None)
                
            except Exception as e:
                logger.error(f"فشل في تنظيف البيانات بعد {item.name}: {e}")
            finally:
                # إزالة السياق من الذاكرة
                self.test_data_contexts.pop(item.nodeid, None)
    
    def _should_auto_cleanup(self, item):
        """تحديد ما إذا كان يجب تنظيف البيانات تلقائياً"""
        
        # تنظيف تلقائي للاختبارات التي تستخدم قاعدة البيانات
        if hasattr(item, 'fixturenames') and 'db' in item.fixturenames:
            return True
        
        # تنظيف تلقائي للاختبارات التي تحتوي على كلمات مفتاحية معينة
        test_keywords = ['factory', 'create', 'client', 'customer', 'financial']
        test_name_lower = item.name.lower()
        
        return any(keyword in test_name_lower for keyword in test_keywords)
    
    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):
        """تنظيف نهائي بعد انتهاء جميع الاختبارات"""
        
        # تعطيل التنظيف النهائي مؤقتاً لتجنب مشاكل الوصول لقاعدة البيانات
        logger.info("تم تخطي التنظيف النهائي - الاختبارات تنظف البيانات تلقائياً")
        return
    
    def _print_final_report(self, final_stats, orphaned_stats, integrity_issues):
        """طباعة تقرير التنظيف النهائي"""
        
        print("\n" + "="*60)
        print("تقرير تنظيف بيانات الاختبار النهائي")
        print("="*60)
        
        print(f"إجمالي السجلات المحذوفة: {final_stats.get('total_deleted', 0)}")
        print(f"النماذج المعالجة: {final_stats.get('models_processed', 0)}")
        print(f"مدة التنظيف: {final_stats.get('duration', 0):.2f} ثانية")
        
        if orphaned_stats:
            print("\nالسجلات اليتيمة المحذوفة:")
            for key, value in orphaned_stats.items():
                print(f"  - {key}: {value}")
        
        if integrity_issues:
            print(f"\nمشاكل سلامة البيانات المتبقية: {len(integrity_issues)}")
            for issue in integrity_issues:
                print(f"  - {issue}")
        else:
            print("\n✅ جميع بيانات الاختبار سليمة")
        
        print("="*60)


# إنشاء مثيل من الإضافة
cleanup_plugin = CleanupPlugin()


# Fixtures مخصصة لإدارة البيانات

@pytest.fixture
def cleanup_after_test():
    """تنظيف البيانات بعد الاختبار"""
    yield
    cleanup_manager.cleanup_all_test_data()


@pytest.fixture
def no_cleanup():
    """منع تنظيف البيانات"""
    yield
    # لا نفعل شيئاً - البيانات ستبقى


@pytest.fixture
def test_data_context():
    """سياق إدارة بيانات الاختبار"""
    with TestDataContext(auto_cleanup=True, create_backup=False) as context:
        yield context


@pytest.fixture
def test_data_with_backup():
    """سياق إدارة بيانات الاختبار مع نسخة احتياطية"""
    with TestDataContext(auto_cleanup=True, create_backup=True) as context:
        yield context


@pytest.fixture
def data_stats():
    """إحصائيات بيانات الاختبار"""
    return cleanup_manager.get_data_statistics()


@pytest.fixture
def cleanup_manager_fixture():
    """مدير تنظيف البيانات"""
    return cleanup_manager


# دوال مساعدة للاختبارات

def mark_cleanup_after(test_func):
    """مُزخرف لتنظيف البيانات بعد الاختبار"""
    return pytest.mark.cleanup_after(test_func)


def mark_no_cleanup(test_func):
    """مُزخرف لمنع تنظيف البيانات"""
    return pytest.mark.no_cleanup(test_func)


def mark_cleanup_before(test_func):
    """مُزخرف لتنظيف البيانات قبل الاختبار"""
    return pytest.mark.cleanup_before(test_func)


def mark_preserve_data(test_func):
    """مُزخرف للحفاظ على البيانات"""
    return pytest.mark.preserve_data(test_func)


# تسجيل الإضافة مع pytest
def pytest_configure(config):
    """تسجيل الإضافة"""
    config.pluginmanager.register(cleanup_plugin, "cleanup_plugin")


def pytest_unconfigure(config):
    """إلغاء تسجيل الإضافة"""
    config.pluginmanager.unregister(cleanup_plugin, "cleanup_plugin")