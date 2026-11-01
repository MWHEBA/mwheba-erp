# -*- coding: utf-8 -*-
"""
BuildingFacilityService - محرك إدارة صندوق صيانة المرافق واتحاد الشاغلين
MWHEBA ERP — Real Estate Wave 3 (Phase 11: HOA Maintenance Escrow & Tax-Free Yields)
"""
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional, List

from django.db import transaction, models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from financial.models import ChartOfAccounts, JournalEntry
from financial.services.role_registry import AccountRoleNames, AccountRoleRegistry
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData

from real_estate.models.project import RealEstateProject
from real_estate.models.unit import PropertyUnit
from real_estate.models.contract import PropertyContract
from real_estate.models.facility import (
    BuildingFacilitySubledger,
    MaintenanceFundOperation,
    SupplementalLevyApportionment
)

logger = logging.getLogger(__name__)


class BuildingFacilityService:
    """
    محرك تشغيل وإدارة صندوق صيانة المرافق واتحاد الشاغلين:
    - الفصل الصارم لأموال الصيانة في حساب بنكي مقيد (Restricted Cash 11170)
    - إدارة أمانات الملاك في حساب التزامات مقيدة (Escrow Liability 21520)
    - إثبات عوائد الشهادات البنكية المعفاة كقيد ميزانية بحت (Balance Sheet Only) بدون المساس بقائمة الدخل (Zero P&L)
    - توزيع عجز الصيانة السنوي (Supplemental Maintenance Levy) على ملاك الوحدات بالتناسب مع المساحة الإجمالية
    """

    @classmethod
    def get_or_resolve_account(cls, role_name: str, fallback_code: str) -> ChartOfAccounts:
        """
        استرجاع حساب من الدليل المحاسبي بالدور المالي أو بالكود الاحتياطي
        """
        acc = AccountRoleRegistry.get_account(role_name)
        if not acc:
            acc = ChartOfAccounts.objects.filter(code=fallback_code, is_active=True).first()
        if not acc or not acc.is_active:
            raise ValidationError(
                _("الحساب المحاسبي المطلوب للدور '%(role)s' أو الكود '%(code)s' غير معرف أو غير نشط في دليل الحسابات.") % {
                    'role': role_name,
                    'code': fallback_code
                }
            )
        return acc

    @classmethod
    def get_or_create_subledger(
        cls,
        project: RealEstateProject,
        user=None,
        restricted_cash_account: Optional[ChartOfAccounts] = None,
        maintenance_escrow_account: Optional[ChartOfAccounts] = None
    ) -> BuildingFacilitySubledger:
        """
        استرجاع أو إنشاء دفتر أستاذ مساعد صندوق الصيانة للمشروع
        """
        subledger = BuildingFacilitySubledger.objects.filter(project=project).first()
        if not subledger:
            cash_acc = restricted_cash_account or cls.get_or_resolve_account(
                AccountRoleNames.REAL_ESTATE_RESTRICTED_CASH.value,
                fallback_code="11170"
            )
            escrow_acc = maintenance_escrow_account or cls.get_or_resolve_account(
                AccountRoleNames.REAL_ESTATE_MAINTENANCE_ESCROW_LIABILITY.value,
                fallback_code="21520"
            )

            creator = user or project.created_by
            subledger = BuildingFacilitySubledger.objects.create(
                project=project,
                restricted_cash_account=cash_acc,
                maintenance_escrow_account=escrow_acc,
                created_by=creator
            )
            logger.info(f"Initialized BuildingFacilitySubledger for project {project.code}")

        return subledger

    @classmethod
    @transaction.atomic
    def record_deposit_collection(
        cls,
        subledger: BuildingFacilitySubledger,
        contract: PropertyContract,
        amount: Decimal,
        user=None,
        operation_date=None,
        description: str = ""
    ) -> MaintenanceFundOperation:
        """
        إثبات تحصيل وديعة صيانة تعاقدية من المشتري:
        Dr: Restricted Cash (11170)
        Cr: Escrow Trust Liability (21520)
        """
        amount_dec = Decimal(str(amount))
        if amount_dec <= Decimal("0.00"):
            raise ValidationError(_("مبلغ وديعة الصيانة المحصلة يجب أن يكون أكبر من الصفر."))

        op_date = operation_date or timezone.localdate()
        desc = description or f"تحصيل وديعة صيانة الوحدة {contract.unit.unit_code} - عقد {contract.contract_number}"

        op = MaintenanceFundOperation.objects.create(
            subledger=subledger,
            operation_type=MaintenanceFundOperation.OperationType.DEPOSIT_COLLECTION,
            operation_date=op_date,
            amount=amount_dec,
            contract=contract,
            unit=contract.unit,
            description=desc,
            created_by=user or subledger.created_by
        )

        cash_acc = subledger.restricted_cash_account or cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_RESTRICTED_CASH.value, fallback_code="11170"
        )
        escrow_acc = subledger.maintenance_escrow_account or cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_MAINTENANCE_ESCROW_LIABILITY.value, fallback_code="21520"
        )

        proj_code = subledger.project.code
        currency_str = getattr(contract.currency, 'code', 'EGP') if contract.currency else 'EGP'

        lines = [
            JournalEntryLineData(
                account_code=cash_acc.code,
                debit=amount_dec,
                credit=Decimal("0.00"),
                currency=currency_str,
                description=desc,
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=escrow_acc.code,
                debit=Decimal("0.00"),
                credit=amount_dec,
                currency=currency_str,
                description=f"أمانات وديعة صيانة - الوحدة {contract.unit.unit_code}",
                project=proj_code
            )
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='BuildingFacilitySubledger',
            object_id=subledger.id,
            operation=f"deposit_{op.id}"
        )

        gateway = AccountingGateway()
        entry = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='BuildingFacilitySubledger',
            source_id=subledger.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='customer_receipt',
            description=desc,
            reference=op.operation_number,
            date=op_date
        )

        op.journal_entry = entry
        op.save(update_fields=['journal_entry'])

        # تحديث رصيد الصندوق
        subledger.total_collected_deposits += amount_dec
        subledger.recalculate_balances()

        return op

    @classmethod
    @transaction.atomic
    def post_bank_yield(
        cls,
        subledger: BuildingFacilitySubledger,
        yield_amount: Decimal,
        certificate_number: str = "",
        yield_rate: Decimal = Decimal("0.00"),
        period_start=None,
        period_end=None,
        user=None,
        description: str = ""
    ) -> MaintenanceFundOperation:
        """
        إثبات عوائد الشهادات والودائع البنكية لصندوق صيانة اتحاد الشاغلين (Tax-Free Balance Sheet Only):
        - ممنوع قطعياً المساس بقائمة الدخل (P&L) كإيراد فوائد تجنباً لضريبة 22.5%
        Dr: Restricted Cash (11170)
        Cr: Escrow Trust Liability (21520)
        """
        amount_dec = Decimal(str(yield_amount))
        if amount_dec <= Decimal("0.00"):
            raise ValidationError(_("مبلغ العائد البنكي لصندوق الصيانة يجب أن يكون أكبر من الصفر."))

        desc = description or (
            f"إثبات عائد بنكي معفى لشهادات صندوق صيانة مشروع {subledger.project.name} "
            f"(شهادة رقم {certificate_number or 'عام'})"
        )

        op = MaintenanceFundOperation.objects.create(
            subledger=subledger,
            operation_type=MaintenanceFundOperation.OperationType.BANK_YIELD,
            operation_date=timezone.localdate(),
            amount=amount_dec,
            bank_certificate_number=certificate_number,
            yield_rate=yield_rate,
            period_start=period_start,
            period_end=period_end,
            description=desc,
            created_by=user or subledger.created_by
        )

        cash_acc = subledger.restricted_cash_account or cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_RESTRICTED_CASH.value, fallback_code="11170"
        )
        escrow_acc = subledger.maintenance_escrow_account or cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_MAINTENANCE_ESCROW_LIABILITY.value, fallback_code="21520"
        )

        proj_code = subledger.project.code
        currency_str = 'EGP'

        # قيد ميزانية بحت (Balance Sheet Only): زيادة البنك وزيادة أمانات الملاك
        lines = [
            JournalEntryLineData(
                account_code=cash_acc.code,
                debit=amount_dec,
                credit=Decimal("0.00"),
                currency=currency_str,
                description=desc,
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=escrow_acc.code,
                debit=Decimal("0.00"),
                credit=amount_dec,
                currency=currency_str,
                description=f"إضافة العائد البنكي لأمانات صندوق صيانة {subledger.project.code} (معفى ضريبياً)",
                project=proj_code
            )
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='BuildingFacilitySubledger',
            object_id=subledger.id,
            operation=f"yield_{op.id}"
        )

        gateway = AccountingGateway()
        entry = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='BuildingFacilitySubledger',
            source_id=subledger.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='bank_entry',
            description=desc,
            reference=op.operation_number,
            date=timezone.localdate()
        )

        op.journal_entry = entry
        op.save(update_fields=['journal_entry'])

        # تحديث رصيد الصندوق
        subledger.total_yield_accumulated += amount_dec
        subledger.recalculate_balances()

        logger.info(
            f"Posted tax-free bank yield of {amount_dec} EGP for subledger {subledger.project.code}. "
            f"JE: {entry.number}"
        )
        return op

    @classmethod
    @transaction.atomic
    def record_facility_expense(
        cls,
        subledger: BuildingFacilitySubledger,
        expense_amount: Decimal,
        expense_category: str,
        description: str = "",
        user=None,
        operation_date=None
    ) -> MaintenanceFundOperation:
        """
        إثبات صرف مصروف تشغيلي من صندوق الصيانة (صيانة مصاعد، أمن، نظافة):
        Dr: Escrow Trust Liability (21520)
        Cr: Restricted Cash (11170)
        """
        amount_dec = Decimal(str(expense_amount))
        if amount_dec <= Decimal("0.00"):
            raise ValidationError(_("مبلغ المصروف التشغيلي يجب أن يكون أكبر من الصفر."))

        op_date = operation_date or timezone.localdate()
        desc = description or f"صرف مصروف تشغيلي ({expense_category}) لمشروع {subledger.project.name}"

        op = MaintenanceFundOperation.objects.create(
            subledger=subledger,
            operation_type=MaintenanceFundOperation.OperationType.FACILITY_EXPENSE,
            operation_date=op_date,
            amount=amount_dec,
            expense_category=expense_category,
            description=desc,
            created_by=user or subledger.created_by
        )

        cash_acc = subledger.restricted_cash_account or cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_RESTRICTED_CASH.value, fallback_code="11170"
        )
        escrow_acc = subledger.maintenance_escrow_account or cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_MAINTENANCE_ESCROW_LIABILITY.value, fallback_code="21520"
        )

        proj_code = subledger.project.code
        currency_str = 'EGP'

        # سحب من البنك المقيد وتخفيض رصيد التزامات الأمانة
        lines = [
            JournalEntryLineData(
                account_code=escrow_acc.code,
                debit=amount_dec,
                credit=Decimal("0.00"),
                currency=currency_str,
                description=f"تخفيض أمانات الصيانة لمقابلة مصروف {desc}",
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=cash_acc.code,
                debit=Decimal("0.00"),
                credit=amount_dec,
                currency=currency_str,
                description=desc,
                project=proj_code
            )
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='BuildingFacilitySubledger',
            object_id=subledger.id,
            operation=f"expense_{op.id}"
        )

        gateway = AccountingGateway()
        entry = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='BuildingFacilitySubledger',
            source_id=subledger.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='vendor_payment',
            description=desc,
            reference=op.operation_number,
            date=op_date
        )

        op.journal_entry = entry
        op.save(update_fields=['journal_entry'])

        # تحديث رصيد الصندوق
        subledger.total_expenses_disbursed += amount_dec
        subledger.recalculate_balances()

        logger.info(
            f"Disbursed facility expense of {amount_dec} EGP for {subledger.project.code}. JE: {entry.number}"
        )
        return op

    @classmethod
    @transaction.atomic
    def calculate_and_apportion_annual_levy(
        cls,
        subledger: BuildingFacilitySubledger,
        period_start,
        period_end,
        user=None
    ) -> Dict[str, Any]:
        """
        احتساب وتوزيع عجز الصيانة السنوي (Supplemental Maintenance Levy) على الملاك:
        Deficit = Total Period Expenses - Total Period Yields
        إذا كان هناك عجز: يوزع على ملاك الوحدات بالتناسب مع المساحة الإجمالية (Gross Area %)
        Dr: Maintenance Levy Receivable (11240)
        Cr: Escrow Trust Liability (21520)
        """
        # احتساب إجمالي المصروفات والعوائد في الفترة
        expenses_agg = subledger.operations.filter(
            operation_type=MaintenanceFundOperation.OperationType.FACILITY_EXPENSE,
            operation_date__gte=period_start,
            operation_date__lte=period_end
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal("0.00")

        yields_agg = subledger.operations.filter(
            operation_type=MaintenanceFundOperation.OperationType.BANK_YIELD,
            operation_date__gte=period_start,
            operation_date__lte=period_end
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal("0.00")

        deficit = expenses_agg - yields_agg
        if deficit <= Decimal("0.00"):
            return {
                'has_deficit': False,
                'period_expenses': expenses_agg,
                'period_yields': yields_agg,
                'deficit_amount': Decimal("0.00"),
                'message': _("لا يوجد عجز مالي في صندوق الصيانة للفترة المحددة. عوائد الصندوق تغطي المصروفات.")
            }

        # جلب الوحدات المؤهلة لتوزيع العجز (المسلمة أو المتعاقد عليها)
        eligible_units = PropertyUnit.objects.filter(
            project=subledger.project,
            status__in=[
                PropertyUnit.UnitStatus.DELIVERED,
                PropertyUnit.UnitStatus.DELIVERED_DEEMED,
                PropertyUnit.UnitStatus.CONTRACTED
            ]
        ).select_related('project')

        if not eligible_units.exists():
            raise ValidationError(
                _("لا توجد وحدات مستلمة أو مباعة بمشروع %(project)s لتحميل عجز الصيانة عليها.") % {
                    'project': subledger.project.code
                }
            )

        total_gross_area = sum(u.gross_area for u in eligible_units)
        if total_gross_area <= Decimal("0.00"):
            raise ValidationError(_("إجمالي مساحات الوحدات المؤهلة يجب أن يكون أكبر من الصفر."))

        # إنشاء حركة العجز السنوي
        desc = (
            f"مطالبة فروق صيانة سنوية استثنائية (عجز) لمشروع {subledger.project.name} "
            f"عن الفترة من {period_start} إلى {period_end}"
        )
        levy_op = MaintenanceFundOperation.objects.create(
            subledger=subledger,
            operation_type=MaintenanceFundOperation.OperationType.SUPPLEMENTAL_LEVY,
            operation_date=timezone.localdate(),
            amount=deficit,
            period_start=period_start,
            period_end=period_end,
            description=desc,
            created_by=user or subledger.created_by
        )

        apportionments = []
        running_apportioned_total = Decimal("0.00")

        sorted_units = sorted(list(eligible_units), key=lambda u: u.gross_area)

        for idx, unit in enumerate(sorted_units):
            contract = PropertyContract.objects.filter(
                unit=unit,
                status__in=[PropertyContract.ContractStatus.ACTIVE, PropertyContract.ContractStatus.COMPLETED]
            ).first()

            customer = contract.customer if contract else None
            if not customer:
                # إذا لم يكن هناك عقد، يتم التعيين للعميل الافتراضي للمشروع أو تخطيه
                continue

            share_pct = (unit.gross_area / total_gross_area) * Decimal("100.0000")
            share_pct = share_pct.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

            # للوحدة الأخيرة، نأخذ المتبقي لتجنب فروق التقريب (Penny Difference Guarantee)
            if idx == len(sorted_units) - 1:
                unit_amount = deficit - running_apportioned_total
            else:
                raw_amt = (unit.gross_area / total_gross_area) * deficit
                unit_amount = raw_amt.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                running_apportioned_total += unit_amount

            apportionment = SupplementalLevyApportionment.objects.create(
                operation=levy_op,
                unit=unit,
                contract=contract,
                customer=customer,
                unit_gross_area=unit.gross_area,
                share_percentage=share_pct,
                apportioned_amount=unit_amount
            )
            apportionments.append(apportionment)

        # قيد إثبات استحقاق فروق الصيانة على الملاك
        levy_rec_acc = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_MAINTENANCE_LEVY_RECEIVABLE.value,
            fallback_code="11240"
        )
        escrow_acc = subledger.maintenance_escrow_account or cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_MAINTENANCE_ESCROW_LIABILITY.value,
            fallback_code="21520"
        )

        proj_code = subledger.project.code
        currency_str = 'EGP'

        lines = [
            JournalEntryLineData(
                account_code=levy_rec_acc.code,
                debit=deficit,
                credit=Decimal("0.00"),
                currency=currency_str,
                description=desc,
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=escrow_acc.code,
                debit=Decimal("0.00"),
                credit=deficit,
                currency=currency_str,
                description=f"إثبات تغطية عجز الصيانة لصالح أمانات صندوق {proj_code}",
                project=proj_code
            )
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='BuildingFacilitySubledger',
            object_id=subledger.id,
            operation=f"levy_{levy_op.id}"
        )

        gateway = AccountingGateway()
        entry = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='BuildingFacilitySubledger',
            source_id=subledger.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='sales_invoice',
            description=desc,
            reference=levy_op.operation_number,
            date=timezone.localdate()
        )

        levy_op.journal_entry = entry
        levy_op.save(update_fields=['journal_entry'])

        logger.info(
            f"Successfully apportioned deficit of {deficit} EGP across {len(apportionments)} units. "
            f"JE: {entry.number}"
        )

        return {
            'has_deficit': True,
            'period_expenses': expenses_agg,
            'period_yields': yields_agg,
            'deficit_amount': deficit,
            'units_count': len(apportionments),
            'operation_number': levy_op.operation_number,
            'journal_entry_number': entry.number,
            'apportionments': apportionments
        }
