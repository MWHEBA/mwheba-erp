from decimal import Decimal
from typing import Optional
from django.db import transaction
from django.utils import timezone
from financial.models.cost_center_budget import CostCenterBudget, CostCenterBudgetLine


class BudgetApprovalService:
    """
    خدمة دورة اعتماد الموازنات والتحكم في الإصدارات (Budget Approval & Versioning Lifecycle Service)
    """

    @classmethod
    def submit_budget(cls, budget_id: int, user=None) -> CostCenterBudget:
        budget = CostCenterBudget.objects.get(pk=budget_id)
        budget.status = 'SUBMITTED'
        budget.save(update_fields=['status', 'updated_at'])
        return budget

    @classmethod
    def approve_budget(cls, budget_id: int, user=None, comment: str = "") -> CostCenterBudget:
        with transaction.atomic():
            budget = CostCenterBudget.objects.get(pk=budget_id)
            # أرشفة وقفل أي إصدارات معتمدة سابقة لمركز التكلفة ونفس السنة
            CostCenterBudget.objects.filter(
                cost_center=budget.cost_center,
                fiscal_year=budget.fiscal_year,
                status='APPROVED'
            ).exclude(pk=budget.pk).update(status='ARCHIVED')

            budget.status = 'APPROVED'
            budget.approved_at = timezone.now()
            budget.approved_by = user
            budget.save(update_fields=['status', 'approved_at', 'approved_by', 'updated_at'])
            return budget

    @classmethod
    def revise_budget(cls, budget_id: int, user=None) -> CostCenterBudget:
        """
        إنشاء إصدار جديد معدّل V+1 من موازنة معتمدة
        """
        with transaction.atomic():
            old_budget = CostCenterBudget.objects.get(pk=budget_id)
            new_version = old_budget.version + 1

            new_budget = CostCenterBudget.objects.create(
                cost_center=old_budget.cost_center,
                fiscal_year=old_budget.fiscal_year,
                version=new_version,
                budget_amount=old_budget.budget_amount,
                status='DRAFT'
            )

            # نسخ بنود الموازنة السابقة للإصدار الجديد
            for line in old_budget.lines.all():
                CostCenterBudgetLine.objects.create(
                    budget=new_budget,
                    account=line.account,
                    allocated_amount=line.allocated_amount,
                    control_policy=line.control_policy
                )

            old_budget.status = 'REVISED'
            old_budget.save(update_fields=['status', 'updated_at'])

            return new_budget
