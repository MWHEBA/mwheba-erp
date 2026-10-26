# -*- coding: utf-8 -*-
from decimal import Decimal
import pytest
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

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
    ChequeActionType,
    ChequeInvoiceAllocation,
    AllocationStatus,
)
from financial.models import (
    Currency,
    ChartOfAccounts,
    AccountType,
    UserTreasuryAccess,
)
from financial.services.bank_reconciliation_service import BankCandidateEngine
from financial.services.subledger_account_service import SubledgerAccountService
from customer.models import Customer
from sale.models import Sale

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
    today = timezone.localdate()
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
    today = timezone.localdate()
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

        today = timezone.localdate()
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
            'action_date': str(timezone.localdate()),
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
            'action_date': str(timezone.localdate()),
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
            'clearing_date': str(timezone.localdate())
        }
        res = auth_client.post(url, data=post_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert res.status_code == 200
        assert res.json()['success'] is True

        sample_payable_cheque.refresh_from_db()
        assert sample_payable_cheque.status == ChequeStatus.CLEARED

    def test_cheque_clear_action_payable_with_custom_exchange_rate(self, auth_client, test_user, base_financial_setup):
        """صرف شيك دفع بسعر صرف فعلي مختلف وتوليد قيد الخصم بنجاح"""
        today = timezone.localdate()
        usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "دولار", "symbol": "$"})
        foreign_payable = Cheque.objects.create(
            cheque_type=ChequeType.PAYABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.ISSUED,
            voucher_number="CHQP-FX-00001",
            cheque_number="FX-9901",
            amount=Decimal("1000.00"),
            currency=usd,
            original_exchange_rate=Decimal("50.000000"),
            functional_amount=Decimal("50000.00"),
            book_value_functional=Decimal("50000.00"),
            remaining_amount=Decimal("1000.00"),
            remaining_functional=Decimal("50000.00"),
            issue_date=today,
            due_date=today,
            drawer_bank_name="Banque Misr",
            drawer_name="موهبة",
            payee_name="المورد الخارجي",
            deposit_bank_account=base_financial_setup['bank'],
            created_by=test_user,
        )

        url = reverse('cheques:cheque_clear_action', kwargs={'pk': foreign_payable.pk})
        post_data = {
            'clearing_date': str(timezone.localdate()),
            'exchange_rate': '52.000000',
            'bank_account': base_financial_setup['bank'].id,
            'notes': 'صرف بسعر 52 مع احتساب خسائر فروق عملة',
        }
        res = auth_client.post(url, data=post_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert res.status_code == 200
        assert res.json()['success'] is True

        foreign_payable.refresh_from_db()
        assert foreign_payable.status == ChequeStatus.CLEARED
        action_log = foreign_payable.action_logs.filter(action=ChequeActionType.CLEAR).first()
        assert action_log is not None
        assert action_log.journal_entry is not None

    def test_convert_guarantee_modal_approval_notes_rendering(self, auth_client, test_user, base_financial_setup):
        """التحقق من ظهور حقل approval_notes في مودال تحويل شيك الضمان"""
        today = timezone.localdate()
        guarantee_cheque = Cheque.objects.create(
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.SECURITY_GUARANTEE,
            status=ChequeStatus.IN_PORTFOLIO,
            voucher_number="CHQR-GUAR-00001",
            cheque_number="GUAR-1001",
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
            drawer_name="العميل الضامن",
            payee_name="موهبة",
            created_by=test_user,
        )

        url = reverse('cheques:receivable_detail', kwargs={'pk': guarantee_cheque.pk})
        res = auth_client.get(url)
        assert res.status_code == 200
        content = res.content.decode('utf-8')
        assert 'name="approval_notes"' in content
        assert 'convertGuaranteeModal' in content

    def test_cheque_return_to_drawer_action_endpoint(self, auth_client, sample_receivable_cheque):
        """التحقق من تنفيذ رد الشيك للساحب وترحيل قيده وإقفال الشيك"""
        url = reverse('cheques:cheque_return_to_drawer_action', kwargs={'pk': sample_receivable_cheque.pk})
        post_data = {
            'action_date': str(timezone.localdate()),
            'reason': 'طلب العميل استبدال الشيك بسداد نقدي مباشر',
        }
        res = auth_client.post(url, data=post_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert res.status_code == 200
        assert res.json()['success'] is True

        sample_receivable_cheque.refresh_from_db()
        assert sample_receivable_cheque.status == ChequeStatus.RETURNED_TO_DRAWER
        action_log = sample_receivable_cheque.action_logs.filter(action=ChequeActionType.RETURN_TO_DRAWER).first()
        assert action_log is not None
        assert action_log.journal_entry is not None

    def test_payable_convert_guarantee_modal_and_action(self, auth_client, test_user, base_financial_setup):
        """التحقق من ظهور مودال تحويل الضمان لشيك الدفع واعتماد تحويله لتشغيلي بنجاح"""
        today = timezone.localdate()
        guarantee_payable = Cheque.objects.create(
            cheque_type=ChequeType.PAYABLE,
            purpose=ChequePurpose.SECURITY_GUARANTEE,
            status=ChequeStatus.ISSUED,
            voucher_number="CHQP-GUAR-00001",
            cheque_number="GUAR-PAY-01",
            amount=Decimal("20000.00"),
            currency=base_financial_setup['currency'],
            original_exchange_rate=Decimal("1.000000"),
            functional_amount=Decimal("20000.00"),
            book_value_functional=Decimal("20000.00"),
            remaining_amount=Decimal("20000.00"),
            remaining_functional=Decimal("20000.00"),
            issue_date=today,
            due_date=today,
            drawer_bank_name="Banque Misr",
            drawer_name="موهبة",
            payee_name="مورد أجهزة",
            deposit_bank_account=base_financial_setup['bank'],
            created_by=test_user,
        )

        # 1. فحص ظهور المودال وزر التحويل في الواجهة
        detail_url = reverse('cheques:payable_detail', kwargs={'pk': guarantee_payable.pk})
        detail_res = auth_client.get(detail_url)
        assert detail_res.status_code == 200
        detail_content = detail_res.content.decode('utf-8')
        assert 'convertGuaranteeModal' in detail_content
        assert 'name="approval_notes"' in detail_content

        # 2. تنفيذ إجراء التحويل عبر POST endpoint
        action_url = reverse('cheques:cheque_convert_guarantee_action', kwargs={'pk': guarantee_payable.pk})
        post_data = {
            'new_purpose': ChequePurpose.INVOICE_SETTLEMENT,
            'approval_notes': 'اعتماد تحويل شيك ضمان الدفع لتشغيلي بعد استلام البضاعة',
        }
        action_res = auth_client.post(action_url, data=post_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert action_res.status_code == 200
        assert action_res.json()['success'] is True

        guarantee_payable.refresh_from_db()
        assert guarantee_payable.purpose == ChequePurpose.INVOICE_SETTLEMENT
        assert guarantee_payable.is_guarantee is False
        action_log = guarantee_payable.action_logs.filter(action=ChequeActionType.CONVERT_GUARANTEE).first()
        assert action_log is not None
        assert action_log.journal_entry is not None

    def test_action_buttons_hidden_without_permissions(self, client, test_user, sample_receivable_cheque, sample_payable_cheque):
        """التحقق من حجب أزرار العمليات في قوالب الشيكات للمستخدم الذي لا يملك الصلاحيات"""
        readonly_user = User.objects.create_user(
            username="readonly_viewer",
            email="readonly@mwheba.com",
            password="ViewerPassword123!",
            is_staff=True,
            is_superuser=False,
        )
        view_perm = Permission.objects.get(codename='view_cheque')
        readonly_user.user_permissions.add(view_perm)
        client.force_login(readonly_user)

        # فحص تفاصيل الوارد
        rec_url = reverse('cheques:receivable_detail', kwargs={'pk': sample_receivable_cheque.pk})
        rec_res = client.get(rec_url)
        assert rec_res.status_code == 200
        rec_content = rec_res.content.decode('utf-8')
        assert 'data-bs-target="#depositModal"' not in rec_content
        assert 'data-bs-target="#endorseModal"' not in rec_content
        assert 'data-bs-target="#returnToDrawerModal"' not in rec_content

        # فحص تفاصيل الصادر
        pay_url = reverse('cheques:payable_detail', kwargs={'pk': sample_payable_cheque.pk})
        pay_res = client.get(pay_url)
        assert pay_res.status_code == 200
        pay_content = pay_res.content.decode('utf-8')
        assert 'data-bs-target="#clearModal"' not in pay_content
        assert 'data-bs-target="#bounceModal"' not in pay_content




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
            'deposit_date': str(timezone.localdate()),
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

    def test_cheque_print_view_applies_bank_layout_calibration(self, auth_client, sample_payable_cheque, base_financial_setup):
        """التحقق من أن معايرة أبعاد الطباعة وقالب البنك تطبق بدقة في CSS للقالب"""
        sample_payable_cheque.deposit_bank_account = base_financial_setup['bank']
        sample_payable_cheque.save()

        BankChequeLayout.objects.create(
            bank_account=base_financial_setup['bank'],
            template_name="قالب البنك الأهلي المخصص",
            paper_width_mm=Decimal('195.00'),
            paper_height_mm=Decimal('82.50'),
            date_pos_x_mm=Decimal('142.00'),
            date_pos_y_mm=Decimal('16.00'),
            font_size_pt=11,
            is_default=True
        )

        url = reverse('cheques:cheque_print', kwargs={'pk': sample_payable_cheque.pk})
        res = auth_client.get(url)
        assert res.status_code == 200
        content = res.content.decode('utf-8')

        assert '195.00mm' in content
        assert '82.50mm' in content
        assert '142.00mm' in content
        assert '16.00mm' in content
        assert '11pt' in content
        assert 'قالب البنك الأهلي المخصص' in content


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
            transaction_date=timezone.localdate(),
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
            transaction_date=timezone.localdate(),
        )
        candidates_outflow = BankCandidateEngine.get_cheque_candidates(
            bank_account=base_financial_setup['bank'],
            stmt_line=outflow_stmt_line
        )
        assert len(candidates_outflow) >= 1
        assert any(c.id == sample_payable_cheque.id for c in candidates_outflow)


@pytest.mark.django_db
class TestChequeAllocationUIAndActions:
    """
    اختبارات تخصيص أوراق القبض على فواتير المبيعات وعكس التخصيص وواجهة المستخدم (المرحلة 3)
    """

    @pytest.fixture
    def customer_and_sale(self, base_financial_setup, test_user):
        customer, _ = Customer.objects.get_or_create(
            name="عميل التخصيص التجاري",
            defaults={"code": "CUST-ALLOC-01", "phone": "01099887766"}
        )
        SubledgerAccountService.get_or_create_customer_account(customer, user=test_user)
        customer.refresh_from_db()

        sale = Sale.objects.create(
            customer=customer,
            date=timezone.localdate(),
            subtotal=Decimal("10000.00"),
            total=Decimal("10000.00"),
            currency=base_financial_setup["currency"],
            exchange_rate=Decimal("1.000000"),
            total_functional=Decimal("10000.00"),
            payment_method="credit",
            payment_status="unpaid",
            status="confirmed",
            created_by=test_user,
        )
        return customer, sale

    @pytest.fixture
    def receivable_cheque_for_allocation(self, base_financial_setup, customer_and_sale, test_user):
        customer, sale = customer_and_sale
        cheque = Cheque.objects.create(
            cheque_number="CHQ-ALLOC-1001",
            voucher_number="V-ALLOC-1001",
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.IN_PORTFOLIO,
            amount=Decimal("6000.00"),
            remaining_amount=Decimal("6000.00"),
            customer=customer,
            drawer_name="ساحب التخصيص",
            currency=base_financial_setup["currency"],
            original_exchange_rate=Decimal("1.000000"),
            issue_date=timezone.localdate(),
            due_date=timezone.localdate() + timezone.timedelta(days=15),
            created_by=test_user,
        )
        return cheque

    def test_receivable_detail_renders_allocation_table_and_modal(
        self, auth_client, receivable_cheque_for_allocation, customer_and_sale
    ):
        """التحقق من أن صفحة تفاصيل الشيك تعرض جدول التخصيصات وزر التخصيص والمودال"""
        url = reverse("cheques:receivable_detail", kwargs={"pk": receivable_cheque_for_allocation.pk})
        res = auth_client.get(url)
        assert res.status_code == 200
        content = res.content.decode("utf-8")

        assert "تخصيصات الشيك على فواتير المبيعات" in content
        assert "المتاح للتخصيص:" in content
        assert "6,000.00" in content
        assert "allocateInvoiceModal" in content
        assert "تخصيص على فاتورة" in content

    def test_allocate_cheque_to_invoice_success(
        self, auth_client, receivable_cheque_for_allocation, customer_and_sale
    ):
        """التحقق من نجاح تخصيص الشيك على فاتورة مبيعات وتحديث رصيدها وسجل التدقيق"""
        customer, sale = customer_and_sale
        url = reverse("cheques:cheque_allocate_invoice_action", kwargs={"pk": receivable_cheque_for_allocation.pk})

        post_data = {
            "sale": sale.id,
            "amount": "4000.00",
            "notes": "تخصيص دفعة جزئية من شيك القبض",
            "idempotency_key": "IDEM-ALLOC-TEST-1",
        }
        res = auth_client.post(url, post_data, follow=True)
        assert res.status_code == 200

        # التحقق من إنشاء سجل التخصيص
        allocation = ChequeInvoiceAllocation.objects.filter(
            cheque=receivable_cheque_for_allocation,
            sale=sale
        ).first()
        assert allocation is not None
        assert allocation.allocated_amount == Decimal("4000.00")
        assert allocation.allocation_status == AllocationStatus.APPLIED
        assert allocation.allocation_audit is not None

        # التحقق من تحديث الفاتورة
        sale.refresh_from_db()
        assert sale.amount_due == Decimal("6000.00")
        assert sale.payment_status in ["partial", "partially_paid"]

        # التحقق من ظهور التخصيص وزر فك التخصيص في تفاصيل الشيك
        detail_url = reverse("cheques:receivable_detail", kwargs={"pk": receivable_cheque_for_allocation.pk})
        detail_res = auth_client.get(detail_url)
        detail_content = detail_res.content.decode("utf-8")
        assert sale.number in detail_content
        assert "4000.00" in detail_content
        assert f"deallocateModal-{allocation.id}" in detail_content

    def test_allocate_cheque_validation_exceeds_available(
        self, auth_client, receivable_cheque_for_allocation, customer_and_sale
    ):
        """التحقق من رفض التخصيص إذا كان المبلغ المطلوب يتجاوز الرصيد غير المخصص في الشيك"""
        customer, sale = customer_and_sale
        url = reverse("cheques:cheque_allocate_invoice_action", kwargs={"pk": receivable_cheque_for_allocation.pk})

        # رصيد الشيك 6000، نطلب 8000
        post_data = {
            "sale": sale.id,
            "amount": "8000.00",
            "notes": "تخصيص بمبلغ يتجاوز رصيد الشيك",
        }
        res = auth_client.post(url, post_data, follow=True)
        assert res.status_code == 200

        # لم يتم إنشاء أي تخصيص
        assert not ChequeInvoiceAllocation.objects.filter(cheque=receivable_cheque_for_allocation).exists()
        sale.refresh_from_db()
        assert sale.amount_due == Decimal("10000.00")

    def test_deallocate_cheque_action_success(
        self, auth_client, receivable_cheque_for_allocation, customer_and_sale
    ):
        """التحقق من نجاح فك التخصيص وإلغائه واستعادة مديونية الفاتورة ورصيد الشيك"""
        customer, sale = customer_and_sale

        # أولاً: إجراء التخصيص
        alloc_url = reverse("cheques:cheque_allocate_invoice_action", kwargs={"pk": receivable_cheque_for_allocation.pk})
        auth_client.post(alloc_url, {"sale": sale.id, "amount": "3000.00"})

        allocation = ChequeInvoiceAllocation.objects.get(cheque=receivable_cheque_for_allocation, sale=sale)
        assert allocation.allocation_status == AllocationStatus.APPLIED

        # ثانياً: إرسال طلب فك التخصيص
        dealloc_url = reverse(
            "cheques:cheque_deallocate_invoice_action",
            kwargs={"pk": receivable_cheque_for_allocation.pk, "allocation_id": allocation.id}
        )
        res = auth_client.post(dealloc_url, {"reason": "إلغاء التخصيص بناءً على طلب العميل"}, follow=True)
        assert res.status_code == 200

        # التحقق من تحول حالة التخصيص إلى REVERSED
        allocation.refresh_from_db()
        assert allocation.allocation_status == AllocationStatus.REVERSED

        # التحقق من استعادة مديونية الفاتورة
        sale.refresh_from_db()
        assert sale.amount_due == Decimal("10000.00")
        assert sale.payment_status == "unpaid"

    def test_allocation_requires_change_cheque_permission(
        self, client, receivable_cheque_for_allocation, customer_and_sale
    ):
        """التحقق من أن التخصيص وفك التخصيص يتطلبان صلاحية cheques.change_cheque"""
        unauthorized_user = User.objects.create_user(
            username="unauth_alloc_user",
            email="unauth_alloc@mwheba.com",
            password="Password123!",
            is_staff=True,
            is_superuser=False,
        )
        client.force_login(unauthorized_user)

        customer, sale = customer_and_sale
        url = reverse("cheques:cheque_allocate_invoice_action", kwargs={"pk": receivable_cheque_for_allocation.pk})
        res = client.post(url, {"sale": sale.id, "amount": "1000.00"})
        assert res.status_code == 403

    def test_allocate_cheque_idempotency_prevents_duplicate_deduction(
        self, auth_client, receivable_cheque_for_allocation, customer_and_sale
    ):
        """التحقق من أن إرسال نفس الطلب مرتين بنفس مفتاح منع التكرار لا ينشئ تخصيصين ولا يخصم الفاتورة مرتين"""
        customer, sale = customer_and_sale
        url = reverse("cheques:cheque_allocate_invoice_action", kwargs={"pk": receivable_cheque_for_allocation.pk})

        post_data = {
            "sale": sale.id,
            "amount": "1000.00",
            "idempotency_key": "IDEM-DUP-TEST-KEY-999",
        }
        # الطلب الأول
        res1 = auth_client.post(url, post_data, follow=True)
        assert res1.status_code == 200

        # الطلب الثاني بنفس المفتاح بالضبط
        res2 = auth_client.post(url, post_data, follow=True)
        assert res2.status_code == 200

        # التحقق الحتمي: تخصيص واحد فقط
        allocations = ChequeInvoiceAllocation.objects.filter(
            cheque=receivable_cheque_for_allocation,
            sale=sale,
            allocation_status=AllocationStatus.APPLIED
        )
        assert allocations.count() == 1
        assert allocations.first().allocated_amount == Decimal("1000.00")

        # التحقق من أن الفاتورة خُصم منها 1000 فقط وليس 2000
        sale.refresh_from_db()
        assert sale.amount_due == Decimal("9000.00")

    def test_allocate_cheque_same_idempotency_key_different_amount_rejected(
        self, auth_client, customer_and_sale, receivable_cheque_for_allocation
    ):
        """التحقق من رفض إعادة استخدام مفتاح التخصيص بمبلغ مختلف واكتشاف التعارض"""
        customer, sale = customer_and_sale
        url = reverse("cheques:cheque_allocate_invoice_action", kwargs={"pk": receivable_cheque_for_allocation.pk})
        shared_key = "IDEM-CONFLICT-TEST"

        # الطلب الأول بمبلغ 1000
        res1 = auth_client.post(url, {
            "sale": sale.id,
            "amount": "1000.00",
            "idempotency_key": shared_key,
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert res1.status_code == 200
        assert res1.json()["success"] is True

        # الطلب الثاني بنفس المفتاح ولكن بمبلغ 2000
        res2 = auth_client.post(url, {
            "sale": sale.id,
            "amount": "2000.00",
            "idempotency_key": shared_key,
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert res2.status_code in [200, 400]
        assert res2.json()["success"] is False
        assert "تعارض في مفتاح عدم التكرار" in res2.json()["message"]

        # التأكد من بقاء التخصيص كما هو بمبلغ 1000 دون تعديل
        allocs = ChequeInvoiceAllocation.objects.filter(cheque=receivable_cheque_for_allocation)
        assert allocs.count() == 1
        assert allocs.first().allocated_amount == Decimal("1000.00")

    def test_allocate_cheque_exact_replay_after_full_allocation_succeeds(
        self, auth_client, customer_and_sale, receivable_cheque_for_allocation
    ):
        """التحقق من أن إعادة إرسال نفس الطلب بعد استنفاد رصيد الشيك بالكامل ترجع نجاحاً متطابقاً دون فشل كاذب"""
        customer, sale = customer_and_sale
        url = reverse("cheques:cheque_allocate_invoice_action", kwargs={"pk": receivable_cheque_for_allocation.pk})
        shared_key = "IDEM-FULL-REPLAY-TEST"

        # تخصيص كامل رصيد الشيك المتاح (6000)
        res1 = auth_client.post(url, {
            "sale": sale.id,
            "amount": "6000.00",
            "idempotency_key": shared_key,
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert res1.status_code == 200
        assert res1.json()["success"] is True

        # إعادة إرسال نفس الطلب بالضبط بنفس المفتاح
        res2 = auth_client.post(url, {
            "sale": sale.id,
            "amount": "6000.00",
            "idempotency_key": shared_key,
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert res2.status_code == 200
        assert res2.json()["success"] is True

        # التأكد من وجود تخصيص واحد فقط بمبلغ 6,000
        allocs = ChequeInvoiceAllocation.objects.filter(cheque=receivable_cheque_for_allocation)
        assert allocs.count() == 1
        assert allocs.first().allocated_amount == Decimal("6000.00")


@pytest.mark.django_db
class TestChequeClearSecurityAndPrintCalibrationGaps:
    """
    اختبارات معالجة ثغرة حسابات المقاصة غير المصرحة ومعايرة السطر الثاني للتفقيط وإخفاء زر الطباعة
    """

    def test_clear_payable_cheque_blocks_unauthorized_bank_account(
        self, client, sample_payable_cheque, base_financial_setup
    ):
        """التحقق من رفض مقاصة الشيك على حساب أوراق القبض أو على حساب غير مصرح للمستخدم"""
        clear_user = User.objects.create_user(
            username="clear_only_user",
            email="clear_only@mwheba.com",
            password="Password123!",
            is_staff=True,
            is_superuser=False,
        )
        ct = ContentType.objects.get_for_model(Cheque)
        perm, _ = Permission.objects.get_or_create(
            codename="collect_cheque",
            content_type=ct,
            defaults={"name": "Can collect cheque"}
        )
        view_perm, _ = Permission.objects.get_or_create(
            codename="view_cheque",
            content_type=ct,
            defaults={"name": "Can view cheque"}
        )
        clear_user.user_permissions.add(perm, view_perm)
        client.force_login(clear_user)

        # المستخدم ليس لديه أي خزائن مصرح بها في UserTreasuryAccess
        url = reverse("cheques:cheque_clear_action", kwargs={"pk": sample_payable_cheque.pk})
        
        # محاولة الصرف على حساب أوراق القبض (غير بنكي)
        res = client.post(url, {
            "bank_account": base_financial_setup["notes_rec"].id,
            "clearing_date": timezone.localdate().isoformat(),
            "exchange_rate": "1.000000",
        }, follow=True)

        # التأكد من عدم تحول الشيك إلى CLEARED وبقائه على حالته
        sample_payable_cheque.refresh_from_db()
        assert sample_payable_cheque.status != ChequeStatus.CLEARED

    def test_header_buttons_print_cheque_permission_gate(
        self, client, sample_receivable_cheque, sample_payable_cheque
    ):
        """التحقق من عدم ظهور زر الطباعة في رأس الصفحة لمستخدم لا يملك صلاحية print_cheque"""
        view_only_user = User.objects.create_user(
            username="view_only_user",
            email="view_only@mwheba.com",
            password="Password123!",
            is_staff=True,
            is_superuser=False,
        )
        ct = ContentType.objects.get_for_model(Cheque)
        view_perm, _ = Permission.objects.get_or_create(
            codename="view_cheque",
            content_type=ct,
            defaults={"name": "Can view cheque"}
        )
        view_only_user.user_permissions.add(view_perm)
        client.force_login(view_only_user)

        # شيك القبض
        res_rec = client.get(reverse("cheques:receivable_detail", kwargs={"pk": sample_receivable_cheque.pk}))
        assert res_rec.status_code == 200
        assert "طباعة إشعار الاستلام" not in res_rec.content.decode("utf-8")

        # شيك الدفع
        res_pay = client.get(reverse("cheques:payable_detail", kwargs={"pk": sample_payable_cheque.pk}))
        assert res_pay.status_code == 200
        assert "طباعة الشيك البنكي" not in res_pay.content.decode("utf-8")

    def test_cheque_print_calibrates_line2_words_and_position(
        self, auth_client, sample_payable_cheque, base_financial_setup
    ):
        """التحقق من أن طباعة الشيك تستخدم إعدادات السطر الثاني للتفقيط وتعرضه في عنصر منفصل"""
        # إنشاء قالب مخصص به موضع السطر الثاني
        layout, _ = BankChequeLayout.objects.get_or_create(
            bank_account=base_financial_setup["bank"],
            template_name="قالب سطرين للتفقيط",
            defaults={
                "is_default": True,
                "amount_words_line1_pos_y_mm": Decimal("44.00"),
                "amount_words_line1_pos_x_mm": Decimal("42.00"),
                "amount_words_line2_pos_y_mm": Decimal("56.00"),
                "amount_words_line2_pos_x_mm": Decimal("42.00"),
            }
        )
        layout.amount_words_line2_pos_y_mm = Decimal("56.00")
        layout.is_default = True
        layout.save()

        # ضبط الشيك بمبلغ كبير يتطلب تفقيطاً طويلاً
        Cheque.objects.filter(pk=sample_payable_cheque.pk).update(
            amount=Decimal("1875432.50"),
            remaining_amount=Decimal("1875432.50"),
            remaining_functional=Decimal("1875432.50")
        )

        url = reverse("cheques:cheque_print", kwargs={"pk": sample_payable_cheque.pk})
        res = auth_client.get(url)
        assert res.status_code == 200
        content = res.content.decode("utf-8")

        # التحقق من وجود السطر الثاني وإحداثياته في الـ CSS والـ HTML
        assert "field-amount-words-line2" in content
        assert "56.00mm" in content

    def test_clear_payable_cheque_blocks_non_bank_account_11190_even_for_admin(
        self, auth_client, sample_payable_cheque, base_financial_setup
    ):
        """التحقق من رفض مقاصة الشيك على حساب 11190 (شيكات برسم التحصيل) حتى لو كان المستخدم أدمن"""
        url = reverse("cheques:cheque_clear_action", kwargs={"pk": sample_payable_cheque.pk})
        res = auth_client.post(url, {
            "bank_account": base_financial_setup["coll_acc"].id,  # 11190
            "clearing_date": timezone.localdate().isoformat(),
            "exchange_rate": "1.000000",
        }, follow=True)

        sample_payable_cheque.refresh_from_db()
        assert sample_payable_cheque.status != ChequeStatus.CLEARED



