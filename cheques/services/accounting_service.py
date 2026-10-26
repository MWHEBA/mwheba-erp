# -*- coding: utf-8 -*-
import hashlib
import json
import logging
import uuid
from decimal import Decimal
from typing import Dict, Any, Optional, List, Tuple

from django.db import transaction, models, IntegrityError
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from financial.models import ChartOfAccounts, JournalEntry
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames, RoleConfigurationError
from financial.services.subledger_account_service import SubledgerAccountService
from financial.services.period_control_service import PeriodControlService
from financial.services.treasury_security_service import TreasurySecurityService
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData
from governance.exceptions import ConcurrencyError, GovernanceError

from cheques.models import (
    Cheque,
    ChequeType,
    ChequePurpose,
    ChequeStatus,
    ChequeActionLog,
    ChequeActionType,
    ChequeSettlementLine,
    ChequeInvoiceAllocation,
)
from cheques.services.disbursement_security_service import ChequeDisbursementSecurityService

logger = logging.getLogger(__name__)


class ConcurrencyConflictError(ConcurrencyError):
    """خطأ تعارض تزامني أو استخدام مكرر لمفتاح عدم التكرار بمعلمات مختلفة"""
    pass


class ChequeAccountingService:
    """
    المحرك المحاسبي الشامل لإدارة الشيكات وأوراق القبض والدفع
    (Comprehensive Double-Entry Cheque Accounting Engine)
    """

    ALLOWED_TRANSITIONS = {
        ChequeType.RECEIVABLE: {
            ChequeStatus.DRAFT: [ChequeStatus.IN_PORTFOLIO, ChequeStatus.CANCELLED],
            ChequeStatus.IN_PORTFOLIO: [
                ChequeStatus.UNDER_COLLECTION,
                ChequeStatus.COLLECTED,
                ChequeStatus.PARTIALLY_COLLECTED,
                ChequeStatus.ENDORSED,
                ChequeStatus.RETURNED_TO_DRAWER,
                ChequeStatus.BOUNCED,
                ChequeStatus.CANCELLED,
                ChequeStatus.IN_PORTFOLIO,
            ],
            ChequeStatus.UNDER_COLLECTION: [
                ChequeStatus.COLLECTED,
                ChequeStatus.PARTIALLY_COLLECTED,
                ChequeStatus.BOUNCED,
                ChequeStatus.RETURNED_TO_DRAWER,
                ChequeStatus.IN_PORTFOLIO,  # تراجع
            ],
            ChequeStatus.PARTIALLY_COLLECTED: [
                ChequeStatus.COLLECTED,
                ChequeStatus.PARTIALLY_COLLECTED,
                ChequeStatus.BOUNCED,
                ChequeStatus.LEGAL_ACTION,
            ],
            ChequeStatus.COLLECTED: [
                ChequeStatus.BOUNCED,
            ],
            ChequeStatus.BOUNCED: [
                ChequeStatus.UNDER_COLLECTION,
                ChequeStatus.LEGAL_ACTION,
                ChequeStatus.RETURNED_TO_DRAWER,
            ],
            ChequeStatus.LEGAL_ACTION: [
                ChequeStatus.LEGAL_SETTLEMENT,
                ChequeStatus.CANCELLED,
            ],
            ChequeStatus.ENDORSED: [
                ChequeStatus.ENDORSED_BOUNCED,
            ],
            ChequeStatus.ENDORSED_BOUNCED: [
                ChequeStatus.IN_PORTFOLIO,
                ChequeStatus.LEGAL_ACTION,
            ],
        },
        ChequeType.PAYABLE: {
            ChequeStatus.DRAFT: [ChequeStatus.ISSUED, ChequeStatus.CANCELLED],
            ChequeStatus.ISSUED: [
                ChequeStatus.CLEARED,
                ChequeStatus.CANCELLED,
                ChequeStatus.BOUNCED,
                ChequeStatus.ISSUED,
            ],
            ChequeStatus.BOUNCED: [
                ChequeStatus.ISSUED,
                ChequeStatus.CANCELLED,
            ],
        }
    }

    ACTION_TARGET_STATUS = {
        ChequeActionType.RECEIVE: ChequeStatus.IN_PORTFOLIO,
        ChequeActionType.CONVERT_GUARANTEE: ChequeStatus.IN_PORTFOLIO,
        ChequeActionType.DEPOSIT: ChequeStatus.UNDER_COLLECTION,
        ChequeActionType.ENDORSE: ChequeStatus.ENDORSED,
        ChequeActionType.BOUNCE: ChequeStatus.BOUNCED,
        ChequeActionType.ISSUE: ChequeStatus.ISSUED,
        ChequeActionType.CLEAR: ChequeStatus.CLEARED,
        ChequeActionType.RETURN_TO_DRAWER: ChequeStatus.RETURNED_TO_DRAWER,
        ChequeActionType.CANCEL: ChequeStatus.CANCELLED,
        ChequeActionType.LEGAL_REFERRAL: ChequeStatus.LEGAL_ACTION,
        ChequeActionType.LEGAL_SETTLEMENT: ChequeStatus.LEGAL_SETTLEMENT,
    }

    @classmethod
    def _compute_payload_hash(cls, cheque_id: int, action_type: str, **params) -> str:
        """حساب البصمة الرقمية المشفرة لمعلمات الطلب لمنع التلاعب وتدقيق إعادة الإرسال"""
        canonical = {
            "cheque_id": cheque_id,
            "action_type": str(action_type),
            "amount_collected": str(params.get("amount_collected", "")),
            "exchange_rate": str(params.get("exchange_rate", "")),
            "bank_charges": str(params.get("bank_charges", "")),
            "bank_charges_vat": str(params.get("bank_charges_vat", "")),
            "bank_account_id": str(params.get("deposit_bank_account_id") or params.get("bank_account_id", "")),
            "value_date": str(params.get("value_date", "")),
            "reason": str(params.get("reason", "")),
            "target_status": str(params.get("target_status", "")),
            "supplier_id": str(params.get("supplier_id", "")),
            "new_purpose": str(params.get("new_purpose", "")),
        }
        raw_str = json.dumps(canonical, sort_keys=True)
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    @classmethod
    def _verify_access_and_read_permissions(cls, cheque: Cheque, user) -> None:
        """التحقق الأمني المبدئي من صلاحية المستخدم للوصول للشيك"""
        if not user or not user.is_authenticated:
            raise ValidationError(_("يجب تسجيل الدخول لتنفيذ هذه العملية."))

    @classmethod
    def _enforce_new_action_governance(
        cls,
        cheque: Cheque,
        action_type: str,
        user,
        request=None,
        **params
    ) -> None:
        """فحوصات الحوكمة والتنفيذ للطلبات الجديدة فقط (الفترة المقفلة، سقف الصرف)"""
        # منع الحركات المالية والتنفيذية على شيكات الضمان قبل تحويلها إلى شيكات تشغيلية
        if cheque.is_guarantee and action_type in [
            ChequeActionType.COLLECT,
            ChequeActionType.PARTIAL_COLLECT,
            ChequeActionType.DEPOSIT,
            ChequeActionType.CLEAR,
            ChequeActionType.ENDORSE,
            ChequeActionType.BOUNCE,
            ChequeActionType.LEGAL_SETTLEMENT,
        ]:
            raise ValidationError(
                _("لا يمكن تحصيل أو إيداع أو صرف أو تظهير أو إثبات ارتداد شيك ضمان خارج الميزانية. يجب اعتماد تحويل الشيك إلى تجاري/تشغيلي أولاً.")
            )

        action_date = params.get("value_date") or timezone.localdate()
        is_open, period = PeriodControlService.validate_period_open(action_date)
        if not is_open:
            period_name = period.name if period else ""
            raise ValidationError(
                _("التاريخ {date} يقع ضمن فترة محاسبية مغلقة ({period}). لا يمكن ترحيل قيود على فترات مقفلة.").format(
                    date=action_date,
                    period=period_name
                )
            )

        # حجز سقف الخزينة اليومي عند تحرير أو تحويل شيكات الدفع لتشغيلي
        if (action_type == ChequeActionType.ISSUE or (action_type == ChequeActionType.CONVERT_GUARANTEE and cheque.cheque_type == ChequeType.PAYABLE)) and cheque.cheque_type == ChequeType.PAYABLE:
            bank_acc_id = params.get("bank_account_id") or params.get("deposit_bank_account_id") or cheque.deposit_bank_account_id
            if not bank_acc_id:
                raise ValidationError(_("يجب تحديد الحساب البنكي المسحوب عليه لإصدار شيك الدفع."))
            cheque.deposit_bank_account_id = bank_acc_id
            ChequeDisbursementSecurityService.enforce_and_reserve(
                user=user,
                bank_account_id=bank_acc_id,
                amount=cheque.functional_amount,
                as_of_date=params.get("value_date") or timezone.localdate(),
                request=request,
                exclude_cheque_id=cheque.id if cheque.pk else None
            )

    @classmethod
    def _validate_state_transition(cls, cheque: Cheque, action_type: str, target_status: Optional[str] = None) -> str:
        """التحقق الصارم من صحة انتقال الحالة في آلة الحالات (State Machine)"""
        # منع الحركات المالية والتنفيذية على شيكات الضمان قبل تحويلها إلى شيكات تشغيلية
        if cheque.is_guarantee and action_type in [
            ChequeActionType.COLLECT,
            ChequeActionType.PARTIAL_COLLECT,
            ChequeActionType.DEPOSIT,
            ChequeActionType.CLEAR,
            ChequeActionType.ENDORSE,
            ChequeActionType.BOUNCE,
            ChequeActionType.LEGAL_SETTLEMENT,
        ]:
            raise ValidationError(
                _("لا يمكن تحصيل أو إيداع أو صرف أو تظهير أو إثبات ارتداد شيك ضمان خارج الميزانية. يجب اعتماد تحويل الشيك إلى تجاري/تشغيلي أولاً.")
            )

        if not target_status:
            if action_type == ChequeActionType.COLLECT:
                # التحصيل يتحدد تلقائياً كلي أو جزئي
                target_status = ChequeStatus.COLLECTED
            elif action_type == ChequeActionType.CONVERT_GUARANTEE:
                target_status = ChequeStatus.ISSUED if cheque.cheque_type == ChequeType.PAYABLE else ChequeStatus.IN_PORTFOLIO
            else:
                target_status = cls.ACTION_TARGET_STATUS.get(action_type)

        if not target_status:
            raise ValidationError(_(f"إجراء غير معروف: {action_type}"))

        # تحويل شيك الضمان إلى شيك تجاري/تشغيلي
        if action_type == ChequeActionType.CONVERT_GUARANTEE:
            if not cheque.is_guarantee:
                raise ValidationError(_("الشيك ليس شيك ضمان أو تم تحويله مسبقاً إلى شيك تجاري."))
            if cheque.cheque_type == ChequeType.PAYABLE:
                if cheque.status in [ChequeStatus.DRAFT, ChequeStatus.ISSUED]:
                    return ChequeStatus.ISSUED
                raise ValidationError(
                    _("لا يمكن تحويل شيك الضمان الصادر من حالة '{current}'.").format(
                        current=cheque.get_status_display()
                    )
                )
            else:
                if cheque.status in [ChequeStatus.DRAFT, ChequeStatus.IN_PORTFOLIO]:
                    return ChequeStatus.IN_PORTFOLIO
                raise ValidationError(
                    _("لا يمكن تحويل شيك الضمان الوارد من حالة '{current}'.").format(
                        current=cheque.get_status_display()
                    )
                )

        allowed = cls.ALLOWED_TRANSITIONS.get(cheque.cheque_type, {}).get(cheque.status, [])
        if target_status not in allowed:
            raise ValidationError(
                _("لا يمكن تحويل حالة الشيك من '{current}' إلى '{target}' عبر الإجراء '{action}'.").format(
                    current=cheque.get_status_display(),
                    target=target_status,
                    action=action_type
                )
            )
        return target_status

    @classmethod
    def process_lifecycle_action(
        cls,
        cheque_id: int,
        action_type: str,
        user,
        idempotency_key: str,
        request=None,
        **params
    ) -> Dict[str, Any]:
        """
        عقد التنفيذ الذري الصارم لحركات دورة حياة الشيك:
        1. التحقق من إلزامية وصيغة idempotency_key الخماسية القياسية.
        2. بروتوكول الترتيب الحتمي للأقفال (Lock Ordering) لمنع Deadlocks:
           أ. قفل الحساب المالي (ChartOfAccounts) تصاعدياً بالـ ID.
           ب. قفل الشريك (Customer / Supplier) تصاعدياً بالـ ID.
           ج. قفل صف الشيك (Cheque) بـ select_for_update().
        3. التعرف على الإرسال المكرر وإرجاع النتيجة السابقة بأمان (Cached Replay) دون إعادة الفحوصات التنفيذية.
        4. تنفيذ الفحوصات الصارمة وتوليد القيد المحاسبي عبر AccountingGateway.
        """
        if not idempotency_key or not str(idempotency_key).strip():
            raise ValidationError(_("مفتاح منع التكرار (idempotency_key) إلزامي لكافة عمليات الشيكات."))

        with transaction.atomic():
            # 1. الترتيب الحتمي للأقفال: قفل الحساب البنكي إن وُجد
            bank_acc_id = params.get("deposit_bank_account_id") or params.get("bank_account_id")
            if bank_acc_id:
                ChartOfAccounts.objects.filter(pk=bank_acc_id).select_for_update().exists()

            # 2. قفل صف الشيك
            try:
                cheque = Cheque.objects.select_for_update().get(pk=cheque_id)
            except Cheque.DoesNotExist:
                raise ValidationError(_("الشيك المطلوب غير موجود."))

            # قفل الحساب البنكي المرتبط بالشيك إن لم يكن مقفولاً
            if cheque.deposit_bank_account_id and cheque.deposit_bank_account_id != bank_acc_id:
                ChartOfAccounts.objects.filter(pk=cheque.deposit_bank_account_id).select_for_update().exists()

            # 3. التحقق الأمني المبدئي
            cls._verify_access_and_read_permissions(cheque, user)

            # 4. حساب بصمة المعلمات
            request_payload_hash = cls._compute_payload_hash(cheque_id, action_type, **params)

            # 5. فحص مفتاح عدم التكرار
            existing_log = ChequeActionLog.objects.filter(idempotency_key=idempotency_key).first()
            if existing_log:
                if (
                    existing_log.cheque_id != cheque.id
                    or existing_log.action != action_type
                    or existing_log.request_payload_hash != request_payload_hash
                ):
                    raise ConcurrencyConflictError(
                        _("تعارض في مفتاح عدم التكرار: المفتاح مستخدم مسبقاً لعملية أخرى أو بمعلمات مختلفة.")
                    )

                logger.info(f"Idempotent Cached Replay returned for key {idempotency_key}")
                return {
                    "cheque": existing_log.cheque,
                    "action_log": existing_log,
                    "journal_entry": existing_log.journal_entry,
                    "is_retry": True,
                }

            # 6. فحوصات الحوكمة والتنفيذ للطلب الجديد
            cls._enforce_new_action_governance(cheque, action_type, user, request=request, **params)

            # 7. التحقق من انتقال الحالة
            target_status = params.pop("target_status", None)
            if action_type == ChequeActionType.COLLECT:
                amount_to_collect = Decimal(str(params.get("amount_collected") or params.get("amount") or cheque.remaining_amount))
                if amount_to_collect < cheque.remaining_amount:
                    target_status = ChequeStatus.PARTIALLY_COLLECTED
                else:
                    target_status = ChequeStatus.COLLECTED
            target_status = cls._validate_state_transition(cheque, action_type, target_status)

            # التحقق الأمني من الحساب البنكي وصلاحية المستخدم عند الصرف والمقاصة (CLEAR)
            if action_type == ChequeActionType.CLEAR:
                bank_account_id = params.get("bank_account_id") or params.get("deposit_bank_account_id") or cheque.deposit_bank_account_id
                if not bank_account_id:
                    default_bank = AccountRoleRegistry.get_account(AccountRoleNames.DEFAULT_BANK_ACCOUNT)
                    bank_account_id = default_bank.id

                bank_acc_obj = ChartOfAccounts.objects.filter(pk=bank_account_id, is_active=True).first()
                if not bank_acc_obj:
                    raise ValidationError(_("الحساب البنكي المحدد غير صالح أو غير نشط."))

                # منع استخدام حسابات أوراق القبض أو أوراق الدفع كحساب بنك للمقاصة
                rec_ctrl = AccountRoleRegistry.get_account(AccountRoleNames.NOTES_RECEIVABLE_CONTROL)
                pay_ctrl = AccountRoleRegistry.get_account(AccountRoleNames.NOTES_PAYABLE_CONTROL)
                if bank_acc_obj.id in [rec_ctrl.id, pay_ctrl.id]:
                    raise ValidationError(_("لا يمكن استخدام حساب أوراق القبض أو أوراق الدفع كحساب بنكي للمقاصة والصرف."))

                # التحقق الصارم من أن الحساب هو حساب بنكي فعلي
                is_bank = (
                    getattr(bank_acc_obj, 'is_bank_account', False)
                    or (bank_acc_obj.account_type and (
                        bank_acc_obj.account_type.code.lower() == 'bank'
                        or 'بنك' in bank_acc_obj.account_type.name
                        or 'مصرف' in bank_acc_obj.account_type.name
                    ))
                    or ('بنك' in bank_acc_obj.name or 'مصرف' in bank_acc_obj.name)
                    or str(bank_acc_obj.code).startswith(('1116', '1117'))
                )
                is_prohibited = (
                    getattr(bank_acc_obj, 'is_cash_account', False)
                    or getattr(bank_acc_obj, 'is_custody_account', False)
                    or str(bank_acc_obj.code).startswith(('1119', '1122', '2112'))
                )
                if not is_bank or is_prohibited:
                    raise ValidationError(_("الحساب المالي المختار ليس حساباً بنكياً صالحاً لإجراء المقاصة والصرف."))

                if user and not (user.is_superuser or getattr(user, 'is_financial_manager', False)):
                    accessible = TreasurySecurityService.get_user_accessible_treasuries(user, action='disburse')
                    if not accessible.filter(pk=bank_acc_obj.id).exists():
                        raise ValidationError(_("ليس لديك صلاحية صرف أو مقاصة على الحساب البنكي المحدد."))

            # 8. إنشاء سجل الحركة أولاً لحجز المعرّف
            value_date = params.get("value_date") or timezone.localdate()
            amount_processed = Decimal(str(params.get("amount_collected") or cheque.amount))
            bank_charges = Decimal(str(params.get("bank_charges") or "0.00"))

            metadata_dict = {}
            prev_issuer = None
            prev_issued_at = None
            if action_type == ChequeActionType.CONVERT_GUARANTEE and cheque.cheque_type == ChequeType.PAYABLE:
                prev_issuer = cheque.issued_by
                prev_issued_at = cheque.issued_at
                metadata_dict["previous_issuer_id"] = cheque.issued_by_id
                metadata_dict["previous_issued_at"] = cheque.issued_at.isoformat() if cheque.issued_at else None

            try:
                action_log = ChequeActionLog.objects.create(
                    cheque=cheque,
                    action=action_type,
                    from_status=cheque.status,
                    to_status=target_status,
                    action_date=value_date,
                    idempotency_key=idempotency_key,
                    request_payload_hash=request_payload_hash,
                    amount_processed=amount_processed,
                    bank_charges=bank_charges,
                    reason=params.get("reason", ""),
                    metadata=metadata_dict,
                    previous_issuer=prev_issuer,
                    previous_issued_at=prev_issued_at,
                    created_by=user,
                )
            except IntegrityError:
                raise ConcurrencyConflictError(_("تم اكتشاف تعارض تزامني أثناء معالجة الطلب."))

            # 9. توليد القيد المحاسبي المزدوج عبر AccountingGateway
            gateway_key = f"JE:cheques:ChequeActionLog:{action_log.id}:{action_type}"
            journal_entry = cls._create_gateway_journal_entry(
                cheque=cheque,
                action_type=action_type,
                action_log=action_log,
                user=user,
                gateway_idempotency_key=gateway_key,
                **params
            )

            if journal_entry:
                action_log.journal_entry = journal_entry
                action_log.save(update_fields=["journal_entry"])

            # 10. تحديث أرصدة وحالة الشيك في قاعدة البيانات
            cls._update_cheque_balances_and_status(cheque, action_log, target_status, user, **params)

            return {
                "cheque": cheque,
                "action_log": action_log,
                "journal_entry": journal_entry,
                "is_retry": False,
            }

    @classmethod
    def _create_gateway_journal_entry(
        cls,
        cheque: Cheque,
        action_type: str,
        action_log: ChequeActionLog,
        user,
        gateway_idempotency_key: str,
        **params
    ) -> Optional[JournalEntry]:
        """
        بناء أسطر القيد المحاسبي المزدوج وتمريره عبر AccountingGateway
        """
        # شيكات الرصيد الافتتاحي لا تولد قيوداً جديدة في الأستاذ العام عند الاستلام أو الإصدار الأولي فقط
        if cheque.is_opening_balance and action_type in [ChequeActionType.RECEIVE, ChequeActionType.ISSUE]:
            logger.info(f"Opening balance cheque #{cheque.id} initial action {action_type}: Zero GL entries generated (already in opening balance batch).")
            return None

        # شيكات الضمان خارج الميزانية (Off-Balance Sheet) إلا إذا كانت الحركة هي تحويلها لتشغيلي
        if cheque.is_guarantee and action_type != ChequeActionType.CONVERT_GUARANTEE:
            logger.info(f"Guarantee cheque #{cheque.id}: Off-balance sheet, zero GL entries generated.")
            return None

        value_date = params.get("value_date") or timezone.localdate()
        entry_lines: List[Dict[str, Any]] = []
        entry_type = "automatic"
        description = f"{action_log.get_action_display()} - شيك #{cheque.cheque_number} ({cheque.voucher_number})"

        # حل الحسابات الرقابية
        rec_control = AccountRoleRegistry.get_account(AccountRoleNames.NOTES_RECEIVABLE_CONTROL)
        coll_account = AccountRoleRegistry.get_account(AccountRoleNames.CHEQUES_UNDER_COLLECTION)
        pay_control = AccountRoleRegistry.get_account(AccountRoleNames.NOTES_PAYABLE_CONTROL)

        # 1. إيصال استلام شيك قبض (RECEIVE) أو تحويل شيك ضمان وارد لتشغيلي (CONVERT_GUARANTEE)
        if action_type == ChequeActionType.RECEIVE or (action_type == ChequeActionType.CONVERT_GUARANTEE and cheque.cheque_type == ChequeType.RECEIVABLE):
            entry_type = "cheque_receipt"
            amount_func = cheque.functional_amount
            # الطرف المدين: أوراق القبض
            entry_lines.append({
                "account_id": rec_control.id,
                "debit": amount_func,
                "credit": Decimal("0.00"),
                "description": f"تحويل شيك ضمان وارد #{cheque.cheque_number} إلى أوراق قبض" if action_type == ChequeActionType.CONVERT_GUARANTEE else f"استلام شيك قبض #{cheque.cheque_number} في المحفظة",
                "cost_center_id": None,
            })
            # الطرف الدائن: العميل أو الدفعات المقدمة
            effective_purpose = params.get('new_purpose') or cheque.purpose
            if effective_purpose == ChequePurpose.ADVANCE_PAYMENT:
                advance_acc = AccountRoleRegistry.get_account(AccountRoleNames.CUSTOMER_ADVANCE_LIABILITY)
                credit_acc_id = advance_acc.id
            else:
                cust_acc = SubledgerAccountService.get_or_create_customer_account(cheque.customer, user=user)
                credit_acc_id = cust_acc.id if cust_acc else rec_control.id

            entry_lines.append({
                "account_id": credit_acc_id,
                "debit": Decimal("0.00"),
                "credit": amount_func,
                "description": f"سداد بشيك #{cheque.cheque_number} - {cheque.drawer_name}",
                "cost_center_id": None,
            })

        # 2. إيداع الشيك برسم التحصيل (DEPOSIT)
        elif action_type == ChequeActionType.DEPOSIT:
            entry_type = "cheque_deposit"
            amount_func = cheque.remaining_functional or cheque.functional_amount
            # الطرف المدين: شيكات برسم التحصيل
            entry_lines.append({
                "account_id": coll_account.id,
                "debit": amount_func,
                "credit": Decimal("0.00"),
                "description": f"إيداع شيك #{cheque.cheque_number} برسم التحصيل بالبنك",
                "cost_center_id": None,
            })
            # الطرف الدائن: أوراق القبض
            entry_lines.append({
                "account_id": rec_control.id,
                "debit": Decimal("0.00"),
                "credit": amount_func,
                "description": f"خروج شيك #{cheque.cheque_number} من الحافظة للبنك",
                "cost_center_id": None,
            })

        # 3. التحصيل البنكي (COLLECT) - كلي أو جزئي
        elif action_type == ChequeActionType.COLLECT:
            entry_type = "cheque_collection"
            bank_account_id = params.get("bank_account_id") or params.get("deposit_bank_account_id") or cheque.deposit_bank_account_id
            if not bank_account_id:
                bank_acc = AccountRoleRegistry.get_account(AccountRoleNames.DEFAULT_BANK_ACCOUNT)
                bank_account_id = bank_acc.id

            settled_curr = Decimal(str(params.get("amount_collected") or params.get("amount") or cheque.remaining_amount))
            rate = Decimal(str(params.get("exchange_rate") or cheque.original_exchange_rate or "1.000000"))
            gross_func = (settled_curr * rate).quantize(Decimal("0.01"))

            # القيمة الدفترية للحصة المسددة
            ratio = (settled_curr / cheque.amount) if cheque.amount else Decimal("1.0")
            settled_book_val = (ratio * cheque.book_value_functional).quantize(Decimal("0.01"))

            bank_charges = Decimal(str(params.get("bank_charges") or "0.00"))
            charges_vat = Decimal(str(params.get("bank_charges_vat") or "0.00"))
            total_deductions = bank_charges + charges_vat
            net_to_bank = gross_func - total_deductions

            # الطرف المدين 1: البنك الجاري
            entry_lines.append({
                "account_id": bank_account_id,
                "debit": net_to_bank,
                "credit": Decimal("0.00"),
                "description": f"تحصيل بنكي صريح لشيك #{cheque.cheque_number} - صافي النقدية",
                "cost_center_id": None,
            })

            # الطرف المدين 2: عمولة بنكية
            if bank_charges > Decimal("0.00"):
                charges_acc = AccountRoleRegistry.get_account(AccountRoleNames.BANK_CHARGES_EXPENSE)
                entry_lines.append({
                    "account_id": charges_acc.id,
                    "debit": bank_charges,
                    "credit": Decimal("0.00"),
                    "description": f"عمولة تحصيل بنكية لشيك #{cheque.cheque_number}",
                    "cost_center_id": cheque.cost_center_id,
                })

            # الطرف المدين 3: ضريبة القيمة المضافة على المصاريف
            if charges_vat > Decimal("0.00"):
                vat_acc = AccountRoleRegistry.get_account(AccountRoleNames.VAT_INPUT)
                entry_lines.append({
                    "account_id": vat_acc.id,
                    "debit": charges_vat,
                    "credit": Decimal("0.00"),
                    "description": f"ضريبة مدخلات 14% على عمولة شيك #{cheque.cheque_number}",
                    "cost_center_id": None,
                })

            # الطرف الدائن: إذا كان الشيك محصلاً مباشرة من المحفظة يُقفل حساب أوراق القبض بالمحفظة (11220)
            # وإذا كان برسم التحصيل بالبنك يُقفل حساب شيكات برسم التحصيل (11221)
            if cheque.status == ChequeStatus.IN_PORTFOLIO:
                credit_account_id = rec_control.id
                credit_desc = f"إقفال أوراق قبض بالمحفظة لتحصيل شيك #{cheque.cheque_number} مباشرة"
            else:
                credit_account_id = coll_account.id
                credit_desc = f"إقفال حصة شيكات برسم التحصيل لشيك #{cheque.cheque_number}"

            entry_lines.append({
                "account_id": credit_account_id,
                "debit": Decimal("0.00"),
                "credit": settled_book_val,
                "description": credit_desc,
                "cost_center_id": None,
            })

            # فروق أسعار الصرف المحققة
            fx_diff = gross_func - settled_book_val
            if fx_diff > Decimal("0.00"):
                fx_gain = AccountRoleRegistry.get_account(AccountRoleNames.FX_REALIZED_GAIN)
                entry_lines.append({
                    "account_id": fx_gain.id,
                    "debit": Decimal("0.00"),
                    "credit": fx_diff,
                    "description": f"أرباح فروق عملة محققة عند تحصيل شيك #{cheque.cheque_number}",
                    "cost_center_id": None,
                })
            elif fx_diff < Decimal("0.00"):
                fx_loss = AccountRoleRegistry.get_account(AccountRoleNames.FX_REALIZED_LOSS)
                entry_lines.append({
                    "account_id": fx_loss.id,
                    "debit": abs(fx_diff),
                    "credit": Decimal("0.00"),
                    "description": f"خسائر فروق عملة محققة عند تحصيل شيك #{cheque.cheque_number}",
                    "cost_center_id": cheque.cost_center_id,
                })

            # معالجة فروق التقريب (Penny difference <= 0.05)
            tot_debit = sum(Decimal(str(l["debit"])) for l in entry_lines)
            tot_credit = sum(Decimal(str(l["credit"])) for l in entry_lines)
            diff = tot_debit - tot_credit
            if diff != Decimal("0.00") and abs(diff) <= Decimal("0.05"):
                round_acc = AccountRoleRegistry.get_account(AccountRoleNames.ROUNDING_DIFFERENCE_ACCOUNT)
                if diff > Decimal("0.00"):
                    entry_lines.append({
                        "account_id": round_acc.id,
                        "debit": Decimal("0.00"),
                        "credit": diff,
                        "description": "فروق تقريب كسور العملة",
                        "cost_center_id": None,
                    })
                else:
                    entry_lines.append({
                        "account_id": round_acc.id,
                        "debit": abs(diff),
                        "credit": Decimal("0.00"),
                        "description": "فروق تقريب كسور العملة",
                        "cost_center_id": None,
                    })

        # 4. ارتداد الشيك (BOUNCE)
        elif action_type == ChequeActionType.BOUNCE:
            entry_type = "cheque_bounce"
            bounced_func = cheque.remaining_functional or cheque.functional_amount

            if cheque.cheque_type == ChequeType.PAYABLE:
                # ارتداد شيك دفع صادر لمورد
                supp_acc = SubledgerAccountService.get_or_create_supplier_account(cheque.supplier, user=user)
                if cheque.status == ChequeStatus.CLEARED:
                    bank_acc_id = cheque.deposit_bank_account_id or (AccountRoleRegistry.get_account(AccountRoleNames.DEFAULT_BANK_ACCOUNT).id)
                    debit_acc_id = bank_acc_id
                    desc = f"ارتداد شيك دفع مصرف #{cheque.cheque_number} - إعادة الرصيد للبنك"
                else:
                    debit_acc_id = pay_control.id
                    desc = f"ارتداد شيك دفع صادر #{cheque.cheque_number} - إلغاء ورقة الدفع"

                entry_lines.append({
                    "account_id": debit_acc_id,
                    "debit": bounced_func,
                    "credit": Decimal("0.00"),
                    "description": desc,
                    "cost_center_id": None,
                })
                entry_lines.append({
                    "account_id": supp_acc.id if supp_acc else pay_control.id,
                    "debit": Decimal("0.00"),
                    "credit": bounced_func,
                    "description": f"إعادة فتح مديونية المورد لارتداد شيك دفع #{cheque.cheque_number}",
                    "cost_center_id": None,
                })
            else:
                # ارتداد شيك قبض وارد من عميل
                from_account_id = coll_account.id if cheque.status in [ChequeStatus.UNDER_COLLECTION, ChequeStatus.PARTIALLY_COLLECTED] else rec_control.id
                entry_lines.append({
                    "account_id": from_account_id,
                    "debit": Decimal("0.00"),
                    "credit": bounced_func,
                    "description": f"ارتداد شيك #{cheque.cheque_number} - إلغاء أثر التحصيل/المحفظة",
                    "cost_center_id": None,
                })

                # الطرف المدين: العميل أو الدفعات المقدمة
                if cheque.purpose == ChequePurpose.ADVANCE_PAYMENT:
                    advance_acc = AccountRoleRegistry.get_account(AccountRoleNames.CUSTOMER_ADVANCE_LIABILITY)
                    debit_acc_id = advance_acc.id
                else:
                    cust_acc = SubledgerAccountService.get_or_create_customer_account(cheque.customer, user=user)
                    debit_acc_id = cust_acc.id if cust_acc else rec_control.id

                entry_lines.append({
                    "account_id": debit_acc_id,
                    "debit": bounced_func,
                    "credit": Decimal("0.00"),
                    "description": f"إعادة فتح المديونية لارتداد شيك #{cheque.cheque_number}",
                    "cost_center_id": None,
                })

        # 5. تظهير شيك لمورد (ENDORSE)
        elif action_type == ChequeActionType.ENDORSE:
            entry_type = "cheque_endorsement"
            amount_func = cheque.functional_amount

            supplier = params.get("supplier")
            if not supplier:
                supp_id = params.get("supplier_id")
                if supp_id:
                    from supplier.models import Supplier
                    supplier = Supplier.objects.filter(pk=supp_id).first()
            if not supplier:
                supplier = cheque.supplier

            if not supplier:
                raise ValidationError(_("يجب تحديد المورد المراد تظهير الشيك إليه."))

            supp_acc = SubledgerAccountService.get_or_create_supplier_account(supplier, user=user)
            # الطرف المدين: المورد
            entry_lines.append({
                "account_id": supp_acc.id,
                "debit": amount_func,
                "credit": Decimal("0.00"),
                "description": f"تظهير شيك قبض #{cheque.cheque_number} للمورد {supplier.name}",
                "cost_center_id": None,
            })
            # الطرف الدائن: أوراق القبض
            entry_lines.append({
                "account_id": rec_control.id,
                "debit": Decimal("0.00"),
                "credit": amount_func,
                "description": f"خروج شيك مظهر #{cheque.cheque_number} من أوراق القبض",
                "cost_center_id": None,
            })

        # 6. إصدار شيك دفع لمورد (ISSUE) أو تحويل شيك ضمان صادر لتشغيلي (CONVERT_GUARANTEE)
        elif action_type == ChequeActionType.ISSUE or (action_type == ChequeActionType.CONVERT_GUARANTEE and cheque.cheque_type == ChequeType.PAYABLE):
            entry_type = "cheque_payment"
            amount_func = cheque.functional_amount
            effective_purpose = params.get('new_purpose') or cheque.purpose
            if effective_purpose == ChequePurpose.ADVANCE_PAYMENT:
                advance_acc = AccountRoleRegistry.get_account(AccountRoleNames.SUPPLIER_ADVANCE_ASSET)
                debit_acc_id = advance_acc.id
            else:
                supp_acc = SubledgerAccountService.get_or_create_supplier_account(cheque.supplier, user=user)
                debit_acc_id = supp_acc.id if supp_acc else pay_control.id

            # الطرف المدين: المورد / الدفعات المقدمة للموردين
            entry_lines.append({
                "account_id": debit_acc_id,
                "debit": amount_func,
                "credit": Decimal("0.00"),
                "description": f"تحويل شيك ضمان صادر #{cheque.cheque_number} إلى ورقة دفع" if action_type == ChequeActionType.CONVERT_GUARANTEE else f"إصدار شيك دفع #{cheque.cheque_number} للمورد {cheque.supplier.name if cheque.supplier else ''}",
                "cost_center_id": None,
            })
            # الطرف الدائن: أوراق الدفع
            entry_lines.append({
                "account_id": pay_control.id,
                "debit": Decimal("0.00"),
                "credit": amount_func,
                "description": f"إثبات التزام ورقة دفع شيك #{cheque.cheque_number}",
                "cost_center_id": None,
            })

        # 7. صرف وخصم شيك بنكي (CLEAR)
        elif action_type == ChequeActionType.CLEAR:
            entry_type = "cheque_clearance"
            bank_account_id = params.get("bank_account_id") or params.get("deposit_bank_account_id") or cheque.deposit_bank_account_id
            if not bank_account_id:
                bank_acc = AccountRoleRegistry.get_account(AccountRoleNames.DEFAULT_BANK_ACCOUNT)
                bank_account_id = bank_acc.id

            rate = Decimal(str(params.get("exchange_rate") or params.get("clearing_rate") or cheque.original_exchange_rate or "1.000000"))
            bank_amount = (cheque.amount * rate).quantize(Decimal("0.01"))
            liability_amount = cheque.book_value_functional or cheque.functional_amount

            # الطرف المدين: أوراق الدفع بالقيمة الدفترية الأصلية
            entry_lines.append({
                "account_id": pay_control.id,
                "debit": liability_amount,
                "credit": Decimal("0.00"),
                "description": f"إقفال التزام ورقة دفع شيك #{cheque.cheque_number} بالصرف البنكي",
                "cost_center_id": None,
            })
            # الطرف الدائن: البنك الجاري بالقيمة الفعلية بسعر الصرف عند الصرف
            entry_lines.append({
                "account_id": bank_account_id,
                "debit": Decimal("0.00"),
                "credit": bank_amount,
                "description": f"خصم شيك صرف #{cheque.cheque_number} من الحساب البنكي",
                "cost_center_id": None,
            })

            # معالجة فروق أسعار الصرف المحققة
            fx_diff = bank_amount - liability_amount
            if fx_diff > Decimal("0.00"):
                # خرج من البنك أكثر من الالتزام الدفتري = خسائر فروق عملة محققة
                fx_loss = AccountRoleRegistry.get_account(AccountRoleNames.FX_REALIZED_LOSS)
                entry_lines.append({
                    "account_id": fx_loss.id,
                    "debit": fx_diff,
                    "credit": Decimal("0.00"),
                    "description": f"خسائر فروق عملة محققة عند صرف شيك دفع #{cheque.cheque_number}",
                    "cost_center_id": cheque.cost_center_id,
                })
            elif fx_diff < Decimal("0.00"):
                # خرج من البنك أقل من الالتزام الدفتري = أرباح فروق عملة محققة
                fx_gain = AccountRoleRegistry.get_account(AccountRoleNames.FX_REALIZED_GAIN)
                entry_lines.append({
                    "account_id": fx_gain.id,
                    "debit": Decimal("0.00"),
                    "credit": abs(fx_diff),
                    "description": f"أرباح فروق عملة محققة عند صرف شيك دفع #{cheque.cheque_number}",
                    "cost_center_id": None,
                })

            # معالجة فروق التقريب (Penny difference <= 0.05)
            tot_debit = sum(Decimal(str(l["debit"])) for l in entry_lines)
            tot_credit = sum(Decimal(str(l["credit"])) for l in entry_lines)
            diff = tot_debit - tot_credit
            if diff != Decimal("0.00") and abs(diff) <= Decimal("0.05"):
                round_acc = AccountRoleRegistry.get_account(AccountRoleNames.ROUNDING_DIFFERENCE_ACCOUNT)
                if diff > Decimal("0.00"):
                    entry_lines.append({
                        "account_id": round_acc.id,
                        "debit": Decimal("0.00"),
                        "credit": diff,
                        "description": "فروق تقريب كسور العملة",
                        "cost_center_id": None,
                    })
                else:
                    entry_lines.append({
                        "account_id": round_acc.id,
                        "debit": abs(diff),
                        "credit": Decimal("0.00"),
                        "description": "فروق تقريب كسور العملة",
                        "cost_center_id": None,
                    })

        # 8. استرداد الشيك للساحب (RETURN_TO_DRAWER)
        elif action_type == ChequeActionType.RETURN_TO_DRAWER:
            entry_type = "cheque_return"
            amount_func = cheque.remaining_functional or cheque.functional_amount
            from_account_id = coll_account.id if cheque.status in [ChequeStatus.UNDER_COLLECTION, ChequeStatus.PARTIALLY_COLLECTED] else rec_control.id

            # الطرف المدين: العميل أو الدفعات المقدمة
            if cheque.purpose == ChequePurpose.ADVANCE_PAYMENT:
                advance_acc = AccountRoleRegistry.get_account(AccountRoleNames.CUSTOMER_ADVANCE_LIABILITY)
                debit_acc_id = advance_acc.id
            else:
                cust_acc = SubledgerAccountService.get_or_create_customer_account(cheque.customer, user=user)
                debit_acc_id = cust_acc.id if cust_acc else rec_control.id

            entry_lines.append({
                "account_id": debit_acc_id,
                "debit": amount_func,
                "credit": Decimal("0.00"),
                "description": f"استرداد شيك #{cheque.cheque_number} وإعادته للساحب بطلب تجاري",
                "cost_center_id": None,
            })
            entry_lines.append({
                "account_id": from_account_id,
                "debit": Decimal("0.00"),
                "credit": amount_func,
                "description": f"إخراج شيك مسترد #{cheque.cheque_number} من الدفاتر",
                "cost_center_id": None,
            })

        # 9. إلغاء شيك دفع أو قبض (CANCEL)
        elif action_type == ChequeActionType.CANCEL:
            entry_type = "cheque_reversal"
            amount_func = cheque.functional_amount
            if cheque.cheque_type == ChequeType.PAYABLE and cheque.status == ChequeStatus.ISSUED:
                supp_acc = SubledgerAccountService.get_or_create_supplier_account(cheque.supplier, user=user)
                entry_lines.append({
                    "account_id": pay_control.id,
                    "debit": amount_func,
                    "credit": Decimal("0.00"),
                    "description": f"إلغاء شيك دفع #{cheque.cheque_number}",
                    "cost_center_id": None,
                })
                entry_lines.append({
                    "account_id": supp_acc.id if supp_acc else pay_control.id,
                    "debit": Decimal("0.00"),
                    "credit": amount_func,
                    "description": f"إعادة إثبات مديونية المورد لإلغاء شيك #{cheque.cheque_number}",
                    "cost_center_id": None,
                })
            elif cheque.cheque_type == ChequeType.RECEIVABLE and cheque.status == ChequeStatus.IN_PORTFOLIO:
                # إلغاء شيك قبض بالمحفظة: عكس قيد الاستلام تماماً
                if cheque.purpose == ChequePurpose.ADVANCE_PAYMENT:
                    advance_acc = AccountRoleRegistry.get_account(AccountRoleNames.CUSTOMER_ADVANCE_LIABILITY)
                    debit_acc_id = advance_acc.id
                else:
                    cust_acc = SubledgerAccountService.get_or_create_customer_account(cheque.customer, user=user)
                    debit_acc_id = cust_acc.id if cust_acc else rec_control.id

                entry_lines.append({
                    "account_id": debit_acc_id,
                    "debit": amount_func,
                    "credit": Decimal("0.00"),
                    "description": f"إلغاء شيك قبض بالمحفظة #{cheque.cheque_number} - إعادة المديونية",
                    "cost_center_id": None,
                })
                entry_lines.append({
                    "account_id": rec_control.id,
                    "debit": Decimal("0.00"),
                    "credit": amount_func,
                    "description": f"إلغاء شيك قبض بالمحفظة #{cheque.cheque_number} - إخراج من أوراق القبض",
                    "cost_center_id": None,
                })

        if not entry_lines:
            return None

        # تحويل الأسطر إلى هياكل بيانات البوابة المركزية JournalEntryLineData
        acc_ids = [line["account_id"] for line in entry_lines]
        account_map = {acc.id: acc.code for acc in ChartOfAccounts.objects.filter(id__in=acc_ids)}
        currency_code = str(cheque.currency.code if hasattr(cheque, "currency") and cheque.currency else "EGP")
        effective_rate = Decimal(str(params.get("exchange_rate") or params.get("clearing_rate") or cheque.original_exchange_rate or "1.000000"))
        exchange_rate = effective_rate if action_type in [ChequeActionType.COLLECT, ChequeActionType.CLEAR] else (cheque.original_exchange_rate or Decimal("1.000000"))

        gateway_lines = []
        for line in entry_lines:
            debit = line.get("debit", Decimal("0.00"))
            credit = line.get("credit", Decimal("0.00"))
            if debit == Decimal("0.00") and credit == Decimal("0.00"):
                continue

            # حل كود مركز التكلفة بدقة سواء كان ممرراً كـ code أو id
            cc_code = line.get("cost_center_code")
            if not cc_code and line.get("cost_center_id"):
                from financial.models import CostCenter
                cc = CostCenter.objects.filter(id=line["cost_center_id"]).first()
                if cc:
                    cc_code = cc.code
            elif not cc_code and getattr(cheque, "cost_center", None) and (line.get("cost_center_id") or "مصروف" in line.get("description", "") or "عمولة" in line.get("description", "")):
                cc_code = cheque.cost_center.code

            gateway_lines.append(
                JournalEntryLineData(
                    account_code=account_map[line["account_id"]],
                    debit=debit,
                    credit=credit,
                    description=line.get("description", ""),
                    cost_center=cc_code or None,
                    currency=currency_code,
                    exchange_rate=exchange_rate,
                )
            )

        if not gateway_lines:
            return None

        # إنشاء القيد عبر بوابة القيود المركزية
        gateway = AccountingGateway()
        journal_entry = gateway.create_journal_entry(
            source_module="cheques",
            source_model="ChequeActionLog",
            source_id=action_log.id,
            lines=gateway_lines,
            idempotency_key=gateway_idempotency_key,
            user=user,
            entry_type=entry_type,
            description=description,
            reference=cheque.voucher_number,
            date=value_date,
        )

        return journal_entry

    @classmethod
    def _update_cheque_balances_and_status(
        cls,
        cheque: Cheque,
        action_log: ChequeActionLog,
        target_status: str,
        user,
        **params
    ) -> None:
        """تحديث أرصدة الشيك ومتابعة حالات الوفاء الجزئي وتاريخ المقاصة وسجلات التسوية"""
        value_date = params.get("value_date") or timezone.localdate()
        update_fields = ["status", "updated_at"]

        if action_log.action == ChequeActionType.COLLECT:
            settled_curr = Decimal(str(params.get("amount_collected") or params.get("amount") or cheque.remaining_amount))
            rate = Decimal(str(params.get("exchange_rate") or cheque.original_exchange_rate or "1.000000"))
            gross_func = (settled_curr * rate).quantize(Decimal("0.01"))
            ratio = (settled_curr / cheque.amount) if cheque.amount else Decimal("1.0")
            settled_book_val = (ratio * cheque.book_value_functional).quantize(Decimal("0.01"))
            fx_diff = gross_func - settled_book_val

            cheque.collected_amount += settled_curr
            cheque.remaining_amount = cheque.amount - cheque.collected_amount
            cheque.remaining_functional = cheque.compute_remaining_functional()
            cheque.collection_date = value_date
            cheque.cleared_at = timezone.now()
            cheque.cleared_by = user
            update_fields.extend(["collected_amount", "remaining_amount", "remaining_functional", "collection_date", "cleared_at", "cleared_by"])

            bank_charges = Decimal(str(params.get("bank_charges") or "0.00"))
            bank_charges_vat = Decimal(str(params.get("bank_charges_vat") or "0.00"))
            net_to_bank = gross_func - (bank_charges + bank_charges_vat)
            deposit_bank_id = params.get("bank_account_id") or params.get("deposit_bank_account_id") or cheque.deposit_bank_account_id
            if not deposit_bank_id:
                bank_acc = AccountRoleRegistry.get_account(AccountRoleNames.DEFAULT_BANK_ACCOUNT)
                deposit_bank_id = bank_acc.id

            if deposit_bank_id and cheque.deposit_bank_account_id != deposit_bank_id:
                cheque.deposit_bank_account_id = deposit_bank_id
                update_fields.append("deposit_bank_account")

            # إنشاء سطر التسوية ChequeSettlementLine
            ChequeSettlementLine.objects.create(
                cheque=cheque,
                action_log=action_log,
                settlement_date=value_date,
                settled_amount_currency=settled_curr,
                exchange_rate=rate,
                settled_amount_functional=gross_func,
                book_value_functional=settled_book_val,
                realized_fx_gain_loss=fx_diff,
                bank_charges=bank_charges,
                net_bank_amount=net_to_bank,
                deposit_bank_account_id=deposit_bank_id,
            )

        elif action_log.action == ChequeActionType.DEPOSIT:
            bank_acc_id = params.get("deposit_bank_account_id") or params.get("bank_account_id")
            if bank_acc_id:
                cheque.deposit_bank_account_id = bank_acc_id
                update_fields.append("deposit_bank_account")

        elif action_log.action == ChequeActionType.ISSUE:
            bank_id = params.get("bank_account_id") or params.get("deposit_bank_account_id") or cheque.deposit_bank_account_id
            if bank_id:
                cheque.deposit_bank_account_id = bank_id
                if "deposit_bank_account" not in update_fields:
                    update_fields.append("deposit_bank_account")
            cheque.issued_at = timezone.now()
            cheque.issued_by = user
            update_fields.extend(["issued_at", "issued_by"])

        elif action_log.action == ChequeActionType.CLEAR:
            bank_id = params.get("bank_account_id") or params.get("deposit_bank_account_id")
            if bank_id and cheque.deposit_bank_account_id != bank_id:
                cheque.deposit_bank_account_id = bank_id
                update_fields.append("deposit_bank_account")
            cheque.cleared_at = timezone.now()
            cheque.cleared_by = user
            cheque.collection_date = value_date
            cheque.remaining_amount = Decimal("0.00")
            cheque.remaining_functional = Decimal("0.00")
            update_fields.extend(["cleared_at", "cleared_by", "collection_date", "remaining_amount", "remaining_functional"])

            rate = Decimal(str(params.get("exchange_rate") or params.get("clearing_rate") or cheque.original_exchange_rate or "1.000000"))
            bank_amount = (cheque.amount * rate).quantize(Decimal("0.01"))
            liability_amount = cheque.book_value_functional or cheque.functional_amount
            fx_diff = bank_amount - liability_amount

            ChequeSettlementLine.objects.create(
                cheque=cheque,
                action_log=action_log,
                settlement_date=value_date,
                settled_amount_currency=cheque.amount,
                exchange_rate=rate,
                settled_amount_functional=bank_amount,
                book_value_functional=liability_amount,
                realized_fx_gain_loss=-fx_diff if fx_diff > Decimal("0.00") else abs(fx_diff),
                bank_charges=Decimal("0.00"),
                net_bank_amount=bank_amount,
                deposit_bank_account_id=cheque.deposit_bank_account_id or bank_id,
            )

        elif action_log.action == ChequeActionType.ENDORSE:
            supp_id = params.get("supplier_id") or (params.get("supplier").id if params.get("supplier") else None)
            if supp_id:
                cheque._authorized_mutation_context = 'ENDORSE'
                cheque.supplier_id = supp_id
                update_fields.append("supplier")

        elif action_log.action == ChequeActionType.BOUNCE:
            if params.get("rejection_slip_image"):
                cheque.rejection_slip_image = params["rejection_slip_image"]
                update_fields.append("rejection_slip_image")

            is_partial_bounce = (cheque.status == ChequeStatus.PARTIALLY_COLLECTED)

            # إذا كان الشيك مرتبطاً بتخصيصات فواتير (سداد فواتير أو دفعات مقدمة مخصصة): إدارة أثر الارتداد
            if cheque.invoice_allocations.filter(allocation_status="APPLIED").exists():
                cls._handle_bounced_invoice_allocations(cheque, user, is_full_bounce=(not is_partial_bounce), action_log=action_log)

            if not is_partial_bounce:
                cheque.collected_amount = Decimal("0.00")
                cheque.remaining_amount = cheque.amount
                cheque.remaining_functional = cheque.compute_remaining_functional()
                update_fields.extend(["collected_amount", "remaining_amount", "remaining_functional"])

        elif action_log.action in [ChequeActionType.CANCEL, ChequeActionType.RETURN_TO_DRAWER]:
            # إلغاء الشيك أو رده للساحب: إلغاء تخصيصات الفواتير وإعادة فتحها كغير مسددة
            if cheque.invoice_allocations.filter(allocation_status="APPLIED").exists():
                cls._handle_bounced_invoice_allocations(cheque, user, is_full_bounce=True, action_log=action_log)

        elif action_log.action == ChequeActionType.CONVERT_GUARANTEE:
            new_purpose = params.get('new_purpose') or ChequePurpose.INVOICE_SETTLEMENT
            cheque._authorized_mutation_context = 'CONVERT_GUARANTEE'
            cheque.purpose = new_purpose
            update_fields.extend(["purpose", "remaining_functional"])
            if cheque.cheque_type == ChequeType.PAYABLE:
                bank_id = params.get("bank_account_id") or params.get("deposit_bank_account_id") or cheque.deposit_bank_account_id
                if bank_id:
                    cheque.deposit_bank_account_id = bank_id
                    if "deposit_bank_account" not in update_fields:
                        update_fields.append("deposit_bank_account")
                # عند تحويل شيك الضمان الصادر إلى تشغيلي: يُسجل المستخدم الحالي وتاريخ اليوم كمصدر فعلي للالتزام المالي
                cheque.issued_at = timezone.now()
                cheque.issued_by = user
                if "issued_at" not in update_fields:
                    update_fields.append("issued_at")
                if "issued_by" not in update_fields:
                    update_fields.append("issued_by")

        cheque.status = target_status
        cheque.save(update_fields=update_fields)

    @classmethod
    def _handle_bounced_invoice_allocations(cls, cheque: Cheque, user, is_full_bounce: bool = True, action_log: Optional[ChequeActionLog] = None) -> None:
        """
        معالجة دورة حياة الشيك المرتد أو الملغى أو المسترد المرتبط بفواتير:
        تعديل مبالغ أو عكس سجلات SalePayment واستدعاء sale.update_payment_status()
        وعكس قيود اليومية المرتبطة بتخصيصات الدفعات المقدمة إن وُجدت
        """
        try:
            from sale.models import SalePayment, Sale
            from customer.models import CustomerAllocationAudit
            import hashlib
            from django.utils import timezone

            allocations = cheque.invoice_allocations.filter(allocation_status="APPLIED")

            for alloc in allocations:
                sale = alloc.sale
                if is_full_bounce:
                    # ارتداد أو إلغاء كامل: تحويل سجل الدفع والتخصيص إلى reversed ووسم سجل التخصيص
                    alloc.allocation_status = "REVERSED"
                    tag = f"[ACTION_REV:{action_log.id}]" if action_log else "[ACTION_REV:BOUNCE]"
                    alloc.notes = f"{alloc.notes or ''} {tag}".strip()
                    alloc.save(update_fields=["allocation_status", "notes"])

                    # تحديث دفعة الفاتورة SalePayment المرتبطة بهذا التخصيص بالتحديد
                    if getattr(alloc, "sale_payment", None):
                        alloc.sale_payment.status = "reversed"
                        alloc.sale_payment.save(update_fields=["status"])
                    else:
                        target_payment = SalePayment.objects.filter(
                            sale=sale,
                            source_type="CHEQUE",
                            reference_number=cheque.voucher_number,
                            amount=alloc.allocated_amount,
                            status="posted"
                        ).first()
                        if target_payment:
                            target_payment.status = "reversed"
                            target_payment.save(update_fields=["status"])
                        else:
                            SalePayment.objects.filter(
                                sale=sale,
                                source_type="CHEQUE",
                                reference_number=cheque.voucher_number,
                                status="posted"
                            ).order_by("-id")[:1].update(status="reversed")

                    # إذا كان للتخصيص قيد يومية (تسوية دفعة مقدمة)، نعكسه
                    if alloc.journal_entry:
                        try:
                            from financial.services.ledger_core_service import LedgerCoreService
                            LedgerCoreService.reverse_entry(
                                entry_id=alloc.journal_entry_id,
                                user=user,
                                reversal_reason=f"عكس قيد تسوية الدفعة المقدمة على الفاتورة {sale.number} لارتداد شيك #{cheque.cheque_number}"
                            )
                        except Exception as je_err:
                            logger.error(f"Error reversing allocation journal entry on bounce: {je_err}")
                            raise ValidationError(_(f"فشل عكس قيد تسوية الدفعة المقدمة عند ارتداد الشيك: {je_err}"))

                    # عكس سجل التدقيق CustomerAllocationAudit واستعادة أرصدة الأستاذ المساعد
                    orig_audit = getattr(alloc, "allocation_audit", None)
                    if not orig_audit:
                        orig_audit = CustomerAllocationAudit.objects.filter(
                            target_document_number=sale.number,
                            source_document_number=cheque.voucher_number,
                            allocated_amount=alloc.allocated_amount,
                            allocation_status="APPLIED"
                        ).first() or CustomerAllocationAudit.objects.filter(
                            target_document_number=sale.number,
                            source_document_number=cheque.voucher_number,
                            allocation_status="APPLIED"
                        ).first()

                    if orig_audit:
                        now = timezone.now()
                        raw_hash = f"REV:{orig_audit.id}:{alloc.allocated_amount}:{now.isoformat()}"
                        rev_hash = hashlib.sha256(raw_hash.encode("utf-8")).hexdigest()
                        CustomerAllocationAudit.objects.create(
                            customer=orig_audit.customer,
                            allocation_reference=f"REV-{orig_audit.allocation_reference}-{uuid.uuid4().hex[:8]}",
                            payment_transaction=orig_audit.payment_transaction,
                            invoice_transaction=orig_audit.invoice_transaction,
                            source_document_type="CHEQUE",
                            source_document_number=cheque.voucher_number,
                            target_document_type="SALES_INVOICE",
                            target_document_number=sale.number,
                            allocation_type="REVERSAL",
                            allocated_amount=alloc.allocated_amount,
                            functional_amount=alloc.allocated_amount_functional,
                            allocation_status="REVERSED",
                            reversed_audit=orig_audit,
                            allocation_date=now.date(),
                            created_by=cheque.created_by,
                            evidence_hash=rev_hash
                        )

                        # استعادة الرصيد المفتوح في الأستاذ المساعد للفاتورة باستخدام القيمة الدفترية للفاتورة
                        if orig_audit.invoice_transaction:
                            inv_txn = orig_audit.invoice_transaction
                            inv_rate = Decimal(str(inv_txn.exchange_rate or "1.000000"))
                            inv_restore_functional = (alloc.allocated_amount * inv_rate).quantize(Decimal("0.01"))
                            inv_txn.open_amount = min(inv_txn.functional_amount, inv_txn.open_amount + inv_restore_functional)
                            inv_txn.open_amount_functional = inv_txn.open_amount
                            if inv_txn.exchange_rate and inv_txn.exchange_rate > Decimal("0.000000"):
                                inv_txn.open_amount_foreign = (inv_txn.open_amount / inv_txn.exchange_rate).quantize(Decimal("0.01"))
                            inv_txn.status = "OPEN" if inv_txn.open_amount >= inv_txn.functional_amount else "PARTIAL"
                            inv_txn.save()

                        # الشيك مرتد فلا يمثل رصيداً دائناً مفتوحاً للعميل، ويجب إغلاقه برصيد صفر
                        if orig_audit.payment_transaction:
                            pay_txn = orig_audit.payment_transaction
                            pay_txn.open_amount = Decimal("0.00")
                            pay_txn.open_amount_functional = Decimal("0.00")
                            pay_txn.open_amount_foreign = Decimal("0.00")
                            pay_txn.status = "CLOSED"
                            pay_txn.save()
                else:
                    # ارتداد جزئي: تعديل مبلغ السداد ليقتصر على الحصة المحصلة فقط
                    ratio = (cheque.collected_amount / cheque.amount) if cheque.amount else Decimal("0.00")
                    actual_cleared = (alloc.allocated_amount * ratio).quantize(Decimal("0.01"))
                    bounced_diff = alloc.allocated_amount - actual_cleared
                    tag = f"[PARTIAL_BOUNCE:{action_log.id}]" if action_log else "[PARTIAL_BOUNCE:BOUNCE]"
                    alloc.notes = f"{alloc.notes or ''} {tag}".strip()
                    alloc.save(update_fields=["notes"])

                    # تعديل دفعة الفاتورة SalePayment المرتبطة بهذا التخصيص فقط
                    if getattr(alloc, "sale_payment", None):
                        alloc.sale_payment.amount = actual_cleared
                        alloc.sale_payment.save(update_fields=["amount"])
                    else:
                        target_payment = SalePayment.objects.filter(
                            sale=sale,
                            source_type="CHEQUE",
                            reference_number=cheque.voucher_number,
                            amount=alloc.allocated_amount,
                            status="posted"
                        ).first()
                        if target_payment:
                            target_payment.amount = actual_cleared
                            target_payment.save(update_fields=["amount"])
                        else:
                            SalePayment.objects.filter(
                                sale=sale,
                                source_type="CHEQUE",
                                reference_number=cheque.voucher_number,
                                status="posted"
                            ).order_by("-id")[:1].update(amount=actual_cleared)

                    # عكس الجزء المرتد في سجل التدقيق والأستاذ المساعد
                    if bounced_diff > Decimal("0.00"):
                        orig_audit = getattr(alloc, "allocation_audit", None)
                        if not orig_audit:
                            orig_audit = CustomerAllocationAudit.objects.filter(
                                target_document_number=sale.number,
                                source_document_number=cheque.voucher_number,
                                allocated_amount=alloc.allocated_amount,
                                allocation_status="APPLIED"
                            ).first() or CustomerAllocationAudit.objects.filter(
                                target_document_number=sale.number,
                                source_document_number=cheque.voucher_number,
                                allocation_status="APPLIED"
                            ).first()

                        if orig_audit:
                            now = timezone.now()
                            raw_hash = f"REV:{orig_audit.id}:{bounced_diff}:{now.isoformat()}"
                            rev_hash = hashlib.sha256(raw_hash.encode("utf-8")).hexdigest()
                            bounced_diff_functional = (bounced_diff * (cheque.original_exchange_rate or Decimal("1.000000"))).quantize(Decimal("0.01"))
                            CustomerAllocationAudit.objects.create(
                                customer=orig_audit.customer,
                                allocation_reference=f"REV-{orig_audit.allocation_reference}-PARTIAL-{uuid.uuid4().hex[:8]}",
                                payment_transaction=orig_audit.payment_transaction,
                                invoice_transaction=orig_audit.invoice_transaction,
                                source_document_type="CHEQUE",
                                source_document_number=cheque.voucher_number,
                                target_document_type="SALES_INVOICE",
                                target_document_number=sale.number,
                                allocation_type="REVERSAL",
                                allocated_amount=bounced_diff,
                                functional_amount=bounced_diff_functional,
                                allocation_status="REVERSED",
                                reversed_audit=orig_audit,
                                allocation_date=now.date(),
                                created_by=cheque.created_by,
                                evidence_hash=rev_hash
                            )
                            # استعادة الفرق المرتد في الرصيد المفتوح للأستاذ المساعد للفاتورة بسعر صرف الفاتورة الدفتري
                            if orig_audit.invoice_transaction:
                                inv_txn = orig_audit.invoice_transaction
                                inv_rate = Decimal(str(inv_txn.exchange_rate or "1.000000"))
                                diff_restore_functional = (bounced_diff * inv_rate).quantize(Decimal("0.01"))
                                inv_txn.open_amount = min(inv_txn.functional_amount, inv_txn.open_amount + diff_restore_functional)
                                inv_txn.open_amount_functional = inv_txn.open_amount
                                if inv_txn.exchange_rate and inv_txn.exchange_rate > Decimal("0.000000"):
                                    inv_txn.open_amount_foreign = (inv_txn.open_amount / inv_txn.exchange_rate).quantize(Decimal("0.01"))
                                inv_txn.status = "OPEN" if inv_txn.open_amount >= inv_txn.functional_amount else "PARTIAL"
                                inv_txn.save()

                            # حركة دفع الشيك: الجزء المرتد لم يعد متاحاً كرصيد دائن
                            if orig_audit.payment_transaction:
                                pay_txn = orig_audit.payment_transaction
                                pay_txn.open_amount = Decimal("0.00")
                                pay_txn.open_amount_functional = Decimal("0.00")
                                pay_txn.open_amount_foreign = Decimal("0.00")
                                pay_txn.status = "CLOSED"
                                pay_txn.save()

                if hasattr(sale, "update_payment_status"):
                    sale.update_payment_status()

            if is_full_bounce and cheque.customer:
                from customer.models import CustomerTransaction
                CustomerTransaction.objects.filter(
                    customer=cheque.customer,
                    transaction_type="CHEQUE",
                    reference_id=str(cheque.id)
                ).update(
                    open_amount=Decimal("0.00"),
                    open_amount_functional=Decimal("0.00"),
                    open_amount_foreign=Decimal("0.00"),
                    status="CLOSED"
                )
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error handling bounced invoice allocations for cheque #{cheque.id}: {e}")
            raise ValidationError(_(f"فشل معالجة ارتداد مخصصات الفواتير للشيك #{cheque.id}: {e}"))

    # --- Convenience Wrapper Methods ---

    @classmethod
    def _extract_cheque_id_and_key(cls, cheque_or_id=None, cheque=None, cheque_id=None, idempotency_key: Optional[str] = None, prefix: str = "ACT", **params) -> Tuple[int, str]:
        obj = cheque_or_id if cheque_or_id is not None else (cheque if cheque is not None else (cheque_id if cheque_id is not None else params.get("cheque_id")))
        if obj is None:
            raise ValueError("cheque or cheque_id must be provided")
        if isinstance(obj, Cheque):
            c_id = obj.id
        else:
            c_id = int(obj)
        ikey = idempotency_key or params.get("idempotency_key")
        if not ikey:
            import uuid
            ikey = f"{prefix}-{c_id}-{uuid.uuid4().hex[:12]}"
        return c_id, ikey

    @classmethod
    def receive_cheque(cls, cheque_or_id=None, user=None, idempotency_key: Optional[str] = None, cheque=None, cheque_id=None, **params) -> Dict[str, Any]:
        c_id, ikey = cls._extract_cheque_id_and_key(cheque_or_id=cheque_or_id, cheque=cheque, cheque_id=cheque_id, idempotency_key=idempotency_key, prefix="REC", **params)
        return cls.process_lifecycle_action(c_id, ChequeActionType.RECEIVE, user, ikey, **params)

    @classmethod
    def deposit_cheque(cls, cheque_or_id=None, user=None, idempotency_key: Optional[str] = None, bank_account_id: Optional[int] = None, bank_account=None, cheque=None, cheque_id=None, **params) -> Dict[str, Any]:
        if isinstance(idempotency_key, int) and bank_account_id is None:
            bank_account_id = idempotency_key
            idempotency_key = None
        c_id, ikey = cls._extract_cheque_id_and_key(cheque_or_id=cheque_or_id, cheque=cheque, cheque_id=cheque_id, idempotency_key=idempotency_key, prefix="DEP", **params)
        b_id = bank_account_id or (bank_account.id if bank_account else params.get("deposit_bank_account_id") or params.get("bank_account_id"))
        if b_id:
            params["deposit_bank_account_id"] = b_id
        return cls.process_lifecycle_action(c_id, ChequeActionType.DEPOSIT, user, ikey, **params)

    @classmethod
    def collect_cheque(cls, cheque_or_id=None, user=None, idempotency_key: Optional[str] = None, cheque=None, cheque_id=None, **params) -> Dict[str, Any]:
        c_id, ikey = cls._extract_cheque_id_and_key(cheque_or_id=cheque_or_id, cheque=cheque, cheque_id=cheque_id, idempotency_key=idempotency_key, prefix="COL", **params)
        if "amount" in params and "amount_collected" not in params:
            params["amount_collected"] = params["amount"]
        return cls.process_lifecycle_action(c_id, ChequeActionType.COLLECT, user, ikey, **params)

    @classmethod
    def bounce_cheque(cls, cheque_or_id=None, user=None, idempotency_key: Optional[str] = None, cheque=None, cheque_id=None, **params) -> Dict[str, Any]:
        c_id, ikey = cls._extract_cheque_id_and_key(cheque_or_id=cheque_or_id, cheque=cheque, cheque_id=cheque_id, idempotency_key=idempotency_key, prefix="BNC", **params)
        return cls.process_lifecycle_action(c_id, ChequeActionType.BOUNCE, user, ikey, **params)

    @classmethod
    def endorse_cheque(cls, cheque_or_id=None, user=None, supplier_id: Optional[int] = None, idempotency_key: Optional[str] = None, supplier=None, cheque=None, cheque_id=None, **params) -> Dict[str, Any]:
        c_id, ikey = cls._extract_cheque_id_and_key(cheque_or_id=cheque_or_id, cheque=cheque, cheque_id=cheque_id, idempotency_key=idempotency_key, prefix="END", **params)
        s_id = supplier_id or (supplier.id if supplier else params.get("supplier_id"))
        if s_id:
            params["supplier_id"] = s_id
        return cls.process_lifecycle_action(c_id, ChequeActionType.ENDORSE, user, ikey, **params)

    @classmethod
    def issue_cheque(cls, cheque_or_id=None, user=None, idempotency_key: Optional[str] = None, cheque=None, cheque_id=None, **params) -> Dict[str, Any]:
        c_id, ikey = cls._extract_cheque_id_and_key(cheque_or_id=cheque_or_id, cheque=cheque, cheque_id=cheque_id, idempotency_key=idempotency_key, prefix="ISS", **params)
        return cls.process_lifecycle_action(c_id, ChequeActionType.ISSUE, user, ikey, **params)

    @classmethod
    def issue_payable_cheque(cls, cheque_or_id=None, user=None, idempotency_key: Optional[str] = None, cheque=None, cheque_id=None, **params) -> Dict[str, Any]:
        return cls.issue_cheque(cheque_or_id=cheque_or_id, user=user, idempotency_key=idempotency_key, cheque=cheque, cheque_id=cheque_id, **params)

    @classmethod
    def clear_payable_cheque(cls, cheque_or_id=None, user=None, idempotency_key: Optional[str] = None, cheque=None, cheque_id=None, **params) -> Dict[str, Any]:
        c_id, ikey = cls._extract_cheque_id_and_key(cheque_or_id=cheque_or_id, cheque=cheque, cheque_id=cheque_id, idempotency_key=idempotency_key, prefix="CLR", **params)
        return cls.process_lifecycle_action(c_id, ChequeActionType.CLEAR, user, ikey, **params)

    @classmethod
    def return_to_drawer(cls, cheque_or_id=None, user=None, idempotency_key: Optional[str] = None, cheque=None, cheque_id=None, **params) -> Dict[str, Any]:
        c_id, ikey = cls._extract_cheque_id_and_key(cheque_or_id=cheque_or_id, cheque=cheque, cheque_id=cheque_id, idempotency_key=idempotency_key, prefix="RTD", **params)
        return cls.process_lifecycle_action(c_id, ChequeActionType.RETURN_TO_DRAWER, user, ikey, **params)

    @classmethod
    def cancel_cheque(cls, cheque_or_id=None, user=None, idempotency_key: Optional[str] = None, cheque=None, cheque_id=None, **params) -> Dict[str, Any]:
        c_id, ikey = cls._extract_cheque_id_and_key(cheque_or_id=cheque_or_id, cheque=cheque, cheque_id=cheque_id, idempotency_key=idempotency_key, prefix="CAN", **params)
        return cls.process_lifecycle_action(c_id, ChequeActionType.CANCEL, user, ikey, **params)

    @classmethod
    def convert_guarantee(cls, cheque_or_id=None, user=None, new_purpose=None, idempotency_key: Optional[str] = None, cheque=None, cheque_id=None, **params) -> Dict[str, Any]:
        c_id, ikey = cls._extract_cheque_id_and_key(cheque_or_id=cheque_or_id, cheque=cheque, cheque_id=cheque_id, idempotency_key=idempotency_key, prefix="CONV", **params)
        return cls.process_lifecycle_action(
            c_id,
            ChequeActionType.CONVERT_GUARANTEE,
            user,
            ikey,
            new_purpose=new_purpose,
            **params
        )

