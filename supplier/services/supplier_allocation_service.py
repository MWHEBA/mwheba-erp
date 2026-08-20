import hashlib
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from supplier.models import Supplier, SupplierTransaction, SupplierAdvancePayment, SupplierAllocationAudit
from governance.services import AccountingGateway, JournalEntryLineData

logger = logging.getLogger("supplier.services.supplier_allocation_service")


class SupplierAllocationService:
    """
    خدمة محرك توزيع الدفعات المقدمة للموردين والتكامل المحاسبي الحصين (FIN-AP-004)
    """

    @classmethod
    def get_available_supplier_prepaid_balance(cls, supplier_id: int) -> Decimal:
        """
        حساب إجمالي الرصيد المسبق المتاح للمورد (الدفعات المقدمة غير المخصصة)
        """
        advances = SupplierAdvancePayment.objects.filter(supplier_id=supplier_id)
        total_remaining = Decimal("0.00")
        for adv in advances:
            total_remaining += adv.remaining_amount
        return total_remaining

    @classmethod
    def allocate_advance_to_purchase_bill(
        cls,
        purchase,
        amount_to_allocate: Optional[Decimal] = None,
        user=None,
        amount: Optional[Decimal] = None
    ) -> SupplierAllocationAudit:
        """
        تخصيص مبلغ من الرصيد المسبق/الدفعات المقدمة للمورد على فاتورة مشتريات
        مع استخدام select_for_update() للوقاية من Race Conditions وتوليد قيد التسوية
        """
        # 1. التحقق من حالة الفاتورة (يُمنع التخصيص للمسودات DRAFT)
        purch_status = str(getattr(purchase, "status", "")).lower()
        if purch_status not in ["confirmed", "posted"]:
            raise ValidationError("لا يمكن تخصيص رصيد مسبق إلا على فواتير المشتريات المعتمدة والمرحلة فقط.")

        target_amount = amount_to_allocate if amount_to_allocate is not None else amount
        if target_amount is None:
            raise ValidationError("المبلغ المراد تخصيصه مطلوب.")
        amount_to_allocate = Decimal(str(target_amount)).quantize(Decimal("0.01"))

        if amount_to_allocate <= Decimal("0.00"):
            raise ValidationError("المبلغ المراد تخصيصه يجب أن يكون أكبر من صفر.")

        allocation_date = timezone.now().date()
        from financial.services.period_control_service import PeriodControlService
        from financial.services.fx_settlement_strategy import SupplierFXStrategy
        from financial.services.partner_currency_snapshot_updater import PartnerCurrencySnapshotUpdater

        PeriodControlService.validate_period_open(allocation_date)

        from utils.templatetags.utils_extras import smart_float
        from core.models import SystemSetting
        currency_sym = purchase.currency.symbol if purchase.currency else SystemSetting.get_setting('currency_symbol', 'ج.م')

        supplier = purchase.supplier
        open_bill_amount = (purchase.total - (purchase.amount_paid or Decimal("0.00"))).quantize(Decimal("0.01"))
        if amount_to_allocate > open_bill_amount:
            raise ValidationError(f"المبلغ المراد تخصيصه ({smart_float(amount_to_allocate)} {currency_sym}) يتجاوز المتبقي من الفاتورة ({smart_float(open_bill_amount)} {currency_sym}).")

        with transaction.atomic():
            locked_supplier = Supplier.objects.select_for_update().get(pk=supplier.id)

            from django.db.models import Q
            purch_curr_id = purchase.currency_id or (locked_supplier.default_currency_id if locked_supplier else None)
            advances_qs = SupplierAdvancePayment.objects.select_for_update().filter(
                supplier_id=locked_supplier.id
            )
            if purch_curr_id:
                advances_qs = advances_qs.filter(Q(currency_id=purch_curr_id) | Q(currency__isnull=True))
            else:
                advances_qs = advances_qs.filter(currency__isnull=True)

            advances = list(advances_qs.order_by("payment_date", "created_at"))

            available_balance = sum(adv.remaining_amount for adv in advances)
            if amount_to_allocate > available_balance:
                raise ValidationError(f"رصيد المورد المسبق المتاح لعملة {currency_sym} ({smart_float(available_balance)}) غير كافٍ لسداد المبلغ المطلوب ({smart_float(amount_to_allocate)}).")

            remaining_to_allocate = amount_to_allocate
            last_audit = None
            total_fx_diff = Decimal("0.00")

            bill_txn, _ = SupplierTransaction.objects.select_for_update().get_or_create(
                supplier=locked_supplier,
                transaction_number=purchase.number,
                defaults={
                    "transaction_type": "BILL",
                    "issue_date": purchase.date,
                    "due_date": purchase.date,
                    "functional_amount": purchase.total,
                    "open_amount": open_bill_amount,
                    "status": "OPEN" if (purchase.amount_paid or Decimal("0.00")) == Decimal("0.00") else "PARTIAL"
                }
            )

            fx_strategy = SupplierFXStrategy()

            for adv in advances:
                if remaining_to_allocate <= Decimal("0.00"):
                    break
                rem = adv.remaining_amount
                if rem <= Decimal("0.00"):
                    continue

                curr_alloc = min(rem, remaining_to_allocate)
                adv.allocated_amount += curr_alloc
                adv.save()

                remaining_to_allocate -= curr_alloc

                adv_rate = adv.exchange_rate if hasattr(adv, "exchange_rate") and adv.exchange_rate else Decimal("1.0")
                purch_rate = purchase.exchange_rate if hasattr(purchase, "exchange_rate") and purchase.exchange_rate else Decimal("1.0")
                fx_diff = fx_strategy.calculate_difference(adv_rate, purch_rate, curr_alloc)
                total_fx_diff += fx_diff

                adv_txn, _ = SupplierTransaction.objects.select_for_update().get_or_create(
                    supplier=locked_supplier,
                    transaction_number=f"ADV-{adv.id}",
                    defaults={
                        "transaction_type": "PAYMENT",
                        "issue_date": adv.payment_date,
                        "due_date": adv.payment_date,
                        "functional_amount": adv.amount,
                        "open_amount": adv.remaining_amount,
                        "status": "PARTIAL" if adv.remaining_amount > 0 else "CLOSED"
                    }
                )
                adv_txn.open_amount = max(Decimal("0.00"), adv_txn.open_amount - curr_alloc)
                adv_txn.status = "CLOSED" if adv_txn.open_amount == 0 else "PARTIAL"
                adv_txn.save()

                bill_txn.open_amount = max(Decimal("0.00"), bill_txn.open_amount - curr_alloc)
                bill_txn.status = "CLOSED" if bill_txn.open_amount == 0 else "PARTIAL"
                bill_txn.save()

                now = timezone.now()
                raw_hash_data = f"{locked_supplier.id}:{adv_txn.id}:{bill_txn.id}:{curr_alloc}:{now.isoformat()}"
                ev_hash = hashlib.sha256(raw_hash_data.encode("utf-8")).hexdigest()

                last_audit = SupplierAllocationAudit.objects.create(
                    supplier=locked_supplier,
                    payment_transaction=adv_txn,
                    invoice_transaction=bill_txn,
                    source_document_type="ADVANCE_PAYMENT",
                    source_document_number=f"ADV-{adv.id}",
                    target_document_type="PURCHASE_BILL",
                    target_document_number=purchase.number,
                    allocation_type="ADVANCE_TO_BILL",
                    allocated_amount=curr_alloc,
                    functional_amount=curr_alloc,
                    allocation_status="APPLIED",
                    allocation_date=now.date(),
                    created_by=user,
                    evidence_hash=ev_hash
                )

                from purchase.models.payment import PurchasePayment
                PurchasePayment.objects.create(
                    purchase=purchase,
                    amount=curr_alloc,
                    payment_date=adv.payment_date if (adv and getattr(adv, "payment_date", None)) else now.date(),
                    payment_method="prepaid_balance",
                    source_type="PREPAID_BALANCE",
                    reference_number=f"ADV-{adv.id}",
                    notes=f"خصم تلقائي من الرصيد المسبق (دفعة #{adv.id})",
                    created_by=user or purchase.created_by,
                    status="posted",
                    financial_status="synced"
                )

            if hasattr(purchase, "update_payment_status"):
                purchase.update_payment_status()

            # إصدار قيد التسوية المحسب المتزن للمورد
            if locked_supplier.financial_account:
                from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
                advance_acc = AccountRoleRegistry.get_account(AccountRoleNames.SUPPLIER_ADVANCE_ASSET)
                partner_acc_code = locked_supplier.financial_account.code

                adv_rate = Decimal(str(getattr(advances[0], "exchange_rate", 1.0) or 1.0)) if advances else Decimal("1.0")
                purch_rate = Decimal(str(getattr(purchase, "exchange_rate", 1.0) or 1.0))

                adv_func = (amount_to_allocate * adv_rate).quantize(Decimal("0.01"))
                purch_func = (amount_to_allocate * purch_rate).quantize(Decimal("0.01"))

                lines = [
                    JournalEntryLineData(
                        account_code=partner_acc_code,
                        debit=purch_func,
                        credit=Decimal("0.00"),
                        description=f"تسوية فاتورة مشتريات {purchase.number} - تخفيض دائنية المورد"
                    ),
                    JournalEntryLineData(
                        account_code=advance_acc.code,
                        debit=Decimal("0.00"),
                        credit=adv_func,
                        description=f"إغلاق دفعات مقدمة للمورد - فاتورة {purchase.number}"
                    )
                ]

                if total_fx_diff != Decimal("0.00"):
                    fx_lines = fx_strategy.generate_entries(
                        difference=total_fx_diff,
                        advance_account_code=advance_acc.code,
                        partner_account_code=partner_acc_code,
                        reference_note=f"فاتورة مشتريات {purchase.number}"
                    )
                    lines.extend(fx_lines)

                # معالجة فروق التقريب الكسري البسيطة (<= 0.05 ج.م)
                tot_deb = sum(l.debit for l in lines)
                tot_crd = sum(l.credit for l in lines)
                if tot_deb != tot_crd:
                    round_diff = (tot_deb - tot_crd).quantize(Decimal("0.01"))
                    if abs(round_diff) <= Decimal("0.05"):
                        round_acc = AccountRoleRegistry.get_account(AccountRoleNames.ROUNDING_DIFFERENCE_ACCOUNT)
                        if round_diff < Decimal("0.00"):
                            lines.append(JournalEntryLineData(account_code=round_acc.code, debit=abs(round_diff), credit=Decimal("0.00"), description="تسوية فارق تقويم كسر بنيات"))
                        else:
                            lines.append(JournalEntryLineData(account_code=round_acc.code, debit=Decimal("0.00"), credit=abs(round_diff), description="تسوية فارق تقويم كسر بنيات"))

                gateway = AccountingGateway()
                gateway.create_journal_entry(
                    source_module="purchase",
                    source_model="SupplierAllocationAudit",
                    source_id=last_audit.id if last_audit else purchase.id,
                    lines=lines,
                    idempotency_key=f"JE:purchase:SupplierAllocationAudit:{last_audit.id if last_audit else purchase.id}:reclassify",
                    user=user or purchase.created_by,
                    entry_type="automatic",
                    description=f"تسوية رصيد مسبق للمورد {supplier.name}",
                    reference=f"فاتورة مشتريات {purchase.number}"
                )

            from financial.services.partner_subledger_service import PartnerSubledgerService
            PartnerSubledgerService.record_purchase_bill(purchase, user)
            from financial.services.partner_balance_service import PartnerBalanceService
            PartnerBalanceService.update_partner_snapshot("supplier", locked_supplier.id)

            return last_audit

    @classmethod
    def create_supplier_advance_payment(
        cls,
        supplier_id: int,
        amount: Decimal,
        payment_date=None,
        payment_method: str = "cash",
        financial_account_id: Optional[int] = None,
        reference_number: Optional[str] = None,
        notes: Optional[str] = None,
        user=None
    ) -> SupplierAdvancePayment:
        """
        إضافة دفعة مقدمة/رصيد مسبق جديد للمورد مع فحص رصيد الخزينة/البنك وإنشاء القيد المحاسبي التلقائي
        """
        amount = Decimal(str(amount))
        if amount <= Decimal("0.00"):
            raise ValidationError("المبلغ يجب أن يكون أكبر من صفر.")

        if not payment_date:
            payment_date = timezone.now().date()

        try:
            from financial.services.period_control_service import PeriodControlService
            PeriodControlService.validate_period_open(payment_date)
        except Exception as e:
            logger.warning(f"Period validation note: {str(e)}")

        with transaction.atomic():
            supplier = Supplier.objects.select_for_update().get(pk=supplier_id)
            
            from financial.models import ChartOfAccounts
            fin_account = None
            if financial_account_id:
                fin_account = ChartOfAccounts.objects.filter(pk=financial_account_id).first()

            advance = SupplierAdvancePayment.objects.create(
                supplier=supplier,
                amount=amount,
                payment_date=payment_date,
                payment_method=payment_method,
                reference_number=reference_number,
                financial_account=fin_account,
                notes=notes,
                created_by=user
            )

            adv_txn, _ = SupplierTransaction.objects.get_or_create(
                supplier=supplier,
                transaction_number=f"ADV-{advance.id}",
                defaults={
                    "transaction_type": "PAYMENT",
                    "issue_date": payment_date,
                    "due_date": payment_date,
                    "functional_amount": amount,
                    "open_amount": amount,
                    "status": "OPEN"
                }
            )

            try:
                advance_acc = ChartOfAccounts.objects.filter(code="10500").first()
                credit_acc_code = fin_account.code if fin_account else (supplier.financial_account.code if supplier.financial_account else "10101")
                if advance_acc:
                    lines = [
                        JournalEntryLineData(
                            account_code=advance_acc.code,
                            debit=amount,
                            credit=Decimal("0.00"),
                            description=f"دفعة مقدمة للمورد {supplier.name} - مرجع #{advance.id}"
                        ),
                        JournalEntryLineData(
                            account_code=credit_acc_code,
                            debit=Decimal("0.00"),
                            credit=amount,
                            description=f"صرف دفعة مقدمة للمورد {supplier.name}"
                        )
                    ]
                    gateway = AccountingGateway()
                    je = gateway.create_journal_entry(
                        source_module="supplier",
                        source_model="SupplierAdvancePayment",
                        source_id=advance.id,
                        lines=lines,
                        idempotency_key=f"JE:supplier:SupplierAdvancePayment:{advance.id}",
                        user=user,
                        entry_type="automatic",
                        description=f"إثبات دفعة مقدمة للمورد {supplier.name}",
                        reference=f"دفعة مقدمة #{advance.id}"
                    )
                    if je:
                        advance.journal_entry = je
                        advance.save(update_fields=["journal_entry"])
            except Exception as e:
                logger.warning(f"لم يتم توليد قيد الدفعة المقدمة للمورد تلقائياً: {str(e)}")

            return advance

    @classmethod
    def allocate_prepaid_bulk(
        cls,
        supplier_id: int,
        allocations_dict: Dict[int, Decimal],
        user=None,
        allocation_date=None
    ) -> List[SupplierAllocationAudit]:
        """
        تخصيص جماعي لرصيد المورد المسبق على أكثر من فاتورة مشتريات بأسلوب محصن ذرية
        مع إنشاء قيد تسوية تجميعي واحد بمرجعية تجميعية فريدة batch_reference
        """
        if not allocations_dict:
            raise ValidationError("لم يتم تحديد أي فواتير للتخصيص.")

        if not allocation_date:
            allocation_date = timezone.now().date()

        try:
            from financial.services.period_control_service import PeriodControlService
            PeriodControlService.validate_period_open(allocation_date)
        except Exception as e:
            logger.warning(f"Period validation note: {str(e)}")

        from purchase.models import Purchase
        from utils.templatetags.utils_extras import smart_float
        from core.models import SystemSetting
        currency_sym = SystemSetting.get_setting('currency_symbol', 'ج.م')

        valid_allocations = {}
        total_requested = Decimal("0.00")

        for pur_id, amt in allocations_dict.items():
            if amt is None:
                continue
            dec_amt = Decimal(str(amt)).quantize(Decimal("0.01"))
            if dec_amt > Decimal("0.00"):
                valid_allocations[int(pur_id)] = dec_amt
                total_requested += dec_amt

        if not valid_allocations or total_requested <= Decimal("0.00"):
            raise ValidationError("يرجى إدخال مبالغ تخصيص أكبر من صفر.")

        import uuid
        batch_reference = f"BATCH-SUPP-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

        with transaction.atomic():
            locked_supplier = Supplier.objects.select_for_update().get(pk=supplier_id)
            available_balance = cls.get_available_supplier_prepaid_balance(locked_supplier.id)

            if total_requested > available_balance:
                raise ValidationError(
                    f"إجمالي مبالغ التخصيص المطلوبة ({smart_float(total_requested)} {currency_sym}) "
                    f"يتجاوز رصيد المورد المسبق المتاح ({smart_float(available_balance)} {currency_sym})."
                )

            purchases = list(
                Purchase.objects.select_for_update().filter(
                    id__in=valid_allocations.keys(),
                    supplier=locked_supplier,
                    status__in=["confirmed", "posted"]
                ).order_by("id")
            )

            advances = list(
                SupplierAdvancePayment.objects.select_for_update().filter(
                    supplier_id=locked_supplier.id
                ).order_by("payment_date", "created_at")
            )

            audits_created = []
            total_actually_allocated = Decimal("0.00")

            from purchase.models.payment import PurchasePayment
            now = timezone.now()

            for purchase in purchases:
                req_amt = valid_allocations.get(purchase.id, Decimal("0.00"))
                if req_amt <= Decimal("0.00"):
                    continue

                open_bill_amount = purchase.total - (purchase.amount_paid or Decimal("0.00"))
                if req_amt > open_bill_amount:
                    raise ValidationError(
                        f"المبلغ المراد تخصيصه ({smart_float(req_amt)} {currency_sym}) "
                        f"يتجاوز المتبقي من الفاتورة #{purchase.number} ({smart_float(open_bill_amount)} {currency_sym})."
                    )

                remaining_for_bill = req_amt

                bill_txn, _ = SupplierTransaction.objects.select_for_update().get_or_create(
                    supplier=locked_supplier,
                    transaction_number=purchase.number,
                    defaults={
                        "transaction_type": "BILL",
                        "issue_date": purchase.date,
                        "due_date": purchase.date,
                        "functional_amount": purchase.total,
                        "open_amount": open_bill_amount,
                        "status": "OPEN" if (purchase.amount_paid or Decimal("0.00")) == Decimal("0.00") else "PARTIAL"
                    }
                )

                pur_curr_id = purchase.currency_id
                for adv in advances:
                    if remaining_for_bill <= Decimal("0.00"):
                        break

                    adv_curr_id = adv.currency_id
                    if pur_curr_id != adv_curr_id:
                        is_egp_match = (
                            (pur_curr_id is None and adv.currency and adv.currency.code == "EGP") or
                            (adv_curr_id is None and purchase.currency and purchase.currency.code == "EGP")
                        )
                        if not is_egp_match:
                            continue

                    rem_adv = adv.remaining_amount
                    if rem_adv <= Decimal("0.00"):
                        continue

                    curr_alloc = min(rem_adv, remaining_for_bill)
                    adv.allocated_amount += curr_alloc
                    adv.save(update_fields=["allocated_amount"])

                    remaining_for_bill -= curr_alloc
                    total_actually_allocated += curr_alloc

                    adv_txn, _ = SupplierTransaction.objects.select_for_update().get_or_create(
                        supplier=locked_supplier,
                        transaction_number=f"ADV-{adv.id}",
                        defaults={
                            "transaction_type": "PAYMENT",
                            "issue_date": adv.payment_date,
                            "due_date": adv.payment_date,
                            "functional_amount": adv.amount,
                            "open_amount": adv.remaining_amount,
                            "status": "PARTIAL" if adv.remaining_amount > 0 else "CLOSED"
                        }
                    )
                    adv_txn.open_amount = max(Decimal("0.00"), adv_txn.open_amount - curr_alloc)
                    adv_txn.status = "CLOSED" if adv_txn.open_amount == Decimal("0.00") else "PARTIAL"
                    adv_txn.save()

                    bill_txn.open_amount = max(Decimal("0.00"), bill_txn.open_amount - curr_alloc)
                    bill_txn.status = "CLOSED" if bill_txn.open_amount == Decimal("0.00") else "PARTIAL"
                    bill_txn.save()

                    raw_hash_data = f"{batch_reference}:{locked_supplier.id}:{adv_txn.id}:{bill_txn.id}:{curr_alloc}:{now.isoformat()}"
                    ev_hash = hashlib.sha256(raw_hash_data.encode("utf-8")).hexdigest()

                    audit = SupplierAllocationAudit.objects.create(
                        supplier=locked_supplier,
                        allocation_reference=f"{batch_reference}-{len(audits_created)+1}",
                        payment_transaction=adv_txn,
                        invoice_transaction=bill_txn,
                        source_document_type="ADVANCE_PAYMENT",
                        source_document_number=f"ADV-{adv.id}",
                        target_document_type="PURCHASE_BILL",
                        target_document_number=purchase.number,
                        allocation_type="ADVANCE_TO_BILL",
                        allocated_amount=curr_alloc,
                        functional_amount=curr_alloc,
                        allocation_status="APPLIED",
                        allocation_date=allocation_date,
                        created_by=user,
                        evidence_hash=ev_hash
                    )
                    audits_created.append(audit)

                    PurchasePayment.objects.create(
                        purchase=purchase,
                        amount=curr_alloc,
                        payment_date=adv.payment_date if (adv and getattr(adv, "payment_date", None)) else allocation_date,
                        payment_method="prepaid_balance",
                        source_type="PREPAID_BALANCE",
                        reference_number=batch_reference,
                        notes=f"تخصيص جماعي من الرصيد المسبق (دفعة #{adv.id} - دفعة {batch_reference})",
                        created_by=user or purchase.created_by,
                        status="posted",
                        financial_status="synced"
                    )

                if hasattr(purchase, "update_payment_status"):
                    purchase.update_payment_status()
                else:
                    tot_paid = sum(p.amount for p in purchase.payments.all())
                    if tot_paid >= purchase.total:
                        purchase.payment_status = "paid"
                    elif tot_paid > 0:
                        purchase.payment_status = "partial"
                    else:
                        purchase.payment_status = "unpaid"
                    purchase.save(update_fields=["payment_status"])

            if total_actually_allocated > Decimal("0.00") and locked_supplier.financial_account:
                try:
                    from financial.models import ChartOfAccounts
                    advance_acc = ChartOfAccounts.objects.filter(code="10500").first()
                    if advance_acc:
                        lines = [
                            JournalEntryLineData(
                                account_code=locked_supplier.financial_account.code,
                                debit=total_actually_allocated,
                                credit=Decimal("0.00"),
                                description=f"تخصيص جماعي رصيد مسبق للمورد - دفعة {batch_reference}"
                            ),
                            JournalEntryLineData(
                                account_code=advance_acc.code,
                                debit=Decimal("0.00"),
                                credit=total_actually_allocated,
                                description=f"إغلاق دفعات مقدمة للمورد {locked_supplier.name} - دفعة {batch_reference}"
                            )
                        ]
                        gateway = AccountingGateway()
                        gateway.create_journal_entry(
                            source_module="purchase",
                            source_model="SupplierAllocationAudit",
                            source_id=audits_created[0].id if audits_created else locked_supplier.id,
                            lines=lines,
                            idempotency_key=f"JE:bulk_alloc:{batch_reference}",
                            user=user,
                            entry_type="automatic",
                            description=f"قيد تسوية تجميعي رصيد مسبق للمورد {locked_supplier.name}",
                            reference=batch_reference
                        )
                except Exception as e:
                    logger.warning(f"لم يتم توليد قيد التسوية التجميعي الموحد: {str(e)}")

            return audits_created

    @classmethod
    def reverse_supplier_allocation(cls, audit_id: int, user=None) -> SupplierAllocationAudit:
        """
        عكس وإلغاء تخصيص رصيد مسبق للمورد (Reversal Engine)
        """
        with transaction.atomic():
            audit = SupplierAllocationAudit.objects.select_for_update().get(pk=audit_id)
            if audit.allocation_status == "REVERSED":
                raise ValueError("سجل التخصيص معكوس بالفعل سابقاً.")

            # رد المبالغ للدفعات المقدمة للمورد
            adv_id_str = audit.source_document_number.replace("ADV-", "") if audit.source_document_number else None
            if adv_id_str and adv_id_str.isdigit():
                adv = SupplierAdvancePayment.objects.select_for_update().filter(pk=int(adv_id_str)).first()
                if adv:
                    adv.allocated_amount = max(Decimal("0.00"), adv.allocated_amount - audit.allocated_amount)
                    adv.save(update_fields=["allocated_amount"])

            # حذف/إلغاء مدفوعات PurchasePayment ذات الصلة
            from purchase.models.payment import PurchasePayment
            payments = PurchasePayment.objects.filter(
                purchase__number=audit.target_document_number,
                source_type="PREPAID_BALANCE"
            )
            for p in payments:
                purchase = p.purchase
                p.delete()
                if hasattr(purchase, "update_payment_status"):
                    purchase.update_payment_status()

            # إنشاء سجل تدقيق عكسي للمورد
            now = timezone.now()
            raw_hash_data = f"REV_SUPP:{audit.id}:{audit.allocated_amount}:{now.isoformat()}"
            rev_hash = hashlib.sha256(raw_hash_data.encode("utf-8")).hexdigest()

            rev_audit = SupplierAllocationAudit.objects.create(
                supplier=audit.supplier,
                payment_transaction=audit.payment_transaction,
                invoice_transaction=audit.invoice_transaction,
                source_document_type=audit.source_document_type,
                source_document_number=audit.source_document_number,
                target_document_type=audit.target_document_type,
                target_document_number=audit.target_document_number,
                allocation_type="REVERSAL",
                allocated_amount=audit.allocated_amount,
                functional_amount=audit.functional_amount,
                allocation_status="REVERSED",
                reversed_audit=audit,
                allocation_date=now.date(),
                created_by=user,
                evidence_hash=rev_hash
            )

            # تترحيل قيد عكسي للمورد في الدفتر العام
            if audit.supplier and audit.supplier.financial_account:
                try:
                    from governance.services import AccountingGateway, JournalEntryLineData
                    from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
                    from financial.services.fx_settlement_strategy import SupplierFXStrategy
                    advance_acc = AccountRoleRegistry.get_account(AccountRoleNames.SUPPLIER_ADVANCE_ASSET)
                    
                    rev_lines = [
                        JournalEntryLineData(
                            account_code=advance_acc.code,
                            debit=audit.functional_amount,
                            credit=Decimal("0.00"),
                            description=f"عكس تسوية دفعة مقدمة للمورد (إلغاء تخصيص #{audit.id})"
                        ),
                        JournalEntryLineData(
                            account_code=audit.supplier.financial_account.code,
                            debit=Decimal("0.00"),
                            credit=audit.functional_amount,
                            description=f"عكس تسوية فاتورة مشتريات - إعادة دائنية المورد (إلغاء تخصيص #{audit.id})"
                        )
                    ]

                    # عكس فروق العملة المحققة IAS 21 بالكامل بنفس القيمة التاريخية
                    if audit.realized_fx_difference and audit.realized_fx_difference != Decimal("0.00"):
                        fx_strategy = SupplierFXStrategy()
                        fx_rev_lines = fx_strategy.generate_entries(
                            difference=-audit.realized_fx_difference,
                            advance_account_code=advance_acc.code,
                            partner_account_code=audit.supplier.financial_account.code,
                            reference_note=f"عكس فروق عملة تخصيص مشتريات #{audit.id}"
                        )
                        rev_lines.extend(fx_rev_lines)

                    gateway = AccountingGateway()
                    gateway.create_journal_entry(
                        source_module="purchase",
                        source_model="SupplierAllocationAudit",
                        source_id=rev_audit.id,
                        lines=rev_lines,
                        idempotency_key=f"JE:purchase:SupplierAllocationAudit:REV:{audit.id}",
                        user=user,
                        entry_type="automatic",
                        description=f"قيد عكسي لتسوية رصيد مسبق للمورد {audit.supplier.name}",
                        reference=f"عكس تخصيص #{audit.id}"
                    )
                except Exception as e:
                    logger.warning(f"لم يتم توليد قيد العكس المحاسبي للمورد: {str(e)}")

            from financial.services.partner_currency_snapshot_updater import PartnerCurrencySnapshotUpdater
            PartnerCurrencySnapshotUpdater.trigger_on_commit(
                partner_type="supplier",
                partner_id=audit.supplier.id,
                currency_code="EGP",
                event_type="ALLOCATION_REVERSED"
            )

            return rev_audit

