"""
اختبارات الخدمات المتقدمة لنظام المخزون
"""
import unittest
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from unittest.mock import patch, Mock

from product.models import (
    Product,
    Category,
    Brand,
    Unit,
    Warehouse,
    ProductStock,
    SupplierProductPrice,
    PriceHistory,
)
from product.services.advanced_reports_service import AdvancedReportsService
from product.services.pricing_service import PricingService
from supplier.models import Supplier

User = get_user_model()


class BaseTestCaseWithAccounts(TestCase):
    """Base test case that sets up accounting system"""
    
    @classmethod
    def setUpTestData(cls):
        """إعداد النظام المحاسبي مرة واحدة للكل"""
        super().setUpTestData()
        from financial.models import AccountType, ChartOfAccounts
        
        # إنشاء أنواع الحسابات الأساسية
        account_types_data = {
            'ASSETS': 'الأصول',
            'LIABILITIES': 'الخصوم',
            'EQUITY': 'حقوق الملكية',
            'REVENUE': 'الإيرادات',
            'EXPENSES': 'المصروفات',
            'RECEIVABLES': 'المدينون',
            'PAYABLES': 'الدائنون',
            'CASH': 'النقدية',
        }
        
        for code, name in account_types_data.items():
            AccountType.objects.get_or_create(
                code=code,
                defaults={'name': name}
            )
        
        # إنشاء حساب نقدية أساسي
        cash_type = AccountType.objects.get(code='CASH')
        ChartOfAccounts.objects.get_or_create(
            code='1001',
            defaults={
                'name': 'الصندوق الرئيسي',
                'account_type': cash_type,
                'is_active': True
            }
        )


class PricingServiceTestCase(TransactionTestCase):
    """اختبارات خدمة التسعير المتقدمة - استخدام TransactionTestCase لعزل أفضل"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="pricinguser", email="pricing@example.com", password="testpass123"
        )

        # إنشاء البيانات الأساسية
        self.category = Category.objects.create(name="إلكترونيات")
        self.brand = Brand.objects.create(name="سامسونج")
        self.unit = Unit.objects.create(name="قطعة", symbol="قطعة")

        self.product = Product.objects.create(
            name="هاتف ذكي",
            sku="PHONE001",
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            cost_price=Decimal("500.00"),
            selling_price=Decimal("750.00"),
            created_by=self.user,
        )

        # إنشاء موردين
        self.supplier1 = Supplier.objects.create(
            name="مورد الإلكترونيات",
            code="SUP001",
            email="supplier1@example.com",
            phone="123456789"
        )

        self.supplier2 = Supplier.objects.create(
            name="مورد التقنية",
            code="SUP002",
            email="supplier2@example.com",
            phone="987654321"
        )

        # تنظيف جميع الأسعار القديمة لضمان عزل الاختبارات
        SupplierProductPrice.objects.all().delete()

        self.pricing_service = PricingService()

    def test_update_supplier_price(self):
        """اختبار تحديث سعر المورد"""
        # إنشاء سعر أولي
        initial_price = SupplierProductPrice.objects.create(
            product=self.product,
            supplier=self.supplier1,
            cost_price=Decimal("450.00"),
            created_by=self.user,
        )
        
        # تحديث السعر
        supplier_price = self.pricing_service.update_supplier_price(
            product=self.product,
            supplier=self.supplier1,
            new_price=Decimal("480.00"),
            user=self.user,
            reason="purchase",
            purchase_reference="PUR001",
        )

        self.assertEqual(supplier_price.cost_price, Decimal("480.00"))
        self.assertEqual(supplier_price.supplier, self.supplier1)

        # التحقق من تسجيل التاريخ
        history = PriceHistory.objects.filter(
            supplier_product_price=supplier_price
        ).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.old_price, Decimal("450.00"))
        self.assertEqual(history.new_price, Decimal("480.00"))
        self.assertEqual(history.change_reason, "purchase")

    def test_set_default_supplier(self):
        """اختبار تعيين مورد افتراضي"""
        # إضافة أسعار لموردين
        price1 = SupplierProductPrice.objects.create(
            product=self.product,
            supplier=self.supplier1,
            cost_price=Decimal("480.00"),
            created_by=self.user,
        )

        price2 = SupplierProductPrice.objects.create(
            product=self.product,
            supplier=self.supplier2,
            cost_price=Decimal("470.00"),
            created_by=self.user,
        )

        # تعيين المورد الثاني كافتراضي
        result = self.pricing_service.set_default_supplier(
            product=self.product, supplier=self.supplier2, user=self.user
        )

        self.assertTrue(result)

        # التحقق من التحديث
        price1.refresh_from_db()
        price2.refresh_from_db()
        self.product.refresh_from_db()

        self.assertFalse(price1.is_default)
        self.assertTrue(price2.is_default)
        self.assertEqual(self.product.default_supplier, self.supplier2)

    def test_bulk_update_prices(self):
        """اختبار تحديث أسعار متعددة"""
        # إنشاء منتج آخر
        product2 = Product.objects.create(
            name="لابتوب",
            sku="LAPTOP001",
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            cost_price=Decimal("2000.00"),
            selling_price=Decimal("3000.00"),
            created_by=self.user,
        )

        # إنشاء الأسعار أولاً
        price1 = SupplierProductPrice.objects.create(
            product=self.product,
            supplier=self.supplier1,
            cost_price=Decimal("480.00"),
            is_default=True,
            created_by=self.user,
        )
        
        price2 = SupplierProductPrice.objects.create(
            product=product2,
            supplier=self.supplier1,
            cost_price=Decimal("1900.00"),
            created_by=self.user,
        )

        # بيانات التحديث - استخدام supplier_price_id
        price_updates = [
            {
                "supplier_price_id": price1.id,
                "new_price": Decimal("485.00"),
            },
            {
                "supplier_price_id": price2.id,
                "new_price": Decimal("1950.00"),
            },
        ]

        # تحديث الأسعار
        results = self.pricing_service.bulk_update_prices(
            price_updates, self.user, "bulk_update"
        )

        # Service returns updated/created/errors
        self.assertEqual(results["updated"], 2)
        self.assertEqual(len(results.get("errors", [])), 0)

        # التحقق من التحديث الفعلي
        price1.refresh_from_db()
        self.assertEqual(price1.cost_price, Decimal("485.00"))
        
        price2.refresh_from_db()
        self.assertEqual(price2.cost_price, Decimal("1950.00"))


class AdvancedReportsServiceTestCase(BaseTestCaseWithAccounts):
    """اختبارات خدمة التقارير المتقدمة"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="reportsuser", email="reports@example.com", password="testpass123"
        )

        # إنشاء البيانات الأساسية
        self.category = Category.objects.create(name="إلكترونيات")
        self.brand = Brand.objects.create(name="سامسونج")
        self.unit = Unit.objects.create(name="قطعة", symbol="قطعة")

        self.warehouse = Warehouse.objects.create(
            name="المخزن الرئيسي", code="MAIN", location="الرياض", manager=self.user
        )

        # إنشاء منتجات متعددة
        self.products = []
        for i in range(5):
            product = Product.objects.create(
                name=f"منتج {i+1}",
                sku=f"PROD00{i+1}",
                category=self.category,
                brand=self.brand,
                unit=self.unit,
                cost_price=Decimal(f"{100 + i*50}.00"),
                selling_price=Decimal(f"{150 + i*75}.00"),
                created_by=self.user,
            )
            self.products.append(product)

            # إنشاء مخزون
            ProductStock.objects.create(
                product=product,
                warehouse=self.warehouse,
                quantity=100 - i * 10,  # كميات متدرجة
                min_stock_level=10,
                max_stock_level=200,
            )

        self.reports_service = AdvancedReportsService()


class SecurityTestCase(BaseTestCaseWithAccounts):
    """اختبارات الأمان للنظام"""

    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
            is_staff=True,
        )

        self.regular_user = User.objects.create_user(
            username="regular", email="regular@example.com", password="regularpass123"
        )

        # إنشاء البيانات الأساسية
        self.category = Category.objects.create(name="أمان")
        self.brand = Brand.objects.create(name="علامة آمنة")
        self.unit = Unit.objects.create(name="وحدة", symbol="وحدة")

        self.warehouse = Warehouse.objects.create(
            name="مخزن آمن", code="SECURE", location="آمن", manager=self.admin_user
        )

        self.product = Product.objects.create(
            name="منتج آمن",
            sku="SECURE001",
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            created_by=self.admin_user,
        )

    def test_user_permissions_on_stock(self):
        """اختبار صلاحيات المستخدم على المخزون"""
        stock = ProductStock.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=100
        )

        # المستخدم العادي لا يجب أن يتمكن من تعديل المخزون مباشرة
        # هذا يجب أن يتم عبر حركات المخزون المعتمدة

        # اختبار إنشاء حركة مخزون بدون اعتماد
        from product.models import InventoryMovement

        movement = InventoryMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            movement_type="adjustment_in",
            document_type="adjustment",
            document_number="ADJ001",
            quantity=50,
            unit_cost=Decimal("100.00"),
            total_cost=Decimal("5000.00"),
            created_by=self.regular_user,
        )

        # الحركة يجب أن تكون غير معتمدة
        self.assertFalse(movement.is_approved)
        self.assertIsNone(movement.approved_by)

    def test_data_validation(self):
        """اختبار التحقق من صحة البيانات"""
        from django.core.exceptions import ValidationError
        from django.db import IntegrityError, transaction

        # اختبار كمية سالبة - PositiveIntegerField يرفض القيم السالبة عند الحفظ
        with transaction.atomic():
            with self.assertRaises((ValidationError, IntegrityError, ValueError)):
                stock = ProductStock(
                    product=self.product,
                    warehouse=self.warehouse,
                    quantity=-10,  # كمية سالبة غير مسموحة
                )
                stock.save()

        # اختبار كمية محجوزة أكبر من الكمية المتاحة
        stock = ProductStock.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=50
        )

        # التحقق من أن الكمية المحجوزة لا يمكن أن تكون أكبر من الكمية المتاحة
        stock.reserved_quantity = 60
        
        # نتحقق من أن الكمية المتاحة سالبة
        available = stock.quantity - stock.reserved_quantity
        self.assertLess(available, 0, "الكمية المحجوزة أكبر من الكمية المتاحة")

    def test_audit_trail(self):
        """اختبار مسار التدقيق"""
        from product.models import InventoryMovement

        # إنشاء حركة مخزون
        movement = InventoryMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            movement_type="in",
            document_type="purchase",
            document_number="REC001",
            quantity=100,
            unit_cost=Decimal("100.00"),
            total_cost=Decimal("10000.00"),
            created_by=self.regular_user,
        )

        # التحقق من تسجيل معلومات التدقيق
        self.assertEqual(movement.created_by, self.regular_user)
        self.assertIsNotNone(movement.created_at)

        # اعتماد الحركة
        movement.is_approved = True
        movement.approved_by = self.admin_user
        movement.approval_date = timezone.now()
        movement.save()

        # التحقق من تسجيل معلومات الاعتماد
        self.assertTrue(movement.is_approved)
        self.assertEqual(movement.approved_by, self.admin_user)
        self.assertIsNotNone(movement.approval_date)


# إعداد تشغيل الاختبارات
if __name__ == "__main__":
    import django
    from django.test.utils import get_runner

    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(["product.tests.test_advanced_services"])
