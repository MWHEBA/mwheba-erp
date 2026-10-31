# -*- coding: utf-8 -*-
"""
FIN-EARLY-SETTLE: Early Settlement Engine
محرك السداد المعجل المحاسبي المنضبط وفق معايير الحوكمة المالية الدقيقة لـ MWHEBA ERP
يفصل بين الفوائد المعترف بها وغير المكتسبة، ويرد الفائدة المدفوعة مقدماً، ويولد قيوداً مجمعة متزنة بالمليم
"""
import logging
import uuid
from decimal import Decimal
from typing import Optional, Dict, Any, List

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from financial.models import ChartOfAccounts, AccountType
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from financial.services.subledger_account_service import SubledgerAccountService
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData
from sale.models.installments import (
    InstallmentPlan,
    InstallmentItem,
    InstallmentCashStatus,
    InstallmentSettlement,
    PlanStatus,
)
from sale.models import Sale, SalePayment

logger = logging.getLogger(__name__)


class EarlySettlementService:
    """
    محرك السداد المعجل للأقساط:
    - اختيار الأقساط المؤهلة K بناءً على remaining_balance > 0 واستبعاد HOLD_REWORK
    - الفصل بين أصل الدين المتبقي الصافي ومصادر الفوائد
    - رد الفوائد المدفوعة مقدماً (Prepaid Interest) بخصمها من الأصل المطلوب
    - منع التحصيل السالب (سقف تسوية الأصل وترحيل الفائض كرصيد دائن مسبق)
    - توليد قيد مركب متزن بالمليم
    - تثبيت سجلات التسوية الدائمة وتحديث أرصدة الأقساط والفاتورة
    """

    @classmethod
    def get_or_create_financing_discount_account(cls):
        """حساب خصم مسموح به تمويلي (53200 - مصروف)"""
        acc = ChartOfAccounts.objects.filter(code__in=['53200', '5320'], is_active=True).first()
        if not acc:
            exp_type = AccountType.objects.filter(category='expense').first()
            if not exp_type:
                exp_type, _ = AccountType.objects.get_or_create(
                    code='EXP', defaults={'name': 'مصروفات', 'category': 'expense', 'nature': 'debit'}
                )
            acc = ChartOfAccounts.objects.create(
                code='53200',
                name='خصم تعجيل سداد تمويلي',
                account_type=exp_type,
                is_active=True
            )
        return acc

    @classmethod
    def get_or_create_unearned_interest_account(cls):
        """حساب فوائد تقسيط غير محققة (21400 - التزام)"""
        acc = ChartOfAccounts.objects.filter(code__in=['21400', '2140'], is_active=True).first()
        if not acc:
            liab_type = AccountType.objects.filter(category='liability').first()
            if not liab_type:
                liab_type, _ = AccountType.objects.get_or_create(
                    code='LIAB', defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'}
                )
            acc = ChartOfAccounts.objects.create(
                code='21400',
                name='فوائد تقسيط غير محققة',
                account_type=liab_type,
                is_active=True
            )
        return acc

    @classmethod
    def get_or_create_customer_prepaid_account(cls):
        """حساب أرصدة دائنة للعملاء (21020 - التزام)"""
        try:
            return AccountRoleRegistry.get_account(AccountRoleNames.CUSTOMER_ADVANCE_LIABILITY)
        except Exception:
            acc = ChartOfAccounts.objects.filter(code__in=['21020', '2102'], is_active=True).first()
            if not acc:
                liab_type = AccountType.objects.filter(category='liability').first()
                if not liab_type:
                    liab_type, _ = AccountType.objects.get_or_create(
                        code='LIAB', defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'}
                    )
                acc = ChartOfAccounts.objects.create(
                    code='21020',
                    name='أرصدة دائنة للعملاء ودفعات مقدمة',
                    account_type=liab_type,
                    is_active=True
                )
            return acc

    @classmethod
    def calculate_early_settlement(
        cls,
        sale: Sale,
        items: Optional[List[InstallmentItem]] = None,
        early_discount_amount: Decimal = Decimal('0.00'),
        early_discount_rate: Optional[Decimal] = None
    ) -> Dict[str, Any]:
        """
        حساب مؤشرات السداد المعجل رياضياً ومحاسبياً دون إجراء تعديل دفتري:
        - تحديد الأقساط المؤهلة K
        - استخراج Settlement Principal, Remaining Interest Debt, Unearned in 21400
        - احتساب Prepaid Interest و Accrued Unpaid Interest
        - حساب Net Due وتحديد ما إذا كان الفرع (أ) سداداً نقدياً أو الفرع (ب) رداً لزيادة
        """
        if not hasattr(sale, 'installment_plan') or not sale.installment_plan:
            raise ValidationError(_("هذه الفاتورة ليست فاتورة تقسيط ولا تملك خطة سداد."))

        plan = sale.installment_plan

        # 1. تحديد الأقساط المؤهلة K (المتبقي فيها رصيد حقيقي بعد المدفوع والتسويات السارية وليست بحالة نزاع فني)
        if items is None:
            all_items = list(plan.items.exclude(
                cash_status=InstallmentCashStatus.HOLD_REWORK
            ).order_by('installment_number'))
            qualified_items = [it for it in all_items if it.remaining_balance > Decimal('0.00')]
        else:
            qualified_items = [
                it for it in items
                if it.remaining_balance > Decimal('0.00') and it.cash_status != InstallmentCashStatus.HOLD_REWORK
            ]

        if not qualified_items:
            raise ValidationError(_("لا توجد أقساط مؤهلة للسداد المعجل."))

        # 2. الفصل المحاسبي بين مبالغ الأصل والفوائد
        settlement_principal = sum(it.remaining_principal for it in qualified_items)
        remaining_interest_debt = sum(it.remaining_interest for it in qualified_items)
        customer_real_debt = settlement_principal + remaining_interest_debt

        # الرصيد الدفتري الفعلي القائم للمؤجل بحساب 21400
        unearned_in_21400 = sum(it.unearned_interest_balance for it in qualified_items)

        # فحص الفائدة المدفوعة مقدماً مقابل المعترف بها
        prepaid_interest = sum(
            max(Decimal('0.00'), it.paid_interest - it.recognized_interest)
            for it in qualified_items
        )
        accrued_unpaid_interest = sum(
            max(Decimal('0.00'), it.recognized_interest - it.paid_interest)
            for it in qualified_items
        )

        effective_principal_due = settlement_principal - prepaid_interest

        # خصم التعجيل
        if early_discount_rate is not None and early_discount_rate > Decimal('0.00'):
            discount_amount = (settlement_principal * (early_discount_rate / Decimal('100.00'))).quantize(Decimal('0.01'))
        else:
            discount_amount = Decimal(str(early_discount_amount or '0.00'))

        # صافي المستحق
        net_due = (settlement_principal - prepaid_interest + accrued_unpaid_interest) - discount_amount

        # تفريع الحسابات
        if net_due >= Decimal('0.00'):
            # الفرع (أ) - العميل مدين بمبلغ صافٍ
            branch = 'A'
            cash_for_principal = effective_principal_due - discount_amount
            cash_for_accrued_interest = accrued_unpaid_interest
            final_cash_required = net_due
            principal_rebate_offset = min(settlement_principal, prepaid_interest)
            customer_net_refund_amount = Decimal('0.00')
        else:
            # الفرع (ب) - العميل دائن بالصافي
            branch = 'B'
            final_cash_required = Decimal('0.00')
            cash_for_principal = Decimal('0.00')
            cash_for_accrued_interest = Decimal('0.00')
            principal_rebate_offset = settlement_principal
            customer_net_refund_amount = abs(net_due)

        waived_interest_settlement = max(Decimal('0.00'), remaining_interest_debt - accrued_unpaid_interest)

        return {
            "sale": sale,
            "plan": plan,
            "qualified_items": qualified_items,
            "items_count": len(qualified_items),
            "settlement_principal": settlement_principal,
            "remaining_interest_debt": remaining_interest_debt,
            "customer_real_debt": customer_real_debt,
            "unearned_in_21400": unearned_in_21400,
            "prepaid_interest": prepaid_interest,
            "accrued_unpaid_interest": accrued_unpaid_interest,
            "effective_principal_due": effective_principal_due,
            "discount_amount": discount_amount,
            "net_due": net_due,
            "branch": branch,
            "final_cash_required": final_cash_required,
            "cash_for_principal": cash_for_principal,
            "cash_for_accrued_interest": cash_for_accrued_interest,
            "principal_rebate_offset": principal_rebate_offset,
            "customer_net_refund_amount": customer_net_refund_amount,
            "waived_interest_settlement": waived_interest_settlement,
        }

    @classmethod
    def execute_early_settlement(
        cls,
        sale: Sale,
        items: Optional[List[InstallmentItem]] = None,
        early_discount_amount: Decimal = Decimal('0.00'),
        early_discount_rate: Optional[Decimal] = None,
        payment_method: str = "cash",
        financial_account=None,
        user=None,
        posting_date=None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        تنفيذ السداد المعجل ذرياً وتوليد القيد المحاسبي المجمع وتثبيت سجلات التسوية
        """
        with transaction.atomic():
            locked_sale = Sale.objects.select_for_update().get(pk=sale.pk)
            customer = locked_sale.customer
            calc = cls.calculate_early_settlement(
                sale=locked_sale,
                items=items,
                early_discount_amount=early_discount_amount,
                early_discount_rate=early_discount_rate
            )

            eff_date = posting_date or timezone.localdate()
            batch_id = f"ES-{locked_sale.id}-{uuid.uuid4().hex[:8]}"

            # 1. تحديد الحسابات
            # حـ/ الخزينة أو البنك
            cash_acc = financial_account
            if not cash_acc:
                if payment_method == "bank":
                    try:
                        cash_acc = AccountRoleRegistry.get_account(AccountRoleNames.BANK_ACCOUNT)
                    except Exception:
                        cash_acc = ChartOfAccounts.objects.filter(code__in=['11020', '1102'], is_active=True).first()
                else:
                    try:
                        cash_acc = AccountRoleRegistry.get_account(AccountRoleNames.CASH_ACCOUNT)
                    except Exception:
                        cash_acc = ChartOfAccounts.objects.filter(code__in=['11010', '1101'], is_active=True).first()

            # حـ/ العملاء التجاري
            cust_acc = None
            try:
                cust_acc = SubledgerAccountService.get_or_create_customer_account(customer, user=user)
            except Exception:
                pass
            if not cust_acc:
                cust_acc = AccountRoleRegistry.get_account(AccountRoleNames.CUSTOMER_CONTROL)

            # حـ/ خصم مسموح به تمويلي (53200)
            discount_acc = cls.get_or_create_financing_discount_account()

            # حـ/ فوائد تقسيط غير محققة (21400)
            unearned_acc = cls.get_or_create_unearned_interest_account()

            # حـ/ أرصدة دائنة للعملاء (21020)
            prepaid_acc = cls.get_or_create_customer_prepaid_account()

            rate = Decimal(str(locked_sale.exchange_rate or "1.000000"))
            curr_code = locked_sale.currency.code if locked_sale.currency else "EGP"

            # 2. بناء سطور القيد المجمع المتزن
            gateway_lines = []

            if calc["branch"] == 'A':
                # الفرع (أ): سداد نقدي من العميل
                if calc["final_cash_required"] > Decimal('0.00'):
                    cash_func = (calc["final_cash_required"] * rate).quantize(Decimal("0.01"))
                    gateway_lines.append(
                        JournalEntryLineData(
                            account_code=cash_acc.code,
                            debit=cash_func,
                            credit=Decimal("0.00"),
                            description=f"تحصيل سداد معجل نقدي - فاتورة {locked_sale.number}",
                            currency=curr_code,
                            exchange_rate=rate,
                        )
                    )

                if calc["discount_amount"] > Decimal('0.00'):
                    disc_func = (calc["discount_amount"] * rate).quantize(Decimal("0.01"))
                    gateway_lines.append(
                        JournalEntryLineData(
                            account_code=discount_acc.code,
                            debit=disc_func,
                            credit=Decimal("0.00"),
                            description=f"خصم تعجيل سداد تمويلي - فاتورة {locked_sale.number}",
                            currency=curr_code,
                            exchange_rate=rate,
                        )
                    )

                if calc["unearned_in_21400"] > Decimal('0.00'):
                    unearned_func = (calc["unearned_in_21400"] * rate).quantize(Decimal("0.01"))
                    gateway_lines.append(
                        JournalEntryLineData(
                            account_code=unearned_acc.code,
                            debit=unearned_func,
                            credit=Decimal("0.00"),
                            description=f"إقفال رصيد فوائد تقسيط مؤجلة بالسداد المعجل - فاتورة {locked_sale.number}",
                            currency=curr_code,
                            exchange_rate=rate,
                        )
                    )

                if calc["customer_real_debt"] > Decimal('0.00'):
                    cust_func = (calc["customer_real_debt"] * rate).quantize(Decimal("0.01"))
                    gateway_lines.append(
                        JournalEntryLineData(
                            account_code=cust_acc.code,
                            debit=Decimal("0.00"),
                            credit=cust_func,
                            description=f"إقفال مديونية العميل بالسداد المعجل - فاتورة {locked_sale.number}",
                            currency=curr_code,
                            exchange_rate=rate,
                        )
                    )

            else:
                # الفرع (ب): رد زيادة للعميل / ترحيل لرصيد مسبق
                if calc["unearned_in_21400"] > Decimal('0.00'):
                    unearned_func = (calc["unearned_in_21400"] * rate).quantize(Decimal("0.01"))
                    gateway_lines.append(
                        JournalEntryLineData(
                            account_code=unearned_acc.code,
                            debit=unearned_func,
                            credit=Decimal("0.00"),
                            description=f"إقفال رصيد فوائد تقسيط غير محققة بالسداد المعجل - فاتورة {locked_sale.number}",
                            currency=curr_code,
                            exchange_rate=rate,
                        )
                    )

                if calc["customer_real_debt"] > Decimal('0.00'):
                    cust_func = (calc["customer_real_debt"] * rate).quantize(Decimal("0.01"))
                    gateway_lines.append(
                        JournalEntryLineData(
                            account_code=cust_acc.code,
                            debit=Decimal("0.00"),
                            credit=cust_func,
                            description=f"إقفال كامل مديونية العميل المتبقية - فاتورة {locked_sale.number}",
                            currency=curr_code,
                            exchange_rate=rate,
                        )
                    )

                if calc["customer_net_refund_amount"] > Decimal('0.00'):
                    ref_func = (calc["customer_net_refund_amount"] * rate).quantize(Decimal("0.01"))
                    gateway_lines.append(
                        JournalEntryLineData(
                            account_code=prepaid_acc.code,
                            debit=Decimal("0.00"),
                            credit=ref_func,
                            description=f"ترحيل رصيد دائن مسبق للعميل ناتج عن رد فائدة معجلة - فاتورة {locked_sale.number}",
                            currency=curr_code,
                            exchange_rate=rate,
                        )
                    )

            # 3. ترحيل القيد عبر AccountingGateway
            gateway = AccountingGateway()
            entry = gateway.create_journal_entry(
                source_module="sale",
                source_model="InstallmentPlan",
                source_id=calc["plan"].id,
                lines=gateway_lines,
                idempotency_key=f"JE:EARLY_SETTLE:{batch_id}",
                user=user,
                entry_type="early_settlement",
                description=f"قيد سداد معجل وتسوية فوائد مؤجلة لحزمة {batch_id} - فاتورة {locked_sale.number}",
                reference=batch_id,
                date=eff_date,
            )

            if not entry:
                raise ValidationError(_("فشلت بوابة القيود في ترحيل قيد السداد المعجل."))

            # 4. تسجيل سند النقدية SalePayment (إذا كان مطلوب كاش)
            payment = None
            if calc["final_cash_required"] > Decimal('0.00'):
                payment = SalePayment.objects.create(
                    sale=locked_sale,
                    batch_id=batch_id,
                    amount=calc["final_cash_required"],
                    payment_date=eff_date,
                    payment_method=payment_method,
                    source_type="EARLY_SETTLEMENT",
                    reference_number=batch_id,
                    financial_account=cash_acc,
                    notes=f"سداد معجل نقدي لحزمة {batch_id}",
                    created_by=user,
                    status="posted",
                    financial_status="synced"
                )

            # إذا وُجد رصيد مردود للعميل (الفرع ب)، نخفض مديونية العميل / نزيد رصيده الدائن
            if calc["customer_net_refund_amount"] > Decimal('0.00'):
                if hasattr(customer, 'balance'):
                    customer.balance = getattr(customer, 'balance', Decimal('0.00')) - calc["customer_net_refund_amount"]
                    customer.save(update_fields=['balance'])
                if hasattr(customer, 'prepaid_balance'):
                    customer.prepaid_balance = getattr(customer, 'prepaid_balance', Decimal('0.00')) + calc["customer_net_refund_amount"]
                    customer.save(update_fields=['prepaid_balance'])

            # 5. تثبيت سجلات التسوية الدائمة InstallmentSettlement
            settlements = []

            # أ) خصم التعجيل
            if calc["discount_amount"] > Decimal('0.00'):
                s_disc = InstallmentSettlement.objects.create(
                    sale=locked_sale,
                    batch_id=batch_id,
                    settlement_type=InstallmentSettlement.SettlementType.EARLY_SETTLEMENT_DISCOUNT,
                    amount=calc["discount_amount"],
                    journal_entry=entry,
                    status="POSTED",
                    affects_invoice_due=True,
                    notes=f"خصم تعجيل سداد ممنوح على أصل الدين - حزمة {batch_id}",
                    created_by=user,
                )
                settlements.append(s_disc)

            # ب) إسقاط الفوائد غير المستحقة
            if calc["waived_interest_settlement"] > Decimal('0.00'):
                s_waiver = InstallmentSettlement.objects.create(
                    sale=locked_sale,
                    batch_id=batch_id,
                    settlement_type=InstallmentSettlement.SettlementType.INTEREST_WAIVER,
                    amount=calc["waived_interest_settlement"],
                    journal_entry=entry,
                    status="POSTED",
                    affects_invoice_due=True,
                    notes=f"إسقاط فوائد تقسيط مؤجلة غير مكتسبة لتعجيل السداد - حزمة {batch_id}",
                    created_by=user,
                )
                settlements.append(s_waiver)

            # ج) رد الفائدة المدفوعة مقدماً
            if calc["prepaid_interest"] > Decimal('0.00'):
                debt_rebate_offset = max(Decimal('0.00'), calc["prepaid_interest"] - calc["customer_net_refund_amount"])
                if debt_rebate_offset > Decimal('0.00'):
                    s_rebate = InstallmentSettlement.objects.create(
                        sale=locked_sale,
                        batch_id=batch_id,
                        settlement_type=InstallmentSettlement.SettlementType.PREPAID_INTEREST_REBATE,
                        amount=debt_rebate_offset,
                        journal_entry=entry,
                        status="POSTED",
                        affects_invoice_due=True,
                        notes=f"رد فوائد مسددة مقدماً وخصمها من أصل الدين - حزمة {batch_id}",
                        created_by=user,
                    )
                    settlements.append(s_rebate)

                if calc["customer_net_refund_amount"] > Decimal('0.00'):
                    s_refund = InstallmentSettlement.objects.create(
                        sale=locked_sale,
                        batch_id=batch_id,
                        settlement_type=InstallmentSettlement.SettlementType.PREPAID_INTEREST_REBATE,
                        amount=calc["customer_net_refund_amount"],
                        journal_entry=entry,
                        status="POSTED",
                        affects_invoice_due=False,
                        notes=f"رد فوائد مسددة مقدماً كرصيد مردود للعميل - حزمة {batch_id}",
                        created_by=user,
                    )
                    settlements.append(s_refund)

            # حفظ لقطة الحالة السابقة للأقساط في سجل التدقيق لضمان دقة العكس المستقبلي
            items_snapshot = []
            for it in calc["qualified_items"]:
                snap_it = InstallmentItem.objects.select_for_update().get(pk=it.pk)
                items_snapshot.append({
                    "item_id": snap_it.id,
                    "paid_principal": str(snap_it.paid_principal),
                    "paid_interest": str(snap_it.paid_interest),
                    "paid_amount": str(snap_it.paid_amount),
                    "settled_principal": str(snap_it.settled_principal),
                    "waived_interest": str(snap_it.waived_interest),
                    "rebated_interest": str(snap_it.rebated_interest),
                    "is_interest_recognized": snap_it.is_interest_recognized,
                    "cash_status": snap_it.cash_status,
                })

            from sale.models import InstallmentOperationAudit
            InstallmentOperationAudit.objects.create(
                plan=calc["plan"],
                action="EARLY_SETTLEMENT",
                idempotency_key=f"EARLY_SETTLEMENT:{batch_id}",
                payload={
                    "batch_id": batch_id,
                    "branch": calc["branch"],
                    "customer_net_refund_amount": str(calc["customer_net_refund_amount"]),
                    "items": items_snapshot,
                },
            )

            # 6. تحديث عناصر الأقساط المسددة ذرياً وشاملاً
            # توزيع المبالغ على الأقساط المختارة
            for it in calc["qualified_items"]:
                locked_it = InstallmentItem.objects.select_for_update().get(pk=it.pk)

                # حصة القسط من النقد والأصل والفوائد
                # تصفير المتبقي على القسط تماماً
                rem_p = locked_it.remaining_principal
                rem_i = locked_it.remaining_interest
                unearned_i = locked_it.unearned_interest_balance

                # الفوائد المقدمة الخاصة بهذا القسط
                it_prepaid = max(Decimal('0.00'), locked_it.paid_interest - locked_it.recognized_interest)
                it_accrued_unpaid = max(Decimal('0.00'), locked_it.recognized_interest - locked_it.paid_interest)

                it_waived = max(Decimal('0.00'), rem_i - it_accrued_unpaid)

                # نسبة خصم التعجيل لهذا القسط
                it_discount = Decimal('0.00')
                if calc["settlement_principal"] > Decimal('0.00') and calc["discount_amount"] > Decimal('0.00'):
                    ratio = rem_p / calc["settlement_principal"]
                    it_discount = (calc["discount_amount"] * ratio).quantize(Decimal('0.01'))

                it_rebate_offset = min(rem_p, it_prepaid)
                it_cash_p = max(Decimal('0.00'), rem_p - it_rebate_offset - it_discount)
                it_cash_i = it_accrued_unpaid

                locked_it.paid_principal += it_cash_p
                locked_it.paid_interest += it_cash_i
                locked_it.paid_amount += (it_cash_p + it_cash_i)
                locked_it.settled_principal += (it_rebate_offset + it_discount)
                locked_it.waived_interest += it_waived
                locked_it.rebated_interest += it_prepaid
                locked_it.cash_status = InstallmentCashStatus.COLLECTED
                locked_it.is_interest_recognized = True
                locked_it.save()

            # 7. تحديث رصيد الفاتورة وحالة الخطة
            locked_sale.update_payment_status()

            plan = calc["plan"]
            all_items_rem = sum(it.remaining_balance for it in plan.items.all())
            if all_items_rem <= Decimal('0.00'):
                plan.status = PlanStatus.COMPLETED
            elif plan.items.filter(cash_status=InstallmentCashStatus.HOLD_REWORK).exists():
                plan.status = PlanStatus.DISPUTED
            else:
                plan.status = PlanStatus.ACTIVE
            plan.save(update_fields=['status'])

            logger.info(
                f"✅ تم تنفيذ السداد المعجل بنجاح للحزمة {batch_id} - فاتورة {locked_sale.number} "
                f"(القيد #{entry.id}) [الفرع: {calc['branch']}]"
            )

            return {
                "status": "SUCCESS",
                "batch_id": batch_id,
                "journal_entry": entry,
                "payment": payment,
                "settlements": settlements,
                "calculations": calc,
            }
