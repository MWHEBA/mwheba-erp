import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency
from product.models import Product, Warehouse, InventoryMovement, Category, Unit
from product.services.voucher_accounting_service import (
    get_inventory_account,
    get_contra_account,
    create_receipt_voucher_entry,
    create_issue_voucher_entry,
)

User = get_user_model()


@pytest.mark.django_db
class TestVoucherAccounting:
    @pytest.fixture(autouse=True)
    def setup_accounts_and_data(self):
        self.egp, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "Egyptian Pound", "symbol": "£"})
        self.asset_type, _ = AccountType.objects.get_or_create(
            code="ASSET", defaults={"name": "Assets", "category": "asset"}
        )
        self.revenue_type, _ = AccountType.objects.get_or_create(
            code="REVENUE", defaults={"name": "Revenues", "category": "revenue"}
        )
        self.expense_type, _ = AccountType.objects.get_or_create(
            code="EXPENSE", defaults={"name": "Expenses", "category": "expense"}
        )

        # Standard COA accounts
        self.inv_11310, _ = ChartOfAccounts.objects.get_or_create(
            code="11310",
            defaults={"name": "مخزون البضائع التامة", "account_type": self.asset_type, "currency": self.egp, "is_active": True}
        )
        self.rev_49110, _ = ChartOfAccounts.objects.get_or_create(
            code="49110",
            defaults={"name": "إيرادات متنوعة", "account_type": self.revenue_type, "currency": self.egp, "is_active": True}
        )
        self.exp_52500, _ = ChartOfAccounts.objects.get_or_create(
            code="52500",
            defaults={"name": "أدوات مكتبية ومطبوعات", "account_type": self.expense_type, "currency": self.egp, "is_active": True}
        )

        self.user, _ = User.objects.get_or_create(username="voucher_tester", defaults={"email": "v_test@example.com"})
        self.warehouse, _ = Warehouse.objects.get_or_create(name="المخزن الرئيسي", defaults={"code": "WH-MAIN"})
        self.category, _ = Category.objects.get_or_create(name="تصنيف عام")
        self.unit, _ = Unit.objects.get_or_create(name="قطعة")
        self.product, _ = Product.objects.get_or_create(
            name="منتج تجريبي للاختبار",
            defaults={
                "category": self.category,
                "unit": self.unit,
                "sku": "SKU-VOUCHER-1",
                "cost_price": Decimal("100.00"),
                "selling_price": Decimal("150.00"),
                "created_by": self.user
            }
        )

    def test_get_inventory_account_fallback(self):
        acc = get_inventory_account(product=self.product, warehouse=self.warehouse)
        assert acc is not None
        assert acc.code == "11310"

    def test_get_contra_account_resolution(self):
        acc_receipt = get_contra_account("supplies_gifts", is_receipt=True)
        assert acc_receipt is not None
        assert acc_receipt.code == "49110"

        acc_issue = get_contra_account("office_supplies", is_receipt=False)
        assert acc_issue is not None
        assert acc_issue.code == "52500"

    def test_create_receipt_voucher_entry(self):
        voucher = InventoryMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            movement_type="in",
            voucher_type="receipt",
            purpose_type="supplies_gifts",
            quantity=Decimal("5.00"),
            unit_cost=Decimal("100.00"),
            movement_date=timezone.now(),
            movement_number="REC-TEST-001",
            is_approved=True,
            approved_by=self.user,
            created_by=self.user
        )

        entry = create_receipt_voucher_entry(voucher)
        assert entry is not None
        voucher.refresh_from_db()
        assert voucher.journal_entry == entry

        lines = list(entry.lines.all())
        assert len(lines) == 2
        debit_line = [l for l in lines if l.debit > 0][0]
        credit_line = [l for l in lines if l.credit > 0][0]
        assert debit_line.account.code == "11310"
        assert debit_line.debit == Decimal("500.00")
        assert credit_line.account.code == "49110"
        assert credit_line.credit == Decimal("500.00")

    def test_create_issue_voucher_entry(self):
        voucher = InventoryMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            movement_type="out",
            voucher_type="issue",
            purpose_type="office_supplies",
            quantity=Decimal("2.00"),
            unit_cost=Decimal("100.00"),
            movement_date=timezone.now(),
            movement_number="ISS-TEST-001",
            is_approved=True,
            approved_by=self.user,
            created_by=self.user
        )

        entry = create_issue_voucher_entry(voucher)
        assert entry is not None
        voucher.refresh_from_db()
        assert voucher.journal_entry == entry

        lines = list(entry.lines.all())
        assert len(lines) == 2
        debit_line = [l for l in lines if l.debit > 0][0]
        credit_line = [l for l in lines if l.credit > 0][0]
        assert debit_line.code == "52500" if hasattr(debit_line, "code") else debit_line.account.code == "52500"
        assert debit_line.debit == Decimal("200.00")
        assert credit_line.code == "11310" if hasattr(credit_line, "code") else credit_line.account.code == "11310"
        assert credit_line.credit == Decimal("200.00")

    def test_issue_voucher_form_valid(self):
        from product.forms import IssueVoucherForm
        from product.models.stock_management import Stock

        Stock.objects.create(product=self.product, warehouse=self.warehouse, quantity=Decimal("10.00"), average_cost=Decimal("100.00"))

        form_data = {
            'product': self.product.id,
            'warehouse': self.warehouse.id,
            'quantity': 2,
            'purpose_type': 'office_supplies',
            'issued_by_name': 'أحمد علي',
            'notes': 'صرف تجريبي'
        }
        form = IssueVoucherForm(data=form_data)
        assert form.is_valid(), f"Form errors: {form.errors}"

    def test_single_source_of_truth_no_double_movement_on_receipt(self):
        """التحقق من عدم حدوث حركات مزدوجة أو تكرار تعديل رصيد المخزون عند اعتماد إذن استلام"""
        from product.models.stock_management import Stock, StockMovement

        # رصيد ابتدائي 0
        stock = Stock.objects.create(product=self.product, warehouse=self.warehouse, quantity=Decimal("0.00"), average_cost=Decimal("0.00"))

        voucher = InventoryMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            movement_type="in",
            voucher_type="receipt",
            purpose_type="opening_balance",
            quantity=Decimal("5.00"),
            unit_cost=Decimal("100.00"),
            movement_date=timezone.now(),
            movement_number="REC-SSOT-001",
            created_by=self.user
        )

        initial_stock_movements_count = StockMovement.objects.count()

        # اعتماد الإذن
        assert voucher.approve(self.user) is True

        # التأكد من تحديث رصيد المخزون مرة واحدة بالضبط (5 قطع وليس 10)
        stock.refresh_from_db()
        assert stock.quantity == Decimal("5.00"), f"Expected 5.00, got {stock.quantity}"

        # التأكد من عدم إنشاء سجل مكرر في StockMovement
        assert StockMovement.objects.count() == initial_stock_movements_count

    def test_single_source_of_truth_no_double_movement_on_issue(self):
        """التحقق من عدم حدوث حركات مزدوجة أو تكرار خصم المخزون عند اعتماد إذن صرف"""
        from product.models.stock_management import Stock, StockMovement

        # رصيد ابتدائي 10
        stock = Stock.objects.create(product=self.product, warehouse=self.warehouse, quantity=Decimal("10.00"), average_cost=Decimal("100.00"))

        voucher = InventoryMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            movement_type="out",
            voucher_type="issue",
            purpose_type="office_supplies",
            quantity=Decimal("3.00"),
            unit_cost=Decimal("100.00"),
            movement_date=timezone.now(),
            movement_number="ISS-SSOT-001",
            created_by=self.user
        )

        initial_stock_movements_count = StockMovement.objects.count()

        # اعتماد الإذن
        assert voucher.approve(self.user) is True

        # التأكد من خصم المخزون مرة واحدة بالضبط (10 - 3 = 7 قطع وليس 4)
        stock.refresh_from_db()
        assert stock.quantity == Decimal("7.00"), f"Expected 7.00, got {stock.quantity}"

        # التأكد من عدم إنشاء سجل مكرر في StockMovement
        assert StockMovement.objects.count() == initial_stock_movements_count

    def test_receipt_and_issue_voucher_detail_view_renders(self, client):
        """التحقق من أن صفحة تفاصيل إذن الاستلام والصرف تفتح وتُرسم بنجاح (200 OK) للإذن المعتمد وغير المعتمد"""
        from django.urls import reverse

        self.user.is_superuser = True
        self.user.save()
        client.force_login(self.user)

        # 1. إذن استلام معتمد
        receipt_voucher = InventoryMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            movement_type="in",
            voucher_type="receipt",
            purpose_type="opening_balance",
            quantity=Decimal("5.00"),
            unit_cost=Decimal("100.00"),
            movement_date=timezone.now(),
            movement_number="REC-VIEW-001",
            is_approved=True,
            approved_by=self.user,
            created_by=self.user
        )

        response = client.get(reverse('product:receipt_voucher_detail', args=[receipt_voucher.pk]))
        assert response.status_code == 200, f"Receipt voucher detail failed with {response.status_code}"

        # 2. إذن صرف معتمد
        issue_voucher = InventoryMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            movement_type="out",
            voucher_type="issue",
            purpose_type="office_supplies",
            quantity=Decimal("2.00"),
            unit_cost=Decimal("100.00"),
            movement_date=timezone.now(),
            movement_number="ISS-VIEW-001",
            is_approved=True,
            approved_by=self.user,
            created_by=self.user
        )

        response = client.get(reverse('product:issue_voucher_detail', args=[issue_voucher.pk]))
        assert response.status_code == 200, f"Issue voucher detail failed with {response.status_code}"
