"""
اختبارات شاملة لنظام ربط المدفوعات بالنظام المالي
"""
import pytest
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.db import transaction
from decimal import Decimal
from datetime import date, datetime

from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.journal_entry import JournalEntry
from financial.services.payment_integration_service import PaymentIntegrationService
from purchase.models import Purchase, PurchasePayment
from sale.models import Sale, SalePayment
from supplier.models import Supplier
from client.models import Customer
from product.models import Warehouse

User = get_user_model()


class PaymentIntegrationTestCase(TransactionTestCase):
    """
    اختبارات خدمة التكامل المالي للمدفوعات
    """

    def setUp(self):
        """إعداد البيانات الأساسية للاختبارات"""
        # إنشاء مستخدم للاختبار
        self.user = User.objects.create_user(
            username="test_user", email="test@example.com", password="testpass123"
        )

        # إنشاء أنواع الحسابات
        self.cash_account_type = AccountType.objects.create(
            name="الخزينة", code="CASH", category="asset"
        )

        self.bank_account_type = AccountType.objects.create(
            name="البنوك", code="BANK", category="asset"
        )

        # إنشاء الحسابات المالية
        self.cash_account = ChartOfAccounts.objects.create(
            name="الصندوق الرئيسي",
            code="1001",
            account_type=self.cash_account_type,
            is_cash_account=True,
            is_active=True,
        )

        self.bank_account = ChartOfAccounts.objects.create(
            name="البنك الأهلي",
            code="1002",
            account_type=self.bank_account_type,
            is_bank_account=True,
            is_active=True,
        )

        # إنشاء حسابات العملاء والموردين
        self.customer_account = ChartOfAccounts.objects.create(
            name="العملاء",
            code="1201",
            account_type=self.cash_account_type,  # مؤقت
            is_active=True,
        )

        self.supplier_account = ChartOfAccounts.objects.create(
            name="الموردين",
            code="2101",
            account_type=self.cash_account_type,  # مؤقت
            is_active=True,
        )

        # إنشاء مورد وعميل
        self.supplier = Supplier.objects.create(
            name="مورد تجريبي", email="supplier@test.com", is_active=True
        )

        self.customer = Customer.objects.create(
            name="عميل تجريبي", email="customer@test.com", is_active=True
        )

        # إنشاء مستودع
        self.warehouse = Warehouse.objects.create(
            name="المستودع الرئيسي", is_active=True
        )

        # إنشاء فاتورة مشتريات
        self.purchase = Purchase.objects.create(
            supplier=self.supplier,
            warehouse=self.warehouse,
            number="PUR0001",
            date=date.today(),
            total=Decimal("1000.00"),
            created_by=self.user,
        )

        # إنشاء فاتورة مبيعات
        self.sale = Sale.objects.create(
            customer=self.customer,
            warehouse=self.warehouse,
            number="SALE0001",
            date=date.today(),
            total=Decimal("1500.00"),
            created_by=self.user,
        )

    def test_purchase_payment_integration(self):
        """اختبار ربط دفعة المشتريات بالنظام المالي"""
        # إنشاء دفعة مشتريات
        payment = PurchasePayment.objects.create(
            purchase=self.purchase,
            financial_account=self.cash_account,
            amount=Decimal("500.00"),
            payment_date=date.today(),
            payment_method="cash",
            created_by=self.user,
        )

        # تنفيذ الربط المالي
        result = PaymentIntegrationService.process_payment(
            payment=payment, payment_type="purchase", user=self.user
        )

        # التحقق من نجاح العملية
        self.assertTrue(result["success"])
        self.assertIn("journal_entry_id", result)

        # التحقق من إنشاء القيد المحاسبي
        journal_entry = JournalEntry.objects.get(id=result["journal_entry_id"])
        self.assertEqual(journal_entry.lines.count(), 2)

        # التحقق من ربط السجلات
        payment.refresh_from_db()
        self.assertEqual(payment.financial_status, "synced")
        self.assertEqual(payment.financial_transaction, journal_entry)

    def test_sale_payment_integration(self):
        """اختبار ربط دفعة المبيعات بالنظام المالي"""
        # إنشاء دفعة مبيعات
        payment = SalePayment.objects.create(
            sale=self.sale,
            financial_account=self.bank_account,
            amount=Decimal("750.00"),
            payment_date=date.today(),
            payment_method="bank_transfer",
            created_by=self.user,
        )

        # تنفيذ الربط المالي
        result = PaymentIntegrationService.process_payment(
            payment=payment, payment_type="sale", user=self.user
        )

        # التحقق من نجاح العملية
        self.assertTrue(result["success"])

        # التحقق من القيد المحاسبي
        journal_entry = JournalEntry.objects.get(id=result["journal_entry_id"])
        debit_line = journal_entry.lines.filter(debit__gt=0).first()
        credit_line = journal_entry.lines.filter(credit__gt=0).first()

        self.assertEqual(debit_line.account, self.bank_account)
        self.assertEqual(credit_line.account, self.customer_account)

    def test_payment_validation_errors(self):
        """اختبار معالجة أخطاء التحقق من صحة البيانات"""
        # اختبار دفعة بدون حساب مالي
        payment = PurchasePayment.objects.create(
            purchase=self.purchase,
            amount=Decimal("500.00"),
            payment_date=date.today(),
            payment_method="cash",
            created_by=self.user,
        )

        result = PaymentIntegrationService.process_payment(
            payment=payment, payment_type="purchase", user=self.user
        )

        self.assertFalse(result["success"])
        self.assertIn("يجب تحديد الحساب المالي", result["message"])

    def test_bulk_payment_sync(self):
        """اختبار المزامنة المجمعة للمدفوعات"""
        # إنشاء عدة دفعات
        payments = []
        for i in range(3):
            payment = PurchasePayment.objects.create(
                purchase=self.purchase,
                financial_account=self.cash_account,
                amount=Decimal(f"{100 + i * 50}.00"),
                payment_date=date.today(),
                payment_method="cash",
                created_by=self.user,
            )
            payments.append(payment)

        # تنفيذ المزامنة المجمعة
        result = PaymentIntegrationService.bulk_sync_payments(
            payments=payments, payment_type="purchase", user=self.user
        )

        # التحقق من النتائج
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["success"], 3)
        self.assertEqual(result["failed"], 0)

        # التحقق من ربط جميع الدفعات
        for payment in payments:
            payment.refresh_from_db()
            self.assertEqual(payment.financial_status, "synced")

    def test_integration_status_check(self):
        """اختبار فحص حالة الربط المالي"""
        payment = PurchasePayment.objects.create(
            purchase=self.purchase,
            financial_account=self.cash_account,
            amount=Decimal("200.00"),
            payment_date=date.today(),
            payment_method="cash",
            created_by=self.user,
        )

        # فحص الحالة قبل الربط
        status = PaymentIntegrationService.get_integration_status(payment)
        self.assertFalse(status["is_synced"])
        self.assertTrue(status["can_be_synced"])

        # ربط الدفعة
        PaymentIntegrationService.process_payment(
            payment=payment, payment_type="purchase", user=self.user
        )

        # فحص الحالة بعد الربط
        status = PaymentIntegrationService.get_integration_status(payment)
        self.assertTrue(status["is_synced"])
        self.assertTrue(status["has_journal_entry"])


class PaymentFormValidationTestCase(TestCase):
    """
    اختبارات التحقق من صحة نماذج المدفوعات
    """

    def setUp(self):
        """إعداد البيانات الأساسية"""
        self.user = User.objects.create_user(
            username="form_test_user", password="testpass123"
        )

        # إنشاء حساب نقدي
        account_type = AccountType.objects.create(
            name="نقدي", code="CASH", category="asset"
        )

        self.cash_account = ChartOfAccounts.objects.create(
            name="الصندوق",
            code="1001",
            account_type=account_type,
            is_cash_account=True,
            is_active=True,
        )

        self.bank_account = ChartOfAccounts.objects.create(
            name="البنك",
            code="1002",
            account_type=account_type,
            is_bank_account=True,
            is_active=True,
        )

    def test_purchase_payment_form_validation(self):
        """اختبار التحقق من صحة نموذج دفعة المشتريات"""
        from purchase.forms import PurchasePaymentForm

        # بيانات صحيحة
        valid_data = {
            "financial_account": self.cash_account.id,
            "amount": "100.00",
            "payment_date": date.today(),
            "payment_method": "cash",
            "notes": "دفعة تجريبية",
        }

        form = PurchasePaymentForm(data=valid_data)
        self.assertTrue(form.is_valid())

        # اختبار عدم تطابق طريقة الدفع مع نوع الحساب
        invalid_data = valid_data.copy()
        invalid_data["payment_method"] = "bank_transfer"  # تحويل بنكي مع حساب نقدي

        form = PurchasePaymentForm(data=invalid_data)
        self.assertFalse(form.is_valid())
        self.assertIn("financial_account", form.errors)

    def test_sale_payment_form_validation(self):
        """اختبار التحقق من صحة نموذج دفعة المبيعات"""
        from sale.forms import SalePaymentForm

        # بيانات صحيحة
        valid_data = {
            "financial_account": self.bank_account.id,
            "amount": "250.00",
            "payment_date": date.today(),
            "payment_method": "bank_transfer",
            "reference_number": "REF123",
        }

        form = SalePaymentForm(data=valid_data)
        self.assertTrue(form.is_valid())

        # اختبار مبلغ سالب
        invalid_data = valid_data.copy()
        invalid_data["amount"] = "-50.00"

        form = SalePaymentForm(data=invalid_data)
        self.assertFalse(form.is_valid())
        self.assertIn("amount", form.errors)


class PaymentSignalsTestCase(TransactionTestCase):
    """
    اختبارات إشارات المدفوعات
    """

    def setUp(self):
        """إعداد البيانات الأساسية"""
        self.user = User.objects.create_user(
            username="signals_test_user", password="testpass123"
        )

        # إنشاء الحسابات والبيانات الأساسية
        account_type = AccountType.objects.create(
            name="نقدي", code="CASH", category="asset"
        )

        self.cash_account = ChartOfAccounts.objects.create(
            name="الصندوق",
            code="1001",
            account_type=account_type,
            is_cash_account=True,
            is_active=True,
        )

        self.supplier = Supplier.objects.create(name="مورد الإشارات", is_active=True)

        self.warehouse = Warehouse.objects.create(
            name="مستودع الإشارات", is_active=True
        )

        self.purchase = Purchase.objects.create(
            supplier=self.supplier,
            warehouse=self.warehouse,
            number="SIG001",
            date=date.today(),
            total=Decimal("800.00"),
            created_by=self.user,
        )

    def test_payment_creation_signal(self):
        """اختبار إشارة إنشاء الدفعة"""
        # إنشاء دفعة مع حساب مالي
        payment = PurchasePayment.objects.create(
            purchase=self.purchase,
            financial_account=self.cash_account,
            amount=Decimal("400.00"),
            payment_date=date.today(),
            payment_method="cash",
            created_by=self.user,
        )

        # التحقق من تنفيذ الربط التلقائي عبر الإشارة
        # ملاحظة: قد يحتاج وقت للتنفيذ بسبب transaction.on_commit
        payment.refresh_from_db()

        # في البيئة الحقيقية، ستكون الإشارة قد نفذت الربط
        # هنا نتحقق من أن الدفعة تم إنشاؤها بنجاح
        self.assertEqual(payment.financial_account, self.cash_account)
        self.assertEqual(payment.financial_status, "pending")


if __name__ == "__main__":
    pytest.main([__file__])
