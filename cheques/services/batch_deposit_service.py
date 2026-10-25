# -*- coding: utf-8 -*-
from decimal import Decimal
from typing import List, Optional
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from financial.models import ChartOfAccounts
from financial.services.treasury_security_service import TreasurySecurityService

from cheques.models import (
    Cheque,
    ChequeType,
    ChequeStatus,
    ChequePurpose,
    ChequeBatchDeposit,
    BatchDepositStatus,
    ChequeActionType,
)
from cheques.services.accounting_service import ChequeAccountingService


class ChequeBatchDepositService:
    """
    خدمة إنشاء وإدارة حافظات إيداع الشيكات المجمعة بالبنوك (FIN-CHQ-BATCH)
    """

    @classmethod
    @transaction.atomic
    def create_and_deposit_batch(
        cls,
        bank_account_id: int,
        cheque_ids: List[int],
        user,
        deposit_date=None,
        notes: str = ""
    ) -> ChequeBatchDeposit:
        """
        إنشاء الحافظة وإيداع كافة الشيكات المحددة دفعة واحدة بالبنك وتوليد قيود الإيداع
        """
        if not cheque_ids:
            raise ValidationError(_("يجب تحديد شيك واحد على الأقل لإنشاء حافظة الإيداع."))

        bank_account = ChartOfAccounts.objects.filter(pk=bank_account_id, is_active=True).first()
        if not bank_account:
            raise ValidationError(_("الحساب البنكي المحدد غير موجود أو غير نشط."))

        # 1. التحقق من صلاحية الإيداع على الحساب البنكي
        TreasurySecurityService.enforce_deposit(user, bank_account_id)

        target_date = deposit_date or timezone.now().date()

        # 2. قفل والتحقق من الشيكات المختارة
        cheques = list(
            Cheque.objects.select_for_update()
            .filter(
                id__in=cheque_ids,
                cheque_type=ChequeType.RECEIVABLE,
                status=ChequeStatus.IN_PORTFOLIO,
            ).exclude(
                purpose=ChequePurpose.SECURITY_GUARANTEE
            )
        )

        if len(cheques) != len(cheque_ids):
            found_ids = {c.id for c in cheques}
            missing = set(cheque_ids) - found_ids
            raise ValidationError(
                _("بعض الشيكات المحددة غير صالحة للإيداع أو ليست في المحفظة: {missing}").format(
                    missing=list(missing)
                )
            )

        # 3. توليد رقم الحافظة الآلي عبر محرك السيريال المركزي
        batch_number = SequenceService.get_next_number(
            DocumentType.CHEQUE_DEPOSIT_BATCH,
            warehouse=None
        )

        total_amount = sum(c.remaining_amount for c in cheques)

        batch = ChequeBatchDeposit.objects.create(
            batch_number=batch_number,
            deposit_date=target_date,
            bank_account=bank_account,
            total_amount=total_amount,
            status=BatchDepositStatus.DEPOSITED,
            notes=notes,
            created_by=user,
        )
        batch.cheques.set(cheques)

        # 4. إيداع كل شيك وتوليد قيد الإيداع المستقل
        for chq in cheques:
            idemp_key = f"DEP-BATCH-{batch.id}-CHQ-{chq.id}"
            ChequeAccountingService.deposit_cheque(
                cheque_id=chq.id,
                user=user,
                idempotency_key=idemp_key,
                bank_account_id=bank_account.id,
                value_date=target_date
            )

        return batch

    @classmethod
    def sync_batch_status(cls, batch: ChequeBatchDeposit) -> str:
        """
        مزامنة وتحديث حالة الحافظة بناء على حالات الشيكات التابعة لها
        """
        cheques = batch.cheques.all()
        if not cheques.exists():
            return batch.status

        statuses = set(cheques.values_list('status', flat=True))
        
        # إذا تم حسم كافة الشيكات (محصلة، مرتدة، أو ملغاة)
        terminal_statuses = {
            ChequeStatus.COLLECTED,
            ChequeStatus.BOUNCED,
            ChequeStatus.CANCELLED,
            ChequeStatus.RETURNED_TO_DRAWER,
            ChequeStatus.LEGAL_ACTION,
            ChequeStatus.LEGAL_SETTLEMENT,
        }

        if statuses.issubset(terminal_statuses):
            batch.status = BatchDepositStatus.CLOSED
        elif any(s in terminal_statuses or s == ChequeStatus.PARTIALLY_COLLECTED for s in statuses):
            batch.status = BatchDepositStatus.PARTIALLY_CLEARED
        else:
            batch.status = BatchDepositStatus.DEPOSITED

        batch.save(update_fields=['status'])
        return batch.status
