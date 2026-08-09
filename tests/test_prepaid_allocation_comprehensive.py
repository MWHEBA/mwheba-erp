from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.test import TestCase

from client.models import Customer, CustomerPayment, CustomerTransaction, CustomerAllocationAudit
from client.services.customer_allocation_audit_service import CustomerAllocationAuditService
from supplier.models import Supplier, SupplierTransaction, SupplierType, SupplierAdvancePayment, SupplierAllocationAudit
from supplier.services.supplier_allocation_service import SupplierAllocationService
from sale.models import Sale, SalePayment
from purchase.models import Purchase
from purchase.models.payment import PurchasePayment
from product.models import Product, Category, Unit

User = get_user_model()


class PrepaidAllocationSystemTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser_alloc", password="password123")
        self.category = Category.objects.create(name="عام")
        self.unit = Unit.objects.create(name="قطعة")
        self.product = Product.objects.create(
            name="منتج تجريبي",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal("10.00"),
            selling_price=Decimal("15.00"),
            created_by=self.user
        )

        # إنشاء عميل ومورد
        self.customer = Customer.objects.create(
            name="عميل التخصيص الاختباري",
            code="CUST-ALLOC-001",
            created_by=self.user
        )

        supplier_type = SupplierType.objects.create(name="نوع تجريبي", code="SUPP_TYPE_TEST")
        self.supplier = Supplier.objects.create(
            name="مورد التخصيص الاختباري",
            code="SUPP-ALLOC-001",
            primary_type=supplier_type,
            created_by=self.user
        )
        from product.models import Warehouse
        self.warehouse = Warehouse.objects.create(name="مخزن رئيسي", code="WH-MAIN")

    def test_customer_payment_clean_validation_tolerance(self):
        """التحقق من رفع القيد في clean() للدفعات المخصومة من الرصيد المسبق للعميل"""
        sale = Sale.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            number="INV-ALLOC-001",
            date=timezone.now().date(),
            subtotal=Decimal("1000.00"),
            total=Decimal("1000.00"),
            created_by=self.user
        )

        sp = SalePayment(
            sale=sale,
            amount=Decimal("500.00"),
            payment_date=timezone.now().date(),
            payment_method="prepaid_balance",
            source_type="PREPAID_BALANCE",
            created_by=self.user
        )
        sp.full_clean()
        sp.save()
        self.assertIsNotNone(sp.pk)
        self.assertIn("خصم من الرصيد المسبق", sp.source_display_info)

    def test_supplier_payment_clean_validation_tolerance(self):
        """التحقق من رفع القيد في clean() للدفعات المخصومة من الرصيد المسبق للمورد"""
        purchase = Purchase.objects.create(
            supplier=self.supplier,
            warehouse=self.warehouse,
            number="BILL-ALLOC-001",
            date=timezone.now().date(),
            subtotal=Decimal("2000.00"),
            total=Decimal("2000.00"),
            created_by=self.user
        )

        pp = PurchasePayment(
            purchase=purchase,
            amount=Decimal("800.00"),
            payment_date=timezone.now().date(),
            payment_method="prepaid_balance",
            source_type="PREPAID_BALANCE",
            created_by=self.user
        )
        pp.full_clean()
        pp.save()
        self.assertIsNotNone(pp.pk)
        self.assertIn("رصيد المورد المسبق", pp.source_display_info)

    def test_customer_prepaid_allocation_flow(self):
        """اختبار دورة تخصيص دفعة مقدمة للعميل على فاتورة مبيعات واستثارة التحديثات"""
        cp = CustomerPayment.objects.create(
            customer=self.customer,
            amount=Decimal("3000.00"),
            payment_date=timezone.now().date(),
            payment_method="cash",
            created_by=self.user
        )

        sale = Sale.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            number="INV-ALLOC-002",
            date=timezone.now().date(),
            subtotal=Decimal("2000.00"),
            total=Decimal("2000.00"),
            created_by=self.user
        )

        audit = CustomerAllocationAuditService.allocate_customer_prepaid_balance_to_sale(
            sale=sale,
            amount_to_allocate=Decimal("2000.00"),
            user=self.user
        )

        self.assertIsNotNone(audit)
        self.assertEqual(audit.allocated_amount, Decimal("2000.00"))
        self.assertIsNotNone(audit.evidence_hash)

        sale.refresh_from_db()
        self.assertEqual(sale.amount_paid, Decimal("2000.00"))
        self.assertEqual(sale.payment_status, "paid")

    def test_supplier_advance_allocation_flow(self):
        """اختبار دورة تخصيص دفعة مقدمة للمورد على فاتورة مشتريات واستثارة التحديثات"""
        adv = SupplierAdvancePayment.objects.create(
            supplier=self.supplier,
            amount=Decimal("5000.00"),
            payment_date=timezone.now().date(),
            payment_method="bank_transfer",
            created_by=self.user
        )

        purchase = Purchase.objects.create(
            supplier=self.supplier,
            warehouse=self.warehouse,
            number="BILL-ALLOC-002",
            date=timezone.now().date(),
            subtotal=Decimal("3500.00"),
            total=Decimal("3500.00"),
            created_by=self.user
        )

        audit = SupplierAllocationService.allocate_advance_to_purchase_bill(
            purchase=purchase,
            amount_to_allocate=Decimal("3500.00"),
            user=self.user
        )

        self.assertIsNotNone(audit)
        self.assertEqual(audit.allocated_amount, Decimal("3500.00"))
        self.assertIsNotNone(audit.evidence_hash)

        adv.refresh_from_db()
        self.assertEqual(adv.allocated_amount, Decimal("3500.00"))
        self.assertEqual(adv.remaining_amount, Decimal("1500.00"))

        purchase.refresh_from_db()
        self.assertEqual(purchase.amount_paid, Decimal("3500.00"))
        self.assertEqual(purchase.payment_status, "paid")

    def test_supplier_advance_creation_and_bulk_allocation(self):
        """اختبار إنشاء دفعة مقدمة للمورد والتوزيع الجماعي التلقائي عبر الفواتير"""
        adv = SupplierAllocationService.create_supplier_advance_payment(
            supplier_id=self.supplier.id,
            amount=Decimal("10000.00"),
            payment_date=timezone.now().date(),
            payment_method="cash",
            notes="دفعة مقدمة لاختبار التوزيع الجماعي",
            user=self.user
        )
        self.assertEqual(adv.amount, Decimal("10000.00"))
        self.assertEqual(self.supplier.available_prepaid_balance, Decimal("10000.00"))

        p1 = Purchase.objects.create(
            supplier=self.supplier, warehouse=self.warehouse, number="BILL-BULK-001",
            date=timezone.now().date(), status="posted", subtotal=Decimal("4000.00"), total=Decimal("4000.00"), created_by=self.user
        )
        p2 = Purchase.objects.create(
            supplier=self.supplier, warehouse=self.warehouse, number="BILL-BULK-002",
            date=timezone.now().date(), status="posted", subtotal=Decimal("3000.00"), total=Decimal("3000.00"), created_by=self.user
        )

        allocations = {p1.id: Decimal("4000.00"), p2.id: Decimal("3000.00")}
        audits = SupplierAllocationService.allocate_prepaid_bulk(
            supplier_id=self.supplier.id,
            allocations_dict=allocations,
            user=self.user
        )

        self.assertEqual(len(audits), 2)
        total_allocated = sum(a.allocated_amount for a in audits)
        self.assertEqual(total_allocated, Decimal("7000.00"))

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.payment_status, "paid")
        self.assertEqual(p2.payment_status, "paid")
        self.assertEqual(self.supplier.available_prepaid_balance, Decimal("3000.00"))

    def test_customer_advance_creation_and_bulk_allocation(self):
        """اختبار تحصيل رصيد مسبق للعميل والتوزيع الجماعي التلقائي عبر الفواتير"""
        pay = CustomerAllocationAuditService.create_customer_advance_payment(
            customer_id=self.customer.id,
            amount=Decimal("15000.00"),
            payment_date=timezone.now().date(),
            payment_method="bank_transfer",
            notes="دفعة مقدمة للعميل لاختبار التوزيع الجماعي",
            user=self.user
        )
        self.assertEqual(pay.amount, Decimal("15000.00"))
        self.assertEqual(self.customer.available_prepaid_balance, Decimal("15000.00"))

        s1 = Sale.objects.create(
            customer=self.customer, warehouse=self.warehouse, number="INV-BULK-001",
            date=timezone.now().date(), status="posted", subtotal=Decimal("6000.00"), total=Decimal("6000.00"), created_by=self.user
        )
        s2 = Sale.objects.create(
            customer=self.customer, warehouse=self.warehouse, number="INV-BULK-002",
            date=timezone.now().date(), status="posted", subtotal=Decimal("5000.00"), total=Decimal("5000.00"), created_by=self.user
        )

        allocations = {s1.id: Decimal("6000.00"), s2.id: Decimal("5000.00")}
        audits = CustomerAllocationAuditService.allocate_prepaid_bulk(
            customer_id=self.customer.id,
            allocations_dict=allocations,
            user=self.user
        )

        self.assertEqual(len(audits), 2)
        total_allocated = sum(a.allocated_amount for a in audits)
        self.assertEqual(total_allocated, Decimal("11000.00"))

        s1.refresh_from_db()
        s2.refresh_from_db()
        self.assertEqual(s1.payment_status, "paid")
        self.assertEqual(s2.payment_status, "paid")
        self.assertEqual(self.customer.available_prepaid_balance, Decimal("4000.00"))

