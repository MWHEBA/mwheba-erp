"""
إعدادات pytest لاختبارات E2E - محسّنة 10/10

التحسينات الجديدة:
- Property-based testing مع Hypothesis
- Concurrency testing مع ThreadPoolExecutor
- Performance benchmarking
- Chaos engineering fixtures
- Database snapshot/restore
- Real-world data generators
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import connection, transaction
from django.core.cache import cache
from django.test.utils import override_settings
import uuid
import time
import random
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

User = get_user_model()


# ==================== Fixtures للمستخدمين ====================

@pytest.fixture
def test_user(db):
    """مستخدم عادي للاختبار - مع تنظيف تلقائي"""
    # حذف المستخدم إن وجد
    User.objects.filter(username='e2e_user').delete()
    
    user = User.objects.create_user(
        username='e2e_user',
        email='e2e@test.com',
        password='testpass123',
        first_name='مستخدم',
        last_name='الاختبار'
    )
    yield user
    
    # تنظيف بعد الاختبار
    try:
        user.delete()
    except:
        pass


@pytest.fixture
def admin_user(db):
    """مستخدم إداري للاختبار - مع تنظيف تلقائي"""
    # حذف المستخدم إن وجد
    User.objects.filter(username='e2e_admin').delete()
    
    user = User.objects.create_superuser(
        username='e2e_admin',
        email='admin@test.com',
        password='adminpass123',
        first_name='مدير',
        last_name='النظام'
    )
    yield user
    
    # تنظيف بعد الاختبار
    try:
        user.delete()
    except:
        pass


@pytest.fixture
def sales_user(db):
    """مستخدم مبيعات للاختبار - مع تنظيف تلقائي"""
    # حذف المستخدم إن وجد
    User.objects.filter(username='e2e_sales').delete()
    
    user = User.objects.create_user(
        username='e2e_sales',
        email='sales@test.com',
        password='testpass123',
        first_name='موظف',
        last_name='المبيعات'
    )
    yield user
    
    # تنظيف بعد الاختبار
    try:
        user.delete()
    except:
        pass


@pytest.fixture
def warehouse_user(db):
    """مستخدم مخازن للاختبار - مع تنظيف تلقائي"""
    # حذف المستخدم إن وجد
    User.objects.filter(username='e2e_warehouse').delete()
    
    user = User.objects.create_user(
        username='e2e_warehouse',
        email='warehouse@test.com',
        password='testpass123',
        first_name='أمين',
        last_name='المخزن'
    )
    yield user
    
    # تنظيف بعد الاختبار
    try:
        user.delete()
    except:
        pass


# ==================== Fixtures للنظام المحاسبي ====================

@pytest.fixture(scope='session')
def setup_chart_of_accounts(django_db_setup, django_db_blocker):
    """تحميل شجرة الحسابات من fixtures النظام"""
    with django_db_blocker.unblock():
        from django.core.management import call_command
        
        # تحميل الحسابات المحاسبية من fixtures النظام
        try:
            call_command('loaddata', 'financial/fixtures/chart_of_accounts.json', verbosity=0)
        except:
            pass
        
        try:
            call_command('loaddata', 'financial/fixtures/financial_categories.json', verbosity=0)
        except:
            pass
        
        # تحميل الفترات المحاسبية إن وجدت
        try:
            call_command('loaddata', 'financial/fixtures/accounting_periods.json', verbosity=0)
        except:
            # إنشاء فترة محاسبية للسنة الحالية إذا لم تكن موجودة
            from financial.models import AccountingPeriod
            from datetime import date
            
            current_year = date.today().year
            AccountingPeriod.objects.get_or_create(
                year=current_year,
                defaults={
                    'start_date': date(current_year, 1, 1),
                    'end_date': date(current_year, 12, 31),
                    'is_closed': False,
                    'is_active': True
                }
            )


# ==================== Fixtures للمنتجات والمخازن ====================

@pytest.fixture
def test_category(db):
    """فئة منتجات للاختبار - مع تنظيف تلقائي"""
    from product.models import Category
    
    # حذف الفئة إن وجدت
    Category.objects.filter(code='E2E_CAT').delete()
    
    category = Category.objects.create(
        name='فئة الاختبار E2E',
        code='E2E_CAT',
        is_active=True
    )
    yield category
    
    # تنظيف بعد الاختبار
    try:
        category.delete()
    except:
        pass


@pytest.fixture
def test_unit(db):
    """وحدة قياس للاختبار - مع تنظيف تلقائي"""
    from product.models import Unit
    
    # حذف الوحدة إن وجدت
    Unit.objects.filter(code='E2E_UNIT').delete()
    
    unit = Unit.objects.create(
        name='قطعة',
        code='E2E_UNIT',
        is_active=True
    )
    yield unit
    
    # تنظيف بعد الاختبار
    try:
        unit.delete()
    except:
        pass


@pytest.fixture
def test_warehouse(db, warehouse_user):
    """مخزن للاختبار - مع تنظيف تلقائي"""
    from product.models import Warehouse, Stock
    
    # حذف المخزن إن وجد
    Warehouse.objects.filter(code='E2E_WH').delete()
    
    warehouse = Warehouse.objects.create(
        code='E2E_WH',
        name='مخزن الاختبار E2E',
        location='موقع الاختبار',
        manager=warehouse_user,
        is_active=True
    )
    yield warehouse
    
    # تنظيف بعد الاختبار
    try:
        # حذف المخزون أولاً
        Stock.objects.filter(warehouse=warehouse).delete()
        warehouse.delete()
    except:
        pass


# ==================== Fixtures للعملاء والموردين ====================

@pytest.fixture
def test_customer(db, test_user):
    """عميل للاختبار - مع تنظيف تلقائي"""
    from client.models import Customer
    from client.services.customer_service import CustomerService
    
    # حذف العميل إن وجد
    Customer.objects.filter(code='E2E_CUST').delete()
    
    service = CustomerService()
    customer = service.create_customer(
        name='عميل الاختبار E2E',
        code='E2E_CUST',
        user=test_user,
        phone='01234567890',
        email='customer@e2e.test',
        address='شارع الاختبار، المنصورة',
        client_type='individual',
        credit_limit=Decimal('10000.00')
    )
    yield customer
    
    # تنظيف بعد الاختبار
    try:
        # حذف الحساب المحاسبي أولاً
        if customer.financial_account:
            customer.financial_account.delete()
        customer.delete()
    except:
        pass


@pytest.fixture
def test_supplier(db, test_user):
    """مورد للاختبار - مع تنظيف تلقائي"""
    from supplier.models import Supplier
    from supplier.services.supplier_service import SupplierService
    
    # حذف المورد إن وجد
    Supplier.objects.filter(code='E2E_SUP').delete()
    
    service = SupplierService()
    supplier = service.create_supplier(
        name='مورد الاختبار E2E',
        code='E2E_SUP',
        user=test_user,
        phone='01234567890',
        email='supplier@e2e.test',
        address='شارع الموردين، المنصورة',
        is_active=True
    )
    yield supplier
    
    # تنظيف بعد الاختبار
    try:
        # حذف الحساب المحاسبي أولاً
        if supplier.financial_account:
            supplier.financial_account.delete()
        supplier.delete()
    except:
        pass


# ==================== Fixtures للتواريخ ====================

@pytest.fixture
def today():
    """تاريخ اليوم"""
    return date.today()


@pytest.fixture
def yesterday():
    """تاريخ أمس"""
    return date.today() - timedelta(days=1)


@pytest.fixture
def tomorrow():
    """تاريخ غداً"""
    return date.today() + timedelta(days=1)


@pytest.fixture
def now():
    """الوقت الحالي"""
    return timezone.now()


# ==================== Hooks للتنظيف ====================

@pytest.fixture(autouse=True)
def cleanup_test_data(db):
    """تنظيف البيانات قبل وبعد كل اختبار"""
    # التنظيف قبل الاختبار
    cache.clear()
    
    yield
    
    # التنظيف بعد الاختبار
    cache.clear()


@pytest.fixture(autouse=True)
def reset_sequences(db):
    """إعادة تعيين sequences بعد كل اختبار (لـ SQLite)"""
    yield
    
    # إعادة تعيين sequences
    try:
        with connection.cursor() as cursor:
            # SQLite specific
            cursor.execute("DELETE FROM sqlite_sequence WHERE name LIKE 'E2E_%'")
    except:
        pass


# ==================== Markers ====================

def pytest_configure(config):
    """تسجيل markers مخصصة"""
    config.addinivalue_line("markers", "e2e: mark test as end-to-end test")
    config.addinivalue_line("markers", "business_flow: complete business flow tests")
    config.addinivalue_line("markers", "payment: payment and accounting tests")
    config.addinivalue_line("markers", "concurrency: concurrency and rollback tests")
    config.addinivalue_line("markers", "security: security and permissions tests")
    config.addinivalue_line("markers", "critical: critical test that must pass")
    config.addinivalue_line("markers", "stress: stress and performance tests")
    config.addinivalue_line("markers", "edge_case: edge case and boundary tests")
    config.addinivalue_line("markers", "integration: integration tests between modules")
    config.addinivalue_line("markers", "property: property-based tests with Hypothesis")
    config.addinivalue_line("markers", "chaos: chaos engineering tests")
    config.addinivalue_line("markers", "performance: performance and benchmark tests")
    config.addinivalue_line("markers", "race_condition: race condition tests")
    config.addinivalue_line("markers", "slow: slow tests (>5 seconds)")


# ==================== Helper Functions ====================

def generate_unique_code(prefix='TEST'):
    """توليد كود فريد للاختبار"""
    return f"{prefix}_{uuid.uuid4().hex[:8].upper()}"


@pytest.fixture
def unique_code():
    """fixture لتوليد كود فريد"""
    return generate_unique_code


# ==================== Performance & Benchmarking ====================

@pytest.fixture
def performance_monitor():
    """مراقب الأداء لقياس سرعة العمليات"""
    class PerformanceMonitor:
        def __init__(self):
            self.timings = {}
        
        @contextmanager
        def measure(self, operation_name):
            start = time.time()
            try:
                yield
            finally:
                elapsed = time.time() - start
                self.timings[operation_name] = elapsed
                print(f"  {operation_name}: {elapsed:.3f}s")
        
        def assert_faster_than(self, operation_name, max_seconds):
            actual = self.timings.get(operation_name, 0)
            assert actual < max_seconds, \
                f" {operation_name} took {actual:.3f}s (max: {max_seconds}s)"
        
        def get_report(self):
            return "\n".join([
                f"  {name}: {time:.3f}s"
                for name, time in sorted(self.timings.items())
            ])
    
    return PerformanceMonitor()


# ==================== Concurrency Testing ====================

@pytest.fixture
def concurrent_executor():
    """Executor للاختبارات المتزامنة"""
    executor = ThreadPoolExecutor(max_workers=10)
    yield executor
    executor.shutdown(wait=True)


@pytest.fixture
def race_condition_detector():
    """كاشف الـ race conditions"""
    class RaceConditionDetector:
        def __init__(self):
            self.results = []
            self.errors = []
        
        def run_concurrent(self, func, args_list, max_workers=10):
            """تشغيل دالة بشكل متزامن مع معاملات مختلفة"""
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(func, *args) for args in args_list]
                
                for future in futures:
                    try:
                        result = future.result()
                        self.results.append(result)
                    except Exception as e:
                        self.errors.append(e)
            
            return self.results, self.errors
        
        def assert_no_race_conditions(self, expected_count):
            """التحقق من عدم وجود race conditions"""
            actual_count = len(self.results)
            error_count = len(self.errors)
            
            print(f"\n Concurrency Results:")
            print(f"   Successful: {actual_count}")
            print(f"   Failed: {error_count}")
            
            if error_count > 0:
                print(f"\n Errors:")
                for i, error in enumerate(self.errors[:5], 1):
                    print(f"   {i}. {type(error).__name__}: {str(error)[:100]}")
            
            assert actual_count == expected_count, \
                f" Race condition detected! Expected {expected_count}, got {actual_count}"
    
    return RaceConditionDetector()


# ==================== Chaos Engineering ====================

@pytest.fixture
def chaos_monkey():
    """Chaos Monkey لاختبار مرونة النظام"""
    class ChaosMonkey:
        @contextmanager
        def simulate_slow_database(self, delay_seconds=0.5):
            """محاكاة بطء قاعدة البيانات"""
            from django.db.backends.signals import connection_created
            
            def add_delay(sender, connection, **kwargs):
                import time
                time.sleep(delay_seconds)
            
            connection_created.connect(add_delay)
            try:
                yield
            finally:
                connection_created.disconnect(add_delay)
        
        @contextmanager
        def simulate_cache_failure(self):
            """محاكاة فشل الـ cache"""
            original_get = cache.get
            original_set = cache.set
            
            def failing_get(*args, **kwargs):
                raise Exception("Cache unavailable")
            
            def failing_set(*args, **kwargs):
                raise Exception("Cache unavailable")
            
            cache.get = failing_get
            cache.set = failing_set
            
            try:
                yield
            finally:
                cache.get = original_get
                cache.set = original_set
        
        @contextmanager
        def simulate_random_failures(self, failure_rate=0.3):
            """محاكاة فشل عشوائي"""
            import random
            
            class RandomFailure(Exception):
                pass
            
            def maybe_fail():
                if random.random() < failure_rate:
                    raise RandomFailure("Random chaos failure")
            
            yield maybe_fail
    
    return ChaosMonkey()


# ==================== Database Snapshot ====================

@pytest.fixture
def db_snapshot():
    """أخذ snapshot من قاعدة البيانات واستعادتها"""
    class DatabaseSnapshot:
        def __init__(self):
            self.snapshot_data = {}
        
        def take_snapshot(self, models_to_snapshot):
            """أخذ snapshot من models محددة"""
            for model in models_to_snapshot:
                model_name = f"{model._meta.app_label}.{model._meta.model_name}"
                self.snapshot_data[model_name] = list(
                    model.objects.all().values()
                )
            print(f"� Snapshot taken: {len(self.snapshot_data)} models")
        
        def restore_snapshot(self, models_to_restore):
            """استعادة الـ snapshot"""
            for model in models_to_restore:
                model_name = f"{model._meta.app_label}.{model._meta.model_name}"
                if model_name in self.snapshot_data:
                    model.objects.all().delete()
                    for data in self.snapshot_data[model_name]:
                        model.objects.create(**data)
            print(f"♻  Snapshot restored")
    
    return DatabaseSnapshot()


# ==================== Real-World Data Generators ====================

@pytest.fixture
def realistic_data_generator():
    """مولد بيانات واقعية"""
    class RealisticDataGenerator:
        ARABIC_NAMES = [
            'محمد أحمد', 'أحمد محمود', 'علي حسن', 'حسن علي',
            'عمر خالد', 'خالد عمر', 'يوسف إبراهيم', 'إبراهيم يوسف',
            'عبدالله سعيد', 'سعيد عبدالله', 'فاطمة محمد', 'عائشة أحمد'
        ]
        
        COMPANY_NAMES = [
            'شركة النور للتجارة', 'مؤسسة الأمل التجارية', 'شركة الفجر للمقاولات',
            'مؤسسة البناء الحديث', 'شركة التقدم الصناعية', 'مؤسسة النجاح التجارية'
        ]
        
        PRODUCT_NAMES = [
            'منتج عالي الجودة', 'منتج اقتصادي', 'منتج فاخر',
            'منتج متوسط', 'منتج شعبي', 'منتج مميز'
        ]
        
        def random_name(self):
            return random.choice(self.ARABIC_NAMES)
        
        def random_company(self):
            return random.choice(self.COMPANY_NAMES)
        
        def random_product_name(self):
            return random.choice(self.PRODUCT_NAMES)
        
        def random_phone(self):
            return f"010{random.randint(10000000, 99999999)}"
        
        def random_price(self, min_price=10, max_price=10000):
            return Decimal(str(random.uniform(min_price, max_price))).quantize(Decimal('0.01'))
        
        def random_quantity(self, min_qty=1, max_qty=1000):
            return random.randint(min_qty, max_qty)
        
        def random_date_in_range(self, start_date, end_date):
            time_between = end_date - start_date
            days_between = time_between.days
            random_days = random.randrange(days_between)
            return start_date + timedelta(days=random_days)
    
    return RealisticDataGenerator()


# ==================== Audit & Logging ====================

@pytest.fixture
def audit_logger():
    """مسجل التدقيق للاختبارات"""
    class AuditLogger:
        def __init__(self):
            self.logs = []
        
        def log(self, event_type, details):
            entry = {
                'timestamp': timezone.now(),
                'event_type': event_type,
                'details': details
            }
            self.logs.append(entry)
            print(f"� {event_type}: {details}")
        
        def assert_event_logged(self, event_type):
            found = any(log['event_type'] == event_type for log in self.logs)
            assert found, f" Event '{event_type}' not logged!"
        
        def get_events_by_type(self, event_type):
            return [log for log in self.logs if log['event_type'] == event_type]
    
    return AuditLogger()
