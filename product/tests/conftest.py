"""
إعداد pytest لاختبارات نظام المخزن المحسن
"""
import pytest
import os
import sys
from decimal import Decimal
from datetime import date, timedelta
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

# إضافة مسار المشروع
project_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if project_path not in sys.path:
    sys.path.insert(0, project_path)

# إعداد Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mwheba_erp.settings')

import django
django.setup()

from product.models import (
    Product, Category, Brand, Unit, Warehouse, ProductStock,
    StockReservation, ProductBatch, SupplierProductPrice
)
from supplier.models import Supplier
from product.tests.test_utils import TestDataFactory

User = get_user_model()


# إعدادات pytest
def pytest_configure(config):
    """إعداد pytest"""
    import django
    from django.conf import settings
    
    # إعداد قاعدة بيانات الاختبار
    settings.DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
        'TEST': {
            'NAME': ':memory:',
        },
    }
    
    # تعطيل الـ migrations للسرعة
    settings.MIGRATION_MODULES = {
        'product': None,
        'supplier': None,
        'financial': None,
        'purchase': None,
        'sale': None,
        'client': None,
        'users': None,
        'core': None,
        'utils': None,
    }
    
    django.setup()


# Fixtures أساسية
@pytest.fixture
def user():
    """مستخدم للاختبار"""
    return TestDataFactory.create_user()


@pytest.fixture
def admin_user():
    """مستخدم إداري للاختبار"""
    return TestDataFactory.create_user(
        username='admin',
        is_staff=True,
        is_superuser=True
    )


@pytest.fixture
def category():
    """فئة للاختبار"""
    return TestDataFactory.create_category()


@pytest.fixture
def brand():
    """علامة تجارية للاختبار"""
    return TestDataFactory.create_brand()


@pytest.fixture
def unit():
    """وحدة قياس للاختبار"""
    return TestDataFactory.create_unit()


@pytest.fixture
def warehouse(user):
    """مستودع للاختبار"""
    return TestDataFactory.create_warehouse(manager=user)


@pytest.fixture
def product(category, brand, unit, user):
    """منتج للاختبار"""
    return TestDataFactory.create_product(
        category=category,
        brand=brand,
        unit=unit,
        created_by=user
    )


@pytest.fixture
def supplier():
    """مورد للاختبار"""
    return TestDataFactory.create_supplier()


# Fixtures للمخزون
@pytest.fixture
def product_stock(product, warehouse):
    """مخزون منتج للاختبار"""
    return TestDataFactory.create_product_stock(
        product=product,
        warehouse=warehouse
    )


@pytest.fixture
def stock_reservation(product, warehouse, user):
    """حجز مخزون للاختبار"""
    return TestDataFactory.create_stock_reservation(
        product=product,
        warehouse=warehouse,
        created_by=user
    )


@pytest.fixture
def product_batch(product, warehouse):
    """دفعة منتج للاختبار"""
    return TestDataFactory.create_product_batch(
        product=product,
        warehouse=warehouse
    )


@pytest.fixture
def supplier_product_price(product, supplier):
    """سعر مورد للاختبار"""
    return TestDataFactory.create_supplier_product_price(
        product=product,
        supplier=supplier
    )


# Fixtures للسيناريوهات المعقدة
@pytest.fixture
def basic_inventory_setup(user):
    """إعداد مخزون أساسي"""
    from product.tests.test_utils import TestScenarios
    return TestScenarios.setup_basic_inventory_scenario()


@pytest.fixture
def supplier_pricing_setup(user):
    """إعداد تسعير الموردين"""
    from product.tests.test_utils import TestScenarios
    return TestScenarios.setup_supplier_pricing_scenario()


@pytest.fixture
def expiry_tracking_setup(user):
    """إعداد تتبع انتهاء الصلاحية"""
    from product.tests.test_utils import TestScenarios
    return TestScenarios.setup_expiry_tracking_scenario()


@pytest.fixture
def reservation_setup(user):
    """إعداد الحجوزات"""
    from product.tests.test_utils import TestScenarios
    return TestScenarios.setup_reservation_scenario()


# Fixtures للخدمات الوهمية
@pytest.fixture
def mock_notification_service():
    """خدمة إشعارات وهمية"""
    from product.tests.test_utils import MockServices
    return MockServices.mock_notification_service()


@pytest.fixture
def mock_email_service():
    """خدمة بريد إلكتروني وهمية"""
    from product.tests.test_utils import MockServices
    return MockServices.mock_email_service()


# Fixtures للعميل (Client)
@pytest.fixture
def client():
    """عميل Django للاختبار"""
    from django.test import Client
    return Client()


@pytest.fixture
def authenticated_client(client, user):
    """عميل مسجل الدخول"""
    client.force_login(user)
    return client


@pytest.fixture
def admin_client(client, admin_user):
    """عميل إداري مسجل الدخول"""
    client.force_login(admin_user)
    return client


# Fixtures للبيانات المتعددة
@pytest.fixture
def multiple_products(category, brand, unit, user):
    """عدة منتجات للاختبار"""
    products = []
    for i in range(5):
        product = TestDataFactory.create_product(
            name=f'منتج {i+1}',
            sku=f'MULTI{i+1:03d}',
            category=category,
            brand=brand,
            unit=unit,
            created_by=user,
            cost_price=Decimal(f'{100 + i*10}.00'),
            selling_price=Decimal(f'{150 + i*15}.00')
        )
        products.append(product)
    return products


@pytest.fixture
def multiple_warehouses(user):
    """عدة مستودعات للاختبار"""
    warehouses = []
    locations = ['الرياض', 'جدة', 'الدمام', 'المدينة', 'مكة']
    
    for i, location in enumerate(locations):
        warehouse = TestDataFactory.create_warehouse(
            name=f'مستودع {location}',
            code=f'WH{i+1:02d}',
            location=location,
            manager=user
        )
        warehouses.append(warehouse)
    return warehouses


@pytest.fixture
def multiple_suppliers():
    """عدة موردين للاختبار"""
    suppliers = []
    for i in range(3):
        supplier = TestDataFactory.create_supplier(
            name=f'مورد {i+1}',
            email=f'supplier{i+1}@example.com'
        )
        suppliers.append(supplier)
    return suppliers


# Fixtures للتواريخ
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
def next_week():
    """تاريخ الأسبوع القادم"""
    return date.today() + timedelta(weeks=1)


@pytest.fixture
def next_month():
    """تاريخ الشهر القادم"""
    return date.today() + timedelta(days=30)


@pytest.fixture
def next_year():
    """تاريخ السنة القادمة"""
    return date.today() + timedelta(days=365)


# Fixtures للأوقات
@pytest.fixture
def now():
    """الوقت الحالي"""
    return timezone.now()


@pytest.fixture
def hour_ago():
    """قبل ساعة"""
    return timezone.now() - timedelta(hours=1)


@pytest.fixture
def hour_later():
    """بعد ساعة"""
    return timezone.now() + timedelta(hours=1)


@pytest.fixture
def day_later():
    """بعد يوم"""
    return timezone.now() + timedelta(days=1)


# Fixtures للأرقام العشرية
@pytest.fixture
def decimal_100():
    """رقم عشري 100"""
    return Decimal('100.00')


@pytest.fixture
def decimal_150():
    """رقم عشري 150"""
    return Decimal('150.00')


@pytest.fixture
def decimal_95():
    """رقم عشري 95"""
    return Decimal('95.00')


# Hooks للاختبارات
def pytest_runtest_setup(item):
    """إعداد قبل كل اختبار"""
    # تنظيف الكاش
    from django.core.cache import cache
    cache.clear()


def pytest_runtest_teardown(item, nextitem):
    """تنظيف بعد كل اختبار"""
    # تنظيف الكاش
    from django.core.cache import cache
    cache.clear()


# Markers مخصصة
def pytest_configure(config):
    """تسجيل markers مخصصة"""
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as unit test"
    )
    config.addinivalue_line(
        "markers", "api: mark test as API test"
    )
    config.addinivalue_line(
        "markers", "view: mark test as view test"
    )
    config.addinivalue_line(
        "markers", "service: mark test as service test"
    )
    config.addinivalue_line(
        "markers", "model: mark test as model test"
    )


# إعدادات إضافية
pytest_plugins = [
    'django',
]
