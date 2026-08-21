import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from purchase.models.procurement_models import PurchaseOrder, PurchaseOrderItem, GoodsReceivedNote
from supplier.models import Supplier
from product.models import Warehouse, Product, Unit
from financial.models import ChartOfAccounts, AccountType

User = get_user_model()


@pytest.mark.django_db
class TestPurchaseOrderLifecycle:
    """اختبارات دورة حياة أوامر الشراء المحوكمة"""

    @pytest.fixture(autouse=True)
    def setup_po_data(self, db):
        self.user = User.objects.create_superuser(
            username="po_admin",
            email="po_admin@mwheba.com",
            password="password123"
        )

        # تجهيز الحسابات
        self.asset_type, _ = AccountType.objects.get_or_create(name="أصول", code="ASSET", category="asset")
        self.liab_type, _ = AccountType.objects.get_or_create(name="خصوم", code="LIAB", category="liability")

        self.inv_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="11310",
            defaults={"name": "مخزون خامات", "account_type": self.asset_type, "is_active": True}
        )
        self.grni_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="21210",
            defaults={"name": "وسيط بضاعة غير مفوترة GRNI", "account_type": self.liab_type, "is_active": True}
        )

        from financial.models import Currency
        self.currency, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True, "is_active": True})

        from product.models import Category
        self.category = Category.objects.create(name="خامات ومعادن")
        self.supplier = Supplier.objects.create(name="شركة التوريدات العالمية", is_active=True)
        self.warehouse = Warehouse.objects.create(name="مستودع الخامات الرئيسي", is_active=True)
        self.unit = Unit.objects.create(name="قطعة", symbol="PCS")

        self.product = Product.objects.create(
            name="حديد تسليح 12 مم",
            category=self.category,
            sku="STL-12",
            unit=self.unit,
            cost_price=Decimal("45.00"),
            selling_price=Decimal("60.00"),
            created_by=self.user,
            is_active=True
        )

    def test_po_create_get_view(self, client):
        client.force_login(self.user)
        resp = client.get(reverse("purchase:po_create"))
        assert resp.status_code == 200
        assert "إنشاء أمر شراء جديد".encode() in resp.content

    def test_po_create_and_detail_view(self, client):
        client.force_login(self.user)

        # 1. إنشاء أمر شراء
        post_data = {
            "supplier": self.supplier.id,
            "warehouse": self.warehouse.id,
            "order_date": timezone.now().date().strftime("%Y-%m-%d"),
            "delivery_due_date": (timezone.now().date() + timezone.timedelta(days=15)).strftime("%Y-%m-%d"),
            "currency": self.currency.id,
            "exchange_rate": "1.000000",
            "payment_terms": "سداد 30 يوم من الاستلام",
            "product[]": [self.product.id],
            "quantity[]": ["100.0000"],
            "unit_price[]": ["50.00"],
            "unit[]": [self.unit.id],
        }

        resp = client.post(reverse("purchase:po_create"), post_data)
        assert resp.status_code == 302

        po = PurchaseOrder.objects.filter(supplier=self.supplier).first()
        assert po is not None
        assert po.status == "DRAFT"
        assert po.total_amount == Decimal("5000.00")
        assert po.items.count() == 1

        # 2. فحص صفحة التفاصيل
        detail_resp = client.get(reverse("purchase:po_detail", kwargs={"pk": po.id}))
        assert detail_resp.status_code == 200
        assert po.order_number.encode() in detail_resp.content

    def test_po_approval_and_short_close_workflow(self, client):
        client.force_login(self.user)

        po = PurchaseOrder.objects.create(
            order_number="PO-TEST-001",
            supplier=self.supplier,
            warehouse=self.warehouse,
            currency=self.currency,
            order_date=timezone.now().date(),
            status="DRAFT",
            total_amount=Decimal("1000.00"),
            functional_amount=Decimal("1000.00"),
            created_by=self.user
        )
        PurchaseOrderItem.objects.create(
            purchase_order=po,
            product=self.product,
            unit=self.unit,
            ordered_qty=Decimal("20.0000"),
            unit_price=Decimal("50.00"),
            total_price=Decimal("1000.00")
        )

        # تقديم للاعتماد
        submit_resp = client.post(reverse("purchase:po_submit", kwargs={"pk": po.id}))
        assert submit_resp.status_code == 302
        po.refresh_from_db()
        assert po.status == "SUBMITTED"

        # اعتماد
        approve_resp = client.post(reverse("purchase:po_approve", kwargs={"pk": po.id}))
        assert approve_resp.status_code == 302
        po.refresh_from_db()
        assert po.status == "APPROVED"
        assert po.approved_by == self.user

        # إغلاق مبكر
        close_resp = client.post(
            reverse("purchase:po_short_close", kwargs={"pk": po.id}),
            {"reason": "اعتذار المورد عن باقي الكمية"}
        )
        assert close_resp.status_code == 302
        po.refresh_from_db()
        assert po.status == "FULLY_RECEIVED"

    def test_po_print_view(self, client):
        client.force_login(self.user)

        po = PurchaseOrder.objects.create(
            order_number="PO-TEST-PRINT",
            supplier=self.supplier,
            warehouse=self.warehouse,
            currency=self.currency,
            order_date=timezone.now().date(),
            status="APPROVED",
            total_amount=Decimal("2500.00"),
            functional_amount=Decimal("2500.00"),
            created_by=self.user
        )

        resp = client.get(reverse("purchase:po_print", kwargs={"pk": po.id}))
        assert resp.status_code == 200

    def test_po_duplicate_and_delete_workflow(self, client):
        client.force_login(self.user)

        # 1. إنشاء أمر للشراء
        po = PurchaseOrder.objects.create(
            order_number="PO-TEST-DUP",
            supplier=self.supplier,
            warehouse=self.warehouse,
            currency=self.currency,
            order_date=timezone.now().date(),
            status="DRAFT",
            total_amount=Decimal("3000.00"),
            functional_amount=Decimal("3000.00"),
            created_by=self.user
        )
        PurchaseOrderItem.objects.create(
            purchase_order=po,
            product=self.product,
            unit=self.unit,
            ordered_qty=Decimal("60.0000"),
            unit_price=Decimal("50.00"),
            total_price=Decimal("3000.00")
        )

        # 2. تكرار أمر الشراء
        dup_resp = client.get(reverse("purchase:po_duplicate", kwargs={"pk": po.id}))
        assert dup_resp.status_code == 302
        assert f"duplicate_from={po.id}" in dup_resp.url

        create_dup_resp = client.get(dup_resp.url)
        assert create_dup_resp.status_code == 200
        assert self.supplier.name.encode() in create_dup_resp.content

        # 3. حذف أمر الشراء
        del_confirm_resp = client.get(reverse("purchase:po_delete", kwargs={"pk": po.id}))
        assert del_confirm_resp.status_code == 200

        del_resp = client.post(reverse("purchase:po_delete", kwargs={"pk": po.id}))
        assert del_resp.status_code == 302
        assert not PurchaseOrder.objects.filter(pk=po.id).exists()

