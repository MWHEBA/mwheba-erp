# -*- coding: utf-8 -*-
"""
FIN-SAL-INS-AMORT: Installment Interest Amortization Service
خدمة استهلاك وإطفاء الفوائد التمويلية المؤجلة للأقساط المستحقة وربطها بإقفال الفترة المحاسبية
"""
import logging
from decimal import Decimal
from typing import Optional, Dict, Any, List

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from sale.models.installments import InstallmentItem, InstallmentCashStatus
from financial.models import JournalEntry, ChartOfAccounts, AccountingPeriod
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData

logger = logging.getLogger(__name__)


class InstallmentInterestAmortizationService:
    """
    خدمة موحدة لإطفاء الفوائد المؤجلة وإثبات إيراد التمويل المحقق
    Dr. 21400 فوائد تقسيط غير محققة
        Cr. 42200 إيرادات فوائد تقسيط محققة
    """

    @classmethod
    def get_or_create_accounts(cls):
        from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
        from financial.models import AccountType
        unearned_acc = None
        realized_acc = None
        try:
            unearned_acc = AccountRoleRegistry.get_account("UNEARNED_INSTALLMENT_INTEREST")
        except Exception:
            pass
        if not unearned_acc:
            liab_type = AccountType.objects.filter(nature="credit").first()
            unearned_acc, _ = ChartOfAccounts.objects.get_or_create(
                code="21400",
                defaults={"name": "فوائد تقسيط غير محققة", "account_type": liab_type, "is_active": True}
            )

        try:
            realized_acc = AccountRoleRegistry.get_account("REALIZED_INSTALLMENT_INTEREST")
        except Exception:
            pass
        if not realized_acc:
            rev_type = AccountType.objects.filter(nature="credit").first()
            realized_acc, _ = ChartOfAccounts.objects.get_or_create(
                code="42200",
                defaults={"name": "إيرادات فوائد تقسيط محققة", "account_type": rev_type, "is_active": True}
            )

        return unearned_acc, realized_acc

    @classmethod
    def amortize_installment_interest(
        cls,
        installment_item: InstallmentItem,
        user=None,
        posting_date=None,
        amount: Optional[Decimal] = None
    ) -> Optional[JournalEntry]:
        """
        إطفاء الفائدة التمويلية المؤجلة لقسط محدد وترحيل قيد الاستهلاك
        """
        if installment_item.is_interest_recognized:
            return None

        amort_amount = amount or installment_item.unearned_interest_balance
        if amort_amount <= Decimal("0.00"):
            return None

        post_date = posting_date or timezone.localdate()
        unearned_acc, realized_acc = cls.get_or_create_accounts()
        sale = installment_item.plan.sale
        cost_center = getattr(sale, 'cost_center', None)

        gateway = AccountingGateway()
        idemp = f"JE:sale:InstallmentItem:{installment_item.id}:amortize"
        entry = gateway.create_journal_entry(
            source_module="sale",
            source_model="InstallmentItem",
            source_id=installment_item.id,
            lines=[
                JournalEntryLineData(
                    account_code=unearned_acc.code,
                    debit=amort_amount,
                    credit=Decimal("0.00"),
                    description=f"إطفاء فوائد مؤجلة قسط #{installment_item.installment_number}",
                    cost_center=cost_center.code if cost_center else None
                ),
                JournalEntryLineData(
                    account_code=realized_acc.code,
                    debit=Decimal("0.00"),
                    credit=amort_amount,
                    description=f"إيراد فوائد تقسيط محققة قسط #{installment_item.installment_number}",
                    cost_center=cost_center.code if cost_center else None
                ),
            ],
            idempotency_key=idemp,
            user=user,
            entry_type="installment_amortization",
            date=post_date,
            description=f"إطفاء فوائد تقسيط مستحقة قسط #{installment_item.installment_number} - فاتورة {sale.number}",
            reference=f"AMORT-INS-{installment_item.id}",
        )
        if entry:
            installment_item.recognized_interest += amort_amount
            installment_item.is_interest_recognized = True
            installment_item.recognized_interest_entry = entry
            installment_item.save(update_fields=['recognized_interest', 'is_interest_recognized', 'recognized_interest_entry'])
            logger.info(f"✅ تم إطفاء فائدة القسط #{installment_item.id} بمبلغ {amort_amount} (قيد #{entry.id})")

        return entry

    @classmethod
    def amortize_matured_installments_for_period(
        cls,
        period: AccountingPeriod,
        user=None
    ) -> List[JournalEntry]:
        """
        إطفاء كافة فوائد الأقساط المستحقة للفترة المحاسبية التي حان أجلها ولم تطفأ بعد
        تُستدعى تلقائياً عند إقفال الفترة PeriodControlService.close_period
        """
        matured_items = InstallmentItem.objects.filter(
            due_date__lte=period.end_date,
            is_interest_recognized=False,
            interest_amount__gt=Decimal("0.00")
        ).exclude(
            cash_status=InstallmentCashStatus.WAIVED
        ).select_related('plan__sale', 'plan__sale__cost_center')

        created_entries = []
        for it in matured_items:
            try:
                je = cls.amortize_installment_interest(
                    installment_item=it,
                    user=user,
                    posting_date=period.end_date
                )
                if je:
                    created_entries.append(je)
            except Exception as e:
                logger.error(f"خطأ أثناء إطفاء فوائد القسط #{it.id} للفترة {period.name}: {e}")

        logger.info(f"🔒 تم إطفاء فوائد {len(created_entries)} قسط مستحق للفترة {period.name}")
        return created_entries
