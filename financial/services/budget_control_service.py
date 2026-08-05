from decimal import Decimal
from typing import Optional
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from financial.models.cost_center import CostCenter
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import AccountingPeriod
from financial.models.cost_center_budget import CostCenterBudget, CostCenterBudgetLine, BudgetOverrideRequest
from financial.services.budget_actual_service import BudgetActualService


class BudgetExceededError(ValidationError):
    """استثناء مخصص عند حظر الترحيل بسبب تجاوز الموازنة"""
    pass


class BudgetControlService:
    """
    محرك الرقابة المحاسبية الوقائية الصارمة للموازنة (Preventative Budget Control Engine)
    """

    @classmethod
    def validate_budget_limit(
        cls,
        cost_center: CostCenter,
        account: ChartOfAccounts,
        accounting_period: AccountingPeriod,
        amount: Decimal,
        user=None
    ) -> bool:
        """
        التحقق من سقف الموازنة المتاحة وتطبيق سياسة الرقابة المحددة (BLOCK, WARN, REQUIRES_APPROVAL, ALLOW)
        """
        if not cost_center or not account or not accounting_period:
            return True

        # جلب أحدث موازنة معتمدة لمركز التكلفة
        budget = CostCenterBudget.objects.filter(
            cost_center=cost_center,
            fiscal_year=accounting_period.fiscal_year,
            status='APPROVED'
        ).order_by('-version').first()

        if not budget:
            return True

        line = CostCenterBudgetLine.objects.filter(budget=budget, account=account).first()
        if not line:
            return True

        policy = line.control_policy
        if policy == 'ALLOW':
            return True

        # حساب الرصيد المستنفذ حالياً
        actual_info = BudgetActualService.get_actual_and_committed(cost_center, account, accounting_period)
        total_used = actual_info['total_used']
        projected_used = total_used + amount

        if projected_used > line.allocated_amount:
            excess = projected_used - line.allocated_amount

            # التحقق مما إذا كان هناك طلب تجاوز مقبول استثنائياً
            if policy == 'REQUIRES_APPROVAL' or user:
                approved_override = BudgetOverrideRequest.objects.filter(
                    cost_center=cost_center,
                    account=account,
                    status='APPROVED',
                    requested_amount__gte=excess
                ).exists()
                if approved_override:
                    return True

            if policy in ['BLOCK', 'REQUIRES_APPROVAL']:
                raise BudgetExceededError(
                    _("حظر الحوكمة: القيد يتجاوز موازنة مركز التكلفة (%(cost_center)s) للحساب (%(account)s) بمبلغ (%(excess)s). السقف المعتمد: (%(allocated)s) - المتبقي: (%(remaining)s).") % {
                        'cost_center': cost_center.name,
                        'account': account.name,
                        'excess': excess,
                        'allocated': line.allocated_amount,
                        'remaining': line.allocated_amount - total_used
                    }
                )

        return True
