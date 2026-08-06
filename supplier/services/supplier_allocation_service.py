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
        amount_to_allocate: Decimal,
        user=None
    ) -> SupplierAllocationAudit:
        """
        تخصيص مبلغ من الرصيد المسبق/الدفعات المقدمة للمورد على فاتورة مشتريات
        مع استخدام select_for_update() للوقاية من Race Conditions وتوليد قيد التسوية
        """
        if amount_to_allocate <= Decimal("0.00"):
            raise ValidationError("المبلغ المراد تخصيصه يجب أن يكون أكبر من صفر.")

        supplier = purchase.supplier
        open_bill_amount = purchase.total - (purchase.amount_paid or Decimal("0.00"))
        if amount_to_allocate > open_bill_amount:
            raise ValidationError(f"المبلغ المراد تخصيصه ({amount_to_allocate}) يتجاوز المتبقي من الفاتورة ({open_bill_amount}).")

        with transaction.atomic():
            # قفل المورد ودفعات المقدمة للحفاظ على نزاهة التزامن
            locked_supplier = Supplier.objects.select_for_update().get(pk=supplier.id)
            available_balance = cls.get_available_supplier_prepaid_balance(locked_supplier.id)

            if amount_to_allocate > available_balance:
                raise ValidationError(f"المبلغ المراد تخصيصه ({amount_to_allocate}) يتجاوز الرصيد المسبق المتاح للمورد ({available_balance}).")

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
                    payment_date=now.date(),
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
