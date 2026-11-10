# -*- coding: utf-8 -*-
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from django.db.models import Q, Sum

from django.contrib import messages
from django.utils import timezone

from users.mixins import SmartPermissionRequiredMixin
from real_estate.models import UnitBooking, RealEstateProject
from customer.models import Customer
from financial.models.chart_of_accounts import ChartOfAccounts


class BookingListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    قائمة استمارات الحجز وأمانات جدية الحجز
    """
    permission_required = 'real_estate.view_unitbooking'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()
        project_id = request.GET.get('project', '').strip()

        bookings_qs = UnitBooking.objects.select_related('customer', 'unit__project').order_by('-booking_date', '-id')

        if search_query:
            bookings_qs = bookings_qs.filter(
                Q(booking_number__icontains=search_query) |
                Q(customer__name__icontains=search_query) |
                Q(unit__unit_code__icontains=search_query)
            )

        if status_filter:
            bookings_qs = bookings_qs.filter(status=status_filter)

        if project_id:
            bookings_qs = bookings_qs.filter(unit__project_id=project_id)

        paginator = Paginator(bookings_qs, 15)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('ajax') == '1':
            table_html = render_to_string(
                'real_estate/partials/booking_table.html',
                {'page_obj': page_obj, 'bookings': page_obj.object_list},
                request=request
            )
            pagination_html = render_to_string(
                'partials/pagination.html',
                {'page_obj': page_obj},
                request=request
            )
            return JsonResponse({
                'success': True,
                'table_html': table_html,
                'pagination_html': pagination_html,
                'total_count': paginator.count
            })

        total_bookings = UnitBooking.objects.count()
        active_count = UnitBooking.objects.filter(status=UnitBooking.BookingStatus.ACTIVE).count()
        pending_refund_count = UnitBooking.objects.filter(status=UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND).count()
        total_holding_deposits = UnitBooking.objects.filter(status=UnitBooking.BookingStatus.ACTIVE).aggregate(s=Sum('holding_deposit'))['s'] or Decimal('0.00')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('استمارات الحجز والأمانات'), 'active': True}
        ]

        context = {
            'page_obj': page_obj,
            'bookings': page_obj.object_list,
            'projects': RealEstateProject.objects.filter(is_archived=False),
            'total_bookings': total_bookings,
            'active_count': active_count,
            'pending_refund_count': pending_refund_count,
            'total_holding_deposits': total_holding_deposits,
            'status_choices': UnitBooking.BookingStatus.choices,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 'real_estate',
            'active_submenu': 'bookings',
        }
        return render(request, 'real_estate/booking_list.html', context)


class BookingDetailView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تفاصيل استمارة الحجز وسند التحصيل وقيد الأمانات مع معالجات الإلغاء والاسترداد الآمنة
    """
    permission_required = 'real_estate.view_unitbooking'

    def get(self, request, pk):
        booking = get_object_or_404(
            UnitBooking.objects.select_related('customer', 'unit__project', 'journal_entry', 'created_by', 'active_cancellation_settlement'),
            pk=pk
        )
        payment_accounts = ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True,
            account_type__category='asset',
            code__startswith='111'
        )

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('الحجوزات'), 'url': reverse('real_estate:booking_list'), 'icon': 'fa-bookmark'},
            {'title': booking.booking_number, 'active': True}
        ]

        header_buttons = [
            {
                'url': reverse('real_estate:booking_print', kwargs={'pk': booking.pk}),
                'icon': 'fa-print',
                'text': _('طباعة استمارة الحجز'),
                'class': 'btn-outline-primary',
                'target': '_blank',
            }
        ]

        context = {
            'booking': booking,
            'settlement': getattr(booking, 'active_cancellation_settlement', None),
            'payment_accounts': payment_accounts,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 'real_estate',
            'active_submenu': 'bookings',
        }
        return render(request, 'real_estate/booking_detail.html', context)

    def post(self, request, pk):
        booking = get_object_or_404(
            UnitBooking.objects.select_related('customer', 'unit__project'),
            pk=pk
        )
        action = request.POST.get('action') or ('cancel' if 'reason' in request.POST else ('refund' if 'refund_account' in request.POST else None))

        if action == 'cancel':
            reason = request.POST.get('reason', _('إلغاء بناء على رغبة العميل'))
            disposition = request.POST.get('disposition', 'REFUND')
            forfeit = (disposition == 'FORFEIT')
            deduction_fees_raw = request.POST.get('deduction_fees', '0')
            try:
                deduction_fees = Decimal(str(deduction_fees_raw))
            except Exception:
                deduction_fees = Decimal('0.00')

            payment_account_id = request.POST.get('payment_account_id')
            payment_account = ChartOfAccounts.objects.filter(pk=payment_account_id).first() if payment_account_id else None

            from real_estate.services.booking_service import UnitBookingService
            try:
                UnitBookingService.cancel_booking(
                    booking_id=booking.id,
                    reason=reason,
                    forfeit_deposit=forfeit,
                    approved_deduction_fees=deduction_fees,
                    user=request.user,
                    payment_account=payment_account
                )
                messages.success(request, _('تم إلغاء الحجز وإعادة إتاحة الوحدة للبيع بنجاح.'))
            except Exception as e:
                messages.error(request, _('فشل إلغاء الحجز: %(err)s') % {'err': str(e)})
            return redirect('real_estate:booking_detail', pk=pk)

        elif action == 'refund':
            method = request.POST.get('method') or request.POST.get('refund_method') or 'BANK_TRANSFER'
            payment_account_id = request.POST.get('refund_account') or request.POST.get('payment_account_id')

            cheque_data = None
            if method == 'CHEQUE':
                cheque_num = (request.POST.get('cheque_number') or '').strip()
                if not cheque_num:
                    messages.error(request, _('رقم الشيك إلزامي للصرف بشيك مصرفي.'))
                    return redirect('real_estate:booking_detail', pk=pk)
                cheque_data = {
                    'cheque_number': cheque_num,
                    'due_date': request.POST.get('due_date') or timezone.localdate(),
                    'drawer_bank_name': request.POST.get('drawer_bank_name', ''),
                    'payee_name': request.POST.get('payee_name', ''),
                }
            elif not payment_account_id:
                messages.error(request, _('يرجى اختيار حساب الخزينة أو البنك لصرف الاسترداد.'))
                return redirect('real_estate:booking_detail', pk=pk)

            payment_account = ChartOfAccounts.objects.filter(pk=payment_account_id).first() if payment_account_id else None
            from real_estate.services.booking_service import UnitBookingService
            try:
                UnitBookingService.process_booking_refund(
                    booking_id=booking.id,
                    payment_account=payment_account,
                    method=method,
                    cheque_data=cheque_data,
                    user=request.user
                )
                messages.success(request, _('تم صرف واسترداد جدية الحجز بنجاح وتوليد سند الصرف المحاسبي.'))
            except Exception as e:
                messages.error(request, _('فشل صرف الاسترداد: %(err)s') % {'err': str(e)})
            return redirect('real_estate:booking_detail', pk=pk)

        elif action == 'review_sales':
            from real_estate.services.booking_service import UnitBookingService, BookingValidationError
            try:
                UnitBookingService.review_booking_sales(booking_id=booking.id, user=request.user)
                messages.success(request, _('تم تسجيل مراجعة المبيعات والحسابات للحجز بنجاح.'))
            except (BookingValidationError, ValidationError) as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, _('فشل تسجيل مراجعة المبيعات: %(err)s') % {'err': str(e)})
            return redirect('real_estate:booking_detail', pk=pk)

        elif action == 'confirm_audit':
            from real_estate.services.booking_service import UnitBookingService, BookingValidationError
            try:
                UnitBookingService.confirm_booking_audit(booking_id=booking.id, user=request.user)
                messages.success(request, _('تم الاعتماد المالي والرقابي للحجز بنجاح، وأصبح جاهزاً للتحويل إلى عقد بيع.'))
            except (BookingValidationError, ValidationError) as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, _('فشل الاعتماد الرقابي: %(err)s') % {'err': str(e)})
            return redirect('real_estate:booking_detail', pk=pk)

        elif action == 'bypass_audit':
            from real_estate.services.booking_service import UnitBookingService, BookingValidationError
            reason = request.POST.get('bypass_reason', '').strip()
            try:
                UnitBookingService.bypass_booking_audit(booking_id=booking.id, user=request.user, reason=reason)
                messages.warning(request, _('تم تسجيل التجاوز الإداري الاستثنائي للرقابة الثنائية بنجاح.'))
            except (BookingValidationError, ValidationError) as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, _('فشل تسجيل التجاوز الإداري: %(err)s') % {'err': str(e)})
            return redirect('real_estate:booking_detail', pk=pk)

        messages.warning(request, _('إجراء غير معروف.'))
        return redirect('real_estate:booking_detail', pk=pk)


class BookingOfficialPrintView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    طباعة استمارة حجز الوحدة وإيصال أمانة جدية الحجز (مع ختم التوثيق الرقمي SHA-256 ورمز QR المباشر)
    """
    permission_required = 'real_estate.view_unitbooking'

    def get(self, request, pk):
        import hashlib
        import io
        import base64
        import qrcode

        booking = get_object_or_404(
            UnitBooking.objects.select_related(
                'customer', 'unit__project', 'unit__floor__block', 'journal_entry', 'created_by'
            ),
            pk=pk
        )

        raw_seed = (
            f"BKG:{booking.booking_number}:{booking.customer_id}:{booking.unit_id}:"
            f"{booking.holding_deposit}:{booking.booking_date}:{booking.status}"
        )
        verification_hash = hashlib.sha256(raw_seed.encode('utf-8')).hexdigest()

        # توليد رابط ورمز QR للتحقق الرقمي اللحظي
        verification_url = request.build_absolute_uri(
            reverse('real_estate:booking_public_verify', kwargs={'token': booking.verification_uuid})
        )

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=4,
            border=1,
        )
        qr.add_data(verification_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        qr_code_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        # استخراج وتوثيق وسيلة السداد القانونية للإيصال
        payment_info = {
            'instrument_type': _('نقداً بالخزينة'),
            'account_name': '',
            'account_code': '',
            'reference': booking.booking_number,
            'entry_number': booking.journal_entry.entry_number if (booking.journal_entry and hasattr(booking.journal_entry, 'entry_number')) else (f"#{booking.journal_entry_id}" if booking.journal_entry_id else '-'),
            'date': booking.booking_date,
        }
        if booking.journal_entry:
            debit_line = booking.journal_entry.lines.filter(debit__gt=0).select_related('account').first()
            if debit_line and debit_line.account:
                payment_info['account_name'] = debit_line.account.name
                payment_info['account_code'] = debit_line.account.code
                if debit_line.account.code.startswith('1111'):
                    payment_info['instrument_type'] = _('نقداً (إيصال توريد نقدية بالخزينة)')
                elif debit_line.account.code.startswith('1112'):
                    payment_info['instrument_type'] = _('تحويل بنكي / إيداع مباشر بحساب الشركة')
                elif debit_line.account.code.startswith('112') or debit_line.account.code.startswith('1113'):
                    payment_info['instrument_type'] = _('شيك بنكي تحت التحصيل')
                else:
                    payment_info['instrument_type'] = _('سداد مصرفي معتمد')
                if debit_line.description:
                    payment_info['reference'] = debit_line.description

        context = {
            'booking': booking,
            'payment_info': payment_info,
            'verification_hash': verification_hash,
            'verification_token': str(booking.verification_uuid).upper()[:16],
            'verification_url': verification_url,
            'qr_code_base64': qr_code_base64,
            'today': timezone.localdate(),
        }
        return render(request, 'real_estate/booking_print.html', context)


class BookingPublicVerificationView(View):
    """
    شاشة التحقق الرقمي اللحظي العامة من صحة استمارة الحجز (Public Verification Portal)
    متاحة للجمهور عبر مسح رمز الاستجابة السريعة QR أو الرابط المباشر
    """
    def get(self, request, token):
        booking = get_object_or_404(
            UnitBooking.objects.select_related(
                'customer', 'unit__project', 'unit__floor__block', 'currency', 'active_cancellation_settlement'
            ),
            verification_uuid=token
        )

        import hashlib
        raw_seed = (
            f"BKG:{booking.booking_number}:{booking.customer_id}:{booking.unit_id}:"
            f"{booking.holding_deposit}:{booking.booking_date}:{booking.status}"
        )
        verification_hash = hashlib.sha256(raw_seed.encode('utf-8')).hexdigest()

        # قناع اسم العميل لحماية الخصوصية
        c_name = booking.customer.name.strip()
        parts = c_name.split()
        if len(parts) >= 2:
            masked_name = f"{parts[0]} {'*' * min(5, len(parts[1]))} {parts[-1]}"
        else:
            masked_name = f"{c_name[:2]}{'*' * max(1, len(c_name)-2)}"

        context = {
            'booking': booking,
            'masked_name': masked_name,
            'verification_hash': verification_hash,
            'verification_token': str(booking.verification_uuid).upper()[:16],
            'is_valid': True,
            'verified_at': timezone.now(),
        }
        return render(request, 'real_estate/booking_public_verify.html', context)


class BookingRecoveryListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    سجل ومتابعة تسويات واسترداد جدية الحجوزات والشيكات الصادرة (Booking Recovery Operational Register)
    """
    permission_required = 'real_estate.view_unitbooking'

    def get(self, request):
        from real_estate.models.refund import BookingCancellationSettlement, RefundDisbursementPayment

        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()
        method_filter = request.GET.get('method', '').strip()

        settlements_qs = BookingCancellationSettlement.objects.select_related(
            'booking__customer', 'booking__unit__project', 'currency', 'processed_by'
        ).prefetch_related('disbursements__cheque', 'disbursements__payment_account').order_by('-settlement_date', '-id')

        if search_query:
            settlements_qs = settlements_qs.filter(
                Q(settlement_number__icontains=search_query) |
                Q(booking__booking_number__icontains=search_query) |
                Q(booking__customer__name__icontains=search_query) |
                Q(booking__unit__unit_code__icontains=search_query) |
                Q(disbursements__cheque__cheque_number__icontains=search_query)
            ).distinct()

        if status_filter:
            settlements_qs = settlements_qs.filter(status=status_filter)

        if method_filter:
            settlements_qs = settlements_qs.filter(disbursements__method=method_filter).distinct()

        # KPI Metrics
        all_settlements = BookingCancellationSettlement.objects.all()
        total_settlements_count = all_settlements.count()
        total_deposit_sum = all_settlements.aggregate(s=Sum('total_deposit_paid'))['s'] or Decimal('0.00')
        total_deductions_sum = all_settlements.aggregate(s=Sum('approved_deduction_fees'))['s'] or Decimal('0.00')
        total_net_refundable_sum = all_settlements.aggregate(s=Sum('net_refundable_amount'))['s'] or Decimal('0.00')
        total_cleared_sum = all_settlements.aggregate(s=Sum('cleared_amount'))['s'] or Decimal('0.00')
        total_remaining_sum = all_settlements.aggregate(s=Sum('remaining_disbursable_amount'))['s'] or Decimal('0.00')

        cheques_count = RefundDisbursementPayment.objects.filter(
            method=RefundDisbursementPayment.DisbursementMethod.CHEQUE
        ).count()

        paginator = Paginator(settlements_qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': _('استمارات الحجز'), 'url': reverse('real_estate:booking_list'), 'icon': 'fa-calendar-check'},
            {'title': _('سجل تسويات واسترداد الحجوزات'), 'active': True},
        ]

        header_buttons = [
            {
                'url': reverse('real_estate:booking_list'),
                'label': _('قائمة استمارات الحجز'),
                'icon': 'fa-calendar-check',
                'class': 'btn-outline-secondary',
            }
        ]

        context = {
            'settlements': page_obj.object_list,
            'page_obj': page_obj,
            'search_query': search_query,
            'status_filter': status_filter,
            'method_filter': method_filter,
            'total_settlements_count': total_settlements_count,
            'total_deposit_sum': total_deposit_sum,
            'total_deductions_sum': total_deductions_sum,
            'total_net_refundable_sum': total_net_refundable_sum,
            'total_cleared_sum': total_cleared_sum,
            'total_remaining_sum': total_remaining_sum,
            'cheques_count': cheques_count,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 'real_estate',
            'active_submenu': 'booking_recovery',
        }
        return render(request, 'real_estate/booking_recovery_list.html', context)

