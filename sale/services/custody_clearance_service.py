# -*- coding: utf-8 -*-
"""
FIN-CUSTODY-CLEAR: Custody Clearance Service
خدمة حوكمة التحصيل الميداني وأمانات التحصيل بالطريق (11030) وتوريد العهد للخزينة المركزية (11010)
"""
import logging
import uuid
from decimal import Decimal
from typing import Optional, Dict, Any, List

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from financial.models import ChartOfAccounts
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData
from sale.models.installments import InstallmentItem, InstallmentCashStatus
from sale.models import SalePayment

logger = logging.getLogger(__name__)


class CustodyClearanceService:
    """
    خدمة التحصيل الميداني وتوريد العهد:
    1. record_field_collection: تحصيل قسط ميدانياً -> مدين حـ/ نقدية بالطريق (11030) / دائن حـ/ العملاء، حالة القسط: COLLECTED_IN_TRANSIT
    2. clear_daily_custody: توريد العهدة للخزينة المركزية -> مدين حـ/ الخزينة (11010) / دائن حـ/ نقدية بالطريق (11030)، حالة القسط: COLLECTED
    """

    @classmethod
    def get_or_create_cash_in_transit_account(cls):
        """
        حساب نقدية بالطريق / عهد محصلين (11030)
        """
        from financial.models import AccountType
        acc = ChartOfAccounts.objects.filter(code__in=['11030', '1103'], is_active=True).first()
        if not acc:
            asset_type = AccountType.objects.filter(category='asset').first()
            if not asset_type:
                asset_type, _ = AccountType.objects.get_or_create(
                    code='ASSET',
                    defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
                )
            acc = ChartOfAccounts.objects.create(
                code='11030',
                name='نقدية بالطريق وعهد تحصيل',
                account_type=asset_type,
                is_active=True
            )
        return acc

    @classmethod
    def get_central_cash_account(cls):
        """
        حساب الخزينة المركزية (11010)
        """
        from financial.models import AccountType
        try:
            return AccountRoleRegistry.get_account(AccountRoleNames.CASH_ACCOUNT)
        except Exception:
            acc = ChartOfAccounts.objects.filter(code__in=['11010', '1101'], is_active=True).first()
            if not acc:
                asset_type = AccountType.objects.filter(category='asset').first()
                if not asset_type:
                    asset_type, _ = AccountType.objects.get_or_create(
                        code='ASSET',
                        defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
                    )
                acc = ChartOfAccounts.objects.create(
                    code='11010',
                    name='الخزينة الرئيسية',
                    account_type=asset_type,
                    is_active=True
                )
            return acc

    @classmethod
    def record_field_collection(
        cls,
        installment_item: InstallmentItem,
        collector,
        amount: Decimal,
        user=None,
        collection_date=None,
        receipt_number: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        تسجيل تحصيل ميداني بواسطة محصل:
        توجيه النقد لحساب نقدية بالطريق (11030) وتعليق القسط كـ COLLECTED_IN_TRANSIT
        """
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))

        if amount <= Decimal("0.00"):
            raise ValidationError(_("يجب أن يكون مبلغ التحصيل الميداني أكبر من الصفر."))

        with transaction.atomic():
            locked_item = InstallmentItem.objects.select_for_update().get(pk=installment_item.pk)
            sale = locked_item.plan.sale
            customer = sale.customer

            remaining_due = locked_item.total_remaining_balance
            if amount > remaining_due:
                raise ValidationError(
                    _(f"مبلغ التحصيل ({amount}) يتجاوز الرصيد الإجمالي المتبقي للقسط ({remaining_due}).")
                )

            eff_date = collection_date or timezone.localdate()
            receipt_ref = receipt_number or f"RECEIPT-{locked_item.id}-{uuid.uuid4().hex[:6]}"

            # 1. القيد المحاسبي: مدين 11030 (نقدية بالطريق) / دائن حساب العميل
            transit_acc = cls.get_or_create_cash_in_transit_account()
            from financial.services.subledger_account_service import SubledgerAccountService
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

            collector_name = collector.get_full_name() if hasattr(collector, "get_full_name") else str(collector)

            gateway_lines = [
                JournalEntryLineData(
                    account_code=transit_acc.code,
                    debit=functional_amount,
                    credit=Decimal("0.00"),
                    description=f"تحصيل ميداني بالطريق - قسط #{locked_item.installment_number} فاتورة {sale.number} (المحصل: {collector_name})",
                    currency=curr_code,
                    exchange_rate=rate,
                ),
                JournalEntryLineData(
                    account_code=cust_acc.code,
                    debit=Decimal("0.00"),
                    credit=functional_amount,
                    description=f"سداد قسط ميداني #{locked_item.installment_number} فاتورة {sale.number} (إيصال: {receipt_ref})",
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
                idempotency_key=f"JE:TRANSIT:{locked_item.id}:{eff_date.isoformat()}:{receipt_ref}",
                user=user,
                entry_type="customer_payment",
                description=f"تحصيل ميداني لقسط #{locked_item.installment_number} فاتورة {sale.number} بإيصال {receipt_ref}",
                reference=receipt_ref,
                date=eff_date,
            )

            # 2. توزيع النقد وتحديث القسط
            unpaid_interest = max(Decimal("0.00"), locked_item.interest_amount - locked_item.paid_interest - locked_item.waived_interest)
            interest_portion = min(amount, unpaid_interest)
            principal_portion = amount - interest_portion

            locked_item.paid_principal += principal_portion
            locked_item.paid_interest += interest_portion
            locked_item.paid_amount += amount
            locked_item.cash_status = InstallmentCashStatus.COLLECTED_IN_TRANSIT
            locked_item.save()

            # 3. تسجيل دفعة بالفاتورة
            SalePayment.objects.create(
                sale=sale,
                installment_item=locked_item,
                amount=amount,
                payment_date=eff_date,
                payment_method="cash",
                source_type="FIELD_COLLECTION",
                reference_number=receipt_ref,
                notes=f"تحصيل ميداني بواسطة {collector_name} - إيصال {receipt_ref}",
                created_by=user,
                status="posted",
                financial_status="synced"
            )

            sale.update_payment_status()

            logger.info(
                f"Field collection recorded for installment #{locked_item.id} "
                f"by {collector_name} (Amount: {amount})"
            )

            return {
                "status": "SUCCESS",
                "installment_item": locked_item,
                "journal_entry": entry,
                "amount": amount,
                "receipt_reference": receipt_ref,
            }

    @classmethod
    def clear_daily_custody(
        cls,
        collector,
        user=None,
        clearance_date=None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        توريد عهدة المحصل الميدانية للخزينة المركزية:
        - قيد تحويل: مدين الخزينة المركزية (11010) / دائن نقدية بالطريق (11030)
        - تحويل الأقساط من COLLECTED_IN_TRANSIT إلى COLLECTED
        - إطفاء الفائدة التمويلية المؤجلة للأقساط عبر InstallmentInterestAmortizationService
        """
        from financial.services.installment_amortization_service import InstallmentInterestAmortizationService

        eff_date = clearance_date or timezone.localdate()
        collector_name = collector.get_full_name() if hasattr(collector, "get_full_name") else str(collector)

        with transaction.atomic():
            # البحث عن الأقساط قيد النقل التي تم تحصيلها
            in_transit_items = InstallmentItem.objects.select_for_update().filter(
                cash_status=InstallmentCashStatus.COLLECTED_IN_TRANSIT
            )

            total_amount = sum(item.paid_amount for item in in_transit_items)
            if not in_transit_items.exists() or total_amount <= Decimal("0.00"):
                return {
                    "status": "NO_ITEMS",
                    "cleared_count": 0,
                    "total_cleared": Decimal("0.00"),
                }

            central_cash = cls.get_central_cash_account()
            transit_acc = cls.get_or_create_cash_in_transit_account()

            clearance_ref = f"CUSTODY-CLEAR-{uuid.uuid4().hex[:8]}"

            gateway_lines = [
                JournalEntryLineData(
                    account_code=central_cash.code,
                    debit=total_amount,
                    credit=Decimal("0.00"),
                    description=f"توريد عهدة تحصيل ميداني للخزينة - المحصل: {collector_name}",
                ),
                JournalEntryLineData(
                    account_code=transit_acc.code,
                    debit=Decimal("0.00"),
                    credit=total_amount,
                    description=f"إخلاء عهدة نقدية بالطريق - المحصل: {collector_name}",
                ),
            ]

            gateway = AccountingGateway()
            entry = gateway.create_journal_entry(
                source_module="sale",
                source_model="InstallmentItem",
                source_id=in_transit_items.first().id,
                lines=gateway_lines,
                idempotency_key=f"JE:CUSTODY:CLEAR:{eff_date.isoformat()}:{clearance_ref}",
                user=user,
                entry_type="cash_transfer",
                description=f"توريد عهدة تحصيل ميداني للخزينة المركزية من المحصل {collector_name}",
                reference=clearance_ref,
                date=eff_date,
            )

            # تحويل الأقساط إلى COLLECTED وإطفاء فوائدها
            cleared_count = 0
            for item in in_transit_items:
                item.cash_status = InstallmentCashStatus.COLLECTED
                item.save(update_fields=['cash_status'])
                cleared_count += 1

                # إطفاء الفائدة
                try:
                    InstallmentInterestAmortizationService.amortize_installment_interest(
                        installment_item=item,
                        user=user,
                        posting_date=eff_date
                    )
                except Exception as amort_err:
                    logger.warning(f"Amortization during custody clearance failed: {amort_err}")

            logger.info(
                f"✅ تم توريد عهدة المحصل {collector_name} للخزينة المركزية بمبلغ {total_amount} "
                f"لعدد {cleared_count} قسط (القيد #{entry.id})"
            )

            return {
                "status": "SUCCESS",
                "cleared_count": cleared_count,
                "total_cleared": total_amount,
                "journal_entry": entry,
                "clearance_reference": clearance_ref,
            }
