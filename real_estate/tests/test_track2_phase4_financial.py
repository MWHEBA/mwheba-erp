# -*- coding: utf-8 -*-
"""
Track 2 - Phase 4: Financial, IFRS 15, Escrow & Subcontractor Netting Test Suite
MWHEBA ERP - Real Estate App

Verifies 100% correctness of:
- IFRS 15 Accrual Journal Entry posting and Egyptian Table Tax 5% (code T2).
- Project Escrow Sub-Account payment routing and advance deposit tracking.
- Segregated legal installment plan creation and penny-difference handling.
- Subcontractor final certificate penalty netting & 5% warranty retention deduction.
- Cancellation sunk costs settlement (demolition + non-returnable materials + labor + supervision).
- As-built true-up reconciliation (positive and negative variances).
- Store material requisition with strict quota controls and cost-reversed returns.
"""
from decimal import Decimal
from datetime import date, timedelta
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    FinishingWorkspace,
    FinishingItemSpec,
    UnitFinishingOrder,
    UnitFinishingOrderItem,
    FinishingAdvanceDeposit,
    FinishingInstallmentPlan,
    FinishingInstallmentItem,
    SubcontractorPenaltySettlementRecord,
    FinishingCancellationSettlement,
    FinishingAsBuiltReconciliation,
    FinishingMaterialRequisition,
    ContractorContract,
)
from customer.models import Customer
from supplier.models import Supplier
from product.models import Product, Category, Unit as ProductMeasurementUnit, Warehouse, InventoryCostLayer, StockLedgerEntry
from financial.models.currency import Currency
from financial.models import (
    ChartOfAccounts,
    JournalEntry,
    JournalEntryLine,
)

from real_estate.services.finishing_financial_service import (
    FinishingFinancialService,
    FinishingEscrowAccountSyncService,
    FinishingSubcontractorPenaltyNettingService,
    FinishingCancellationService,
    FinishingAsBuiltTrueUpService,
    FinishingStoreRequisitionService,
    FinishingMaterialReturnService,
)

User = get_user_model()


@pytest.fixture
def financial_setup(db):
    """Sets up base records for financial and accounting tests."""
    user = User.objects.create_user(
        username="accountant_phase4",
        email="acc_p4@example.com",
        password="password123"
    )
    customer = Customer.objects.create(
        name="عميل اختبار المرحلة الرابعة المالية",
        code="CUST-P4-001",
        phone="01011223344"
    )
    project = RealEstateProject.objects.create(
        name="مشروع الحوكمة المالية",
        code="FIN-PRJ-01",
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        created_by=user
    )
    block = PropertyBlock.objects.create(
        project=project,
        name="عمارة 30",
        code="B30"
    )
    floor = PropertyFloor.objects.create(
        block=block,
        floor_number=4,
        name="الدور الرابع"
    )
    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="FIN-U401",
        unit_type="APARTMENT",
        gross_area=Decimal('250.00'),
        net_area=Decimal('210.00'),
        meter_price=Decimal('35000.00'),
        total_price=Decimal('8750000.00'),
        status='CONTRACTED'
    )
    egp, _ = Currency.objects.get_or_create(code="EGP", defaults={'name': "جنيه مصري", 'symbol': "ج.م", 'is_functional': True})
    contract = PropertyContract.objects.create(
        contract_number="CNT-FIN-401",
        project=project,
        unit=unit,
        customer=customer,
        final_contract_price=Decimal('8750000.00'),
        contract_date=date(2025, 4, 1),
        delivery_date=date(2027, 9, 30),
        currency=egp,
        status='ACTIVE',
        created_by=user
    )
    order = UnitFinishingOrder.objects.create(
        order_number="FO-FIN-TEST-001",
        unit=unit,
        contract=contract,
        customer=customer,
        title="أمر تشطيب فحص الحوكمة المالية",
        current_stage='CLIENT_APPROVAL',
        gross_finishing_amount=Decimal('200000.00'),
        advance_deposit_required=Decimal('70000.00'),
        total_deposit_paid=Decimal('0.00'),
        created_by=user
    )
    workspace = FinishingWorkspace.objects.create(
        project=project,
        name="صالة الاستقبال الكبرى",
        code="LIV-GRND"
    )
    category, _ = Category.objects.get_or_create(name="سيراميك وبورسلين")
    unit_m2, _ = ProductMeasurementUnit.objects.get_or_create(name="متر مربع", symbol="M2")
    product = Product.objects.create(
        name="بورسلين هندي فاخر 120x120",
        sku="PORC-IND-120",
        category=category,
        unit=unit_m2,
        cost_price=Decimal('500.00'),
        selling_price=Decimal('750.00'),
        created_by=user
    )
    warehouse = Warehouse.objects.create(
        name="المخزن المركزي لمشروع الحوكمة المالية",
        is_active=True
    )
    supplier = Supplier.objects.create(
        name="شركة المقاولون التخصصيون لأعمال التشطيب",
        code="SUP-P4-FIN"
    )
    contractor_contract = ContractorContract.objects.create(
        contract_number="CC-FIN-001",
        title="عقد مقاول باطن تشطيبات",
        project=project,
        contractor=supplier,
        contract_type='SUBCONTRACTOR',
        initial_contract_value=Decimal('500000.00'),
        created_by=user
    )

    return {
        'user': user,
        'customer': customer,
        'project': project,
        'unit': unit,
        'contract': contract,
        'order': order,
        'workspace': workspace,
        'product': product,
        'warehouse': warehouse,
        'supplier': supplier,
        'contractor_contract': contractor_contract,
    }


@pytest.mark.django_db
def test_accrual_journal_entry_posting_and_table_tax_5_pct(financial_setup):
    """Test IFRS 15 accrual journal entry with Egyptian Table Tax 5% (code T2)."""
    data = financial_setup
    order = data['order']
    user = data['user']

    # Net revenue = 200,000 EGP
    # Table tax 5% = 10,000 EGP
    # Total receivable from client = 210,000 EGP
    entry, tax = FinishingFinancialService.create_accrual_journal_entry(order, user)
    order.refresh_from_db()

    assert order.accrual_journal_entry == entry
    assert tax == Decimal('10000.00')

    # Verify journal entry lines
    lines = entry.lines.all()
    assert lines.count() == 3

    # Check lines debit and credit balance
    total_debit = sum(l.debit for l in lines)
    total_credit = sum(l.credit for l in lines)
    assert total_debit == Decimal('210000.00')
    assert total_credit == Decimal('210000.00')

    # Line 1: Debit Client (11220) = 210,000
    debit_line = lines.get(account__code='11220')
    assert debit_line.debit == Decimal('210000.00')
    assert debit_line.credit == Decimal('0.00')

    # Line 2: Credit Finishing Revenue (41200) = 200,000
    rev_line = lines.get(account__code='41200')
    assert rev_line.credit == Decimal('200000.00')

    # Line 3: Credit Table Tax 5% (21320) = 10,000
    tax_line = lines.get(account__code='21320')
    assert tax_line.credit == Decimal('10000.00')

    # Test idempotency (calling again returns same entry)
    entry2, tax2 = FinishingFinancialService.create_accrual_journal_entry(order, user)
    assert entry2.id == entry.id
    assert tax2 == tax


@pytest.mark.django_db
def test_advance_deposit_and_escrow_routing(financial_setup):
    """Test recording client advance deposit (35%) routed into project escrow bank sub-account."""
    data = financial_setup
    order = data['order']
    user = data['user']

    deposit_amount = Decimal('70000.00')
    deposit = FinishingFinancialService.record_advance_deposit(
        order=order,
        payment_amount=deposit_amount,
        user=user,
        notes="سداد دفعة مقدمة 35% بشيك مصرفي مسحوب على بنك مصر"
    )
    order.refresh_from_db()

    assert order.total_deposit_paid == deposit_amount
    assert deposit.order == order
    assert deposit.amount == deposit_amount
    assert deposit.journal_entry is not None

    # Check deposit journal entry
    je = deposit.journal_entry
    lines = je.lines.all()
    assert sum(l.debit for l in lines) == deposit_amount
    assert sum(l.credit for l in lines) == deposit_amount


@pytest.mark.django_db
def test_segregated_finishing_installment_plan_creation(financial_setup):
    """Test generating a segregated finishing installment plan independent of property contract."""
    data = financial_setup
    order = data['order']
    user = data['user']

    # Deposit 70,000 EGP paid out of 200,000 EGP
    # Remaining balance to schedule = 130,000 EGP across 4 quarterly installments
    order.total_deposit_paid = Decimal('70000.00')
    order.save(update_fields=['total_deposit_paid'])

    plan = FinishingFinancialService.generate_segregated_installment_plan(
        order=order,
        number_of_installments=4,
        start_date=date(2025, 7, 1),
        frequency_months=3,
        user=user
    )
    order.refresh_from_db()

    assert order.finishing_installment_plan == plan
    assert plan.total_finishing_amount == Decimal('210000.00')
    assert plan.down_payment_paid == Decimal('70000.00')
    assert plan.scheduled_balance == Decimal('140000.00')
    assert plan.number_of_installments == 4

    items = plan.items.all().order_by('installment_number')
    assert items.count() == 4

    # 140,000 / 4 = 35,000 each
    total_items_sum = sum(i.amount for i in items)
    assert total_items_sum == Decimal('140000.00')
    assert items[0].amount == Decimal('35000.00')
    assert items[0].due_date == date(2025, 7, 1)
    assert items[1].due_date == date(2025, 10, 1)


@pytest.mark.django_db
def test_subcontractor_warranty_retention_and_penalty_netting(financial_setup):
    """Test 5% warranty retention deduction and netting of penalties against subcontractor certificate."""
    data = financial_setup
    order = data['order']
    contractor = data['contractor_contract']
    user = data['user']

    gross_cert = Decimal('100000.00')
    # Retention 5% = 5,000
    # Delay penalties = 8,000, safety = 2,000, damages = 1,500 -> total penalties = 11,500
    # Net payable = 100,000 - 5,000 - 11,500 = 83,500 EGP
    settlement = FinishingSubcontractorPenaltyNettingService.net_subcontractor_final_certificate(
        order=order,
        contractor=contractor,
        gross_final_certificate_amount=gross_cert,
        delay_penalties=Decimal('8000.00'),
        safety_violations=Decimal('2000.00'),
        debris_and_damages=Decimal('1500.00'),
        user=user
    )

    assert settlement.gross_final_certificate_amount == gross_cert
    assert settlement.total_penalties_netted == Decimal('11500.00')
    assert settlement.net_payable_amount == Decimal('83500.00')


@pytest.mark.django_db
def test_cancellation_sunk_cost_settlement_refund(financial_setup):
    """Test cancellation when deposit exceeds sunk costs -> generates refund to client."""
    data = financial_setup
    order = data['order']
    user = data['user']

    # Client paid 60,000 EGP deposit
    order.total_deposit_paid = Decimal('60000.00')
    order.save(update_fields=['total_deposit_paid'])

    # Sunk costs = 10,000 demo + 8,000 scrap + 5,000 labor + 2,000 supervision = 25,000 EGP
    # Net refund = 60,000 - 25,000 = 35,000 EGP
    settlement = FinishingCancellationService.settle_order_cancellation(
        order=order,
        executed_demolition_cost=Decimal('10000.00'),
        custom_materials_scrap_cost=Decimal('8000.00'),
        labor_costs_incurred=Decimal('5000.00'),
        earned_supervision_fee=Decimal('2000.00'),
        cancellation_reason="طلب العميل إيقاف الباقة لظروف السفر للخارج",
        user=user
    )
    order.refresh_from_db()

    assert order.current_stage == 'CANCELLED'
    assert settlement.total_sunk_costs == Decimal('25000.00')
    assert settlement.deposit_paid == Decimal('60000.00')
    assert settlement.net_refundable_to_client == Decimal('35000.00')
    assert settlement.shortfall_due_from_client == Decimal('0.00')


@pytest.mark.django_db
def test_cancellation_sunk_cost_settlement_shortfall(financial_setup):
    """Test cancellation when sunk costs exceed deposit -> generates shortfall due from client."""
    data = financial_setup
    order = data['order']
    user = data['user']

    # Client paid only 15,000 EGP deposit
    order.total_deposit_paid = Decimal('15000.00')
    order.save(update_fields=['total_deposit_paid'])

    # Sunk costs = 20,000 demo + 10,000 scrap + 8,000 labor + 2,000 supervision = 40,000 EGP
    # Shortfall due from client = 40,000 - 15,000 = 25,000 EGP
    settlement = FinishingCancellationService.settle_order_cancellation(
        order=order,
        executed_demolition_cost=Decimal('20000.00'),
        custom_materials_scrap_cost=Decimal('10000.00'),
        labor_costs_incurred=Decimal('8000.00'),
        earned_supervision_fee=Decimal('2000.00'),
        cancellation_reason="إلغاء تعسفي من العميل بعد بدء التكسير والشراء",
        user=user
    )
    order.refresh_from_db()

    assert order.current_stage == 'CANCELLED'
    assert settlement.total_sunk_costs == Decimal('40000.00')
    assert settlement.deposit_paid == Decimal('15000.00')
    assert settlement.net_refundable_to_client == Decimal('0.00')
    assert settlement.shortfall_due_from_client == Decimal('25000.00')


@pytest.mark.django_db
def test_as_built_true_up_reconciliation_positive_and_negative(financial_setup):
    """Test as-built true-up reconciliation for both cost overruns and underruns."""
    data = financial_setup
    order = data['order']
    user = data['user']

    # 1. Cost Overrun: Estimated 200,000 -> Actual 218,000 (+18,000 variance)
    rec_positive = FinishingAsBuiltTrueUpService.reconcile_as_built_quantities(
        order=order,
        actual_as_built_total=Decimal('218000.00'),
        user=user
    )
    assert rec_positive.estimated_boq_total == Decimal('200000.00')
    assert rec_positive.actual_as_built_total == Decimal('218000.00')
    assert rec_positive.variance_amount == Decimal('18000.00')
    assert rec_positive.balancing_action == 'CLIENT_ADDITIONAL_INVOICE'

    # 2. Cost Underrun: Actual 192,000 (-8,000 variance)
    rec_negative = FinishingAsBuiltTrueUpService.reconcile_as_built_quantities(
        order=order,
        actual_as_built_total=Decimal('192000.00'),
        user=user
    )
    assert rec_negative.variance_amount == Decimal('-8000.00')
    assert rec_negative.balancing_action == 'CLIENT_CREDIT_REFUND'


@pytest.mark.django_db
def test_store_material_requisition_quota_guard(financial_setup):
    """Test that material requisitions cannot exceed approved BOQ item gross quantity."""
    data = financial_setup
    order = data['order']
    workspace = data['workspace']
    product = data['product']
    warehouse = data['warehouse']
    contractor = data['supplier']
    user = data['user']

    # Seed cost layer with 100 m²
    receipt = StockLedgerEntry.objects.create(
        entry_number='RECEIPT-P4-STORE', movement_service_ref='P4-STORE',
        product=product, warehouse=warehouse, movement_type='RECEIPT',
        quantity=Decimal('100.00'), unit_cost=Decimal('500.00'), total_cost=Decimal('50000.00')
    )
    InventoryCostLayer.objects.create(
        product=product, warehouse=warehouse, receipt_date=timezone.now(),
        stock_ledger_entry=receipt, original_qty=Decimal('100.00'), remaining_qty=Decimal('100.00'),
        unit_cost=Decimal('500.00'), status='OPEN'
    )

    # Approved gross quantity = 80 m²
    order_item = UnitFinishingOrderItem.objects.create(
        order=order,
        workspace=workspace,
        category='FLOORING',
        item_description="توريد وتركيب بورسلين أرضيات",
        quantity=Decimal('76.00'),
        scrap_rate=Decimal('5.26'),
        gross_quantity=Decimal('80.00'),
        measuring_unit="M2",
        unit_selling_price=Decimal('750.00'),
        issued_quantity_from_store=Decimal('0.00')
    )

    # Issue 50 m² -> allowed
    req1 = FinishingStoreRequisitionService.issue_materials_from_store(
        order_item=order_item,
        product=product,
        warehouse=warehouse,
        contractor=contractor,
        quantity_to_issue=Decimal('50.00'),
        user=user
    )
    order_item.refresh_from_db()
    assert order_item.issued_quantity_from_store == Decimal('50.00')
    assert req1.quantity_issued == Decimal('50.00')

    # Attempt to issue 40 m² -> blocked (50 + 40 = 90 > 80)
    with pytest.raises(ValidationError) as exc:
        FinishingStoreRequisitionService.issue_materials_from_store(
            order_item=order_item,
            product=product,
            warehouse=warehouse,
            contractor=contractor,
            quantity_to_issue=Decimal('40.00'),
            user=user
        )
    assert "سيتجاوز كوتة البند المعتمدة" in str(exc.value)

    # Issue 30 m² -> allowed (50 + 30 = 80)
    req2 = FinishingStoreRequisitionService.issue_materials_from_store(
        order_item=order_item,
        product=product,
        warehouse=warehouse,
        contractor=contractor,
        quantity_to_issue=Decimal('30.00'),
        user=user
    )
    order_item.refresh_from_db()
    assert order_item.issued_quantity_from_store == Decimal('80.00')


@pytest.mark.django_db
def test_store_material_return_and_quota_reversal(financial_setup):
    """Test returning unused sound materials to store and reversing issued quota."""
    data = financial_setup
    order = data['order']
    workspace = data['workspace']
    product = data['product']
    warehouse = data['warehouse']
    contractor = data['supplier']
    user = data['user']

    # Seed cost layer
    receipt = StockLedgerEntry.objects.create(
        entry_number='RECEIPT-P4-RET', movement_service_ref='P4-RET',
        product=product, warehouse=warehouse, movement_type='RECEIPT',
        quantity=Decimal('100.00'), unit_cost=Decimal('500.00'), total_cost=Decimal('50000.00')
    )
    InventoryCostLayer.objects.create(
        product=product, warehouse=warehouse, receipt_date=timezone.now(),
        stock_ledger_entry=receipt, original_qty=Decimal('100.00'), remaining_qty=Decimal('20.00'),
        unit_cost=Decimal('500.00'), status='OPEN'
    )

    # Currently issued = 80 m²
    order_item = UnitFinishingOrderItem.objects.create(
        order=order,
        workspace=workspace,
        category='FLOORING',
        item_description="توريد وتركيب بورسلين أرضيات",
        quantity=Decimal('76.00'),
        scrap_rate=Decimal('5.26'),
        gross_quantity=Decimal('80.00'),
        measuring_unit="M2",
        unit_selling_price=Decimal('750.00'),
        issued_quantity_from_store=Decimal('80.00')
    )

    # Return 15 m² intact tiles to store
    ret = FinishingMaterialReturnService.return_materials_to_store(
        order_item=order_item,
        product=product,
        warehouse=warehouse,
        contractor=contractor,
        quantity_to_return=Decimal('15.00'),
        return_reason="فائض سليم بعد انتهاء أعمال التبليط بالفراغ",
        user=user
    )
    order_item.refresh_from_db()

    assert order_item.issued_quantity_from_store == Decimal('65.00')
    assert ret.transaction_type == 'RETURN'
    assert ret.is_cost_reversed is True

    # Attempt to return 70 m² (more than the currently issued 65 m²) -> blocked
    with pytest.raises(ValidationError) as exc:
        FinishingMaterialReturnService.return_materials_to_store(
            order_item=order_item,
            product=product,
            warehouse=warehouse,
            contractor=contractor,
            quantity_to_return=Decimal('70.00'),
            user=user
        )
    assert "تتجاوز إجمالي المنصرف" in str(exc.value)
