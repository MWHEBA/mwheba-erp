# -*- coding: utf-8 -*-
"""
Contractor Progress Service (Track 1 & Wave 2 - Phase 6)
إدارة مستخلصات مقاولي الباطن والتشييد:
- حساب الاستقطاعات المتسلسلة (14 خطوة) مع منع الازدواج الضريبي لضريبة الخصم والإضافة (نموذج 41)
- الربط المحكم مع دورة الاعتماد المؤسسية EnterpriseApprovalRequest وقواعد الاعتماد المتدرجة
- القفل التشفيري ضد تعديل البيانات المالية بعد الاعتماد (Cryptographic Financial Merkle Hash Lock)
- الحارس المالي والرقابي الصارم (Hard Payment Guard) للحجز القضائي والتنازل البنكي وصمام خطابات الضمان
- التمييز بين الأوعية الضريبية المصرية (ضريبة الجدول 5% كود T2 مقابل ضريبة القيمة المضافة 14% كود T1)
- دورة الإلغاء العكسي المعياري (Storno Reversal Workflow) وإعادة ضبط أرصدة العقد
- الإفراج المرحلي عن التأمين (50% استلام ابتدائي و50% استلام نهائي بعد سنة الصيانة)
- جدولة سداد المستخلصات على دفعات وشيكات بنكية آجلة (PDC Cheques via cheques app)
"""
from decimal import Decimal
import logging
from typing import Optional, Dict, Any, List
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from real_estate.models import (
    ContractorProgressCertificate,
    ContractorContract,
    CertificatePaymentInstallmentSchedule,
    ContractorSupplierLienAssignment,
)
from financial.models import ChartOfAccounts, JournalEntry
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from financial.services.approval_service import ApprovalService
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData
from real_estate.services.contractor_contract_service import ContractorContractService

logger = logging.getLogger(__name__)


class MissingApprovalRuleError(ValidationError):
    """خطأ عدم وجود قاعدة اعتماد مالي مطابقة للمستخلص"""
    pass


class MutationTamperError(ValidationError):
    """خطأ اكتشاف تعديل مالي غير مصرح به على مستخلص معتمد أو قيد الاعتماد"""
    pass


class SequentialOrderError(ValidationError):
    """خطأ عدم الالتزام بالترتيب التسلسلي للمستخلصات لنفس العقد"""
    pass


class FinalSettlementComplianceError(ValidationError):
    """خطأ عدم استيفاء الشروط الإلزامية للمستخلص الختامي ومخالصة الضمان"""
    pass


class ContractorProgressService:
    """
    محرك خدمة مستخلصات مقاولي الباطن والاعتمادات المؤسسية
    """

    @classmethod
    def get_or_resolve_account(cls, role_name: str, fallback_code: str) -> ChartOfAccounts:
        """جلب الحساب المحاسبي عبر سجل الأدوار الموحد مع استخدام الحساب الاحتياطي"""
        try:
            account = AccountRoleRegistry.get_account(role_name)
        except Exception:
            account = None
        if not account:
            account = ChartOfAccounts.objects.filter(code=fallback_code).first()
        if not account or not account.is_active:
            if account and not account.can_post_entries() and account.children.filter(is_active=True, is_leaf=True).exists():
                return account.children.filter(is_active=True, is_leaf=True).first()
            raise ValidationError(
                _("الحساب المحاسبي للدور '%(role)s' (كود %(code)s) غير مهيأ أو غير نشط في دليل الحسابات.") % {
                    'role': role_name,
                    'code': fallback_code
                }
            )
        return account

    @classmethod
    @transaction.atomic
    def submit_certificate_for_approval(cls, certificate: ContractorProgressCertificate, user) -> ContractorProgressCertificate:
        """
        تقديم المستخلص لدورة الاعتماد المالي المؤسسية
        يتحقق من الحسابات والتسلسل الزمني ويثبت البصمة الرقمية المشفرة (Merkle Tree Snapshot)
        """
        cert = ContractorProgressCertificate.objects.select_for_update().get(id=certificate.id)

        # 1. التحقق من الترتيب التسلسلي الصارم ومنع فتح مستخلصين في آن واحد لذات العقد
        if cert.contract_id:
            prior_open_certs = ContractorProgressCertificate.objects.filter(
                contract=cert.contract,
                sequence_order__lt=cert.sequence_order,
                status__in=[
                    ContractorProgressCertificate.CertificateStatus.DRAFT,
                    ContractorProgressCertificate.CertificateStatus.PENDING_APPROVAL
                ]
            ).exclude(id=cert.id)

            if prior_open_certs.exists():
                raise SequentialOrderError(
                    _("لا يمكن تقديم المستخلص رقم %(num)s للاعتماد في وجود مستخلصات سابقة قيد الإعداد أو المراجعة لذات العقد.") % {
                        'num': cert.certificate_number
                    }
                )

        # 2. فحص متطلبات المستخلص الختامي ومخالصة الضمان (Final Settlement Guard)
        if cert.certificate_type == ContractorProgressCertificate.CertificateType.FINAL_SETTLEMENT:
            contract = cert.contract
            decennial_pol = cert.decennial_liability_insurance_policy or (contract.decennial_liability_insurance_policy if contract else '')
            occupancy_num = cert.certificate_of_occupancy_number or (contract.certificate_of_occupancy_number if contract else '')
            syndicate_clear = cert.syndicate_supervision_clearance or (contract.syndicate_supervision_clearance if contract else False)

            if not decennial_pol or not occupancy_num or not syndicate_clear:
                raise FinalSettlementComplianceError(
                    _("لا يمكن اعتماد المستخلص الختامي قبل إرفاق: وثيقة تأمين المجمعة العشرية، شهادة صلاحية المبنى للإشغال، وشهادة الإشراف الهندسي المعتمدة من نقابة المهندسين.")
                )

        # 3. عزل وحجر البنود المتنازع عليها (Disputed Line Items Quarantine)
        if cert.contract_id:
            disputed_items = cert.items.filter(is_disputed_holdback=True)
            cert.disputed_items_holdback_total = sum(
                (item.total_cumulative_amount - (item.contract_item.total_budget_amount if False else Decimal("0.00")))
                for item in disputed_items
            ) if disputed_items.exists() else Decimal("0.00")

        # 4. إعادة حساب المبالغ بدقة
        cert.compute_amounts()

        # 5. توليد وتثبيت البصمة الرقمية المشفرة لحماية البيانات من التعديل (Cryptographic Financial Snapshot)
        cert.approval_snapshot_hash = cert.compute_financial_hash()

        # 6. استدعاء خدمة الاعتماد المؤسسية
        currency_code = getattr(cert.currency, 'code', 'EGP')
        approval_req = ApprovalService.check_and_create_approval_request(
            module='REAL_ESTATE',
            reference_id=f"CERT-{cert.id}",
            amount=cert.net_amount,
            currency=currency_code,
            user=user
        )

        if approval_req is None:
            raise MissingApprovalRuleError(
                _("لا توجد قاعدة اعتماد مالي مطابقة لمستخلص المقاول بمبلغ %(amount)s %(currency)s. يرجى مراجعة إعدادات الاعتمادات.") % {
                    'amount': cert.net_amount,
                    'currency': currency_code
                }
            )

        cert.approval_request = approval_req
        cert.status = ContractorProgressCertificate.CertificateStatus.PENDING_APPROVAL
        cert.save()

        logger.info(f"Contractor certificate {cert.certificate_number} submitted for approval. Request ID: {approval_req.id}")
        return cert

    @classmethod
    def verify_and_post_certificate(cls, certificate: ContractorProgressCertificate, user) -> JournalEntry:
        """
        التحقق من اكتمال الاعتماد والقفل التشفيري، ثم إصدار قيد استحقاق المستخلص عبر AccountingGateway:
        دعم منظومة الاستقطاعات الـ 14 كاملة مع تمييز ضرائب الجدول (5%) والقيمة المضافة (14%) والحجز القضائي والتنازل البنكي
        """
        cert = ContractorProgressCertificate.objects.get(id=certificate.id)

        # 1. الحارس المالي الصارم (Hard Payment Guard): التحقق من اكتمال الاعتماد المؤسسي
        if not cert.approval_request or cert.approval_request.status != 'APPROVED':
            curr_status = cert.approval_request.status if cert.approval_request else 'NO_REQUEST'
            raise ValidationError(
                _("لا يمكن إصدار القيد المالي أو الصرف: المستخلص لم يستوفِ دورة الاعتمادات المالية المطلوبة (الحالة الحالية: %(status)s).") % {
                    'status': curr_status
                }
            )

        # 2. القفل التشفيري للبيانات المالية (Cryptographic Mutation Lock)
        current_hash = cert.compute_financial_hash()
        if cert.approval_snapshot_hash and current_hash != cert.approval_snapshot_hash:
            # إلغاء الاعتماد فوراً وحفظ المسودة بسبب التلاعب بالبيانات المالية
            with transaction.atomic():
                cert.approval_request.status = 'CANCELLED'
                cert.approval_request.save(update_fields=['status'])

                cert.status = ContractorProgressCertificate.CertificateStatus.DRAFT
                cert.approval_snapshot_hash = ""
                cert.save(update_fields=['status', 'approval_snapshot_hash', 'updated_at'])

            logger.critical(
                f"SECURITY ALERT: Financial mutation detected on approved certificate {cert.certificate_number}. Approval revoked."
            )
            raise MutationTamperError(
                _("تم اكتشاف تعديل في الأرقام المالية للمستخلص بعد الاعتماد. تم إلغاء الاعتماد تلقائياً وإعادة المستخلص للمسودة.")
            )

        # 3. التحقق الرقابي من أهلية الصرف للعقد (Pay or Extend / Bank LG / Garnishment)
        if cert.contract_id:
            eligibility = ContractorContractService.check_contract_payout_eligibility(cert.contract, cert.period_end)
            if eligibility["pay_or_extend_triggered"]:
                raise ValidationError(
                    _("تم تجميد صرف المستخلص لتفعيل صمام المطالبة بتمديد أو تسييل خطاب الضمان البنكي (Pay or Extend).")
                )

        # 4. إعداد القيد المحاسبي المزدوج عبر AccountingGateway
        currency_str = getattr(cert.currency, 'code', 'EGP')
        proj_code = cert.project.code if cert.project else None

        # مسار التوافق الرجعي 100% للمستخلصات السابقة (بدون عقد جديد)
        if not cert.contract_id:
            return cls._post_legacy_certificate(cert, user, currency_str, proj_code)

        # مسار العقود والتشييد الموسع للمسار الأول (Track 1)
        return cls._post_track1_contract_certificate(cert, user, currency_str, proj_code)

    @classmethod
    def _post_legacy_certificate(
        cls,
        cert: ContractorProgressCertificate,
        user,
        currency_str: str,
        proj_code: Optional[str]
    ) -> JournalEntry:
        """إصدار قيد المستخلص القديم بدقة تامة للحفاظ على التوافقية الرجعية الكاملة"""
        wip_account = cls.get_or_resolve_account(AccountRoleNames.REAL_ESTATE_WIP_CONSTRUCTION.value, fallback_code="12101")
        retention_account = cls.get_or_resolve_account(AccountRoleNames.REAL_ESTATE_CONTRACTOR_RETENTIONS_PAYABLE.value, fallback_code="21310")
        payable_account = getattr(cert.contractor, 'financial_account', None)
        if not payable_account or not payable_account.can_post_entries():
            payable_account = getattr(cert.contractor, 'financial_account', None)
        if not payable_account or not payable_account.can_post_entries():
            payable_account = cls.get_or_resolve_account(AccountRoleNames.SUPPLIER_PAYABLE_CONTROL.value, fallback_code="21110")
            if not payable_account.can_post_entries() and payable_account.children.filter(is_active=True, is_leaf=True).exists():
                payable_account = payable_account.children.filter(is_active=True, is_leaf=True).first()
            if not payable_account.can_post_entries() and payable_account.children.filter(is_active=True, is_leaf=True).exists():
                payable_account = payable_account.children.filter(is_active=True, is_leaf=True).first()
        wht_account = cls.get_or_resolve_account(AccountRoleNames.WITHHOLDING_TAX_PAYABLE.value, fallback_code="21330")
        advance_account = cls.get_or_resolve_account(AccountRoleNames.REAL_ESTATE_CONTRACTOR_ADVANCE.value, fallback_code="11350")

        gross_addition = cert.current_period_work + cert.materials_on_site

        lines = [
            JournalEntryLineData(
                account_code=wip_account.code,
                debit=gross_addition,
                credit=Decimal("0.00"),
                currency=currency_str,
                description=f"إثبات تكلفة أعمال مقاولة مستخلص {cert.certificate_number} - {cert.contractor.name}",
                project=proj_code
            )
        ]

        if cert.retention_amount > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=retention_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.retention_amount,
                    currency=currency_str,
                    description=f"استقطاع تأمين حسن تنفيذ ({cert.retention_rate}%) مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.advance_payment_recovery > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=advance_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.advance_payment_recovery,
                    currency=currency_str,
                    description=f"استرداد دفعة مقدمة مقاول مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.wht_amount > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=wht_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.wht_amount,
                    currency=currency_str,
                    description=f"ضريبة خصم وإضافة ({cert.wht_rate}%) مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        # صافي المستحق للمقاول
        lines.append(
            JournalEntryLineData(
                account_code=payable_account.code,
                debit=Decimal("0.00"),
                credit=cert.net_amount,
                currency=currency_str,
                description=f"صافي استحقاق المقاول {cert.contractor.name} - مستخلص {cert.certificate_number}",
                project=proj_code
            )
        )

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='ContractorProgressCertificate',
            object_id=cert.id,
            operation='accrual'
        )

        gateway = AccountingGateway()
        journal_entry = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='ContractorProgressCertificate',
            source_id=cert.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='general_ledger',
            description=f"استحقاق مستخلص مقاول الباطن {cert.certificate_number} - {cert.contractor.name}",
            reference=f"CERT-{cert.certificate_number}",
            date=timezone.localdate()
        )

        cert.journal_entry = journal_entry
        cert.status = ContractorProgressCertificate.CertificateStatus.APPROVED
        cert.save(update_fields=['journal_entry', 'status', 'updated_at'])

        logger.info(f"Contractor certificate {cert.certificate_number} posted to GL. Entry ID: {journal_entry.id}")
        return journal_entry

    @classmethod
    @transaction.atomic
    def _post_track1_contract_certificate(
        cls,
        cert: ContractorProgressCertificate,
        user,
        currency_str: str,
        proj_code: Optional[str]
    ) -> JournalEntry:
        """
        إصدار القيد المحاسبي المتكامل للمسار الأول مع تفصيل الاستقطاعات الـ 14 والضرائب المتوافقة
        """
        contract = cert.contract

        # الحسابات المدينة
        wip_account = cls.get_or_resolve_account(AccountRoleNames.REAL_ESTATE_WIP_CONSTRUCTION.value, fallback_code="12101")
        vat_input_account = cls.get_or_resolve_account(AccountRoleNames.VAT_INPUT.value, fallback_code="11410")

        # الحسابات الدائنة
        retention_account = cls.get_or_resolve_account(AccountRoleNames.REAL_ESTATE_CONTRACTOR_RETENTIONS_PAYABLE.value, fallback_code="21310")
        cube_hold_account = cls.get_or_resolve_account("cube_test_hold", fallback_code="21315")
        syndicate_account = cls.get_or_resolve_account("syndicate_stamp", fallback_code="21345")
        car_ins_account = cls.get_or_resolve_account("car_insurance", fallback_code="21360")
        advance_account = cls.get_or_resolve_account(AccountRoleNames.REAL_ESTATE_CONTRACTOR_ADVANCE.value, fallback_code="11350")
        wht_account = cls.get_or_resolve_account(AccountRoleNames.WITHHOLDING_TAX_PAYABLE.value, fallback_code="21330")
        social_ins_account = cls.get_or_resolve_account("social_insurance_payable", fallback_code="21340")
        utilities_account = cls.get_or_resolve_account("site_utilities_recovery", fallback_code="42301")
        debris_account = cls.get_or_resolve_account("debris_clearance_recovery", fallback_code="42304")
        hoisting_account = cls.get_or_resolve_account("equipment_hoisting_recovery", fallback_code="42302")
        labor_advance_account = cls.get_or_resolve_account("labor_advance", fallback_code="11355")
        hse_medical_account = cls.get_or_resolve_account("hse_medical_recovery", fallback_code="42303")
        store_account = cls.get_or_resolve_account("store_inventory", fallback_code="11201")
        penalties_account = cls.get_or_resolve_account("delay_penalties_income", fallback_code="42101")

        # حساب المقاول أو الحساب البنكي المتنازل له أو حساب الحجز القضائي
        if contract.is_garnished_by_court:
            payable_account = cls.get_or_resolve_account("judicial_garnishment_escrow", fallback_code="21350")
            payout_desc = f"تجنيب مستحقات المقاول بحساب الأمانات القضائية (قضية {contract.garnishment_case_number}) - مستخلص {cert.certificate_number}"
        else:
            payable_account = getattr(cert.contractor, 'financial_account', None)
            if not payable_account or not payable_account.can_post_entries():
                payable_account = cls.get_or_resolve_account(AccountRoleNames.SUPPLIER_PAYABLE_CONTROL.value, fallback_code="21110")
                if not payable_account.can_post_entries() and payable_account.children.filter(is_active=True, is_leaf=True).exists():
                    payable_account = payable_account.children.filter(is_active=True, is_leaf=True).first()
            if contract.is_assigned_to_bank:
                payout_desc = f"صافي مستحق لصالح {contract.assigned_bank_name} (IBAN: {contract.assigned_bank_iban}) - مستخلص {cert.certificate_number}"
            else:
                payout_desc = f"صافي استحقاق المقاول {cert.contractor.name} - مستخلص {cert.certificate_number}"

        lines: List[JournalEntryLineData] = []

        # 1. إثبات تكلفة الأعمال والتشوينات وفروق الأسعار والتعويضات المعتمدة (مدين)
        gross_wip_period = (
            cert.current_period_work +
            cert.net_materials_on_site +
            cert.price_escalation_amount +
            cert.approved_suspension_standby_claims
        )
        if gross_wip_period > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=wip_account.code,
                    debit=gross_wip_period,
                    credit=Decimal("0.00"),
                    currency=currency_str,
                    description=f"إثبات تكلفة أعمال وتشوينات وفروق أسعار مستخلص {cert.certificate_number} - {cert.contractor.name}",
                    project=proj_code
                )
            )

        # 2. إثبات ضريبة الجدول (5%) أو ضريبة القيمة المضافة (14%) المصرية (مدين)
        if contract.tax_regime == ContractorContract.TaxRegime.TABLE_TAX_5:
            cert.vat_schedule_rate = Decimal("5.00")
            cert.vat_schedule_amount = (cert.current_period_work * Decimal("0.05")).quantize(Decimal("0.01"))
            if cert.vat_schedule_amount > Decimal("0.00"):
                lines.append(
                    JournalEntryLineData(
                        account_code=vat_input_account.code,
                        debit=cert.vat_schedule_amount,
                        credit=Decimal("0.00"),
                        currency=currency_str,
                        description=f"ضريبة جدول مقاولات 5% (كود T2) - مستخلص {cert.certificate_number}",
                        project=proj_code
                    )
                )
        elif contract.tax_regime == ContractorContract.TaxRegime.STANDARD_VAT_14:
            cert.vat_schedule_rate = Decimal("14.00")
            cert.vat_schedule_amount = (cert.current_period_work * Decimal("0.14")).quantize(Decimal("0.01"))
            if cert.vat_schedule_amount > Decimal("0.00"):
                lines.append(
                    JournalEntryLineData(
                        account_code=vat_input_account.code,
                        debit=cert.vat_schedule_amount,
                        credit=Decimal("0.00"),
                        currency=currency_str,
                        description=f"ضريبة قيمة مضافة مدخلات 14% (كود T1) - مستخلص {cert.certificate_number}",
                        project=proj_code
                    )
                )

        # 3. إثبات الاستقطاعات الدائنة
        if cert.retention_amount > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=retention_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.retention_amount,
                    currency=currency_str,
                    description=f"استقطاع تأمين حسن تنفيذ ({cert.retention_rate}%) - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.pending_cube_test_hold_amount > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=cube_hold_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.pending_cube_test_hold_amount,
                    currency=currency_str,
                    description=f"أمانة نتائج كسر مكعبات خرسانة 28 يوم معلقة - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.syndicate_stamp_amount > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=syndicate_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.syndicate_stamp_amount,
                    currency=currency_str,
                    description=f"استقطاع دمغة نقابة المهندسين والتطبيقيين ({cert.syndicate_stamp_rate}%) - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.car_insurance_amount > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=car_ins_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.car_insurance_amount,
                    currency=currency_str,
                    description=f"استقطاع قسط وثيقة تأمين أخطار المقاولين CAR - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.advance_payment_recovery > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=advance_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.advance_payment_recovery,
                    currency=currency_str,
                    description=f"استرداد دفعة مقدمة مقاول ({cert.advance_payment_recovery}) - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.wht_amount > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=wht_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.wht_amount,
                    currency=currency_str,
                    description=f"ضريبة الخصم والإضافة ({cert.wht_rate}%) على الوعاء {cert.taxable_base_form41} - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.social_insurance_amount > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=social_ins_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.social_insurance_amount,
                    currency=currency_str,
                    description=f"تأمينات اجتماعية مقاولات استمارة 19 ({cert.social_insurance_rate}%) - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.site_utilities_deduction_amount > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=utilities_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.site_utilities_deduction_amount,
                    currency=currency_str,
                    description=f"استقطاع استهلاك مياه وإنارة الموقع ({cert.site_utilities_deduction_rate}%) - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.debris_clearance_charges > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=debris_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.debris_clearance_charges,
                    currency=currency_str,
                    description=f"استقطاع تكاليف رفع الرتش ومخلفات التكسير - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.equipment_hoisting_charges > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=hoisting_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.equipment_hoisting_charges,
                    currency=currency_str,
                    description=f"استقطاع ساعات تشغيل أوناش الأبراج - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        emergency_labor_total = cert.direct_labor_advances_deduction + cert.interim_on_account_payments
        if emergency_labor_total > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=labor_advance_account.code,
                    debit=Decimal("0.00"),
                    credit=emergency_labor_total,
                    currency=currency_str,
                    description=f"استرداد سلف العمالة والدفعات تحت الحساب بالفترة - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.hse_medical_and_incident_costs > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=hse_medical_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.hse_medical_and_incident_costs,
                    currency=currency_str,
                    description=f"استرداد نفقات علاج وإسعاف حوادث السلامة - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.store_materials_deduction > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=store_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.store_materials_deduction,
                    currency=currency_str,
                    description=f"استقطاع مسحوبات الخامات من مخزن المشروع - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        total_operational_penalties = (
            cert.delay_penalties +
            cert.concrete_quality_penalties +
            cert.excess_material_waste_penalties +
            cert.punch_list_penalties +
            cert.penalty_deductions
        )
        if total_operational_penalties > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=penalties_account.code,
                    debit=Decimal("0.00"),
                    credit=total_operational_penalties,
                    currency=currency_str,
                    description=f"إيرادات غرامات تأخير وجودة وهالك زائد - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        # 4. خط صافي استحقاق المقاول القابل للصرف
        # ضمان دقة التوازن المزدوج (Penny Balancing)
        total_debits = sum(line.debit for line in lines)
        total_credits = sum(line.credit for line in lines)
        net_payable_balanced = (total_debits - total_credits).quantize(Decimal("0.01"))

        lines.append(
            JournalEntryLineData(
                account_code=payable_account.code,
                debit=Decimal("0.00"),
                credit=net_payable_balanced,
                currency=currency_str,
                description=payout_desc,
                project=proj_code
            )
        )

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='ContractorProgressCertificate',
            object_id=cert.id,
            operation='track1_accrual'
        )

        gateway = AccountingGateway()
        journal_entry = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='ContractorProgressCertificate',
            source_id=cert.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='general_ledger',
            description=f"استحقاق مستخلص مقاول الباطن {cert.certificate_number} - {cert.contractor.name}",
            reference=f"CERT-{cert.certificate_number}",
            date=timezone.localdate()
        )

        # تحديث أرقام العقد التراكمية
        contract.total_certified_work += cert.current_period_work
        contract.advance_payment_recovered += cert.advance_payment_recovery
        contract.total_retention_retained += cert.retention_amount
        contract.save(update_fields=[
            "total_certified_work",
            "advance_payment_recovered",
            "total_retention_retained",
            "updated_at"
        ])

        cert.journal_entry = journal_entry
        cert.status = ContractorProgressCertificate.CertificateStatus.APPROVED
        cert.save()

        logger.info(f"Contractor certificate {cert.certificate_number} posted to GL via Track 1. Entry ID: {journal_entry.id}")
        return journal_entry

    @classmethod
    @transaction.atomic
    def reverse_certificate(
        cls,
        certificate: ContractorProgressCertificate,
        reason: str,
        user=None
    ) -> JournalEntry:
        """
        دورة الإلغاء العكسي المعياري (Storno Reversal Workflow):
        توليد قيد عكسي مطابق يعكس الحسابات المدينة والدائنة مع رد المبالغ المطفأة للعقد
        """
        cert = ContractorProgressCertificate.objects.select_for_update().get(id=certificate.id)

        if not cert.journal_entry:
            raise ValidationError(_("لا يمكن إلغاء المستخلص: لا يوجد قيد يومية مسجل للمستخلص."))

        if cert.status == ContractorProgressCertificate.CertificateStatus.CANCELLED:
            raise ValidationError(_("المستخلص ملغي بالفعل."))

        orig_entry = cert.journal_entry
        currency_str = getattr(cert.currency, 'code', 'EGP')
        proj_code = cert.project.code if cert.project else None

        # إنشاء الأسطر العكسية المتطابقة تماماً (Storno)
        storno_lines: List[JournalEntryLineData] = []
        for line in orig_entry.lines.all():
            storno_lines.append(
                JournalEntryLineData(
                    account_code=line.account.code,
                    debit=line.credit,  # عكس الدائن إلى مدين
                    credit=line.debit,  # عكس المدين إلى دائن
                    currency=currency_str,
                    description=f"قيد عكسي لإلغاء مستخلص {cert.certificate_number} ({reason})",
                    project=proj_code
                )
            )

        gateway = AccountingGateway()
        idemp_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='ContractorProgressCertificate',
            object_id=cert.id,
            operation='storno_reversal'
        )

        storno_entry = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='ContractorProgressCertificate',
            source_id=cert.id,
            lines=storno_lines,
            idempotency_key=idemp_key,
            user=user,
            entry_type='storno',
            description=f"قيد عكسي لإلغاء استحقاق مستخلص {cert.certificate_number} - {cert.contractor.name} ({reason})",
            reference=f"REV-CERT-{cert.certificate_number}",
            date=timezone.localdate()
        )

        # رد أرقام العقد التراكمية
        if cert.contract_id:
            contract = cert.contract
            contract.total_certified_work = max(Decimal("0.00"), contract.total_certified_work - cert.current_period_work)
            contract.advance_payment_recovered = max(Decimal("0.00"), contract.advance_payment_recovered - cert.advance_payment_recovery)
            contract.total_retention_retained = max(Decimal("0.00"), contract.total_retention_retained - cert.retention_amount)
            contract.save(update_fields=[
                "total_certified_work",
                "advance_payment_recovered",
                "total_retention_retained",
                "updated_at"
            ])

        cert.reversal_entry = storno_entry
        cert.status = ContractorProgressCertificate.CertificateStatus.CANCELLED
        cert.save(update_fields=["reversal_entry", "status", "updated_at"])

        logger.info(f"Certificate {cert.certificate_number} reversed. Storno Entry ID: {storno_entry.id}")
        return storno_entry

    @classmethod
    @transaction.atomic
    def release_retention(
        cls,
        contract: ContractorContract,
        release_type: str,
        amount: Decimal,
        defect_deductions: Decimal = Decimal("0.00"),
        user=None
    ) -> JournalEntry:
        """
        الإفراج عن تأمين حسن التنفيذ (50% استلام ابتدائي و50% استلام نهائي بعد سنة الصيانة)
        Dr: Contractor Retentions Payable (21310)
        Cr: Defect Rectification Recovery (42201 - إن وجدت خصومات عيوب)
        Cr: Contractor / Assigned Bank Payable (21110)
        """
        contract = ContractorContract.objects.select_for_update().get(id=contract.id)

        available_retention = contract.total_retention_retained - contract.total_retention_released
        if amount > available_retention:
            raise ValidationError(
                _("مبلغ التأمين المطلوب الإفراج عنه (%(amount)s) يتجاوز رصيد التأمين المحتجز المتاح (%(avail)s).") % {
                    'amount': amount,
                    'avail': available_retention
                }
            )

        retention_account = cls.get_or_resolve_account(AccountRoleNames.REAL_ESTATE_CONTRACTOR_RETENTIONS_PAYABLE.value, fallback_code="21310")
        defect_account = cls.get_or_resolve_account("defect_rectification_recovery", fallback_code="42201")

        if contract.is_garnished_by_court:
            payable_account = cls.get_or_resolve_account("judicial_garnishment_escrow", fallback_code="21350")
        else:
            payable_account = getattr(contract.contractor, 'financial_account', None)
            if not payable_account or not payable_account.can_post_entries():
                payable_account = getattr(cert.contractor, 'financial_account', None)
        if not payable_account or not payable_account.can_post_entries():
            payable_account = cls.get_or_resolve_account(AccountRoleNames.SUPPLIER_PAYABLE_CONTROL.value, fallback_code="21110")
            if not payable_account.can_post_entries() and payable_account.children.filter(is_active=True, is_leaf=True).exists():
                payable_account = payable_account.children.filter(is_active=True, is_leaf=True).first()
                if not payable_account.can_post_entries() and payable_account.children.filter(is_active=True, is_leaf=True).exists():
                    payable_account = payable_account.children.filter(is_active=True, is_leaf=True).first()

        currency_str = getattr(contract.currency, 'code', 'EGP')
        proj_code = contract.project.code if contract.project else None
        net_released_payout = (amount - defect_deductions).quantize(Decimal("0.01"))

        desc = f"الإفراج عن تأمين حسن التنفيذ ({release_type}) - عقد {contract.contract_number} - {contract.contractor.name}"

        lines = [
            JournalEntryLineData(
                account_code=retention_account.code,
                debit=amount,
                credit=Decimal("0.00"),
                currency=currency_str,
                description=desc,
                project=proj_code
            )
        ]

        if defect_deductions > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=defect_account.code,
                    debit=Decimal("0.00"),
                    credit=defect_deductions,
                    currency=currency_str,
                    description=f"استقطاع تكاليف إصلاح العيوب من التأمين المفرج عنه - عقد {contract.contract_number}",
                    project=proj_code
                )
            )

        lines.append(
            JournalEntryLineData(
                account_code=payable_account.code,
                debit=Decimal("0.00"),
                credit=net_released_payout,
                currency=currency_str,
                description=f"صافي التأمين المفرج عنه للصرف - عقد {contract.contract_number}",
                project=proj_code
            )
        )

        gateway = AccountingGateway()
        idemp_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='ContractorContract',
            object_id=contract.id,
            operation=f'retention_release_{release_type}_{amount}'
        )

        journal_entry = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='ContractorContract',
            source_id=contract.id,
            lines=lines,
            idempotency_key=idemp_key,
            user=user,
            entry_type='general_ledger',
            description=desc,
            reference=f"RET-REL-{contract.contract_number}",
            date=timezone.localdate()
        )

        contract.total_retention_released += amount
        contract.save(update_fields=["total_retention_released", "updated_at"])

        logger.info(f"Retention released for contract {contract.contract_number}: {amount} {currency_str}. Entry ID: {journal_entry.id}")
        return journal_entry

    @classmethod
    @transaction.atomic
    def settle_installment_with_cheque(
        cls,
        installment: CertificatePaymentInstallmentSchedule,
        cheque,
        user=None
    ) -> JournalEntry:
        """
        سداد دفعة مجدولة من المستخلص بشيك بنكي آجل (PDC Cheque)
        Dr: Contractor Payable (21110)
        Cr: Notes Payable - Cheques (21210)
        """
        inst = CertificatePaymentInstallmentSchedule.objects.select_for_update().get(id=installment.id)
        cert = inst.certificate
        contract = cert.contract

        if inst.is_settled:
            raise ValidationError(_("الدفعة مسددة بالفعل."))

        payable_account = getattr(cert.contractor, 'financial_account', None)
        if not payable_account or not payable_account.can_post_entries():
            payable_account = cls.get_or_resolve_account(AccountRoleNames.SUPPLIER_PAYABLE_CONTROL.value, fallback_code="21110")
            if not payable_account.can_post_entries() and payable_account.children.filter(is_active=True, is_leaf=True).exists():
                payable_account = payable_account.children.filter(is_active=True, is_leaf=True).first()
        notes_payable_account = cls.get_or_resolve_account("notes_payable", fallback_code="21210")

        currency_str = getattr(cert.currency, 'code', 'EGP')
        proj_code = cert.project.code if cert.project else None
        cheque_num = getattr(cheque, 'cheque_number', str(cheque.id) if hasattr(cheque, 'id') else '')

        desc = f"سداد الدفعة المجدولة رقم {inst.installment_number} بشيك آجل رقم {cheque_num} - مستخلص {cert.certificate_number}"

        lines = [
            JournalEntryLineData(
                account_code=payable_account.code,
                debit=inst.amount,
                credit=Decimal("0.00"),
                currency=currency_str,
                description=desc,
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=notes_payable_account.code,
                debit=Decimal("0.00"),
                credit=inst.amount,
                currency=currency_str,
                description=desc,
                project=proj_code
            )
        ]

        gateway = AccountingGateway()
        idemp_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='CertificatePaymentInstallmentSchedule',
            object_id=inst.id,
            operation='cheque_payout'
        )

        journal_entry = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='CertificatePaymentInstallmentSchedule',
            source_id=inst.id,
            lines=lines,
            idempotency_key=idemp_key,
            user=user,
            entry_type='general_ledger',
            description=desc,
            reference=f"PDC-INST-{inst.id}",
            date=timezone.localdate()
        )

        if hasattr(cheque, '_meta'):
            inst.pdc_cheque = cheque
            inst.is_settled = True
            inst.save(update_fields=["pdc_cheque", "is_settled"])
        else:
            inst.is_settled = True
            inst.save(update_fields=["is_settled"])

        logger.info(f"Installment {inst.installment_number} settled with PDC cheque {cheque_num}. Entry ID: {journal_entry.id}")
        return journal_entry

    reverse_posted_certificate_storno = reverse_certificate
