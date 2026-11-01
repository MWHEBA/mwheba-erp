# -*- coding: utf-8 -*-
import datetime
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from sale.models.installments import InstallmentPlan, InstallmentItem
from cheques.models import Cheque, ChequeType, ChequeStatus, AllocationStatus
from cheques.models.allocation import ChequeInvoiceAllocation
from cheques.services.allocation_service import ChequeAllocationService as AllocationService
from sale.services.installment_engine import InstallmentEngine
from customer.models import Customer
from financial.models import ChartOfAccounts, AccountType, AccountingPeriod, Currency

User = get_user_model()


class DecoupledInstallmentTests(TestCase):
    """
    اختبارات التحقق من استقلالية نظام الأقساط والشيكات عن فواتير المبيعات (Phase 0.5 Decoupling)
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='test_estate_user',
            password='Password123!',
            is_superuser=True
        )
        self.egp, _ = Currency.objects.get_or_create(
            code='EGP',
            defaults={'name': 'جنيه مصري', 'is_functional': True}
        )
        AccountingPeriod.objects.get_or_create(
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 12, 31),
            defaults={'name': 'فترة 2026', 'status': 'open'}
        )
        self.acc_type, _ = AccountType.objects.get_or_create(
            code='ASSET',
            defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
        )
        self.receivable_acc, _ = ChartOfAccounts.objects.get_or_create(
            code='10301',
            defaults={'name': 'عملاء تجاريون', 'account_type': self.acc_type, 'is_active': True}
        )
        self.cash_acc, _ = ChartOfAccounts.objects.get_or_create(
            code='10100',
            defaults={'name': 'الصندوق الرئيسي', 'account_type': self.acc_type, 'is_active': True}
        )
        self.customer = Customer.objects.create(
            name='عميل حجز عقاري',
            phone='01011112222',
            financial_account=self.receivable_acc
        )

    def test_decoupled_installment_plan_creation_without_sale(self):
        """
        التحقق من إمكانية إنشاء خطة أقساط مستقلة تماماً بدون فاتورة مبيعات
        وسلامة السلاسل النصية __str__ للخطة والأقساط
        """
        plan = InstallmentPlan.objects.create(
            sale=None,
            customer=self.customer,
            total_principal=Decimal('90000.00'),
            total_markup=Decimal('10000.00'),
            total_amount=Decimal('100000.00'),
            number_of_installments=2,
            start_date=datetime.date(2026, 1, 1),
            status=InstallmentPlan.PlanStatus.DRAFT,
            created_by=self.user,
        )

        item1 = InstallmentItem.objects.create(
            plan=plan,
            installment_number=1,
            due_date=datetime.date(2026, 2, 1),
            principal_amount=Decimal('45000.00'),
            interest_amount=Decimal('5000.00'),
            total_amount=Decimal('50000.00'),
            cash_status=InstallmentItem.CashStatus.PENDING,
        )

        # التحقق من أن __str__ آمن ولا يثير استثناءات في غياب الفاتورة
        self.assertIn("PLAN-", str(plan))
        self.assertIn("عميل حجز عقاري", str(plan))
        self.assertIn(str(plan.id), str(item1))

    def test_chk_installment_plan_financial_validity_constraint(self):
        """
        التحقق من إنفاذ قيد قاعدة البيانات chk_installment_plan_financial_validity
        (total_amount > 0 and number_of_installments > 0)
        """
        with self.assertRaises(IntegrityError):
            InstallmentPlan.objects.create(
                sale=None,
                customer=self.customer,
                total_principal=Decimal('0.00'),
                total_markup=Decimal('0.00'),
                total_amount=Decimal('0.00'),  # Invalid <= 0
                number_of_installments=0,      # Invalid <= 0
                start_date=datetime.date(2026, 1, 1),
                status=InstallmentPlan.PlanStatus.DRAFT,
                created_by=self.user,
            )

    def test_clean_blocks_orphan_plan_activation(self):
        """
        التحقق من أن clean() يمنع تفعيل خطة أقساط يتيمة (بدون فاتورة وبدون عقد)
        """
        plan = InstallmentPlan(
            sale=None,
            customer=self.customer,
            total_principal=Decimal('50000.00'),
            total_markup=Decimal('0.00'),
            total_amount=Decimal('50000.00'),
            number_of_installments=1,
            start_date=datetime.date(2026, 1, 1),
            status=InstallmentPlan.PlanStatus.ACTIVE,
            created_by=self.user,
        )
        with self.assertRaises(ValidationError) as cm:
            plan.clean()
        self.assertIn("لا يمكن تفعيل خطة أقساط يتيمة بدون مصدر معتمد", str(cm.exception))

    def test_contract_cash_collection_without_sale(self):
        """
        تسجيل سداد قسط نقدي على خطة غير مرتبطة بفاتورة مبيعات:
        1. يتم التوزيع النسبي وتحديث مبالغ وحالة القسط
        2. لا يتم إنشاء SalePayment إطلاقاً
        3. لا يحدث أي AttributeError عند إغلاق الخطة
        """
        plan = InstallmentPlan.objects.create(
            sale=None,
            customer=self.customer,
            total_principal=Decimal('45000.00'),
            total_markup=Decimal('5000.00'),
            total_amount=Decimal('50000.00'),
            number_of_installments=1,
            start_date=datetime.date(2026, 1, 1),
            status=InstallmentPlan.PlanStatus.DRAFT,
            created_by=self.user,
        )

        item = InstallmentItem.objects.create(
            plan=plan,
            installment_number=1,
            due_date=datetime.date(2026, 2, 1),
            principal_amount=Decimal('45000.00'),
            interest_amount=Decimal('5000.00'),
            total_amount=Decimal('50000.00'),
            cash_status=InstallmentItem.CashStatus.PENDING,
        )

        # سداد كامل القسط
        payment = InstallmentEngine.record_installment_payment(
            installment_item=item,
            amount=Decimal('50000.00'),
            payment_date=datetime.date(2026, 2, 1),
            user=self.user,
            payment_method='cash',
            financial_account=self.cash_acc,
        )

        # التحقق من أن السداد لا ينشئ SalePayment
        self.assertIsNone(payment)

        # التحقق من تحديث القسط وإغلاق الخطة بنجاح
        item.refresh_from_db()
        plan.refresh_from_db()

        self.assertEqual(item.paid_amount, Decimal('50000.00'))
        self.assertEqual(item.paid_principal, Decimal('45000.00'))
        self.assertEqual(item.paid_interest, Decimal('5000.00'))
        self.assertEqual(item.cash_status, InstallmentItem.CashStatus.COLLECTED)
        self.assertEqual(plan.status, InstallmentPlan.PlanStatus.COMPLETED)

    def test_decoupled_cheque_allocation_and_reversal(self):
        """
        التحقق من تخصيص شيك قبض على قسط خطة مستقلة بدون فاتورة مبيعات،
        وتحديث التغطية الورقية، ثم عكس التخصيص بنجاح دون أي خطأ
        """
        plan = InstallmentPlan.objects.create(
            sale=None,
            customer=self.customer,
            total_principal=Decimal('100000.00'),
            total_markup=Decimal('0.00'),
            total_amount=Decimal('100000.00'),
            number_of_installments=1,
            start_date=datetime.date(2026, 1, 1),
            status=InstallmentPlan.PlanStatus.DRAFT,
            created_by=self.user,
        )

        item = InstallmentItem.objects.create(
            plan=plan,
            installment_number=1,
            due_date=datetime.date(2026, 3, 1),
            principal_amount=Decimal('100000.00'),
            interest_amount=Decimal('0.00'),
            total_amount=Decimal('100000.00'),
            cash_status=InstallmentItem.CashStatus.PENDING,
        )

        cheque = Cheque.objects.create(
            cheque_type=ChequeType.RECEIVABLE,
            cheque_number='CHQ-TEST-001',
            drawer_bank_name='البنك الأهلي المصري',
            currency=self.egp,
            issue_date=datetime.date(2026, 1, 1),
            amount=Decimal('50000.00'),
            due_date=datetime.date(2026, 3, 1),
            customer=self.customer,
            status=ChequeStatus.IN_PORTFOLIO,
            created_by=self.user,
        )

        # تخصيص الشيك على القسط مباشرة بدون فاتورة
        allocation = AllocationService.allocate_cheque_to_invoice(
            cheque=cheque,
            sale=None,
            amount=Decimal('50000.00'),
            installment_item=item,
            user=self.user,
        )

        self.assertIsNotNone(allocation)
        self.assertIsNone(allocation.sale)
        self.assertEqual(allocation.installment_item, item)
        self.assertEqual(allocation.allocated_amount, Decimal('50000.00'))

        # التحقق من ربط الشيك بالقسط
        item.refresh_from_db()
        self.assertIn(cheque, item.cheques.all())

        # عكس التخصيص بنجاح
        AllocationService.reverse_cheque_allocation(
            allocation=allocation,
            reason='إلغاء الشيك أو استبداله',
            user=self.user
        )

        allocation.refresh_from_db()
        self.assertEqual(allocation.allocation_status, AllocationStatus.REVERSED)
