# -*- coding: utf-8 -*-
"""
Test Suite: Contract Assignment & Resale Subledger Transfer Protocol
(Wave 3 Phase 13 - Resale & Contract Assignment Engine)
"""

import pytest
from decimal import Decimal
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from customer.models import Customer
from financial.models import ChartOfAccounts, AccountType, Currency, JournalEntry
from sale.models.installments import InstallmentPlan, InstallmentItem
from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    ContractAssignmentEndorsement,
)
from real_estate.services.assignment_service import ContractAssignmentService

User = get_user_model()


@pytest.fixture
def assignment_setup(db):
    user, _ = User.objects.get_or_create(
        username="legal_officer",
        defaults={"email": "legal_officer@test.com", "is_staff": True}
    )
    approver, _ = User.objects.get_or_create(
        username="cfo_user",
        defaults={"email": "cfo@test.com", "is_staff": True}
    )
    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "جنيه مصري", "symbol": "ج.م"}
    )

    asset_type, _ = AccountType.objects.get_or_create(
        code='asset',
        defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
    )
    liability_type, _ = AccountType.objects.get_or_create(
        code='liability',
        defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'}
    )
    revenue_type, _ = AccountType.objects.get_or_create(
        code='revenue',
        defaults={'name': 'إيرادات', 'category': 'revenue', 'nature': 'credit'}
    )

    bank_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11160",
        defaults={
            "name": "حساب البنك التجاري الدولي CIB",
            "account_type": asset_type,
            "is_active": True
        }
    )
    liability_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21102",
        defaults={
            "name": "التزامات عقود عملاء حجز عقاري (Contract Liabilities)",
            "account_type": liability_type,
            "is_active": True
        }
    )
    fee_income_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="42202",
        defaults={
            "name": "إيرادات رسوم التنازل والاستبدال العقاري",
            "account_type": revenue_type,
            "is_active": True
        }
    )

    assignor, _ = Customer.objects.get_or_create(
        code="CUST-ASN-01",
        defaults={"name": "السيد إبراهيم حسن (المتنازل)", "default_currency": currency}
    )
    assignee, _ = Customer.objects.get_or_create(
        code="CUST-ASN-02",
        defaults={"name": "السيد محمود الجوهري (المتنازل إليه)", "default_currency": currency}
    )

    project = RealEstateProject.objects.create(
        code="PRJ-ASN-01",
        name="كمبوند صن رايز جاردنز",
        start_date=date(2024, 1, 1),
        expected_completion_date=date(2026, 12, 31),
        total_land_area=Decimal("20000.00"),
        gross_built_area=Decimal("60000.00"),
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, code="B-03", name="برج الفيروز")
    floor = PropertyFloor.objects.create(block=block, floor_number=4, name="الدور الرابع")

    unit = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="SUN-U404",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.CONTRACTED,
        net_area=Decimal("130.00"),
        gross_area=Decimal("150.00"),
        meter_price=Decimal("13333.33"),
        base_price=Decimal("2000000.00"),
        total_price=Decimal("2000000.00")
    )

    contract = PropertyContract.objects.create(
        contract_number="CTR-ASN-001",
        project=project,
        unit=unit,
        customer=assignor,
        status=PropertyContract.ContractStatus.ACTIVE,
        contract_date=date(2026, 1, 1),
        delivery_date=date(2028, 12, 31),
        final_contract_price=Decimal("2000000.00"),
        down_payment=Decimal("400000.00"),
        currency=currency,
        created_by=user
    )

    plan = InstallmentPlan.objects.create(
        customer=assignor,
        total_principal=Decimal("1600000.00"),
        total_amount=Decimal("1600000.00"),
        number_of_installments=8,
        start_date=date(2026, 4, 1),
        frequency='QUARTERLY',
        created_by=user
    )
    contract.installment_plan = plan
    contract.save(update_fields=['installment_plan'])

    # توليد الأقساط (8 أقساط كل قسط 200,000)
    for i in range(1, 9):
        # القسط الأول مسدد، الباقي في الانتظار بتواريخ مستقبلية في 2027
        is_paid = (i == 1)
        paid_val = Decimal("200000.00") if is_paid else Decimal("0.00")
        c_status = InstallmentItem.CashStatus.COLLECTED if is_paid else InstallmentItem.CashStatus.PENDING
        d_date = date(2026, 3, 1) if is_paid else date(2027, i, 1)

        InstallmentItem.objects.create(
            plan=plan,
            installment_number=i,
            due_date=d_date,
            principal_amount=Decimal("200000.00"),
            interest_amount=Decimal("0.00"),
            total_amount=Decimal("200000.00"),
            paid_amount=paid_val,
            paid_principal=paid_val,
            cash_status=c_status
        )

    return {
        "user": user,
        "approver": approver,
        "currency": currency,
        "project": project,
        "unit": unit,
        "contract": contract,
        "plan": plan,
        "assignor": assignor,
        "assignee": assignee,
        "bank_acc": bank_acc,
        "liability_acc": liability_acc,
        "fee_income_acc": fee_income_acc,
    }


@pytest.mark.django_db
class TestContractAssignmentSubledgerTransfer:

    def test_assignment_eligibility_validation(self, assignment_setup):
        """التحقق من ضوابط وأهلية التنازل للغير (Resale Transfer Eligibility)"""
        contract = assignment_setup["contract"]
        assignor = assignment_setup["assignor"]
        assignee = assignment_setup["assignee"]
        plan = assignment_setup["plan"]

        # 1. لا يجوز التنازل لنفس العميل الأصلي
        with pytest.raises(ValidationError, match="لا يجوز التنازل لنفس العميل"):
            ContractAssignmentService.validate_assignment_eligibility(contract, assignor)

        # 2. لا يجوز التنازل لعقد مفسوخ أو غير سارٍ
        contract.status = PropertyContract.ContractStatus.TERMINATED
        contract.save(update_fields=['status'])
        with pytest.raises(ValidationError, match="غير سارٍ"):
            ContractAssignmentService.validate_assignment_eligibility(contract, assignee)

        contract.status = PropertyContract.ContractStatus.ACTIVE
        contract.save(update_fields=['status'])

        # 3. التحقق من حظر التنازل حال وجود أقساط متأخرة
        unpaid_item = plan.items.exclude(cash_status=InstallmentItem.CashStatus.COLLECTED).first()
        unpaid_item.due_date = date(2024, 1, 1)  # تاريخ ماضٍ متأخر
        unpaid_item.save(update_fields=['due_date'])

        with pytest.raises(ValidationError, match="لوجود أقساط مستحقة ومتأخرة"):
            ContractAssignmentService.validate_assignment_eligibility(contract, assignee)

        # إعادة تاريخ القسط للمستقبل
        unpaid_item.due_date = date(2027, 1, 1)
        unpaid_item.save(update_fields=['due_date'])

        # 4. التحقق من الحد الأدنى للمبالغ المسددة (مثلاً 50% كشرط اختباري)
        with pytest.raises(ValidationError, match="أقل من النسبة المشروطة للتنازل"):
            ContractAssignmentService.validate_assignment_eligibility(
                contract, assignee, min_paid_percentage=Decimal("50.00")
            )

    def test_create_assignment_endorsement_draft(self, assignment_setup):
        """إنشاء مسودة ملحق التنازل وحساب المبالغ وبصمة التحقق الرقمية SHA-256"""
        contract = assignment_setup["contract"]
        assignee = assignment_setup["assignee"]
        user = assignment_setup["user"]

        endorsement = ContractAssignmentService.create_assignment_endorsement(
            contract=contract,
            assignee_customer=assignee,
            administrative_fee_percentage=Decimal("2.50"),
            resale_price=Decimal("2500000.00"),
            notes="تنازل رسمي معتمد بالشهر العقاري",
            user=user
        )

        assert endorsement.id is not None
        assert endorsement.status == ContractAssignmentEndorsement.AssignmentStatus.DRAFT
        assert endorsement.assignment_number.startswith("TRF")
        assert endorsement.original_contract_price == Decimal("2000000.00")

        # المسدد = مقدم (400,000) + قسط أول (200,000) = 600,000
        assert endorsement.paid_amount_at_assignment == Decimal("600000.00")
        assert endorsement.remaining_balance_at_assignment == Decimal("1400000.00")

        # رسوم التنازل = 2.5% من 2,000,000 = 50,000 ج.م
        assert endorsement.administrative_fee == Decimal("50000.00")

        # التحقق من وجود بصمة التشفير SHA-256
        assert len(endorsement.verification_token) == 64
        assert endorsement.verification_token == endorsement.generate_verification_token()

    def test_approve_assignment_endorsement(self, assignment_setup):
        """اعتماد ملحق التنازل من الإدارة المالية والقانونية"""
        contract = assignment_setup["contract"]
        assignee = assignment_setup["assignee"]
        user = assignment_setup["user"]
        approver = assignment_setup["approver"]

        endorsement = ContractAssignmentService.create_assignment_endorsement(
            contract=contract,
            assignee_customer=assignee,
            user=user
        )
        assert endorsement.status == ContractAssignmentEndorsement.AssignmentStatus.DRAFT

        approved = ContractAssignmentService.approve_assignment(endorsement, approver)
        assert approved.status == ContractAssignmentEndorsement.AssignmentStatus.APPROVED
        assert approved.approved_by == approver

    def test_execute_contract_assignment_subledger_transfer(self, assignment_setup):
        """تنفيذ التنازل وترحيل الالتزامات ونقل العقد دفترياً للمشتري الجديد"""
        contract = assignment_setup["contract"]
        assignor = assignment_setup["assignor"]
        assignee = assignment_setup["assignee"]
        plan = assignment_setup["plan"]
        user = assignment_setup["user"]
        bank_acc = assignment_setup["bank_acc"]
        liability_acc = assignment_setup["liability_acc"]
        fee_income_acc = assignment_setup["fee_income_acc"]

        endorsement = ContractAssignmentService.create_assignment_endorsement(
            contract=contract,
            assignee_customer=assignee,
            administrative_fee_percentage=Decimal("2.50"),
            user=user
        )

        executed = ContractAssignmentService.execute_contract_assignment(
            endorsement=endorsement,
            user=user,
            payment_account=bank_acc
        )

        assert executed.status == ContractAssignmentEndorsement.AssignmentStatus.EXECUTED
        assert executed.executed_at is not None

        # 1. التحقق من انتقال ملكية العقد وخطة التقسيط للعميل الجديد
        contract.refresh_from_db()
        plan.refresh_from_db()

        assert contract.customer_id == assignee.id
        assert plan.customer_id == assignee.id

        # 2. التحقق من قيد مناقلة الالتزام التعاقدي (Subledger Transfer Entry)
        transfer_entry = JournalEntry.objects.filter(
            source_model="ContractAssignmentEndorsement",
            source_id=endorsement.id,
            lines__account=liability_acc
        ).first()

        assert transfer_entry is not None
        lines = list(transfer_entry.lines.all())
        assert len(lines) == 2

        # سطر المدين: تخفيض التزام المتنازل (21102) بمبلغ 600,000
        debit_line = next(l for l in lines if l.debit > 0)
        assert debit_line.account.code == liability_acc.code
        assert debit_line.debit == Decimal("600000.00")
        assert assignor.name in debit_line.description

        # سطر الدائن: إثبات التزام المتنازل إليه (21102) بمبلغ 600,000
        credit_line = next(l for l in lines if l.credit > 0)
        assert credit_line.account.code == liability_acc.code
        assert credit_line.credit == Decimal("600000.00")
        assert assignee.name in credit_line.description

        # 3. التحقق من قيد رسوم التنازل الإدارية (50,000 ج.م)
        fee_entry = JournalEntry.objects.filter(
            source_model="ContractAssignmentEndorsement",
            source_id=endorsement.id,
            lines__account=fee_income_acc
        ).first()

        assert fee_entry is not None
        fee_lines = list(fee_entry.lines.all())
        assert len(fee_lines) == 2

        bank_line = next(l for l in fee_lines if l.debit > 0)
        assert bank_line.account.code == bank_acc.code
        assert bank_line.debit == Decimal("50000.00")

        inc_line = next(l for l in fee_lines if l.credit > 0)
        assert inc_line.account.code == fee_income_acc.code
        assert inc_line.credit == Decimal("50000.00")

    def test_assignment_cannot_be_reexecuted(self, assignment_setup):
        """منع تكرار تنفيذ ملحق التنازل المنفذ مسبقاً (Double-Execution Guard)"""
        contract = assignment_setup["contract"]
        assignee = assignment_setup["assignee"]
        user = assignment_setup["user"]

        endorsement = ContractAssignmentService.create_assignment_endorsement(
            contract=contract,
            assignee_customer=assignee,
            user=user
        )
        ContractAssignmentService.execute_contract_assignment(endorsement=endorsement, user=user)

        with pytest.raises(ValidationError, match="تم تنفيذه وترحيله مسبقاً"):
            ContractAssignmentService.execute_contract_assignment(endorsement=endorsement, user=user)
