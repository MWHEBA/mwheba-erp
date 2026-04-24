"""
إعدادات pytest العامة - محسنة للاختبارات E2E
"""
import os
import sys
import django
from django.conf import settings
import pytest
from hypothesis import settings as hypothesis_settings
import logging

# إضافة مسار المشروع
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# تكوين Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')

if not settings.configured:
    django.setup()

# تقليل مستوى التسجيل للاختبارات
logging.getLogger('django').setLevel(logging.WARNING)
logging.getLogger('django.db.backends').setLevel(logging.WARNING)

# إعدادات Hypothesis للـ Property-based testing
hypothesis_settings.register_profile("default", max_examples=10, deadline=5000)
hypothesis_settings.register_profile("ci", max_examples=50, deadline=10000)
hypothesis_settings.register_profile("dev", max_examples=5, deadline=2000)

# تحديد البروفايل حسب البيئة
profile = os.getenv("HYPOTHESIS_PROFILE", "dev")
hypothesis_settings.load_profile(profile)

# Fixtures أساسية
@pytest.fixture
def arabic_faker():
    """Faker للنصوص العربية"""
    from faker import Faker
    return Faker('ar_SA')

@pytest.fixture
def test_user(db):
    """مستخدم للاختبار"""
    from django.contrib.auth.models import User
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )

@pytest.fixture
def admin_user(db):
    """مستخدم إداري للاختبار"""
    from django.contrib.auth.models import User
    return User.objects.create_superuser(
        username='admin',
        email='admin@example.com', 
        password='adminpass123'
    )

@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """
    تمكين الوصول لقاعدة البيانات لجميع الاختبارات تلقائياً
    """
    pass

@pytest.fixture
def client_with_user(client, test_user):
    """Client مع مستخدم مسجل دخول"""
    client.force_login(test_user)
    return client

@pytest.fixture
def admin_client(client, admin_user):
    """Client مع مستخدم إداري مسجل دخول"""
    client.force_login(admin_user)
    return client

@pytest.fixture
def test_data_context():
    """Context للبيانات التجريبية"""
    return {
        'created_at': 'test_context'
    }

@pytest.fixture
def data_stats():
    """إحصائيات البيانات للاختبار"""
    return {
        'database_size': '0 MB',
        'last_updated': 'test_stats',
        '_total_records': 0,
        '_timestamp': 'test_timestamp'
    }

# إعدادات خاصة باختبارات E2E
@pytest.fixture(scope="session")
def django_db_setup(django_db_setup):
    """إعداد قاعدة البيانات للاختبارات"""
    # استخدام django_db_setup الافتراضي
    pass


@pytest.fixture
def test_supplier():
    """مورد للاختبارات"""
    try:
        from supplier.models import Supplier
        
        supplier, created = Supplier.objects.get_or_create(
            code='TEST_SUP_001',
            defaults={
                'name': 'مورد الاختبار',
                'phone': '01234567890',
                'email': 'test@supplier.com',
                'address': 'شارع الاختبار، المنصورة'
            }
        )
        return supplier
    except ImportError:
        return None

@pytest.fixture
def test_customer():
    """عميل للاختبارات"""
    try:
        from client.models import Customer
        
        customer, created = Customer.objects.get_or_create(
            code='TEST_CUST_001',
            defaults={
                'name': 'أحمد محمد علي - اختبار',
                'phone': '01234567890',
                'email': 'test@customer.com',
                'address': 'شارع الاختبار، المنصورة',
                'is_active': True
            }
        )
        return customer
    except ImportError:
        return None

@pytest.fixture
def e2e_test_prefix():
    """Prefix فريد لاختبارات E2E"""
    import time
    return f"E2E_TEST_{int(time.time())}_"

# معالجة الأخطاء في الاختبارات
def pytest_runtest_makereport(item, call):
    """معالجة تقارير الاختبارات"""
    if "incremental" in item.keywords:
        if call.excinfo is not None:
            parent = item.parent
            parent._previousfailed = item

def pytest_runtest_setup(item):
    """إعداد الاختبار"""
    if "incremental" in item.keywords:
        previousfailed = getattr(item.parent, "_previousfailed", None)
        if previousfailed is not None:
            pytest.xfail("previous test failed (%s)" % previousfailed.name)