from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
from core.models import SystemSetting
from client.models import Customer
from product.models import Category, Unit, Product, Warehouse, Stock, SerialNumber
from sale.models import Quotation, QuotationItem, Sale
from financial.models import ChartOfAccounts, AccountType, AccountingPeriod

User = get_user_model()


class QuotationSystemTest(TestCase):
    """
    اختبارات نظام عروض الأسعار بالكامل (موديلات، فورمز، واجهات، تحويل)
    """

    def setUp(self):
        # مستخدمين وصلاحيات
        self.admin = User.objects.create_superuser(
            username="adminuser", password="adminpass123", email="admin@example.com"
        )
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )

        # تفعيل الميزة
        SystemSetting.objects.update_or_create(
            key="enable_quotations", defaults={"value": "true"}
        )
        # تفعيل الإنشاء التلقائي لحسابات العملاء
        SystemSetting.objects.update_or_create(
            key="AUTO_CREATE_CUSTOMER_ACCOUNTS", defaults={"value": "true"}
        )

        # تهيئة شجرة الحسابات والفترات المالية
        self.setup_chart_of_accounts()

        # مخزن، تصنيف، منتج، عميل
        self.warehouse = Warehouse.objects.create(
            name="مخزن رئيسي", is_active=True
        )
        self.category = Category.objects.create(
            name="تصنيف مبيعات"
        )
        self.unit = Unit.objects.create(
            name="قطعة"
        )
        self.product = Product.objects.create(
            name="منتج اختبار",
            sku="PRD001",
            category=self.category,
            unit=self.unit,
            selling_price=Decimal("100.00"),
            cost_price=Decimal("70.00"),
            is_active=True,
            created_by=self.admin
        )
        self.stock = Stock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=Decimal("50.00"),
            created_by=self.admin
        )
        self.customer = Customer.objects.create(
            name="عميل اختبار",
            phone="01234567890",
            email="customer@example.com",
            is_active=True,
            created_by=self.admin
        )

        # تسجيل دخول للمستخدم
        self.client.login(username="adminuser", password="adminpass123")

    def setup_chart_of_accounts(self):
        """تهيئة أنواع الحسابات والحسابات الرئيسية والفترة المالية المفتوحة للنظام"""
        # 1. الفترة المالية المفتوحة للسنة الحالية
        current_year = timezone.now().year
        AccountingPeriod.objects.get_or_create(
            name=f'السنة المالية {current_year}',
            start_date=timezone.datetime(current_year, 1, 1).date(),
            end_date=timezone.datetime(current_year, 12, 31).date(),
            defaults={'status': 'open'}
        )

        # 2. أرقام الفواتير وعروض الأسعار التسلسلية
        SerialNumber.objects.get_or_create(
            document_type='sale',
            year=current_year,
            defaults={'prefix': 'SALE', 'last_number': 0}
        )
        SerialNumber.objects.get_or_create(
            document_type='quotation',
            year=current_year,
            defaults={'prefix': 'QT', 'last_number': 0}
        )

        # 3. أنواع الحسابات
        asset_type, _ = AccountType.objects.get_or_create(
            code='ASSET',
            defaults={'name': 'أصول', 'nature': 'debit'}
        )
        revenue_type, _ = AccountType.objects.get_or_create(
            code='REVENUE',
            defaults={'name': 'إيرادات', 'nature': 'credit'}
        )
        expense_type, _ = AccountType.objects.get_or_create(
            code='EXPENSE',
            defaults={'name': 'مصروفات', 'nature': 'debit'}
        )
        
        # 4. الحسابات المطلوبة
        ChartOfAccounts.objects.get_or_create(
            code='10300',
            defaults={'name': 'مدينو العملاء', 'account_type': asset_type, 'is_active': True}
        )
        ChartOfAccounts.objects.get_or_create(
            code='40100',
            defaults={'name': 'إيرادات المبيعات', 'account_type': revenue_type, 'is_active': True}
        )
        ChartOfAccounts.objects.get_or_create(
            code='10400',
            defaults={'name': 'المخزون', 'account_type': asset_type, 'is_active': True}
        )
        ChartOfAccounts.objects.get_or_create(
            code='50100',
            defaults={'name': 'تكلفة البضاعة المباعة', 'account_type': expense_type, 'is_active': True}
        )
        ChartOfAccounts.objects.get_or_create(
            code='50300',
            defaults={'name': 'تكلفة البضاعة المباعة 50300', 'account_type': expense_type, 'is_active': True}
        )
        ChartOfAccounts.objects.get_or_create(
            code='2010001',
            defaults={'name': 'مخزون البضاعة - حركة', 'account_type': asset_type, 'is_active': True}
        )
        ChartOfAccounts.objects.get_or_create(
            code='10100',
            defaults={'name': 'الخزينة', 'account_type': asset_type, 'is_active': True}
        )

    def test_quotation_creation_and_totals(self):
        """
        اختبار إنشاء عرض سعر وحساب إجمالياته تلقائياً
        """
        quotation = Quotation.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            date=timezone.now().date(),
            valid_until=timezone.now().date() + timezone.timedelta(days=7),
            created_by=self.admin,
            discount=Decimal("10.00"),
            notes="شروط الدفع عند التوريد"
        )
        self.assertIsNotNone(quotation.number)
        self.assertTrue(quotation.number.startswith("QT"))

        item = QuotationItem.objects.create(
            quotation=quotation,
            product=self.product,
            quantity=Decimal("5.00"),
            unit_price=Decimal("100.00"),
            discount=Decimal("20.00"),
            total=Decimal("0.00")  # سيتم حسابه بالـ save
        )
        # 5 * 100 - 20 = 480
        self.assertEqual(item.total, Decimal("480.00"))

        # تحديث المجموع وحفظ العرض
        quotation.subtotal = item.total
        quotation.tax = Decimal("67.20")  # 14% من 480
        quotation.total = quotation.subtotal - quotation.discount + quotation.tax
        quotation.save()

        self.assertEqual(quotation.total, Decimal("537.20"))

    def test_quotation_views_list_and_detail(self):
        """
        اختبار واجهات العرض والتفاصيل لعروض الأسعار
        """
        quotation = Quotation.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            date=timezone.now().date(),
            created_by=self.admin
        )
        
        # قائمة عروض الأسعار
        response = self.client.get(reverse("sale:quotation_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, quotation.number)

        # تفاصيل عرض السعر
        response = self.client.get(reverse("sale:quotation_detail", kwargs={"pk": quotation.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, quotation.number)

    def test_convert_quotation_to_sale_invoice(self):
        """
        اختبار تحويل عرض السعر إلى فاتورة مبيعات والتأكد من نقل كافة البيانات بدقة
        """
        quotation = Quotation.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            date=timezone.now().date(),
            created_by=self.admin
        )
        QuotationItem.objects.create(
            quotation=quotation,
            product=self.product,
            quantity=Decimal("2.00"),
            unit_price=Decimal("100.00"),
            discount=Decimal("0.00"),
            total=Decimal("200.00")
        )
        quotation.subtotal = Decimal("200.00")
        quotation.discount = Decimal("0.00")
        quotation.tax = Decimal("28.00")
        quotation.total = Decimal("228.00")
        quotation.save()

        # تشغيل دالة التحويل عبر الـ view
        response = self.client.post(reverse("sale:quotation_convert_to_sale", kwargs={"pk": quotation.pk}))
        
        # يجب أن يعيد التوجيه لصفحة تفاصيل الفاتورة الناتجة
        self.assertEqual(response.status_code, 302)

        # التحقق من تحديث حالة العرض وربطه بالفاتورة
        quotation.refresh_from_db()
        self.assertEqual(quotation.status, "accepted")
        self.assertIsNotNone(quotation.converted_to_sale)

        # التحقق من الفاتورة المنشأة
        sale = quotation.converted_to_sale
        self.assertEqual(sale.customer, self.customer)
        self.assertEqual(sale.warehouse, self.warehouse)
        self.assertEqual(sale.total, Decimal("228.00"))
        self.assertEqual(sale.items.count(), 1)
        self.assertEqual(sale.items.first().product, self.product)
        self.assertEqual(sale.items.first().quantity, Decimal("2.00"))

    def test_quotation_with_tax_disabled(self):
        """
        اختبار إنشاء عرض سعر مع إلغاء تفعيل الضريبة والتأكد من أنها تساوي صفر
        """
        response = self.client.post(
            reverse("sale:quotation_create"),
            data={
                "customer": self.customer.id,
                "warehouse": self.warehouse.id,
                "date": timezone.now().date().strftime("%Y-%m-%d"),
                "discount": "0.00",
                # tax_active is omitted to simulate being unchecked
                "product[]": [self.product.id],
                "quantity[]": ["2.00"],
                "unit_price[]": ["100.00"],
                "discount[]": ["0.00"]
            }
        )
        self.assertEqual(response.status_code, 302)
        quotation = Quotation.objects.order_by("-id").first()
        self.assertFalse(quotation.tax_active)
        self.assertEqual(quotation.tax, Decimal("0.00"))
        self.assertEqual(quotation.total, Decimal("200.00"))
