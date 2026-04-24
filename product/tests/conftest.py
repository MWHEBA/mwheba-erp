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
project_path = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if project_path not in sys.path:
    sys.path.insert(0, project_path)

# إعداد Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "corporate_erp.settings")

import django

django.setup()

from product.models import (
    Product,
    Category,

    Unit,
    Warehouse,
    StockReservation,
    ProductBatch,
    SupplierProductPrice,
)
from supplier.models import Supplier
# استيراد TestDataFactory من tests/factories
# from tests.factories.academic_factories import AcademicYearFactory

# إنشاء TestDataFactory مؤقت
class TestDataFactory:
    @staticmethod
    def create_user(**kwargs):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        defaults = {
            'username': f'testuser_{User.objects.count() + 1}',
            'email': f'test{User.objects.count() + 1}@example.com',
            'password': 'testpass123'
        }
        defaults.update(kwargs)
        password = defaults.pop('password')
        user = User.objects.create_user(**defaults)
        user.set_password(password)
        user.save()
        return user
    
    @staticmethod
    def create_category(**kwargs):
        from product.models import Category
        defaults = {
            'name': f'فئة اختبار {Category.objects.count() + 1}',
            'is_active': True
        }
        defaults.update(kwargs)
        return Category.objects.create(**defaults)
    
    @staticmethod
    def create_unit(**kwargs):
        from product.models import Unit
        defaults = {
            'name': f'وحدة اختبار {Unit.objects.count() + 1}',
            'symbol': f'U{Unit.objects.count() + 1}',
            'is_active': True
        }
        defaults.update(kwargs)
        return Unit.objects.create(**defaults)
    
    @staticmethod
    def create_warehouse(**kwargs):
        from product.models import Warehouse
        defaults = {
            'name': f'مخزن اختبار {Warehouse.objects.count() + 1}',
            'code': f'WH{Warehouse.objects.count() + 1:03d}',
            'location': 'موقع اختبار',
            'is_active': True
        }
        defaults.update(kwargs)
        return Warehouse.objects.create(**defaults)
    
    @staticmethod
    def create_product(**kwargs):
        from product.models import Product
        defaults = {
            'name': f'منتج اختبار {Product.objects.count() + 1}',
            'sku': f'PROD{Product.objects.count() + 1:03d}',
            'cost_price': Decimal('100.00'),
            'selling_price': Decimal('150.00'),
            'is_active': True
        }
        defaults.update(kwargs)
        return Product.objects.create(**defaults)
    
    @staticmethod
    def create_supplier(**kwargs):
        from supplier.models import Supplier
        defaults = {
            'name': f'مورد اختبار {Supplier.objects.count() + 1}',
            'email': f'supplier{Supplier.objects.count() + 1}@example.com',
            'phone': f'01{Supplier.objects.count() + 1:09d}',
            'is_active': True
        }
        defaults.update(kwargs)
        return Supplier.objects.create(**defaults)
    
    @staticmethod
    def create_product_stock(**kwargs):
        from product.models import Stock
        defaults = {
            'quantity': 100,
            'reserved_quantity': 0,
            'min_stock_level': 10
        }
        defaults.update(kwargs)
        return Stock.objects.create(**defaults)
    
    @staticmethod
    def create_stock_reservation(**kwargs):
        from product.models import StockReservation
        defaults = {
            'quantity': 10,
            'status': 'active',
            'expires_at': timezone.now() + timedelta(days=7)
        }
        defaults.update(kwargs)
        return StockReservation.objects.create(**defaults)
    
    @staticmethod
    def create_product_batch(**kwargs):
        from product.models import ProductBatch
        defaults = {
            'batch_number': f'BATCH{ProductBatch.objects.count() + 1:03d}',
            'quantity': 50,
            'production_date': date.today(),
            'expiry_date': date.today() + timedelta(days=365)
        }
        defaults.update(kwargs)
        return ProductBatch.objects.create(**defaults)
    
    @staticmethod
    def create_supplier_product_price(**kwargs):
        from product.models import SupplierProductPrice
        defaults = {
            'price': Decimal('95.00'),
            'minimum_quantity': 1,
            'is_active': True
        }
        defaults.update(kwargs)
        return SupplierProductPrice.objects.create(**defaults)

# إنشاء TestScenarios مؤقت
class TestScenarios:
    @staticmethod
    def setup_basic_inventory_scenario():
        return {'message': 'Basic inventory scenario setup'}
    
    @staticmethod
    def setup_supplier_pricing_scenario():
        return {'message': 'Supplier pricing scenario setup'}
    
    @staticmethod
    def setup_expiry_tracking_scenario():
        return {'message': 'Expiry tracking scenario setup'}
    
    @staticmethod
    def setup_reservation_scenario():
        return {'message': 'Reservation scenario setup'}

# إنشاء MockServices مؤقت
class MockServices:
    @staticmethod
    def mock_notification_service():
        return {'message': 'Mock notification service'}
    
    @staticmethod
    def mock_email_service():
        return {'message': 'Mock email service'}

User = get_user_model()


# إعدادات pytest
def pytest_configure(config):
    """إعداد pytest"""
    import django
    from django.conf import settings

    # إعداد قاعدة بيانات الاختبار
    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {
            "NAME": ":memory:",
        },
    }

    # تعطيل الـ migrations للسرعة
    settings.MIGRATION_MODULES = {
        "product": None,
        "supplier": None,
        "financial": None,
        "purchase": None,
        "sale": None,
        "client": None,
        "users": None,
        "core": None,
        "utils": None,
    }

    django.setup()


# Fixtures للحسابات المحاسبية
@pytest.fixture(scope="session", autouse=True)
def setup_accounting_system(django_db_setup, django_db_blocker):
    """إعداد النظام المحاسبي للاختبارات"""
    with django_db_blocker.unblock():
        from financial.models import AccountType, ChartOfAccounts
        
        # إنشاء أنواع الحسابات الأساسية
        account_types = {
            'ASSETS': {'name': 'الأصول', 'code': 'ASSETS'},
            'LIABILITIES': {'name': 'الخصوم', 'code': 'LIABILITIES'},
            'EQUITY': {'name': 'حقوق الملكية', 'code': 'EQUITY'},
            'REVENUE': {'name': 'الإيرادات', 'code': 'REVENUE'},
            'EXPENSES': {'name': 'المصروفات', 'code': 'EXPENSES'},
            'RECEIVABLES': {'name': 'المدينون', 'code': 'RECEIVABLES'},
            'PAYABLES': {'name': 'الدائنون', 'code': 'PAYABLES'},
            'CASH': {'name': 'النقدية', 'code': 'CASH'},
        }
        
        for code, data in account_types.items():
            AccountType.objects.get_or_create(
                code=code,
                defaults={'name': data['name']}
            )
        
        # إنشاء حسابات أساسية
        cash_type = AccountType.objects.get(code='CASH')
        ChartOfAccounts.objects.get_or_create(
            code='1001',
            defaults={
                'name': 'الصندوق الرئيسي',
                'account_type': cash_type,
                'is_active': True
            }
        )


# Fixtures أساسية
@pytest.fixture
def user():
    """مستخدم للاختبار"""
    return TestDataFactory.create_user()


@pytest.fixture
def admin_user():
    """مستخدم إداري للاختبار"""
    return TestDataFactory.create_user(
        username="admin", is_staff=True, is_superuser=True
    )


@pytest.fixture
def category():
    """فئة للاختبار"""
    return TestDataFactory.create_category()




@pytest.fixture
def unit():
    """وحدة قياس للاختبار"""
    return TestDataFactory.create_unit()


@pytest.fixture
def warehouse(user):
    """مخزن للاختبار"""
    return TestDataFactory.create_warehouse(manager=user)


@pytest.fixture
def product(category, unit, user):
    """منتج للاختبار"""
    return TestDataFactory.create_product(
        category=category, unit=unit, created_by=user
    )


@pytest.fixture
def supplier():
    """مورد للاختبار"""
    return TestDataFactory.create_supplier()


# Fixtures للمخزون
@pytest.fixture
def product_stock(product, warehouse):
    """مخزون منتج للاختبار"""
    return TestDataFactory.create_product_stock(product=product, warehouse=warehouse)


@pytest.fixture
def stock_reservation(product, warehouse, user):
    """حجز مخزون للاختبار"""
    return TestDataFactory.create_stock_reservation(
        product=product, warehouse=warehouse, created_by=user
    )


@pytest.fixture
def product_batch(product, warehouse):
    """دفعة منتج للاختبار"""
    return TestDataFactory.create_product_batch(product=product, warehouse=warehouse)


@pytest.fixture
def supplier_product_price(product, supplier):
    """سعر مورد للاختبار"""
    return TestDataFactory.create_supplier_product_price(
        product=product, supplier=supplier
    )


@pytest.fixture
def basic_inventory_setup(user):
    """إعداد مخزون أساسي"""
    return TestScenarios.setup_basic_inventory_scenario()


@pytest.fixture
def supplier_pricing_setup(user):
    """إعداد تسعير الموردين"""
    return TestScenarios.setup_supplier_pricing_scenario()


@pytest.fixture
def expiry_tracking_setup(user):
    """إعداد تتبع انتهاء الصلاحية"""
    return TestScenarios.setup_expiry_tracking_scenario()


@pytest.fixture
def reservation_setup(user):
    """إعداد الحجوزات"""
    return TestScenarios.setup_reservation_scenario()


# Fixtures للخدمات الوهمية
@pytest.fixture
def mock_notification_service():
    """خدمة إشعارات وهمية"""
    return MockServices.mock_notification_service()


@pytest.fixture
def mock_email_service():
    """خدمة بريد إلكتروني وهمية"""
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
def multiple_products(category, unit, user):
    """عدة منتجات للاختبار"""
    products = []
    for i in range(5):
        product = TestDataFactory.create_product(
            name=f"منتج {i+1}",
            sku=f"MULTI{i+1:03d}",
            category=category,
            unit=unit,
            created_by=user,
            cost_price=Decimal(f"{100 + i*10}.00"),
            selling_price=Decimal(f"{150 + i*15}.00"),
        )
        products.append(product)
    return products


@pytest.fixture
def multiple_warehouses(user):
    """عدة مخزنات للاختبار"""
    warehouses = []
    locations = ["الرياض", "جدة", "الدمام", "المدينة", "مكة"]

    for i, location in enumerate(locations):
        warehouse = TestDataFactory.create_warehouse(
            name=f"مخزن {location}",
            code=f"WH{i+1:02d}",
            location=location,
            manager=user,
        )
        warehouses.append(warehouse)
    return warehouses


@pytest.fixture
def multiple_suppliers():
    """عدة موردين للاختبار"""
    suppliers = []
    for i in range(3):
        supplier = TestDataFactory.create_supplier(
            name=f"مورد {i+1}", email=f"supplier{i+1}@example.com"
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
    return Decimal("100.00")


@pytest.fixture
def decimal_150():
    """رقم عشري 150"""
    return Decimal("150.00")


@pytest.fixture
def decimal_95():
    """رقم عشري 95"""
    return Decimal("95.00")


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
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "unit: mark test as unit test")
    config.addinivalue_line("markers", "api: mark test as API test")
    config.addinivalue_line("markers", "view: mark test as view test")
    config.addinivalue_line("markers", "service: mark test as service test")
    config.addinivalue_line("markers", "model: mark test as model test")


# إعدادات إضافية - تم نقلها إلى conftest.py الرئيسي
# pytest_plugins = [
#     "django",
# ]
