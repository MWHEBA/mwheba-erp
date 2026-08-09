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
        target_amount = amount_to_allocate if amount_to_allocate is not None else amount
        if target_amount is None:
            raise ValidationError("المبلغ المراد تخصيصه مطلوب.")
        amount_to_allocate = Decimal(str(target_amount))

        if amount_to_allocate <= Decimal("0.00"):
            raise ValidationError("المبلغ المراد تخصيصه يجب أن يكون أكبر من صفر.")

        from utils.templatetags.utils_extras import smart_float
        from core.models import SystemSetting
        currency_sym = SystemSetting.get_setting('currency_symbol', 'ج.م')

        supplier = purchase.supplier
        open_bill_amount = purchase.total - (purchase.amount_paid or Decimal("0.00"))
        if amount_to_allocate > open_bill_amount:
            raise ValidationError(f"المبلغ المراد تخصيصه ({smart_float(amount_to_allocate)} {currency_sym}) يتجاوز المتبقي من الفاتورة ({smart_float(open_bill_amount)} {currency_sym}).")

        with transaction.atomic():
            # قفل المورد ودفعات المقدمة للحفاظ على نزاهة التزامن
            locked_supplier = Supplier.objects.select_for_update().get(pk=supplier.id)
            available_balance = cls.get_available_supplier_prepaid_balance(locked_supplier.id)

            if amount_to_allocate > available_balance:
                raise ValidationError(f"رصيد المورد المسبق المتاح ({smart_float(available_balance)} {currency_sym}) غير كافٍ لسداد المبلغ المطلوب ({smart_float(amount_to_allocate)} {currency_sym}).")

            # اختيار الدفعات المقدمة أقدم فأقدم (FIFO)
            advances = SupplierAdvancePayment.objects.select_for_update().filter(
                supplier_id=locked_supplier.id
            ).order_by("payment_date", "created_at")

            remaining_to_allocate = amount_to_allocate
            last_audit = None

            # الحصول على أو إنشاء معاملات الأستاذ الفرعي للفاتورة
            bill_txn, _ = SupplierTransaction.objects.select_for_update().get_or_create(
                supplier=locked_supplier,
                transaction_number=purchase.number,
                defaults={
                    "transaction_type": "BILL",
                    "issue_date": purchase.date,
                    "due_date": purchase.date,
                    "functional_amount": purchase.total,
                    "open_amount": purchase.total - (purchase.amount_paid or Decimal("0.00")),
                    "status": "OPEN" if (purchase.amount_paid or Decimal("0.00")) == Decimal("0.00") else "PARTIAL"
                }
            )

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

                # إنشاء/جلب معاملة الأستاذ الفرعي للدفعة المقدمة
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

                # تحديث معاملة الفاتورة
                bill_txn.open_amount = max(Decimal("0.00"), bill_txn.open_amount - curr_alloc)
                bill_txn.status = "CLOSED" if bill_txn.open_amount == 0 else "PARTIAL"
                bill_txn.save()

                # إنشاء توقيع SHA-256
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

                # تسجيل PurchasePayment مخصصة على الفاتورة لتعديل paid_amount وحالة السداد
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

            # تحديث حالة الدفع للفاتورة
            if hasattr(purchase, "update_payment_status"):
                purchase.update_payment_status()
            else:
                total_paid = sum(p.amount for p in purchase.payments.all())
                if total_paid >= purchase.total:
                    purchase.payment_status = "paid"
                elif total_paid > 0:
                    purchase.payment_status = "partial"
                else:
                    purchase.payment_status = "unpaid"
                purchase.save(update_fields=["payment_status"])

            # قيد التسوية المحاسبية إذا كان حساب الدفعات المقدمة مستقل
            try:
                if supplier.financial_account:
                    from financial.models import ChartOfAccounts
                    advance_acc = ChartOfAccounts.objects.filter(code="10500").first() # حساب دفعات مقدمة للموردين
                    if advance_acc:
                        lines = [
                            JournalEntryLineData(
                                account_code=supplier.financial_account.code,
                                debit=amount_to_allocate,
                                credit=Decimal("0.00"),
                                description=f"تسوية فاتورة مشتريات {purchase.number} - تخفيض دائنية المورد"
                            ),
                            JournalEntryLineData(
                                account_code=advance_acc.code,
                                debit=Decimal("0.00"),
                                credit=amount_to_allocate,
                                description=f"إغلاق دفعات مقدمة للمورد - فاتورة {purchase.number}"
                            )
                        ]
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
            except Exception as e:
                logger.warning(f"لم يتم توليد قيد التسوية المحاسبية التلقائي: {str(e)}")

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
                    status="posted"
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

                for adv in advances:
                    if remaining_for_bill <= Decimal("0.00"):
                        break

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
            return rev_audit

