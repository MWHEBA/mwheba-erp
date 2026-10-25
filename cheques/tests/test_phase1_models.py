# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from financial.models import ChartOfAccounts, Currency, AccountType
from customer.models import Customer
from supplier.models import Supplier
from cheques.models import (
    Checkbook,
    CheckbookLeaf,
    Cheque,
    ChequeType,
    ChequePurpose,
    ChequeStatus,
    ChequeActionLog,
    ChequeActionType,
    ChequeSettlementLine,
    ChequeBatchDeposit,
    BatchDepositStatus,
    ChequeInvoiceAllocation,
    AllocationStatus,
    BankChequeLayout,
)

User = get_user_model()


@pytest.fixture
def test_user(db):
    user = User.objects.filter(username='test_cheque_admin').first()
    if not user:
        user = User.objects.create_user(
            username='test_cheque_admin',
            email='cheque_admin@mwheba.com',
            password='Password123!'
        )
    return user


@pytest.fixture
def bank_account(db):
    account = ChartOfAccounts.objects.filter(code='1112001').first()
    if not account:
        account_type, _ = AccountType.objects.get_or_create(
            code='asset',
            defaults={
                'name': 'أصول',
                'category': 'asset',
                'nature': 'debit'
            }
        )
        account = ChartOfAccounts.objects.create(
            name='بنك مصر الجاري',
            code='1112001',
            account_type=account_type,
            level=3,
            is_active=True
        )
    return account


@pytest.fixture
def currency_egp(db):
    currency = Currency.objects.filter(code='EGP').first()
    if not currency:
        currency = Currency.objects.create(
            name='جنيه مصري',
            code='EGP',
            symbol='ج.م',
            is_functional=True,
            is_active=True
        )
    return currency


@pytest.fixture
def customer_sample(db):
    customer = Customer.objects.filter(name='شركة الأمل للتجارة').first()
    if not customer:
        customer = Customer.objects.create(
            name='شركة الأمل للتجارة',
            code='CUST-001',
            phone='01000000001'
        )
    return customer


@pytest.fixture
def supplier_sample(db):
    supplier = Supplier.objects.filter(name='شركة النور للورق').first()
    if not supplier:
        supplier = Supplier.objects.create(
            name='شركة النور للورق',
            code='SUPP-001'
        )
    return supplier


@pytest.mark.django_db
class TestCheckbookAndLeafModels:
    """اختبارات دفاتر الشيكات والأوراق الذرية وحماية التداخل"""

    def test_checkbook_creation_and_automatic_leaves_generation(self, test_user, bank_account):
        """التحقق من إنشاء الدفتر وتوليد الأوراق تلقائياً بحالة AVAILABLE"""
        checkbook = Checkbook.objects.create(
            name='دفتر بنك مصر 2026',
            bank_account=bank_account,
            serial_prefix='BM',
            serial_from=1001,
            serial_to=1010,
            created_by=test_user
        )
        assert checkbook.leaf_count == 10
        assert checkbook.leaves.count() == 10
        first_leaf = checkbook.leaves.first()
        assert first_leaf.serial_number == 'BM1001'
        assert first_leaf.status == CheckbookLeaf.LeafStatus.AVAILABLE

    def test_checkbook_invalid_range_validation(self, test_user, bank_account):
        """التحقق من رفض النطاق غير الصالح عندما تكون البداية أكبر من النهاية"""
        with pytest.raises(ValidationError):
            checkbook = Checkbook(
                name='دفتر غير صالح',
                bank_account=bank_account,
                serial_from=2000,
                serial_to=1900,
                created_by=test_user
            )
            checkbook.clean()

    def test_checkbook_overlapping_range_prevention(self, test_user, bank_account):
        """التحقق من منع تداخل نطاقات دفاتر الشيكات لنفس الحساب البنكي"""
        Checkbook.objects.create(
            name='دفتر 1',
            bank_account=bank_account,
            serial_prefix='CIB',
            serial_from=5000,
            serial_to=5050,
            created_by=test_user
        )

        overlapping_checkbook = Checkbook(
            name='دفتر متداخل',
            bank_account=bank_account,
            serial_prefix='CIB',
            serial_from=5040,
            serial_to=5100,
            created_by=test_user
        )
        with pytest.raises(ValidationError):
            overlapping_checkbook.clean()

    def test_checkbook_leaf_voided_reason_requirement(self, test_user, bank_account):
        """التحقق من إلزامية تدوين سبب الإتلاف عند تحويل ورقة الدفتر إلى VOIDED"""
        checkbook = Checkbook.objects.create(
            name='دفتر اختبار الإتلاف',
            bank_account=bank_account,
            serial_prefix='VD',
            serial_from=1,
            serial_to=5,
            created_by=test_user
        )
        leaf = checkbook.leaves.first()
        leaf.status = CheckbookLeaf.LeafStatus.VOIDED
        leaf.voided_reason = ''  # فارغ
        with pytest.raises(ValidationError):
            leaf.clean()

        # مع كتابة السبب تنجح
        leaf.voided_reason = 'تلف الورقة في الطابعة أثناء إعداد الصك'
        leaf.clean()
        leaf.save()
        assert leaf.status == CheckbookLeaf.LeafStatus.VOIDED


@pytest.mark.django_db
class TestChequeModelConstraintsAndCalculations:
    """اختبارات النموذج المركزي للشيك والقيود الرياضية والحسابات التلقائية"""

    def test_cheque_creation_and_functional_calculation(self, test_user, customer_sample, currency_egp):
        """التحقق من حساب المعادل المحلي وتلقائية القيم الدفترية"""
        cheque = Cheque.objects.create(
            voucher_number='CHQ-REC-0001',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            cheque_number='123456',
            amount=Decimal('50000.00'),
            currency=currency_egp,
            original_exchange_rate=Decimal('1.000000'),
            issue_date=timezone.now().date(),
            due_date=timezone.now().date() + timezone.timedelta(days=30),
            drawer_bank_name='البنك التجاري الدولي CIB',
            drawer_name='عميل الأمل',
            payee_name='شركة موهبة',
            customer=customer_sample,
            created_by=test_user
        )
        assert cheque.functional_amount == Decimal('50000.00')
        assert cheque.book_value_functional == Decimal('50000.00')
        assert cheque.remaining_amount == Decimal('50000.00')
        assert cheque.remaining_functional == Decimal('50000.00')
        assert cheque.is_guarantee is False
        assert cheque.is_advance_payment is False

    def test_cheque_remaining_functional_partial_calculation(self, test_user, customer_sample, currency_egp):
        """التحقق من حساب المعادل المحلي للمتبقي عند الوفاء الجزئي"""
        cheque = Cheque.objects.create(
            voucher_number='CHQ-REC-0002',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            cheque_number='987654',
            amount=Decimal('10000.00'),
            collected_amount=Decimal('4000.00'),
            remaining_amount=Decimal('6000.00'),
            currency=currency_egp,
            original_exchange_rate=Decimal('1.000000'),
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            drawer_bank_name='بنك مصر',
            drawer_name='عميل تجريبي',
            payee_name='شركة موهبة',
            customer=customer_sample,
            created_by=test_user
        )
        assert cheque.remaining_functional == Decimal('6000.00')

    def test_cheque_positive_amount_validation(self, test_user, customer_sample, currency_egp):
        """التحقق من رفض المبالغ الصفرية أو السالبة بـ ValidationError"""
        with pytest.raises(ValidationError):
            cheque = Cheque(
                voucher_number='CHQ-REC-INVALID',
                cheque_type=ChequeType.RECEIVABLE,
                cheque_number='0000',
                amount=Decimal('0.00'),
                currency=currency_egp,
                issue_date=timezone.now().date(),
                due_date=timezone.now().date(),
                drawer_bank_name='البنك الأهلي',
                drawer_name='محرر الشيك',
                payee_name='المستفيد',
                customer=customer_sample,
                created_by=test_user
            )
            cheque.clean()

    def test_cheque_collected_exceeding_total_validation(self, test_user, customer_sample, currency_egp):
        """التحقق من رفض تجاوز المبلغ المحصل لمبلغ الشيك الكلي"""
        with pytest.raises(ValidationError):
            cheque = Cheque(
                voucher_number='CHQ-REC-EXCEED',
                cheque_type=ChequeType.RECEIVABLE,
                cheque_number='1111',
                amount=Decimal('5000.00'),
                collected_amount=Decimal('6000.00'),
                currency=currency_egp,
                issue_date=timezone.now().date(),
                due_date=timezone.now().date(),
                drawer_bank_name='بنك القاهرة',
                drawer_name='محرر الشيك',
                payee_name='المستفيد',
                customer=customer_sample,
                created_by=test_user
            )
            cheque.clean()


@pytest.mark.django_db
class TestChequeImmutabilityAndDeletionGuards:
    """اختبارات تجميد الحقول بعد الترحيل وحظر الحذف"""

    def test_cheque_immutability_after_draft(self, test_user, customer_sample, currency_egp):
        """التحقق من حظر تعديل الحقول المالية لشيك خرج من حالة المسودة"""
        cheque = Cheque.objects.create(
            voucher_number='CHQ-REC-POSTED',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.IN_PORTFOLIO,  # حالة مرحلة بعد المسودة
            cheque_number='55555',
            amount=Decimal('20000.00'),
            currency=currency_egp,
            original_exchange_rate=Decimal('1.000000'),
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            drawer_bank_name='بنك QNB',
            drawer_name='عميل تجميد',
            payee_name='شركة موهبة',
            customer=customer_sample,
            created_by=test_user
        )

        # محاولة تعديل المبلغ بعد الترحيل
        cheque.amount = Decimal('25000.00')
        with pytest.raises(ValidationError):
            cheque.save()

    def test_authorized_mutation_context_allows_leaf_replacement(self, test_user, bank_account, supplier_sample, currency_egp):
        """التحقق من السماح باستبدال الورقة التالفة فقط في السياق المعتمد"""
        checkbook = Checkbook.objects.create(
            name='دفتر صرف',
            bank_account=bank_account,
            serial_prefix='PAY',
            serial_from=101,
            serial_to=105,
            created_by=test_user
        )
        leaf1 = checkbook.leaves.get(serial_number='PAY101')
        leaf2 = checkbook.leaves.get(serial_number='PAY102')

        cheque = Cheque.objects.create(
            voucher_number='CHQ-PAY-0001',
            cheque_type=ChequeType.PAYABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.ISSUED,
            checkbook_leaf=leaf1,
            cheque_number='PAY101',
            amount=Decimal('15000.00'),
            currency=currency_egp,
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            drawer_bank_name='بنك مصر',
            drawer_name='شركة موهبة',
            payee_name='مورد النور',
            supplier=supplier_sample,
            created_by=test_user
        )

        # تعديل ورقة الدفتر بدون سياق معتمد -> يُرفض
        cheque.checkbook_leaf = leaf2
        cheque.cheque_number = 'PAY102'
        with pytest.raises(ValidationError):
            cheque.save()

        # مع تفعيل السياق المعتمد -> ينجح
        cheque._authorized_mutation_context = 'REPLACE_RUINED_LEAF'
        cheque.save()
        cheque.refresh_from_db()
        assert cheque.checkbook_leaf_id == leaf2.id
        assert cheque.cheque_number == 'PAY102'

    def test_cheque_delete_prevention(self, test_user, customer_sample, currency_egp):
        """التحقق من منع حذف شيك مرحل أو مرتبط بسجلات تدقيق"""
        cheque = Cheque.objects.create(
            voucher_number='CHQ-REC-DEL',
            cheque_type=ChequeType.RECEIVABLE,
            status=ChequeStatus.IN_PORTFOLIO,
            cheque_number='7777',
            amount=Decimal('3000.00'),
            currency=currency_egp,
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            drawer_bank_name='بنك مصر',
            drawer_name='عميل',
            payee_name='مستفيد',
            customer=customer_sample,
            created_by=test_user
        )

        # حذف الفردي يُرفض
        with pytest.raises(ValidationError):
            cheque.delete()

        # حذف الـ QuerySet يُرفض أيضاً
        with pytest.raises(ValidationError):
            Cheque.objects.filter(pk=cheque.pk).delete()


@pytest.mark.django_db
class TestSupportingModelsAndSequences:
    """اختبارات نماذج سجل التدقيق، الحوافظ، والتخصيص، والتسلسل المركزي"""

    def test_cheque_action_log_creation(self, test_user, customer_sample, currency_egp):
        """التحقق من إنشاء سجل الحركة والتدقيق مع مفتاح منع التكرار وبصمة المعلمات"""
        cheque = Cheque.objects.create(
            voucher_number='CHQ-ACT-0001',
            cheque_type=ChequeType.RECEIVABLE,
            cheque_number='8888',
            amount=Decimal('7000.00'),
            currency=currency_egp,
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            drawer_bank_name='البنك الأهلي',
            drawer_name='عميل',
            payee_name='مستفيد',
            customer=customer_sample,
            created_by=test_user
        )

        log = ChequeActionLog.objects.create(
            cheque=cheque,
            action=ChequeActionType.RECEIVE,
            from_status=ChequeStatus.DRAFT,
            to_status=ChequeStatus.IN_PORTFOLIO,
            action_date=timezone.now().date(),
            idempotency_key='ACT-KEY-001',
            request_payload_hash='hash1234567890abcdef',
            created_by=test_user
        )
        assert log.id is not None
        assert log.is_reversed is False

        # تكرار نفس الـ idempotency_key يثير خطأ قاعدة بيانات
        with pytest.raises(IntegrityError):
            ChequeActionLog.objects.create(
                cheque=cheque,
                action=ChequeActionType.DEPOSIT,
                from_status=ChequeStatus.IN_PORTFOLIO,
                to_status=ChequeStatus.UNDER_COLLECTION,
                action_date=timezone.now().date(),
                idempotency_key='ACT-KEY-001',  # مكرر
                request_payload_hash='hash_other',
                created_by=test_user
            )

    def test_bank_cheque_layout_defaults(self, bank_account):
        """التحقق من إنشاء وضبط القالب الافتراضي لأبعاد طباعة الشيك"""
        layout1 = BankChequeLayout.objects.create(
            bank_account=bank_account,
            template_name='CIB Corporate Layout',
            is_default=True
        )
        assert layout1.is_default is True

        layout2 = BankChequeLayout.objects.create(
            bank_account=bank_account,
            template_name='CIB New Layout',
            is_default=True
        )
        layout1.refresh_from_db()
        assert layout2.is_default is True
        assert layout1.is_default is False

    def test_sequence_service_central_numbering_for_cheques(self):
        """التحقق من أن SequenceService يولد الترقيم القياسي لأنواع مستندات الشيكات"""
        num_rec = SequenceService.get_next_number(DocumentType.CHEQUE_RECEIVABLE)
        assert 'CHQR' in num_rec

        num_pay = SequenceService.get_next_number(DocumentType.CHEQUE_PAYABLE)
        assert 'CHQP' in num_pay

        num_batch = SequenceService.get_next_number(DocumentType.CHEQUE_DEPOSIT_BATCH)
        assert 'CHQB' in num_batch
