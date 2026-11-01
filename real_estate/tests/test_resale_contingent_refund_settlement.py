# -*- coding: utf-8 -*-
"""
Test Suite: Resale-Contingent Refund Workflow & Settlement
(Wave 3 Phase 14 - Resale-Contingent Refund Workflow)
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
    ResaleContingentRefund,
)
from real_estate.services.resale_refund_service import ResaleContingentRefundService

User = get_user_model()


@pytest.fixture
def refund_setup(db):
    user, _ = User.objects.get_or_create(
        username="refund_officer",
        defaults={"email": "refund@test.com", "is_staff": True}
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

    cash_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11110",
        defaults={
            "name": "الخزينة الرئيسية",
            "account_type": asset_type,
            "is_active": True
        }
    )
    forfeited_liability_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21701",
        defaults={
            "name": "مستحقات عملاء عقود مفسوخة معلقة لإعادة الطرح",
            "account_type": liability_type,
            "is_active": True
        }
    )

    old_customer, _ = Customer.objects.get_or_create(
        code="CUST-RFD-01",
        defaults={"name": "السيد عمر عبد الرحيم (العميل المفسوخ)", "default_currency": currency}
    )
    new_customer, _ = Customer.objects.get_or_create(
        code="CUST-RFD-02",
        defaults={"name": "السيد خالد الشربيني (المشتري الجديد)", "default_currency": currency}
    )

    project = RealEstateProject.objects.create(
        code="PRJ-RFD-01",
        name="كمبوند الزمرد ريزيدنس",
        start_date=date(2024, 1, 1),
        expected_completion_date=date(2026, 12, 31),
        total_land_area=Decimal("12000.00"),
        gross_built_area=Decimal("40000.00"),
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, code="B-07", name="برج الزمرد")
    floor = PropertyFloor.objects.create(block=block, floor_number=1, name="الدور الأول")

    unit = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="ZOM-U101",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.AVAILABLE,
        net_area=Decimal("90.00"),
        gross_area=Decimal("110.00"),
        meter_price=Decimal("10000.00"),
        base_price=Decimal("1100000.00"),
        total_price=Decimal("1100000.00")
    )

    # العقد القديم المفسوخ
    old_contract = PropertyContract.objects.create(
        contract_number="CTR-RFD-OLD",
        project=project,
        unit=unit,
        customer=old_customer,
        status=PropertyContract.ContractStatus.TERMINATED,
        contract_date=date(2025, 1, 1),
        delivery_date=date(2026, 12, 31),
        final_contract_price=Decimal("1100000.00"),
        down_payment=Decimal("200000.00"),
        currency=currency,
        created_by=user
    )

    old_plan = InstallmentPlan.objects.create(
        customer=old_customer,
        total_principal=Decimal("900000.00"),
        total_amount=Decimal("900000.00"),
        number_of_installments=3,
        start_date=date(2025, 4, 1),
        frequency='QUARTERLY',
        created_by=user
    )
    old_contract.installment_plan = old_plan
    old_contract.save(update_fields=['installment_plan'])

    # سدد قسطاً واحداً بقيمة 100,000 قبل الفسخ
    InstallmentItem.objects.create(
        plan=old_plan,
        installment_number=1,
        due_date=date(2025, 4, 1),
        principal_amount=Decimal("100000.00"),
        interest_amount=Decimal("0.00"),
        total_amount=Decimal("100000.00"),
        paid_amount=Decimal("100000.00"),
        paid_principal=Decimal("100000.00"),
        cash_status=InstallmentItem.CashStatus.COLLECTED
    )

    # العقد الجديد للمشتري الثاني بعد إعادة الطرح
    new_contract = PropertyContract.objects.create(
        contract_number="CTR-RFD-NEW",
        project=project,
        unit=unit,
        customer=new_customer,
        status=PropertyContract.ContractStatus.ACTIVE,
        contract_date=date(2026, 2, 1),
        delivery_date=date(2027, 12, 31),
        final_contract_price=Decimal("1200000.00"),
        down_payment=Decimal("300000.00"),
        currency=currency,
        created_by=user
    )

    return {
        "user": user,
        "currency": currency,
        "cash_acc": cash_acc,
        "forfeited_liability_acc": forfeited_liability_acc,
        "old_contract": old_contract,
        "new_contract": new_contract,
        "unit": unit,
        "old_customer": old_customer,
        "new_customer": new_customer,
    }


@pytest.mark.django_db
class TestResaleContingentRefundSettlement:

    def test_create_contingent_refund(self, refund_setup):
        """إنشاء سجل مستحقات معلقة واحتساب صافي الرد بعد خصم غرامة الفسخ"""
        user = refund_setup["user"]
        old_contract = refund_setup["old_contract"]

        # إجمالي ما سدده العميل القديم = 200,000 مقدم + 100,000 قسط = 300,000
        # غرامة الفسخ = 50,000 ج.م -> الصافي المعلق = 250,000 ج.م
        refund = ResaleContingentRefundService.create_contingent_refund(
            cancelled_contract=old_contract,
            cancellation_penalty_amount=Decimal("50000.00"),
            notes="فسخ تعاقد بناء على طلب العميل مع خصم 50,000 غرامة إدارية",
            user=user
        )

        assert refund.id is not None
        assert refund.status == ResaleContingentRefund.RefundStatus.PENDING_RESALE
        assert refund.total_paid_before_cancellation == Decimal("300000.00")
        assert refund.cancellation_penalty_amount == Decimal("50000.00")
        assert refund.net_refundable_amount == Decimal("250000.00")
        assert refund.refund_number.startswith("RRF")

    def test_link_resale_contract_and_authorize_disbursement(self, refund_setup):
        """الربط بعقد المشتري الجديد والتصريح بالصرف بعد تحصيل المقدم"""
        user = refund_setup["user"]
        old_contract = refund_setup["old_contract"]
        new_contract = refund_setup["new_contract"]

        refund = ResaleContingentRefundService.create_contingent_refund(
            cancelled_contract=old_contract,
            cancellation_penalty_amount=Decimal("50000.00"),
            user=user
        )

        authorized_refund = ResaleContingentRefundService.link_resale_contract_and_authorize_disbursement(
            refund_record=refund,
            new_contract=new_contract,
            user=user
        )

        assert authorized_refund.status == ResaleContingentRefund.RefundStatus.DISBURSEMENT_AUTHORIZED
        assert authorized_refund.resale_contract == new_contract
        assert authorized_refund.authorized_by == user

    def test_disburse_refund_journal_entry(self, refund_setup):
        """صرف المستحقات دفترياً وإصدار قيد اليومية (Dr: 21701 / Cr: 11110)"""
        user = refund_setup["user"]
        old_contract = refund_setup["old_contract"]
        new_contract = refund_setup["new_contract"]
        cash_acc = refund_setup["cash_acc"]
        forfeited_acc = refund_setup["forfeited_liability_acc"]

        refund = ResaleContingentRefundService.create_contingent_refund(
            cancelled_contract=old_contract,
            cancellation_penalty_amount=Decimal("50000.00"),
            user=user
        )
        ResaleContingentRefundService.link_resale_contract_and_authorize_disbursement(
            refund_record=refund,
            new_contract=new_contract,
            user=user
        )

        disbursed = ResaleContingentRefundService.disburse_refund(
            refund_record=refund,
            payment_account=cash_acc,
            user=user
        )

        assert disbursed.status == ResaleContingentRefund.RefundStatus.DISBURSED
        assert disbursed.disbursed_at is not None
        assert disbursed.disbursement_entry is not None

        je = disbursed.disbursement_entry
        lines = list(je.lines.all())
        assert len(lines) == 2

        debit_line = next(l for l in lines if l.debit > 0)
        assert debit_line.account.code == forfeited_acc.code
        assert debit_line.debit == Decimal("250000.00")

        credit_line = next(l for l in lines if l.credit > 0)
        assert credit_line.account.code == cash_acc.code
        assert credit_line.credit == Decimal("250000.00")

    def test_disburse_before_authorization_rejected(self, refund_setup):
        """حظر صرف المستحقات قبل إعادة بيع الوحدة والتصريح بالصرف"""
        user = refund_setup["user"]
        old_contract = refund_setup["old_contract"]
        cash_acc = refund_setup["cash_acc"]

        refund = ResaleContingentRefundService.create_contingent_refund(
            cancelled_contract=old_contract,
            cancellation_penalty_amount=Decimal("50000.00"),
            user=user
        )

        # محاولة الصرف والمستحقات لا تزال معلقة PENDING_RESALE
        with pytest.raises(ValidationError, match="لا يمكن صرف المستحقات قبل التصريح بالصرف"):
            ResaleContingentRefundService.disburse_refund(
                refund_record=refund,
                payment_account=cash_acc,
                user=user
            )
