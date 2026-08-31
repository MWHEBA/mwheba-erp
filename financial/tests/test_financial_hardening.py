import pytest
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from sale.models import Sale, SalePayment
from purchase.models import Purchase, PurchasePayment
from customer.models import Customer
from supplier.models import Supplier
from product.models import Product, Category, Warehouse, Unit
from financial.models import ChartOfAccounts, AccountType, AccountingPeriod
from product.models import SerialNumber
from sale.services.sale_service import SaleService
from purchase.services.purchase_service import PurchaseService
from financial.services.payment_management_service import PaymentManagementService

User = get_user_model()


@pytest.fixture
def hardening_env(db):
    user = User.objects.create_superuser(username="admin_h_user", email="admin_h@test.com", password="password")
    regular_user = User.objects.create_user(username="regular_h_user", email="user_h@test.com", password="password")

    current_year = timezone.now().year
    AccountingPeriod.objects.get_or_create(
        start_date=timezone.datetime(current_year, 1, 1).date(),
        end_date=timezone.datetime(current_year, 12, 31).date(),
        defaults={"name": f"السنة المالية {current_year}", "status": "open"}
    )
    SerialNumber.objects.get_or_create(document_type="sale", year=current_year, defaults={"prefix": "SALE", "last_number": 0})
    SerialNumber.objects.get_or_create(document_type="purchase", year=current_year, defaults={"prefix": "PUR", "last_number": 0})

    cash_type, _ = AccountType.objects.get_or_create(code="CASH", defaults={"name": "نقدية", "nature": "debit"})
    asset_type, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "أصول", "nature": "debit"})
    rev_type, _ = AccountType.objects.get_or_create(code="REVENUE", defaults={"name": "إيرادات", "nature": "credit"})
    liab_type, _ = AccountType.objects.get_or_create(code="LIABILITY", defaults={"name": "خصوم", "nature": "credit"})
    exp_type, _ = AccountType.objects.get_or_create(code="EXPENSE", defaults={"name": "مصروفات", "nature": "debit"})

    ChartOfAccounts.objects.get_or_create(code="11110", defaults={"name": "الخزينة", "account_type": cash_type, "is_active": True})
    ChartOfAccounts.objects.get_or_create(code="41100", defaults={"name": "المبيعات", "account_type": rev_type, "is_active": True})
    ChartOfAccounts.objects.get_or_create(code="11310", defaults={"name": "المخزون", "account_type": asset_type, "is_active": True})
    ChartOfAccounts.objects.get_or_create(code="51100", defaults={"name": "تكلفة البضاعة", "account_type": exp_type, "is_active": True})
    ChartOfAccounts.objects.get_or_create(code="21810", defaults={"name": "ضريبة خصم أرباح تجارية", "account_type": liab_type, "is_active": True})
    ChartOfAccounts.objects.get_or_create(code="21330", defaults={"name": "ضريبة الخصم والتحصيل", "account_type": liab_type, "is_active": True})

    category, _ = Category.objects.get_or_create(name="Hardening Cat", defaults={"is_active": True})
    warehouse, _ = Warehouse.objects.get_or_create(code="MWH", defaults={"name": "Main Warehouse", "is_active": True})
    unit, _ = Unit.objects.get_or_create(symbol="pcs", defaults={"name": "Piece", "is_active": True})

    product, _ = Product.objects.get_or_create(
        sku="HD-001",
        defaults={
            "name": "Hardening Product",
            "category": category,
            "unit": unit,
            "cost_price": Decimal("50.00"),
            "selling_price": Decimal("100.00"),
            "is_active": True,
            "created_by": user,
        }
    )

    from product.services.inventory_service import InventoryService
    InventoryService.record_movement(
        product=product,
        movement_type="in",
        quantity=Decimal("100"),
        warehouse=warehouse,
        source="initial_stock",
        unit_cost=product.cost_price,
        reference_number="INIT-HD-001",
        notes="Initial stock for testing",
        user=user
    )

    from customer.services import CustomerService
    customer = CustomerService().create_customer(
        name="Hardened Customer",
        code="HCUST01",
        phone="0100000001",
        user=user
    )

    from supplier.services import SupplierService
    supplier = SupplierService().create_supplier(
        name="Hardened Supplier",
        code="HSUPP01",
        phone="0100000002",
        user=user
    )

    return {
        "admin": user,
        "regular_user": regular_user,
        "product": product,
        "warehouse": warehouse,
        "customer": customer,
        "supplier": supplier,
    }


@pytest.mark.django_db
class TestFinancialHardeningSuite:
    def test_backend_idempotency_blocks_duplicate_sale_payment(self, hardening_env):
        """
        اختبار أن إرسال نفس الدفعة مرتين بنفس الـ idempotency_key يعيد الدفعة الأصلية دون تكرار
        """
        customer = hardening_env["customer"]
        admin = hardening_env["admin"]
        product = hardening_env["product"]
        warehouse = hardening_env["warehouse"]

        sale_data = {
            "date": timezone.now().date(),
            "customer_id": customer.id,
            "warehouse_id": warehouse.id,
            "payment_method": "credit",
            "items": [{"product_id": product.id, "quantity": Decimal("2"), "unit_price": Decimal("100.00")}]
        }
        sale = SaleService.create_sale(sale_data, user=admin)

        payment_data = {
            "amount": Decimal("100.00"),
            "payment_method": "11110",
            "payment_date": sale.date,
            "idempotency_key": "IDEM-TEST-PAY-001"
        }

        # الطلب الأول
        pmt1 = SaleService.process_payment(sale, payment_data, user=admin)
        assert pmt1.idempotency_key == "IDEM-TEST-PAY-001"
        assert SalePayment.objects.filter(sale=sale).count() == 1

        # الطلب الثاني المكرر بنفس الـ Idempotency Key
        pmt2 = SaleService.process_payment(sale, payment_data, user=admin)
        assert pmt2.id == pmt1.id
        assert SalePayment.objects.filter(sale=sale).count() == 1

    def test_purchase_wht_journal_entry_splits_to_payable(self, hardening_env):
        """
        اختبار قيد المشتريات وتوزيع ضريبة الخصم والإضافة (WHT) إلى حساب الالتزام الدائن 21810
        """
        supplier = hardening_env["supplier"]
        admin = hardening_env["admin"]
        product = hardening_env["product"]
        warehouse = hardening_env["warehouse"]

        purchase_data = {
            "date": timezone.now().date(),
            "supplier_id": supplier.id,
            "warehouse_id": warehouse.id,
            "payment_method": "credit",
            "wht_active": True,
            "wht_rate": Decimal("1.00"),
            "wht_amount": Decimal("2.00"),
            "items": [{"product_id": product.id, "quantity": Decimal("2"), "unit_price": Decimal("100.00")}]
        }
        purchase = PurchaseService.create_purchase(purchase_data, user=admin)
        assert purchase.journal_entry is not None

        lines = purchase.journal_entry.lines.all()
        wht_lines = [l for l in lines if l.account.code in ["21810", "21330"] and l.credit > Decimal("0.00")]
        assert len(wht_lines) >= 1
        assert sum(l.credit for l in wht_lines) == Decimal("2.00")

    def test_payment_rbac_blocks_unauthorized_deletion(self, hardening_env):
        """
        اختبار منع المستخدم العادي غير المصرح له من حذف الدفعات
        """
        customer = hardening_env["customer"]
        admin = hardening_env["admin"]
        regular_user = hardening_env["regular_user"]
        product = hardening_env["product"]
        warehouse = hardening_env["warehouse"]

        sale_data = {
            "date": timezone.now().date(),
            "customer_id": customer.id,
            "warehouse_id": warehouse.id,
            "payment_method": "credit",
            "items": [{"product_id": product.id, "quantity": Decimal("1"), "unit_price": Decimal("100.00")}]
        }
        sale = SaleService.create_sale(sale_data, user=admin)
        payment = SaleService.process_payment(sale, {"amount": Decimal("50.00"), "payment_method": "11110"}, user=admin)

        # المستخدم العادي بدون صلاحية يفشل
        with pytest.raises(ValidationError, match="ليس لديك الصلاحية"):
            PaymentManagementService.delete_payment(payment, user=regular_user)

        # المشرف ينجح
        success = PaymentManagementService.delete_payment(payment, user=admin)
        assert success is True
