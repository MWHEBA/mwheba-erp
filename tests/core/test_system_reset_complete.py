import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from core.services.system_reset_service import SystemResetService
from core.models import DocumentSequenceRule, DocumentSequenceCounter, Notification, DashboardStat
from governance.models import IdempotencyRecord
from customer.models import Customer
from supplier.models import Supplier
from product.models import Product, Category, Unit, Warehouse, Stock, PriceHistory, SerialNumber
from financial.models import (
    FiscalYear, AccountingPeriod, ChartOfAccounts, AccountType,
    JournalEntry, JournalEntryLine, OpeningBalanceBatch, OpeningBalanceLine,
    BankStatementBatch, ControlAccountOverrideRequest
)
from sale.models import Sale, SaleItem, Quotation, QuotationItem
from purchase.models import Purchase, PurchaseItem, SupplierBill
from work_order.models import WorkOrder
from printing_pricing.models import PrintingOrder

User = get_user_model()


@pytest.mark.django_db
class TestSystemResetComplete:
    """
    اختبارات شاملة ومكثفة لخدمة تفريغ وتصفير النظام
    """

    def test_complete_system_reset(self):
        # 1. إعداد بيانات أساسية (Master Data)
        user, _ = User.objects.get_or_create(username="admin_reset_test", defaults={"email": "admin_reset_test@mwheba.com", "is_superuser": True})
        category, _ = Category.objects.get_or_create(name="تصنيف تصفير تجريبي")
        unit, _ = Unit.objects.get_or_create(name="قطعة تصفير", defaults={"symbol": "RST_PCS"})
        warehouse, _ = Warehouse.objects.get_or_create(code="WH-RESET-99", defaults={"name": "مخزن التصفير التجريبي"})
        
        acc_type, _ = AccountType.objects.get_or_create(
            name="أصول تصفير",
            code="ASSETS_RST",
            defaults={"nature": "debit", "category": "asset"}
        )
        acc1, _ = ChartOfAccounts.objects.get_or_create(
            code="111199",
            defaults={
                "name": "خزينة التصفير التجريبية",
                "account_type": acc_type,
                "opening_balance": Decimal("5000.00"),
                "is_leaf": True,
                "is_active": True
            }
        )
        acc1.opening_balance = Decimal("5000.00")
        acc1.save()

        acc2, _ = ChartOfAccounts.objects.get_or_create(
            code="410199",
            defaults={
                "name": "مبيعات التصفير التجريبية",
                "account_type": acc_type,
                "opening_balance": Decimal("0.00"),
                "is_leaf": True,
                "is_active": True
            }
        )

        customer, _ = Customer.objects.get_or_create(
            code="CUST-RST-001",
            defaults={"name": "عميل تصفير تجريبي", "balance": Decimal("1500.00")}
        )
        customer.balance = Decimal("1500.00")
        customer.save()

        supplier, _ = Supplier.objects.get_or_create(
            name="مورد تصفير تجريبي",
            defaults={"balance": Decimal("3000.00")}
        )
        supplier.balance = Decimal("3000.00")
        supplier.save()

        product, _ = Product.objects.get_or_create(
            sku="PRD-RST-001",
            defaults={
                "name": "منتج تصفير تجريبي",
                "category": category,
                "unit": unit,
                "cost_price": Decimal("100.00"),
                "selling_price": Decimal("150.00"),
                "created_by": user
            }
        )
        stock, _ = Stock.objects.get_or_create(
            product=product,
            warehouse=warehouse,
            defaults={"quantity": 50, "reserved_quantity": 10}
        )
        stock.quantity = 50
        stock.reserved_quantity = 10
        stock.save()

        fiscal_year = FiscalYear.objects.first()
        if not fiscal_year:
            fiscal_year = FiscalYear.objects.create(
                year_code="FY_RST_2099",
                name="سنة التصفير 2099",
                start_date="2099-01-01",
                end_date="2099-12-31",
                status="open"
            )

        period = AccountingPeriod.objects.first()
        if not period:
            period = AccountingPeriod.objects.create(
                fiscal_year=fiscal_year,
                name="فترة التصفير 2099",
                period_number=1,
                start_date="2099-01-01",
                end_date="2099-01-31",
                status="open"
            )

        # 2. إنشاء حركات تجريبية (Transactions & Opening Balances)
        je = JournalEntry.objects.create(
            number="GL269998",
            date=timezone.now().date(),
            description="قيد تجريبي للتصفير",
            status="posted"
        )
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=acc1,
            debit=Decimal("1000.00"),
            credit=Decimal("0.00")
        )
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=acc2,
            debit=Decimal("0.00"),
            credit=Decimal("1000.00")
        )

        batch = OpeningBalanceBatch.objects.create(
            batch_number="OPB269998",
            fiscal_year=fiscal_year,
            status="draft",
            journal_entry=je
        )
        OpeningBalanceLine.objects.create(
            batch=batch,
            account=acc1,
            debit=Decimal("5000.00"),
            credit=Decimal("0.00")
        )
        OpeningBalanceBatch.objects.filter(pk=batch.pk).update(status="posted")

        # طلب استثناء محاسبي
        ControlAccountOverrideRequest.objects.create(
            opening_batch=batch,
            account=acc1,
            requested_by=user,
            reason="استثناء تجريبي",
            status="approved"
        )

        # قفل السنة والفترة بعد إنشاء الدفعة لاختبار قيام المعالج بفتحها
        fiscal_year.status = "closed"
        fiscal_year.save()

        period.status = "closed"
        period.save()

        rule, _ = DocumentSequenceRule.objects.get_or_create(
            document_type="SALE_RST",
            defaults={"prefix": "INV-RST-", "is_locked": True}
        )
        rule.is_locked = True
        rule.save()

        counter, _ = DocumentSequenceCounter.objects.get_or_create(
            document_type="SALE_RST",
            year=2026,
            defaults={"last_number": 45, "rule": rule}
        )
        counter.last_number = 45
        counter.save()

        # إشعارات ومفاتيح idempotency وداشبورد
        Notification.objects.create(user=user, title="إشعار تجريبي", message="رسالة")
        DashboardStat.objects.create(title="إحصائية تجريبية", value="1000")
        IdempotencyRecord.objects.create(
            operation_type="TEST_OP",
            idempotency_key="TEST-KEY-12345",
            expires_at=timezone.now() + timezone.timedelta(days=1),
            result_data={"test": True}
        )

        # حركات مبيعات ومشتريات
        sale = Sale.objects.create(
            number="SALE-RST-001",
            date=timezone.now().date(),
            customer=customer,
            warehouse=warehouse,
            subtotal=Decimal("150.00"),
            total=Decimal("150.00"),
            created_by=user
        )
        SaleItem.objects.create(
            sale=sale,
            product=product,
            quantity=1,
            unit_price=Decimal("150.00"),
            total=Decimal("150.00")
        )

        quotation = Quotation.objects.create(
            number="QUO-RST-001",
            date=timezone.now().date(),
            customer=customer,
            total=Decimal("300.00"),
            created_by=user
        )
        QuotationItem.objects.create(
            quotation=quotation,
            product=product,
            quantity=2,
            unit_price=Decimal("150.00"),
            total=Decimal("300.00")
        )

        purchase = Purchase.objects.create(
            number="PUR-RST-001",
            date=timezone.now().date(),
            supplier=supplier,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            created_by=user
        )
        PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            quantity=1,
            unit_price=Decimal("100.00"),
            total=Decimal("100.00")
        )

        PriceHistory.objects.create(
            product=product,
            old_price=Decimal("90.00"),
            new_price=Decimal("100.00"),
            change_reason="purchase",
            source_type="CATALOG_BASE",
            changed_by=user
        )
        SerialNumber.objects.create(
            document_type="test_doc",
            last_number=5,
            prefix="DOC-",
            year=2026
        )

        # 3. تشغيل خدمة التصفير
        summary = SystemResetService.reset_test_transactions(user=user)
        assert summary is not None

        # 4. التحقق من مسح الحركات والأرصدة الافتتاحية والمبيعات والمشتريات
        assert OpeningBalanceBatch.objects.filter(batch_number="OPB269998").count() == 0
        assert OpeningBalanceLine.objects.count() == 0
        assert ControlAccountOverrideRequest.objects.count() == 0
        assert JournalEntry.objects.filter(number="GL269998").count() == 0
        assert Sale.objects.filter(number="SALE-RST-001").count() == 0
        assert SaleItem.objects.count() == 0
        assert Quotation.objects.filter(number="QUO-RST-001").count() == 0
        assert Purchase.objects.filter(number="PUR-RST-001").count() == 0
        assert PurchaseItem.objects.count() == 0
        assert PriceHistory.objects.count() == 0
        assert SerialNumber.objects.count() == 0
        assert Notification.objects.count() == 0
        assert DashboardStat.objects.count() == 0
        assert IdempotencyRecord.objects.count() == 0

        # 5. التحقق من تصفير الأرصدة
        customer.refresh_from_db()
        assert customer.balance == Decimal("0.00")

        supplier.refresh_from_db()
        assert supplier.balance == Decimal("0.00")

        acc1.refresh_from_db()
        assert acc1.opening_balance == Decimal("0.00")

        stock.refresh_from_db()
        assert stock.quantity == 0
        assert stock.reserved_quantity == 0

        # 6. التحقق من فتح الفترات المالية وتصفير العدادات
        fiscal_year.refresh_from_db()
        assert fiscal_year.status == "open"
        assert fiscal_year.is_closed is False

        period.refresh_from_db()
        assert period.status == "open"
        assert period.is_closed is False

        counter.refresh_from_db()
        assert counter.last_number == 0

        rule.refresh_from_db()
        assert rule.is_locked is False

        # 7. التحقق من بقاء البيانات الأساسية (Master Data)
        assert User.objects.filter(username="admin_reset_test").exists()
        assert Category.objects.filter(name="تصنيف تصفير تجريبي").exists()
        assert Warehouse.objects.filter(code="WH-RESET-99").exists()
        assert Product.objects.filter(sku="PRD-RST-001").exists()
        assert Customer.objects.filter(code="CUST-RST-001").exists()
        assert Supplier.objects.filter(name="مورد تصفير تجريبي").exists()
        assert ChartOfAccounts.objects.filter(code="111199").exists()
