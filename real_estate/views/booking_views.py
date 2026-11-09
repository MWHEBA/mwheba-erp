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
            payment_account_id = request.POST.get('payment_account_id')
            payment_account = ChartOfAccounts.objects.filter(pk=payment_account_id).first() if payment_account_id else None

            from real_estate.services.booking_service import UnitBookingService
            try:
                UnitBookingService.cancel_booking(
                    booking_id=booking.id,
                    reason=reason,
                    forfeit_deposit=forfeit,
                    user=request.user,
                    payment_account=payment_account
                )
                messages.success(request, _('تم إلغاء الحجز وإعادة إتاحة الوحدة للبيع بنجاح.'))
            except Exception as e:
                messages.error(request, _('فشل إلغاء الحجز: %(err)s') % {'err': str(e)})
            return redirect('real_estate:booking_detail', pk=pk)

        elif action == 'refund':
            payment_account_id = request.POST.get('refund_account') or request.POST.get('payment_account_id')
            if not payment_account_id:
                messages.error(request, _('يرجى اختيار حساب الخزينة أو البنك لصرف الاسترداد.'))
                return redirect('real_estate:booking_detail', pk=pk)

            payment_account = get_object_or_404(ChartOfAccounts, pk=payment_account_id)
            from real_estate.services.booking_service import UnitBookingService
            try:
                UnitBookingService.process_booking_refund(
                    booking_id=booking.id,
                    payment_account=payment_account,
                    user=request.user
                )
                messages.success(request, _('تم صرف واسترداد جدية الحجز بنجاح وتوليد سند الصرف المحاسبي.'))
            except Exception as e:
                messages.error(request, _('فشل صرف الاسترداد: %(err)s') % {'err': str(e)})
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

        context = {
            'booking': booking,
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

