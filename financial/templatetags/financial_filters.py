from django import template
from django.db.models import Sum

register = template.Library()


@register.filter
def sum_debit(lines):
    """حساب مجموع المدين"""
    if not lines:
        return 0
    return sum(line.debit for line in lines)


@register.filter
def sum_credit(lines):
    """حساب مجموع الدائن"""
    if not lines:
        return 0
    return sum(line.credit for line in lines)


@register.filter
def max_amount(lines):
    """حساب أكبر مبلغ (مدين أو دائن)"""
    if not lines:
        return 0
    total_debit = sum(line.debit for line in lines)
    total_credit = sum(line.credit for line in lines)
    return max(total_debit, total_credit)


@register.filter
def get_main_account(lines):
    """الحصول على الحساب الرئيسي"""
    if not lines or len(lines) != 2:
        return "متعدد"

    debit_line = next((line for line in lines if line.debit > 0), None)
    credit_line = next((line for line in lines if line.credit > 0), None)

    if debit_line and credit_line:
        return f"{debit_line.account.name} ← {credit_line.account.name}"

    return "متعدد"


@register.filter
def get_entry_type(lines):
    """تحديد نوع القيد"""
    if not lines:
        return {"type": "تحويل", "class": "bg-info"}

    if len(lines) == 2:
        for line in lines:
            if line.debit > 0 and (
                "خزينة" in line.account.name or "نقدية" in line.account.name
            ):
                return {"type": "إيراد نقدي", "class": "bg-success"}
            elif line.credit > 0 and (
                "خزينة" in line.account.name or "نقدية" in line.account.name
            ):
                return {"type": "مصروف نقدي", "class": "bg-danger"}
            elif line.debit > 0 and "بنك" in line.account.name:
                return {"type": "إيراد بنكي", "class": "bg-primary"}
            elif line.credit > 0 and "بنك" in line.account.name:
                return {"type": "مصروف بنكي", "class": "bg-warning"}

    if len(lines) > 2:
        return {"type": "قيد مركب", "class": "bg-secondary"}

    return {"type": "تحويل", "class": "bg-info"}
