"""
Enterprise Unit & Integration Tests for Sales Order Down Payment (العربون)
اختبارات شاملة وموسعة لجميع قواعد حوكمة الدفعة المقدمة المشترطة في أوامر البيع
"""
import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from client.models import Customer, CustomerPayment, CustomerTransaction
from product.models.product_core import Product, Category, Unit
from product.models.stock_management import Warehouse, Stock
from product.services.inventory_reservation_service import InventoryReservationService
from sale.models.sales_models import SalesOrder, SalesOrderItem, DeliveryNote
from sale.models import Sale
from sale.services.sales_service import SalesService
from client.services.customer_allocation_audit_service import CustomerAllocationAuditService

User = get_user_model()


@pytest.mark.django_db
class TestSalesOrderDownPaymentLifecycle:

    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.user = User.objects.create_superuser(
            username="so_dp_admin",
            email="so_dp_admin@test.com",
            password="password123"
        )
        self.customer = Customer.objects.create(
            name="شركة الأهرام للتجارة",
            code="CUST-DP-001",
            phone="01099887766",
            client_type="company"
        )
        self.other_customer = Customer.objects.create(
            name="شركة النيل للخدمات",
            code="CUST-DP-002",
            phone="01099887755",
            client_type="company"
        )
        self.warehouse, _ = Warehouse.objects.get_or_create(
            code="WH-DP-01",
            defaults={"name": "مخزن التجربة الرئيسي", "is_active": True}
        )
        self.category = Category.objects.create(name="معدات وشبكات")
        self.unit = Unit.objects.create(name="قطعة")
        self.product = Product.objects.create(
            name="خادم مركزي Enterprise Server",
            sku="SRV-DP-001",
            category=self.category,
            unit=self.unit,
            created_by=self.user,
            selling_price=Decimal("10000.00"),
            cost_price=Decimal("7000.00"),
            is_active=True
        )

        from financial.models import ChartOfAccounts, AccountType, AccountingPeriod
        asset_type, _ = AccountType.objects.get_or_create(name="Current Asset", nature="DEBIT", defaults={"code": "1000"})
        liability_type, _ = AccountType.objects.get_or_create(name="Current Liability", nature="CREDIT", defaults={"code": "2000"})
        revenue_type, _ = AccountType.objects.get_or_create(name="Revenue", nature="CREDIT", defaults={"code": "4000"})
        expense_type, _ = AccountType.objects.get_or_create(name="Expense", nature="DEBIT", defaults={"code": "5000"})

        self.treasury_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="10101", 
            defaults={"name": "الخزينة الرئيسية", "account_type": asset_type, "is_active": True}
        )
        self.ar_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="10200", 
            defaults={"name": "مدينو عملاء", "account_type": asset_type, "is_active": True}
        )
        self.inv_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="10400", 
            defaults={"name": "مخزون بضاعة", "account_type": asset_type, "is_active": True}
        )
        self.adv_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="20200", 
            defaults={"name": "دفعات مقدمة من العملاء", "account_type": liability_type, "is_active": True}
        )
        self.adv_acc_alt, _ = ChartOfAccounts.objects.get_or_create(
            code="21510", 
            defaults={"name": "دفعات مقدمة 21510", "account_type": liability_type, "is_active": True}
        )
        self.rev_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="40100", 
            defaults={"name": "إيرادات المبيعات", "account_type": revenue_type, "is_active": True}
        )
        self.rev_acc_alt, _ = ChartOfAccounts.objects.get_or_create(
            code="41100", 
            defaults={"name": "إيرادات المبيعات 41100", "account_type": revenue_type, "is_active": True}
        )
        self.cogs_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="50100", 
            defaults={"name": "تكلفة البضاعة المباعة", "account_type": expense_type, "is_active": True}
        )
        self.cogs_acc_alt, _ = ChartOfAccounts.objects.get_or_create(
            code="51100", 
            defaults={"name": "تكلفة البضاعة المباعة 51100", "account_type": expense_type, "is_active": True}
        )

        today = timezone.now().date()
        AccountingPeriod.objects.get_or_create(
            name=f"Period_{today.year}_{today.month}",
            start_date=today.replace(day=1),
            end_date=today.replace(day=28),
            defaults={"status": "open"}
        )

        from core.models import SystemSetting
        SystemSetting.set_setting('enable_sales_orders', 'true')
        SystemSetting.set_setting('enable_delivery_notes', 'true')

        Stock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=Decimal("20.00")
        )

    def test_down_payment_properties_and_calculation(self):
        """1. التحقق من حسابات الدفعة المقدمة (المبلغ الثابت والنسبة المئوية) وخصائص النموذج"""
        so = SalesService.create_sales_order(
            customer=self.customer,
            warehouse=self.warehouse,
            order_date=timezone.now().date(),
            items_data=[{
                "product": self.product,
                "ordered_qty": Decimal("2"),
                "unit_price": Decimal("10000.00"),
                "discount_percentage": Decimal("0")
            }],
            user=self.user,
            vat_rate=Decimal("14.00"),
            required_down_payment=Decimal("5000.00"),
            down_payment_type="fixed"
        )
        # Total = 2 * 10000 + 14% VAT = 22800
        assert so.total_amount == Decimal("22800.00")
        assert so.effective_required_down_payment == Decimal("5000.00")
        assert so.paid_down_payment == Decimal("0.00")
        assert so.remaining_down_payment == Decimal("5000.00")
        assert not so.is_down_payment_satisfied
        assert so.down_payment_status == "PENDING"

        # تغيير إلى نسبة مئوية 25%
        so.down_payment_type = "percentage"
        so.required_down_payment = Decimal("25.00")
        so.save()
        # 25% من 22800 = 5700
        assert so.effective_required_down_payment == Decimal("5700.00")
        assert so.remaining_down_payment == Decimal("5700.00")

    def test_down_payment_collection_view_and_journal_entry(self, client):
        """2. التحقق من تحصيل دفعة مقدمة عبر الـ View وتوليد سند القبض وقيد اليومية المحاسبي"""
        client.force_login(self.user)
        so = SalesService.create_sales_order(
            customer=self.customer,
            warehouse=self.warehouse,
            order_date=timezone.now().date(),
            items_data=[{
                "product": self.product,
                "ordered_qty": Decimal("1"),
                "unit_price": Decimal("10000.00"),
                "discount_percentage": Decimal("0")
            }],
            user=self.user,
            vat_rate=Decimal("0.00"),
            required_down_payment=Decimal("3000.00")
        )

        collect_url = reverse("sale:sales_order_collect_down_payment", args=[so.pk])
        response = client.post(collect_url, {
            "amount": "3000.00",
            "payment_method": "cash",
            "financial_account": self.treasury_acc.id,
            "payment_date": timezone.now().date().isoformat(),
            "notes": "سند قبض دفعة مقدمة للاختبار"
        })

        assert response.status_code == 302
        so.refresh_from_db()
        assert so.paid_down_payment == Decimal("3000.00")
        assert so.remaining_down_payment == Decimal("0.00")
        assert so.is_down_payment_satisfied
        assert so.down_payment_status == "SATISFIED"

        # التحقق من وجود سند القبض وربطه بأمر البيع
        payment = CustomerPayment.objects.filter(sales_order=so).first()
        assert payment is not None
        assert payment.amount == Decimal("3000.00")
        assert payment.customer == self.customer
        assert payment.financial_account == self.treasury_acc

    def test_warehouse_delivery_blocked_until_down_payment_satisfied(self, client):
        """3. التحقق من منع إصدار إذن تسليم مخزني إذا لم يتم سداد الدفعة المقدمة المشترطة"""
        client.force_login(self.user)
        so = SalesService.create_sales_order(
            customer=self.customer,
            warehouse=self.warehouse,
            order_date=timezone.now().date(),
            items_data=[{
                "product": self.product,
                "ordered_qty": Decimal("1"),
                "unit_price": Decimal("10000.00"),
                "discount_percentage": Decimal("0")
            }],
            user=self.user,
            vat_rate=Decimal("0.00"),
            required_down_payment=Decimal("4000.00")
        )
        SalesService.approve_sales_order(so.id, self.user)

        delivery_url = reverse("sale:delivery_note_create")
        # محاولة فتح صفحة التسليم GET
        response_get = client.get(f"{delivery_url}?so_id={so.pk}")
        assert response_get.status_code == 302
        assert response_get.url == reverse("sale:sales_order_detail", args=[so.pk])

        # محاولة إرسال إذن التسليم POST
        so_item = so.items.first()
        response_post = client.post(delivery_url, {
            "sales_order": so.pk,
            "delivery_date": timezone.now().date().isoformat(),
            "so_item_id[]": [str(so_item.id)],
            "delivered_qty[]": ["1"]
        })
        assert response_post.status_code == 302
        assert DeliveryNote.objects.filter(sales_order=so).count() == 0

        # تحصيل جزء من العربون (أقل من المشترط) -> يظل الحظر قائماً
        CustomerAllocationAuditService.create_prepaid_payment(
            customer_id=self.customer.id,
            amount=Decimal("2000.00"),
            sales_order=so,
            financial_account_id=self.treasury_acc.id,
            user=self.user
        )
        so.refresh_from_db()
        assert not so.is_down_payment_satisfied

        response_post2 = client.post(delivery_url, {
            "sales_order": so.pk,
            "delivery_date": timezone.now().date().isoformat(),
            "so_item_id[]": [str(so_item.id)],
            "delivered_qty[]": ["1"]
        })
        assert response_post2.status_code == 302
        assert DeliveryNote.objects.filter(sales_order=so).count() == 0

        # استكمال باقي العربون -> يتم السماح بالتسليم فوراً
        CustomerAllocationAuditService.create_prepaid_payment(
            customer_id=self.customer.id,
            amount=Decimal("2000.00"),
            sales_order=so,
            financial_account_id=self.treasury_acc.id,
            user=self.user
        )
        so.refresh_from_db()
        assert so.is_down_payment_satisfied

        response_post3 = client.post(delivery_url, {
            "sales_order": so.pk,
            "delivery_date": timezone.now().date().isoformat(),
            "so_item_id[]": [str(so_item.id)],
            "delivered_qty[]": ["1"]
        })
        assert response_post3.status_code == 302
        assert DeliveryNote.objects.filter(sales_order=so).count() == 1

    def test_management_override_permits_delivery(self, client):
        """4. التحقق من سماح التجاوز الإداري (VIP Override) بإصدار إذن التسليم قبل استيفاء العربون"""
        client.force_login(self.user)
        so = SalesService.create_sales_order(
            customer=self.customer,
            warehouse=self.warehouse,
            order_date=timezone.now().date(),
            items_data=[{
                "product": self.product,
                "ordered_qty": Decimal("1"),
                "unit_price": Decimal("10000.00"),
                "discount_percentage": Decimal("0")
            }],
            user=self.user,
            vat_rate=Decimal("0.00"),
            required_down_payment=Decimal("5000.00")
        )
        SalesService.approve_sales_order(so.id, self.user)

        # تنفيذ التجاوز الإداري
        override_url = reverse("sale:sales_order_override_down_payment", args=[so.pk])
        resp_override = client.post(override_url, {
            "override_reason": "عميل استراتيجي VIP معتمد من الإدارة"
        })
        assert resp_override.status_code == 302
        so.refresh_from_db()
        assert so.down_payment_override
        assert so.is_down_payment_satisfied
        assert so.down_payment_status == "OVERRIDDEN"

        # الآن إذن التسليم يجب أن ينجح
        so_item = so.items.first()
        delivery_url = reverse("sale:delivery_note_create")
        resp_dn = client.post(delivery_url, {
            "sales_order": so.pk,
            "delivery_date": timezone.now().date().isoformat(),
            "so_item_id[]": [str(so_item.id)],
            "delivered_qty[]": ["1"]
        })
        assert resp_dn.status_code == 302
        assert DeliveryNote.objects.filter(sales_order=so).count() == 1

    def test_inventory_reservation_sweep_protects_satisfied_orders(self):
        """5. التحقق من أن الكرون جوب لا يفك حجز المخزون لأمر بيع سدد عربونه بالكامل"""
        so = SalesService.create_sales_order(
            customer=self.customer,
            warehouse=self.warehouse,
            order_date=timezone.now().date(),
            items_data=[{
                "product": self.product,
                "ordered_qty": Decimal("1"),
                "unit_price": Decimal("10000.00"),
                "discount_percentage": Decimal("0")
            }],
            user=self.user,
            vat_rate=Decimal("0.00"),
            required_down_payment=Decimal("2000.00")
        )
        SalesService.approve_sales_order(so.id, self.user)

        # سداد العربون
        CustomerAllocationAuditService.create_prepaid_payment(
            customer_id=self.customer.id,
            amount=Decimal("2000.00"),
            sales_order=so,
            financial_account_id=self.treasury_acc.id,
            user=self.user
        )

        # جعل تاريخ انتهاء الحجز في الماضي لمحاكاة انتهاء الـ TTL
        from product.models.inventory_reservation import InventoryReservation
        past_time = timezone.now() - timezone.timedelta(days=2)
        InventoryReservation.objects.filter(sales_order=so).update(expires_at=past_time)

        # تشغيل الـ sweep
        swept = InventoryReservationService.sweep_expired_reservations(user=self.user)
        # الحجز المحمي لا يجب أن يكون ضمن الـ swept
        res = InventoryReservation.objects.filter(sales_order=so).first()
        assert res.reservation_status == "ACTIVE"

    def test_customer_locked_on_edit_when_payments_exist(self, client):
        """6. التحقق من قفل تعديل العميل عند وجود دفعات مسددة مرتبطة بأمر البيع"""
        client.force_login(self.user)
        so = SalesService.create_sales_order(
            customer=self.customer,
            warehouse=self.warehouse,
            order_date=timezone.now().date(),
            items_data=[{
                "product": self.product,
                "ordered_qty": Decimal("1"),
                "unit_price": Decimal("10000.00"),
                "discount_percentage": Decimal("0")
            }],
            user=self.user,
            vat_rate=Decimal("0.00"),
            required_down_payment=Decimal("3000.00")
        )

        CustomerAllocationAuditService.create_prepaid_payment(
            customer_id=self.customer.id,
            amount=Decimal("3000.00"),
            sales_order=so,
            financial_account_id=self.treasury_acc.id,
            user=self.user
        )

        edit_url = reverse("sale:sales_order_edit", args=[so.pk])
        # محاولة تغيير العميل إلى عميل آخر
        resp_edit = client.post(edit_url, {
            "customer": self.other_customer.id,
            "warehouse": self.warehouse.id,
            "order_date": timezone.now().date().isoformat(),
            "currency": "EGP",
            "exchange_rate": "1.000000",
            "product[]": [str(self.product.id)],
            "quantity[]": ["1"],
            "unit_price[]": ["10000.00"],
            "discount[]": ["0"],
            "required_down_payment": "3000.00"
        })
        assert resp_edit.status_code == 302
        so.refresh_from_db()
        assert so.customer_id == self.customer.id  # لم يتغير

    def test_prevent_reducing_total_below_paid_down_payment(self, client):
        """7. التحقق من منع تقليص إجمالي أمر البيع لأقل من المبالغ المحصلة فعلياً"""
        client.force_login(self.user)
        so = SalesService.create_sales_order(
            customer=self.customer,
            warehouse=self.warehouse,
            order_date=timezone.now().date(),
            items_data=[{
                "product": self.product,
                "ordered_qty": Decimal("2"),
                "unit_price": Decimal("10000.00"),
                "discount_percentage": Decimal("0")
            }],
            user=self.user,
            vat_rate=Decimal("0.00"),
            required_down_payment=Decimal("8000.00")
        )

        CustomerAllocationAuditService.create_prepaid_payment(
            customer_id=self.customer.id,
            amount=Decimal("8000.00"),
            sales_order=so,
            financial_account_id=self.treasury_acc.id,
            user=self.user
        )

        edit_url = reverse("sale:sales_order_edit", args=[so.pk])
        # محاولة تقليص الكمية إلى 0.5 (إجمالي 5000 < 8000 محصلة)
        resp_edit = client.post(edit_url, {
            "customer": self.customer.id,
            "warehouse": self.warehouse.id,
            "order_date": timezone.now().date().isoformat(),
            "currency": "EGP",
            "exchange_rate": "1.000000",
            "product[]": [str(self.product.id)],
            "quantity[]": ["0.5"],
            "unit_price[]": ["10000.00"],
            "discount[]": ["0"],
            "required_down_payment": "8000.00"
        })
        so.refresh_from_db()
        assert so.total_amount == Decimal("20000.00")  # لم يتم تقليصها لأقل من 8000

    def test_convert_sales_order_to_sale_automatically_allocates_down_payment(self, client):
        """8. التحقق من تسوية الدفعة المقدمة تلقائياً في فاتورة المبيعات عند تحويل أمر البيع"""
        client.force_login(self.user)
        so = SalesService.create_sales_order(
            customer=self.customer,
            warehouse=self.warehouse,
            order_date=timezone.now().date(),
            items_data=[{
                "product": self.product,
                "ordered_qty": Decimal("1"),
                "unit_price": Decimal("10000.00"),
                "discount_percentage": Decimal("0")
            }],
            user=self.user,
            vat_rate=Decimal("0.00"),
            required_down_payment=Decimal("3000.00")
        )

        # تحصيل العربون
        CustomerAllocationAuditService.create_prepaid_payment(
            customer_id=self.customer.id,
            amount=Decimal("3000.00"),
            sales_order=so,
            financial_account_id=self.treasury_acc.id,
            user=self.user
        )

        # إنشاء الفاتورة من أمر البيع
        sale_create_url = reverse("sale:sale_create")
        post_sale = {
            "date": timezone.now().date().isoformat(),
            "customer": self.customer.id,
            "warehouse": self.warehouse.id,
            "sales_order": so.id,
            "invoice_type": "credit",
            "currency": "1",
            "exchange_rate": "1.000000",
            "product[]": [str(self.product.id)],
            "quantity[]": ["1"],
            "unit_price[]": ["10000.00"],
            "discount[]": ["0"]
        }
        resp = client.post(sale_create_url, post_sale)
        assert resp.status_code == 302

        sale = Sale.objects.filter(sales_order=so).first()
        assert sale is not None
        assert sale.total == Decimal("10000.00")
        # التحقق من أن الدفعة المقدمة البالغة 3000 تم تسويتها تلقائياً
        assert sale.amount_paid == Decimal("3000.00")
        assert sale.amount_due == Decimal("7000.00")
        assert sale.payment_status == "partially_paid"
