# -*- coding: utf-8 -*-
import datetime
import uuid
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from django.core.cache import cache
from django.core.exceptions import ValidationError

from core.models import SystemModule
from users.models import User
from customer.models import Customer
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency
from financial.models.journal_entry import JournalEntry
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames

from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData
from governance.exceptions import IdempotencyError

from cheques.models.cheque import Cheque, ChequeType, ChequeStatus, ChequePurpose
from cheques.models.allocation import ChequeInvoiceAllocation
from sale.models.installments import InstallmentPlan, InstallmentItem

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    UnitBooking,
    PropertyContract,
    ContractCoOwner,
)

from real_estate.services.accounting_service import RealEstateAccountingService
from real_estate.services.clearance_service import ContractDebtClearanceService


class RealEstatePhase3EventAccountingTests(TestCase):
    """
    مجموعة الاختبارات الشاملة للمرحلة 3:
    1. تحصين AccountingGateway ببصمة البيانات المالية (Financial Fingerprint Hardening).
    2. دورة قيود اليومية لأحداث القطاع العقاري اليوم الأول (Day-1 IFRS 15 Events).
    3. عزل حساب الضمان البنكي لحافظات الشيكات (Escrow Isolation).
    4. قاعدة منع ازدواج الالتزامات عند استبدال الشيك بنقدية (Anti-Duplication Rule).
    5. بوابة الاعتراف بالإيراد (IFRS 15 Revenue Assessment Gate).
    6. خدمة براءة الذمة والمخالصة المالية التامة للعقد (ContractDebtClearanceService).
    """

    def setUp(self):
        cache.clear()
        SystemModule.objects.update_or_create(
            code='real_estate',
            defaults={'name_ar': 'القطاع العقاري', 'name_en': 'Real Estate', 'is_enabled': True}
        )

        self.user = User.objects.create_superuser(
            username='admin_re_phase3',
            email='admin_re3@example.com',
            password='password123'
        )

        # أنواع الحسابات
        self.asset_type, _ = AccountType.objects.get_or_create(
            code='asset',
            defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
        )
        self.liability_type, _ = AccountType.objects.get_or_create(
            code='liability',
            defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'}
        )
        self.revenue_type, _ = AccountType.objects.get_or_create(
            code='revenue',
            defaults={'name': 'إيرادات', 'category': 'revenue', 'nature': 'credit'}
        )

        # تهيئة الحسابات الأساسية في دليل الحسابات
        self.cash_account, _ = ChartOfAccounts.objects.get_or_create(
            code='11110',
            defaults={
                'name': 'الخزينة الرئيسية',
                'account_type': self.asset_type,
                'is_active': True,
                'is_leaf': True
            }
        )
        self.escrow_bank_account, _ = ChartOfAccounts.objects.get_or_create(
            code='11160',
            defaults={
                'name': 'حساب الضمان البنكي للمشروع (Escrow)',
                'account_type': self.asset_type,
                'is_active': True,
                'is_leaf': True
            }
        )
        self.booking_advance_account, _ = ChartOfAccounts.objects.get_or_create(
            code='21101',
            defaults={
                'name': 'دفعات حجز عملاء عقارات',
                'account_type': self.liability_type,
                'is_active': True,
                'is_leaf': True
            }
        )
        self.contract_liability_account, _ = ChartOfAccounts.objects.get_or_create(
            code='21102',
            defaults={
                'name': 'التزامات عقود بيع وحدات عقارية',
                'account_type': self.liability_type,
                'is_active': True,
                'is_leaf': True
            }
        )
        self.vault_cheques_account, _ = ChartOfAccounts.objects.get_or_create(
            code='11220',
            defaults={
                'name': 'أوراق قبض وشيكات بالخزينة',
                'account_type': self.asset_type,
                'is_active': True,
                'is_leaf': True
            }
        )
        self.revenue_account, _ = ChartOfAccounts.objects.get_or_create(
            code='41101',
            defaults={
                'name': 'إيرادات مبيعات عقارية محققة',
                'account_type': self.revenue_type,
                'is_active': True,
                'is_leaf': True
            }
        )
        self.penalty_income_account, _ = ChartOfAccounts.objects.get_or_create(
            code='42201',
            defaults={
                'name': 'إيرادات غرامات وفسخ عقود عقارية',
                'account_type': self.revenue_type,
                'is_active': True,
                'is_leaf': True
            }
        )
        self.forfeited_balances_account, _ = ChartOfAccounts.objects.get_or_create(
            code='21701',
            defaults={
                'name': 'أمانات محتجزة معلقة لحين إعادة بيع الوحدة',
                'account_type': self.liability_type,
                'is_active': True,
                'is_leaf': True
            }
        )

        self.egp, _ = Currency.objects.get_or_create(
            code='EGP',
            defaults={'name': 'جنيه مصري', 'symbol': 'ج.م', 'is_functional': True}
        )

        # حساب العميل المستقل
        self.customer_fin_account, _ = ChartOfAccounts.objects.get_or_create(
            code='11210009',
            defaults={
                'name': 'حساب العميل أحمد ممدوح',
                'account_type': self.asset_type,
                'is_active': True,
                'is_leaf': True
            }
        )
        self.customer = Customer.objects.create(
            code='CUST-RE-P3',
            name='أحمد ممدوح العقاري',
            phone='01099999999',
            financial_account=self.customer_fin_account,
            created_by=self.user
        )

        # المشروع والوحدة
        self.project = RealEstateProject.objects.create(
            code='PRJ-P3-TOWER',
            name='برج النخبة 3',
            escrow_account=self.escrow_bank_account,
            start_date=timezone.localdate(),
            expected_completion_date=timezone.localdate() + datetime.timedelta(days=730),
            created_by=self.user
        )
        self.block = PropertyBlock.objects.create(
            project=self.project,
            code='BLK-P3-A',
            name='المبنى أ'
        )
        self.floor = PropertyFloor.objects.create(
            block=self.block,
            floor_number=3,
            name='الدور الثالث'
        )
        self.unit = PropertyUnit.objects.create(
            project=self.project,
            floor=self.floor,
            unit_code='TWR3-F03-U01',
            unit_type=PropertyUnit.UnitType.APARTMENT,
            gross_area=Decimal('150.00'),
            net_area=Decimal('120.00'),
            meter_price=Decimal('20000.00'),
            total_price=Decimal('3000000.00')
        )

        # الحجز المبدئي
        self.booking = UnitBooking.objects.create(
            booking_number=f"BK-P3-{uuid.uuid4().hex[:6].upper()}",
            unit=self.unit,
            customer=self.customer,
            booking_date=timezone.localdate(),
            expiry_date=timezone.localdate() + datetime.timedelta(days=14),
            holding_deposit=Decimal('50000.00'),
            created_by=self.user
        )

        # العقد
        self.contract = PropertyContract.objects.create(
            contract_number=f"SPA-P3-{uuid.uuid4().hex[:6].upper()}",
            project=self.project,
            unit=self.unit,
            customer=self.customer,
            contract_date=timezone.localdate(),
            delivery_date=timezone.localdate() + datetime.timedelta(days=730),
            final_contract_price=Decimal('3000000.00'),
            down_payment=Decimal('300000.00'),
            currency=self.egp,
            revenue_recognition_method=PropertyContract.RevenueMethod.POINT_IN_TIME,
            created_by=self.user
        )

    def test_gateway_fingerprint_hardening_idempotent_replay(self):
        """
        اختبار تحصين AccountingGateway:
        1. إنشاء قيد جديد ينجح ويخزن بصمة الطلب.
        2. إعادة استدعاء نفس الـ idempotency_key بنفس البيانات يعيد القيد الأصلي بأمان.
        3. إعادة استدعاء نفس المفتاح ببيانات مختلفة (مبلغ معدل) يرفع IdempotencyError صريح.
        """
        gateway = AccountingGateway()
        idem_key = f"JE:test:phase3_fingerprint:{uuid.uuid4().hex}"

        lines = [
            JournalEntryLineData(
                account_code='11110',
                debit=Decimal('1000.00'),
                credit=Decimal('0.00'),
                currency='EGP'
            ),
            JournalEntryLineData(
                account_code='21101',
                debit=Decimal('0.00'),
                credit=Decimal('1000.00'),
                currency='EGP'
            )
        ]

        # 1. أول إنشاء
        entry1 = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='UnitBooking',
            source_id=self.booking.id,
            lines=lines,
            idempotency_key=idem_key,
            user=self.user
        )
        self.assertIsNotNone(entry1.id)

        # 2. إعادة نفس الطلب بنفس البيانات -> يعيد نفس القيد تماماً
        entry2 = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='UnitBooking',
            source_id=self.booking.id,
            lines=lines,
            idempotency_key=idem_key,
            user=self.user
        )
        self.assertEqual(entry1.id, entry2.id)

        # 3. إعادة نفس المفتاح لكن مع تعديل المبالغ -> يجب أن يرفع IdempotencyError
        divergent_lines = [
            JournalEntryLineData(
                account_code='11110',
                debit=Decimal('2000.00'),
                credit=Decimal('0.00'),
                currency='EGP'
            ),
            JournalEntryLineData(
                account_code='21101',
                debit=Decimal('0.00'),
                credit=Decimal('2000.00'),
                currency='EGP'
            )
        ]

        with self.assertRaises(IdempotencyError) as ctx:
            gateway.create_journal_entry(
                source_module='real_estate',
                source_model='UnitBooking',
                source_id=self.booking.id,
                lines=divergent_lines,
                idempotency_key=idem_key,
                user=self.user
            )

        self.assertIn("Payload divergence detected", str(ctx.exception))

    def test_day1_event_1_booking_holding_fee(self):
        """
        Event 1: إثبات تحصيل جدية الحجز
        Dr: Cash / Bank (11110)
        Cr: Customer Booking Advances (21101)
        """
        entry = RealEstateAccountingService.post_booking_holding_fee(
            booking=self.booking,
            payment_account=self.cash_account,
            user=self.user
        )

        self.assertEqual(entry.status, 'posted')
        self.assertEqual(entry.total_amount, Decimal('50000.00'))

        lines = list(entry.lines.all())
        self.assertEqual(len(lines), 2)
        debit_line = next(l for l in lines if l.debit > 0)
        credit_line = next(l for l in lines if l.credit > 0)

        self.assertEqual(debit_line.account.code, '11110')
        self.assertEqual(debit_line.debit, Decimal('50000.00'))
        self.assertEqual(credit_line.account.code, '21101')
        self.assertEqual(credit_line.credit, Decimal('50000.00'))

    def test_day1_event_1b_booking_conversion(self):
        """
        Event 1b: تحويل جدية الحجز لمقدم تعاقد
        Dr: Customer Booking Advances (21101) [50,000]
        Dr: Cash / Bank (11110) [250,000 إضافي]
        Cr: Real Estate Contract Liability (21102) [300,000]
        """
        entry = RealEstateAccountingService.post_booking_conversion(
            booking=self.booking,
            contract=self.contract,
            user=self.user,
            additional_down_payment=Decimal('250000.00'),
            payment_account=self.cash_account
        )

        self.assertEqual(entry.status, 'posted')
        self.assertEqual(entry.total_amount, Decimal('300000.00'))

        lines = list(entry.lines.all())
        debit_adv = next(l for l in lines if l.account.code == '21101')
        debit_cash = next(l for l in lines if l.account.code == '11110')
        credit_liab = next(l for l in lines if l.account.code == '21102')

        self.assertEqual(debit_adv.debit, Decimal('50000.00'))
        self.assertEqual(debit_cash.debit, Decimal('250000.00'))
        self.assertEqual(credit_liab.credit, Decimal('300000.00'))

    def test_day1_event_2_contract_cheques_and_escrow_isolation(self):
        """
        Event 2: إثبات استلام شيكات الأقساط المؤجلة بالخزينة وعزل حساب الضمان
        Dr: Vault Cheques (11220) [2,700,000]
        Cr: Contract Liabilities (21102) [2,700,000]
        وتأكيد قفل deposit_bank_account على حساب الضمان escrow_bank_account.
        """
        cheques = []
        for i in range(1, 4):
            chq = Cheque.objects.create(
                voucher_number=f"CHQ-P3-{uuid.uuid4().hex[:6].upper()}",
                cheque_type=ChequeType.RECEIVABLE,
                purpose=ChequePurpose.INVOICE_SETTLEMENT,
                status=ChequeStatus.UNDER_COLLECTION,
                cheque_number=f"9000{i}",
                amount=Decimal('900000.00'),
                currency=self.egp,
                issue_date=timezone.localdate(),
                due_date=timezone.localdate() + datetime.timedelta(days=90 * i),
                drawer_bank_name='البنك الأهلي المصري',
                drawer_name=self.customer.name,
                payee_name='شركة التطوير العقاري',
                customer=self.customer,
                created_by=self.user
            )
            cheques.append(chq)

        entry = RealEstateAccountingService.post_contract_execution_cheques(
            contract=self.contract,
            cheques=cheques,
            user=self.user
        )

        self.assertEqual(entry.status, 'posted')
        self.assertEqual(entry.total_amount, Decimal('2700000.00'))

        # التحقق من عزل حساب الضمان على الشيكات
        for chq in cheques:
            chq.refresh_from_db()
            self.assertEqual(chq.deposit_bank_account_id, self.escrow_bank_account.id)

        lines = list(entry.lines.all())
        debit_vault = next(l for l in lines if l.account.code == '11220')
        credit_liab = next(l for l in lines if l.account.code == '21102')

        self.assertEqual(debit_vault.debit, Decimal('2700000.00'))
        self.assertEqual(credit_liab.credit, Decimal('2700000.00'))

    def test_day1_event_3a_direct_cash_installment(self):
        """
        Event 3a: سداد قسط نقدي مباشر في حساب الضمان البنكي
        Dr: Bank Escrow (11160) [100,000]
        Cr: Contract Liabilities (21102) [100,000]
        """
        plan = InstallmentPlan.objects.create(
            sale=None,
            total_amount=Decimal('2700000.00'),
            total_principal=Decimal('2700000.00'),
            number_of_installments=1,
            start_date=timezone.localdate(),
            customer=self.customer,
            status=InstallmentPlan.PlanStatus.ACTIVE,
            created_by=self.user
        )
        item = InstallmentItem.objects.create(
            plan=plan,
            installment_number=1,
            due_date=timezone.localdate() + datetime.timedelta(days=90),
            principal_amount=Decimal('100000.00'),
            total_amount=Decimal('100000.00')
        )

        entry = RealEstateAccountingService.post_direct_cash_installment(
            contract=self.contract,
            installment_item=item,
            amount=Decimal('100000.00'),
            payment_account=self.escrow_bank_account,
            user=self.user
        )

        self.assertEqual(entry.status, 'posted')
        self.assertEqual(entry.total_amount, Decimal('100000.00'))

        lines = list(entry.lines.all())
        self.assertEqual(lines[0].account.code, '11160')
        self.assertEqual(lines[0].debit, Decimal('100000.00'))
        self.assertEqual(lines[1].account.code, '21102')
        self.assertEqual(lines[1].credit, Decimal('100000.00'))

    def test_day1_event_3c_cheque_replacement_anti_duplication_rule(self):
        """
        Event 3c: استبدال شيك ورقي بنقدية - التحقق الصارم من قاعدة منع ازدواج الالتزام (Anti-Duplication)
        Dr: Bank Escrow (11160) [50,000]
        Cr: Vault Cheques (11220) [50,000]
        ويجب أن لا يمس القيد حساب التزامات العقد 21102 إطلاقاً لمنع ازدواج تسجيل الدفعة!
        """
        chq = Cheque.objects.create(
            voucher_number=f"CHQ-P3-{uuid.uuid4().hex[:6].upper()}",
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.UNDER_COLLECTION,
            cheque_number="888111",
            amount=Decimal('50000.00'),
            currency=self.egp,
            issue_date=timezone.localdate(),
            due_date=timezone.localdate() + datetime.timedelta(days=30),
            drawer_bank_name='البنك الأهلي',
            drawer_name=self.customer.name,
            payee_name='شركة التطوير',
            customer=self.customer,
            created_by=self.user
        )

        entry = RealEstateAccountingService.post_cheque_replacement_cash(
            contract=self.contract,
            cheque=chq,
            amount=Decimal('50000.00'),
            payment_account=self.escrow_bank_account,
            user=self.user
        )

        self.assertEqual(entry.status, 'posted')
        lines = list(entry.lines.all())
        account_codes = [l.account.code for l in lines]

        # التأكيد الحاسم: حساب التزامات العقد 21102 غير موجود في القيد
        self.assertNotIn('21102', account_codes)
        self.assertIn('11160', account_codes)
        self.assertIn('11220', account_codes)

        debit_line = next(l for l in lines if l.debit > 0)
        credit_line = next(l for l in lines if l.credit > 0)
        self.assertEqual(debit_line.account.code, '11160')
        self.assertEqual(credit_line.account.code, '11220')

    def test_day1_event_4_ifrs15_revenue_recognition_gate(self):
        """
        Event 4: بوابة الاعتراف بالإيراد وفق معيار IFRS 15
        1. في طريقة Point in Time: يرفض الاعتراف قبل التسليم الفعلي للوحدة.
        2. عند التسليم (is_handover=True): يعترف بالإيراد بنجاح:
           Dr: Contract Liabilities (21102) [3,000,000]
           Cr: Realized Revenue (41101) [3,000,000]
        """
        # 1. الرفض قبل التسليم
        self.contract.revenue_recognition_method = PropertyContract.RevenueMethod.POINT_IN_TIME
        self.contract.unit.status = PropertyUnit.UnitStatus.RESERVED
        self.contract.unit.save()

        with self.assertRaises(ValidationError) as ctx:
            RealEstateAccountingService.post_revenue_recognition(
                contract=self.contract,
                amount=Decimal('3000000.00'),
                user=self.user,
                is_handover=False
            )
        self.assertIn("Point in Time", str(ctx.exception))

        # 2. القبول عند التسليم الفعلي (Handover)
        entry = RealEstateAccountingService.post_revenue_recognition(
            contract=self.contract,
            amount=Decimal('3000000.00'),
            user=self.user,
            is_handover=True
        )

        self.assertEqual(entry.status, 'posted')
        self.assertEqual(entry.total_amount, Decimal('3000000.00'))

        lines = list(entry.lines.all())
        debit_liab = next(l for l in lines if l.account.code == '21102')
        credit_rev = next(l for l in lines if l.account.code == '41101')

        self.assertEqual(debit_liab.debit, Decimal('3000000.00'))
        self.assertEqual(credit_rev.credit, Decimal('3000000.00'))

    def test_day1_event_5_contract_cancellation_and_settlement(self):
        """
        Event 5: فسخ وإلغاء العقد العقاري
        Dr: Contract Liabilities (21102) [3,000,000]
        Cr: Vault Cheques (11220) [2,700,000 رد شيكات]
        Cr: Penalty Income (42201) [150,000 غرامة إدارية]
        Cr: Bank Escrow (11160) [100,000 مسترد نقدي للعميل]
        Cr: Forfeited Balances (21701) [50,000 معلقة لحين إعادة البيع]
        """
        entry = RealEstateAccountingService.post_contract_cancellation(
            contract=self.contract,
            penalty_amount=Decimal('150000.00'),
            refund_amount=Decimal('100000.00'),
            uncashed_cheques_amount=Decimal('2700000.00'),
            forfeited_pending_resale=Decimal('50000.00'),
            refund_account=self.escrow_bank_account,
            user=self.user
        )

        self.assertEqual(entry.status, 'posted')
        self.assertEqual(entry.total_amount, Decimal('3000000.00'))

        lines = list(entry.lines.all())
        debit_liab = next(l for l in lines if l.account.code == '21102')
        credit_vault = next(l for l in lines if l.account.code == '11220')
        credit_penalty = next(l for l in lines if l.account.code == '42201')
        credit_refund = next(l for l in lines if l.account.code == '11160')
        credit_forfeited = next(l for l in lines if l.account.code == '21701')

        self.assertEqual(debit_liab.debit, Decimal('3000000.00'))
        self.assertEqual(credit_vault.credit, Decimal('2700000.00'))
        self.assertEqual(credit_penalty.credit, Decimal('150000.00'))
        self.assertEqual(credit_refund.credit, Decimal('100000.00'))
        self.assertEqual(credit_forfeited.credit, Decimal('50000.00'))

    def test_contract_debt_clearance_service(self):
        """
        Phase 3.5: فحص براءة الذمة التامة للعقد العقاري وإصدار الشهادة
        1. العقد غير مكتمل السداد يرفض إصدار شهادة المخالصة.
        2. عند سداد كامل الأقساط وعدم وجود شيكات مرتدة، تصدر الشهادة وتتحول حالة العقد إلى COMPLETED.
        """
        plan = InstallmentPlan.objects.create(
            sale=None,
            total_amount=Decimal('2700000.00'),
            total_principal=Decimal('2700000.00'),
            number_of_installments=1,
            start_date=timezone.localdate(),
            customer=self.customer,
            status=InstallmentPlan.PlanStatus.ACTIVE,
            created_by=self.user
        )
        item = InstallmentItem.objects.create(
            plan=plan,
            installment_number=1,
            due_date=timezone.localdate() + datetime.timedelta(days=90),
            principal_amount=Decimal('2700000.00'),
            total_amount=Decimal('2700000.00'),
            paid_amount=Decimal('0.00')
        )
        self.contract.installment_plan = plan
        self.contract.status = PropertyContract.ContractStatus.ACTIVE
        self.contract.save()

        from customer.models import CustomerPayment
        from real_estate.models.contract import ContractPaymentReceipt
        dp_payment = CustomerPayment.objects.create(
            customer=self.customer,
            amount=Decimal('300000.00'),
            payment_date=timezone.localdate(),
            payment_method='CASH',
            created_by=self.user
        )
        ContractPaymentReceipt.objects.create(
            contract=self.contract,
            customer_payment=dp_payment,
            installment_item=None
        )

        # 1. فحص قبل السداد -> غير مبرأ الذمة
        eval1 = ContractDebtClearanceService.evaluate_contract_clearance(self.contract)
        self.assertFalse(eval1['is_cleared'])
        self.assertEqual(eval1['remaining_balance'], Decimal('2700000.00'))

        with self.assertRaises(ValidationError):
            ContractDebtClearanceService.issue_clearance_certificate(self.contract, self.user)

        # 2. سداد القسط بالكامل
        item.paid_amount = Decimal('2700000.00')
        item.paid_principal = Decimal('2700000.00')
        item.save()

        eval2 = ContractDebtClearanceService.evaluate_contract_clearance(self.contract)
        self.assertTrue(eval2['is_cleared'])
        self.assertTrue(eval2['can_issue_clearance_certificate'])

        cert = ContractDebtClearanceService.issue_clearance_certificate(self.contract, self.user)
        self.contract.refresh_from_db()

        self.assertEqual(self.contract.status, PropertyContract.ContractStatus.COMPLETED)
        self.assertTrue(self.contract.installments_settled)
        self.assertIn("CLR-", cert['certificate_number'])
