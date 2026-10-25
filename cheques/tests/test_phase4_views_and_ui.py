# -*- coding: utf-8 -*-
from decimal import Decimal
import pytest
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from cheques.models import (
    Cheque,
    ChequeType,
    ChequeStatus,
    ChequePurpose,
    Checkbook,
    CheckbookLeaf,
    CheckbookLeafStatus,
    ChequeBatchDeposit,
    BankChequeLayout,
)
from financial.models import (
    Currency,
    ChartOfAccounts,
    AccountType,
    UserTreasuryAccess,
)
from financial.services.bank_reconciliation_service import BankCandidateEngine

User = get_user_model()


@pytest.fixture
def auth_client(client, test_user):
    """عميل اختبار مسجل الدخول بصلاحيات كاملة لتطبيق الشيكات"""
    perms = Permission.objects.filter(
        codename__in=[
            'view_cheque', 'add_cheque', 'change_cheque', 'delete_cheque',
            'deposit_cheque', 'collect_cheque', 'bounce_cheque', 'endorse_cheque',
            'reverse_cheque_action', 'print_cheque', 'manage_checkbooks',
            'manage_guarantee_cheques', 'convert_guarantee'
        ]
    )
    test_user.user_permissions.add(*perms)
    client.force_login(test_user)
    return client


@pytest.fixture
def test_user():
    user = User.objects.create_user(
        username="cheques_ui_tester",
        email="cheques_ui@mwheba.com",
        password="ValidPassword123!",
        is_staff=True,
        is_superuser=True,
    )
    return user


@pytest.fixture
def base_financial_setup(test_user):
    egp, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={
            "name": "Egyptian Pound",
            "symbol": "EGP",
            "is_functional": True,
            "is_active": True,
            "decimal_places": 2
        }
    )

    asset_type, _ = AccountType.objects.get_or_create(
        code="asset",
        defaults={"name": "أصول", "category": "asset", "nature": "debit"}
    )
    liability_type, _ = AccountType.objects.get_or_create(
        code="liability",
        defaults={"name": "خصوم", "category": "liability", "nature": "credit"}
    )
    expense_type, _ = AccountType.objects.get_or_create(
        code="expense",
        defaults={"name": "مصروفات", "category": "expense", "nature": "debit"}
    )

    bank_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11110",
        defaults={
            "name": "بنك مصر - حساب جاري",
            "account_type": asset_type,
            "level": 4,
            "is_leaf": True,
            "is_active": True,
            "currency": egp,
        }
    )

    notes_rec, _ = ChartOfAccounts.objects.get_or_create(
        code="11220",
        defaults={
            "name": "أوراق القبض",
            "account_type": asset_type,
            "level": 4,
            "is_leaf": True,
            "is_active": True,
            "currency": egp,
        }
    )

    coll_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11190",
        defaults={
            "name": "شيكات برسم التحصيل",
            "account_type": asset_type,
            "level": 4,
            "is_leaf": True,
            "is_active": True,
            "currency": egp,
        }
    )

    notes_pay, _ = ChartOfAccounts.objects.get_or_create(
        code="21120",
        defaults={
            "name": "أوراق الدفع",
            "account_type": liability_type,
            "level": 4,
            "is_leaf": True,
            "is_active": True,
            "currency": egp,
        }
    )

    # منح صلاحية الخزينة للمستخدم
    UserTreasuryAccess.objects.get_or_create(
        user=test_user,
        treasury=bank_acc,
        defaults={
            'can_deposit': True,
            'can_disburse': True,
            'max_single_disbursement_limit': Decimal('1000000.00'),
            'daily_disbursement_limit': Decimal('5000000.00'),
        }
    )

    return {
        'currency': egp,
        'bank': bank_acc,
        'notes_rec': notes_rec,
        'coll_acc': coll_acc,
        'notes_pay': notes_pay,
    }


@pytest.fixture
def sample_receivable_cheque(test_user, base_financial_setup):
    today = timezone.now().date()
    return Cheque.objects.create(
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        voucher_number="CHQR-2026-00001",
        cheque_number="RCV-1001",
        amount=Decimal("15000.00"),
        currency=base_financial_setup['currency'],
        original_exchange_rate=Decimal("1.000000"),
        functional_amount=Decimal("15000.00"),
        book_value_functional=Decimal("15000.00"),
        remaining_amount=Decimal("15000.00"),
        remaining_functional=Decimal("15000.00"),
        issue_date=today,
        due_date=today,
        drawer_bank_name="Banque Misr",
        drawer_name="العميل أحمد محمود",
        payee_name="موهبة",
        created_by=test_user,
    )


@pytest.fixture
def sample_payable_cheque(test_user, base_financial_setup):
    today = timezone.now().date()
    book = Checkbook.objects.create(
        bank_account=base_financial_setup['bank'],
        name="دفتر بنك مصر 01",
        serial_prefix="BM",
        serial_from=5001,
        serial_to=5010,
        current_serial=5001,
        leaf_count=10,
        created_by=test_user,
    )
    leaf = book.leaves.get(serial_number="BM5001")

    return Cheque.objects.create(
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.ISSUED,
        voucher_number="CHQP-2026-00001",
        cheque_number="BM5001",
        checkbook_leaf=leaf,
        deposit_bank_account=base_financial_setup['bank'],
        amount=Decimal("25000.00"),
        currency=base_financial_setup['currency'],
        original_exchange_rate=Decimal("1.000000"),
        functional_amount=Decimal("25000.00"),
        book_value_functional=Decimal("25000.00"),
        remaining_amount=Decimal("25000.00"),
        remaining_functional=Decimal("25000.00"),
        issue_date=today,
        due_date=today,
        payee_name="شركة التوريدات المتحدة",
        drawer_bank_name="Banque Misr",
        created_by=test_user,
    )


@pytest.mark.django_db
class TestChequeReceivableViews:
    """اختبارات شاشات أوراق القبض (ListView, CreateView, DetailView) والبحث اللحظي"""

    def test_receivable_list_view_renders_correctly(self, auth_client, sample_receivable_cheque):
        url = reverse('cheques:receivable_list')
        response = auth_client.get(url)
        assert response.status_code == 200
        assert 'cheques' in response.context
        assert 'stats' in response.context
        assert sample_receivable_cheque.cheque_number in response.content.decode('utf-8')
        assert 'أوراق القبض والشيكات الواردة' in response.content.decode('utf-8')

    def test_receivable_list_ajax_do_search(self, auth_client, sample_receivable_cheque):
        url = reverse('cheques:receivable_list')
        response = auth_client.get(url, {'search': 'RCV-1001', 'ajax': '1'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert response.status_code == 200
        data = response.json()
        assert 'table_html' in data
        assert 'pagination_html' in data
        assert 'stats' in data
        assert 'RCV-1001' in data['table_html']

    def test_receivable_create_view_get_and_post(self, auth_client, base_financial_setup):
        url = reverse('cheques:receivable_create')
        get_res = auth_client.get(url)
        assert get_res.status_code == 200

        today = timezone.now().date()
        post_data = {
            'cheque_number': 'RCV-NEW-99',
            'purpose': ChequePurpose.INVOICE_SETTLEMENT,
            'amount': '30000.00',
            'currency': base_financial_setup['currency'].id,
            'original_exchange_rate': '1.000000',
            'issue_date': str(today),
            'due_date': str(today),
            'drawer_bank_name': 'CIB Bank',
            'drawer_name': 'عميل جديد',
            'payee_name': 'موهبة',
        }
        post_res = auth_client.post(url, data=post_data)
        assert post_res.status_code == 302
        new_cheque = Cheque.objects.get(cheque_number='RCV-NEW-99')
        assert new_cheque.amount == Decimal('30000.00')
        assert new_cheque.voucher_number.startswith('CHQR')

    def test_receivable_detail_view_renders_timeline_and_modals(self, auth_client, sample_receivable_cheque):
        url = reverse('cheques:receivable_detail', kwargs={'pk': sample_receivable_cheque.pk})
        response = auth_client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert sample_receivable_cheque.cheque_number in content
        assert 'depositModal' in content
        assert 'collectModal' in content
        assert 'bounceModal' in content


@pytest.mark.django_db
class TestChequePayableViews:
    """اختبارات شاشات أوراق الدفع (ListView, CreateView, DetailView)"""

    def test_payable_list_view_renders_correctly(self, auth_client, sample_payable_cheque):
        url = reverse('cheques:payable_list')
        response = auth_client.get(url)
        assert response.status_code == 200
        assert 'stats' in response.context
        assert sample_payable_cheque.cheque_number in response.content.decode('utf-8')

    def test_payable_list_ajax_do_search(self, auth_client, sample_payable_cheque):
        url = reverse('cheques:payable_list')
        response = auth_client.get(url, {'search': 'BM5001', 'ajax': '1'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert response.status_code == 200
        data = response.json()
        assert 'BM5001' in data['table_html']

    def test_payable_detail_view_renders(self, auth_client, sample_payable_cheque):
        url = reverse('cheques:payable_detail', kwargs={'pk': sample_payable_cheque.pk})
        response = auth_client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert sample_payable_cheque.cheque_number in content
        assert 'clearModal' in content


@pytest.mark.django_db
class TestChequeActionEndpoints:
    """اختبارات استدعاء العمليات والمودالات عبر POST endpoints"""

    def test_cheque_deposit_action_endpoint(self, auth_client, sample_receivable_cheque, base_financial_setup):
        url = reverse('cheques:cheque_deposit_action', kwargs={'pk': sample_receivable_cheque.pk})
        post_data = {
            'deposit_bank_account': base_financial_setup['bank'].id,
            'action_date': str(timezone.now().date()),
            'notes': 'إيداع تجريبي للاختبار',
        }
        res = auth_client.post(url, data=post_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert res.status_code == 200
        json_data = res.json()
        assert json_data['success'] is True

        sample_receivable_cheque.refresh_from_db()
        assert sample_receivable_cheque.status == ChequeStatus.UNDER_COLLECTION
        assert sample_receivable_cheque.deposit_bank_account == base_financial_setup['bank']

    def test_cheque_bounce_action_endpoint(self, auth_client, sample_receivable_cheque):
        sample_receivable_cheque.status = ChequeStatus.UNDER_COLLECTION
        sample_receivable_cheque.save()

        url = reverse('cheques:cheque_bounce_action', kwargs={'pk': sample_receivable_cheque.pk})
        post_data = {
            'action_date': str(timezone.now().date()),
            'bounce_reason': 'عدم كفاية الرصيد بالبنك',
        }
        res = auth_client.post(url, data=post_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert res.status_code == 200
        assert res.json()['success'] is True

        sample_receivable_cheque.refresh_from_db()
        assert sample_receivable_cheque.status == ChequeStatus.BOUNCED

    def test_cheque_clear_action_payable(self, auth_client, sample_payable_cheque):
        url = reverse('cheques:cheque_clear_action', kwargs={'pk': sample_payable_cheque.pk})
        post_data = {
            'clearing_date': str(timezone.now().date())
        }
        res = auth_client.post(url, data=post_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert res.status_code == 200
        assert res.json()['success'] is True

        sample_payable_cheque.refresh_from_db()
        assert sample_payable_cheque.status == ChequeStatus.CLEARED


@pytest.mark.django_db
class TestBatchDepositAndCheckbookViews:
    """اختبارات شاشات الحوافظ ودفاتر الشيكات"""

    def test_batch_deposit_list_and_create(self, auth_client, base_financial_setup, sample_receivable_cheque):
        list_url = reverse('cheques:batch_deposit_list')
        assert auth_client.get(list_url).status_code == 200

        create_url = reverse('cheques:batch_deposit_create')
        assert auth_client.get(create_url).status_code == 200

        post_data = {
            'bank_account': base_financial_setup['bank'].id,
            'deposit_date': str(timezone.now().date()),
            'cheques': [sample_receivable_cheque.id],
            'notes': 'حافظة تجريبية'
        }
        post_res = auth_client.post(create_url, data=post_data)
        assert post_res.status_code == 302
        batch = ChequeBatchDeposit.objects.first()
        assert batch is not None
        assert batch.cheques.filter(id=sample_receivable_cheque.id).exists()

    def test_checkbook_create_and_detail(self, auth_client, base_financial_setup):
        create_url = reverse('cheques:checkbook_create')
        post_data = {
            'bank_account': base_financial_setup['bank'].id,
            'name': 'دفتر بنك مصر فرع الدقي',
            'serial_prefix': 'DQ',
            'serial_from': 7001,
            'serial_to': 7005,
            'is_active': True,
        }
        res = auth_client.post(create_url, data=post_data)
        assert res.status_code == 302

        cb = Checkbook.objects.get(name='دفتر بنك مصر فرع الدقي')
        assert cb.leaf_count == 5
        assert cb.leaves.count() == 5

        detail_url = reverse('cheques:checkbook_detail', kwargs={'pk': cb.pk})
        detail_res = auth_client.get(detail_url)
        assert detail_res.status_code == 200
        assert 'DQ7001' in detail_res.content.decode('utf-8')


@pytest.mark.django_db
class TestChequePrintAndReconciliationIntegration:
    """اختبارات الطباعة بالتفقيط والتكامل مع مرشحي التسوية البنكية"""

    def test_cheque_print_view_with_arabic_tafqeet(self, auth_client, sample_receivable_cheque):
        url = reverse('cheques:cheque_print', kwargs={'pk': sample_receivable_cheque.pk})
        res = auth_client.get(url)
        assert res.status_code == 200
        content = res.content.decode('utf-8')
        assert 'خمسة عشر ألف' in content  # تفقيط 15,000 ج.م بالعربية
        assert 'فقط' in content
        assert 'لا غير' in content

    def test_bank_candidate_engine_returns_cheques_for_reconciliation(self, base_financial_setup, sample_receivable_cheque, sample_payable_cheque):
        """التحقق من أن محول المرشحين يفرز الشيكات برسم التحصيل للإيداعات وشيكات الدفع للسحب"""
        # جعل شيك القبض برسم التحصيل في البنك
        sample_receivable_cheque.status = ChequeStatus.UNDER_COLLECTION
        sample_receivable_cheque.deposit_bank_account = base_financial_setup['bank']
        sample_receivable_cheque.save()

        # حركة إيداع بنكي بكشف الحساب (debit > 0)
        from types import SimpleNamespace
        inflow_stmt_line = SimpleNamespace(
            debit=Decimal('15000.00'),
            credit=Decimal('0.00'),
            transaction_date=timezone.now().date(),
        )

        candidates_inflow = BankCandidateEngine.get_cheque_candidates(
            bank_account=base_financial_setup['bank'],
            stmt_line=inflow_stmt_line
        )
        assert len(candidates_inflow) >= 1
        assert any(c.id == sample_receivable_cheque.id for c in candidates_inflow)

        # حركة خصم وسحب بنكي بكشف الحساب (credit > 0)
        outflow_stmt_line = SimpleNamespace(
            debit=Decimal('0.00'),
            credit=Decimal('25000.00'),
            transaction_date=timezone.now().date(),
        )
        candidates_outflow = BankCandidateEngine.get_cheque_candidates(
            bank_account=base_financial_setup['bank'],
            stmt_line=outflow_stmt_line
        )
        assert len(candidates_outflow) >= 1
        assert any(c.id == sample_payable_cheque.id for c in candidates_outflow)
