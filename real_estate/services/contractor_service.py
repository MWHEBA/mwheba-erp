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
from typing import Optional, Dict, Any, List, Tuple
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
    def calculate_engineering_scope_ceiling(
        cls,
        cert: ContractorProgressCertificate
    ) -> Tuple[Decimal, Decimal, bool, int]:
        """
        حساب سقف الأعمال المعتمدة هندسياً وميدانياً لنطاق عقد المقاولة والمستخلص بدقة:
        - يراعي العمارة/البلوك المخصص للعقد أو المستخلص (Subcontract Scope Isolation).
        - يمنع تسرب أو احتساب إنجاز عمارات أخرى لا تخص نطاق العقد.
        - يحسب نسبة الإنجاز الموزونة للأعمال المعتمدة استشارياً (PASSED_AND_VERIFIED).
        يرجع: (max_cumulative_ceiling, verified_scope_ratio, has_assigned_trades, max_stage_pct)
        """
        if not cert.contractor_id or not cert.project_id:
            return Decimal('0.00'), Decimal('1.00'), False, 0

        from real_estate.models import UnitSiteProgressRecord
        from real_estate.services.site_progress_service import ProjectProgressCalculationService
        from django.db.models import Max

        # تحديد نطاق العمارة المستهدفة بالعقد أو المستخلص (Subcontract Scope Isolation)
        if cert.contract and cert.contract.block_id:
            if cert.block_id and cert.block_id != cert.contract.block_id:
                raise ValidationError(
                    _("لا يمكن معالجة المستخلص: عمارة المستخلص (%(cert_b)s) تتعارض مع العمارة المحددة بنطاق العقد (%(cnt_b)s).") % {
                        'cert_b': cert.block_id,
                        'cnt_b': cert.contract.block_id
                    }
                )
            target_block_id = cert.contract.block_id
        else:
            target_block_id = cert.block_id

        assigned_trades = UnitSiteProgressRecord.objects.filter(
            contractor_id=cert.contractor_id,
            unit__project_id=cert.project_id,
            is_applicable=True
        )
        if target_block_id:
            assigned_trades = assigned_trades.filter(unit__block_id=target_block_id)

        if not assigned_trades.exists():
            return Decimal('0.00'), Decimal('1.00'), False, 0

        verified_trades = assigned_trades.filter(
            status=UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED,
            completion_percentage__gt=0
        )
        max_stage_pct = int(verified_trades.aggregate(m=Max('completion_percentage'))['m'] or 0)

        total_assigned_weight = Decimal('0.00')
        verified_weighted_progress = Decimal('0.00')
        for trade in assigned_trades:
            w = ProjectProgressCalculationService.STAGE_WEIGHTS.get(trade.trade_stage, Decimal('1.00'))
            total_assigned_weight += w
            if trade.status == UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED and trade.completion_percentage > 0:
                verified_weighted_progress += (Decimal(str(trade.completion_percentage)) / Decimal('100.00')) * w

        if total_assigned_weight > Decimal('0.00'):
            verified_scope_ratio = (verified_weighted_progress / total_assigned_weight)
        else:
            verified_scope_ratio = Decimal('0.00')

        contract_val = (
            cert.contract.revised_contract_value
            if (cert.contract and cert.contract.revised_contract_value > 0)
            else (cert.contract.initial_contract_value if cert.contract else cert.gross_certified_work)
        )
        max_cumulative_ceiling = (contract_val * verified_scope_ratio).quantize(Decimal('0.01'))

        return max_cumulative_ceiling, verified_scope_ratio, True, max_stage_pct

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
            same_seq_certs = ContractorProgressCertificate.objects.filter(
                contract=cert.contract,
                sequence_order=cert.sequence_order
            ).exclude(id=cert.id).exclude(
                status=ContractorProgressCertificate.CertificateStatus.CANCELLED
            )
            if same_seq_certs.exists():
                raise ValidationError(
                    _("لا يمكن تقديم المستخلص رقم %(num)s للاعتماد: يوجد مستخلص آخر بنفس الرقم التسلسلي (%(seq)s) لهذا العقد.") % {
                        'num': cert.certificate_number,
                        'seq': cert.sequence_order
                    }
                )

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
            contract = ContractorContract.objects.select_for_update().get(id=cert.contract_id)
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
            if disputed_items.exists():
                cert.disputed_items_holdback_total = sum(item.current_work_value for item in disputed_items)

        # 4. التحقق الهندسي المسبق وسقف المطالبة ومنع القص الصامت
        max_ceiling, verified_ratio, has_assigned, max_stage_pct = cls.calculate_engineering_scope_ceiling(cert)
        if has_assigned and cert.gross_certified_work > Decimal('0.00') and max_ceiling > Decimal('0.00'):
            if cert.gross_certified_work > max_ceiling:
                # Anti-silent-clipping: Do NOT mutate gross_certified_work!
                cert.unverified_work_holdback = (cert.gross_certified_work - max_ceiling).quantize(Decimal('0.01'))
            else:
                cert.unverified_work_holdback = Decimal('0.00')

        # فحص جودة المقاول والعيوب المانعة للتسليم (Critical Snag Blocker Guard)
        if cert.contractor_id and cert.project_id:
            from real_estate.models import UnitSnagItem
            critical_snags = UnitSnagItem.objects.filter(
                contractor_id=cert.contractor_id,
                unit__project_id=cert.project_id,
                severity=UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER,
                status__in=[UnitSnagItem.SnagStatus.OPEN, UnitSnagItem.SnagStatus.IN_PROGRESS]
            )
            if critical_snags.exists():
                is_waiver_valid = bool(
                    getattr(cert, 'consultant_waiver_approved', False) and
                    str(getattr(cert, 'consultant_waiver_reference', '') or '').strip()
                )

                if not is_waiver_valid:
                    raise ValidationError(
                        _("لا يمكن تقديم المستخلص للاعتماد: توجد عيوب حرجة مانعة للتسليم (%(count)d ملاحظة) مسجلة على المقاول لم يتم إصلاحها أو تسويتها.") % {
                            'count': critical_snags.count()
                        }
                    )

        # 5. تشغيل فحص النزاهة والحسابات للمستخلص (Clean & Amount Calculation)
        cert.clean()
        cert.compute_amounts()

        # 6. توليد وتثبيت البصمة الرقمية المشفرة لحماية البيانات من التعديل (Cryptographic Financial Snapshot)
        cert.approval_snapshot_hash = cert.compute_financial_hash()

        # 7. استدعاء خدمة الاعتماد المؤسسية
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
        cert = ContractorProgressCertificate.objects.select_for_update().get(id=certificate.id)

        # التحقق من عدم الترحيل المزدوج (Idempotent Guard)
        if cert.status == ContractorProgressCertificate.CertificateStatus.APPROVED and cert.journal_entry_id:
            return cert.journal_entry

        # 1. الحارس المالي الصارم (Hard Payment Guard): التحقق من اكتمال الاعتماد المؤسسي
        if not cert.approval_request or cert.approval_request.status != 'APPROVED':
            curr_status = cert.approval_request.status if cert.approval_request else 'NO_REQUEST'
            raise ValidationError(
                _("لا يمكن إصدار القيد المالي أو الصرف: المستخلص لم يستوفِ دورة الاعتمادات المالية المطلوبة (الحالة الحالية: %(status)s).") % {
                    'status': curr_status
                }
            )

        # التحقق الرقابي من تطابق مقاول المستخلص مع مقاول العقد الأصلي
        if cert.contract_id and cert.contractor_id != cert.contract.contractor_id:
            raise ValidationError(
                _("لا يمكن ترحيل المستخلص: مقاول المستخلص (%(cert_c)s) غير مطابق للمقاول المسند إليه العقد (%(cnt_c)s).") % {
                    'cert_c': cert.contractor.name if cert.contractor else cert.contractor_id,
                    'cnt_c': cert.contract.contractor.name if cert.contract.contractor else cert.contract.contractor_id
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

        # 3b. التحقق الرقابي من خلو المقاول من العيوب الحرجة المانعة للصرف لحظة الترحيل المالي (Critical Snag Posting Guard)
        if cert.contractor_id and cert.project_id:
            from real_estate.models import UnitSnagItem
            critical_snags = UnitSnagItem.objects.filter(
                contractor_id=cert.contractor_id,
                unit__project_id=cert.project_id,
                severity=UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER,
                status__in=[UnitSnagItem.SnagStatus.OPEN, UnitSnagItem.SnagStatus.IN_PROGRESS]
            )
            if critical_snags.exists():
                is_waiver_valid = bool(
                    getattr(cert, 'consultant_waiver_approved', False) and
                    str(getattr(cert, 'consultant_waiver_reference', '') or '').strip()
                )
                if not is_waiver_valid:
                    raise ValidationError(
                        _("لا يمكن ترحيل أو صرف المستخلص المالي: توجد عيوب حرجة مانعة للتسليم (%(count)d ملاحظة) مسجلة على المقاول لم يتم إصلاحها أو تسويتها.") % {
                            'count': critical_snags.count()
                        }
                    )

        # 4. التحقق الهندسي الميداني وسقف المطالبة المعتمدة (Site Progress & Claim Ceiling Verification):
        # يراعي نطاق العقد والعمارة بدقة، ويمنع خلط الأعمال بين العمارات، ويحظر تعديل البيانات المالية بعد الاعتماد
        max_ceiling, verified_ratio, has_assigned, max_stage_pct = cls.calculate_engineering_scope_ceiling(cert)
        if has_assigned and cert.gross_certified_work > Decimal('0.00'):
            if verified_ratio <= Decimal('0.00'):
                raise ValidationError(
                    _("لا يمكن ترحيل أو اعتماد المستخلص المالي للمقاول (%(contractor)s): توجد بنود تنفيذ ميدانية مسندة له بنطاق العقد ولكن لم يتم اعتماد أي بند منها استشارياً بنسبة إنجاز موجبة (PASSED_AND_VERIFIED).") % {
                        'contractor': cert.contractor.name if cert.contractor else cert.contractor_id
                    }
                )
            effective_gross = cert.gross_certified_work - cert.unverified_work_holdback
            if effective_gross > max_ceiling:
                raise ValidationError(
                    _("لا يمكن ترحيل المستخلص: إجمالي الأعمال المطالب بها بعد الاستقطاع غير المعتمد (%(gross)s) يتجاوز سقف الأعمال المعتمدة هندسياً لنطاق العقد (%(ceiling)s). يرجى تعديل المستخلص وإعادة اعتماده.") % {
                        'gross': effective_gross,
                        'ceiling': max_ceiling
                    }
                )

        # 5. إعداد القيد المحاسبي المزدوج عبر AccountingGateway
        currency_str = getattr(cert.currency, 'code', 'EGP')
        proj_code = cert.project.code if cert.project else None

        # مسار التوافق الرجعي 100% للمستخلصات السابقة (بدون عقد جديد)
        if not cert.contract_id:
            entry = cls._post_legacy_certificate(cert, user, currency_str, proj_code)
        else:
            # مسار العقود والتشييد الموسع للمسار الأول (Track 1)
            entry = cls._post_track1_contract_certificate(cert, user, currency_str, proj_code)

        # قفل البنود المستلمة كمفوترة (is_billed) لنطاق العقد والعمارة المحددة فقط
        if cert.contractor_id and cert.project_id:
            from real_estate.models import UnitSiteProgressRecord
            target_block_id = cert.block_id or (cert.contract.block_id if cert.contract else None)
            billed_qs = UnitSiteProgressRecord.objects.filter(
                contractor_id=cert.contractor_id,
                unit__project_id=cert.project_id,
                is_applicable=True,
                status=UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED
            )
            if target_block_id:
                billed_qs = billed_qs.filter(unit__block_id=target_block_id)
            billed_qs.update(is_billed=True)

        return entry

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
        cert.refresh_from_db()
        contract = ContractorContract.objects.select_for_update().get(id=cert.contract_id)

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

        if cert.released_cube_test_hold_amount > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=cube_hold_account.code,
                    debit=cert.released_cube_test_hold_amount,
                    credit=Decimal("0.00"),
                    currency=currency_str,
                    description=f"رد أمانة كسر مكعبات خرسانة 28 يوم ناجحة - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.released_retention_amount > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=retention_account.code,
                    debit=cert.released_retention_amount,
                    credit=Decimal("0.00"),
                    currency=currency_str,
                    description=f"رد تأمين حسن تنفيذ بموجب المستخلص - مستخلص {cert.certificate_number}",
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
            cert.hse_safety_penalties +
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

        if cert.disputed_items_holdback_total > Decimal("0.00"):
            disputed_hold_account = cls.get_or_resolve_account("disputed_items_hold", fallback_code="21315")
            lines.append(
                JournalEntryLineData(
                    account_code=disputed_hold_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.disputed_items_holdback_total,
                    currency=currency_str,
                    description=f"أمانة مبالغ بنود متنازع عليها فنياً ومحجوزة مؤقتاً - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.unverified_work_holdback > Decimal("0.00"):
            unverified_hold_account = cls.get_or_resolve_account("unverified_work_hold", fallback_code="21318")
            lines.append(
                JournalEntryLineData(
                    account_code=unverified_hold_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.unverified_work_holdback,
                    currency=currency_str,
                    description=f"استقطاع أعمال غير معتمدة استشارياً لحين اكتمال RFI - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.total_backcharges > Decimal("0.00"):
            backcharges_account = cls.get_or_resolve_account("backcharges_recovery", fallback_code="42201")
            lines.append(
                JournalEntryLineData(
                    account_code=backcharges_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.total_backcharges,
                    currency=currency_str,
                    description=f"استقطاع أوامر خصم ومصاريف محملة على المقاول (Backcharges) - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.defect_rectification_costs > Decimal("0.00"):
            defect_rect_account = cls.get_or_resolve_account("defect_rectification_recovery", fallback_code="42201")
            lines.append(
                JournalEntryLineData(
                    account_code=defect_rect_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.defect_rectification_costs,
                    currency=currency_str,
                    description=f"استقطاع تكاليف إصلاح عيوب مصنعيات - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.nominated_subcontractor_setoff > Decimal("0.00"):
            subcontractor_account = cls.get_or_resolve_account("nominated_subcontractor_payable", fallback_code="21110")
            lines.append(
                JournalEntryLineData(
                    account_code=subcontractor_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.nominated_subcontractor_setoff,
                    currency=currency_str,
                    description=f"مقاصة سداد مباشر لمقاول باطن معين - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.scaffolding_damage_deduction > Decimal("0.00"):
            scaffolding_account = cls.get_or_resolve_account("scaffolding_damage_recovery", fallback_code="42201")
            lines.append(
                JournalEntryLineData(
                    account_code=scaffolding_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.scaffolding_damage_deduction,
                    currency=currency_str,
                    description=f"استقطاع تلفيات وهوالك شدات معدنية وسقالات - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.tripartite_supplier_liens_deduction > Decimal("0.00"):
            lien_account = cls.get_or_resolve_account("tripartite_supplier_lien_payable", fallback_code="21310")
            lines.append(
                JournalEntryLineData(
                    account_code=lien_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.tripartite_supplier_liens_deduction,
                    currency=currency_str,
                    description=f"حجز وتجنيب مستحقات مورد خامات بموجب اتفاق ثلاثي - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.dewatering_fuel_and_stoppage_charges > Decimal("0.00"):
            dewatering_account = cls.get_or_resolve_account("dewatering_recovery", fallback_code="42301")
            lines.append(
                JournalEntryLineData(
                    account_code=dewatering_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.dewatering_fuel_and_stoppage_charges,
                    currency=currency_str,
                    description=f"استقطاع تكاليف ديزل وتشغيل طلمبات النزح الجوفي - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        if cert.third_party_lab_charges > Decimal("0.00"):
            lab_account = cls.get_or_resolve_account("third_party_lab_recovery", fallback_code="42201")
            lines.append(
                JournalEntryLineData(
                    account_code=lab_account.code,
                    debit=Decimal("0.00"),
                    credit=cert.third_party_lab_charges,
                    currency=currency_str,
                    description=f"استقطاع تكاليف اختبارات معامل ضبط الجودة الخارجية - مستخلص {cert.certificate_number}",
                    project=proj_code
                )
            )

        # 4. خط صافي استحقاق المقاول القابل للصرف المطابق تماماً لصافي المستخلص المعتمد
        lines.append(
            JournalEntryLineData(
                account_code=payable_account.code,
                debit=Decimal("0.00"),
                credit=cert.net_amount,
                currency=currency_str,
                description=payout_desc,
                project=proj_code
            )
        )

        total_debits = sum(line.debit for line in lines)
        total_credits = sum(line.credit for line in lines)
        rounding_diff = (total_debits - total_credits).quantize(Decimal("0.01"))
        if rounding_diff != Decimal("0.00"):
            if abs(rounding_diff) <= Decimal("0.05"):
                rounding_account = cls.get_or_resolve_account("rounding_differences", fallback_code="42101")
                if rounding_diff > Decimal("0.00"):
                    lines.append(
                        JournalEntryLineData(
                            account_code=rounding_account.code,
                            debit=Decimal("0.00"),
                            credit=rounding_diff,
                            currency=currency_str,
                            description=f"فروق تقريب قيد مستخلص {cert.certificate_number}",
                            project=proj_code
                        )
                    )
                else:
                    lines.append(
                        JournalEntryLineData(
                            account_code=rounding_account.code,
                            debit=-rounding_diff,
                            credit=Decimal("0.00"),
                            currency=currency_str,
                            description=f"فروق تقريب قيد مستخلص {cert.certificate_number}",
                            project=proj_code
                        )
                    )
            else:
                raise ValidationError(
                    _("عدم تطابق توازن القيد المحاسبي المولد للمستخلص: مدين (%(deb)s) مقابل دائن (%(cred)s).") % {
                        'deb': total_debits,
                        'cred': total_credits
                    }
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

        # تسوية أوامر الخصم المرتبطة بالمستخلص عبر الاستقطاع المباشر
        from real_estate.models import ContractorBackcharge
        for bc in cert.backcharges.filter(is_settled=False):
            bc.is_settled = True
            bc.settlement_method = ContractorBackcharge.SettlementMethod.CERTIFICATE
            bc.settlement_journal_entry = journal_entry
            bc.save(update_fields=['is_settled', 'settlement_method', 'settlement_journal_entry'])

        # تسوية الخصومات البينية المرتبطة بالمستخلص
        from real_estate.models import ContractorBackcharge
        cert.backcharges.filter(is_settled=False).update(
            is_settled=True,
            settlement_method=ContractorBackcharge.SettlementMethod.CERTIFICATE
        )

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
            contract = ContractorContract.objects.select_for_update().get(id=cert.contract_id)
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

        # فك قفل الفوترة عن بنود الموقع الميدانية لنطاق العقد والعمارة المحددة إذا لم يعد هناك مستخلصات سارية معتمدة لنفس النطاق
        if cert.contractor_id and cert.project_id:
            from real_estate.models import UnitSiteProgressRecord
            from django.db.models import Q

            target_block_id = cert.block_id or (cert.contract.block_id if cert.contract else None)
            other_certs_qs = ContractorProgressCertificate.objects.filter(
                contractor_id=cert.contractor_id,
                project_id=cert.project_id,
                status=ContractorProgressCertificate.CertificateStatus.APPROVED
            ).exclude(pk=cert.pk)

            if target_block_id:
                other_certs_covering_block = other_certs_qs.filter(
                    Q(block_id=target_block_id) |
                    Q(contract__block_id=target_block_id) |
                    (Q(block_id__isnull=True) & Q(contract__block_id__isnull=True))
                )
                if not other_certs_covering_block.exists():
                    UnitSiteProgressRecord.objects.filter(
                        contractor_id=cert.contractor_id,
                        unit__project_id=cert.project_id,
                        unit__block_id=target_block_id,
                        is_billed=True
                    ).update(is_billed=False)
            else:
                active_blocks = set(
                    other_certs_qs.exclude(block_id__isnull=True).values_list('block_id', flat=True)
                ) | set(
                    other_certs_qs.exclude(contract__block_id__isnull=True).values_list('contract__block_id', flat=True)
                )
                has_active_project_wide = other_certs_qs.filter(
                    block_id__isnull=True, contract__block_id__isnull=True
                ).exists()

                if not has_active_project_wide:
                    records_to_release = UnitSiteProgressRecord.objects.filter(
                        contractor_id=cert.contractor_id,
                        unit__project_id=cert.project_id,
                        is_billed=True
                    )
                    if active_blocks:
                        records_to_release = records_to_release.exclude(unit__block_id__in=active_blocks)
                    records_to_release.update(is_billed=False)

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
        user=None,
        operation_id: str = None,
        idempotency_key: str = None
    ) -> JournalEntry:
        """
        الإفراج عن تأمين حسن التنفيذ (50% استلام ابتدائي و50% استلام نهائي بعد سنة الصيانة)
        Dr: Contractor Retentions Payable (21310)
        Cr: Defect Rectification Recovery (42201 - إن وجدت خصومات عيوب)
        Cr: Contractor / Assigned Bank Payable (21110)
        """
        contract = ContractorContract.objects.select_for_update().get(id=contract.id)

        SUBSTANTIAL_TYPES = {'SUBSTANTIAL', 'SUBSTANTIAL_HANDOVER'}
        FINAL_TYPES = {'FINAL', 'FINAL_SETTLEMENT', 'FINAL_HANDOVER', 'FINAL_WARRANTY_CLEARANCE'}
        ALL_SUPPORTED_TYPES = SUBSTANTIAL_TYPES | FINAL_TYPES

        if release_type not in ALL_SUPPORTED_TYPES:
            raise ValidationError(
                _("نوع الإفراج عن التأمين غير صالح أو غير معتمد: %(t)s") % {'t': release_type}
            )

        amount_norm = Decimal(str(amount)).quantize(Decimal("0.01"))
        defect_norm = Decimal(str(defect_deductions or 0)).quantize(Decimal("0.01"))

        if defect_norm < Decimal("0.00") or defect_norm > amount_norm:
            raise ValidationError(
                _("قيمة استقطاعات إصلاح العيوب (%(ded)s) غير صالحة ولا يمكن أن تتجاوز مبلغ الإفراج (%(amt)s).") % {
                    'ded': defect_norm,
                    'amt': amount_norm
                }
            )

        # صمام أمان الاعتماد الميداني وخلو المقاول من العيوب المفتوحة
        from real_estate.services.site_progress_service import ProjectProgressCalculationService
        can_release, reason, stats = ProjectProgressCalculationService.validate_subcontractor_retention_release(contract)
        if not can_release:
            raise ValidationError(reason)

        normalized_stage = 'SUBSTANTIAL' if release_type in SUBSTANTIAL_TYPES else 'FINAL'
        gateway = AccountingGateway()

        op_name = operation_id or f'retention_release_{normalized_stage}_{amount_norm}_{defect_norm}'
        if not idempotency_key:
            idemp_key = AccountingGateway.generate_idempotency_key(
                module='real_estate',
                model='ContractorContract',
                object_id=contract.id,
                operation=op_name
            )
        else:
            idemp_key = idempotency_key

        from financial.models import JournalEntry

        # البحث عن العملية المكتملة قبل شروط الطلب الجديد، بصرف النظر عن الرصيد المتبقي (Idempotent Retry Guard)
        existing_entry = JournalEntry.objects.filter(idempotency_key=idemp_key).first()
        if existing_entry:
            import json
            saved_stage = None
            if existing_entry.notes:
                try:
                    payload = json.loads(existing_entry.notes)
                    if isinstance(payload, dict):
                        saved_stage = payload.get('stage')
                        if payload.get('contract_id') and payload['contract_id'] != contract.id:
                            raise ValidationError(_("تعارض في بيانات إعادة طلب الإفراج: العقد المسجل بالقيد غير مطابق للعقد الحالي."))
                except (ValueError, TypeError):
                    saved_stage = None

            if not saved_stage:
                desc_text = existing_entry.description or ''
                ref_text = existing_entry.reference or ''
                if any(st in desc_text or st in ref_text for st in ['(FINAL', 'FINAL_', 'FINAL-']):
                    saved_stage = 'FINAL'
                elif any(st in desc_text or st in ref_text for st in ['(SUBSTANTIAL', 'SUBSTANTIAL_', 'SUBSTANTIAL-']):
                    saved_stage = 'SUBSTANTIAL'

            if saved_stage and saved_stage != normalized_stage:
                raise ValidationError(
                    _("تعارض في مرحلة الإفراج: العملية السابقة لنفس المعرف تخص مرحلة (%(prev)s) بينما الطلب الحالي يخص مرحلة (%(curr)s).") % {
                        'prev': saved_stage,
                        'curr': normalized_stage
                    }
                )

            retention_account = cls.get_or_resolve_account(AccountRoleNames.REAL_ESTATE_CONTRACTOR_RETENTIONS_PAYABLE.value, fallback_code="21310")
            defect_account = cls.get_or_resolve_account("defect_rectification_recovery", fallback_code="42201")

            ret_line = existing_entry.lines.filter(account=retention_account).first()
            def_line = existing_entry.lines.filter(account=defect_account).first()

            existing_debit = ret_line.debit.quantize(Decimal("0.01")) if ret_line else Decimal("0.00")
            existing_defect = def_line.credit.quantize(Decimal("0.01")) if def_line else Decimal("0.00")

            if existing_debit != amount_norm or existing_defect != defect_norm:
                raise ValidationError(
                    _("تعارض في بيانات إعادة طلب الإفراج: البيانات المالية للطلب الحالي غير مطابقة للقيد المسجل مسبقاً بنفس المعرف.")
                )
            return existing_entry

        is_substantial = release_type in SUBSTANTIAL_TYPES
        max_substantial = (contract.total_retention_retained * Decimal("0.50")).quantize(Decimal("0.01")) if is_substantial else Decimal("0.00")

        available_retention = contract.total_retention_retained - contract.total_retention_released
        if amount > available_retention:
            raise ValidationError(
                _("مبلغ التأمين المطلوب الإفراج عنه (%(amount)s) يتجاوز رصيد التأمين المحتجز المتاح (%(avail)s).") % {
                    'amount': amount,
                    'avail': available_retention
                }
            )

        # 2. التحقق من سقف الإفراج المرحلي التراكمي (Cumulative Substantial Cap)
        if is_substantial:
            if (contract.total_retention_released + amount) > max_substantial:
                raise ValidationError(
                    _("إجمالي المبالغ المفرج عنها من تأمين الاستلام الابتدائي (%(tot)s) يتجاوز الحد الأقصى المسموح به 50%% من إجمالي التأمين المحتجز (%(max)s).") % {
                        'tot': contract.total_retention_released + amount,
                        'max': max_substantial
                    }
                )

        # 3. التحقق من مستندات ومحاضر الاستلام للمرحلة
        has_evidence = bool(
            contract.actual_completion_date or
            contract.sectional_handovers.exists() or
            contract.certificate_of_occupancy_number or
            contract.syndicate_supervision_clearance
        )
        if not has_evidence:
            raise ValidationError(_("يلزم تقديم محضر استلام معتمد أو مستندات مرحلية رسمية للإفراج عن التأمين."))

        # 4. التحقق من انقضاء فترة الضمان والصيانة للإفراج النهائي
        if release_type in FINAL_TYPES:
            if not contract.actual_completion_date:
                raise ValidationError(_("لا يمكن الإفراج عن التأمين النهائي بدون إثبات تاريخ الاستلام الابتدائي والأعمال."))
            warranty_months = contract.defect_liability_period_months or 12
            from dateutil.relativedelta import relativedelta
            warranty_end = contract.actual_completion_date + relativedelta(months=warranty_months)
            if timezone.localdate() < warranty_end:
                raise ValidationError(
                    _("لا يمكن الإفراج عن التأمين النهائي قبل انقضاء فترة الضمان والصيانة (تاريخ انتهاء الضمان: %(end)s).") % {
                        'end': warranty_end
                    }
                )

        retention_account = cls.get_or_resolve_account(AccountRoleNames.REAL_ESTATE_CONTRACTOR_RETENTIONS_PAYABLE.value, fallback_code="21310")
        defect_account = cls.get_or_resolve_account("defect_rectification_recovery", fallback_code="42201")

        if contract.is_garnished_by_court:
            payable_account = cls.get_or_resolve_account("judicial_garnishment_escrow", fallback_code="21350")
        else:
            payable_account = getattr(contract.contractor, 'financial_account', None)
            if not payable_account or not payable_account.can_post_entries():
                payable_account = cls.get_or_resolve_account(AccountRoleNames.SUPPLIER_PAYABLE_CONTROL.value, fallback_code="21110")
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

        journal_entry = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='ContractorContract',
            source_id=contract.id,
            lines=lines,
            idempotency_key=idemp_key,
            user=user,
            entry_type='general_ledger',
            description=desc,
            reference=f"RET-REL-{normalized_stage}-{contract.contract_number}",
            date=timezone.localdate()
        )

        import json
        payload_data = {
            'stage': normalized_stage,
            'release_type': release_type,
            'amount': str(amount_norm),
            'defect_deductions': str(defect_norm),
            'contract_id': contract.id,
            'contract_number': contract.contract_number,
            'contractor_id': contract.contractor_id,
            'currency': currency_str,
            'operation_id': operation_id or '',
        }
        journal_entry.notes = json.dumps(payload_data)
        journal_entry.save(update_fields=["notes"])

        contract.total_retention_released += amount
        contract.save(update_fields=["total_retention_released", "updated_at"])

        logger.info(f"Retention released for contract {contract.contract_number}: {amount} {currency_str}. Entry ID: {journal_entry.id}")
        return journal_entry

    @classmethod
    def release_retention_guarantee(cls, *args, **kwargs):
        """توافقية مع شاشات الإفراج عن تأمين حسن التنفيذ"""
        return cls.release_retention(*args, **kwargs)

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
        contract = ContractorContract.objects.select_for_update().get(id=cert.contract_id) if cert.contract_id else None

        if cert.status != ContractorProgressCertificate.CertificateStatus.APPROVED:
            raise ValidationError(_("لا يمكن سداد دفعة لمستخلص غير معتمد رسمياً."))

        if contract:
            eligibility = ContractorContractService.check_contract_payout_eligibility(contract)
            if not eligibility.get("is_eligible_for_direct_payout", True) or eligibility.get("freeze_payout", False):
                reasons = "; ".join(eligibility.get("blocking_reasons", []))
                raise ValidationError(_("تم تجميد صرف المستخلص: %(reasons)s") % {'reasons': reasons})

        if inst.is_settled:
            raise ValidationError(_("الدفعة مسددة بالفعل."))

        locked_cheque = None
        if hasattr(cheque, 'id') and cheque.id and hasattr(cheque, '_meta'):
            from cheques.models import Cheque
            locked_cheque = Cheque.objects.select_for_update().get(id=cheque.id)
        else:
            locked_cheque = cheque

        # 1. التحقق من صلاحية حالة الشيك (يجب أن يكون صادر ومسلم للمستفيد)
        cheque_status = getattr(locked_cheque, 'status', None)
        if cheque_status:
            from cheques.models.cheque import ChequeStatus
            if cheque_status != ChequeStatus.ISSUED and str(cheque_status).upper() != "ISSUED":
                raise ValidationError(
                    _("لا يمكن سداد دفعة المستخلص إلا بشيك في حالة 'صادر ومسلم' (الحالة الحالية: %(st)s).") % {
                        'st': cheque_status
                    }
                )

        # فحص غرض الشيك (حظر شيكات الضمان)
        cheque_purpose = getattr(locked_cheque, 'purpose', None)
        if cheque_purpose:
            from cheques.models.cheque import ChequePurpose
            if cheque_purpose == ChequePurpose.SECURITY_GUARANTEE or str(cheque_purpose).upper() == "SECURITY_GUARANTEE":
                raise ValidationError(_("لا يمكن سداد دفعة تشغيلية لمستخلص باستخدام شيك ضمان / تأمين حسن تنفيذ."))

        # 2. التحقق من المستفيد والمورد
        cheque_supplier_id = getattr(locked_cheque, 'supplier_id', None)
        cheque_payee = getattr(locked_cheque, 'payee_name', '').strip()
        contractor_name = cert.contractor.name.strip() if cert.contractor else ''

        if cheque_supplier_id:
            expected_supplier_id = cert.contractor_id
            if contract and contract.is_assigned_to_bank and getattr(contract, 'assigned_bank_supplier_id', None):
                expected_supplier_id = contract.assigned_bank_supplier_id or cert.contractor_id
            if cheque_supplier_id != expected_supplier_id:
                raise ValidationError(_("الشيك صادر لمورد آخر مختلف عن مقاول المستخلص."))

        # التحقق من تطابق اسم المستفيد المسجل على الشيك في جميع الأحوال
        is_bank_assigned_match = bool(
            contract and contract.is_assigned_to_bank and contract.assigned_bank_name and
            contract.assigned_bank_name in cheque_payee
        )
        if not cheque_payee or (contractor_name and cheque_payee != contractor_name and not is_bank_assigned_match):
            raise ValidationError(
                _("اسم المستفيد المسجل على الشيك (%(payee)s) غير مطابق لمقاول المستخلص (%(contractor)s).") % {
                    'payee': cheque_payee,
                    'contractor': contractor_name
                }
            )

        # 3. التحقق من العملة
        cheque_curr_id = getattr(locked_cheque, 'currency_id', None)
        if cheque_curr_id and cert.currency_id and cheque_curr_id != cert.currency_id:
            raise ValidationError(_("عملة الشيك غير متطابقة مع عملة المستخلص."))

        # التحقق من أن إجمالي المدفوعات المسددة للمستخلص لا تتجاوز صافي الاستحقاق المعتمد
        from django.db.models import Sum
        already_settled_for_cert = CertificatePaymentInstallmentSchedule.objects.filter(
            certificate=cert,
            is_settled=True
        ).exclude(id=inst.id).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

        remaining_cert_liability = max(Decimal('0.00'), cert.net_amount - already_settled_for_cert)
        if inst.amount > remaining_cert_liability:
            raise ValidationError(
                _("مبلغ الدفعة المطلوب سدادها (%(inst_amt)s) يتجاوز صافي الاستحقاق المتبقي للمستخلص (%(rem)s).") % {
                    'inst_amt': inst.amount,
                    'rem': remaining_cert_liability
                }
            )

        # 4. حساب الرصيد المتاح للتخصيص دون تصفير رصيد الصرف البنكي
        if hasattr(locked_cheque, 'amount'):
            cheque_total_amount = locked_cheque.amount or Decimal('0.00')
            cheque_filter_kwargs = {'pdc_cheque': locked_cheque} if hasattr(locked_cheque, '_meta') else {'pdc_cheque_id': getattr(locked_cheque, 'id', 0)}
            allocated_to_installments = CertificatePaymentInstallmentSchedule.objects.filter(
                is_settled=True,
                **cheque_filter_kwargs
            ).exclude(id=inst.id).aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0.00')

            allocated_to_invoices = Decimal('0.00')
            if hasattr(locked_cheque, 'invoice_allocations'):
                from cheques.models.allocation import AllocationStatus
                allocated_to_invoices = locked_cheque.invoice_allocations.filter(
                    allocation_status=AllocationStatus.APPLIED
                ).aggregate(
                    total=Sum('allocated_amount')
                )['total'] or Decimal('0.00')

            prepaid_alloc = getattr(locked_cheque, 'prepaid_allocated_amount', Decimal('0.00')) or Decimal('0.00')
            total_allocated = allocated_to_installments + allocated_to_invoices + prepaid_alloc
            available_for_allocation = max(Decimal('0.00'), cheque_total_amount - total_allocated)

            if inst.amount > available_for_allocation:
                raise ValidationError(
                    _("مبلغ الدفعة المطلوب سدادها (%(inst_amt)s) يتجاوز الرصيد المتاح للتخصيص بالشيك (%(rem)s).") % {
                        'inst_amt': inst.amount,
                        'rem': available_for_allocation
                    }
                )

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

    @classmethod
    @transaction.atomic
    def absorb_pending_backcharges(cls, certificate: ContractorProgressCertificate) -> int:
        """
        امتصاص الخصومات المعلقة للمقاول في مسودة المستخلص
        """
        from real_estate.models import ContractorBackcharge
        from django.db.models import Q
        if certificate.status != ContractorProgressCertificate.CertificateStatus.DRAFT:
            return 0
        qs = ContractorBackcharge.objects.filter(
            contractor_id=certificate.contractor_id,
            is_settled=False,
            certificate__isnull=True
        )
        if certificate.contract_id:
            qs = qs.filter(Q(contract_id=certificate.contract_id) | Q(contract__isnull=True))

        count = 0
        for bc in qs:
            bc.certificate = certificate
            bc.settlement_method = ContractorBackcharge.SettlementMethod.CERTIFICATE
            if not bc.contract_id and certificate.contract_id:
                bc.contract_id = certificate.contract_id
            bc.save()
            count += 1

        if count > 0:
            certificate.total_backcharges = sum(b.amount for b in certificate.backcharges.all())
            certificate.compute_amounts()
            certificate.save()

        return count

    @classmethod
    @transaction.atomic
    def liquidate_backcharge_against_retention(cls, backcharge_id: int, user=None) -> JournalEntry:
        """
        تسييل خصم بيني أو تكلفة إصلاح عيب مباشرة من حساب تأمين حسن التنفيذ للمقاول (21310)
        Dr: Contractor Retentions Payable (21310)
        Cr: Backcharges Recovery / Defect Rectification Income (42201)
        """
        from real_estate.models import ContractorBackcharge, UnitSnagItem
        backcharge = ContractorBackcharge.objects.select_for_update().get(id=backcharge_id)
        if backcharge.is_settled:
            raise ValidationError(_("هذا الخصم تمت تسويته مسبقاً."))

        if backcharge.certificate:
            if backcharge.certificate.status == ContractorProgressCertificate.CertificateStatus.APPROVED:
                raise ValidationError(_("لا يمكن تسييل خصم تم ترحيل مستخلصه واعتماده نهائياً."))
            # تعديل مبالغ المستخلص المرتبط لمنع التكرار المحاسبي للاسترداد
            cert = backcharge.certificate
            cert.total_backcharges = max(Decimal('0.00'), cert.total_backcharges - backcharge.amount)
            cert.compute_amounts()
            if cert.approval_snapshot_hash:
                cert.approval_snapshot_hash = cert.compute_financial_hash()
            cert.save(update_fields=['total_backcharges', 'net_amount', 'approval_snapshot_hash'])

        contract = backcharge.contract
        contractor = backcharge.contractor or (contract.contractor if contract else None)
        if not contractor:
            raise ValidationError(_("يجب تحديد المقاول لتسييل الخصم من حسابه."))

        currency_str = getattr(contract.currency if contract else None, 'code', 'EGP')
        proj_code = contract.project.code if (contract and contract.project) else None

        retention_account = cls.get_or_resolve_account(AccountRoleNames.REAL_ESTATE_CONTRACTOR_RETENTIONS_PAYABLE.value, fallback_code="21310")
        recovery_account = cls.get_or_resolve_account("backcharges_recovery", fallback_code="42201")

        amount = backcharge.amount
        if amount <= Decimal('0.00'):
            raise ValidationError(_("مبلغ الخصم يجب أن يكون أكبر من الصفر."))

        if contract:
            available_retention = contract.total_retention_retained - contract.total_retention_released
            if amount > available_retention:
                raise ValidationError(
                    _("مبلغ الخصم المراد تسييله (%(amt)s) يتجاوز رصيد التأمين المتاح بالعقد (%(avail)s).") % {
                        'amt': amount,
                        'avail': available_retention
                    }
                )

        lines = [
            JournalEntryLineData(
                account_code=retention_account.code,
                debit=amount,
                credit=Decimal("0.00"),
                currency=currency_str,
                description=f"تسييل مباشر من تأمين المقاول {contractor.name} لتسوية خصم/عيب {backcharge.memo_reference or backcharge.id}",
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=recovery_account.code,
                debit=Decimal("0.00"),
                credit=amount,
                currency=currency_str,
                description=f"استرداد تكاليف إصلاح عيوب / خصم بيني على المقاول {contractor.name}",
                project=proj_code
            )
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='ContractorBackcharge',
            object_id=backcharge.id,
            operation='retention_liquidation'
        )

        gateway = AccountingGateway()
        journal_entry = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='ContractorBackcharge',
            source_id=backcharge.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='general_ledger',
            description=f"تسييل تأمين مقاول لتغطية خصم إصلاح عيوب - {contractor.name}",
            reference=f"BC-LIQ-{backcharge.id}",
            date=timezone.localdate()
        )

        backcharge.is_settled = True
        backcharge.settlement_method = ContractorBackcharge.SettlementMethod.RETENTION_LIQUIDATION
        backcharge.settlement_journal_entry = journal_entry
        backcharge.save()

        if contract:
            contract.total_retention_released += amount
            contract.save(update_fields=['total_retention_released', 'updated_at'])

        if backcharge.snag_item:
            backcharge.snag_item.status = UnitSnagItem.SnagStatus.RESOLVED
            backcharge.snag_item.resolution_notes = f"تمت التسوية بتسييل {amount} {currency_str} من تأمين المقاول بقيد {journal_entry.number}"
            backcharge.snag_item.resolved_at = timezone.now()
            backcharge.snag_item.save(update_fields=['status', 'resolution_notes', 'resolved_at'])

        logger.info(f"Backcharge {backcharge.id} liquidated against retention. Journal entry: {journal_entry.id}")
        return journal_entry

    reverse_posted_certificate_storno = reverse_certificate
