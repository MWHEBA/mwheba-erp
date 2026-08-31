import datetime
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from sale.models import Sale, SaleItem, SalePayment
from sale.forms import SalePaymentForm
from sale.services.sale_service import SaleService
from customer.models import Customer
from product.models import Warehouse, Product, Category, Unit

User = get_user_model()


class SalePaymentValidationTest(TestCase):
    """
    اختبارات التحقق الصارم من الدفعات لمنع السداد الزائد عن المتبقي
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='password123'
        )
        from financial.models import ChartOfAccounts, AccountType, AccountingPeriod
        AccountingPeriod.objects.get_or_create(
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 12, 31),
            defaults={'name': 'فترة 2026', 'status': 'open'}
        )
        self.acc_type, _ = AccountType.objects.get_or_create(
            code='ASSET',
            defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
        )
        self.accounts_receivable, _ = ChartOfAccounts.objects.get_or_create(
            code='10301',
            defaults={'name': 'عملاء تجاريون', 'account_type': self.acc_type, 'is_active': True}
        )
        self.cash_account, _ = ChartOfAccounts.objects.get_or_create(
            code='10100',
            defaults={'name': 'الصندوق الرئيسية', 'account_type': self.acc_type, 'is_active': True}
        )
        self.customer = Customer.objects.create(
            name='عميل اختبار',
            phone='01000000000',
            financial_account=self.accounts_receivable
        )
        self.warehouse = Warehouse.objects.create(
            name='المخزن الرئيسي',
            is_active=True
        )
        self.category = Category.objects.create(name='عام')
        self.unit = Unit.objects.create(name='قطعة')
        self.product = Product.objects.create(
            name='منتج اختبار',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('50.00'),
            selling_price=Decimal('100.00'),
            created_by=self.user
        )
        # إنشاء فاتورة بقيمة 100 ج.م
        self.sale = Sale.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            date=timezone.now().date(),
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
            payment_status='unpaid',
            created_by=self.user
        )
        SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            quantity=Decimal('1'),
            unit_price=Decimal('100.00'),
            total=Decimal('100.00')
        )

    def test_form_blocks_overpayment(self):
        """اختبار أن النموذج يرفض إدخال مبلغ أكبر من المتبقي"""
        form_data = {
            'amount': '150.00',  # يتجاوز الـ 100.00
            'payment_date': timezone.now().date(),
            'payment_method': 'cash',
        }
        form = SalePaymentForm(data=form_data, sale=self.sale)
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
        self.assertTrue(any('يتجاوز المبلغ المتبقي' in err for err in form.errors['amount']))

    def test_service_blocks_overpayment(self):
        """اختبار أن خدمة الدفع تمنع إضافة مبلغ يتجاوز المتبقي"""
        payment_data = {
            'amount': Decimal('150.00'),
            'payment_method': 'cash',
            'payment_date': timezone.now().date(),
        }
        with self.assertRaises(ValidationError):
            SaleService.process_payment(self.sale, payment_data, self.user)

    def test_service_blocks_payment_on_paid_invoice(self):
        """اختبار أن الخدمة تمنع إضافة أية دفعة على فاتورة مسددة بالكامل"""
        # سداد الفاتورة بالكامل بـ 100 ج.م
        payment_data1 = {
            'amount': Decimal('100.00'),
            'payment_method': 'cash',
            'payment_date': timezone.now().date(),
        }
        SaleService.process_payment(self.sale, payment_data1, self.user)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.payment_status, 'paid')
        self.assertEqual(self.sale.amount_due, Decimal('0.00'))

        # محاولة إضافة دفعة إضافية بـ 10 ج.م
        payment_data2 = {
            'amount': Decimal('10.00'),
            'payment_method': 'cash',
            'payment_date': timezone.now().date(),
        }
        with self.assertRaises(ValidationError):
            SaleService.process_payment(self.sale, payment_data2, self.user)
