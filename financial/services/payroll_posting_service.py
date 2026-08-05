from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from financial.models.cost_center_governance import EmployeeCostCenterAllocation
from financial.services.ledger_core_service import LedgerCoreService


class PayrollPostingService:
    """
    خدمة تترحيل الرواتب والأجور وتأكيد التوزيع 100% (PayrollPostingService)
    """

    @staticmethod
    def validate_employee_payroll_allocations(employee_id: str) -> Decimal:
        """
        التحقق من استيفاء نسب توزيع راتب الموظف لـ 100% بالكامل قبل إنشاء قيد الرواتب
        """
        allocations = EmployeeCostCenterAllocation.objects.filter(employee_id=employee_id)
        if not allocations.exists():
            raise ValidationError(
                _("حظر الحوكمة: لا توجد مراكز تكلفة مخصصة لراتب الموظف (%(emp)s).") % {'emp': employee_id}
            )

        total_pct = sum(a.percentage for a in allocations)
        if abs(total_pct - Decimal("100.00")) > Decimal("0.01"):
            raise ValidationError(
                _("حظر الحوكمة: إجمالي توزيعات راتب الموظف (%(pct)s%%) يجب أن يساوي 100%% بالكامل قبل التترحيل.") % {'pct': total_pct}
            )

        return total_pct

    @classmethod
    def post_employee_payroll_entry(cls, date, employee_id: str, employee_name: str, total_salary: Decimal, expense_account, bank_account, created_by):
        """
        إنشاء وتترحيل قيد راتب الموظف مقسماً حسب مراكز التكلفة المعرف له
        """
        cls.validate_employee_payroll_allocations(employee_id)
        allocations = EmployeeCostCenterAllocation.objects.filter(employee_id=employee_id)

        lines_data = []
        # أسطر المدين (توزيع المصروف على مراكز التكلفة)
        for alloc in allocations:
            debit_amt = (alloc.percentage / Decimal("100.00")) * total_salary
            lines_data.append({
                'account': expense_account,
                'debit': debit_amt.quantize(Decimal("0.01")),
                'credit': Decimal("0.00"),
                'description': f"راتب {employee_name} ({alloc.cost_center.name})",
                'cost_center': alloc.cost_center
            })

        # سطر الدائن (حساب البنك / النقدية)
        lines_data.append({
            'account': bank_account,
            'debit': Decimal("0.00"),
            'credit': total_salary.quantize(Decimal("0.01")),
            'description': f"صرف راتب الموظف {employee_name}",
            'cost_center': None
        })

        with transaction.atomic():
            entry = LedgerCoreService.create_draft_entry(
                date=date,
                description=f"قيد راتب الموظف {employee_name} ({employee_id})",
                reference=f"PAY-{employee_id}",
                entry_type="PAYROLL",
                created_by=created_by,
                lines_data=lines_data
            )
            return LedgerCoreService.post_entry(entry.id, created_by)
