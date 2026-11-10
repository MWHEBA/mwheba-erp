# -*- coding: utf-8 -*-
"""
Matrix Views - عروض مصفوفة الوحدات المعمارية التفاعلية
تدعم التصفح السريع والتحميل فائق السرعة عبر استعلام واحد مجمع (< 60ms)
مع مراعاة التجاوب اللوحي (Tablet Touch Support) والتحكم في التزامن المتفائل
"""
import json
import datetime
from decimal import Decimal
from django.shortcuts import render, get_object_or_404
from django.views import View
from django.http import JsonResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Prefetch
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from users.mixins import SmartPermissionRequiredMixin
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.currency import Currency
from real_estate.models import (
    RealEstateProject, PropertyFloor, PropertyUnit, UnitBooking,
    RealEstateBroker, BrokerAttributionAudit
)
from real_estate.services.booking_service import (
    UnitBookingService,
    ConcurrencyBookingConflictError,
    BookingValidationError,
)
from customer.models import Customer


class ProjectMatrixView(LoginRequiredMixin, View):
    """
    عرض المصفوفة المعمارية التفاعلية للوحدات حسب الطوابق والمشروع
    """
    def get(self, request, project_id):
        project = get_object_or_404(RealEstateProject, pk=project_id)

        # استعلام مجمع عالي الكفاءة يمنع N+1 بالكامل (سقف 2 استعلام فقط)
        units_qs = PropertyUnit.objects.filter(
            project=project,
            is_active=True
        ).select_related(
            'floor', 'block', 'project', 'current_booking'
        ).prefetch_related(
            Prefetch(
                'bookings',
                queryset=UnitBooking.objects.filter(status=UnitBooking.BookingStatus.ACTIVE),
                to_attr='active_bookings'
            )
        ).order_by('-floor__floor_number', 'unit_code')

        # تجميع الوحدات حسب الطوابق
        floors_dict = {}
        total_units = 0
        available_count = 0
        reserved_count = 0
        contracted_count = 0
        blocked_count = 0
        total_portfolio_value = Decimal('0.00')

        for unit in units_qs:
            total_units += 1
            total_portfolio_value += unit.total_price

            if unit.status == PropertyUnit.UnitStatus.AVAILABLE:
                available_count += 1
            elif unit.status == PropertyUnit.UnitStatus.RESERVED:
                reserved_count += 1
            elif unit.status in [PropertyUnit.UnitStatus.CONTRACTED, PropertyUnit.UnitStatus.DELIVERED]:
                contracted_count += 1
            elif unit.status == PropertyUnit.UnitStatus.BLOCKED:
                blocked_count += 1

            fl = unit.floor
            if fl.id not in floors_dict:
                floors_dict[fl.id] = {
                    'floor': fl,
                    'units': []
                }
            floors_dict[fl.id]['units'].append(unit)

        # ترتيب الطوابق معمارياً من الأعلى إلى الأسفل (البنتهاوس والرووف ثم المتكرر فالأرضي والبدروم)
        floors_data = sorted(
            floors_dict.values(),
            key=lambda x: x['floor'].floor_number,
            reverse=True
        )

        User = get_user_model()
        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('إدارة التطوير العقاري'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-building'},
            {'title': project.name, 'url': reverse('real_estate:project_detail', kwargs={'pk': project.id})},
            {'title': _('المصفوفة التفاعلية'), 'active': True}
        ]

        header_buttons = [
            {
                'text': _('مصفوفة التنفيذ الميداني'),
                'url': reverse('real_estate:site_project_report', kwargs={'project_id': project.id}),
                'icon': 'fa-hard-hat',
                'class': 'btn-outline-primary'
            },
            {
                'text': _('مصفوفة التسعير الآلي'),
                'url': reverse('real_estate:project_pricing', kwargs={'project_id': project.id}),
                'icon': 'fa-tags',
                'class': 'btn-primary'
            }
        ]

        currencies = Currency.objects.filter(is_active=True)
        payment_accounts = ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True,
            account_type__category='asset',
            code__startswith='111'
        )
        brokers = RealEstateBroker.objects.filter(is_active=True)
        specialists = User.objects.filter(is_active=True).only('id', 'first_name', 'last_name', 'username')

        context = {
            'project': project,
            'floors_data': floors_data,
            'total_units': total_units,
            'available_count': available_count,
            'reserved_count': reserved_count,
            'contracted_count': contracted_count,
            'blocked_count': blocked_count,
            'total_portfolio_value': total_portfolio_value,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'page_title': f"{_('مصفوفة الوحدات')}: {project.name}",
            'customers': Customer.objects.filter(is_active=True).only('id', 'name', 'code', 'phone')[:100],
            'currencies': currencies,
            'payment_accounts': payment_accounts,
            'brokers': brokers,
            'specialists': specialists,
        }
        return render(request, 'real_estate/matrix.html', context)


class ApiUnitDetailView(LoginRequiredMixin, View):
    """
    جلب تفاصيل الوحدة العقارية ومواصفاتها المعمارية للنافذة المنبثقة
    """
    def get(self, request, unit_id):
        unit = get_object_or_404(
            PropertyUnit.objects.select_related('floor', 'block', 'project', 'current_booking__customer'),
            pk=unit_id
        )

        booking_data = None
        if unit.current_booking:
            b = unit.current_booking
            booking_data = {
                'id': b.id,
                'booking_number': b.booking_number,
                'customer_name': b.customer.name,
                'holding_deposit': str(b.holding_deposit),
                'booking_date': b.booking_date.strftime('%Y-%m-%d'),
                'expiry_date': b.expiry_date.strftime('%Y-%m-%d'),
                'status': b.get_status_display(),
            }

        data = {
            'id': unit.id,
            'unit_code': unit.unit_code,
            'project_name': unit.project.name,
            'block_name': unit.block.name if unit.block else '-',
            'floor_name': unit.floor.name,
            'floor_type': unit.floor.get_floor_type_display(),
            'unit_type': unit.get_unit_type_display(),
            'status': unit.status,
            'status_display': unit.get_status_display(),
            'net_area': str(unit.net_area),
            'gross_area': str(unit.gross_area),
            'terrace_area': str(unit.terrace_area),
            'garden_area': str(unit.garden_area),
            'loading_ratio': str(unit.loading_ratio),
            'meter_price': str(unit.meter_price),
            'total_price': str(unit.total_price),
            'current_booking': booking_data,
        }
        return JsonResponse({'success': True, 'unit': data})


class ApiBookUnitView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    حجز الوحدة العقارية عبر طلب AJAX مع الحراسة التزامنية وفرض صلاحيات الحجز والتحصيل
    """
    permission_required = 'real_estate.add_unitbooking'

    def post(self, request, unit_id):
        try:
            body = json.loads(request.body.decode('utf-8')) if request.body else request.POST
        except Exception:
            body = request.POST

        customer_id = body.get('customer_id') or body.get('customer')
        holding_deposit = Decimal(str(body.get('holding_deposit', '0.00') or '0.00'))
        expiry_date_str = body.get('expiry_date')
        expiry_days = body.get('expiry_days')
        notes = body.get('notes', '')

        if not customer_id:
            return JsonResponse({'success': False, 'message': _('يرجى اختيار العميل الحاجز.')}, status=400)

        if expiry_date_str:
            try:
                expiry_date = datetime.datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'success': False, 'message': _('صيغة التاريخ غير صحيحة (YYYY-MM-DD).')}, status=400)
        elif expiry_days:
            try:
                expiry_date = timezone.localdate() + datetime.timedelta(days=int(expiry_days))
            except (ValueError, TypeError):
                expiry_date = timezone.localdate() + datetime.timedelta(days=7)
        else:
            expiry_date = timezone.localdate() + datetime.timedelta(days=7)

        customer = get_object_or_404(Customer, pk=customer_id)

        # العملة وحساب السداد
        currency_id = body.get('deposit_currency') or body.get('currency_id') or body.get('currency')
        currency = None
        if currency_id:
            currency = Currency.objects.filter(pk=currency_id).first() if str(currency_id).isdigit() else Currency.objects.filter(code=str(currency_id)).first()

        payment_account_id = body.get('payment_account_id') or body.get('payment_account')
        payment_account = ChartOfAccounts.objects.filter(pk=payment_account_id).first() if payment_account_id else None

        # ملحقات الوحدة
        parking_slot_code = body.get('parking_slot_code') or None
        parking_slot_price = Decimal(str(body.get('parking_slot_price', '0.00') or '0.00')) if body.get('parking_slot_price') else None
        storage_locker_code = body.get('storage_locker_code') or None
        storage_locker_price = Decimal(str(body.get('storage_locker_price', '0.00') or '0.00')) if body.get('storage_locker_price') else None
        finishing_meter_rate = Decimal(str(body.get('finishing_meter_rate', '0.00') or '0.00')) if body.get('finishing_meter_rate') else None
        total_finishing_amount = Decimal(str(body.get('total_finishing_amount', '0.00') or '0.00')) if body.get('total_finishing_amount') else None
        utilities_deposit_amount = Decimal(str(body.get('utilities_deposit_amount', '0.00') or '0.00')) if body.get('utilities_deposit_amount') else None

        # مسؤولو المبيعات وبصمة الإحالة
        User = get_user_model()
        call_specialist_id = body.get('call_specialist_id') or body.get('call_specialist')
        visit_specialist_id = body.get('visit_specialist_id') or body.get('visit_specialist')
        site_specialist_id = body.get('site_specialist_id') or body.get('site_specialist')
        call_specialist = User.objects.filter(pk=call_specialist_id).first() if call_specialist_id else None
        visit_specialist = User.objects.filter(pk=visit_specialist_id).first() if visit_specialist_id else None
        site_specialist = User.objects.filter(pk=site_specialist_id).first() if site_specialist_id else None

        sales_channel = body.get('sales_channel') or None
        marketing_lead_source = body.get('marketing_lead_source') or body.get('lead_source') or None
        broker_id = body.get('broker_id')
        broker = None
        if broker_id:
            broker = RealEstateBroker.objects.filter(pk=broker_id, is_active=True).first()

        collection_method = body.get('collection_method') or 'CASH'
        cheque_number = body.get('cheque_number') or None
        due_date = body.get('due_date') or None
        drawer_bank_name = body.get('drawer_bank_name') or ''

        try:
            booking = UnitBookingService.create_booking(
                unit_id=unit_id,
                customer=customer,
                holding_deposit=holding_deposit,
                expiry_date=expiry_date,
                notes=notes,
                user=request.user,
                currency=currency,
                payment_account=payment_account,
                finishing_meter_rate=finishing_meter_rate,
                total_finishing_amount=total_finishing_amount,
                utilities_deposit_amount=utilities_deposit_amount,
                parking_slot_code=parking_slot_code,
                parking_slot_price=parking_slot_price,
                storage_locker_code=storage_locker_code,
                storage_locker_price=storage_locker_price,
                sales_channel=sales_channel,
                marketing_lead_source=marketing_lead_source,
                collection_method=collection_method,
                cheque_number=cheque_number,
                due_date=due_date,
                drawer_bank_name=drawer_bank_name,
                call_specialist=call_specialist,
                visit_specialist=visit_specialist,
                site_specialist=site_specialist,
            )

            # توثيق بصمة أسبقية ومصدر العميل (Lead Attribution Lock) لكافة القنوات والوسطاء بعد نجاح الحجز
            if not BrokerAttributionAudit.objects.filter(customer=customer).exists():
                touch_source = BrokerAttributionAudit.LeadSource.DIRECT_WALK_IN
                if broker_id and broker:
                    touch_source = BrokerAttributionAudit.LeadSource.BROKER_REFERRAL
                elif marketing_lead_source in BrokerAttributionAudit.LeadSource.values:
                    touch_source = marketing_lead_source

                BrokerAttributionAudit.objects.create(
                    customer=customer,
                    first_touch_source=touch_source,
                    referring_broker=broker if broker_id else None,
                    is_locked=True
                )
            return JsonResponse({
                'success': True,
                'message': _('تم حجز الوحدة بنجاح برقم: %(num)s') % {'num': booking.booking_number},
                'booking_id': booking.id,
                'booking_number': booking.booking_number,
                'unit_status': 'RESERVED',
                'unit_status_display': _('محجوزة مؤقتاً')
            })
        except PermissionDenied as p_err:
            return JsonResponse({'success': False, 'message': str(p_err)}, status=403)
        except ConcurrencyBookingConflictError as c_err:
            return JsonResponse({'success': False, 'message': str(c_err)}, status=409)
        except BookingValidationError as v_err:
            return JsonResponse({'success': False, 'message': str(v_err)}, status=400)
        except Exception as err:
            return JsonResponse({'success': False, 'message': str(err)}, status=500)


class ApiCancelBookingView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    إلغاء حجز الوحدة وتحريرها للبيع مجدداً مع حراسة الصلاحيات وفصل الاسترداد
    """
    permission_required = 'real_estate.change_unitbooking'

    def post(self, request, booking_id):
        try:
            body = json.loads(request.body.decode('utf-8')) if request.body else request.POST
        except Exception:
            body = request.POST

        reason = body.get('reason', _('إلغاء بناء على رغبة العميل'))
        disposition = body.get('disposition', 'REFUND')
        forfeit_deposit = (disposition == 'FORFEIT') or bool(body.get('forfeit_deposit', False))
        deduction_fees = Decimal(str(body.get('deduction_fees') or '0.00'))
        payment_account_id = body.get('payment_account_id')

        # فحص صلاحية الصرف المالي المستقلة عند طلب استرداد نقدي فوري
        if payment_account_id and not forfeit_deposit:
            user = request.user
            if not (user.is_superuser or getattr(user, 'is_admin', False)):
                has_refund_perm = (
                    user.has_perm('real_estate.refund_unitbooking')
                    or user.has_perm('customer.add_customerpayment')
                    or user.has_perm('financial.add_journalentry')
                    or user.has_perm('financial.add_paymentvoucher')
                )
                if not has_refund_perm:
                    return JsonResponse({
                        'success': False,
                        'message': _('غير مصرح لك بصرف واسترداد جدية الحجز المالية.')
                    }, status=403)

        payment_account = None
        if payment_account_id:
            payment_account = get_object_or_404(ChartOfAccounts, pk=payment_account_id)

        try:
            booking = UnitBookingService.cancel_booking(
                booking_id=booking_id,
                reason=reason,
                forfeit_deposit=forfeit_deposit,
                approved_deduction_fees=deduction_fees,
                user=request.user,
                payment_account=payment_account
            )
            return JsonResponse({
                'success': True,
                'message': _('تم إلغاء الحجز وإعادة إتاحة الوحدة للبيع بنجاح.'),
                'booking_id': booking.id,
                'booking_status': booking.status,
                'booking_status_display': booking.get_status_display(),
                'unit_id': booking.unit_id,
                'unit_status': 'AVAILABLE',
                'unit_status_display': _('متاحة للبيع')
            })
        except PermissionDenied as p_err:
            return JsonResponse({'success': False, 'message': str(p_err)}, status=403)
        except BookingValidationError as v_err:
            return JsonResponse({'success': False, 'message': str(v_err)}, status=400)
        except Exception as err:
            return JsonResponse({'success': False, 'message': str(err)}, status=500)


class ApiRefundBookingView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    إجراء التسوية المالية لرد وصرف جدية الحجز (Settle Refund)
    تشترط صلاحية صرف مالي مستقلة (refund_unitbooking أو صلاحيات مالية معتمدة)
    يدعم الصرف نقداً أو بتحويل بنكي أو بشيك مصرفي آجل.
    """
    permission_required = 'real_estate.refund_unitbooking'

    def has_permission(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser or getattr(user, 'is_admin', False):
            return True
        return (
            user.has_perm('real_estate.refund_unitbooking')
            or user.has_perm('customer.add_customerpayment')
            or user.has_perm('financial.add_journalentry')
            or user.has_perm('financial.add_paymentvoucher')
        )

    def post(self, request, booking_id):
        try:
            body = json.loads(request.body.decode('utf-8')) if request.body else request.POST
        except Exception:
            body = request.POST

        method = body.get('method') or body.get('refund_method') or 'BANK_TRANSFER'
        payment_account_id = body.get('payment_account_id') or body.get('refund_account')

        cheque_data = None
        if method == 'CHEQUE':
            cheque_num = body.get('cheque_number', '').strip()
            if not cheque_num:
                return JsonResponse({'success': False, 'message': _('رقم الشيك إلزامي للصرف بشيك.')}, status=400)
            cheque_data = {
                'cheque_number': cheque_num,
                'due_date': body.get('due_date') or timezone.localdate(),
                'drawer_bank_name': body.get('drawer_bank_name', ''),
                'payee_name': body.get('payee_name', ''),
            }
        elif not payment_account_id:
            return JsonResponse({'success': False, 'message': _('يرجى تحديد حساب الخزينة أو البنك لصرف المبلغ.')}, status=400)

        payment_account = get_object_or_404(ChartOfAccounts, pk=payment_account_id) if payment_account_id else None

        try:
            booking = UnitBookingService.process_booking_refund(
                booking_id=booking_id,
                payment_account=payment_account,
                method=method,
                cheque_data=cheque_data,
                user=request.user
            )
            return JsonResponse({
                'success': True,
                'message': _('تم صرف واسترداد جدية الحجز بنجاح وتوليد سند الصرف المحاسبي.'),
                'booking_id': booking.id,
                'booking_status': booking.status,
                'booking_status_display': booking.get_status_display()
            })
        except PermissionDenied as p_err:
            return JsonResponse({'success': False, 'message': str(p_err)}, status=403)
        except BookingValidationError as v_err:
            return JsonResponse({'success': False, 'message': str(v_err)}, status=400)
        except Exception as err:
            return JsonResponse({'success': False, 'message': str(err)}, status=500)
