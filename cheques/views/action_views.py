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

from cheques.models import (
    Cheque,
    ChequeType,
    ChequeStatus,
    ChequeActionLog,
    ChequeActionType,
    ChequeInvoiceAllocation,
    AllocationStatus,
)
from cheques.services.accounting_service import ChequeAccountingService
from cheques.services.reversal_service import ChequeReversalService
from cheques.services.allocation_service import ChequeAllocationService
from cheques.forms.action_forms import (
    ChequeDepositActionForm,
    ChequeCollectActionForm,
    ChequeBounceActionForm,
    ChequeEndorseActionForm,
    ChequeReversalActionForm,
    ChequeConvertGuaranteeActionForm,
    ChequeClearActionForm,
    ChequeReturnToDrawerActionForm,
    ChequeAllocateToInvoiceForm,
    ChequeDeallocateActionForm,
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
    """إثبات خصم وصرف شيك الدفع الصادر من الحساب البنكي مع معالجة فروق الصرف"""
    cheque = get_object_or_404(Cheque, pk=pk, cheque_type=ChequeType.PAYABLE)
    redirect_url = reverse('cheques:payable_detail', kwargs={'pk': cheque.pk})
    form = ChequeClearActionForm(request.POST, user=request.user, cheque=cheque)

    if form.is_valid():
        clearing_date = form.cleaned_data['clearing_date']
        exchange_rate = form.cleaned_data.get('exchange_rate') or cheque.original_exchange_rate or Decimal('1.000000')
        bank_account = form.cleaned_data.get('bank_account')
        notes = form.cleaned_data.get('notes', '')
        user_key = form.cleaned_data.get('idempotency_key') or request.POST.get('idempotency_key', '').strip()
        idempotency_key = user_key or f"CLR-{cheque.id}-{uuid.uuid4().hex[:8]}"

        try:
            ChequeAccountingService.clear_payable_cheque(
                cheque_or_id=cheque.id,
                user=request.user,
                idempotency_key=idempotency_key,
                value_date=clearing_date,
                exchange_rate=exchange_rate,
                bank_account_id=bank_account.id if bank_account else None,
                notes=notes,
            )
            return _handle_response(request, True, _("تم إثبات صرف وخصم الشيك من الحساب البنكي بنجاح."), redirect_url)
        except (ValidationError, Exception) as e:
            return _handle_response(request, False, str(e), redirect_url)

    error_msg = "; ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
    return _handle_response(request, False, error_msg, redirect_url)


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


@login_required
@permission_required('cheques.bounce_cheque', raise_exception=True)
@require_POST
def cheque_return_to_drawer_action(request, pk):
    """رد واسترداد شيك القبض للساحب مع إقفاله وإعادة فتح المديونية أو الدفعة المقدمة"""
    cheque = get_object_or_404(Cheque, pk=pk, cheque_type=ChequeType.RECEIVABLE)
    redirect_url = reverse('cheques:receivable_detail', kwargs={'pk': cheque.pk})
    form = ChequeReturnToDrawerActionForm(request.POST)

    if form.is_valid():
        action_date = form.cleaned_data['action_date']
        reason = form.cleaned_data['reason']
        user_key = form.cleaned_data.get('idempotency_key') or request.POST.get('idempotency_key', '').strip()
        idempotency_key = user_key or f"RTD-{cheque.id}-{uuid.uuid4().hex[:8]}"

        try:
            ChequeAccountingService.return_to_drawer(
                cheque_or_id=cheque.id,
                user=request.user,
                idempotency_key=idempotency_key,
                value_date=action_date,
                reason=reason,
            )
            return _handle_response(request, True, _("تم إثبات رد الشيك للساحب وترحيل القيد المحاسبي بنجاح."), redirect_url)
        except (ValidationError, Exception) as e:
            return _handle_response(request, False, str(e), redirect_url)

    error_msg = "; ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
    return _handle_response(request, False, error_msg, redirect_url)


@login_required
@permission_required('cheques.change_cheque', raise_exception=True)
@require_POST
def cheque_allocate_invoice_action(request, pk):
    """تخصيص شيك القبض على فاتورة مبيعات محددة"""
    cheque = get_object_or_404(Cheque, pk=pk, cheque_type=ChequeType.RECEIVABLE)
    redirect_url = reverse('cheques:receivable_detail', kwargs={'pk': cheque.pk})

    if cheque.status in [ChequeStatus.DRAFT, ChequeStatus.BOUNCED, ChequeStatus.CANCELLED, ChequeStatus.RETURNED_TO_DRAWER]:
        return _handle_response(
            request, False,
            _("لا يمكن تخصيص شيك في حالة: {status}.").format(status=cheque.get_status_display()),
            redirect_url
        )

    if cheque.is_guarantee:
        return _handle_response(
            request, False,
            _("لا يمكن تخصيص شيك الضمان على فواتير المبيعات قبل تحويله إلى شيك تشغيلي."),
            redirect_url
        )

    # 1. فحص مسبق لمنع التكرار الحتمي (Idempotency Replay Guard)
    user_key = request.POST.get('idempotency_key', '').strip()
    if user_key:
        from customer.models import CustomerAllocationAudit
        alloc_ref = f"ALLOC:{user_key}"
        existing_audit = CustomerAllocationAudit.objects.filter(
            allocation_reference=alloc_ref,
            allocation_status="APPLIED"
        ).first()
        if existing_audit:
            existing_alloc = ChequeInvoiceAllocation.objects.filter(
                allocation_audit=existing_audit
            ).first()
            if existing_alloc:
                post_sale_id = request.POST.get('sale')
                post_amount_raw = request.POST.get('amount')
                try:
                    post_amount = Decimal(str(post_amount_raw)) if post_amount_raw else None
                except Exception:
                    post_amount = None

                # التحقق من تطابق الشيك والفاتورة والمبلغ لمنع التعارض والنجاح المضلل
                if (
                    existing_alloc.cheque_id != cheque.id
                    or (post_sale_id and str(existing_alloc.sale_id) != str(post_sale_id))
                    or (post_amount is not None and existing_alloc.allocated_amount != post_amount)
                ):
                    return _handle_response(
                        request, False,
                        _("تعارض في مفتاح عدم التكرار: المفتاح مستخدم مسبقاً لعملية تخصيص أخرى أو بمبلغ مختلف."),
                        redirect_url
                    )

                # مطابقة تامة: إعادة نجاح فوري للعملية السابقة دون أي إعادة خصم أو خطأ في الرصيد المتبقي
                return _handle_response(
                    request, True,
                    _("تم تخصيص الشيك بمبلغ {amount} على فاتورة المبيعات رقم {sale_num} بنجاح.").format(
                        amount=existing_alloc.allocated_amount, sale_num=existing_alloc.sale.number
                    ),
                    redirect_url
                )

    form = ChequeAllocateToInvoiceForm(request.POST, cheque=cheque, user=request.user)
    if form.is_valid():
        sale = form.cleaned_data['sale']
        amount = form.cleaned_data['amount']
        notes = form.cleaned_data.get('notes', '')
        idempotency_key = user_key or f"ALLOC-{cheque.id}-{sale.id}-{uuid.uuid4().hex[:8]}"

        try:
            alloc = ChequeAllocationService.allocate_cheque_to_invoice(
                cheque=cheque,
                sale=sale,
                amount=amount,
                user=request.user,
                notes=notes,
                idempotency_key=idempotency_key
            )
            return _handle_response(
                request, True,
                _("تم تخصيص الشيك بمبلغ {amount} على فاتورة المبيعات رقم {sale_num} بنجاح.").format(
                    amount=amount, sale_num=sale.number
                ),
                redirect_url
            )
        except (ValidationError, Exception) as e:
            return _handle_response(request, False, str(e), redirect_url)

    error_msg = "; ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
    return _handle_response(request, False, error_msg, redirect_url)


@login_required
@permission_required('cheques.change_cheque', raise_exception=True)
@require_POST
def cheque_deallocate_invoice_action(request, pk, allocation_id):
    """إلغاء وفك تخصيص الشيك عن فاتورة المبيعات واستعادة مديونيتها"""
    cheque = get_object_or_404(Cheque, pk=pk, cheque_type=ChequeType.RECEIVABLE)
    redirect_url = reverse('cheques:receivable_detail', kwargs={'pk': cheque.pk})
    allocation = get_object_or_404(ChequeInvoiceAllocation, pk=allocation_id, cheque=cheque)

    form = ChequeDeallocateActionForm(request.POST)
    if form.is_valid():
        reason = form.cleaned_data['reason']

        try:
            ChequeAllocationService.reverse_cheque_allocation(
                allocation=allocation,
                reason=reason,
                user=request.user
            )
            return _handle_response(
                request, True,
                _("تم فك وإلغاء تخصيص الشيك على الفاتورة رقم {sale_num} بنجاح.").format(
                    sale_num=allocation.sale.number
                ),
                redirect_url
            )
        except (ValidationError, Exception) as e:
            return _handle_response(request, False, str(e), redirect_url)

    error_msg = "; ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
    return _handle_response(request, False, error_msg, redirect_url)


