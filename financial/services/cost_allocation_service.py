from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from financial.models.journal_entry import JournalEntryLineCostAllocation, JournalEntryLine
from financial.models.cost_center import CostCenter


class CostAllocationService:
    """
    محرك التوزيع المالي الفرعي لمراكز التكلفة متعددة الحصص (CostAllocationService)
    """

    @staticmethod
    def allocate_journal_line(line: JournalEntryLine, allocations: list) -> list:
        """
        توزيع سطر القيد المحاسبي على عدة مراكز تكلفة بـ % أو مبالغ ثنائية
        """
        if line.journal_entry and line.journal_entry.status == 'posted':
            raise ValidationError(_("حظر الحوكمة: لا يمكن تعديل توزيعات سطر مالي تابع لقيد مرحل."))

        line_total = line.debit if line.debit > 0 else line.credit
        if line_total <= 0:
            raise ValidationError(_("حظر الحوكمة: يجب أن يحتوي السطر على مبلغ مدين أو دائن أكبر من صفر للتوزيع."))

        created_allocations = []
        total_percentage = Decimal("0.00")
        total_amount = Decimal("0.00")

        with transaction.atomic():
            # تفريغ أي حصص فرعية قديمة قبل التحديث
            line.cost_allocations.all().delete()

            for item in allocations:
                cc = item.get('cost_center')
                if isinstance(cc, int):
                    cc = CostCenter.objects.get(id=cc)

                pct = Decimal(str(item.get('percentage', 0)))
                amt = Decimal(str(item.get('amount', 0)))

                if pct > 0 and amt == 0:
                    amt = (pct / Decimal("100.00")) * line_total
                elif amt > 0 and pct == 0:
                    pct = (amt / line_total) * Decimal("100.00")

                total_percentage += pct
                total_amount += amt

                alloc_obj = JournalEntryLineCostAllocation.objects.create(
                    line=line,
                    cost_center=cc,
                    percentage=pct.quantize(Decimal("0.01")),
                    amount=amt.quantize(Decimal("0.01"))
                )
                created_allocations.append(alloc_obj)

            # التحقق من اكتمال التوزيع المالي بنسبة 100%
            if abs(total_percentage - Decimal("100.00")) > Decimal("0.05"):
                raise ValidationError(
                    _("حظر الحوكمة: إجمالي نسب التوزيع (%(pct)s%%) يجب أن يساوي 100%% بالكامل.") % {'pct': total_percentage}
                )

        return created_allocations

    @staticmethod
    def seed_invoice_line_cost_center(header_cost_center, line_obj) -> bool:
        """
        زراعة مركز التكلفة من هيدر الفاتورة لأسطر الفاتورة كـ Default مع حماية استقلالية الأسطر
        """
        if not getattr(line_obj, 'cost_center', None) and header_cost_center:
            line_obj.cost_center = header_cost_center
            if hasattr(line_obj, 'save'):
                line_obj.save(update_fields=['cost_center'])
            return True
        return False
