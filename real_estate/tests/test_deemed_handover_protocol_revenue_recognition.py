# -*- coding: utf-8 -*-
"""
Tests for Deemed Handover Protocol & IFRS 15 Realized Revenue Recognition
MWHEBA ERP — Real Estate Wave 3 (Phase 10)
"""
from decimal import Decimal
from datetime import date
import pytest

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from customer.models import Customer
from financial.models import Currency, ChartOfAccounts, AccountType
from financial.services.role_registry import AccountRoleNames

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    PropertyHandoverReceipt,
    LegalNotice,
)
from real_estate.services.handover_service import HandoverExecutionService

User = get_user_model()


@pytest.fixture
def deemed_handover_setup(db):
    user, _ = User.objects.get_or_create(
        username="legal_handover_officer",
        defaults={"email": "legal_handover@test.com", "is_staff": True}
    )
    cfo, _ = User.objects.get_or_create(
        username="cfo_approver",
        defaults={"email": "cfo_handover@test.com", "is_staff": True}
    )
    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "جنيه مصري", "symbol": "ج.م"}
    )

    asset_type, _ = AccountType.objects.get_or_create(code='asset', defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'})
    liability_type, _ = AccountType.objects.get_or_create(code='liability', defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'})
    revenue_type, _ = AccountType.objects.get_or_create(code='revenue', defaults={'name': 'إيرادات', 'category': 'revenue', 'nature': 'credit'})
    expense_type, _ = AccountType.objects.get_or_create(code='expense', defaults={'name': 'مصروفات', 'category': 'expense', 'nature': 'debit'})

    contract_liability_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21102",
        defaults={
            "name": "التزامات عقود التطوير العقاري",
            "account_type": liability_type,
            "is_active": True
        }
    )
    revenue_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="41101",
        defaults={
            "name": "إيرادات بيع وتطوير عقاري محققة",
            "account_type": revenue_type,
            "is_active": True
        }
    )
    cogs_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="51100",
        defaults={
            "name": "تكلفة مبيعات التطوير العقاري",
            "account_type": expense_type,
            "is_active": True
        }
    )
    wip_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="12101",
        defaults={
            "name": "مشروعات تحت التنفيذ - أعمال إنشائية",
            "account_type": asset_type,
            "is_active": True
        }
    )

    customer, _ = Customer.objects.get_or_create(
        code="CUST-DEEM-01",
        defaults={"name": "المشتري الممتنع عن الاستلام", "default_currency": currency}
    )

    project = RealEstateProject.objects.create(
        code="PRJ-DEEM-01",
        name="أبراج النيل الملكية",
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        total_land_area=Decimal("12000.00"),
        gross_built_area=Decimal("45000.00"),
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, code="B-05", name="عمارة 5")
    floor = PropertyFloor.objects.create(block=block, floor_number=6, name="الدور السادس")

    unit = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="NR-U601",
        gross_area=Decimal("180.00"),
        net_area=Decimal("155.00"),
        meter_price=Decimal("25000.00"),
        total_price=Decimal("4500000.00"),
        progress_percentage=Decimal("100.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    contract = PropertyContract.objects.create(
        contract_number="CTR-DEEM-2026-001",
        project=project,
        unit=unit,
        customer=customer,
        final_contract_price=Decimal("4500000.00"),
        down_payment=Decimal("900000.00"),
        currency=currency,
        contract_date=date(2025, 2, 1),
        delivery_date=date(2027, 6, 30),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=user
    )

    # إنشاء إنذار رسمي مسلّم على يد محضر بانقضاء مهلة الحضور للاستلام
    notice = LegalNotice.objects.create(
        contract=contract,
        customer=customer,
        stage=LegalNotice.EscalationStage.STAGE_3_FORMAL_DEMAND,
        channel=LegalNotice.NoticeChannel.COURT_BAILIFF,
        status=LegalNotice.NoticeStatus.SERVED,
        total_demanded_amount=Decimal("4500000.00"),
        created_by=user
    )

    return {
        "user": user,
        "cfo": cfo,
        "customer": customer,
        "project": project,
        "unit": unit,
        "contract": contract,
        "legal_notice": notice,
        "accounts": {
            "liability": contract_liability_acc,
            "revenue": revenue_acc,
            "cogs": cogs_acc,
            "wip": wip_acc
        }
    }


@pytest.mark.django_db
class TestDeemedHandoverProtocolRevenueRecognition:
    """اختبارات بروتوكول التسليم الحُكمي بقوة العقد وقانون البناء"""

    def test_deemed_handover_execution_and_ifrs15_revenue_recognition(self, deemed_handover_setup):
        """التحقق من تنفيذ التسليم الحُكمي دون توقيع العميل وترحيل قيد الإيراد وتحويل الوحدة إلى DELIVERED_DEEMED"""
        setup = deemed_handover_setup
        contract = setup["contract"]
        unit = setup["unit"]
        user = setup["user"]
        cfo = setup["cfo"]
        notice = setup["legal_notice"]

        # إنشاء مسودة محضر تسليم حُكمي
        receipt = HandoverExecutionService.create_handover_receipt(
            contract=contract,
            handover_type=PropertyHandoverReceipt.HandoverType.DEEMED,
            created_by=user,
            legal_notice=notice,
            notes="تم إعمال بروتوكول التسليم الحُكمي لانقضاء أكثر من 60 يوماً على إعلان المشتري رسمياً على يد محضر."
        )

        assert receipt.status == PropertyHandoverReceipt.HandoverStatus.DRAFT
        assert receipt.handover_type == PropertyHandoverReceipt.HandoverType.DEEMED
        assert receipt.client_signatory_name == ""  # لا يتطلب توقيع المشتري الممتنع

        # تنفيذ التسليم الحُكمي
        executed = HandoverExecutionService.execute_deemed_handover(
            receipt=receipt,
            executed_by=cfo,
            recognized_revenue_amount=Decimal("4500000.00")
        )

        assert executed.status == PropertyHandoverReceipt.HandoverStatus.EXECUTED
        unit.refresh_from_db()
        assert unit.status == PropertyUnit.UnitStatus.DELIVERED_DEEMED
        assert executed.executed_by == cfo

        # التحقق من بصمة التوثيق المشفرة
        assert len(executed.verification_hash) == 64
        assert executed.verification_hash == executed.generate_verification_hash()

        # التحقق من قيد الإيراد المحقق IFRS 15
        rev_entry = executed.revenue_journal_entry
        assert rev_entry is not None
        assert rev_entry.is_balanced is True

        lines = list(rev_entry.lines.all())
        dr_line = [l for l in lines if l.debit > 0][0]
        cr_line = [l for l in lines if l.credit > 0][0]

        assert dr_line.account.code == "21102"
        assert dr_line.debit == Decimal("4500000.00")

        assert cr_line.account.code == "41101"
        assert cr_line.credit == Decimal("4500000.00")

    def test_deemed_handover_rejected_without_legal_notice(self, deemed_handover_setup):
        """التحقق من رفض إنشاء أو تنفيذ التسليم الحُكمي بدون ربط إنذار قانوني رسمي معتمد"""
        setup = deemed_handover_setup
        with pytest.raises(ValidationError) as exc_info:
            HandoverExecutionService.create_handover_receipt(
                contract=setup["contract"],
                handover_type=PropertyHandoverReceipt.HandoverType.DEEMED,
                created_by=setup["user"],
                legal_notice=None  # بدون إنذار
            )
        assert "إخطار قانوني رسمي" in str(exc_info.value)

    def test_deemed_handover_rejected_with_draft_or_unserved_notice(self, deemed_handover_setup):
        """التحقق من رفض التسليم الحُكمي إذا كان الإخطار القانوني لا يزال مسودة أو لم يتم إعلانه رسمياً"""
        setup = deemed_handover_setup
        unserved_notice = LegalNotice.objects.create(
            contract=setup["contract"],
            customer=setup["customer"],
            stage=LegalNotice.EscalationStage.STAGE_3_FORMAL_DEMAND,
            status=LegalNotice.NoticeStatus.DRAFT,  # مسودة لم تعلن
            created_by=setup["user"]
        )

        receipt = PropertyHandoverReceipt.objects.create(
            contract=setup["contract"],
            unit=setup["unit"],
            handover_type=PropertyHandoverReceipt.HandoverType.DEEMED,
            legal_notice=unserved_notice,
            created_by=setup["user"]
        )

        with pytest.raises(ValidationError) as exc_info:
            HandoverExecutionService.execute_deemed_handover(
                receipt=receipt,
                executed_by=setup["cfo"]
            )
        assert "لم يتم إرساله أو تسليمه رسمياً" in str(exc_info.value)

    def test_deemed_handover_with_interim_cogs(self, deemed_handover_setup):
        """التحقق من ترحيل تكلفة المبيعات التقديرية (Interim COGS) بالتوازي في التسليم الحُكمي"""
        setup = deemed_handover_setup
        receipt = HandoverExecutionService.create_handover_receipt(
            contract=setup["contract"],
            handover_type=PropertyHandoverReceipt.HandoverType.DEEMED,
            created_by=setup["user"],
            legal_notice=setup["legal_notice"]
        )

        budgeted_cost_per_meter = Decimal("14000.00")
        expected_cogs = budgeted_cost_per_meter * setup["unit"].gross_area  # 14000 * 180 = 2,520,000.00

        executed = HandoverExecutionService.execute_deemed_handover(
            receipt=receipt,
            executed_by=setup["cfo"],
            budgeted_cost_per_meter=budgeted_cost_per_meter
        )

        assert executed.interim_cogs_amount == expected_cogs
        assert executed.cogs_journal_entry is not None
        assert executed.cogs_journal_entry.is_balanced is True

        cogs_lines = list(executed.cogs_journal_entry.lines.all())
        dr = [l for l in cogs_lines if l.debit > 0][0]
        cr = [l for l in cogs_lines if l.credit > 0][0]

        assert dr.account.code == "51100"
        assert dr.debit == expected_cogs

        assert cr.account.code == "12101"
        assert cr.credit == expected_cogs
