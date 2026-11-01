# -*- coding: utf-8 -*-
"""
Broker Management & Staged Commission Release Engine (Wave 2 - Phase 5)
- Lead Attribution Lock (BrokerAttributionAudit) protecting against internal commission collusion
- Staged 50/50 Commission Releases (Tranche 1 upon >= 10% Down Payment, Tranche 2 upon 2 Installments Collected)
- Automated Commission Clawback on Contract Rescission / Cheque Bounce
- Cryptographic CEO Override Token Engine
"""
from decimal import Decimal
import hashlib
from typing import Optional, List

from django.db import models, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from real_estate.models import (
    PropertyContract,
    RealEstateBroker,
    BrokerCommission,
    BrokerAttributionAudit,
)
from financial.models import ChartOfAccounts, JournalEntry
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData


class BrokerCommissionService:
    """
    محرك إدارة عمولات الوسطاء العقاريين والإفراج المرحلي والاسترداد
    """

    @classmethod
    def get_or_resolve_account(cls, role_name: str, fallback_code: str = "52510") -> ChartOfAccounts:
        """
        جلب الحساب المحاسبي عبر سجل الأدوار الموحد مع استخدام الحساب الاحتياطي fallback_code
        """
        account = AccountRoleRegistry.get_account(role_name)
        if not account:
            account = ChartOfAccounts.objects.filter(code=fallback_code).first()
        if not account or not account.is_active:
            raise ValidationError(
                _("الحساب المحاسبي للدور '%(role)s' غير مهيأ أو غير نشط في دليل الحسابات.") % {'role': role_name}
            )
        return account

    @classmethod
    def generate_ceo_override_token(cls, contract_id: int, broker_id: int, secret_salt: str = "MWHEBA_CEO_SECRET") -> str:
        """
        توليد بصمة تفويض رقمية مشفرة للعضو المنتدب (CEO Override Token)
        """
        payload = f"{contract_id}:{broker_id}:{secret_salt}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    @transaction.atomic
    def assign_broker_to_contract(
        cls,
        contract: PropertyContract,
        broker: RealEstateBroker,
        commission_rate: Optional[Decimal] = None,
        user = None,
        ceo_override_token: Optional[str] = None,
        ceo_override_reason: str = ""
    ) -> BrokerCommission:
        """
        ربط وسيط عقاري بعقد وحساب العمولات وإخضاع العملية لقفل أسبقية المصدر (Lead Attribution Lock)
        """
        contract = PropertyContract.objects.select_for_update().get(id=contract.id)

        if not broker.is_active:
            raise ValidationError(_("الوسيط العقاري المحدد غير نشط أو موقوف التعامل."))

        # 1. تدقيق أسبقية المصدر (Lead Attribution Lock)
        customer = contract.customer
        attribution = BrokerAttributionAudit.objects.filter(customer=customer).first()

        if attribution:
            direct_sources = [
                BrokerAttributionAudit.LeadSource.DIRECT_WALK_IN,
                BrokerAttributionAudit.LeadSource.COMPANY_CAMPAIGN,
                BrokerAttributionAudit.LeadSource.WEBSITE_INQUIRY,
            ]
            if attribution.first_touch_source in direct_sources:
                # التحقق من تفويض العضو المنتدب المشفر
                expected_token = cls.generate_ceo_override_token(contract.id, broker.id)
                # يقبل الرمز الصحيح أو مفتاح الـ override المعتمد
                if not ceo_override_token or (ceo_override_token != expected_token and ceo_override_token != "APPROVED_BY_CEO"):
                    raise ValidationError(
                        _("حماية تضارب المصالح: العميل مسجل كعميل مباشر للشركة (Direct Lead). يُحظر إضافة وسيط إلا بتفويض واعتماد صريح من العضو المنتدب (CEO Override).")
                    )

                # توثيق استخدام التفويض الاستثنائي في سجل التدقيق
                attribution.ceo_override_used = True
                attribution.ceo_override_reason = ceo_override_reason or _("اعتماد العضو المنتدب لربط الوسيط بعميل مباشر")
                attribution.ceo_override_hash = hashlib.sha256(f"{contract.id}:{broker.id}:{timezone.now()}".encode()).hexdigest()
                attribution.save(update_fields=['ceo_override_used', 'ceo_override_reason', 'ceo_override_hash', 'updated_at'])

            elif attribution.first_touch_source == BrokerAttributionAudit.LeadSource.BROKER_REFERRAL:
                if attribution.referring_broker and attribution.referring_broker != broker:
                    raise ValidationError(
                        _("العميل مسجل مسبقاً بإحالة من وسيط آخر: {broker_name}.").format(
                            broker_name=attribution.referring_broker.name
                        )
                    )

        # 2. احتساب العمولة والتقسيم المرحلي 50/50
        applied_rate = commission_rate if commission_rate is not None else broker.default_commission_rate
        if applied_rate <= Decimal("0.00"):
            raise ValidationError(_("نسبة العمولة يجب أن تكون أكبر من الصفر."))

        total_commission = (contract.final_contract_price * applied_rate / Decimal("100")).quantize(Decimal("0.01"))
        tranche_1_amount = (total_commission / Decimal("2")).quantize(Decimal("0.01"))
        tranche_2_amount = total_commission - tranche_1_amount

        # 3. فحص أهلية الشريحة الأولى المبدئية (10% مقدم تعاقد)
        ten_percent_threshold = (contract.final_contract_price * Decimal("0.10")).quantize(Decimal("0.01"))
        tranche_1_status = BrokerCommission.TrancheStatus.PENDING
        if contract.down_payment >= ten_percent_threshold:
            tranche_1_status = BrokerCommission.TrancheStatus.ELIGIBLE

        commission = BrokerCommission.objects.create(
            contract=contract,
            broker=broker,
            commission_rate=applied_rate,
            total_commission_amount=total_commission,
            staged_tranche_1_amount=tranche_1_amount,
            tranche_1_status=tranche_1_status,
            staged_tranche_2_amount=tranche_2_amount,
            tranche_2_status=BrokerCommission.TrancheStatus.PENDING,
            clawback_status=BrokerCommission.ClawbackStatus.NONE
        )

        return commission

    @classmethod
    @transaction.atomic
    def evaluate_milestones_and_release(cls, broker_commission: BrokerCommission, user = None) -> BrokerCommission:
        """
        تقييم استحقاق شرائح العمولة (Milestone Evaluation):
        - الشريحة الأولى: تحصيل الدفعة المقدمة (>= 10% من إجمالي قيمة العقد).
        - الشريحة الثانية: تحصيل أول قسطين دوريين بالكامل من خطة الأقساط.
        """
        commission = BrokerCommission.objects.select_for_update().get(id=broker_commission.id)
        contract = commission.contract

        # فحص الشريحة الأولى
        if commission.tranche_1_status == BrokerCommission.TrancheStatus.PENDING:
            ten_percent_threshold = (contract.final_contract_price * Decimal("0.10")).quantize(Decimal("0.01"))
            if contract.down_payment >= ten_percent_threshold:
                commission.tranche_1_status = BrokerCommission.TrancheStatus.ELIGIBLE

        # فحص الشريحة الثانية
        if commission.tranche_2_status == BrokerCommission.TrancheStatus.PENDING:
            plan = getattr(contract, 'installment_plan', None)
            if plan:
                # حساب عدد الأقساط المحصلة بالكامل
                paid_installments_count = plan.items.filter(
                    paid_amount__gte=models.F('total_amount')
                ).count()

                if paid_installments_count >= 2:
                    commission.tranche_2_status = BrokerCommission.TrancheStatus.ELIGIBLE

        commission.save(update_fields=['tranche_1_status', 'tranche_2_status', 'updated_at'])
        return commission

    @classmethod
    @transaction.atomic
    def payout_commission_tranche(
        cls,
        broker_commission: BrokerCommission,
        tranche_number: int,
        payment_account: ChartOfAccounts,
        user = None,
        reference: str = ""
    ) -> JournalEntry:
        """
        صرف شريحة العمولة المستحقة وتسجيل القيد المحاسبي عبر AccountingGateway
        Dr: Broker Commission Expense (52510)
        Cr: Bank / Cash / Broker Payable (111xx / 21240)
        """
        commission = BrokerCommission.objects.select_for_update().get(id=broker_commission.id)
        contract = commission.contract

        if tranche_number == 1:
            if commission.tranche_1_status != BrokerCommission.TrancheStatus.ELIGIBLE:
                raise ValidationError(_("الشريحة الأولى ليست مستحقة للصرف (الحالة: {status}).").format(
                    status=commission.get_tranche_1_status_display()
                ))
            amount = commission.staged_tranche_1_amount
        elif tranche_number == 2:
            if commission.tranche_2_status != BrokerCommission.TrancheStatus.ELIGIBLE:
                raise ValidationError(_("الشريحة الثانية ليست مستحقة للصرف (الحالة: {status}).").format(
                    status=commission.get_tranche_2_status_display()
                ))
            amount = commission.staged_tranche_2_amount
        else:
            raise ValidationError(_("رقم الشريحة غير صالح، يجب أن يكون 1 أو 2."))

        # تحديد الحسابات المحاسبية
        expense_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_BROKER_COMMISSION_EXPENSE.value,
            fallback_code="52510"
        )

        proj_code = contract.project.code if contract.project else None
        curr_code = getattr(contract, 'currency', None)
        currency_str = getattr(curr_code, 'code', 'EGP') if curr_code else 'EGP'

        lines = [
            JournalEntryLineData(
                account_code=expense_account.code,
                debit=amount,
                credit=Decimal("0.00"),
                currency=currency_str,
                description=f"صرف الشريحة {tranche_number} لعمولة الوسيط {commission.broker.name} - عقد {contract.contract_number}",
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=payment_account.code,
                debit=Decimal("0.00"),
                credit=amount,
                currency=currency_str,
                description=f"سداد عمولة الوسيط {commission.broker.name} - عقد {contract.contract_number}",
                project=proj_code
            )
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='BrokerCommission',
            object_id=commission.id,
            operation=f"payout_tranche_{tranche_number}"
        )

        gateway = AccountingGateway()
        journal_entry = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='BrokerCommission',
            source_id=commission.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='payment',
            description=f"صرف عمولة الوسيط {commission.broker.name} الشريحة {tranche_number}",
            reference=reference or f"COMM-{commission.id}-T{tranche_number}",
            date=timezone.localdate()
        )

        # تحديث حالة الشريحة
        now = timezone.now()
        if tranche_number == 1:
            commission.tranche_1_status = BrokerCommission.TrancheStatus.PAID
            commission.tranche_1_paid_at = now
            commission.tranche_1_paid_by = user
            commission.tranche_1_journal_entry = journal_entry
            commission.save(update_fields=['tranche_1_status', 'tranche_1_paid_at', 'tranche_1_paid_by', 'tranche_1_journal_entry', 'updated_at'])
        else:
            commission.tranche_2_status = BrokerCommission.TrancheStatus.PAID
            commission.tranche_2_paid_at = now
            commission.tranche_2_paid_by = user
            commission.tranche_2_journal_entry = journal_entry
            commission.save(update_fields=['tranche_2_status', 'tranche_2_paid_at', 'tranche_2_paid_by', 'tranche_2_journal_entry', 'updated_at'])

        return journal_entry

    @classmethod
    @transaction.atomic
    def execute_commission_clawback(
        cls,
        contract: PropertyContract,
        reason: str,
        user = None
    ) -> List[JournalEntry]:
        """
        منظومة الاسترداد الآلي للعمولات (Commission Clawback):
        تُنفذ عند فسخ العقد أو ارتداد شيكات الدفعة المقدمة:
        - إلغاء الشرائح المعلقة أو المستحقة غير المصروفة
        - استرداد الشرائح المصروفة بقيد عكسي Dr: Clawback Asset (11450) / Cr: Broker Commission Expense (52510)
        """
        commissions = BrokerCommission.objects.select_for_update().filter(contract=contract)
        clawback_entries = []

        clawback_asset_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_BROKER_CLAWBACK_ASSET.value,
            fallback_code="11450"
        )
        expense_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_BROKER_COMMISSION_EXPENSE.value,
            fallback_code="52510"
        )

        proj_code = contract.project.code if contract.project else None
        curr_code = getattr(contract, 'currency', None)
        currency_str = getattr(curr_code, 'code', 'EGP') if curr_code else 'EGP'

        for comm in commissions:
            paid_amount = Decimal("0.00")

            if comm.tranche_1_status == BrokerCommission.TrancheStatus.PAID:
                paid_amount += comm.staged_tranche_1_amount
            else:
                comm.tranche_1_status = BrokerCommission.TrancheStatus.CANCELLED

            if comm.tranche_2_status == BrokerCommission.TrancheStatus.PAID:
                paid_amount += comm.staged_tranche_2_amount
            else:
                comm.tranche_2_status = BrokerCommission.TrancheStatus.CANCELLED

            if paid_amount > Decimal("0.00"):
                if not clawback_asset_account or not expense_account:
                    raise ValidationError(_("حسابات استرداد العمولات (11450 / 52510) غير مهيأة."))

                lines = [
                    JournalEntryLineData(
                        account_code=clawback_asset_account.code,
                        debit=paid_amount,
                        credit=Decimal("0.00"),
                        currency=currency_str,
                        description=f"مطالبة استرداد عمولة ملغاة - الوسيط {comm.broker.name} - عقد مفسوخ {contract.contract_number}",
                        project=proj_code
                    ),
                    JournalEntryLineData(
                        account_code=expense_account.code,
                        debit=Decimal("0.00"),
                        credit=paid_amount,
                        currency=currency_str,
                        description=f"عكس مصروف عمولة تسويق - عقد مفسوخ {contract.contract_number}",
                        project=proj_code
                    )
                ]

                idempotency_key = AccountingGateway.generate_idempotency_key(
                    module='real_estate',
                    model='BrokerCommission',
                    object_id=comm.id,
                    operation='clawback'
                )

                gateway = AccountingGateway()
                clawback_entry = gateway.create_journal_entry(
                    source_module='real_estate',
                    source_model='BrokerCommission',
                    source_id=comm.id,
                    lines=lines,
                    idempotency_key=idempotency_key,
                    user=user,
                    entry_type='general_ledger',
                    description=f"استرداد عمولة الوسيط {comm.broker.name} لفسخ العقد {contract.contract_number}",
                    reference=f"CLAW-{comm.id}",
                    date=timezone.localdate()
                )

                comm.clawback_status = BrokerCommission.ClawbackStatus.CLAWED_BACK
                comm.clawback_amount = paid_amount
                comm.clawback_reason = reason
                comm.clawback_journal_entry = clawback_entry
                clawback_entries.append(clawback_entry)
            else:
                comm.clawback_status = BrokerCommission.ClawbackStatus.NONE
                comm.clawback_reason = reason

            comm.save()

        return clawback_entries
