# -*- coding: utf-8 -*-
"""
FIN-SAL-INS-007: CompliancePackService
حزمة مطابقة مراقب الحسابات والفحص الضريبي وجدول تسوية الأستاذ العام
مطابقة دقيقة بين:
1. حساب أرباح تقسيط غير محققة (21400) في ميزان المراجعة مع رصيد unearned_interest_balance للأقساط
2. حساب إيرادات فوائد التقسيط المحققة (42200) في قائمة الدخل مع recognized_interest للأقساط
3. تجزئة أعمار الديون المجدولة (IFRS 9 Aging Schedule)
"""
import io
from decimal import Decimal
from typing import Dict, Any, List
from django.utils import timezone
from django.db.models import Sum, Q

from sale.models.installments import (
    InstallmentPlan,
    InstallmentItem,
    InstallmentCashStatus,
    PlanStatus,
)
from financial.models.chart_of_accounts import ChartOfAccounts


class CompliancePackService:
    """
    توليد مذكرات المطابقة الدفترية وحزمة مراقب الحسابات والفحص الضريبي
    """

    @classmethod
    def get_unearned_interest_gl_balance(cls) -> Decimal:
        """جلب رصيد حساب 21400 من شجرة الحسابات (دائن بطبيعته)"""
        acc = ChartOfAccounts.objects.filter(code__in=['21400', '2140'], is_active=True).first()
        if not acc:
            return Decimal("0.00")
        return acc.current_balance

    @classmethod
    def get_recognized_interest_gl_balance(cls) -> Decimal:
        """جلب رصيد حساب 42200 من شجرة الحسابات (دائن بطبيعته)"""
        acc = ChartOfAccounts.objects.filter(code__in=['42200', '4220'], is_active=True).first()
        if not acc:
            return Decimal("0.00")
        return acc.current_balance

    @classmethod
    def generate_reconciliation_summary(cls) -> Dict[str, Any]:
        """
        إجراء المطابقة الشاملة بين الأستاذ العام والأقساط
        """
        all_items = list(InstallmentItem.objects.select_related('plan', 'plan__sale').all())

        total_plans_count = InstallmentPlan.objects.count()
        active_plans_count = InstallmentPlan.objects.filter(status=PlanStatus.ACTIVE).count()

        # حساب الفوائد غير المحققة القائمة من جداول الأقساط
        schedule_unearned_interest = sum(
            it.unearned_interest_balance for it in all_items
            if it.plan.status in [PlanStatus.ACTIVE, PlanStatus.DISPUTED]
        )

        # حساب الفوائد المعترف بها من جداول الأقساط
        schedule_recognized_interest = sum(
            it.recognized_interest for it in all_items
        )

        total_remaining_principal = sum(it.remaining_principal for it in all_items)
        total_remaining_interest = sum(it.remaining_interest for it in all_items)
        total_remaining_balance = total_remaining_principal + total_remaining_interest

        gl_unearned_21400 = cls.get_unearned_interest_gl_balance()
        gl_recognized_42200 = cls.get_recognized_interest_gl_balance()

        diff_unearned = (schedule_unearned_interest - abs(gl_unearned_21400)).quantize(Decimal("0.01"))
        diff_recognized = (schedule_recognized_interest - abs(gl_recognized_42200)).quantize(Decimal("0.01"))

        # تجزئة أعمار الديون المجدولة (Aging Breakdown)
        today = timezone.localdate()
        aging = {
            "current_not_due": Decimal("0.00"),
            "overdue_1_30": Decimal("0.00"),
            "overdue_31_60": Decimal("0.00"),
            "overdue_61_90": Decimal("0.00"),
            "overdue_over_90": Decimal("0.00"),
        }

        for it in all_items:
            rem = it.remaining_balance
            if rem <= Decimal("0.00") or it.cash_status in [InstallmentCashStatus.COLLECTED, InstallmentCashStatus.WAIVED]:
                continue

            if it.due_date >= today:
                aging["current_not_due"] += rem
            else:
                days_late = (today - it.due_date).days
                if days_late <= 30:
                    aging["overdue_1_30"] += rem
                elif days_late <= 60:
                    aging["overdue_31_60"] += rem
                elif days_late <= 90:
                    aging["overdue_61_90"] += rem
                else:
                    aging["overdue_over_90"] += rem

        return {
            "report_date": today,
            "total_plans_count": total_plans_count,
            "active_plans_count": active_plans_count,
            "total_remaining_principal": total_remaining_principal,
            "total_remaining_interest": total_remaining_interest,
            "total_remaining_balance": total_remaining_balance,
            "schedule_unearned_interest": schedule_unearned_interest,
            "gl_unearned_21400": gl_unearned_21400,
            "diff_unearned": diff_unearned,
            "schedule_recognized_interest": schedule_recognized_interest,
            "gl_recognized_42200": gl_recognized_42200,
            "diff_recognized": diff_recognized,
            "is_unearned_reconciled": abs(diff_unearned) <= Decimal("0.05"),
            "is_recognized_reconciled": abs(diff_recognized) <= Decimal("0.05"),
            "aging": aging,
        }

    @classmethod
    def export_excel_pack(cls) -> io.BytesIO:
        """
        تصدير حزمة المراجعة والتسوية الرسمية إلى ملف إكسيل منسق بنظام openpyxl
        """
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

        summary = cls.generate_reconciliation_summary()
        wb = openpyxl.Workbook()

        # Sheet 1: ملخص المطابقة المحاسبية
        ws_sum = wb.active
        ws_sum.title = "مطابقة الأستاذ العام"
        ws_sum.sheet_view.rightToLeft = True

        header_font = Font(name="Arial", size=12, bold=True, color="FFFFFF")
        title_font = Font(name="Arial", size=14, bold=True)
        bold_font = Font(name="Arial", size=11, bold=True)
        regular_font = Font(name="Arial", size=11)

        primary_fill = PatternFill(start_color="1A365D", end_color="1A365D", fill_type="solid")
        light_fill = PatternFill(start_color="F7FAFC", end_color="F7FAFC", fill_type="solid")
        success_fill = PatternFill(start_color="C6F6D5", end_color="C6F6D5", fill_type="solid")

        thin_border = Border(
            left=Side(style='thin', color='D2D6DC'),
            right=Side(style='thin', color='D2D6DC'),
            top=Side(style='thin', color='D2D6DC'),
            bottom=Side(style='thin', color='D2D6DC'),
        )

        ws_sum.merge_cells("A1:D1")
        ws_sum["A1"] = f"حزمة مطابقة مراقب الحسابات لمحفظة التقسيط - شركة موهبة ({summary['report_date']})"
        ws_sum["A1"].font = title_font
        ws_sum["A1"].alignment = Alignment(horizontal="center", vertical="center")

        ws_sum.append([])
        ws_sum.append(["البند المحاسبي", "رصيد جداول الأقساط", "رصيد الأستاذ العام (GL)", "فرق المطابقة"])
        for col in range(1, 5):
            cell = ws_sum.cell(row=3, column=col)
            cell.font = header_font
            cell.fill = primary_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        rows_data = [
            ("فوائد تقسيط غير محققة (21400)", summary["schedule_unearned_interest"], summary["gl_unearned_21400"], summary["diff_unearned"]),
            ("إيرادات فوائد تقسيط محققة (42200)", summary["schedule_recognized_interest"], summary["gl_recognized_42200"], summary["diff_recognized"]),
            ("إجمالي أصل المديونية القائمة", summary["total_remaining_principal"], "-", "-"),
            ("إجمالي الفوائد المتبقية للمطالبة", summary["total_remaining_interest"], "-", "-"),
            ("إجمالي المديونية التعاقدية الشاملة", summary["total_remaining_balance"], "-", "-"),
        ]

        for r_idx, r in enumerate(rows_data, start=4):
            ws_sum.append(list(r))
            for c_idx in range(1, 5):
                cell = ws_sum.cell(row=r_idx, column=c_idx)
                cell.font = regular_font
                cell.border = thin_border
                if c_idx > 1 and isinstance(cell.value, (int, float, Decimal)):
                    cell.number_format = "#,##0.00"
                    cell.alignment = Alignment(horizontal="right")

        # إضافة قسم أعمار الديون
        ws_sum.append([])
        ws_sum.append(["فترة الاستحقاق (Aging Schedule)", "المبلغ المتبقي (ج.م)", "النسبة من الإجمالي", "الملاحظات الرقابية"])
        aging_header_row = ws_sum.max_row
        for col in range(1, 5):
            cell = ws_sum.cell(row=aging_header_row, column=col)
            cell.font = header_font
            cell.fill = primary_fill
            cell.alignment = Alignment(horizontal="center")

        tot_rem = summary["total_remaining_balance"] or Decimal("1.00")
        aging_rows = [
            ("أقساط سارية لم يحل أجلها", summary["aging"]["current_not_due"], "طبيعي - التزام عادي"),
            ("متأخرات من 1 إلى 30 يوماً", summary["aging"]["overdue_1_30"], "متابعة تذكير ودي"),
            ("متأخرات من 31 إلى 60 يوماً", summary["aging"]["overdue_31_60"], "إنذار أول وتجميد صرف بضاعة"),
            ("متأخرات من 61 إلى 90 يوماً", summary["aging"]["overdue_61_90"], "إنذار مسجل وتلويح بالسند لأمر"),
            ("متأخرات تجاوزت 90 يوماً", summary["aging"]["overdue_over_90"], "إحالة للشؤون القانونية وسقوط الأجل"),
        ]

        for label, val, note in aging_rows:
            pct = (val / tot_rem * 100).quantize(Decimal("0.1"))
            ws_sum.append([label, val, f"{pct}%", note])
            curr_row = ws_sum.max_row
            for col in range(1, 5):
                cell = ws_sum.cell(row=curr_row, column=col)
                cell.font = regular_font
                cell.border = thin_border
                if col == 2:
                    cell.number_format = "#,##0.00"
                    cell.alignment = Alignment(horizontal="right")

        # ضبط أبعاد الأعمدة
        ws_sum.column_dimensions["A"].width = 38
        ws_sum.column_dimensions["B"].width = 25
        ws_sum.column_dimensions["C"].width = 25
        ws_sum.column_dimensions["D"].width = 35

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output
