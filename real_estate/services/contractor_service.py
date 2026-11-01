# -*- coding: utf-8 -*-
"""
Contractor Progress Service (Wave 2 - Phase 6)
إدارة مستخلصات مقاولي الباطن والتشييد:
- حساب الاستقطاعات (تأمين حسن تنفيذ، استرداد الدفعة المقدمة، ضريبة الخصم والإضافة)
- الربط المحكم مع دورة الاعتماد المؤسسية EnterpriseApprovalRequest وقواعد الاعتماد المتدرجة
- القفل التشفيري ضد تعديل البيانات المالية بعد الاعتماد (Cryptographic Financial Mutation Lock)
- الحارس المالي الصارم (Hard Payment Guard) وإصدار قيود الاستحقاق عبر AccountingGateway
"""
from decimal import Decimal
import logging
from typing import Optional

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from real_estate.models import ContractorProgressCertificate
from financial.models import ChartOfAccounts, JournalEntry
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from financial.services.approval_service import ApprovalService
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData

logger = logging.getLogger(__name__)


class MissingApprovalRuleError(ValidationError):
    """خطأ عدم وجود قاعدة اعتماد مالي مطابقة للمستخلص"""
    pass


class MutationTamperError(ValidationError):
    """خطأ اكتشاف تعديل مالي غير مصرح به على مستخلص معتمد أو قيد الاعتماد"""
    pass


class ContractorProgressService:
    """
    محرك خدمة مستخلصات مقاولي الباطن والاعتمادات المؤسسية
    """

    @classmethod
    def get_or_resolve_account(cls, role_name: str, fallback_code: str) -> ChartOfAccounts:
        """جلب الحساب المحاسبي عبر سجل الأدوار الموحد مع استخدام الحساب الاحتياطي"""
        account = AccountRoleRegistry.get_account(role_name)
        if not account:
            account = ChartOfAccounts.objects.filter(code=fallback_code).first()
        if not account or not account.is_active:
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
        يتحقق من الحسابات ويثبت البصمة الرقمية المشفرة
        """
        cert = ContractorProgressCertificate.objects.select_for_update().get(id=certificate.id)

        # 1. إعادة حساب المبالغ بدقة
        cert.compute_amounts()

        # 2. توليد وتثبيت البصمة الرقمية المشفرة لحماية البيانات من التعديل
        cert.approval_snapshot_hash = cert.compute_financial_hash()

        # 3. استدعاء خدمة الاعتماد المؤسسية
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
        cert.save(update_fields=['gross_certified_work', 'previous_certified_work', 'current_period_work',
                                'materials_on_site', 'retention_amount', 'advance_payment_recovery',
                                'wht_amount', 'penalty_deductions', 'net_amount',
                                'approval_snapshot_hash', 'approval_request', 'status', 'updated_at'])

        logger.info(f"Contractor certificate {cert.certificate_number} submitted for approval. Request ID: {approval_req.id}")
        return cert

    @classmethod
    def verify_and_post_certificate(cls, certificate: ContractorProgressCertificate, user) -> JournalEntry:
        """
        التحقق من اكتمال الاعتماد والقفل التشفيري، ثم إصدار قيد استحقاق المستخلص عبر AccountingGateway
        Dr: WIP Construction Project Cost (12101) [بإجمالي قيمة الأعمال + التشوينات]
        Cr: Contractor Retentions Payable (21310) [بتأمين حسن التنفيذ]
        Cr: Contractor Advance Payments (11350) [باسترداد الدفعة المقدمة]
        Cr: Withholding Tax Payable (21330) [بضريبة الخصم والإضافة]
        Cr: Supplier / Contractor Payable Control (21110) [بصافي المستحق للصرف]
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

        # 3. تحديد الحسابات المحاسبية وإصدار القيد
        with transaction.atomic():
            cert = ContractorProgressCertificate.objects.select_for_update().get(id=cert.id)
        wip_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_WIP_CONSTRUCTION.value,
            fallback_code="12101"
        )
        retention_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_CONTRACTOR_RETENTIONS_PAYABLE.value,
            fallback_code="21310"
        )
        payable_account = cls.get_or_resolve_account(
            AccountRoleNames.SUPPLIER_PAYABLE_CONTROL.value,
            fallback_code="21110"
        )
        wht_account = cls.get_or_resolve_account(
            AccountRoleNames.WITHHOLDING_TAX_PAYABLE.value,
            fallback_code="21330"
        )
        advance_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_CONTRACTOR_ADVANCE.value,
            fallback_code="11350"
        )

        currency_str = getattr(cert.currency, 'code', 'EGP')
        proj_code = cert.project.code if cert.project else None

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
