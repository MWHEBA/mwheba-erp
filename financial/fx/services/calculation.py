import hashlib
import logging
from decimal import Decimal
from typing import Dict, Any, List
from django.db import models
from django.utils import timezone
from financial.models.currency import Currency, ExchangeRate
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.services.exchange_rate_service import ExchangeRateService
from financial.fx.models import FXRevaluationRun, FXRevaluationLine, FXRateSnapshot

logger = logging.getLogger("financial.fx.services.calculation")


class FXCalculationService:
    """
    FXCalculationService - محرك حساب المعاينة وتوليد مسودة التقييم (Calculation Engine)
    يحسب صافي الذمم المفتوحة وحسابات النقدية الأجنبية ويجمد صور أسعار الصرف
    """

    @classmethod
    def calculate_and_create_run(
        cls,
        period,
        user=None,
        company_code: str = "DEFAULT",
        accounting_book: str = "PRIMARY",
        valuation_type: str = "PERIOD_END",
        valuation_method: str = "OPEN_ITEMS",
        currency_scope: str = "ALL_CURRENCIES",
        target_currency=None
    ) -> FXRevaluationRun:
        """
        حساب فروق تقييم أسعار الصرف غير المحققة وإنشاء FXRevaluationRun بحالة CALCULATED
        مع تجميد أسعار الصرف وإنشاء FXRevaluationLine لكل بند.
        """
        as_of_date = period.end_date
        func_curr = ExchangeRateService.get_functional_currency()
        if not func_curr:
            raise ValueError("لم يتم تحديد العملة الأساسية للمؤسسة.")

        # 1. إنشاء أو جلب كائن الـ Run بحالة DRAFT
        run, _created = FXRevaluationRun.objects.get_or_create(
            company_code=company_code,
            period=period,
            valuation_type=valuation_type,
            currency_scope=currency_scope,
            accounting_book=accounting_book,
            defaults={
                'valuation_method': valuation_method,
                'target_currency': target_currency,
                'run_date': as_of_date,
                'created_by': user,
                'status': 'DRAFT',
            }
        )

        # إذا كانت مسودة أو محسوبة مسبقاً، مسح البنود والـ Snapshots السابقة لإعادة الحساب النظيف
        if run.status in ['DRAFT', 'CALCULATED', 'FAILED']:
            run.lines.all().delete()
            run.rate_snapshots.all().delete()

        # 2. تحديد العملات الأجنبية المستهدفة
        if currency_scope == 'SPECIFIC' and target_currency:
            active_currencies = [target_currency]
        else:
            active_currencies = list(Currency.objects.filter(is_active=True, is_functional=False))

        total_gain_loss = Decimal("0.00")

        # جلب الحسابات المحاسبية المعتمدة لأرباح/خسائر الفروق ولذمم AR
        fx_unrealized_account = cls._get_or_create_fx_unrealized_account()
        ar_account_default = cls._get_or_create_ar_account()

        # 3. معالجة وحساب أسعار الصرف وتجميدها في FXRateSnapshot
        snapshots_map = {}
        for curr in active_currencies:
            rate_val = ExchangeRateService.get_rate(curr.code, func_curr.code, date=as_of_date)
            snapshot = FXRateSnapshot.objects.create(
                run=run,
                currency=curr,
                rate_type='CLOSING',
                rate_date=as_of_date,
                rate=rate_val,
                source="CBE_OFFICIAL"
            )
            snapshots_map[curr.code] = snapshot

        # 4. حساب بنود عملاء المبيعات (AR Items)
        try:
            from sale.models import CustomerTransaction
            ar_txs = CustomerTransaction.objects.filter(
                currency__in=active_currencies,
                created_at__date__lte=as_of_date
            ).select_related('customer', 'currency')

            for tx in ar_txs:
                open_foreign = tx.amount - getattr(tx, 'paid_amount', Decimal("0.00"))
                if abs(open_foreign) > Decimal("0.0001"):
                    closing_rate = snapshots_map[tx.currency.code].rate
                    old_rate = tx.exchange_rate if tx.exchange_rate and tx.exchange_rate > 0 else Decimal("1.000000")
                    old_functional = (open_foreign * old_rate).quantize(Decimal("0.01"))
                    closing_functional = (open_foreign * closing_rate).quantize(Decimal("0.01"))
                    diff = closing_functional - old_functional

                    # حساب الـ Source Hash لمنع التعديل المتزامن
                    source_str = f"AR_{tx.id}_{tx.amount}_{tx.updated_at if hasattr(tx, 'updated_at') else ''}"
                    source_hash = hashlib.sha256(source_str.encode('utf-8')).hexdigest()

                    FXRevaluationLine.objects.create(
                        run=run,
                        source_type='AR_INVOICE',
                        source_id=str(tx.id),
                        source_hash=source_hash,
                        account=ar_account_default,
                        partner_name=str(tx.customer) if tx.customer else "عميل",
                        currency=tx.currency,
                        open_foreign_amount=open_foreign,
                        old_rate=old_rate,
                        new_rate=closing_rate,
                        old_functional_value=old_functional,
                        new_functional_value=closing_functional,
                        unrealized_difference=diff,
                        gain_loss_account=fx_unrealized_account
                    )
                    total_gain_loss += diff
        except Exception as e:
            logger.warning(f"ملاحظة أثناء استعلام بنود AR للتقييم: {e}")

        # 5. حساب بنود فواتير الموردين (AP Items)
        try:
            from purchase.models import PurchaseInvoice
            ap_invs = PurchaseInvoice.objects.filter(
                currency__in=active_currencies,
                issue_date__lte=as_of_date
            ).exclude(status='cancelled').select_related('supplier', 'currency')

            ap_account_default = cls._get_or_create_ap_account()

            for inv in ap_invs:
                open_foreign = inv.total_amount - getattr(inv, 'paid_amount', Decimal("0.00"))
                if abs(open_foreign) > Decimal("0.0001"):
                    closing_rate = snapshots_map[inv.currency.code].rate
                    old_rate = inv.exchange_rate if inv.exchange_rate and inv.exchange_rate > 0 else Decimal("1.000000")
                    old_functional = (open_foreign * old_rate).quantize(Decimal("0.01"))
                    closing_functional = (open_foreign * closing_rate).quantize(Decimal("0.01"))
                    # بالنسبة للموردين (التزام): زيادة الجنيه تعني خسارة (فرق عكسي)
                    diff = old_functional - closing_functional

                    source_str = f"AP_{inv.id}_{inv.total_amount}_{inv.updated_at if hasattr(inv, 'updated_at') else ''}"
                    source_hash = hashlib.sha256(source_str.encode('utf-8')).hexdigest()

                    FXRevaluationLine.objects.create(
                        run=run,
                        source_type='AP_INVOICE',
                        source_id=str(inv.id),
                        source_hash=source_hash,
                        account=ap_account_default,
                        partner_name=str(inv.supplier) if inv.supplier else "مورد",
                        currency=inv.currency,
                        open_foreign_amount=open_foreign,
                        old_rate=old_rate,
                        new_rate=closing_rate,
                        old_functional_value=old_functional,
                        new_functional_value=closing_functional,
                        unrealized_difference=diff,
                        gain_loss_account=fx_unrealized_account
                    )
                    total_gain_loss += diff
        except Exception as e:
            logger.warning(f"ملاحظة أثناء استعلام بنود AP للتقييم: {e}")

        # 6. حساب أرصدة الخزن والبنوك الأجنبية (Monetary Cash Items)
        try:
            cash_accounts = ChartOfAccounts.objects.filter(
                currency__in=active_currencies,
                is_active=True,
                is_leaf=True
            ).select_related('currency')

            for acc in cash_accounts:
                open_foreign = getattr(acc, 'current_balance_foreign', Decimal("0.00"))
                if abs(open_foreign) > Decimal("0.0001"):
                    closing_rate = snapshots_map[acc.currency.code].rate
                    old_functional = getattr(acc, 'current_balance', Decimal("0.00"))
                    closing_functional = (open_foreign * closing_rate).quantize(Decimal("0.01"))
                    diff = closing_functional - old_functional

                    source_str = f"CASH_{acc.id}_{open_foreign}_{old_functional}"
                    source_hash = hashlib.sha256(source_str.encode('utf-8')).hexdigest()

                    FXRevaluationLine.objects.create(
                        run=run,
                        source_type='CASH_ACCOUNT',
                        source_id=str(acc.id),
                        source_hash=source_hash,
                        account=acc,
                        partner_name=acc.name,
                        currency=acc.currency,
                        open_foreign_amount=open_foreign,
                        old_rate=Decimal("1.000000"),
                        new_rate=closing_rate,
                        old_functional_value=old_functional,
                        new_functional_value=closing_functional,
                        unrealized_difference=diff,
                        gain_loss_account=fx_unrealized_account
                    )
                    total_gain_loss += diff
        except Exception as e:
            logger.warning(f"ملاحظة أثناء حساب حسابات الخزن والبنوك للتقييم: {e}")

        # تحديث حالة الـ Run والإجمالي
        run.total_unrealized_gain_loss = total_gain_loss
        run.status = 'CALCULATED'
        run.save()

        return run

    @classmethod
    def _get_or_create_fx_unrealized_account(cls):
        acc = ChartOfAccounts.objects.filter(
            is_leaf=True,
            is_active=True
        ).filter(
            models.Q(code__in=["71020", "71020_UNREALIZED_FX_GAIN_LOSS", "420101", "520101"]) |
            models.Q(name__icontains="فروق تقييم") |
            models.Q(name__icontains="فروق عملة")
        ).first()
        if not acc:
            acc_type = AccountType.objects.filter(category__in=["revenue", "expense", "other_income"]).first() or AccountType.objects.first()
            acc = ChartOfAccounts.objects.create(
                code="71020_UNREALIZED_FX_GAIN_LOSS",
                name="حساب فروق تقييم أسعار الصرف غير المحققة (IAS 21)",
                account_type=acc_type,
                is_active=True,
                is_leaf=True
            )
        return acc

    @classmethod
    def _get_or_create_ar_account(cls):
        from financial.services.role_registry import AccountRoleRegistry
        acc = AccountRoleRegistry.get_account_by_role("CUSTOMER_RECEIVABLE_CONTROL")
        if not acc or not acc.is_leaf:
            acc = ChartOfAccounts.objects.filter(
                is_leaf=True,
                is_active=True
            ).filter(
                models.Q(code__startswith="11210") |
                models.Q(code__in=["11210", "11210001", "1101001", "1103001"]) |
                models.Q(name__icontains="عملاء")
            ).first()
        if not acc:
            acc_type = AccountType.objects.filter(category="asset").first() or AccountType.objects.first()
            acc = ChartOfAccounts.objects.create(
                code="11210001",
                name="حساب ذمم العملاء الافتراضي",
                account_type=acc_type,
                is_active=True,
                is_leaf=True
            )
        return acc

    @classmethod
    def _get_or_create_ap_account(cls):
        from financial.services.role_registry import AccountRoleRegistry
        acc = AccountRoleRegistry.get_account_by_role("SUPPLIER_PAYABLE_CONTROL")
        if not acc or not acc.is_leaf:
            acc = ChartOfAccounts.objects.filter(
                is_leaf=True,
                is_active=True
            ).filter(
                models.Q(code__startswith="21110") |
                models.Q(code__in=["21110", "21110001", "2101001", "20100"]) |
                models.Q(name__icontains="موردين")
            ).first()
        if not acc:
            acc_type = AccountType.objects.filter(category="liability").first() or AccountType.objects.first()
            acc = ChartOfAccounts.objects.create(
                code="21110001",
                name="حساب ذمم الموردين الافتراضي",
                account_type=acc_type,
                is_active=True,
                is_leaf=True
            )
        return acc
