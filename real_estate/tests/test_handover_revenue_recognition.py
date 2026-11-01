# -*- coding: utf-8 -*-
"""
Tests for Property Handover Execution & IFRS 15 Realized Revenue Recognition
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
    UnitSnagItem,
)
from real_estate.services.handover_service import HandoverExecutionService

User = get_user_model()


@pytest.fixture
def handover_setup(db):
    user, _ = User.objects.get_or_create(
        username="handover_admin",
        defaults={"email": "handover_admin@test.com", "is_staff": True}
    )
    engineer, _ = User.objects.get_or_create(
        username="resident_engineer",
        defaults={"email": "resident_eng@test.com", "is_staff": True}
    )
    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "جنيه مصري", "symbol": "ج.م"}
    )

    # تجهيز أنواع الحسابات والحسابات المحاسبية لدورة معيار IFRS 15 وتكلفة المبيعات
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
        code="CUST-HDR-01",
        defaults={"name": "م. طارق العريان", "default_currency": currency}
    )

    project = RealEstateProject.objects.create(
        code="PRJ-HDR-01",
        name="كمبوند بارك إكسيلنس",
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        total_land_area=Decimal("15000.00"),
        gross_built_area=Decimal("60000.00"),
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, code="T-10", name="برج 10")
    floor = PropertyFloor.objects.create(block=block, floor_number=4, name="الدور الرابع")

    unit = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="PX-U404",
        gross_area=Decimal("150.00"),
        net_area=Decimal("128.00"),
        meter_price=Decimal("20000.00"),
        total_price=Decimal("3000000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    contract = PropertyContract.objects.create(
        contract_number="CTR-HDR-2026-001",
        project=project,
        unit=unit,
        customer=customer,
        final_contract_price=Decimal("3000000.00"),
        down_payment=Decimal("600000.00"),
        currency=currency,
        contract_date=date(2025, 2, 1),
        delivery_date=date(2027, 6, 30),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=user
    )

    return {
        "user": user,
        "engineer": engineer,
        "customer": customer,
        "project": project,
        "unit": unit,
        "contract": contract,
        "accounts": {
            "liability": contract_liability_acc,
            "revenue": revenue_acc,
            "cogs": cogs_acc,
            "wip": wip_acc
        }
    }


@pytest.mark.django_db
class TestHandoverRevenueRecognition:
    """اختبارات دورة التسليم الفعلي والاعتراف بالإيراد وفق IFRS 15 وتكلفة المبيعات"""

    def test_physical_handover_execution_and_ifrs15_revenue_recognition(self, handover_setup):
        """التحقق من اعتماد التسليم الفعلي وترحيل قيد الاعتراف بالإيراد المتوازن تماماً بالقرش"""
        setup = handover_setup
        contract = setup["contract"]
        unit = setup["unit"]
        user = setup["user"]
        engineer = setup["engineer"]

        # إنشاء مسودة محضر تسليم فعلي
        receipt = HandoverExecutionService.create_handover_receipt(
            contract=contract,
            handover_type=PropertyHandoverReceipt.HandoverType.PHYSICAL,
            created_by=user,
            site_engineer=engineer,
            client_signatory_name="م. طارق العريان (أصيلاً)",
            client_signatory_national_id="29010101234567",
            electric_meter_reading=Decimal("1420.50"),
            water_meter_reading=Decimal("312.00"),
            keys_handed_over_count=4,
            access_cards_count=2,
            notes="تم استلام الشقة والشبابيك والأبواب بحالة ممتازة دون أي ملاحظات."
        )

        assert receipt.status == PropertyHandoverReceipt.HandoverStatus.DRAFT
        assert receipt.receipt_number.startswith("HDR")
        assert unit.status == PropertyUnit.UnitStatus.CONTRACTED

        # تنفيذ التسليم الفعلي
        executed_receipt = HandoverExecutionService.execute_physical_handover(
            receipt=receipt,
            executed_by=engineer,
            recognized_revenue_amount=Decimal("3000000.00")
        )

        # 1. التحقق من تحول حالة المحضر والوحدة
        assert executed_receipt.status == PropertyHandoverReceipt.HandoverStatus.EXECUTED
        unit.refresh_from_db()
        assert unit.status == PropertyUnit.UnitStatus.DELIVERED
        assert executed_receipt.executed_by == engineer
        assert executed_receipt.executed_at is not None

        # 2. التحقق من توليد بصمة الهاش الرقمية SHA-256
        assert len(executed_receipt.verification_hash) == 64
        assert executed_receipt.verification_hash == executed_receipt.generate_verification_hash()

        # 3. التحقق من قيد الاعتراف بالإيراد IFRS 15 المتوازن
        rev_entry = executed_receipt.revenue_journal_entry
        assert rev_entry is not None
        assert rev_entry.is_balanced is True

        lines = list(rev_entry.lines.all())
        assert len(lines) == 2

        # طرف مدين: تخفيض التزامات العقود 21102
        dr_line = [l for l in lines if l.debit > 0][0]
        assert dr_line.account.code == "21102"
        assert dr_line.debit == Decimal("3000000.00")

        # طرف دائن: إثبات إيراد بيع عقاري محقق 41101
        cr_line = [l for l in lines if l.credit > 0][0]
        assert cr_line.account.code == "41101"
        assert cr_line.credit == Decimal("3000000.00")

    def test_physical_handover_allocates_interim_cogs(self, handover_setup):
        """التحقق من احتساب وترحيل تكلفة مبيعات الوحدة التقديرية (Interim COGS) من مشروعات تحت التنفيذ"""
        setup = handover_setup
        contract = setup["contract"]
        unit = setup["unit"]
        engineer = setup["engineer"]

        receipt = HandoverExecutionService.create_handover_receipt(
            contract=contract,
            handover_type=PropertyHandoverReceipt.HandoverType.PHYSICAL,
            created_by=setup["user"],
            site_engineer=engineer,
            client_signatory_name="م. طارق العريان"
        )

        # التكلفة التقديرية للمتر 12,000 ج.م × 150 م² = 1,800,000 ج.م
        budgeted_meter_cost = Decimal("12000.00")
        expected_cogs = budgeted_meter_cost * unit.gross_area  # 1,800,000.00

        executed_receipt = HandoverExecutionService.execute_physical_handover(
            receipt=receipt,
            executed_by=engineer,
            budgeted_cost_per_meter=budgeted_meter_cost
        )

        assert executed_receipt.interim_cogs_amount == expected_cogs
        cogs_entry = executed_receipt.cogs_journal_entry
        assert cogs_entry is not None
        assert cogs_entry.is_balanced is True

        lines = list(cogs_entry.lines.all())
        assert len(lines) == 2

        # طرف مدين: تكلفة مبيعات التطوير العقاري 51100
        dr_line = [l for l in lines if l.debit > 0][0]
        assert dr_line.account.code == "51100"
        assert dr_line.debit == expected_cogs

        # طرف دائن: تخفيض مشروعات تحت التنفيذ 12101
        cr_line = [l for l in lines if l.credit > 0][0]
        assert cr_line.account.code == "12101"
        assert cr_line.credit == expected_cogs

    def test_physical_handover_blocked_by_open_critical_snags(self, handover_setup):
        """التحقق من حظر تسليم الوحدة في حالة وجود ملاحظات فنية حرجة (Blockers) غير معالجة"""
        setup = handover_setup
        contract = setup["contract"]
        unit = setup["unit"]
        engineer = setup["engineer"]

        # تسجيل عيب حرج يمنع السكن (مثل كسر في مواسير التغذية أو تسريب كهرباء)
        UnitSnagItem.objects.create(
            unit=unit,
            room_location="الحمام الرئيسي",
            category=UnitSnagItem.SnagCategory.PLUMBING,
            severity=UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER,
            description="تسريب شديد في خط التغذية الرئيسي للحمام أسفل الأرضية",
            status=UnitSnagItem.SnagStatus.OPEN,
            created_by=engineer
        )

        receipt = HandoverExecutionService.create_handover_receipt(
            contract=contract,
            created_by=setup["user"],
            site_engineer=engineer,
            client_signatory_name="م. طارق العريان"
        )

        with pytest.raises(ValidationError) as exc_info:
            HandoverExecutionService.execute_physical_handover(
                receipt=receipt,
                executed_by=engineer
            )

        assert "ملاحظة فنية حرجة" in str(exc_info.value)
        # التأكد من بقاء المحضر كمسودة والوحدة لم يتم تسليمها
        receipt.refresh_from_db()
        assert receipt.status == PropertyHandoverReceipt.HandoverStatus.DRAFT
        unit.refresh_from_db()
        assert unit.status != PropertyUnit.UnitStatus.DELIVERED

    def test_physical_handover_succeeds_after_resolving_critical_snags(self, handover_setup):
        """التحقق من نجاح التسليم بمجرد معالجة واعتماد حل العيب الحرج من الاستشاري"""
        setup = handover_setup
        contract = setup["contract"]
        unit = setup["unit"]
        engineer = setup["engineer"]

        snag = UnitSnagItem.objects.create(
            unit=unit,
            room_location="لوحة القواطع الرئيسية",
            category=UnitSnagItem.SnagCategory.ELECTRICAL,
            severity=UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER,
            description="خلل في القاطع التفاضلي للكهرباء",
            status=UnitSnagItem.SnagStatus.OPEN,
            created_by=engineer
        )

        receipt = HandoverExecutionService.create_handover_receipt(
            contract=contract,
            created_by=setup["user"],
            site_engineer=engineer,
            client_signatory_name="م. طارق العريان"
        )

        # حل الملاحظة واعتماد الاستشاري
        snag.mark_resolved(engineer=engineer, resolution_notes="تم استبدال القاطع واختبار الأحمال بنجاح.")

        # المحاولة الآن بعد المعالجة
        executed = HandoverExecutionService.execute_physical_handover(
            receipt=receipt,
            executed_by=engineer
        )
        assert executed.status == PropertyHandoverReceipt.HandoverStatus.EXECUTED
        unit.refresh_from_db()
        assert unit.status == PropertyUnit.UnitStatus.DELIVERED

    def test_physical_handover_requires_client_signatory_name(self, handover_setup):
        """التحقق من إلزامية اسم المستلم أو الوكيل الحاضر للتسليم الفعلي"""
        setup = handover_setup
        receipt = HandoverExecutionService.create_handover_receipt(
            contract=setup["contract"],
            created_by=setup["user"],
            site_engineer=setup["engineer"],
            client_signatory_name=""  # فارغ
        )

        with pytest.raises(ValidationError) as exc_info:
            HandoverExecutionService.execute_physical_handover(
                receipt=receipt,
                executed_by=setup["engineer"]
            )
        assert "اسم المستلم" in str(exc_info.value)

    def test_handover_idempotency_prevents_double_execution(self, handover_setup):
        """التحقق من حظر إعادة تنفيذ المحضر المنفذ مسبقاً لمنع ازدواجية القيود"""
        setup = handover_setup
        receipt = HandoverExecutionService.create_handover_receipt(
            contract=setup["contract"],
            created_by=setup["user"],
            site_engineer=setup["engineer"],
            client_signatory_name="م. طارق العريان"
        )
        HandoverExecutionService.execute_physical_handover(
            receipt=receipt,
            executed_by=setup["engineer"]
        )

        with pytest.raises(ValidationError) as exc_info:
            HandoverExecutionService.execute_physical_handover(
                receipt=receipt,
                executed_by=setup["engineer"]
            )
        assert "معتمد ومنفذ بالفعل" in str(exc_info.value)
