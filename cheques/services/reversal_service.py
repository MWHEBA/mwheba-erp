# -*- coding: utf-8 -*-
import logging
from decimal import Decimal
from typing import Dict, Any, Optional

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from financial.models.bank_reconciliation import BankReconciliationMatch
from financial.services.ledger_core_service import LedgerCoreService
from cheques.models import (
    Cheque,
    ChequeType,
    ChequePurpose,
    ChequeStatus,
    ChequeActionLog,
    ChequeActionType,
    ChequeSettlementLine,
)

logger = logging.getLogger(__name__)


class ChequeReversalService:
    """
    خدمة التراجع الخطي الآمن عن حركات الشيكات (LIFO Action Reversal Engine)
    تستهدف حصراً آخر حركة أصلية فعالة غير معكوسة وتمنع التراجع العشوائي أو كسر التسويات البنكية
    """

    @classmethod
    def reverse_last_action(
        cls,
        cheque_id: Optional[int] = None,
        user=None,
        reason: str = "",
        idempotency_key: Optional[str] = None,
        cheque: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        تنفيذ التراجع الخطي الآمن:
        1. استهداف «آخر حركة أصلية فعالة غير معكوسة» واستثناء حركات REVERSE_ACTION.
        2. التحقق من عدم وجود حركات أصلية لاحقة فعالة.
        3. التحقق الصارم من التسوية البنكية: إذا كان القيد مطابقاً في كشف حساب البنك، يمنع التراجع قطيعاً.
        4. فحص وعكس التخصيصات الفاتورية إن وُجدت.
        5. عكس قيد اليومية المرتبط عبر LedgerCoreService.reverse_entry().
        6. استعادة الأرصدة (المحصل والمتبقي) وحالة الشيك للحالة السابقة target_log.from_status.
        7. وسم الحركة target_log.is_reversed = True وتسجيل حركة REVERSE_ACTION جديدة.
        """
        if cheque_id is None and cheque is not None:
            cheque_id = cheque.id
        if not cheque_id:
            raise ValidationError(_("يجب تحديد الشيك المراد التراجع عن حركته."))
        if not idempotency_key:
            import uuid
            idempotency_key = f"REV-{cheque_id}-{uuid.uuid4().hex[:12]}"
        if not reason or not reason.strip():
            raise ValidationError(_("يجب تدوين سبب التراجع عن الحركة."))

        with transaction.atomic():
            # 0. التحقق من مفتاح منع التكرار وإرجاع النتيجة السابقة بأمان (Cached Replay)
            existing_rev = ChequeActionLog.objects.filter(idempotency_key=idempotency_key).first()
            if existing_rev:
                if existing_rev.cheque_id != cheque_id or existing_rev.action != ChequeActionType.REVERSE_ACTION:
                    raise ValidationError(
                        _("تعارض في مفتاح عدم التكرار: المفتاح مستخدم مسبقاً لعملية أخرى أو لشيك مختلف.")
                    )
                logger.info(f"Reversal Idempotent Cached Replay returned for key {idempotency_key}")
                reversed_target = getattr(existing_rev, "reverses_log", None)
                return {
                    "cheque": existing_rev.cheque,
                    "reversed_action_log": reversed_target,
                    "reversal_log": existing_rev,
                    "reversal_entry": existing_rev.journal_entry,
                    "is_retry": True,
                }

            cheque = Cheque.objects.select_for_update().get(pk=cheque_id)

            # 1. البحث عن آخر حركة أصلية فعالة غير معكوسة
            target_log = cheque.action_logs.filter(
                is_reversed=False
            ).exclude(
                action=ChequeActionType.REVERSE_ACTION
            ).order_by("-id").first()

            if not target_log:
                raise ValidationError(_("لا توجد حركات قابلة للتراجع على هذا الشيك."))

            # 2. التحقق من عدم وجود حركات أصلية لاحقة نشطة
            subsequent_active = cheque.action_logs.filter(
                id__gt=target_log.id,
                is_reversed=False
            ).exclude(
                action=ChequeActionType.REVERSE_ACTION
            )
            if subsequent_active.exists():
                raise ValidationError(
                    _("لا يمكن التراجع عن الحركة '{action}' لوجود حركات لاحقة نشطة يجب التراجع عنها أولاً وفق مبدأ LIFO.").format(
                        action=target_log.get_action_display()
                    )
                )

            # 3. فحص التسوية البنكية (Bank Reconciliation Guard)
            reversal_entry = None
            if target_log.journal_entry:
                is_reconciled = BankReconciliationMatch.objects.filter(
                    journal_line__journal_entry=target_log.journal_entry,
                    status="MATCHED"
                ).exists()
                if is_reconciled:
                    raise ValidationError(
                        _("لا يمكن التراجع عن حركة تم مطابقتها واعتمادها في كشف الحساب البنكي. يجب إلغاء المطابقة البنكية أولاً.")
                    )

                # عكس قيد اليومية
                reversal_reason = f"عكس تدقيقي لحركة {target_log.get_action_display()} لشيك #{cheque.cheque_number}: {reason}"
                reversal_entry = LedgerCoreService.reverse_entry(
                    entry_id=target_log.journal_entry_id,
                    user=user,
                    reversal_reason=reversal_reason
                )

            # 4. استعادة الأرصدة والحقول بحسب نوع الحركة المتراجع عنها
            if target_log.action == ChequeActionType.COLLECT:
                # حذف أو عكس سطر التسوية المرتبط
                settlement = ChequeSettlementLine.objects.filter(action_log=target_log).first()
                if settlement:
                    cheque.collected_amount -= settlement.settled_amount_currency
                    cheque.remaining_amount += settlement.settled_amount_currency
                    settlement.delete()
                else:
                    cheque.collected_amount = Decimal("0.00")
                    cheque.remaining_amount = cheque.amount
                cheque.remaining_functional = cheque.compute_remaining_functional()

            elif target_log.action == ChequeActionType.CLEAR:
                # عكس صرف شيك الدفع: استعادة الرصيد المتبقي وحذف سطر التسوية وإلغاء بيانات الصرف
                settlement = ChequeSettlementLine.objects.filter(action_log=target_log).first()
                if settlement:
                    settlement.delete()
                cheque.remaining_amount = cheque.amount
                cheque.remaining_functional = cheque.compute_remaining_functional()
                cheque.cleared_at = None
                cheque.cleared_by = None
                cheque.collection_date = None

            elif target_log.action == ChequeActionType.CONVERT_GUARANTEE:
                # عكس تحويل الضمان: استعادة غرض شيك الضمان الأصلي وبيانات جهة وتاريخ الإصدار السابقة من الحقول المنظمة
                cheque._authorized_mutation_context = 'REVERSE_CONVERT_GUARANTEE'
                cheque.purpose = ChequePurpose.SECURITY_GUARANTEE
                if cheque.cheque_type == ChequeType.PAYABLE:
                    # 1. الاستعادة من الحقول المنظمة المستقلة في سجل الحركة
                    if target_log.previous_issuer_id or target_log.previous_issued_at:
                        cheque.issued_by = target_log.previous_issuer
                        cheque.issued_at = target_log.previous_issued_at
                    elif getattr(target_log, 'metadata', None) and ('previous_issuer_id' in target_log.metadata or 'previous_issued_at' in target_log.metadata):
                        prev_uid = target_log.metadata.get('previous_issuer_id')
                        cheque.issued_by_id = prev_uid if prev_uid else None
                        prev_at = target_log.metadata.get('previous_issued_at')
                        if prev_at:
                            from django.utils.dateparse import parse_datetime
                            cheque.issued_at = parse_datetime(prev_at)
                        else:
                            cheque.issued_at = None
                    else:
                        # 2. استرجاع احتياطي من سجل الإصدار السابق المؤكد إن وُجد، أو تصفير إذا كان قادماً من مسودة
                        prev_issue_log = cheque.action_logs.filter(
                            action=ChequeActionType.ISSUE
                        ).exclude(id=target_log.id).order_by('-id').first()
                        if prev_issue_log:
                            cheque.issued_by = prev_issue_log.created_by
                            cheque.issued_at = prev_issue_log.created_at
                        elif target_log.from_status == ChequeStatus.DRAFT:
                            cheque.issued_by = None
                            cheque.issued_at = None

            elif target_log.action == ChequeActionType.ENDORSE:
                # عكس تظهير الشيك: إلغاء المورد المظهر إليه
                cheque._authorized_mutation_context = 'REVERSE_ENDORSE'
                cheque.supplier = None

            elif target_log.action in [ChequeActionType.BOUNCE, ChequeActionType.CANCEL, ChequeActionType.RETURN_TO_DRAWER]:
                # استعادة تخصيصات الفواتير التي تأثرت بهذه الحركة حصراً (سواء ارتداد/إلغاء كامل أو جزئي)
                target_tag = f"[ACTION_REV:{target_log.id}]"
                legacy_tag = f"[BOUNCE_REV:{target_log.id}]"
                partial_tag = f"[PARTIAL_BOUNCE:{target_log.id}]"

                # 1. التخصيصات المعكوسة بسبب هذه الحركة
                reversed_by_action = [
                    a for a in cheque.invoice_allocations.all()
                    if target_tag in (a.notes or "") or legacy_tag in (a.notes or "")
                ]
                # 2. التخصيصات المتأثرة بارتداد جزئي
                partial_by_action = [
                    a for a in cheque.invoice_allocations.all()
                    if partial_tag in (a.notes or "")
                ]

                # في حال عدم وجود وسوم محددة، نعتمد على التخصيصات المعكوسة التي لم تُلغَ يدوياً
                if not reversed_by_action and not partial_by_action:
                    reversed_by_action = [
                        a for a in cheque.invoice_allocations.filter(allocation_status="REVERSED")
                        if "[MANUAL_REV" not in (a.notes or "")
                    ]

                for alloc in reversed_by_action:
                    alloc.allocation_status = "APPLIED"
                    alloc.notes = (alloc.notes or "").replace(target_tag, "").replace(legacy_tag, "").strip()
                    alloc.save(update_fields=["allocation_status", "notes"])
                    sale = alloc.sale
                    from sale.models import SalePayment
                    if alloc.sale_payment_id:
                        alloc.sale_payment.status = "posted"
                        alloc.sale_payment.amount = alloc.allocated_amount
                        alloc.sale_payment.save(update_fields=["status", "amount"])
                    else:
                        target_pmt = SalePayment.objects.filter(
                            sale=sale,
                            source_type="CHEQUE",
                            reference_number=cheque.voucher_number,
                            amount=alloc.allocated_amount
                        ).first()
                        if target_pmt:
                            target_pmt.status = "posted"
                            target_pmt.amount = alloc.allocated_amount
                            target_pmt.save(update_fields=["status", "amount"])
                            alloc.sale_payment = target_pmt
                            alloc.save(update_fields=["sale_payment"])
                        else:
                            SalePayment.objects.filter(
                                sale=sale,
                                source_type="CHEQUE",
                                reference_number=cheque.voucher_number
                            ).update(status="posted", amount=alloc.allocated_amount)
                    if hasattr(sale, "update_payment_status"):
                        sale.update_payment_status()

                    # استعادة الرصيد المفتوح للأستاذ المساعد للفاتورة
                    orig_audit = getattr(alloc, "allocation_audit", None)
                    inv_txn = orig_audit.invoice_transaction if orig_audit else None
                    if not inv_txn:
                        from customer.models import CustomerTransaction
                        inv_txn = CustomerTransaction.objects.filter(
                            customer=sale.customer,
                            transaction_type="INVOICE",
                            reference_id=str(sale.id)
                        ).first()
                    if inv_txn:
                        inv_txn.open_amount = max(Decimal("0.00"), inv_txn.open_amount - alloc.allocated_amount_functional)
                        inv_txn.open_amount_functional = inv_txn.open_amount
                        if inv_txn.exchange_rate and inv_txn.exchange_rate > Decimal("0.000000"):
                            inv_txn.open_amount_foreign = (inv_txn.open_amount / inv_txn.exchange_rate).quantize(Decimal("0.01"))
                        inv_txn.status = "CLOSED" if inv_txn.open_amount <= Decimal("0.00") else "PARTIAL"
                        inv_txn.save()

                    # استعادة القيد المحاسبي لتسوية الدفعة المقدمة إن وُجد
                    if alloc.journal_entry:
                        try:
                            if alloc.journal_entry.reversed_by_entry and alloc.journal_entry.reversed_by_entry.status == "posted":
                                new_je = LedgerCoreService.reverse_entry(
                                    entry_id=alloc.journal_entry.reversed_by_entry_id,
                                    user=user,
                                    reversal_reason=f"استعادة قيد تسوية الدفعة المقدمة على الفاتورة {sale.number} بعد التراجع عن حركة {target_log.get_action_display()} لشيك #{cheque.cheque_number}"
                                )
                                alloc.journal_entry = new_je
                                alloc.save(update_fields=["journal_entry"])
                            elif alloc.journal_entry.status != "posted":
                                from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
                                from financial.services.subledger_account_service import SubledgerAccountService
                                from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData, JournalEntrySourceInfo
                                advance_acc = AccountRoleRegistry.get_account(AccountRoleNames.CUSTOMER_ADVANCE_LIABILITY)
                                cust_acc = SubledgerAccountService.get_or_create_customer_account(sale.customer, user=user)
                                rate = cheque.original_exchange_rate or Decimal("1.000000")
                                curr_code = cheque.currency.code if cheque.currency else "EGP"
                                functional_amount = (alloc.allocated_amount * rate).quantize(Decimal("0.01"))
                                new_je = AccountingGateway.create_journal_entry(
                                    source_info=JournalEntrySourceInfo(
                                        module="cheques",
                                        model="Cheque",
                                        object_id=cheque.id,
                                        reference=f"RESTORE-ALLOC-{cheque.voucher_number}->{sale.number}",
                                    ),
                                    date=timezone.now().date(),
                                    description=f"استعادة قيد تسوية دفعة مقدمة لشيك #{cheque.cheque_number} على فاتورة {sale.number}",
                                    lines=[
                                        JournalEntryLineData(
                                            account_code=advance_acc.code,
                                            debit=functional_amount,
                                            credit=Decimal("0.00"),
                                            description=f"تسوية دفعة مقدمة لشيك #{cheque.cheque_number} على فاتورة {sale.number}",
                                            cost_center=None,
                                            currency=curr_code,
                                            exchange_rate=rate,
                                        ),
                                        JournalEntryLineData(
                                            account_code=cust_acc.code,
                                            debit=Decimal("0.00"),
                                            credit=functional_amount,
                                            description=f"سداد فاتورة {sale.number} من دفعة مقدمة لشيك #{cheque.cheque_number}",
                                            cost_center=None,
                                            currency=curr_code,
                                            exchange_rate=rate,
                                        ),
                                    ],
                                    user=user,
                                )
                                alloc.journal_entry = new_je
                                alloc.save(update_fields=["journal_entry"])
                        except Exception as je_err:
                            logger.error(f"Error restoring allocation journal entry: {je_err}")
                            raise ValidationError(_(f"فشل استعادة قيد اليومية لتسوية الدفعة المقدمة: {je_err}"))

                for alloc in partial_by_action:
                    alloc.notes = (alloc.notes or "").replace(partial_tag, "").strip()
                    alloc.save(update_fields=["notes"])
                    sale = alloc.sale
                    from sale.models import SalePayment
                    old_pmt_amount = Decimal("0.00")
                    if alloc.sale_payment_id:
                        old_pmt_amount = alloc.sale_payment.amount
                        alloc.sale_payment.status = "posted"
                        alloc.sale_payment.amount = alloc.allocated_amount
                        alloc.sale_payment.save(update_fields=["status", "amount"])
                    else:
                        target_pmt = SalePayment.objects.filter(
                            sale=sale,
                            source_type="CHEQUE",
                            reference_number=cheque.voucher_number
                        ).first()
                        if target_pmt:
                            old_pmt_amount = target_pmt.amount
                            target_pmt.status = "posted"
                            target_pmt.amount = alloc.allocated_amount
                            target_pmt.save(update_fields=["status", "amount"])
                            alloc.sale_payment = target_pmt
                            alloc.save(update_fields=["sale_payment"])
                        else:
                            SalePayment.objects.filter(
                                sale=sale,
                                source_type="CHEQUE",
                                reference_number=cheque.voucher_number
                            ).update(status="posted", amount=alloc.allocated_amount)
                    if hasattr(sale, "update_payment_status"):
                        sale.update_payment_status()

                    # استعادة الرصيد المفتوح للأستاذ المساعد للفاتورة
                    restored_diff = max(Decimal("0.00"), alloc.allocated_amount - old_pmt_amount)
                    rate = cheque.original_exchange_rate or Decimal("1.000000")
                    restored_diff_functional = (restored_diff * rate).quantize(Decimal("0.01"))
                    orig_audit = getattr(alloc, "allocation_audit", None)
                    inv_txn = orig_audit.invoice_transaction if orig_audit else None
                    if not inv_txn:
                        from customer.models import CustomerTransaction
                        inv_txn = CustomerTransaction.objects.filter(
                            customer=sale.customer,
                            transaction_type="INVOICE",
                            reference_id=str(sale.id)
                        ).first()
                    if inv_txn and restored_diff_functional > Decimal("0.00"):
                        inv_txn.open_amount = max(Decimal("0.00"), inv_txn.open_amount - restored_diff_functional)
                        inv_txn.open_amount_functional = inv_txn.open_amount
                        if inv_txn.exchange_rate and inv_txn.exchange_rate > Decimal("0.000000"):
                            inv_txn.open_amount_foreign = (inv_txn.open_amount / inv_txn.exchange_rate).quantize(Decimal("0.01"))
                        inv_txn.status = "CLOSED" if inv_txn.open_amount <= Decimal("0.00") else "PARTIAL"
                        inv_txn.save()

                previous_status = target_log.from_status
                if previous_status == ChequeStatus.COLLECTED:
                    cheque.collected_amount = cheque.amount
                    cheque.remaining_amount = Decimal("0.00")
                    cheque.remaining_functional = Decimal("0.00")
                elif previous_status in [ChequeStatus.IN_PORTFOLIO, ChequeStatus.UNDER_COLLECTION]:
                    cheque.collected_amount = Decimal("0.00")
                    cheque.remaining_amount = cheque.amount
                    cheque.remaining_functional = cheque.compute_remaining_functional()
                elif previous_status == ChequeStatus.PARTIALLY_COLLECTED:
                    cheque.remaining_amount = max(Decimal("0.00"), cheque.amount - cheque.collected_amount)
                    cheque.remaining_functional = cheque.compute_remaining_functional()

            # 5. استعادة الحالة السابقة
            previous_status = target_log.from_status
            cheque.status = previous_status
            cheque.save()

            # 6. تسجيل حركة العكس الجديدة
            reversal_log = ChequeActionLog.objects.create(
                cheque=cheque,
                action=ChequeActionType.REVERSE_ACTION,
                from_status=target_log.to_status,
                to_status=previous_status,
                action_date=timezone.now().date(),
                idempotency_key=idempotency_key,
                amount_processed=target_log.amount_processed,
                bank_charges=target_log.bank_charges,
                journal_entry=reversal_entry,
                reason=f"تراجع عن حركة {target_log.get_action_display()}: {reason}",
                created_by=user,
            )

            # 7. وسم الحركة كمعكوسة وربطها بحركة العكس
            target_log.is_reversed = True
            target_log.reversed_by_log = reversal_log
            target_log.save(update_fields=["is_reversed", "reversed_by_log"])

            logger.info(f"Reversed action #{target_log.id} on Cheque #{cheque.id}. Reverted to status: {previous_status}")
            return {
                "cheque": cheque,
                "reversed_action_log": target_log,
                "reversal_log": reversal_log,
                "reversal_entry": reversal_entry,
            }
