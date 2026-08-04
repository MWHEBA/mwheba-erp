"""
SupplierSubledgerService - محرك دفتر الأستاذ الفرعي للموردين (Sprint 2 Subledgers Engine)
يمتلك حل الحسابات الفرعية، قواعد مطابقة الحسابات الرئاسية للموردين، وتقرير أعمار الديون
يفوض استعلامات دفتر الأستاذ العام 100% لـ LedgerQueryService (FIN-CORE-014)
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.utils import timezone

from supplier.models import Supplier
from financial.services.ledger_query_service import LedgerQueryService
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames

logger = logging.getLogger("supplier.supplier_subledger_service")


class SupplierSubledgerService:
    """
    خدمة دفتر الأستاذ الفرعي للموردين
    """

    @classmethod
    def resolve_supplier_account(cls, supplier_id: int):
        """
        حل وتدقيق وجود الحساب المالي الفرعي للمورد
        """
        supplier = Supplier.objects.select_related('financial_account').get(pk=supplier_id)
        if not supplier.financial_account:
            raise ValueError(f"Supplier {supplier.name} (ID: {supplier_id}) has no associated financial account.")
        return supplier, supplier.financial_account

    @classmethod
    def get_supplier_balance(
        cls,
        supplier_id: int,
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        استعلام رصيد المورد الحالي من واقع حقائق دفتر الأستاذ عبر LedgerQueryService
        """
        supplier, account = cls.resolve_supplier_account(supplier_id)
        balance_data = LedgerQueryService.get_account_balance(account, as_of_date=as_of_date)
        balance_data['supplier_id'] = supplier.id
        balance_data['supplier_code'] = supplier.code
        balance_data['supplier_name'] = supplier.name
        return balance_data

    @classmethod
    def get_supplier_statement(
        cls,
        supplier_id: int,
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        استخراج كشف حساب جاري للمورد عبر LedgerQueryService
        """
        supplier, account = cls.resolve_supplier_account(supplier_id)
        statement_data = LedgerQueryService.get_account_statement(account, start_date=start_date, end_date=end_date)
        statement_data['supplier_id'] = supplier.id
        statement_data['supplier_code'] = supplier.code
        statement_data['supplier_name'] = supplier.name
        return statement_data

    @classmethod
    def get_supplier_aging_report(
        cls,
        supplier_ids: Optional[List[int]] = None,
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        حساب تقرير أعمار ديون الموردين (Aging Buckets: 0-30, 31-60, 61-90, 90+)
        يعتمد التقرير التشغيلي على تواريخ استحقاق فواتير الشراء والمدفوعات الموزعة (FIN-SUB-001 Allocation Engine)
        """
        ref_date = as_of_date or timezone.now().date()
        suppliers = Supplier.objects.filter(is_active=True).select_related('financial_account')
        if supplier_ids:
            suppliers = suppliers.filter(pk__in=supplier_ids)

        report_rows = []
        total_summary = {
            'bucket_0_30': Decimal('0.00'),
            'bucket_31_60': Decimal('0.00'),
            'bucket_61_90': Decimal('0.00'),
            'bucket_90_plus': Decimal('0.00'),
            'total_balance': Decimal('0.00')
        }

        for supplier in suppliers:
            if not supplier.financial_account:
                continue

            bal_data = LedgerQueryService.get_account_balance(supplier.financial_account, as_of_date=ref_date)
            balance = bal_data['balance']

            if balance <= Decimal('0.00'):
                continue

            stmt = LedgerQueryService.get_account_statement(supplier.financial_account, end_date=ref_date)
            transactions = stmt['transactions']

            bucket_0_30 = Decimal('0.00')
            bucket_31_60 = Decimal('0.00')
            bucket_61_90 = Decimal('0.00')
            bucket_90_plus = Decimal('0.00')

            for txn in reversed(transactions):
                if txn['credit'] <= 0:
                    continue
                txn_date = txn['date']
                days_old = (ref_date - txn_date).days

                amount = txn['credit']
                if days_old <= 30:
                    bucket_0_30 += amount
                elif days_old <= 60:
                    bucket_31_60 += amount
                elif days_old <= 90:
                    bucket_61_90 += amount
                else:
                    bucket_90_plus += amount

            row_total = bucket_0_30 + bucket_31_60 + bucket_61_90 + bucket_90_plus
            if row_total > 0 and row_total != balance:
                factor = balance / row_total
                bucket_0_30 = (bucket_0_30 * factor).quantize(Decimal('0.01'))
                bucket_31_60 = (bucket_31_60 * factor).quantize(Decimal('0.01'))
                bucket_61_90 = (bucket_61_90 * factor).quantize(Decimal('0.01'))
                bucket_90_plus = (bucket_90_plus * factor).quantize(Decimal('0.01'))

            report_rows.append({
                'supplier_id': supplier.id,
                'supplier_code': supplier.code,
                'supplier_name': supplier.name,
                'bucket_0_30': bucket_0_30,
                'bucket_31_60': bucket_31_60,
                'bucket_61_90': bucket_61_90,
                'bucket_90_plus': bucket_90_plus,
                'total_balance': balance
            })

            total_summary['bucket_0_30'] += bucket_0_30
            total_summary['bucket_31_60'] += bucket_31_60
            total_summary['bucket_61_90'] += bucket_61_90
            total_summary['bucket_90_plus'] += bucket_90_plus
            total_summary['total_balance'] += balance

        return {
            'as_of_date': ref_date,
            'rows': report_rows,
            'summary': total_summary
        }

    @classmethod
    def reconcile_supplier_control_account(cls) -> Dict[str, Any]:
        """
        مطابقة رصيد حساب التحكم الإجمالي للموردين (Supplier Payable Control) مع مجموع أرصدة الموردين
        """
        control_account = AccountRoleRegistry.get_account(AccountRoleNames.SUPPLIER_PAYABLE_CONTROL)
        suppliers = Supplier.objects.filter(is_active=True, financial_account__isnull=False)
        sub_accounts = [s.financial_account for s in suppliers]

        reconciliation = LedgerQueryService.get_control_account_reconciliation(control_account, sub_accounts)
        return reconciliation
