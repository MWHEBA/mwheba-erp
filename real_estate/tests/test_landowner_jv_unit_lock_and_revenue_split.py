# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from datetime import date
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from customer.models import Customer
from financial.models import Currency
from sale.models.installments import InstallmentPlan, InstallmentItem
from real_estate.models.project import RealEstateProject
from real_estate.models.topology import PropertyBlock, PropertyFloor
from real_estate.models.unit import PropertyUnit
from real_estate.models.booking import UnitBooking
from real_estate.models.contract import PropertyContract
from real_estate.models.partnership import (
    LandownerPartnership,
    LandownerUnitAllocation,
    LandownerRevenueShareAccrual
)
from real_estate.services.landowner_service import LandownerPartnershipService

User = get_user_model()


@pytest.fixture
def landowner_setup(db):
    user, _ = User.objects.get_or_create(username="jv_admin", defaults={"is_staff": True})
    currency, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "جنيه مصري", "symbol": "ج.م"})

    customer, _ = Customer.objects.get_or_create(
        code="CUST-BUYER-JV",
        defaults={"name": "عميل مشتري بالكمبوند", "default_currency": currency}
    )

    project, _ = RealEstateProject.objects.get_or_create(
        code="PRJ-JV-01",
        defaults={
            "name": "مشروع أبراج النيل للمشاركة",
            "start_date": date(2025, 1, 1),
            "expected_completion_date": date(2028, 1, 1),
            "total_land_area": Decimal("5000.00"),
            "gross_built_area": Decimal("25000.00"),
            "created_by": user
        }
    )
    block, _ = PropertyBlock.objects.get_or_create(project=project, code="BLK-A", defaults={"name": "برج أ"})
    floor, _ = PropertyFloor.objects.get_or_create(block=block, floor_number=1, defaults={"name": "الدور الأول"})

    unit_allocated = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="JV-U101",
        gross_area=Decimal("150.00"),
        net_area=Decimal("125.00"),
        meter_price=Decimal("30000.00"),
        total_price=Decimal("4500000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    unit_market = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="JV-U102",
        gross_area=Decimal("150.00"),
        net_area=Decimal("125.00"),
        meter_price=Decimal("30000.00"),
        total_price=Decimal("4500000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    # اتفاقية مشاركة بنظام مختلط (وحدات عينية + 35% من إيرادات باقي الوحدات)
    partnership = LandownerPartnership.objects.create(
        project=project,
        partner_name="الحاج إبراهيم الدسوقي وشركاه (ملاك الأرض)",
        partnership_type=LandownerPartnership.PartnershipType.HYBRID,
        revenue_share_percentage=Decimal("35.00"),
        land_area_sqm=Decimal("5000.00"),
        agreed_land_valuation=Decimal("75000000.00"),
        status=LandownerPartnership.PartnershipStatus.ACTIVE,
        created_by=user
    )

    # خطة تقسيط وعقد للوحدة المطروحة للبيع في السوق (unit_market)
    plan = InstallmentPlan.objects.create(
        sale=None,
        total_principal=Decimal("4000000.00"),
        total_amount=Decimal("4000000.00"),
        number_of_installments=4,
        start_date=date(2026, 1, 1),
        customer=customer,
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=user
    )

    contract = PropertyContract.objects.create(
        contract_number="CTR-JV-2026-01",
        project=project,
        unit=unit_market,
        customer=customer,
        installment_plan=plan,
        contract_date=date(2026, 1, 1),
        delivery_date=date(2028, 1, 1),
        final_contract_price=Decimal("4500000.00"),
        down_payment=Decimal("500000.00"),
        currency=currency,
        created_by=user,
        status=PropertyContract.ContractStatus.ACTIVE
    )

    item = InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        due_date=date(2026, 4, 1),
        principal_amount=Decimal("1000000.00"),
        total_amount=Decimal("1000000.00"),
        paid_amount=Decimal("0.00"),
        cash_status=InstallmentItem.CashStatus.PENDING
    )

    return {
        "user": user,
        "project": project,
        "partnership": partnership,
        "unit_allocated": unit_allocated,
        "unit_market": unit_market,
        "customer": customer,
        "contract": contract,
        "installment_item": item,
    }


class TestLandownerJVUnitLockAndRevenueSplit:
    """
    اختبارات قفل وحدات مالك الأرض واقتسام الإيرادات وأستاذ المساعد
    """

    def test_landowner_unit_allocation_locks_status(self, landowner_setup):
        """تخصيص الوحدة يقفل حالتها تلقائياً على LANDOWNER_ALLOCATED"""
        data = landowner_setup
        unit = data["unit_allocated"]
        partnership = data["partnership"]

        allocations = LandownerPartnershipService.allocate_units_to_landowner(
            partnership=partnership,
            units=[unit],
            user=data["user"]
        )

        assert len(allocations) == 1
        unit.refresh_from_db()
        assert unit.status == PropertyUnit.UnitStatus.LANDOWNER_ALLOCATED

    def test_booking_attempt_on_allocated_unit_is_hard_blocked(self, landowner_setup):
        """محاولة حجز وحدة مخصصة لمالك الأرض تُحظر بصراحة وترفع ValidationError"""
        data = landowner_setup
        unit = data["unit_allocated"]
        partnership = data["partnership"]

        # تخصيص الوحدة
        LandownerPartnershipService.allocate_units_to_landowner(
            partnership=partnership,
            units=[unit],
            user=data["user"]
        )
        unit.refresh_from_db()

        # محاولة إنشاء حجز من قبل مسؤول مبيعات
        booking = UnitBooking(
            booking_number="BK-TEST-LOCKED",
            unit=unit,
            customer=data["customer"],
            booking_date=timezone.localdate(),
            expiry_date=timezone.localdate(),
            holding_deposit=Decimal("100000.00"),
            created_by=data["user"]
        )

        with pytest.raises(ValidationError) as exc_info:
            booking.clean()

        assert "مخصصة لمالك الأرض" in str(exc_info.value)

    def test_contract_attempt_on_allocated_unit_is_hard_blocked(self, landowner_setup):
        """محاولة إبرام عقد بيع على وحدة مخصصة لمالك الأرض تُحظر وترفع ValidationError"""
        data = landowner_setup
        unit = data["unit_allocated"]
        partnership = data["partnership"]

        LandownerPartnershipService.allocate_units_to_landowner(
            partnership=partnership,
            units=[unit],
            user=data["user"]
        )
        unit.refresh_from_db()

        contract = PropertyContract(
            contract_number="CTR-TEST-LOCKED",
            project=data["project"],
            unit=unit,
            customer=data["customer"],
            contract_date=timezone.localdate(),
            delivery_date=timezone.localdate(),
            final_contract_price=Decimal("4500000.00"),
            down_payment=Decimal("500000.00"),
            currency=data["contract"].currency,
            created_by=data["user"]
        )

        with pytest.raises(ValidationError) as exc_info:
            contract.clean()

        assert "مخصصة لمالك الأرض" in str(exc_info.value)

    def test_deallocate_unit_reverts_to_available(self, landowner_setup):
        """إلغاء التخصيص يعيد الوحدة تلقائياً لحالة AVAILABLE"""
        data = landowner_setup
        unit = data["unit_allocated"]
        partnership = data["partnership"]

        allocs = LandownerPartnershipService.allocate_units_to_landowner(
            partnership=partnership,
            units=[unit],
            user=data["user"]
        )
        unit.refresh_from_db()
        assert unit.status == PropertyUnit.UnitStatus.LANDOWNER_ALLOCATED

        # إلغاء التخصيص
        LandownerPartnershipService.deallocate_unit(allocs[0], user=data["user"])
        unit.refresh_from_db()
        assert unit.status == PropertyUnit.UnitStatus.AVAILABLE

    def test_revenue_sharing_pro_rata_accrual(self, landowner_setup):
        """احتساب وقيد استحقاق مالك الأرض التناسبي (35%) فور تحصيل دفعة قسط"""
        data = landowner_setup
        partnership = data["partnership"]
        contract = data["contract"]
        installment = data["installment_item"]

        # تحصيل قسط بقيمة 500,000 جنيه
        collected_amount = Decimal("500000.00")
        expected_landowner_share = Decimal("175000.00")  # 500,000 * 35% = 175,000

        accrual = LandownerPartnershipService.calculate_and_accrue_revenue_share(
            partnership=partnership,
            contract=contract,
            collected_amount=collected_amount,
            installment_item=installment,
            collection_event='INSTALLMENT_COLLECTION',
            user=data["user"]
        )

        assert accrual.partnership == partnership
        assert accrual.collected_amount == collected_amount
        assert accrual.share_percentage == Decimal("35.00")
        assert accrual.accrued_amount == expected_landowner_share
        assert accrual.status == LandownerRevenueShareAccrual.AccrualStatus.ACCRUED

    def test_landowner_subledger_summary(self, landowner_setup):
        """التحقق من كشف الحساب التحليلي لأستاذ مالك الأرض المساعد"""
        data = landowner_setup
        partnership = data["partnership"]
        contract = data["contract"]

        # قيد استحقاقين متتاليين
        accrual1 = LandownerPartnershipService.calculate_and_accrue_revenue_share(
            partnership=partnership,
            contract=contract,
            collected_amount=Decimal("1000000.00"),
            user=data["user"]
        )  # 350,000
        accrual2 = LandownerPartnershipService.calculate_and_accrue_revenue_share(
            partnership=partnership,
            contract=contract,
            collected_amount=Decimal("500000.00"),
            user=data["user"]
        )  # 175,000

        # محاكاة صرف استحقاق أول
        accrual1.status = LandownerRevenueShareAccrual.AccrualStatus.DISBURSED
        accrual1.save()

        summary = LandownerPartnershipService.get_landowner_subledger_summary(partnership)

        assert summary["total_collected_base"] == Decimal("1500000.00")
        assert summary["total_accrued_share"] == Decimal("525000.00")
        assert summary["total_disbursed"] == Decimal("350000.00")
        assert summary["net_payable_balance"] == Decimal("175000.00")
