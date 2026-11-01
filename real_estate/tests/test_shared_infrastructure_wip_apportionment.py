# -*- coding: utf-8 -*-
"""
Test Suite: Shared Central Infrastructure WIP Cost Apportionment
(Wave 3 Phase 14 - Shared Central Infrastructure Cost Apportionment)
"""

import pytest
from decimal import Decimal
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from financial.models import ChartOfAccounts, AccountType, Currency, JournalEntry
from real_estate.models import (
    RealEstateProject,
    SharedInfrastructureAsset,
    SharedInfrastructureApportionment,
)
from real_estate.services.infrastructure_service import InfrastructureApportionmentService

User = get_user_model()


@pytest.fixture
def infra_setup(db):
    user, _ = User.objects.get_or_create(
        username="cost_accountant",
        defaults={"email": "cost_accountant@test.com", "is_staff": True}
    )
    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "جنيه مصري", "symbol": "ج.م"}
    )

    asset_type, _ = AccountType.objects.get_or_create(
        code='asset',
        defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
    )

    wip_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="12101",
        defaults={
            "name": "مشروعات تحت التنفيذ - أعمال إنشاءات وتطوير",
            "account_type": asset_type,
            "is_active": True
        }
    )
    infra_asset_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="12390",
        defaults={
            "name": "أصول بنية تحتية مركزية وسيطة",
            "account_type": asset_type,
            "is_active": True
        }
    )

    project_a = RealEstateProject.objects.create(
        code="PRJ-TWR-A",
        name="برج النرجس السكني (A)",
        start_date=date(2024, 1, 1),
        expected_completion_date=date(2026, 12, 31),
        total_land_area=Decimal("5000.00"),
        gross_built_area=Decimal("30000.00"),
        created_by=user
    )

    project_b = RealEstateProject.objects.create(
        code="PRJ-TWR-B",
        name="برج الياسمين الفندقي (B)",
        start_date=date(2024, 1, 1),
        expected_completion_date=date(2026, 12, 31),
        total_land_area=Decimal("5000.00"),
        gross_built_area=Decimal("20000.00"),
        created_by=user
    )

    # محطة تكييف مركزي متراكم عليها تكاليف إنشاء 5,000,000 ج.م
    central_chiller = SharedInfrastructureAsset.objects.create(
        code="CHILLER-01",
        name="محطة تكييف مركزي المجمع الشرقي (Central Chillers)",
        compound_name="كمبوند صن رايز",
        infrastructure_type=SharedInfrastructureAsset.InfrastructureType.CENTRAL_CHILLERS,
        total_capacity_load=Decimal("2500.00"),
        capacity_unit="TR",
        accumulated_wip_cost=Decimal("5000000.00"),
        apportioned_wip_cost=Decimal("0.00"),
        created_by=user
    )

    return {
        "user": user,
        "currency": currency,
        "wip_acc": wip_acc,
        "infra_asset_acc": infra_asset_acc,
        "project_a": project_a,
        "project_b": project_b,
        "central_chiller": central_chiller,
    }


@pytest.mark.django_db
class TestSharedInfrastructureApportionment:

    def test_create_apportionment_by_sellable_area(self, infra_setup):
        """إنشاء محضر توزيع واحتساب نسب التوزيع بدقة (60% للبرج A و 40% للبرج B)"""
        user = infra_setup["user"]
        chiller = infra_setup["central_chiller"]
        proj_a = infra_setup["project_a"]
        proj_b = infra_setup["project_b"]

        beneficiary_metrics = [
            {"project": proj_a, "metric_value": Decimal("30000.00")},  # 30,000 م² (60%)
            {"project": proj_b, "metric_value": Decimal("20000.00")},  # 20,000 م² (40%)
        ]

        apportionment = InfrastructureApportionmentService.create_apportionment(
            infrastructure_asset=chiller,
            total_amount=Decimal("2000000.00"),
            beneficiary_metrics=beneficiary_metrics,
            allocation_basis=SharedInfrastructureApportionment.AllocationBasis.SELLABLE_AREA,
            notes="توزيع دفعة أعمال التكييف المركزي مرحلة 1",
            user=user
        )

        assert apportionment.id is not None
        assert apportionment.status == SharedInfrastructureApportionment.ApportionmentStatus.DRAFT
        assert apportionment.total_apportioned_amount == Decimal("2000000.00")
        assert apportionment.lines.count() == 2

        line_a = apportionment.lines.get(beneficiary_project=proj_a)
        assert line_a.allocation_percentage == Decimal("60.0000")
        assert line_a.allocated_amount == Decimal("1200000.00")

        line_b = apportionment.lines.get(beneficiary_project=proj_b)
        assert line_b.allocation_percentage == Decimal("40.0000")
        assert line_b.allocated_amount == Decimal("800000.00")

    def test_post_apportionment_journal_entry(self, infra_setup):
        """ترحيل التوزيع وإثبات قيد نقل التكاليف إلى مشروعات تحت التنفيذ الخاصة بكل برج"""
        user = infra_setup["user"]
        chiller = infra_setup["central_chiller"]
        proj_a = infra_setup["project_a"]
        proj_b = infra_setup["project_b"]
        wip_acc = infra_setup["wip_acc"]
        infra_asset_acc = infra_setup["infra_asset_acc"]

        beneficiary_metrics = [
            {"project": proj_a, "metric_value": Decimal("30000.00")},
            {"project": proj_b, "metric_value": Decimal("20000.00")},
        ]

        apportionment = InfrastructureApportionmentService.create_apportionment(
            infrastructure_asset=chiller,
            total_amount=Decimal("2000000.00"),
            beneficiary_metrics=beneficiary_metrics,
            user=user
        )

        posted_app = InfrastructureApportionmentService.post_apportionment(
            apportionment=apportionment,
            user=user
        )

        assert posted_app.status == SharedInfrastructureApportionment.ApportionmentStatus.POSTED

        chiller.refresh_from_db()
        assert chiller.apportioned_wip_cost == Decimal("2000000.00")
        assert chiller.remaining_wip_cost == Decimal("3000000.00")

        # التحقق من قيد اليومية
        je = JournalEntry.objects.filter(
            source_model="SharedInfrastructureApportionment",
            source_id=posted_app.id
        ).first()

        assert je is not None
        lines = list(je.lines.all())
        assert len(lines) == 3

        # أسطر المدين لمشروعات الأبراج
        debit_lines = [l for l in lines if l.debit > 0]
        assert len(debit_lines) == 2
        line_a_je = next(l for l in debit_lines if proj_a.name in l.description)
        assert line_a_je.account.code == wip_acc.code
        assert line_a_je.debit == Decimal("1200000.00")

        line_b_je = next(l for l in debit_lines if proj_b.name in l.description)
        assert line_b_je.account.code == wip_acc.code
        assert line_b_je.debit == Decimal("800000.00")

        # سطر الدائن للأصل الوسيط
        credit_line = next(l for l in lines if l.credit > 0)
        assert credit_line.account.code == infra_asset_acc.code
        assert credit_line.credit == Decimal("2000000.00")

    def test_apportionment_exceeding_wip_rejected(self, infra_setup):
        """رفض توزيع مبلغ يتجاوز الرصيد المتبقي بمحطة البنية التحتية"""
        user = infra_setup["user"]
        chiller = infra_setup["central_chiller"]
        proj_a = infra_setup["project_a"]

        beneficiary_metrics = [
            {"project": proj_a, "metric_value": Decimal("30000.00")},
        ]

        # الرصيد المتاح 5,000,000 ومحاولة توزيع 6,000,000
        with pytest.raises(ValidationError, match="يتجاوز الرصيد المتبقي المتاح"):
            InfrastructureApportionmentService.create_apportionment(
                infrastructure_asset=chiller,
                total_amount=Decimal("6000000.00"),
                beneficiary_metrics=beneficiary_metrics,
                user=user
            )

    def test_cannot_repost_apportionment(self, infra_setup):
        """منع تكرار ترحيل محضر التوزيع المرحل مسبقاً (Idempotency Guard)"""
        user = infra_setup["user"]
        chiller = infra_setup["central_chiller"]
        proj_a = infra_setup["project_a"]

        beneficiary_metrics = [
            {"project": proj_a, "metric_value": Decimal("30000.00")},
        ]

        apportionment = InfrastructureApportionmentService.create_apportionment(
            infrastructure_asset=chiller,
            total_amount=Decimal("1000000.00"),
            beneficiary_metrics=beneficiary_metrics,
            user=user
        )

        InfrastructureApportionmentService.post_apportionment(apportionment=apportionment, user=user)

        with pytest.raises(ValidationError, match="مرحل بالدفاتر مسبقاً"):
            InfrastructureApportionmentService.post_apportionment(apportionment=apportionment, user=user)
