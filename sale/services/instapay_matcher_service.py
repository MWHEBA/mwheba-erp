# -*- coding: utf-8 -*-
"""
FIN-INSTAPAY-MATCH: InstaPay & Bank Wire Matcher Service
خدمة مطابقة تحويلات إنستاباي والحوالات البنكية اللحظية مع أقساط المبيعات وإسقاط غرامات ما بعد التحويل
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
from sale.models.installments import InstallmentItem, InstallmentCashStatus, PlanStatus
from sale.models import SalePayment

logger = logging.getLogger(__name__)


class InstaPayMatcherService:
    """
    خدمة مطابقة التحويلات البنكية اللحظية (إنستاباي / سويفت):
    - مطابقة الحوالة بالقسط
    - تسجيل سند الدفع بالبنك وتوثيق instapay_reference
    - إسقاط غرامات التأخير الناتجة بعد تاريخ التحويل الفعلي
    - إطفاء الفائدة التمويلية للقسط
    """

    @classmethod
    def match_and_settle_installment(
        cls,
        installment_item: InstallmentItem,
        instapay_reference: str,
        amount: Decimal,
        bank_account=None,
        transfer_date=None,
        user=None,
        payer_name: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        مطابقة وتسوية قسط عبر تحويل إنستاباي أو حوالة بنكية فورية
        """
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))

        if amount <= Decimal("0.00"):
            raise ValidationError(_("يجب أن يكون مبلغ التحويل أكبر من الصفر."))

        if not instapay_reference or not instapay_reference.strip():
            raise ValidationError(_("يجب توفير الرقم المرجعي للتحويل اللحظي (InstaPay Reference)."))

        # التحقق من عدم استخدام المرجع سابقاً منعاً للتكرار
        if SalePayment.objects.filter(instapay_reference=instapay_reference, status="posted").exists():
            raise ValidationError(
                _("الرقم المرجعي لتحويل إنستاباي مسجل مسبقاً في عملية دفع سابقة.")
            )

        with transaction.atomic():
            locked_item = InstallmentItem.objects.select_for_update().get(pk=installment_item.pk)
            sale = locked_item.plan.sale
            customer = sale.customer

            remaining_due = locked_item.total_remaining_balance
            if amount > remaining_due:
                raise ValidationError(
                    _(f"مبلغ التحويل ({amount}) يتجاوز الرصيد الإجمالي المتبقي للقسط ({remaining_due}).")
                )

            eff_date = transfer_date or timezone.localdate()

            # 1. القيد المحاسبي: مدين البنك / دائن حساب العميل
            bank_acc = bank_account
            if not bank_acc:
                try:
                    bank_acc = AccountRoleRegistry.get_account(AccountRoleNames.BANK_ACCOUNT)
                except Exception:
                    bank_acc = ChartOfAccounts.objects.filter(code__in=['11020', '1102'], is_active=True).first()

            if not bank_acc:
                from financial.models import AccountType
                asset_type = AccountType.objects.filter(category='asset').first()
                if not asset_type:
                    asset_type, _ = AccountType.objects.get_or_create(
                        code='ASSET',
                        defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
                    )
                bank_acc = ChartOfAccounts.objects.create(
                    code='11020',
                    name='البنك التجاري الجاري',
                    account_type=asset_type,
                    is_active=True
                )

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

            gateway_lines = [
                JournalEntryLineData(
                    account_code=bank_acc.code,
                    debit=functional_amount,
                    credit=Decimal("0.00"),
                    description=f"تحويل إنستاباي - قسط #{locked_item.installment_number} فاتورة {sale.number} (مرجع: {instapay_reference})",
                    currency=curr_code,
                    exchange_rate=rate,
                ),
                JournalEntryLineData(
                    account_code=cust_acc.code,
                    debit=Decimal("0.00"),
                    credit=functional_amount,
                    description=f"سداد قسط #{locked_item.installment_number} فاتورة {sale.number} عبر إنستاباي",
                    currency=curr_code,
                    exchange_rate=rate,
                ),
            ]

            gateway = AccountingGateway()
            entry = gateway.create_journal_entry(
                source_module="sale",
                source_model="InstallmentItem",
                source_id=locked_item.id,
                lines=gateway_lines,
                idempotency_key=f"JE:INSTAPAY:{locked_item.id}:{instapay_reference}",
                user=user,
                entry_type="customer_payment",
                description=f"سداد قسط #{locked_item.installment_number} فاتورة {sale.number} عبر إنستاباي مرجع {instapay_reference}",
                reference=instapay_reference,
                date=eff_date,
            )

            # 2. إسقاط غرامات التأخير اللاحقة لتاريخ التحويل الفعلي
            if locked_item.penalty_amount > Decimal("0.00") and eff_date <= locked_item.due_date:
                locked_item.penalty_amount = Decimal("0.00")

            # 3. توزيع المبلغ وتحديث حالة القسط
            unpaid_interest = max(Decimal("0.00"), locked_item.interest_amount - locked_item.paid_interest - locked_item.waived_interest)
            interest_portion = min(amount, unpaid_interest)
            principal_portion = amount - interest_portion

            locked_item.paid_principal += principal_portion
            locked_item.paid_interest += interest_portion
            locked_item.paid_amount += amount

            if locked_item.total_remaining_balance <= Decimal("0.00"):
                locked_item.cash_status = InstallmentCashStatus.COLLECTED

            locked_item.save()

            # 4. تسجيل دفعة بالفاتورة مع المرجع
            payment = SalePayment.objects.create(
                sale=sale,
                installment_item=locked_item,
                amount=amount,
                payment_date=eff_date,
                payment_method="bank",
                source_type="INSTAPAY",
                instapay_reference=instapay_reference,
                third_party_payer_name=payer_name or "",
                financial_account=bank_acc,
                reference_number=instapay_reference,
                notes=f"تحويل إنستاباي رقم {instapay_reference} - قسط #{locked_item.installment_number}",
                created_by=user,
                status="posted",
                financial_status="synced"
            )

            sale.update_payment_status()

            # 5. إطفاء الفائدة التمويلية المؤجلة
            amort_entry = None
            try:
                amort_entry = InstallmentInterestAmortizationService.amortize_installment_interest(
                    installment_item=locked_item,
                    user=user,
                    posting_date=eff_date
                )
            except Exception as e:
                logger.warning(f"Amortization error in instapay matcher: {e}")

            # 6. تحديث حالة الخطة
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
                f"✅ تم بنجاح مطابقة وسداد قسط إنستاباي #{locked_item.id} "
                f"بمبلغ {amount} ومرجع {instapay_reference}"
            )

            return {
                "status": "SUCCESS",
                "installment_item": locked_item,
                "payment": payment,
                "journal_entry": entry,
                "amortization_entry": amort_entry,
                "instapay_reference": instapay_reference,
                "amount": amount,
            }
