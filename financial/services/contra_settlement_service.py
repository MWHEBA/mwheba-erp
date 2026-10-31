# -*- coding: utf-8 -*-
"""
FIN-CONTRA-SETTLE: Partner Contra Settlement Service
خدمة تنفيذ مقاصة حسابات الشركاء (موردين / عملاء) لتسوية أقساط المبيعات مع إطفاء الفوائد وتوثيق الأستاذ العام
"""
import logging
import uuid
from decimal import Decimal
from typing import Optional, Dict, Any

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from financial.models import ChartOfAccounts
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from financial.services.subledger_account_service import SubledgerAccountService
from financial.services.installment_amortization_service import InstallmentInterestAmortizationService
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData
from sale.models.installments import (
    InstallmentItem,
    InstallmentCashStatus,
    InstallmentSettlement,
    PlanStatus,
)
from sale.models import SalePayment

logger = logging.getLogger(__name__)


class PartnerContraSettlementService:
    """
    خدمة المقاصة بين مستحقات المورد وديون أقساط العميل:
    - التحقق من أرصدة القسط والمديونية
    - إنشاء قيد يومية متزن: مدين حـ/ الموردين (21010/21110) / دائن حـ/ العملاء (11010)
    - استدعاء إطفاء الفائدة التمويلية المؤجلة للقسط عبر InstallmentInterestAmortizationService
    - تحديث مبالغ القسط وحالته النقدية إلى COLLECTED_CONTRA
    - إنشاء سجل تسوية تعاقدي دائم وسند سداد بالفاتورة
    """

    @classmethod
    def execute_contra_settlement(
        cls,
        installment_item: InstallmentItem,
        supplier,
        amount: Decimal,
        user=None,
        contra_ref: Optional[str] = None,
        posting_date=None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        تنفيذ مقاصة الموردين مع قسط العميل
        """
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))

        if amount <= Decimal("0.00"):
            raise ValidationError(_("يجب أن يكون مبلغ المقاصة أكبر من الصفر."))

        if not supplier:
            raise ValidationError(_("يجب تحديد المورد المراد إجراء المقاصة معه."))

        with transaction.atomic():
            locked_item = InstallmentItem.objects.select_for_update().get(pk=installment_item.pk)
            sale = locked_item.plan.sale
            customer = sale.customer

            remaining_due = locked_item.total_remaining_balance
            if amount > remaining_due:
                raise ValidationError(
                    _(f"مبلغ المقاصة ({amount}) يتجاوز الرصيد الإجمالي المتبقي للقسط ({remaining_due}).")
                )

            effective_date = posting_date or timezone.localdate()
            if not contra_ref:
                contra_ref = f"CONTRA-SETTLE-{locked_item.id}-{uuid.uuid4().hex[:8]}"

            # 1. تحديد حسابات الأستاذ العام والمساعد
            # حساب المورد (مدين لتخفيض الالتزام)
            supplier_acc = None
            try:
                supplier_acc = SubledgerAccountService.get_or_create_supplier_account(supplier, user=user)
            except Exception:
                pass
            if not supplier_acc:
                supplier_acc = AccountRoleRegistry.get_account(AccountRoleNames.SUPPLIER_PAYABLE_CONTROL)

            # حساب العميل (دائن لتخفيض مديونية العميل)
            cust_acc = None
            try:
                cust_acc = SubledgerAccountService.get_or_create_customer_account(customer, user=user)
            except Exception:
                pass
            if not cust_acc:
                cust_acc = AccountRoleRegistry.get_account(AccountRoleNames.CUSTOMER_CONTROL)

            rate = Decimal(str(sale.exchange_rate or "1.000000"))
            curr_code = sale.currency.code if sale.currency else "EGP"
            functional_amount = (amount * rate).quantize(Decimal("0.01"))

            # 2. إنشاء قيد المقاصة المتزن
            gateway_lines = [
                JournalEntryLineData(
                    account_code=supplier_acc.code,
                    debit=functional_amount,
                    credit=Decimal("0.00"),
                    description=f"تسوية مقاصة موردين - سداد قسط #{locked_item.installment_number} فاتورة {sale.number} (مورد: {supplier.name})",
                    currency=curr_code,
                    exchange_rate=rate,
                ),
                JournalEntryLineData(
                    account_code=cust_acc.code,
                    debit=Decimal("0.00"),
                    credit=functional_amount,
                    description=f"تسوية مقاصة عملاء - سداد قسط #{locked_item.installment_number} فاتورة {sale.number} (عميل: {customer.name})",
                    currency=curr_code,
                    exchange_rate=rate,
                ),
            ]

            gateway = AccountingGateway()
            contra_entry = gateway.create_journal_entry(
                source_module="sale",
                source_model="InstallmentItem",
                source_id=locked_item.id,
                lines=gateway_lines,
                idempotency_key=f"JE:CONTRA:{locked_item.id}:{effective_date.isoformat()}:{contra_ref}",
                user=user,
                entry_type="contra_settlement",
                description=f"تسوية مقاصة موردين/عملاء لقسط #{locked_item.installment_number} فاتورة {sale.number}",
                reference=contra_ref,
                date=effective_date,
            )

            if not contra_entry:
                raise ValidationError(_("فشلت بوابة القيود في ترحيل قيد المقاصة بين المورد والعميل."))

            # 3. إطفاء الفائدة التمويلية المؤجلة إن وُجدت
            amort_entry = None
            try:
                amort_entry = InstallmentInterestAmortizationService.amortize_installment_interest(
                    installment_item=locked_item,
                    user=user,
                    posting_date=effective_date
                )
            except Exception as amort_err:
                logger.warning(f"Interest amortization during contra failed or skipped: {amort_err}")

            # 4. توزيع مبلغ المقاصة بين الفائدة والأصل
            # الأولوية للفوائد المستحقة ثم الأصل
            unpaid_interest = max(Decimal("0.00"), locked_item.interest_amount - locked_item.paid_interest - locked_item.waived_interest)
            interest_portion = min(amount, unpaid_interest)
            principal_portion = amount - interest_portion

            locked_item.paid_principal += principal_portion
            locked_item.paid_interest += interest_portion
            locked_item.paid_amount += amount

            # إذا تم تغطية القسط بالكامل يتحول لـ COLLECTED_CONTRA
            if locked_item.total_remaining_balance <= Decimal("0.00"):
                locked_item.cash_status = InstallmentCashStatus.COLLECTED_CONTRA

            locked_item.contra_settlement_reference = contra_ref
            locked_item.save()

            # 5. تسجيل تسوية تعاقدية دائمة InstallmentSettlement (غير مكررة الأثر على المديونية نظراً لإنشاء SalePayment)
            settlement_record = InstallmentSettlement.objects.create(
                sale=sale,
                installment_item=locked_item,
                settlement_type=InstallmentSettlement.SettlementType.CONTRA_SETTLEMENT,
                amount=amount,
                journal_entry=contra_entry,
                status="POSTED",
                affects_invoice_due=False,
                notes=notes or f"مقاصة مع المورد {supplier.name} بموجب المرجع {contra_ref}",
                created_by=user,
            )

            # 6. تسجيل دفعة بالفاتورة SalePayment
            SalePayment.objects.create(
                sale=sale,
                installment_item=locked_item,
                amount=amount,
                payment_date=effective_date,
                payment_method="contra",
                source_type="CONTRA",
                reference_number=contra_ref,
                financial_account=None,
                notes=f"تسوية مقاصة موردين مع {supplier.name} - قسط #{locked_item.installment_number}",
                created_by=user,
                status="posted",
                financial_status="synced"
            )

            # 7. تحديث حالة الفاتورة والخطة
            sale.update_payment_status()

            plan = locked_item.plan
            all_collected = not plan.items.filter(
                cash_status__in=[
                    InstallmentCashStatus.PENDING,
                    InstallmentCashStatus.OVERDUE,
                    InstallmentCashStatus.BOUNCED
                ]
            ).exists()
            if all_collected and sale.amount_due <= Decimal("0.00"):
                plan.status = PlanStatus.COMPLETED
                plan.save(update_fields=['status'])

            logger.info(
                f"✅ تم تنفيذ المقاصة بنجاح للقسط #{locked_item.id} بمبلغ {amount} "
                f"مع المورد {supplier.name} (القيد #{contra_entry.id})"
            )

            return {
                "status": "SUCCESS",
                "installment_item": locked_item,
                "contra_entry": contra_entry,
                "amortization_entry": amort_entry,
                "settlement_record": settlement_record,
                "amount": amount,
                "principal_portion": principal_portion,
                "interest_portion": interest_portion,
            }
