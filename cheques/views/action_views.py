# -*- coding: utf-8 -*-
import hashlib
import uuid
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.db import transaction

from cheques.models import Cheque, ChequeType, ChequeStatus, ChequeActionLog, ChequeActionType
from cheques.services.accounting_service import ChequeAccountingService
from cheques.services.reversal_service import ChequeReversalService
from cheques.forms.action_forms import (
    ChequeDepositActionForm,
    ChequeCollectActionForm,
    ChequeBounceActionForm,
    ChequeEndorseActionForm,
    ChequeReversalActionForm,
    ChequeConvertGuaranteeActionForm,
)


def _handle_response(request, success: bool, message: str, redirect_url: str):
    """مساعد الرد الموحد (يدعم كلاً من AJAX واستجابات الـ Redirect القياسية)"""
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({
            'success': success,
            'message': message,
            'redirect_url': redirect_url if success else None
        }, status=200 if success else 400)

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)
    return redirect(redirect_url)


@login_required
@permission_required('cheques.deposit_cheque', raise_exception=True)
@require_POST
def cheque_deposit_action(request, pk):
    """إيداع الشيك بالبنك برسم التحصيل"""
    cheque = get_object_or_404(Cheque, pk=pk)
    redirect_url = reverse('cheques:receivable_detail', kwargs={'pk': cheque.pk})
    form = ChequeDepositActionForm(request.POST, user=request.user)

    if form.is_valid():
        bank_account = form.cleaned_data['deposit_bank_account']
        action_date = form.cleaned_data['action_date']
        notes = form.cleaned_data.get('notes', '')
        idempotency_key = request.POST.get('idempotency_key') or f"DEP-{cheque.id}-{uuid.uuid4().hex[:8]}"

        try:
            ChequeAccountingService.deposit_cheque(
                cheque_or_id=cheque.id,
                user=request.user,
                idempotency_key=idempotency_key,
                bank_account_id=bank_account.id,
                value_date=action_date,
                notes=notes
            )
            return _handle_response(request, True, _("تم إيداع الشيك بالبنك برسم التحصيل بنجاح."), redirect_url)
        except (ValidationError, Exception) as e:
            return _handle_response(request, False, str(e), redirect_url)

    error_msg = "; ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
    return _handle_response(request, False, error_msg, redirect_url)


@login_required
@permission_required('cheques.collect_cheque', raise_exception=True)
@require_POST
def cheque_collect_action(request, pk):
    """إثبات تحصيل الشيك البنكي (كلي أو جزئي)"""
    cheque = get_object_or_404(Cheque, pk=pk)
    redirect_url = reverse('cheques:receivable_detail', kwargs={'pk': cheque.pk})
    form = ChequeCollectActionForm(request.POST, user=request.user, cheque=cheque)

    if form.is_valid():
        amount_collected = form.cleaned_data['amount_collected']
        value_date = form.cleaned_data['value_date']
        exchange_rate = form.cleaned_data['exchange_rate']
        bank_charges = form.cleaned_data.get('bank_charges') or Decimal('0.00')
        bank_charges_vat = form.cleaned_data.get('bank_charges_vat') or Decimal('0.00')
        deposit_bank_account = form.cleaned_data.get('deposit_bank_account') or cheque.deposit_bank_account
        notes = form.cleaned_data.get('notes', '')
        user_key = request.POST.get('idempotency_key', '').strip()
        deposit_bank_id = deposit_bank_account.id if deposit_bank_account else None
        if user_key:
            idempotency_key = user_key
        else:
            sig = f"COL:{cheque.id}:{request.user.id}:{amount_collected}:{value_date}:{exchange_rate}:{bank_charges}:{bank_charges_vat}:{deposit_bank_id}"
            det_hash = hashlib.sha256(sig.encode('utf-8')).hexdigest()[:12]
            idempotency_key = f"COL-{cheque.id}-{det_hash}"

        try:
            ChequeAccountingService.collect_cheque(
                cheque_or_id=cheque.id,
                user=request.user,
                idempotency_key=idempotency_key,
                amount_collected=amount_collected,
                exchange_rate=exchange_rate,
                value_date=value_date,
                bank_charges=bank_charges,
                bank_charges_vat=bank_charges_vat,
                bank_account_id=deposit_bank_id,
                notes=notes
            )
            return _handle_response(request, True, _("تم تسجيل وقيد تحصيل الشيك بالبنك بنجاح."), redirect_url)
        except (ValidationError, Exception) as e:
            return _handle_response(request, False, str(e), redirect_url)

    error_msg = "; ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
    return _handle_response(request, False, error_msg, redirect_url)


@login_required
@permission_required('cheques.bounce_cheque', raise_exception=True)
@require_POST
def cheque_bounce_action(request, pk):
    """إثبات ارتداد ورفض الشيك بالبنك"""
    cheque = get_object_or_404(Cheque, pk=pk)
    detail_route = 'cheques:receivable_detail' if cheque.cheque_type == ChequeType.RECEIVABLE else 'cheques:payable_detail'
    redirect_url = reverse(detail_route, kwargs={'pk': cheque.pk})
    form = ChequeBounceActionForm(request.POST, request.FILES)

    if form.is_valid():
        action_date = form.cleaned_data['action_date']
        bounce_reason = form.cleaned_data['bounce_reason']
        rejection_notice_image = form.cleaned_data.get('rejection_notice_image')
        notes = form.cleaned_data.get('notes', '')
        idempotency_key = request.POST.get('idempotency_key') or f"BNC-{cheque.id}-{uuid.uuid4().hex[:8]}"

        try:
            ChequeAccountingService.bounce_cheque(
                cheque_or_id=cheque.id,
                user=request.user,
                idempotency_key=idempotency_key,
                value_date=action_date,
                reason=bounce_reason,
                rejection_slip_image=rejection_notice_image,
                notes=notes
            )
            return _handle_response(request, True, _("تم تسجيل ارتداد الشيك وتحديث القيود والأرصدة بنجاح."), redirect_url)
        except (ValidationError, Exception) as e:
            return _handle_response(request, False, str(e), redirect_url)

    error_msg = "; ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
    return _handle_response(request, False, error_msg, redirect_url)


@login_required
@permission_required('cheques.endorse_cheque', raise_exception=True)
@require_POST
def cheque_endorse_action(request, pk):
    """تظهير شيك القبض لصالح مورد أو جهة خارجية"""
    cheque = get_object_or_404(Cheque, pk=pk, cheque_type=ChequeType.RECEIVABLE)
    redirect_url = reverse('cheques:receivable_detail', kwargs={'pk': cheque.pk})
    form = ChequeEndorseActionForm(request.POST)

    if form.is_valid():
        supplier = form.cleaned_data['supplier']
        action_date = form.cleaned_data['action_date']
        notes = form.cleaned_data.get('notes', '')
        idempotency_key = request.POST.get('idempotency_key') or f"END-{cheque.id}-{uuid.uuid4().hex[:8]}"

        try:
            ChequeAccountingService.endorse_cheque(
                cheque_or_id=cheque.id,
                user=request.user,
                idempotency_key=idempotency_key,
                supplier_id=supplier.id,
                value_date=action_date,
                notes=notes
            )
            return _handle_response(request, True, _("تم تظهير الشيك بنجاح وقيد مديونية المورد."), redirect_url)
        except (ValidationError, Exception) as e:
            return _handle_response(request, False, str(e), redirect_url)

    error_msg = "; ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
    return _handle_response(request, False, error_msg, redirect_url)


@login_required
@permission_required('cheques.collect_cheque', raise_exception=True)
@require_POST
def cheque_clear_action(request, pk):
    """إثبات خصم وصرف شيك الدفع الصادر من الحساب البنكي"""
    cheque = get_object_or_404(Cheque, pk=pk, cheque_type=ChequeType.PAYABLE)
    redirect_url = reverse('cheques:payable_detail', kwargs={'pk': cheque.pk})
    clearing_date_raw = request.POST.get('clearing_date')
    if clearing_date_raw:
        if isinstance(clearing_date_raw, str):
            try:
                from datetime import datetime
                clearing_date = datetime.strptime(clearing_date_raw.strip(), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                clearing_date = timezone.now().date()
        else:
            clearing_date = clearing_date_raw
    else:
        clearing_date = timezone.now().date()
    idempotency_key = request.POST.get('idempotency_key') or f"CLR-{cheque.id}-{uuid.uuid4().hex[:8]}"

    try:
        ChequeAccountingService.clear_payable_cheque(
            cheque_or_id=cheque.id,
            user=request.user,
            idempotency_key=idempotency_key,
            value_date=clearing_date,
        )
        return _handle_response(request, True, _("تم إثبات صرف وخصم الشيك من الحساب البنكي بنجاح."), redirect_url)
    except (ValidationError, Exception) as e:
        return _handle_response(request, False, str(e), redirect_url)


@login_required
@permission_required('cheques.reverse_cheque_action', raise_exception=True)
@require_POST
def cheque_reverse_action(request, pk):
    """التراجع الخطي (LIFO) وعكس آخر حركة محاسبية للشيك"""
    cheque = get_object_or_404(Cheque, pk=pk)
    detail_route = 'cheques:receivable_detail' if cheque.cheque_type == ChequeType.RECEIVABLE else 'cheques:payable_detail'
    redirect_url = reverse(detail_route, kwargs={'pk': cheque.pk})
    form = ChequeReversalActionForm(request.POST)

    if form.is_valid():
        reason = form.cleaned_data['reason']
        idempotency_key = request.POST.get('idempotency_key') or f"REV-{cheque.id}-{uuid.uuid4().hex[:8]}"
        try:
            ChequeReversalService.reverse_last_action(
                cheque_id=cheque.id,
                user=request.user,
                reason=reason,
                idempotency_key=idempotency_key
            )
            return _handle_response(request, True, _("تم التراجع المحاسبي عن الحركة وعكس القيد بنجاح."), redirect_url)
        except (ValidationError, Exception) as e:
            return _handle_response(request, False, str(e), redirect_url)

    error_msg = "; ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
    return _handle_response(request, False, error_msg, redirect_url)


@login_required
@permission_required('cheques.add_cheque', raise_exception=True)
@require_POST
def cheque_receive_action(request, pk):
    """اعتماد واستلام شيك قبض ونقله من مسودة إلى المحفظة وترحيل قيده"""
    cheque = get_object_or_404(Cheque, pk=pk, cheque_type=ChequeType.RECEIVABLE)
    redirect_url = reverse('cheques:receivable_detail', kwargs={'pk': cheque.pk})
    idempotency_key = request.POST.get('idempotency_key') or f"REC-{cheque.id}-{uuid.uuid4().hex[:8]}"
    try:
        ChequeAccountingService.receive_cheque(
            cheque_or_id=cheque.id,
            user=request.user,
            idempotency_key=idempotency_key
        )
        return _handle_response(request, True, _("تم اعتماد واستلام شيك القبض وترحيل قيده للمحفظة بنجاح."), redirect_url)
    except (ValidationError, Exception) as e:
        return _handle_response(request, False, str(e), redirect_url)


@login_required
@permission_required('cheques.add_cheque', raise_exception=True)
@require_POST
def cheque_issue_action(request, pk):
    """اعتماد وإصدار شيك دفع ونقله من مسودة إلى صادر وحجز السقف وترحيل قيده"""
    cheque = get_object_or_404(Cheque, pk=pk, cheque_type=ChequeType.PAYABLE)
    redirect_url = reverse('cheques:payable_detail', kwargs={'pk': cheque.pk})
    idempotency_key = request.POST.get('idempotency_key') or f"ISS-{cheque.id}-{uuid.uuid4().hex[:8]}"
    try:
        ChequeAccountingService.issue_cheque(
            cheque_or_id=cheque.id,
            user=request.user,
            idempotency_key=idempotency_key,
            request=request
        )
        return _handle_response(request, True, _("تم اعتماد وإصدار شيك الدفع وترحيل قيده بنجاح."), redirect_url)
    except (ValidationError, Exception) as e:
        return _handle_response(request, False, str(e), redirect_url)


@login_required
@permission_required('cheques.cancel_cheque', raise_exception=True)
@require_POST
def cheque_cancel_action(request, pk):
    """إلغاء شيك دفع أو قبض"""
    cheque = get_object_or_404(Cheque, pk=pk)
    detail_route = 'cheques:receivable_detail' if cheque.cheque_type == ChequeType.RECEIVABLE else 'cheques:payable_detail'
    redirect_url = reverse(detail_route, kwargs={'pk': cheque.pk})
    idempotency_key = request.POST.get('idempotency_key') or f"CAN-{cheque.id}-{uuid.uuid4().hex[:8]}"
    reason = request.POST.get('reason', '') or str(_("إلغاء بطلب إداري"))
    try:
        ChequeAccountingService.cancel_cheque(
            cheque_or_id=cheque.id,
            user=request.user,
            idempotency_key=idempotency_key,
            reason=reason
        )
        return _handle_response(request, True, _("تم إلغاء الشيك وعكس أثره المحاسبي بنجاح."), redirect_url)
    except (ValidationError, Exception) as e:
        return _handle_response(request, False, str(e), redirect_url)


@login_required
@permission_required('cheques.convert_guarantee', raise_exception=True)
@require_POST
def cheque_convert_guarantee_action(request, pk):
    """تحويل شيك الضمان خارج الميزانية إلى شيك تجاري ساري وتوليد قيده"""
    cheque = get_object_or_404(Cheque, pk=pk)
    detail_route = 'cheques:receivable_detail' if cheque.cheque_type == ChequeType.RECEIVABLE else 'cheques:payable_detail'
    redirect_url = reverse(detail_route, kwargs={'pk': cheque.pk})
    form = ChequeConvertGuaranteeActionForm(request.POST)

    if form.is_valid():
        new_purpose = form.cleaned_data['new_purpose']
        approval_notes = form.cleaned_data.get('approval_notes', '')

        try:
            user_key = request.POST.get('idempotency_key', '').strip()
            idempotency_key = user_key or f"CONV-{cheque.id}-{uuid.uuid4().hex[:8]}"

            ChequeAccountingService.convert_guarantee(
                cheque_or_id=cheque.id,
                user=request.user,
                new_purpose=new_purpose,
                idempotency_key=idempotency_key,
                reason=approval_notes
            )

            return _handle_response(request, True, _("تم اعتماد تحويل شيك الضمان إلى شيك تجاري وترحيل قيده بنجاح."), redirect_url)
        except (ValidationError, Exception) as e:
            return _handle_response(request, False, str(e), redirect_url)

    error_msg = "; ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
    return _handle_response(request, False, error_msg, redirect_url)
