from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from django.urls import reverse

from .models import WorkOrder
from client.models import Customer, CustomerPayment
from core.models import SystemModule
from sale.models import Sale, Quotation
from purchase.models import Purchase
from financial.models import ChartOfAccounts, AccountType, FinancialTransaction

User = get_user_model()


class WorkOrderTests(TestCase):
    """
    سلسلة اختبارات لموديول أوامر الشغل ومركز التكلفة
    """

    def setUp(self):
        # 1. مستخدم تجريبي
        self.user = User.objects.create_superuser(
            username="admin",
            password="adminpassword",
            email="admin@erp.com"
        )
        self.client.login(username="admin", password="adminpassword")

        # 2. عميل تجريبي
        self.customer = Customer.objects.create(
            name="عميل تجريبي للشغل",
            code="CUSTWO01",
            email="wo@test.com",
            client_type="individual"
        )

        # 3. موديول أوامر الشغل
        self.module, _ = SystemModule.objects.get_or_create(
            code="work_orders",
            defaults={"name_ar": "أوامر الشغل", "name_en": "Work Orders", "is_enabled": True}
        )
        self.module.is_enabled = True
        self.module.save()

    def test_work_order_creation_and_serial(self):
        """
        اختبار إنشاء أمر الشغل وتوليد الرقم المسلسل تلقائياً
        """
        wo = WorkOrder.objects.create(
            customer=self.customer,
            start_date=timezone.now().date(),
            delivery_date=timezone.now().date() + timezone.timedelta(days=7),
            estimated_cost=Decimal("15000.00"),
            created_by=self.user
        )
        current_year = timezone.now().year
        self.assertTrue(wo.number.startswith(f"WO-{current_year}-"))
        self.assertEqual(wo.status, "pending")
        self.assertEqual(wo.estimated_cost, Decimal("15000.00"))

    def test_work_order_toggle_protection(self):
        """
        اختبار حماية مسارات موديول أوامر الشغل عند إلغاء التفعيل
        """
        # إنشاء أمر شغل
        wo = WorkOrder.objects.create(
            customer=self.customer,
            created_by=self.user
        )

        # تعطيل الموديول
        self.module.is_enabled = False
        self.module.save()

        # محاولة الوصول لصفحة تفاصيل أمر الشغل
        response = self.client.get(reverse("work_order:work_order_detail", kwargs={"pk": wo.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "غير مفعل")

        # إعادة تفعيل الموديول
        self.module.is_enabled = True
        self.module.save()
        response = self.client.get(reverse("work_order:work_order_detail", kwargs={"pk": wo.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "غير مفعل")

    def test_work_order_profitability_calculations(self):
        """
        اختبار لوحة معلومات أمر الشغل وحسابات الأرباح والإيرادات والتكاليف
        """
        from product.models import Warehouse

        # 1. إنشاء مخزن
        warehouse = Warehouse.objects.create(name="مخزن تجريبي", is_active=True)

        # 2. إنشاء أمر شغل
        wo = WorkOrder.objects.create(
            customer=self.customer,
            estimated_cost=Decimal("2000.00"),
            created_by=self.user
        )

        # 3. ربط عرض سعر
        quotation = Quotation.objects.create(
            customer=self.customer,
            date=timezone.now().date(),
            valid_until=timezone.now().date() + timezone.timedelta(days=7),
            discount=Decimal("0.00"),
            tax=Decimal("0.00"),
            total=Decimal("5000.00"),
            work_order=wo,
            created_by=self.user
        )

        # 4. ربط فاتورة مبيعات مؤكدة (إيراد)
        sale = Sale.objects.create(
            customer=self.customer,
            warehouse=warehouse,
            date=timezone.now().date(),
            subtotal=Decimal("4000.00"),
            total=Decimal("4000.00"),
            status="confirmed",
            payment_method="credit",
            work_order=wo,
            created_by=self.user
        )

        # 5. ربط فاتورة مشتريات مؤكدة (تكلفة)
        from supplier.models import Supplier, SupplierType
        supplier_type, _ = SupplierType.objects.get_or_create(
            code="general",
            defaults={"name": "عام", "is_active": True}
        )
        supplier = Supplier.objects.create(
            name="مورد تجريبي",
            code="SUPPWO01",
            primary_type=supplier_type
        )
        purchase = Purchase.objects.create(
            supplier=supplier,
            warehouse=warehouse,
            date=timezone.now().date(),
            subtotal=Decimal("1500.00"),
            total=Decimal("1500.00"),
            status="confirmed",
            payment_status="unpaid",
            work_order=wo,
            created_by=self.user
        )

        # 6. طلب صفحة التفاصيل والتحقق من الحسابات المالية
        response = self.client.get(reverse("work_order:work_order_detail", kwargs={"pk": wo.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["sales_total"], Decimal("4000.00"))
        self.assertEqual(response.context["purchases_total"], Decimal("1500.00"))
        self.assertEqual(response.context["total_revenue"], Decimal("4000.00"))
        self.assertEqual(response.context["total_cost"], Decimal("1500.00"))
        self.assertEqual(response.context["net_profit"], Decimal("2500.00"))
        self.assertEqual(response.context["profit_margin"], Decimal("62.50"))
