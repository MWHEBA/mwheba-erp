"""
AJAX views for inline editing of payroll lines in the payroll detail page.
Supports update, add, and delete operations with full audit logging.
"""
import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from ..decorators import can_process_payroll
from ..models import Payroll, PayrollLine
from ..services.payroll_audit_service import PayrollAuditService

# البنود التي لا يمكن تعديلها أو حذفها — مرتبطة بكيانات خارجية أو محسوبة تلقائياً
READONLY_CODES = {
    'BASIC_SALARY',           # الأجر الأساسي — محفوظ في payroll.basic_salary
    'INSURABLE_SALARY',       # مرجعية فقط — لا يدخل في الإجماليات
    'ADVANCE_DEDUCTION',      # مرتبط بـ AdvanceInstallment — يُعدَّل من صفحة السلف
    'SOCIAL_INSURANCE',       # تأمينات اجتماعية — محسوبة تلقائياً
    'SOCIAL_INSURANCE_EMP',   # تأمينات اجتماعية (حصة الموظف)
    'INCOME_TAX',             # ضريبة دخل — محسوبة تلقائياً
}

# prefixes للبنود التي لا يمكن تعديلها أو حذفها
READONLY_PREFIXES = (
    'ADVANCE_',   # أقساط سلف فردية مثل ADVANCE_42
    'PENALTY_',   # جزاءات مرتبطة بـ PenaltyReward
    'REWARD_',    # مكافآت مرتبطة بـ PenaltyReward
)

# البنود التي يمكن تعديل قيمتها فقط (الاسم ثابت)
VALUE_ONLY_CODES = {
    'ABSENCE_DEDUCTION', 'LATE_DEDUCTION', 'EXTRA_PERM_DEDUCTION',
    'UNPAID_LEAVE_DEDUCTION', 'OVERTIME',
}


def _is_readonly(code: str) -> bool:
    """Check if a line code is protected from editing or deletion."""
    return code in READONLY_CODES or code.startswith(READONLY_PREFIXES)


def _build_totals(payroll) -> dict:
    """Build totals dict mirroring exactly the logic in payroll_detail view."""
    from decimal import Decimal, ROUND_HALF_UP

    lines = payroll.lines.all()
    if not lines.exists():
        return {
            'earnings': float(payroll.total_additions or 0),
            'deductions': float(payroll.total_deductions or 0),
            'net': float(payroll.correct_net_salary),
        }

    earnings = lines.filter(component_type='earning')
    deductions = lines.filter(component_type='deduction')

    has_basic_line = earnings.filter(code='BASIC_SALARY').exists()
    earnings_sum = sum(
        line.amount for line in earnings.exclude(code='INSURABLE_SALARY')
    )
    total_earnings = earnings_sum if has_basic_line else payroll.basic_salary + earnings_sum
    total_deductions = sum(line.amount for line in deductions)

    net = (total_earnings - total_deductions).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    payroll.gross_salary = total_earnings
    payroll.total_deductions = total_deductions
    payroll.net_salary = net
    payroll.save(force_save=True)

    return {
        'earnings': float(total_earnings),
        'deductions': float(total_deductions),
        'net': float(net),
    }


def _error(message, status=400):
    return JsonResponse({'success': False, 'error': message}, status=status)


@login_required
@can_process_payroll
@require_http_methods(['PATCH'])
def payroll_line_update(request, line_pk):
    """Update name and/or amount of an existing payroll line."""
    line = get_object_or_404(PayrollLine.objects.select_related('payroll'), pk=line_pk)
    payroll = line.payroll

    if payroll.status not in ('draft', 'calculated'):
        return _error('لا يمكن تعديل قسيمة معتمدة أو مدفوعة', 403)

    if _is_readonly(line.code):
        return _error('لا يمكن تعديل هذا البند', 403)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return _error('بيانات غير صالحة')

    old_amount = line.amount
    old_name = line.name

    # تحديث القيمة
    if 'amount' in data:
        try:
            line.amount = Decimal(str(data['amount']))
        except (InvalidOperation, ValueError):
            return _error('قيمة المبلغ غير صالحة')

    # تحديث الاسم — فقط للبنود التي ليست في VALUE_ONLY_CODES
    new_name = old_name
    if 'name' in data and line.code not in VALUE_ONLY_CODES:
        new_name = str(data['name']).strip()
        if not new_name:
            return _error('اسم البند لا يمكن أن يكون فارغاً')
        line.name = new_name

    # تعليم البند كمعدّل يدوياً
    if not line.is_manual:
        line.is_modified = True

    # rate=0 عشان save() يحتفظ بالـ amount كما هو
    line.rate = Decimal('0')
    line.save()

    # بناء ملاحظة الـ audit بعد الحفظ
    changes = []
    if new_name != old_name:
        changes.append(f'الاسم: {old_name} ← {new_name}')
    if line.amount != old_amount:
        changes.append(f'{line.name}: {old_amount} ← {line.amount}')
    audit_note = ' | '.join(changes) if changes else f'تعديل: {line.name}'

    totals = _build_totals(payroll)
    PayrollAuditService.log_lines_edited(payroll, request.user, changes_summary=audit_note)

    return JsonResponse({
        'success': True,
        'line': {
            'id': line.pk,
            'name': line.name,
            'amount': str(line.amount),
            'is_modified': line.is_modified,
            'is_manual': line.is_manual,
        },
        'totals': totals,
    })


@login_required
@can_process_payroll
@require_http_methods(['POST'])
def payroll_line_add(request, pk):
    """Add a new manual payroll line (earning or deduction)."""
    payroll = get_object_or_404(Payroll, pk=pk)

    if payroll.status not in ('draft', 'calculated'):
        return _error('لا يمكن تعديل قسيمة معتمدة أو مدفوعة', 403)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return _error('بيانات غير صالحة')

    name = str(data.get('name', '')).strip()
    if not name:
        return _error('اسم البند مطلوب')

    line_type = data.get('type', '')
    if line_type not in ('earning', 'deduction'):
        return _error('نوع البند غير صالح')

    try:
        amount = Decimal(str(data.get('amount', 0)))
        if amount < 0:
            return _error('المبلغ لا يمكن أن يكون سالباً')
    except (InvalidOperation, ValueError):
        return _error('قيمة المبلغ غير صالحة')

    # تحديد الترتيب — بعد آخر بند من نفس النوع
    last_order = (
        payroll.lines.filter(component_type=line_type)
        .order_by('-order')
        .values_list('order', flat=True)
        .first()
    ) or 0

    line = PayrollLine.objects.create(
        payroll=payroll,
        code=f'MANUAL_{line_type.upper()}_{payroll.pk}_{last_order + 1}',
        name=name,
        component_type=line_type,
        source='adjustment',
        amount=amount,
        rate=Decimal('0'),
        quantity=Decimal('1'),
        order=last_order + 1,
        is_manual=True,
        is_modified=False,
    )

    totals = _build_totals(payroll)
    PayrollAuditService.log_lines_edited(
        payroll, request.user,
        changes_summary=f'إضافة: {name} ({amount})'
    )

    return JsonResponse({
        'success': True,
        'line': {
            'id': line.pk,
            'name': line.name,
            'amount': str(line.amount),
            'type': line.component_type,
            'is_manual': True,
            'category': 'c',
        },
        'totals': totals,
    }, status=201)


@login_required
@can_process_payroll
@require_http_methods(['DELETE'])
def payroll_line_delete(request, line_pk):
    """Delete a payroll line (only non-readonly lines)."""
    line = get_object_or_404(PayrollLine.objects.select_related('payroll'), pk=line_pk)
    payroll = line.payroll

    if payroll.status not in ('draft', 'calculated'):
        return _error('لا يمكن تعديل قسيمة معتمدة أو مدفوعة', 403)

    if _is_readonly(line.code):
        return _error('لا يمكن حذف هذا البند', 403)

    audit_note = f'حذف: {line.name} ({line.amount})'
    line.delete()

    totals = _build_totals(payroll)
    PayrollAuditService.log_lines_edited(payroll, request.user, changes_summary=audit_note)

    return JsonResponse({'success': True, 'totals': totals})
