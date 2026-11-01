# -*- coding: utf-8 -*-
"""
Test Suite: Unit Swap Lifecycle & Rescheduling Protocol
(Wave 3 Phase 13 - Unit Swap Engine)
"""

import pytest
from decimal import Decimal
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from customer.models import Customer
from financial.models import ChartOfAccounts, AccountType, Currency
from sale.models.installments import InstallmentPlan, InstallmentItem
from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    UnitSwapRecord,
)
from real_estate.services.swap_service import UnitSwapService

User = get_user_model()


@pytest.fixture
def unit_swap_setup(db):
    user, _ = User.objects.get_or_create(
        username="swap_officer",
        defaults={"email": "swap_officer@test.com", "is_staff": True}
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

    cash_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11110",
        defaults={
            "name": "الخزينة الرئيسية",
            "account_type": asset_type,
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
    liability_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21102",
        defaults={
            "name": "التزامات عقود عملاء حجز عقاري (Contract Liabilities)",
            "account_type": liability_type,
            "is_active": True
        }
    )

    customer, _ = Customer.objects.get_or_create(
        code="CUST-SWAP-01",
        defaults={"name": "السيد أحمد مظهر", "default_currency": currency}
    )

    project = RealEstateProject.objects.create(
        code="PRJ-SWAP-01",
        name="كمبوند الزهور بارك",
        start_date=date(2024, 1, 1),
        expected_completion_date=date(2026, 12, 31),
        total_land_area=Decimal("15000.00"),
        gross_built_area=Decimal("50000.00"),
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, code="B-01", name="برج النخيل")
    floor_2 = PropertyFloor.objects.create(block=block, floor_number=2, name="الدور الثاني")
    floor_6 = PropertyFloor.objects.create(block=block, floor_number=6, name="الدور السادس")

    # الوحدة القديمة (120م - 1,000,000 ج.م)
    old_unit = PropertyUnit.objects.create(
        project=project,
        floor=floor_2,
        unit_code="PALM-U201",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.CONTRACTED,
        net_area=Decimal("100.00"),
        gross_area=Decimal("120.00"),
        meter_price=Decimal("8333.33"),
        base_price=Decimal("1000000.00"),
        total_price=Decimal("1000000.00")
    )

    # الوحدة الجديدة للترقية (180م - 1,600,000 ج.م)
    new_unit = PropertyUnit.objects.create(
        project=project,
        floor=floor_6,
        unit_code="PALM-U601",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.AVAILABLE,
        net_area=Decimal("150.00"),
        gross_area=Decimal("180.00"),
        meter_price=Decimal("8888.89"),
        base_price=Decimal("1600000.00"),
        total_price=Decimal("1600000.00")
    )

    # عقد بيع سارٍ للوحدة القديمة
    contract = PropertyContract.objects.create(
        contract_number="CTR-SWAP-001",
        project=project,
        unit=old_unit,
        customer=customer,
        status=PropertyContract.ContractStatus.ACTIVE,
        contract_date=date(2025, 1, 15),
        delivery_date=date(2026, 12, 31),
        final_contract_price=Decimal("1000000.00"),
        down_payment=Decimal("200000.00"),
        currency=currency,
        created_by=user
    )

    # خطة أقساط للرصيد المتبقي (800,000 على 4 أقساط كل قسط 200,000)
    plan = InstallmentPlan.objects.create(
        customer=customer,
        total_principal=Decimal("800000.00"),
        total_amount=Decimal("800000.00"),
        number_of_installments=4,
        start_date=date(2025, 4, 1),
        frequency='QUARTERLY',
        created_by=user
    )
    contract.installment_plan = plan
    contract.save(update_fields=['installment_plan'])

    # توليد 4 أقساط
    items = []
    for i in range(1, 5):
        item = InstallmentItem.objects.create(
            plan=plan,
            installment_number=i,
            due_date=date(2025, i * 3, 1),
            principal_amount=Decimal("200000.00"),
            interest_amount=Decimal("0.00"),
            total_amount=Decimal("200000.00"),
            paid_amount=Decimal("0.00"),
            paid_principal=Decimal("0.00"),
            cash_status=InstallmentItem.CashStatus.PENDING
        )
        items.append(item)

    return {
        "user": user,
        "currency": currency,
        "project": project,
        "old_unit": old_unit,
        "new_unit": new_unit,
        "contract": contract,
        "plan": plan,
        "cash_acc": cash_acc,
        "fee_income_acc": fee_income_acc,
        "customer": customer,
    }


@pytest.mark.django_db
class TestUnitSwapLifecycle:

    def test_swap_eligibility_validation(self, unit_swap_setup):
        """التحقق من موانع وضوابط أهلية الاستبدال"""
        contract = unit_swap_setup["contract"]
        old_unit = unit_swap_setup["old_unit"]
        new_unit = unit_swap_setup["new_unit"]

        # 1. لا يجوز استبدال الوحدة بنفسها
        with pytest.raises(ValidationError, match="لا يجوز اختيار نفس الوحدة"):
            UnitSwapService.validate_swap_eligibility(contract, old_unit, old_unit)

        # 2. لا يجوز الاستبدال لوحدة غير متاحة (مثلاً محجوزة أو متعاقد عليها)
        new_unit.status = PropertyUnit.UnitStatus.CONTRACTED
        new_unit.save(update_fields=['status'])
        with pytest.raises(ValidationError, match="ليست متاحة للبيع"):
            UnitSwapService.validate_swap_eligibility(contract, old_unit, new_unit)

        # إعادة الوحدة إلى متاحة
        new_unit.status = PropertyUnit.UnitStatus.AVAILABLE
        new_unit.save(update_fields=['status'])

        # 3. لا يجوز الاستبدال لعقد غير سارٍ
        contract.status = PropertyContract.ContractStatus.TERMINATED
        contract.save(update_fields=['status'])
        with pytest.raises(ValidationError, match="غير سارٍ"):
            UnitSwapService.validate_swap_eligibility(contract, old_unit, new_unit)

        contract.status = PropertyContract.ContractStatus.ACTIVE
        contract.save(update_fields=['status'])

        # 4. لا يجوز استبدال وحدة تم تسليمها بالفعل للعميل
        old_unit.status = PropertyUnit.UnitStatus.DELIVERED
        old_unit.save(update_fields=['status'])
        with pytest.raises(ValidationError, match="تم تسليمها للعميل مسبقاً"):
            UnitSwapService.validate_swap_eligibility(contract, old_unit, new_unit)

    def test_create_swap_record_draft(self, unit_swap_setup):
        """إنشاء محضر استبدال مسودة وحساب فارق السعر تلقائياً"""
        contract = unit_swap_setup["contract"]
        new_unit = unit_swap_setup["new_unit"]
        user = unit_swap_setup["user"]

        swap_record = UnitSwapService.create_swap_record(
            contract=contract,
            new_unit=new_unit,
            administrative_fee=Decimal("20000.00"),
            settlement_method=UnitSwapRecord.SettlementMethod.RE_AMORTIZE_EXISTING,
            notes="ترقية إلى شقة أكبر بالدور السادس",
            user=user
        )

        assert swap_record.id is not None
        assert swap_record.status == UnitSwapRecord.SwapStatus.DRAFT
        assert swap_record.old_unit_price == Decimal("1000000.00")
        assert swap_record.new_unit_price == Decimal("1600000.00")
        assert swap_record.price_difference == Decimal("600000.00")  # ترقية بمقدار 600,000 ج.م
        assert swap_record.administrative_fee == Decimal("20000.00")
        assert swap_record.swap_number.startswith("SWP")

    def test_unit_swap_atomic_state_flip(self, unit_swap_setup):
        """تنفيذ الاستبدال والتحقق من التبديل الذري لحالات الوحدات وتحديث العقد"""
        contract = unit_swap_setup["contract"]
        old_unit = unit_swap_setup["old_unit"]
        new_unit = unit_swap_setup["new_unit"]
        user = unit_swap_setup["user"]
        cash_acc = unit_swap_setup["cash_acc"]

        swap_record = UnitSwapService.create_swap_record(
            contract=contract,
            new_unit=new_unit,
            administrative_fee=Decimal("20000.00"),
            user=user
        )

        old_v = old_unit.status_version
        new_v = new_unit.status_version

        executed_swap = UnitSwapService.execute_unit_swap(
            swap_record=swap_record,
            user=user,
            payment_account=cash_acc
        )

        assert executed_swap.status == UnitSwapRecord.SwapStatus.EXECUTED
        assert executed_swap.executed_at is not None

        # تحديث كائنات قاعدة البيانات
        old_unit.refresh_from_db()
        new_unit.refresh_from_db()
        contract.refresh_from_db()

        # التأكد من التبديل الذري: الوحدة القديمة أصبحت متاحة، والجديدة أصبحت متعاقد عليها
        assert old_unit.status == PropertyUnit.UnitStatus.AVAILABLE
        assert old_unit.status_version > old_v

        assert new_unit.status == PropertyUnit.UnitStatus.CONTRACTED
        assert new_unit.status_version > new_v

        # العقد أصبح مربوطاً بالوحدة الجديدة وبالسعر الجديد
        assert contract.unit_id == new_unit.id
        assert contract.final_contract_price == Decimal("1600000.00")

    def test_unit_swap_reamortization_on_installment_plan(self, unit_swap_setup):
        """إعادة جدولة وتوزيع فارق السعر بالتساوي على الأقساط غير المسددة"""
        contract = unit_swap_setup["contract"]
        new_unit = unit_swap_setup["new_unit"]
        user = unit_swap_setup["user"]
        plan = unit_swap_setup["plan"]

        # تسديد القسط الأول (200,000) وترك 3 أقساط غير مسددة
        first_item = plan.items.first()
        first_item.paid_amount = Decimal("200000.00")
        first_item.paid_principal = Decimal("200000.00")
        first_item.cash_status = InstallmentItem.CashStatus.COLLECTED
        first_item.save(update_fields=['paid_amount', 'paid_principal', 'cash_status'])

        swap_record = UnitSwapService.create_swap_record(
            contract=contract,
            new_unit=new_unit,
            administrative_fee=Decimal("0.00"),
            user=user
        )
        # فارق السعر = +600,000 ج.م يوزع على الـ 3 أقساط المتبقية (200,000 إضافية لكل قسط)
        UnitSwapService.execute_unit_swap(swap_record=swap_record, user=user)

        plan.refresh_from_db()
        unpaid_items = plan.items.exclude(cash_status=InstallmentItem.CashStatus.COLLECTED).order_by('due_date')
        assert unpaid_items.count() == 3

        # كل قسط غير مسدد أصبح 400,000 بدلاً من 200,000
        for item in unpaid_items:
            assert item.principal_amount == Decimal("400000.00")
            assert item.total_amount == Decimal("400000.00")
            assert item.remaining_balance == Decimal("400000.00")

        # مجموع الخطة أصبح: 800,000 + 600,000 = 1,400,000
        assert plan.total_principal == Decimal("1400000.00")

    def test_unit_swap_administrative_fee_journal_entry(self, unit_swap_setup):
        """إصدار قيد رسوم الاستبدال الإدارية وإثبات الإيراد عبر بوابة الحوكمة"""
        contract = unit_swap_setup["contract"]
        new_unit = unit_swap_setup["new_unit"]
        user = unit_swap_setup["user"]
        cash_acc = unit_swap_setup["cash_acc"]
        fee_income_acc = unit_swap_setup["fee_income_acc"]

        swap_record = UnitSwapService.create_swap_record(
            contract=contract,
            new_unit=new_unit,
            administrative_fee=Decimal("25000.00"),
            user=user
        )

        UnitSwapService.execute_unit_swap(
            swap_record=swap_record,
            user=user,
            payment_account=cash_acc
        )

        # استعلام قيد اليومية المرتبط بمحضر الاستبدال
        from financial.models.journal_entry import JournalEntry
        entry = JournalEntry.objects.filter(
            source_model="UnitSwapRecord",
            source_id=swap_record.id
        ).first()

        assert entry is not None
        lines = list(entry.lines.all())
        assert len(lines) == 2

        # سطر المدين: الخزينة (11110)
        debit_line = next(l for l in lines if l.debit > 0)
        assert debit_line.account.code == cash_acc.code
        assert debit_line.debit == Decimal("25000.00")

        # سطر الدائن: إيرادات رسوم الاستبدال (42202)
        credit_line = next(l for l in lines if l.credit > 0)
        assert credit_line.account.code == fee_income_acc.code
        assert credit_line.credit == Decimal("25000.00")

    def test_unit_swap_cannot_be_reexecuted(self, unit_swap_setup):
        """منع تكرار تنفيذ محضر الاستبدال المنفذ مسبقاً (Idempotency Guard)"""
        contract = unit_swap_setup["contract"]
        new_unit = unit_swap_setup["new_unit"]
        user = unit_swap_setup["user"]

        swap_record = UnitSwapService.create_swap_record(
            contract=contract,
            new_unit=new_unit,
            user=user
        )
        UnitSwapService.execute_unit_swap(swap_record=swap_record, user=user)

        with pytest.raises(ValidationError, match="تم تنفيذه وترحيله مسبقاً"):
            UnitSwapService.execute_unit_swap(swap_record=swap_record, user=user)
