# -*- coding: utf-8 -*-
from decimal import Decimal
import pytest
from django.urls import reverse
from django.test import Client
from django.contrib.auth import get_user_model
from django.core.cache import cache

from core.models import SystemModule
from core.middleware.module_control import ModuleAccessMiddleware
from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    ContractorProgressCertificate,
    RealEstateBroker,
    BrokerCommission,
    BrokerAttributionAudit,
)
from supplier.models import Supplier
from customer.models import Customer
from financial.models import ChartOfAccounts, AccountType, Currency, EnterpriseApprovalRule
from financial.services.role_registry import AccountRoleNames

User = get_user_model()


@pytest.fixture
def phase5_1_setup(db):
    cache.delete('enabled_modules_set')
    cache.delete('module_namespace_map')

    mod, _ = SystemModule.objects.get_or_create(code='real_estate', defaults={'name_ar': 'العقارات', 'is_enabled': True})
    mod.is_enabled = True
    mod.save()
    ModuleAccessMiddleware.invalidate_cache()

    user = User.objects.create_superuser(username='admin_crud_test', password='password123', email='crud@test.com')
    client = Client()
    client.login(username='admin_crud_test', password='password123')

    # Currency
    curr, _ = Currency.objects.get_or_create(code='EGP', defaults={'name': 'Egyptian Pound', 'symbol': 'ج.م', 'is_functional': True})

    # Account Types
    asset_type, _ = AccountType.objects.get_or_create(
        code='asset',
        defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
    )
    liability_type, _ = AccountType.objects.get_or_create(
        code='liability',
        defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'}
    )
    expense_type, _ = AccountType.objects.get_or_create(
        code='expense',
        defaults={'name': 'مصروفات', 'category': 'expense', 'nature': 'debit'}
    )

    # Accounts
    wip_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="12101",
        defaults={'name': 'WIP Construction Project Cost', 'account_type': asset_type, 'is_leaf': True, 'is_active': True}
    )
    retention_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21310",
        defaults={'name': 'Contractor Retentions Payable', 'account_type': liability_type, 'is_leaf': True, 'is_active': True}
    )
    payable_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21110",
        defaults={'name': 'Supplier Control Account', 'account_type': liability_type, 'is_leaf': True, 'is_active': True}
    )
    wht_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21330",
        defaults={'name': 'Withholding Tax Payable', 'account_type': liability_type, 'is_leaf': True, 'is_active': True}
    )
    adv_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11350",
        defaults={'name': 'Contractor Advance Payments', 'account_type': asset_type, 'is_leaf': True, 'is_active': True}
    )
    cash_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11110",
        defaults={'name': 'Treasury Cash', 'account_type': asset_type, 'is_leaf': True, 'is_active': True}
    )
    comm_exp_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="52510",
        defaults={'name': 'Broker Commissions Expense', 'account_type': expense_type, 'is_leaf': True, 'is_active': True}
    )

    for acc in [wip_acc, retention_acc, payable_acc, wht_acc, adv_acc, cash_acc, comm_exp_acc]:
        acc.is_active = True
        acc.is_leaf = True
        acc.children.all().delete()
        acc.save()

    # Project & Contractor
    project = RealEstateProject.objects.create(
        code='PRJ-CRUD',
        name='مشروع الزمردة التنفيذي',
        project_type=RealEstateProject.ProjectType.RESIDENTIAL,
        status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
        total_land_area=4000,
        gross_built_area=9000,
        start_date='2026-01-01',
        expected_completion_date='2027-01-01',
        created_by=user
    )

    contractor = Supplier.objects.create(
        name='شركة الأهرام للمقاولات العامة',
        financial_account=payable_acc,
        is_active=True
    )

    customer = Customer.objects.create(
        name='محمد علي المستثمر',
        phone='01009988776',
        is_active=True
    )

    block = PropertyBlock.objects.create(project=project, code='B1', name='عمارة 1')
    floor = PropertyFloor.objects.create(block=block, floor_number=1, name='الدور الأول')
    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code='U-101',
        unit_type=PropertyUnit.UnitType.APARTMENT,
        gross_area=Decimal('150.00'),
        net_area=Decimal('130.00'),
        meter_price=Decimal('10000.00'),
        base_price=Decimal('1500000.00'),
        total_price=Decimal('1500000.00'),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    contract = PropertyContract.objects.create(
        contract_number='CONT-CRUD-001',
        project=project,
        unit=unit,
        customer=customer,
        contract_date='2026-02-01',
        delivery_date='2027-01-01',
        final_contract_price=Decimal('1500000.00'),
        down_payment=Decimal('300000.00'),
        status=PropertyContract.ContractStatus.ACTIVE,
        currency=curr,
        created_by=user
    )

    EnterpriseApprovalRule.objects.create(
        module='REAL_ESTATE',
        rule_name='مستخلصات المقاولين العامة',
        min_amount=Decimal('0.00'),
        max_amount=Decimal('50000000.00'),
        currency='EGP',
        approver_role='SUPERADMIN',
        is_active=True
    )

    return {
        'client': client,
        'user': user,
        'project': project,
        'contractor': contractor,
        'currency': curr,
        'contract': contract,
        'customer': customer,
        'cash_acc': cash_acc
    }


@pytest.mark.django_db
def test_contractor_certificate_create_and_detail_views(phase5_1_setup):
    client = phase5_1_setup['client']
    project = phase5_1_setup['project']
    contractor = phase5_1_setup['contractor']
    curr = phase5_1_setup['currency']

    # 1. GET Create Form
    url_create = reverse('real_estate:contractor_create')
    resp_get = client.get(url_create)
    assert resp_get.status_code == 200
    assert 'real_estate/contractor_form.html' in [t.name for t in resp_get.templates]

    # 2. POST Create Certificate
    payload = {
        'certificate_number': 'CERT-TEST-001',
        'project': project.id,
        'contractor': contractor.id,
        'contract_reference': 'PO-9988',
        'period_start': '2026-03-01',
        'period_end': '2026-03-31',
        'currency': curr.id,
        'gross_certified_work': '500000.00',
        'previous_certified_work': '100000.00',
        'materials_on_site': '50000.00',
        'retention_rate': '5.00',
        'advance_payment_recovery': '20000.00',
        'wht_rate': '1.00',
        'penalty_deductions': '5000.00',
        'notes': 'أعمال صب الخرسانة المسلحة للأعمدة'
    }
    resp_post = client.post(url_create, payload)
    assert resp_post.status_code == 302

    cert = ContractorProgressCertificate.objects.get(certificate_number='CERT-TEST-001')
    assert cert.current_period_work == Decimal('400000.00')
    # base = 400000 + 50000 = 450000
    # retention = 450000 * 5% = 22500
    assert cert.retention_amount == Decimal('22500.00')
    # wht = 400000 * 1% = 4000
    assert cert.wht_amount == Decimal('4000.00')
    # net = 400000 + 50000 - 22500 - 20000 - 4000 - 5000 = 398500
    assert cert.net_amount == Decimal('398500.00')
    assert cert.status == ContractorProgressCertificate.CertificateStatus.DRAFT

    # 3. GET Detail View
    url_detail = reverse('real_estate:contractor_detail', kwargs={'pk': cert.pk})
    resp_detail = client.get(url_detail)
    assert resp_detail.status_code == 200
    assert 'real_estate/contractor_detail.html' in [t.name for t in resp_detail.templates]
    detail_content = resp_detail.content.decode('utf-8')
    assert 'CERT-TEST-001' in detail_content
    assert '398,500.00' in detail_content


@pytest.mark.django_db
def test_contractor_certificate_update_and_approval_workflow(phase5_1_setup):
    client = phase5_1_setup['client']
    project = phase5_1_setup['project']
    contractor = phase5_1_setup['contractor']
    curr = phase5_1_setup['currency']
    user = phase5_1_setup['user']

    cert = ContractorProgressCertificate.objects.create(
        certificate_number='CERT-UP-001',
        project=project,
        contractor=contractor,
        period_start='2026-04-01',
        period_end='2026-04-30',
        currency=curr,
        gross_certified_work=Decimal('200000.00'),
        previous_certified_work=Decimal('0.00'),
        created_by=user
    )

    # 1. Update Certificate
    url_update = reverse('real_estate:contractor_update', kwargs={'pk': cert.pk})
    resp_get_update = client.get(url_update)
    assert resp_get_update.status_code == 200

    resp_post_update = client.post(url_update, {
        'gross_certified_work': '300000.00',
        'previous_certified_work': '50000.00',
        'materials_on_site': '10000.00',
        'retention_rate': '5.00',
        'advance_payment_recovery': '0.00',
        'wht_rate': '1.00',
        'penalty_deductions': '0.00',
        'period_start': '2026-04-01',
        'period_end': '2026-04-30',
        'currency': curr.id,
    })
    assert resp_post_update.status_code == 302
    cert.refresh_from_db()
    assert cert.gross_certified_work == Decimal('300000.00')
    assert cert.current_period_work == Decimal('250000.00')

    # 2. Submit for Approval
    url_submit = reverse('real_estate:contractor_submit', kwargs={'pk': cert.pk})
    resp_submit = client.post(url_submit)
    assert resp_submit.status_code == 302
    cert.refresh_from_db()
    assert cert.status == ContractorProgressCertificate.CertificateStatus.PENDING_APPROVAL
    assert cert.approval_snapshot_hash != ""

    # Approve request to test post GL
    cert.approval_request.status = 'APPROVED'
    cert.approval_request.save()

    # 3. Post to GL
    url_post_gl = reverse('real_estate:contractor_post_gl', kwargs={'pk': cert.pk})
    resp_post_gl = client.post(url_post_gl)
    assert resp_post_gl.status_code == 302
    cert.refresh_from_db()
    assert cert.status == ContractorProgressCertificate.CertificateStatus.APPROVED
    assert cert.journal_entry is not None


@pytest.mark.django_db
def test_broker_crud_views(phase5_1_setup):
    client = phase5_1_setup['client']

    # 1. GET Broker Create Form
    url_create = reverse('real_estate:broker_create')
    resp_get = client.get(url_create)
    assert resp_get.status_code == 200
    assert 'real_estate/broker_form.html' in [t.name for t in resp_get.templates]

    # 2. POST Create Broker
    payload = {
        'code': 'BRK-COLDWELL',
        'name': 'كولد ويل بانكر للتسويق العقاري',
        'broker_type': RealEstateBroker.BrokerType.AGENCY,
        'phone': '01223344556',
        'email': 'agency@coldwell.test',
        'contact_person': 'م. تامر الشناوي',
        'default_commission_rate': '3.00',
        'commercial_registration': 'CR-776655',
        'tax_id': 'TX-998811',
        'notes': 'عقد مسوق استراتيجي للمشروعات السكنية'
    }
    resp_post = client.post(url_create, payload)
    assert resp_post.status_code == 302

    broker = RealEstateBroker.objects.get(code='BRK-COLDWELL')
    assert broker.name == 'كولد ويل بانكر للتسويق العقاري'
    assert broker.default_commission_rate == Decimal('3.00')

    # 3. GET Broker Detail View
    url_detail = reverse('real_estate:broker_detail', kwargs={'pk': broker.pk})
    resp_detail = client.get(url_detail)
    assert resp_detail.status_code == 200
    assert 'real_estate/broker_detail.html' in [t.name for t in resp_detail.templates]
    assert 'BRK-COLDWELL' in resp_detail.content.decode('utf-8')

    # 4. Update Broker View
    url_update = reverse('real_estate:broker_update', kwargs={'pk': broker.pk})
    resp_update = client.post(url_update, {
        'name': 'كولد ويل بانكر مصر الجديدة',
        'broker_type': RealEstateBroker.BrokerType.AGENCY,
        'default_commission_rate': '3.50',
        'is_active': 'on'
    })
    assert resp_update.status_code == 302
    broker.refresh_from_db()
    assert broker.name == 'كولد ويل بانكر مصر الجديدة'
    assert broker.default_commission_rate == Decimal('3.50')


@pytest.mark.django_db
def test_broker_contract_assignment_and_commission_lifecycle(phase5_1_setup):
    client = phase5_1_setup['client']
    contract = phase5_1_setup['contract']
    user = phase5_1_setup['user']
    cash_acc = phase5_1_setup['cash_acc']

    broker = RealEstateBroker.objects.create(
        code='BRK-PRIME',
        name='برايم إستايت',
        broker_type=RealEstateBroker.BrokerType.AGENCY,
        default_commission_rate=Decimal('2.50'),
        created_by=user
    )

    # 1. Assign broker to contract
    url_assign = reverse('real_estate:contract_assign_broker', kwargs={'contract_id': contract.id})
    resp_assign = client.post(url_assign, {
        'broker': broker.id,
        'commission_rate': '2.50'
    })
    assert resp_assign.status_code == 302

    comm = BrokerCommission.objects.get(contract=contract, broker=broker)
    # 1,500,000 * 2.5% = 37,500
    assert comm.total_commission_amount == Decimal('37500.00')
    assert comm.staged_tranche_1_amount == Decimal('18750.00')
    assert comm.staged_tranche_2_amount == Decimal('18750.00')

    # 2. Evaluate Tranche Milestones
    # contract has 300,000 collected out of 1,500,000 (20% >= 10%), so tranche 1 should become ELIGIBLE
    url_eval = reverse('real_estate:commission_evaluate', kwargs={'pk': comm.pk})
    resp_eval = client.post(url_eval)
    assert resp_eval.status_code == 302
    comm.refresh_from_db()
    assert comm.tranche_1_status == BrokerCommission.TrancheStatus.ELIGIBLE

    # 3. Payout Tranche 1
    url_payout = reverse('real_estate:commission_payout', kwargs={'pk': comm.pk})
    resp_payout = client.post(url_payout, {
        'tranche': '1',
        'payment_account': cash_acc.id
    })
    assert resp_payout.status_code == 302
    comm.refresh_from_db()
    assert comm.tranche_1_status == BrokerCommission.TrancheStatus.PAID
    assert comm.tranche_1_journal_entry is not None
    assert comm.released_commission_amount == Decimal('18750.00')
    assert comm.remaining_commission == Decimal('18750.00')

    # 4. Commission List View renders correctly
    url_comm_list = reverse('real_estate:commission_list')
    resp_comm_list = client.get(url_comm_list)
    assert resp_comm_list.status_code == 200
    assert 'real_estate/commission_list.html' in [t.name for t in resp_comm_list.templates]
    assert 'BRK-PRIME' in resp_comm_list.content.decode('utf-8')
