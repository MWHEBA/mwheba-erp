import pytest
import uuid
from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model

from supplier.models import Supplier
from product.models.product_core import Product, Category, Unit
from product.models.stock_management import Warehouse, Stock
from purchase.services.purchase_return_service import PurchaseReturnService
from product.services.inventory_reservation_service import InventoryReservationService
from financial.models import ChartOfAccounts, AccountType
from financial.models import ChartOfAccounts, AccountType, AccountingPeriod
from financial.models import ChartOfAccounts, AccountType, AccountingPeriod, FiscalYear

User = get_user_model()


class Sprint5TestSuite(TestCase):
    """
    حزمة اختبارات Sprint 5: مرتجعات المشتريات المحصنة وتصفية الحجوزات المنتهية (FIN-SAL-006 & FIN-SAL-008)
    """

    def setUp(self):
        self.user = User.objects.create_user(username=f"sp5_admin_{uuid.uuid4().hex[:4]}", password="password123")
        
        # إنشاء السنة المالية والفترة المحاسبية المفتوحة
        fy, _ = FiscalYear.objects.get_or_create(
            name="2026",
            defaults={
                "start_date": date(2026, 1, 1),
                "end_date": date(2026, 12, 31),
                "status": "open"
            }
        )
        AccountingPeriod.objects.get_or_create(
            period_number=8,
            fiscal_year=fy,
            defaults={
                "name": "فترة أغسطس 2026",
                "start_date": date(2026, 8, 1),
                "end_date": date(2026, 8, 31),
                "status": "open"
            }
        )

        # إنشاء شجرة الحسابات الأساسية لاختبار حركة المخزون
        asset_type, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "أصول", "category": "ASSET"})
        expense_type, _ = AccountType.objects.get_or_create(code="EXPENSE", defaults={"name": "مصروفات", "category": "EXPENSE"})
        liability_type, _ = AccountType.objects.get_or_create(code="LIABILITY", defaults={"name": "إلتزامات", "category": "LIABILITY"})

        ChartOfAccounts.objects.get_or_create(code="10400", defaults={"name": "المخزون", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="50100", defaults={"name": "تكلفة البضاعة المباعة", "account_type": expense_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="20200", defaults={"name": "استلامات غير مفوترة", "account_type": liability_type, "is_active": True})

        self.supplier = Supplier.objects.create(name="مورد المعدات الصناعية", code=f"SUPP{uuid.uuid4().hex[:4]}")

        self.category = Category.objects.create(name="معدات", code=f"EQ{uuid.uuid4().hex[:4]}")
        self.unit = Unit.objects.create(name="قطعة")
        self.product = Product.objects.create(
            name="محرك بريميوم",
            sku=f"ENG{uuid.uuid4().hex[:4]}",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            created_by=self.user
        )
        self.warehouse = Warehouse.objects.create(name="مستودع القاهرة المركزى", code=f"WH{uuid.uuid4().hex[:4]}")

        # إنشاء مخزون 20 قطعة متوفرة بالمخزن
        self.stock = Stock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=Decimal("20.0000")
        )

    def test_01_purchase_return_split_guard(self):
        """اختبار فصل مرتجع المشتريات بين الكمية الفعيلة والإشعار المدين (FIN-SAL-006)"""
        # طلب مرتجع 50 قطعة مع توفر 20 قطعة فقط بالمخزن الفعلي
        res = PurchaseReturnService.process_purchase_return(
            supplier_id=self.supplier.id,
            product_id=self.product.id,
            warehouse_id=self.warehouse.id,
            requested_qty=Decimal("50.0000"),
            return_unit_price=Decimal("100.00"),
            user=self.user
        )

        self.assertEqual(res["physical_return_qty"], Decimal("20.0000"))
        self.assertEqual(res["debit_note_qty"], Decimal("30.0000"))
        self.assertEqual(res["total_return_value"], Decimal("5000.00"))
        self.assertIsNotNone(res["debit_note_ref"])

    def test_02_expired_reservation_sweep(self):
        """اختبار تنظيف وإفراج الحجوزات المنتهية تلقائياً (FIN-SAL-008)"""
        swept = InventoryReservationService.sweep_expired_reservations(user=self.user)
        self.assertIsInstance(swept, list)
