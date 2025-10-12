"""
إعدادات pytest لاختبارات نظام التسعير
Pytest Configuration for Pricing System Tests
"""
import pytest
import os
import django
from django.conf import settings
from django.test.utils import get_runner
from django.contrib.auth.models import User
from decimal import Decimal

# إعداد Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mwheba_erp.settings')
django.setup()


@pytest.fixture(scope='session')
def django_db_setup():
    """إعداد قاعدة البيانات للاختبارات"""
    settings.DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }


@pytest.fixture
def user():
    """إنشاء مستخدم للاختبار"""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )


@pytest.fixture
def admin_user():
    """إنشاء مستخدم إداري للاختبار"""
    return User.objects.create_superuser(
        username='admin',
        email='admin@example.com',
        password='adminpass123'
    )


@pytest.fixture
def client_obj():
    """إنشاء عميل للاختبار"""
    from client.models import Client
    return Client.objects.create(
        name='عميل تجريبي',
        email='client@test.com',
        phone='01234567890',
        address='عنوان تجريبي'
    )


@pytest.fixture
def supplier():
    """إنشاء مورد للاختبار"""
    from supplier.models import Supplier
    return Supplier.objects.create(
        name='مورد تجريبي',
        email='supplier@test.com',
        phone='01234567890',
        address='عنوان المورد'
    )


@pytest.fixture
def paper_type():
    """إنشاء نوع ورق للاختبار"""
    from pricing.models import PaperType
    return PaperType.objects.create(
        name='ورق أبيض',
        description='ورق أبيض عادي',
        weight=80,
        price_per_kg=Decimal('15.00')
    )


@pytest.fixture
def paper_size():
    """إنشاء مقاس ورق للاختبار"""
    from pricing.models import PaperSize
    return PaperSize.objects.create(
        name='A4',
        width=21.0,
        height=29.7,
        description='مقاس A4 قياسي'
    )


@pytest.fixture
def plate_size():
    """إنشاء مقاس زنك للاختبار"""
    from pricing.models import PlateSize
    return PlateSize.objects.create(
        name='70x100',
        width=70.0,
        height=100.0,
        price=Decimal('200.00')
    )


@pytest.fixture
def coating_type():
    """إنشاء نوع طلاء للاختبار"""
    from pricing.models import CoatingType
    return CoatingType.objects.create(
        name='لامينيشن لامع',
        description='طلاء لامع',
        price_per_sheet=Decimal('0.25')
    )


@pytest.fixture
def finishing_type():
    """إنشاء نوع تشطيب للاختبار"""
    from pricing.models import FinishingType
    return FinishingType.objects.create(
        name='تجليد حلزوني',
        description='تجليد بالحلزون',
        price_per_unit=Decimal('2.00')
    )


@pytest.fixture
def print_direction():
    """إنشاء اتجاه طباعة للاختبار"""
    from pricing.models import PrintDirection
    return PrintDirection.objects.create(
        name='طباعة وجه واحد',
        description='طباعة على وجه واحد فقط'
    )


@pytest.fixture
def pricing_order(user, client_obj):
    """إنشاء طلب تسعير للاختبار"""
    from pricing.models import PricingOrder
    return PricingOrder.objects.create(
        client=client_obj,
        product_name='كتالوج شركة',
        quantity=1000,
        description='كتالوج تعريفي للشركة',
        created_by=user
    )


@pytest.fixture
def complete_pricing_order(user, client_obj, paper_type, paper_size):
    """إنشاء طلب تسعير كامل للاختبار"""
    from pricing.models import PricingOrder
    return PricingOrder.objects.create(
        client=client_obj,
        product_name='كتالوج شركة',
        quantity=1000,
        description='كتالوج تعريفي للشركة',
        paper_type=paper_type,
        paper_size=paper_size,
        colors=4,
        pages=16,
        paper_cost=Decimal('500.00'),
        printing_cost=Decimal('300.00'),
        finishing_cost=Decimal('200.00'),
        created_by=user
    )


@pytest.fixture
def pricing_quotation(user, pricing_order):
    """إنشاء عرض سعر للاختبار"""
    from pricing.models import PricingQuotation
    from datetime import date, timedelta
    
    return PricingQuotation.objects.create(
        order=pricing_order,
        total_price=Decimal('1500.00'),
        profit_margin=Decimal('20.00'),
        valid_until=date.today() + timedelta(days=30),
        notes='عرض سعر تجريبي',
        created_by=user
    )


@pytest.fixture
def order_supplier(pricing_order, supplier):
    """إنشاء مورد طلب للاختبار"""
    from pricing.models import OrderSupplier
    return OrderSupplier.objects.create(
        order=pricing_order,
        supplier=supplier,
        service_type='printing',
        cost=Decimal('300.00'),
        notes='خدمة طباعة'
    )


@pytest.fixture
def internal_content(pricing_order, paper_type, paper_size):
    """إنشاء محتوى داخلي للاختبار"""
    from pricing.models import InternalContent
    return InternalContent.objects.create(
        order=pricing_order,
        paper_type=paper_type,
        paper_size=paper_size,
        pages=16,
        colors=4,
        description='محتوى داخلي للكتالوج'
    )


@pytest.fixture
def order_finishing(pricing_order, finishing_type, supplier):
    """إنشاء تشطيب طلب للاختبار"""
    from pricing.models import OrderFinishing
    return OrderFinishing.objects.create(
        order=pricing_order,
        finishing_type=finishing_type,
        cost=Decimal('100.00'),
        supplier=supplier,
        notes='تجليد حلزوني'
    )


@pytest.fixture
def extra_expense(pricing_order):
    """إنشاء مصروف إضافي للاختبار"""
    from pricing.models import ExtraExpense
    return ExtraExpense.objects.create(
        order=pricing_order,
        description='مصروف شحن',
        amount=Decimal('50.00')
    )


@pytest.fixture
def order_comment(pricing_order, user):
    """إنشاء تعليق طلب للاختبار"""
    from pricing.models import OrderComment
    return OrderComment.objects.create(
        order=pricing_order,
        comment='تعليق تجريبي على الطلب',
        created_by=user
    )


@pytest.fixture
def pricing_approval_workflow(user):
    """إنشاء سير عمل موافقة للاختبار"""
    from pricing.models import PricingApprovalWorkflow
    return PricingApprovalWorkflow.objects.create(
        name='سير موافقة عادي',
        description='سير موافقة للطلبات العادية',
        created_by=user
    )


@pytest.fixture
def pricing_approval(pricing_order, pricing_approval_workflow, user):
    """إنشاء موافقة للاختبار"""
    from pricing.models import PricingApproval
    return PricingApproval.objects.create(
        order=pricing_order,
        workflow=pricing_approval_workflow,
        approver=user,
        level=1,
        notes='موافقة تجريبية'
    )


@pytest.fixture
def api_client():
    """إنشاء عميل API للاختبار"""
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def authenticated_api_client(api_client, user):
    """إنشاء عميل API مع تسجيل دخول"""
    api_client.force_authenticate(user=user)
    return api_client


# Markers للاختبارات
def pytest_configure(config):
    """تكوين pytest markers"""
    config.addinivalue_line(
        "markers", "slow: اختبارات بطيئة التنفيذ"
    )
    config.addinivalue_line(
        "markers", "integration: اختبارات التكامل"
    )
    config.addinivalue_line(
        "markers", "unit: اختبارات الوحدة"
    )
    config.addinivalue_line(
        "markers", "api: اختبارات الـ API"
    )
    config.addinivalue_line(
        "markers", "view: اختبارات الواجهات"
    )
    config.addinivalue_line(
        "markers", "service: اختبارات الخدمات"
    )
    config.addinivalue_line(
        "markers", "model: اختبارات النماذج"
    )
    config.addinivalue_line(
        "markers", "form: اختبارات النماذج"
    )
    config.addinivalue_line(
        "markers", "javascript: اختبارات JavaScript"
    )
    config.addinivalue_line(
        "markers", "selenium: اختبارات Selenium"
    )
    config.addinivalue_line(
        "markers", "performance: اختبارات الأداء"
    )
    config.addinivalue_line(
        "markers", "security: اختبارات الأمان"
    )


# إعدادات إضافية للاختبارات
@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """تمكين الوصول لقاعدة البيانات لجميع الاختبارات"""
    pass


@pytest.fixture
def sample_calculation_data():
    """بيانات عينة للحسابات"""
    return {
        'quantity': 1000,
        'paper_cost_per_unit': Decimal('0.50'),
        'printing_cost_per_unit': Decimal('0.30'),
        'finishing_cost_per_unit': Decimal('0.20'),
        'profit_margin': Decimal('20.00'),
        'colors': 4,
        'pages': 16
    }


@pytest.fixture
def mock_api_responses():
    """استجابات API وهمية للاختبار"""
    return {
        'paper_price': {
            'success': True,
            'price': Decimal('75.00'),
            'weight': Decimal('5.00')
        },
        'plate_price': {
            'success': True,
            'total_price': Decimal('200.00'),
            'price_per_plate': Decimal('50.00')
        },
        'calculate_cost': {
            'success': True,
            'total_cost': Decimal('1000.00'),
            'paper_cost': Decimal('500.00'),
            'printing_cost': Decimal('300.00'),
            'finishing_cost': Decimal('200.00')
        }
    }


class TestDataFactory:
    """مصنع إنشاء بيانات الاختبار"""
    
    @staticmethod
    def create_paper_types(count=5):
        """إنشاء أنواع ورق متعددة"""
        from pricing.models import PaperType
        paper_types = []
        
        for i in range(count):
            paper_type = PaperType.objects.create(
                name=f'ورق نوع {i+1}',
                weight=80 + (i * 20),
                price_per_kg=Decimal(f'{15 + i}.00')
            )
            paper_types.append(paper_type)
            
        return paper_types
    
    @staticmethod
    def create_paper_sizes(count=5):
        """إنشاء مقاسات ورق متعددة"""
        from pricing.models import PaperSize
        sizes = [
            ('A4', 21.0, 29.7),
            ('A3', 29.7, 42.0),
            ('A5', 14.8, 21.0),
            ('Letter', 21.6, 27.9),
            ('Legal', 21.6, 35.6)
        ]
        
        paper_sizes = []
        for i in range(min(count, len(sizes))):
            name, width, height = sizes[i]
            paper_size = PaperSize.objects.create(
                name=name,
                width=width,
                height=height
            )
            paper_sizes.append(paper_size)
            
        return paper_sizes
    
    @staticmethod
    def create_pricing_orders(user, client_obj, count=10):
        """إنشاء طلبات تسعير متعددة"""
        from pricing.models import PricingOrder
        orders = []
        
        for i in range(count):
            order = PricingOrder.objects.create(
                client=client_obj,
                product_name=f'منتج {i+1}',
                quantity=1000 + (i * 100),
                description=f'وصف المنتج {i+1}',
                created_by=user
            )
            orders.append(order)
            
        return orders


@pytest.fixture
def test_data_factory():
    """إرجاع مصنع بيانات الاختبار"""
    return TestDataFactory
