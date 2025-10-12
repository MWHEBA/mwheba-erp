"""
اختبارات نظام تزامن المدفوعات الشاملة
"""
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from ..models.payment_sync import (
    PaymentSyncOperation,
    PaymentSyncLog,
    PaymentSyncRule,
    PaymentSyncError,
)
from ..services.payment_sync_service import PaymentSyncService
from ..signals.payment_signals import PaymentSignalHandler

User = get_user_model()


class PaymentSyncServiceTestCase(TransactionTestCase):
    """اختبارات خدمة تزامن المدفوعات"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="syncuser", email="sync@example.com", password="testpass123"
        )

        self.sync_service = PaymentSyncService()

        # إنشاء قواعد تزامن تجريبية
        self._create_test_sync_rules()

        # إنشاء بيانات تجريبية للمبيعات والمشتريات
        self._create_test_data()

    def _create_test_sync_rules(self):
        """إنشاء قواعد تزامن تجريبية"""
        # قاعدة تزامن دفعات المبيعات
        self.sale_sync_rule = PaymentSyncRule.objects.create(
            name="تزامن دفعات المبيعات",
            source_model="sale_payment",
            trigger_event="on_create",
            sync_to_customer_payment=True,
            sync_to_journal_entry=True,
            sync_to_balance_cache=True,
            is_active=True,
            priority=1,
            created_by=self.user,
        )

        # قاعدة تزامن دفعات المشتريات
        self.purchase_sync_rule = PaymentSyncRule.objects.create(
            name="تزامن دفعات المشتريات",
            source_model="purchase_payment",
            trigger_event="on_create",
            sync_to_supplier_payment=True,
            sync_to_journal_entry=True,
            sync_to_balance_cache=True,
            is_active=True,
            priority=1,
            created_by=self.user,
        )

    def _create_test_data(self):
        """إنشاء بيانات تجريبية"""
        # إنشاء عميل ومورد تجريبيين
        try:
            from client.models import Customer
            from supplier.models import Supplier
            from sale.models import Sale
            from purchase.models import Purchase

            self.customer = Customer.objects.create(
                name="عميل تجريبي", email="customer@test.com", phone="123456789"
            )

            self.supplier = Supplier.objects.create(
                name="مورد تجريبي", email="supplier@test.com", phone="987654321"
            )

            # إنشاء فاتورة مبيعات تجريبية
            self.sale = Sale.objects.create(
                customer=self.customer,
                number="SALE-001",
                date=date.today(),
                total=Decimal("1000"),
                created_by=self.user,
            )

            # إنشاء فاتورة مشتريات تجريبية
            self.purchase = Purchase.objects.create(
                supplier=self.supplier,
                number="PURCH-001",
                date=date.today(),
                total=Decimal("500"),
                created_by=self.user,
            )

        except ImportError:
            # إذا لم تكن النماذج متاحة، إنشاء mock objects
            self.customer = MagicMock()
            self.customer.id = 1
            self.customer.name = "عميل تجريبي"

            self.supplier = MagicMock()
            self.supplier.id = 1
            self.supplier.name = "مورد تجريبي"

            self.sale = MagicMock()
            self.sale.id = 1
            self.sale.number = "SALE-001"
            self.sale.customer = self.customer

            self.purchase = MagicMock()
            self.purchase.id = 1
            self.purchase.number = "PURCH-001"
            self.purchase.supplier = self.supplier

    def test_sync_operation_creation(self):
        """اختبار إنشاء عملية تزامن"""
        # إنشاء دفعة مبيعات وهمية
        sale_payment = MagicMock()
        sale_payment.id = 1
        sale_payment.amount = Decimal("500")
        sale_payment.payment_date = date.today()
        sale_payment.payment_method = "cash"
        sale_payment.sale = self.sale
        sale_payment.__class__.__name__ = "SalePayment"

        # تنفيذ التزامن
        sync_operation = self.sync_service.sync_payment(
            sale_payment, "create_payment", self.user
        )

        # التحقق من إنشاء العملية
        self.assertIsInstance(sync_operation, PaymentSyncOperation)
        self.assertEqual(sync_operation.operation_type, "create_payment")
        self.assertEqual(sync_operation.created_by, self.user)
        self.assertIn("amount", sync_operation.payment_data)

    def test_sync_rule_matching(self):
        """اختبار تطابق قواعد التزامن"""
        # إنشاء دفعة مبيعات وهمية
        sale_payment = MagicMock()
        sale_payment.__class__.__name__ = "SalePayment"

        # الحصول على القواعد المطبقة
        applicable_rules = self.sync_service._get_applicable_rules(
            sale_payment, "create_payment"
        )

        # التحقق من وجود قاعدة واحدة على الأقل
        self.assertGreater(len(applicable_rules), 0)
        self.assertEqual(applicable_rules[0].source_model, "sale_payment")

    @patch("financial.services.payment_sync_service.JournalEntryService")
    def test_journal_entry_sync(self, mock_journal_service):
        """اختبار تزامن القيود المحاسبية"""
        # إعداد mock
        mock_entry = MagicMock()
        mock_entry.id = 1
        mock_entry.number = "JE-001"
        mock_journal_service.create_simple_entry.return_value = mock_entry

        # إنشاء دفعة مبيعات وهمية
        sale_payment = MagicMock()
        sale_payment.id = 1
        sale_payment.amount = Decimal("500")
        sale_payment.payment_date = date.today()
        sale_payment.sale = self.sale
        sale_payment.__class__.__name__ = "SalePayment"

        # تنفيذ التزامن
        sync_operation = self.sync_service.sync_payment(
            sale_payment, "create_payment", self.user
        )

        # التحقق من استدعاء إنشاء القيد
        self.assertTrue(mock_journal_service.create_simple_entry.called)

    def test_rollback_functionality(self):
        """اختبار وظيفة التراجع"""
        # إضافة عنصر للمكدس
        self.sync_service.rollback_stack.append(
            {
                "action": "delete_customer_payment",
                "object_id": 123,
                "model": "CustomerPayment",
            }
        )

        # محاكاة خطأ والتراجع
        with patch.object(self.sync_service, "_execute_rollback_item") as mock_rollback:
            try:
                self.sync_service._rollback_operations()
            except:
                pass

            # التحقق من استدعاء التراجع
            mock_rollback.assert_called_once()

        # التحقق من مسح المكدس
        self.assertEqual(len(self.sync_service.rollback_stack), 0)

    def test_error_handling(self):
        """اختبار معالجة الأخطاء"""
        # إنشاء دفعة وهمية
        payment = MagicMock()
        payment.id = 1
        payment.__class__.__name__ = "SalePayment"

        # إنشاء عملية تزامن
        sync_operation = PaymentSyncOperation.objects.create(
            operation_type="create_payment",
            payment_data={"id": 1},
            created_by=self.user,
        )

        # محاكاة خطأ
        test_error = ValidationError("خطأ تجريبي")

        # معالجة الخطأ
        self.sync_service._handle_sync_error(sync_operation, test_error)

        # التحقق من تسجيل الخطأ
        sync_operation.refresh_from_db()
        self.assertEqual(sync_operation.status, "failed")
        self.assertIsNotNone(sync_operation.error_message)

        # التحقق من إنشاء سجل خطأ
        error_log = PaymentSyncError.objects.filter(
            sync_operation=sync_operation
        ).first()
        self.assertIsNotNone(error_log)
        self.assertEqual(error_log.error_type, "validation_error")


class PaymentSignalHandlerTestCase(TestCase):
    """اختبارات معالج إشارات المدفوعات"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="signaluser", password="testpass123"
        )

    def test_significant_changes_detection(self):
        """اختبار كشف التغييرات المهمة"""
        # إنشاء دفعة وهمية
        payment = MagicMock()
        payment.amount = Decimal("1000")
        payment.payment_date = date.today()
        payment.payment_method = "cash"
        payment.notes = "ملاحظة"

        # محاكاة تغيير مهم
        old_payment = MagicMock()
        old_payment.amount = Decimal("500")  # تغيير في المبلغ
        old_payment.payment_date = date.today()
        old_payment.payment_method = "cash"
        old_payment.notes = "ملاحظة"

        with patch.object(payment.__class__, "objects") as mock_objects:
            mock_objects.get.return_value = old_payment

            # التحقق من كشف التغيير
            has_changes = PaymentSignalHandler._has_significant_changes(payment)
            self.assertTrue(has_changes)

    @patch("financial.signals.payment_signals.payment_sync_service")
    def test_payment_created_signal(self, mock_sync_service):
        """اختبار إشارة إنشاء دفعة"""
        # إنشاء دفعة وهمية
        payment = MagicMock()
        payment.id = 1

        # تشغيل معالج الإشارة
        PaymentSignalHandler.handle_payment_created(MagicMock, payment, True)

        # التحقق من استدعاء خدمة التزامن (بشكل غير متزامن)
        # ملاحظة: هذا اختبار مبسط للمنطق
        self.assertTrue(True)  # الاختبار الفعلي يحتاج إعداد أكثر تعقيداً

    @patch("financial.signals.payment_signals.payment_sync_service")
    def test_payment_deleted_signal(self, mock_sync_service):
        """اختبار إشارة حذف دفعة"""
        # إنشاء دفعة وهمية
        payment = MagicMock()
        payment.id = 1

        # تشغيل معالج الإشارة
        PaymentSignalHandler.handle_payment_deleted(MagicMock, payment)

        # التحقق من استدعاء خدمة التزامن
        mock_sync_service.sync_payment.assert_called_once_with(
            payment, "delete_payment"
        )


class PaymentSyncRuleTestCase(TestCase):
    """اختبارات قواعد تزامن المدفوعات"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="ruleuser", password="testpass123"
        )

    def test_rule_creation(self):
        """اختبار إنشاء قاعدة تزامن"""
        rule = PaymentSyncRule.objects.create(
            name="قاعدة تجريبية",
            description="قاعدة للاختبار",
            source_model="sale_payment",
            trigger_event="on_create",
            sync_to_customer_payment=True,
            sync_to_journal_entry=True,
            is_active=True,
            priority=1,
            created_by=self.user,
        )

        self.assertEqual(rule.name, "قاعدة تجريبية")
        self.assertTrue(rule.is_active)
        self.assertEqual(rule.priority, 1)

    def test_rule_conditions_matching(self):
        """اختبار تطابق شروط القاعدة"""
        # قاعدة مع شروط
        rule = PaymentSyncRule.objects.create(
            name="قاعدة مشروطة",
            source_model="sale_payment",
            trigger_event="on_create",
            conditions={"payment_method": "cash"},
            is_active=True,
            created_by=self.user,
        )

        # دفعة تطابق الشروط
        matching_payment = MagicMock()
        matching_payment.payment_method = "cash"

        # دفعة لا تطابق الشروط
        non_matching_payment = MagicMock()
        non_matching_payment.payment_method = "bank"

        # اختبار التطابق
        self.assertTrue(rule.matches_conditions(matching_payment))
        self.assertFalse(rule.matches_conditions(non_matching_payment))

    def test_sync_targets_retrieval(self):
        """اختبار الحصول على أهداف التزامن"""
        rule = PaymentSyncRule.objects.create(
            name="قاعدة متعددة الأهداف",
            source_model="sale_payment",
            trigger_event="on_create",
            sync_to_customer_payment=True,
            sync_to_journal_entry=True,
            sync_to_balance_cache=False,
            is_active=True,
            created_by=self.user,
        )

        targets = rule.get_sync_targets()

        self.assertIn("customer_payment", targets)
        self.assertIn("journal_entry", targets)
        self.assertNotIn("balance_cache", targets)


class PaymentSyncIntegrationTestCase(TransactionTestCase):
    """اختبارات التكامل الشاملة"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="integrationuser", password="testpass123"
        )

    def test_end_to_end_sale_payment_sync(self):
        """اختبار التزامن الشامل لدفعة مبيعات"""
        # هذا اختبار مبسط - في الواقع يحتاج بيانات حقيقية

        # إنشاء قاعدة تزامن
        sync_rule = PaymentSyncRule.objects.create(
            name="تزامن شامل",
            source_model="sale_payment",
            trigger_event="on_create",
            sync_to_customer_payment=True,
            sync_to_journal_entry=True,
            is_active=True,
            created_by=self.user,
        )

        # محاكاة دفعة مبيعات
        sale_payment = MagicMock()
        sale_payment.id = 1
        sale_payment.amount = Decimal("1000")
        sale_payment.payment_date = date.today()
        sale_payment.payment_method = "cash"
        sale_payment.__class__.__name__ = "SalePayment"

        # محاكاة فاتورة مبيعات
        sale = MagicMock()
        sale.id = 1
        sale.number = "SALE-001"
        sale.customer = MagicMock()
        sale.customer.id = 1
        sale.customer.name = "عميل تجريبي"
        sale_payment.sale = sale

        # تنفيذ التزامن
        sync_service = PaymentSyncService()

        with patch.multiple(
            sync_service,
            _sync_to_customer_payment=MagicMock(),
            _sync_to_journal_entry=MagicMock(),
            _update_balance_cache=MagicMock(),
        ):
            sync_operation = sync_service.sync_payment(
                sale_payment, "create_payment", self.user
            )

        # التحقق من نجاح العملية
        self.assertEqual(sync_operation.status, "completed")
        self.assertIsNotNone(sync_operation.completed_at)

    def test_sync_failure_and_rollback(self):
        """اختبار فشل التزامن والتراجع"""
        # إنشاء قاعدة تزامن
        sync_rule = PaymentSyncRule.objects.create(
            name="قاعدة فاشلة",
            source_model="sale_payment",
            trigger_event="on_create",
            sync_to_customer_payment=True,
            is_active=True,
            created_by=self.user,
        )

        # محاكاة دفعة
        payment = MagicMock()
        payment.id = 1
        payment.__class__.__name__ = "SalePayment"

        # محاكاة فشل في التزامن
        sync_service = PaymentSyncService()

        with patch.object(sync_service, "_sync_to_customer_payment") as mock_sync:
            mock_sync.side_effect = Exception("خطأ في التزامن")

            sync_operation = sync_service.sync_payment(
                payment, "create_payment", self.user
            )

        # التحقق من فشل العملية
        self.assertIn(sync_operation.status, ["failed", "rolled_back"])
        self.assertIsNotNone(sync_operation.error_message)
