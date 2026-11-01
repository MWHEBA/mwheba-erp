# -*- coding: utf-8 -*-
"""
Tests for Post-Handover Warranty Tickets & Contractor Retention Debits
MWHEBA ERP — Real Estate Wave 3 (Phase 12)
"""
from decimal import Decimal
from datetime import date, timedelta
import pytest

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from customer.models import Customer
from supplier.models import Supplier
from financial.models import Currency, ChartOfAccounts, AccountType
from financial.services.role_registry import AccountRoleNames

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    PropertyHandoverReceipt,
    ContractorProgressCertificate,
    WarrantyTicket,
)
from real_estate.services.warranty_service import WarrantyDefectService

User = get_user_model()


@pytest.fixture
def warranty_setup(db):
    user, _ = User.objects.get_or_create(
        username="warranty_officer",
        defaults={"email": "warranty_officer@test.com", "is_staff": True}
    )
    engineer, _ = User.objects.get_or_create(
        username="inspecting_eng",
        defaults={"email": "inspecting_eng@test.com", "is_staff": True}
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

    retention_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21310",
        defaults={
            "name": "تأمينات مقاولي الباطن المحتجزة (Contractor Retentions Payable)",
            "account_type": liability_type,
            "is_active": True
        }
    )
    cash_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11110",
        defaults={
            "name": "الخزينة الرئيسية للمشروع",
            "account_type": asset_type,
            "is_active": True
        }
    )

    customer, _ = Customer.objects.get_or_create(
        code="CUST-WRN-01",
        defaults={"name": "السيد حازم إمام", "default_currency": currency}
    )

    contractor, _ = Supplier.objects.get_or_create(
        code="SUP-CONTR-01",
        defaults={"name": "شركة الإسكندرية للأعمال الصحية والسباكة"}
    )

    project = RealEstateProject.objects.create(
        code="PRJ-WRN-01",
        name="كمبوند جرين تاورز",
        start_date=date(2024, 1, 1),
        expected_completion_date=date(2026, 12, 31),
        total_land_area=Decimal("12000.00"),
        gross_built_area=Decimal("45000.00"),
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, code="B-02", name="برج الياسمين")
    floor = PropertyFloor.objects.create(block=block, floor_number=2, name="الدور الثاني")

    unit = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="GT-U202",
        gross_area=Decimal("140.00"),
        net_area=Decimal("120.00"),
        meter_price=Decimal("25000.00"),
        total_price=Decimal("3500000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    contract = PropertyContract.objects.create(
        contract_number="CTR-WRN-2026-001",
        project=project,
        unit=unit,
        customer=customer,
        final_contract_price=Decimal("3500000.00"),
        down_payment=Decimal("700000.00"),
        currency=currency,
        contract_date=date(2024, 5, 1),
        delivery_date=date(2025, 10, 1),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=user
    )

    # إنشاء محضر تسليم منفذ قبل 60 يوماً
    handover_date = timezone.localdate() - timedelta(days=60)
    receipt = PropertyHandoverReceipt.objects.create(
        contract=contract,
        unit=unit,
        handover_type=PropertyHandoverReceipt.HandoverType.PHYSICAL,
        status=PropertyHandoverReceipt.HandoverStatus.EXECUTED,
        handover_date=handover_date,
        client_signatory_name="حازم إمام",
        created_by=user
    )
    unit.status = PropertyUnit.UnitStatus.DELIVERED
    unit.save(update_fields=['status'])

    # إنشاء مستخلص مقاول باطن معتمد بمبلغ تأمين محتجز 100,000 ج.م
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="CERT-PLUMB-01",
        project=project,
        contractor=contractor,
        currency=currency,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 3, 31),
        gross_certified_work=Decimal("2000000.00"),
        current_period_work=Decimal("2000000.00"),
        retention_rate=Decimal("5.00"),
        retention_amount=Decimal("100000.00"),
        net_amount=Decimal("1900000.00"),
        status=ContractorProgressCertificate.CertificateStatus.APPROVED,
        created_by=user
    )

    return {
        "user": user,
        "engineer": engineer,
        "customer": customer,
        "contractor": contractor,
        "project": project,
        "unit": unit,
        "contract": contract,
        "receipt": receipt,
        "certificate": cert,
        "retention_account": retention_acc,
        "cash_account": cash_acc
    }


@pytest.mark.django_db
class TestContractorRetentionWarrantyDebit:
    """اختبارات تذاكر الضمان وخصم تكاليف إصلاح العيوب من تأمين أعمال المقاولين دون المساس بقائمة الدخل"""

    def test_create_warranty_ticket_within_warranty_period(self, warranty_setup):
        """التحقق من فتح تذكرة ضمان بنجاح لوحدة مسلّمة ضمن فترة الضمان السارية"""
        setup = warranty_setup
        ticket = WarrantyDefectService.create_warranty_ticket(
            unit=setup["unit"],
            contract=setup["contract"],
            customer=setup["customer"],
            category=WarrantyTicket.TicketCategory.FINISHING_PLUMBING,
            priority=WarrantyTicket.TicketPriority.HIGH,
            title="تسريب في محبس الدفن الرئيسي للحمام",
            description="تسريب مياه مستمر من أسفل سيراميك الحمام الرئيسي",
            created_by=setup["user"]
        )

        assert ticket.status == WarrantyTicket.TicketStatus.REPORTED
        assert ticket.ticket_number.startswith("WRN-GT-U202-")
        assert ticket.unit == setup["unit"]
        assert ticket.actual_repair_cost == Decimal("0.00")

    def test_create_warranty_ticket_rejected_for_undelivered_unit(self, warranty_setup):
        """التحقق من رفض فتح تذكرة ضمان لوحدة غير مسلّمة بعد"""
        setup = warranty_setup
        undelivered_unit = PropertyUnit.objects.create(
            project=setup["project"],
            floor=setup["unit"].floor,
            unit_code="GT-U203",
            gross_area=Decimal("120.00"),
            net_area=Decimal("100.00"),
            meter_price=Decimal("25000.00"),
            total_price=Decimal("3000000.00"),
            status=PropertyUnit.UnitStatus.CONTRACTED  # غير مسلّمة
        )

        with pytest.raises(ValidationError) as exc_info:
            WarrantyDefectService.create_warranty_ticket(
                unit=undelivered_unit,
                contract=setup["contract"],
                customer=setup["customer"],
                category=WarrantyTicket.TicketCategory.FINISHING_ELECTRICAL,
                title="عطل في مفاتيح الإنارة",
                description="مفاتيح الإنارة لا تعمل",
                created_by=setup["user"]
            )
        assert "لم يتم تسليمها للعميل بعد" in str(exc_info.value)

    def test_create_warranty_ticket_rejected_when_warranty_expired(self, warranty_setup):
        """التحقق من رفض فتح تذكرة ضمان تشطيبات إذا انقضت أكثر من سنة على تاريخ التسليم"""
        setup = warranty_setup
        # تعديل تاريخ محضر التسليم ليكون قبل 400 يوم (أكثر من سنة)
        setup["receipt"].handover_date = timezone.localdate() - timedelta(days=400)
        setup["receipt"].save(update_fields=['handover_date'])

        with pytest.raises(ValidationError) as exc_info:
            WarrantyDefectService.create_warranty_ticket(
                unit=setup["unit"],
                contract=setup["contract"],
                customer=setup["customer"],
                category=WarrantyTicket.TicketCategory.FINISHING_PAINTING,
                warranty_type=WarrantyTicket.WarrantyType.FINISHING_ONE_YEAR,
                title="تقشير دهانات الصالة",
                description="تقشير في دهانات الصالة",
                created_by=setup["user"]
            )
        assert "انتهت فترة ضمان التشطيبات" in str(exc_info.value)

    def test_contractor_complies_and_resolves_with_zero_financial_impact(self, warranty_setup):
        """التحقق من قيام المقاول بالإصلاح على نفقته الخاصة وإغلاق التذكرة دون أي قيد أو تكلفة مالية على المطور"""
        setup = warranty_setup
        ticket = WarrantyDefectService.create_warranty_ticket(
            unit=setup["unit"],
            contract=setup["contract"],
            customer=setup["customer"],
            category=WarrantyTicket.TicketCategory.FINISHING_PLUMBING,
            title="تسريب في محبس الدفن",
            description="تسريب في محبس الدفن",
            created_by=setup["user"]
        )

        # إسناد التذكرة لمقاول الباطن
        WarrantyDefectService.inspect_and_assign_contractor(
            ticket=ticket,
            responsible_contractor=setup["contractor"],
            inspected_by=setup["engineer"],
            engineer_notes="تمت المعاينة ومطلوب من مقاول السباكة تغيير قلب المحبس"
        )
        assert ticket.status == WarrantyTicket.TicketStatus.CONTRACTOR_NOTIFIED
        assert ticket.contractor_sla_deadline is not None

        # قيام المقاول بالإصلاح على حسابه
        resolved_ticket = WarrantyDefectService.resolve_by_contractor(
            ticket=ticket,
            resolution_notes="تم تغيير قلب المحبس ومعالجة السيراميك على حساب المقاول واستلام الساكن",
            user=setup["engineer"]
        )

        assert resolved_ticket.status == WarrantyTicket.TicketStatus.RESOLVED_BY_CONTRACTOR
        assert resolved_ticket.actual_repair_cost == Decimal("0.00")
        assert resolved_ticket.retention_journal_entry is None  # لا يوجد قيد خصم

    def test_contractor_defaults_and_debits_retention_with_zero_pnl_impact(self, warranty_setup):
        """التحقق من تقاعس المقاول وتنفيذ الإصلاح المباشر وخصم التكلفة آلياً من تأمين المقاول دون لمس قائمة الدخل"""
        setup = warranty_setup
        contractor = setup["contractor"]
        project = setup["project"]
        engineer = setup["engineer"]
        cash_acc = setup["cash_account"]

        ticket = WarrantyDefectService.create_warranty_ticket(
            unit=setup["unit"],
            contract=setup["contract"],
            customer=setup["customer"],
            category=WarrantyTicket.TicketCategory.FINISHING_PLUMBING,
            title="كسر في ماسورة صرف رئيسية بالحمام",
            description="كسر ماسورة الصرف أدى إلى تلفيات وتأخر المقاول عن الحضور رغم الإنذار",
            created_by=setup["user"]
        )

        WarrantyDefectService.inspect_and_assign_contractor(
            ticket=ticket,
            responsible_contractor=contractor,
            inspected_by=engineer,
            sla_days=3
        )

        # رصيد التأمين المتاح للمقاول قبل الخصم = 100,000 ج.م
        balance_before = WarrantyDefectService.get_contractor_retention_balance(
            contractor=contractor,
            project=project
        )
        assert balance_before == Decimal("100000.00")

        # تنفيذ الإصلاح المباشر وسداد 35,000 ج.م من الخزينة وخصمها من تأمين المقاول
        repair_cost = Decimal("35000.00")
        closed_ticket = WarrantyDefectService.execute_contractor_default_and_debit_retention(
            ticket=ticket,
            repair_cost=repair_cost,
            settlement_account=cash_acc,
            user=engineer,
            closure_notes="تم الاستعانة بورشة صيانة خارجية وسداد 35,000 ج.م نقداً وخصمها من تأمين المقاول"
        )

        # 1. التحقق من تحول حالة التذكرة
        assert closed_ticket.status == WarrantyTicket.TicketStatus.CLOSED_DEBITED
        assert closed_ticket.actual_repair_cost == repair_cost
        assert closed_ticket.retention_journal_entry is not None

        # 2. التحقق من القيد المحاسبي المتوازن بالكامل بالقرش
        entry = closed_ticket.retention_journal_entry
        assert entry.is_balanced is True

        lines = list(entry.lines.all())
        assert len(lines) == 2

        dr_line = [l for l in lines if l.debit > 0][0]
        cr_line = [l for l in lines if l.credit > 0][0]

        # طرف مدين: تخفيض التزامات تأمينات المقاول المحتجزة 21310
        assert dr_line.account.code == "21310"
        assert dr_line.account.account_type.category == "liability"
        assert dr_line.debit == repair_cost

        # طرف دائن: صرف النقدية من الخزينة 11110
        assert cr_line.account.code == "11110"
        assert cr_line.account.account_type.category == "asset"
        assert cr_line.credit == repair_cost

        # 3. التحقق القاطع: عزل تام لقائمة دخل المطور (Zero P&L Impact)
        for line in lines:
            assert line.account.account_type.category not in ["revenue", "expense"]

        # 4. التحقق من انخفاض رصيد تأمين أعمال المقاول في المشروع إلى 65,000 ج.م
        balance_after = WarrantyDefectService.get_contractor_retention_balance(
            contractor=contractor,
            project=project
        )
        assert balance_after == Decimal("65000.00")

    def test_contractor_default_fails_when_repair_cost_exceeds_available_retention(self, warranty_setup):
        """التحقق من رفض الخصم وإطلاق استثناء إذا كانت تكلفة الإصلاح تتجاوز رصيد تأمين المقاول المتاح"""
        setup = warranty_setup
        contractor = setup["contractor"]
        cash_acc = setup["cash_account"]

        ticket = WarrantyDefectService.create_warranty_ticket(
            unit=setup["unit"],
            contract=setup["contract"],
            customer=setup["customer"],
            category=WarrantyTicket.TicketCategory.STRUCTURAL_DECENNIAL,
            warranty_type=WarrantyTicket.WarrantyType.STRUCTURAL_TEN_YEARS,
            title="شرخ عميق بالكمرة الرئيسية",
            description="شرخ يتطلب أعمال قمصان خرسانية بتكلفة باهظة",
            created_by=setup["user"]
        )

        WarrantyDefectService.inspect_and_assign_contractor(
            ticket=ticket,
            responsible_contractor=contractor,
            inspected_by=setup["engineer"]
        )

        # التكلفة المطلوبة 150,000 ج.م بينما المتاح بتأمين المقاول 100,000 ج.م فقط
        exorbitant_cost = Decimal("150000.00")

        with pytest.raises(ValidationError) as exc_info:
            WarrantyDefectService.execute_contractor_default_and_debit_retention(
                ticket=ticket,
                repair_cost=exorbitant_cost,
                settlement_account=cash_acc,
                user=setup["engineer"]
            )
        assert "رصيد تأمين أعمال المقاول" in str(exc_info.value)
        assert "غير كافٍ" in str(exc_info.value)
