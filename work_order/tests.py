from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from django.urls import reverse

from .models import WorkOrder
from customer.models import Customer, CustomerPayment
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
            customer_type="individual"
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
        from datetime import timedelta
        wo = WorkOrder.objects.create(
            customer=self.customer,
            start_date=timezone.now().date(),
            delivery_date=timezone.now().date() + timedelta(days=7),
            estimated_cost=Decimal("15000.00"),
            created_by=self.user
        )
        current_year = timezone.now().year
        self.assertTrue(wo.number.startswith("WO"))
        self.assertIn(str(current_year)[-2:], wo.number)
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
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "غير مفعل", status_code=403)

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
            valid_until=timezone.now().date() + timedelta(days=7),
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

    def test_work_order_cancellation_guards(self):
        """
        اختبار قيود الحوكمة لمنع إلغاء أمر الشغل إذا ارتبطت به فواتير مؤكدة أو عمليات مالية
        """
        from product.models import Warehouse
        warehouse = Warehouse.objects.create(name="مخزن رئيسي", is_active=True)

        wo = WorkOrder.objects.create(
            customer=self.customer,
            created_by=self.user
        )

        # 1. إلغاء أمر شغل غير مرتبط بحركات -> ينجح
        url = reverse("work_order:work_order_change_status", kwargs={"pk": wo.pk})
        response = self.client.post(url, {"status": "cancelled"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        wo.refresh_from_db()
        self.assertEqual(wo.status, "cancelled")

        # إعادة فتح أمر الشغل
        response = self.client.post(url, {"status": "in_progress"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        wo.refresh_from_db()
        self.assertEqual(wo.status, "in_progress")

        # 2. ربط فاتورة مبيعات مؤكدة
        Sale.objects.create(
            customer=self.customer,
            warehouse=warehouse,
            date=timezone.now().date(),
            subtotal=Decimal("1000.00"),
            total=Decimal("1000.00"),
            status="confirmed",
            payment_method="credit",
            work_order=wo,
            created_by=self.user
        )

        # محاولة الإلغاء -> يجب أن يمنع النظام الإلغاء
        response = self.client.post(url, {"status": "cancelled"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("المستندات المرتبطة", data["message"])
        wo.refresh_from_db()
        self.assertNotEqual(wo.status, "cancelled")

    def test_work_order_api_customer_work_orders(self):
        """
        اختبار الـ API الخاص بجلب أوامر الشغل للـ Select2
        """
        wo1 = WorkOrder.objects.create(
            customer=self.customer,
            created_by=self.user
        )
        wo_cancelled = WorkOrder.objects.create(
            customer=self.customer,
            status="cancelled",
            created_by=self.user
        )

        url = reverse("work_order:api_customer_work_orders")
        response = self.client.get(url, {"customer_id": self.customer.id})
        self.assertEqual(response.status_code, 200)
        results = response.json().get("results", [])
        ids = [r["id"] for r in results]
        self.assertIn(wo1.id, ids)
        self.assertNotIn(wo_cancelled.id, ids)

    def test_work_order_quotation_and_sale_forms(self):
        """
        اختبار ربط أمر الشغل في نماذج عروض الأسعار وفواتير المبيعات
        """
        from sale.forms import SaleForm, QuotationForm
        from product.models import Warehouse
        warehouse = Warehouse.objects.create(name="مخزن رئيسي 2", is_active=True)

        wo = WorkOrder.objects.create(
            customer=self.customer,
            created_by=self.user
        )
        wo_cancelled = WorkOrder.objects.create(
            customer=self.customer,
            status="cancelled",
            created_by=self.user
        )

        # 1. التحقق من فلاتر الـ Queryset في النماذج
        sale_form = SaleForm(user=self.user)
        self.assertIn(wo, sale_form.fields["work_order"].queryset)
        self.assertNotIn(wo_cancelled, sale_form.fields["work_order"].queryset)

        quotation_form = QuotationForm()
        self.assertIn(wo, quotation_form.fields["work_order"].queryset)
        self.assertNotIn(wo_cancelled, quotation_form.fields["work_order"].queryset)

    def test_work_order_multicurrency_ias21_profit_breakdown(self):
        """
        اختبار احتساب أرباح التشغيل الحقيقية متعددة العملات IAS 21 وحسابات الحصالة
        """
        from product.models import Warehouse, Product, Unit, Category
        from financial.models import Currency, FinancialCategory, FinancialTransaction, JournalEntry, ChartOfAccounts, AccountType
        from supplier.models import Supplier, SupplierType
        from sale.models import SaleReturn, SaleReturnItem

        cat = Category.objects.create(name="مطبوعات")
        unit = Unit.objects.create(name="قطعة")
        warehouse = Warehouse.objects.create(name="مخزن مركزي", is_active=True)
        product = Product.objects.create(name="بروشور تسويقي", unit=unit, category=cat, cost_price=Decimal("50.00"), selling_price=Decimal("100.00"), created_by=self.user)

        wo = WorkOrder.objects.create(
            customer=self.customer,
            created_by=self.user
        )

        # 1. فاتورة مبيعات بالدولار USD (سعر الصرف = 50.0)
        usd_currency, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "is_functional": False, "symbol": "$"})
        
        sale = Sale.objects.create(
            customer=self.customer,
            warehouse=warehouse,
            date=timezone.now().date(),
            currency=usd_currency,
            exchange_rate=Decimal("50.000000"),
            subtotal=Decimal("200.00"),  # $200 = 10,000 EGP
            total=Decimal("200.00"),
            status="confirmed",
            payment_method="credit",
            work_order=wo,
            created_by=self.user
        )

        # 2. مرتجع مبيعات $50 = 2,500 EGP
        sale_return = SaleReturn.objects.create(
            number="RET-001",
            warehouse=warehouse,
            sale=sale,
            date=timezone.now().date(),
            subtotal=Decimal("50.00"),
            total=Decimal("50.00"),
            status="confirmed",
            created_by=self.user
        )

        # 3. فاتورة مشتريات خامات (3,000 EGP)
        supplier_type, _ = SupplierType.objects.get_or_create(code="raw_mat", defaults={"name": "مورد خامات"})
        supplier = Supplier.objects.create(name="مورد ورق", code="SUPP_PAPER", primary_type=supplier_type)
        purchase = Purchase.objects.create(
            supplier=supplier,
            warehouse=warehouse,
            date=timezone.now().date(),
            subtotal=Decimal("3000.00"),
            total=Decimal("3000.00"),
            status="confirmed",
            payment_status="unpaid",
            work_order=wo,
            created_by=self.user
        )

        # 4. مصروف مباشر (1,000 EGP)
        account_type, _ = AccountType.objects.get_or_create(code="EXP_OP", defaults={"name": "مصروفات تشغيلية", "nature": "DEBIT", "category": "EXPENSE"})
        exp_account, _ = ChartOfAccounts.objects.get_or_create(code="510999", defaults={"name": "مصروفات تشغيل مباشرة", "account_type": account_type})
        fin_cat = FinancialCategory.objects.create(name="مصروفات أوامر شغل", code="WO_EXP", default_expense_account=exp_account)
        
        je = JournalEntry.objects.create(
            reference="JE_WO_TEST",
            date=timezone.now().date(),
            entry_type="GENERAL",
            work_order=wo,
            created_by=self.user
        )
        ft = FinancialTransaction.objects.create(
            title="مصروف تشغيلي لأمر شغل",
            account=exp_account,
            transaction_type="expense",
            amount=Decimal("1000.00"),
            date=timezone.now().date(),
            status="approved",
            work_order=wo,
            journal_entry=je,
            created_by=self.user
        )

        # 5. دفعة مقدمة من العميل لحصالة أمر الشغل ($100 = 5,000 EGP)
        cp = CustomerPayment.objects.create(
            customer=self.customer,
            amount=Decimal("5000.00"),
            allocated_currency_amount_cached=Decimal("5000.00"),
            payment_date=timezone.now().date(),
            payment_method="cash",
            work_order=wo,
            created_by=self.user
        )

        # 6. فحص شاشة التفاصيل والحسابات
        response = self.client.get(reverse("work_order:work_order_detail", kwargs={"pk": wo.pk}))
        self.assertEqual(response.status_code, 200)

        # صافي الإيرادات: (200 - 50) * 50 = 7,500 EGP
        self.assertEqual(response.context["net_sales_revenue"], Decimal("7500.00"))
        # إجمالي التكاليف: 3000 (مشتريات) + 1000 (مصاريف مباشرة) = 4,000 EGP
        self.assertEqual(response.context["total_cost"], Decimal("4000.00"))
        # مجمل ربح التشغيل الحقيقي: 7,500 - 4,000 = 3,500 EGP
        self.assertEqual(response.context["net_profit"], Decimal("3500.00"))
        # الدفعات المقدمة المسددة (الحصالة): 5,000 EGP
        self.assertEqual(response.context["total_deposits"], Decimal("5000.00"))
