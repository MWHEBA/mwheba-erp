# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import UnifiedLog
from customer.models import Customer
from financial.models import Currency
from sale.models.installments import InstallmentPlan, InstallmentItem
from real_estate.models.project import RealEstateProject
from real_estate.models.topology import PropertyBlock, PropertyFloor
from real_estate.models.unit import PropertyUnit
from real_estate.models.contract import PropertyContract, ContractCoOwner
from real_estate.models.legal import LegalNotice
from real_estate.services.legal_escalation_service import LegalEscalationPipeline

User = get_user_model()


@pytest.fixture
def escalation_setup(db):
    user, _ = User.objects.get_or_create(username="legal_officer", defaults={"is_staff": True})
    currency, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "جنيه مصري", "symbol": "ج.م"})

    primary_customer, _ = Customer.objects.get_or_create(
        code="CUST-LEGAL-01",
        defaults={
            "name": "محمود سمير الألفي",
            "phone_primary": "01011112222",
            "national_id": "29001011234567",
            "address": "القطامية - التجمع الخامس",
            "default_currency": currency
        }
    )

    co_owner_customer, _ = Customer.objects.get_or_create(
        code="CUST-LEGAL-02",
        defaults={
            "name": "حسام سمير الألفي",
            "phone_primary": "01122223333",
            "national_id": "29303031234567",
            "address": "القطامية - التجمع الخامس",
            "default_currency": currency
        }
    )

    project, _ = RealEstateProject.objects.get_or_create(
        code="PRJ-LEGAL",
        defaults={
            "name": "كمبوند الأفق السكني",
            "start_date": date(2025, 1, 1),
            "expected_completion_date": date(2027, 12, 31),
            "created_by": user
        }
    )
    block, _ = PropertyBlock.objects.get_or_create(project=project, code="BLK-L", defaults={"name": "عمارة ل"})
    floor, _ = PropertyFloor.objects.get_or_create(block=block, floor_number=3, defaults={"name": "الدور الثالث"})

    unit, _ = PropertyUnit.objects.get_or_create(
        project=project,
        unit_code="L-F03-U01",
        defaults={
            "floor": floor,
            "gross_area": Decimal("180.00"),
            "net_area": Decimal("150.00"),
            "meter_price": Decimal("25000.00"),
            "total_price": Decimal("4500000.00"),
            "status": PropertyUnit.UnitStatus.AVAILABLE
        }
    )

    # إنشاء خطة تقسيط مستقلة
    plan = InstallmentPlan.objects.create(
        sale=None,
        total_principal=Decimal("4000000.00"),
        total_amount=Decimal("4000000.00"),
        number_of_installments=4,
        start_date=date(2026, 1, 1),
        customer=primary_customer,
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=user
    )

    contract = PropertyContract.objects.create(
        contract_number="CTR-LEGAL-2026-001",
        project=project,
        unit=unit,
        customer=primary_customer,
        installment_plan=plan,
        contract_date=date(2026, 1, 1),
        delivery_date=date(2027, 12, 31),
        final_contract_price=Decimal("4500000.00"),
        down_payment=Decimal("500000.00"),
        currency=currency,
        created_by=user,
        status=PropertyContract.ContractStatus.ACTIVE
    )

    # إضافة شريك متضامن
    ContractCoOwner.objects.create(
        contract=contract,
        co_owner=co_owner_customer,
        share_percentage=Decimal("50.00"),
        is_joint_and_several_guarantor=True
    )

    # توليد 4 أقساط
    # قسط 1: مستحق في 2026-01-15 (متعثر T+75 يوم نسبة لـ 2026-04-01 -> مرحلة 4 فسخ)
    i1 = InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        due_date=date(2026, 1, 15),
        principal_amount=Decimal("1000000.00"),
        total_amount=Decimal("1000000.00"),
        paid_amount=Decimal("0.00"),
        cash_status=InstallmentItem.CashStatus.OVERDUE
    )
    # قسط 2: مستحق في 2026-03-01 (متعثر T+31 يوم نسبة لـ 2026-04-01 -> مرحلة 3 إنذار رسمي)
    i2 = InstallmentItem.objects.create(
        plan=plan,
        installment_number=2,
        due_date=date(2026, 3, 1),
        principal_amount=Decimal("1000000.00"),
        total_amount=Decimal("1000000.00"),
        paid_amount=Decimal("0.00"),
        cash_status=InstallmentItem.CashStatus.OVERDUE
    )
    # قسط 3: مستحق في 2026-03-22 (متعثر T+10 أيام نسبة لـ 2026-04-01 -> مرحلة 2 تأخير ودي)
    i3 = InstallmentItem.objects.create(
        plan=plan,
        installment_number=3,
        due_date=date(2026, 3, 22),
        principal_amount=Decimal("1000000.00"),
        total_amount=Decimal("1000000.00"),
        paid_amount=Decimal("0.00"),
        cash_status=InstallmentItem.CashStatus.OVERDUE
    )
    # قسط 4: مستحق في 2026-04-06 (متبقي 5 أيام T-5 نسبة لـ 2026-04-01 -> مرحلة 1 تذكير استباقي)
    i4 = InstallmentItem.objects.create(
        plan=plan,
        installment_number=4,
        due_date=date(2026, 4, 6),
        principal_amount=Decimal("1000000.00"),
        total_amount=Decimal("1000000.00"),
        paid_amount=Decimal("0.00"),
        cash_status=InstallmentItem.CashStatus.PENDING
    )

    return {
        "user": user,
        "contract": contract,
        "primary_customer": primary_customer,
        "co_owner_customer": co_owner_customer,
        "plan": plan,
        "installments": [i1, i2, i3, i4],
        "as_of_date": date(2026, 4, 1)
    }


class TestLegalEscalationWorkflow:
    """
    اختبارات دورة التصعيد القانوني الكاملة والإنذارات الرسمية المعتمدة
    """

    def test_stage_1_pre_due_reminder(self, escalation_setup):
        """اختبار المرحلة 1 (استباقية T-5): إرسال تذكير re_installment_reminder عبر WhatsApp"""
        data = escalation_setup
        inst = data["installments"][3]  # due 2026-04-06, as of 2026-04-01 -> T-5

        stage, overdue_days = LegalEscalationPipeline.determine_escalation_stage(inst, as_of_date=data["as_of_date"])
        assert stage == LegalNotice.EscalationStage.STAGE_1_PRE_DUE
        assert overdue_days == 0

        with patch("core.services.whatsapp_service.WhatsAppService.send_template_message") as mock_send:
            mock_send.return_value = {"success": True, "message_id": "wamid.TEST_PRE_DUE_01"}

            notice = LegalEscalationPipeline.execute_escalation_for_installment(
                installment=inst,
                as_of_date=data["as_of_date"],
                user=data["user"]
            )

            assert notice.stage == LegalNotice.EscalationStage.STAGE_1_PRE_DUE
            assert notice.status == LegalNotice.NoticeStatus.SENT
            assert notice.meta_message_id == "wamid.TEST_PRE_DUE_01"
            assert notice.penalty_amount == Decimal("0.00")
            assert notice.template_name == "re_installment_reminder"
            assert mock_send.called

    def test_stage_2_grace_expired_with_penalty(self, escalation_setup):
        """اختبار المرحلة 2 (تأخير ودي T+10): احتساب غرامة التأخير اليومية والتحذير"""
        data = escalation_setup
        inst = data["installments"][2]  # due 2026-03-22, as of 2026-04-01 -> 10 days overdue

        stage, overdue_days = LegalEscalationPipeline.determine_escalation_stage(inst, as_of_date=data["as_of_date"])
        assert stage == LegalNotice.EscalationStage.STAGE_2_GRACE_EXPIRED
        assert overdue_days == 10

        # غرامة 0.1% يومياً على 1,000,000 لمدة 10 أيام = 1,000,000 * 0.001 * 10 = 10,000.00
        expected_penalty = Decimal("10000.00")
        calc_penalty = LegalEscalationPipeline.calculate_contractual_penalty(inst, overdue_days)
        assert calc_penalty == expected_penalty

        with patch("core.services.whatsapp_service.WhatsAppService.send_template_message") as mock_send:
            mock_send.return_value = {"success": True, "message_id": "wamid.TEST_STAGE2_02"}

            notice = LegalEscalationPipeline.execute_escalation_for_installment(
                installment=inst,
                as_of_date=data["as_of_date"],
                user=data["user"]
            )

            assert notice.stage == LegalNotice.EscalationStage.STAGE_2_GRACE_EXPIRED
            assert notice.overdue_days == 10
            assert notice.penalty_amount == expected_penalty
            assert notice.total_demanded_amount == Decimal("1010000.00")

            inst.refresh_from_db()
            assert inst.penalty_amount == expected_penalty
            assert inst.reminder_count >= 1

    def test_stage_3_formal_legal_demand_and_co_owner_joint_liability(self, escalation_setup):
        """اختبار المرحلة 3 (T+30): إنذار رسمي بالسداد على يد محضر مع تكافل الشركاء وبصمة SHA-256"""
        data = escalation_setup
        inst = data["installments"][1]  # due 2026-03-01, as of 2026-04-01 -> 31 days overdue

        stage, overdue_days = LegalEscalationPipeline.determine_escalation_stage(inst, as_of_date=data["as_of_date"])
        assert stage == LegalNotice.EscalationStage.STAGE_3_FORMAL_DEMAND
        assert overdue_days == 31

        with patch("core.services.whatsapp_service.WhatsAppService.send_template_message") as mock_send:
            mock_send.return_value = {"success": True, "message_id": "wamid.TEST_STAGE3_DEMAND"}

            notice = LegalEscalationPipeline.execute_escalation_for_installment(
                installment=inst,
                as_of_date=data["as_of_date"],
                user=data["user"]
            )

            assert notice.stage == LegalNotice.EscalationStage.STAGE_3_FORMAL_DEMAND
            assert notice.template_name == "re_legal_notice_demand"
            assert notice.cure_deadline_days == 15
            assert notice.cure_deadline_date == date(2026, 4, 16)
            assert bool(notice.verification_token) is True
            assert len(notice.verification_token) == 64  # SHA-256

            # التحقق من نص الإنذار القانوني الرسمي واشتماله على الشريك والكفيل الغارم وقانون التجارة 17 لسنة 1999
            letter = notice.legal_letter_text
            assert "إنذار رسمي بالسداد على يد محضر" in letter
            assert data["primary_customer"].name in letter
            assert data["co_owner_customer"].name in letter
            assert "كفيلاً غارماً متضامناً متكافلاً" in letter
            assert "قانون التجارة رقم 17 لسنة 1999" in letter
            assert "الشرط الفاسخ الصريح" in letter
            assert notice.verification_token in letter

            # التحقق من سياق التصدير المعتمد
            ctx = LegalEscalationPipeline.get_certified_demand_letter_context(notice)
            assert ctx["contract_number"] == data["contract"].contract_number
            assert len(ctx["co_owners"]) == 1
            assert ctx["co_owners"][0]["is_guarantor"] is True

    def test_stage_4_rescission_and_repossession(self, escalation_setup):
        """اختبار المرحلة 4 (T+60): محضر إنهاء وتصفية التعاقد وإسقاط الحيازة وإحالة القسط للملاحقة القضائية"""
        data = escalation_setup
        inst = data["installments"][0]  # due 2026-01-15, as of 2026-04-01 -> 76 days overdue

        stage, overdue_days = LegalEscalationPipeline.determine_escalation_stage(inst, as_of_date=data["as_of_date"])
        assert stage == LegalNotice.EscalationStage.STAGE_4_RESCISSION_NOTICE
        assert overdue_days == 76

        with patch("core.services.whatsapp_service.WhatsAppService.send_template_message") as mock_send:
            mock_send.return_value = {"success": True, "message_id": "wamid.TEST_STAGE4_RESCIND"}

            notice = LegalEscalationPipeline.execute_escalation_for_installment(
                installment=inst,
                as_of_date=data["as_of_date"],
                user=data["user"]
            )

            assert notice.stage == LegalNotice.EscalationStage.STAGE_4_RESCISSION_NOTICE
            assert "محضر رسمي لإنهاء وتصفية التعاقد" in notice.legal_letter_text
            assert "إسقاط حيازة الطرف الثاني" in notice.legal_letter_text

            inst.refresh_from_db()
            assert inst.cash_status == InstallmentItem.CashStatus.LEGAL_ACTION
            assert inst.legal_referral_date == data["as_of_date"]
            assert inst.court_case_number == notice.notice_number

    def test_fallback_to_sms_on_meta_error_131026(self, escalation_setup):
        """اختبار آلية التراجع التلقائي لـ SMS عند تعذر تسليم WhatsApp لخطأ ميتا 131026 والتوثيق في UnifiedLog"""
        data = escalation_setup
        inst = data["installments"][1]  # Stage 3

        initial_log_count = UnifiedLog.objects.filter(category="integration").count()

        # محاكاة خطأ ميتا رقم 131026: الرقم غير مسجل على واتساب
        notice = LegalEscalationPipeline.execute_escalation_for_installment(
            installment=inst,
            as_of_date=data["as_of_date"],
            user=data["user"],
            simulate_meta_error=131026
        )

        assert notice.channel == LegalNotice.NoticeChannel.SMS
        assert notice.fallback_channel_used == "SMS"
        assert notice.fallback_error_code == 131026
        assert notice.status == LegalNotice.NoticeStatus.FALLBACK_TRIGGERED

        # التحقق من صدور قيد توثيقي في UnifiedLog
        after_log_count = UnifiedLog.objects.filter(category="integration").count()
        assert after_log_count == initial_log_count + 1

        last_log = UnifiedLog.objects.filter(category="integration").latest("timestamp")
        assert "تفعيل قناة التراجع التلقائي لـ SMS" in last_log.message
        assert "131026" in last_log.message
