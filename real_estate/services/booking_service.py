# -*- coding: utf-8 -*-
"""
UnitBookingService - محرك حجز الوحدات وإدارة التزامن المتفائل والتحويل لتعاقدات
مسؤول عن:
1. الحجز الذري للوحدة ومنع التكرار والحجز المزدوج عبر كافة محركات قواعد البيانات.
2. تحويل الحجز إلى عقد بيع نهائي ونقل دفعة جدية الحجز للدفعة المقدمة.
3. إلغاء الحجز وإعادة إتاحة الوحدة في دورة إعادة البيع (Resale Lifecycle).
"""
import uuid
import datetime
import logging
from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from real_estate.models.unit import PropertyUnit
from real_estate.models.booking import UnitBooking
from real_estate.models.contract import PropertyContract

logger = logging.getLogger(__name__)


class ConcurrencyBookingConflictError(Exception):
    """خطأ تعارض التزامن عند محاولة حجز وحدة غير متاحة أو محجوزة بالتزامن"""
    pass


class BookingValidationError(ValidationError):
    """خطأ تحقق من صحة بيانات الحجز ودورة حياته"""
    pass


class UnitBookingService:
    """
    محرك حوكمة وحجز الوحدات العقارية
    """

    @classmethod
    def create_booking(
        cls,
        unit_id: int,
        customer,
        holding_deposit: Decimal,
        expiry_date: datetime.date,
        user,
        booking_date: datetime.date = None,
        notes: str = None,
        booking_number: str = None,
        currency=None,
        exchange_rate: Decimal = None,
        payment_account=None,
    ) -> UnitBooking:
        """
        حجز وحدة عقارية بحماية تزامنية ذرية مستقلة عن نوع قاعدة البيانات
        مع إثبات تحصيل جدية الحجز محاسبياً وإصدار إيصال السداد في معاملة ذرية واحدة.
        (Cross-Database Concurrency Guard & Atomic Booking Collection):
        1. قفل صف الوحدة عبر select_for_update داخل معاملة ذرية.
        2. تنفيذ استعلام تحديث شرطي مباشر يضمن تعديل الصف فقط إذا كان AVAILABLE.
        3. تسجيل الحجز وتحديث الحجز الحالي وإصدار التزامن OCC (status_version).
        4. ترحيل قيد إثبات تحصيل جدية الحجز محاسبياً بحساب 21101 عند وجود مبلغ مسدد.
        """
        if holding_deposit < Decimal('0.00'):
            raise BookingValidationError(_("مبلغ جدية الحجز لا يمكن أن يكون سالباً."))

        if not expiry_date:
            raise BookingValidationError(_("يجب تحديد تاريخ انتهاء مهلة الحجز."))

        if user and hasattr(user, 'has_perm') and not (user.is_superuser or getattr(user, 'is_admin', False)):
            if not user.has_perm('real_estate.add_unitbooking'):
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied(_("غير مصرح لك بإنشاء حجز للوحدة العقارية (real_estate.add_unitbooking)."))

        b_date = booking_date or timezone.localdate()
        if expiry_date < b_date:
            raise BookingValidationError(_("تاريخ انتهاء الحجز لا يمكن أن يكون سابقاً لتاريخ الحجز."))

        with transaction.atomic():
            # 1. قفل صف الوحدة لمنع التعديل المتزامن
            try:
                locked_unit = PropertyUnit.objects.select_for_update().get(pk=unit_id)
            except PropertyUnit.DoesNotExist:
                raise BookingValidationError(_("الوحدة العقارية المطلوبة غير موجودة."))

            if locked_unit.status != PropertyUnit.UnitStatus.AVAILABLE:
                raise ConcurrencyBookingConflictError(
                    _("الوحدة رقم %(code)s غير متاحة حالياً (الحالة الحالية: %(status)s).") % {
                        'code': locked_unit.unit_code,
                        'status': locked_unit.get_status_display()
                    }
                )

            # 2. القفل الشرطي الذري (Database-Agnostic Atomic State Machine Lock)
            # يعمل بسلامة 100% عبر PostgreSQL, MySQL, MariaDB, SQLite
            rows_updated = PropertyUnit.objects.filter(
                pk=unit_id,
                status=PropertyUnit.UnitStatus.AVAILABLE
            ).update(
                status=PropertyUnit.UnitStatus.RESERVED,
                status_version=models.F('status_version') + 1
            )

            if rows_updated == 0:
                raise ConcurrencyBookingConflictError(
                    _("تعارض تزامن: تم حجز الوحدة %(code)s من قبل مستخدم آخر في نفس اللحظة.") % {
                        'code': locked_unit.unit_code
                    }
                )

            # 3. توليد رقم الحجز الفريد
            if not booking_number:
                b_num = f"BK-{locked_unit.unit_code}-{timezone.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
            else:
                b_num = booking_number

            # تحديد عملة الحجز وسعر الصرف
            booking_curr = currency or getattr(locked_unit.project, 'currency', None)
            if not booking_curr:
                from financial.models import Currency
                booking_curr = Currency.objects.filter(is_functional=True).first()

            # 4. إنشاء سجل الحجز
            booking = UnitBooking.objects.create(
                booking_number=b_num,
                unit=locked_unit,
                customer=customer,
                booking_date=b_date,
                expiry_date=expiry_date,
                holding_deposit=holding_deposit,
                currency=booking_curr,
                exchange_rate=exchange_rate or Decimal('1.000000'),
                status=UnitBooking.BookingStatus.ACTIVE,
                notes=notes or "",
                created_by=user
            )

            # 5. إثبات تحصيل جدية الحجز محاسبياً وإصدار إيصال السداد في دفتر الأستاذ العام
            if holding_deposit > Decimal('0.00'):
                deposit_acc = payment_account
                if not deposit_acc:
                    if locked_unit.project and locked_unit.project.escrow_account:
                        deposit_acc = locked_unit.project.escrow_account
                    else:
                        from real_estate.services.accounting_service import RealEstateAccountingService
                        from financial.services.role_registry import AccountRoleNames
                        deposit_acc = RealEstateAccountingService.get_or_resolve_account(
                            AccountRoleNames.CASH_DRAWER.value,
                            fallback_code="11101"
                        )

                from real_estate.services.accounting_service import RealEstateAccountingService
                je = RealEstateAccountingService.post_booking_holding_fee(
                    booking=booking,
                    payment_account=deposit_acc,
                    user=user,
                    reference=booking.booking_number
                )
                booking.journal_entry = je
                booking.is_deposit_collected = True
                booking.save(update_fields=['journal_entry', 'is_deposit_collected'])

            # 6. ربط الحجز النشط بالوحدة
            locked_unit.current_booking = booking
            locked_unit.refresh_from_db(fields=['status_version'])
            locked_unit.save(update_fields=['current_booking'])

            logger.info(
                f"✅ تم حجز الوحدة {locked_unit.unit_code} بنجاح برقم {booking.booking_number} "
                f"للعميل {customer.name} حتى {expiry_date}"
            )
            return booking

    @classmethod
    def convert_booking_to_contract(
        cls,
        booking_id: int,
        user,
        final_contract_price: Decimal = None,
        down_payment: Decimal = None,
        contract_date: datetime.date = None,
        delivery_date: datetime.date = None,
        currency=None,
        exchange_rate: Decimal = None,
        contract_number: str = None,
        payment_account=None,
    ) -> PropertyContract:
        """
        تحويل استمارة الحجز إلى تعاقد بيع نهائي (SPA) بقفل ثنائي ذري
        """
        with transaction.atomic():
            try:
                locked_booking = UnitBooking.objects.select_for_update().get(pk=booking_id)
            except UnitBooking.DoesNotExist:
                raise BookingValidationError(_("استمارة الحجز المطلوبة غير موجودة."))

            locked_unit = PropertyUnit.objects.select_for_update().get(pk=locked_booking.unit_id)

            if locked_booking.status != UnitBooking.BookingStatus.ACTIVE:
                raise BookingValidationError(
                    _("لا يمكن تحويل حجز غير نشط إلى عقد (الحالة الحالية: %(status)s).") % {
                        'status': locked_booking.get_status_display()
                    }
                )

            if locked_unit.status != PropertyUnit.UnitStatus.RESERVED or locked_unit.current_booking_id != locked_booking.id:
                raise BookingValidationError(_("حالة الوحدة لا تتوافق مع بيانات الحجز الحالي."))

            # التحقق الصارم من إثبات تحصيل جدية الحجز محاسبياً قبل اعتمادها كمقدم تعاقد
            if locked_booking.holding_deposit > Decimal('0.00') and not locked_booking.is_deposit_collected:
                from financial.models.journal_entry import JournalEntry
                has_je = JournalEntry.objects.filter(
                    source_module='real_estate',
                    source_model='UnitBooking',
                    source_id=locked_booking.id
                ).exists()
                if not has_je:
                    raise BookingValidationError(
                        _("لا يمكن تحويل الحجز لعقد: لم يتم إثبات تحصيل جدية الحجز محاسبياً وإصدار إيصال السداد.")
                    )

            c_date = contract_date or timezone.localdate()
            d_date = delivery_date or (c_date + datetime.timedelta(days=730))
            price = final_contract_price or locked_unit.total_price

            curr = currency or getattr(locked_unit.project, 'currency', None)
            if not curr:
                from financial.models import Currency
                curr = Currency.objects.filter(is_functional=True).first()

            cnt_rate = Decimal(str(exchange_rate or getattr(locked_unit.project, 'exchange_rate', '1.000000') or '1.000000'))

            # احتساب معادل جدية الحجز المحصلة بعملة العقد التعاقدية
            booking_curr = getattr(locked_booking, 'currency', None)
            booking_curr_code = getattr(booking_curr, 'code', 'EGP') if booking_curr else 'EGP'
            booking_rate = Decimal(str(getattr(locked_booking, 'exchange_rate', '1.000000') or '1.000000'))
            contract_curr_code = getattr(curr, 'code', 'EGP') if curr else 'EGP'

            # حساب القيمة الوظيفية لجدية الحجز المسددة
            if booking_curr_code != 'EGP' and booking_rate > Decimal('0.00'):
                func_holding = (locked_booking.holding_deposit * booking_rate).quantize(Decimal('0.01'))
            else:
                func_holding = locked_booking.holding_deposit

            # تحويل القيمة الوظيفية إلى عملة العقد المقومة به
            if contract_curr_code == booking_curr_code:
                contract_holding = locked_booking.holding_deposit
            elif contract_curr_code != 'EGP' and cnt_rate > Decimal('0.00'):
                contract_holding = (func_holding / cnt_rate).quantize(Decimal('0.01'))
            else:
                contract_holding = func_holding

            # احتساب مقدم العقد والتحقق الصارم من سداد أي فرق إضافي ذرياً
            if down_payment is not None:
                requested_dp = Decimal(str(down_payment))
            else:
                requested_dp = contract_holding

            extra_down = requested_dp - contract_holding
            if extra_down > Decimal('0.00'):
                deposit_acc = payment_account
                if not deposit_acc and locked_unit.project and locked_unit.project.escrow_account:
                    deposit_acc = locked_unit.project.escrow_account

                if not deposit_acc:
                    raise BookingValidationError(
                        _("مقدم التعاقد المحدد (%(dp)s) يتجاوز جدية الحجز المحصلة (%(holding)s). "
                          "يجب تحديد حساب الخزينة أو البنك لتحصيل فرق المقدم ذرياً، أو الاقتصار على جدية الحجز المحصلة.") % {
                            'dp': requested_dp,
                            'holding': contract_holding
                        }
                    )
                dp = requested_dp
                additional_to_collect = extra_down
                payment_account = deposit_acc
            else:
                dp = requested_dp
                additional_to_collect = Decimal('0.00')

            # 1. تحديث حالة الحجز إلى محول لعقد
            locked_booking.status = UnitBooking.BookingStatus.CONVERTED_TO_CONTRACT
            locked_booking.save(update_fields=['status', 'updated_at'])

            # 2. فك ارتباط الحجز المؤقت وتحديث حالة الوحدة لـ CONTRACTED
            locked_unit.status = PropertyUnit.UnitStatus.CONTRACTED
            locked_unit.status_version += 1
            locked_unit.current_booking = None
            locked_unit.save(update_fields=['status', 'status_version', 'current_booking'])

            # 3. إنشاء العقد الرسمي
            cnt_num = contract_number or f"CTR-{locked_unit.unit_code}-{timezone.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
            contract = PropertyContract.objects.create(
                contract_number=cnt_num,
                project=locked_unit.project,
                unit=locked_unit,
                customer=locked_booking.customer,
                status=PropertyContract.ContractStatus.ACTIVE,
                contract_date=c_date,
                delivery_date=d_date,
                final_contract_price=price,
                down_payment=dp,
                currency=curr,
                exchange_rate=exchange_rate or Decimal('1.000000'),
                created_by=user
            )

            # 4. إعادة تصنيف مقدم الحجز محاسبياً ونقله إلى التزام العقد وتحصيل أي فرق إضافي ذرياً (Event 1b)
            if locked_booking.holding_deposit > Decimal('0.00') or additional_to_collect > Decimal('0.00'):
                from real_estate.services.accounting_service import RealEstateAccountingService
                RealEstateAccountingService.post_booking_conversion(
                    booking=locked_booking,
                    contract=contract,
                    user=user,
                    additional_down_payment=additional_to_collect,
                    payment_account=payment_account,
                    reference=contract.contract_number
                )

            logger.info(
                f"✅ تم تحويل الحجز {locked_booking.booking_number} إلى العقد {contract.contract_number} "
                f"للوحدة {locked_unit.unit_code}"
            )
            return contract

    @classmethod
    def cancel_booking(
        cls,
        booking_id: int,
        reason: str,
        forfeit_deposit: bool = False,
        user=None,
        payment_account=None,
    ) -> UnitBooking:
        """
        إلغاء الحجز وإعادة إتاحة الوحدة للبيع مجدداً في دورة إعادة البيع (Resale Lifecycle)
        مع حراسة الصلاحيات وفصل طلب الاسترداد عن اكتماله الفعلي.
        """
        if not reason:
            raise BookingValidationError(_("يجب تحديد سبب إلغاء الحجز."))

        if user and hasattr(user, 'has_perm') and not (user.is_superuser or getattr(user, 'is_admin', False)):
            if not (user.has_perm('real_estate.change_unitbooking') or user.has_perm('real_estate.delete_unitbooking')):
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied(_("غير مصرح لك بإلغاء حجز الوحدة العقارية (real_estate.change_unitbooking)."))

        with transaction.atomic():
            try:
                locked_booking = UnitBooking.objects.select_for_update().get(pk=booking_id)
            except UnitBooking.DoesNotExist:
                raise BookingValidationError(_("استمارة الحجز المطلوبة غير موجودة."))

            locked_unit = PropertyUnit.objects.select_for_update().get(pk=locked_booking.unit_id)

            has_deposit = (locked_booking.holding_deposit > Decimal('0.00') and locked_booking.is_deposit_collected)

            allowed_cancel_statuses = [UnitBooking.BookingStatus.ACTIVE]
            if has_deposit:
                allowed_cancel_statuses.append(UnitBooking.BookingStatus.EXPIRED_RELEASED)

            if locked_booking.status not in allowed_cancel_statuses:
                raise BookingValidationError(
                    _("لا يمكن إلغاء حجز غير نشط أو غير مؤهل للمراجعة (الحالة الحالية: %(status)s).") % {
                        'status': locked_booking.get_status_display()
                    }
                )

            # إذا طُلب إلغاء مع استرداد فوري لجدية الحجز (Immediate Refund Disbursement)
            if payment_account and not forfeit_deposit and has_deposit:
                if user and hasattr(user, 'has_perm') and not (user.is_superuser or getattr(user, 'is_admin', False)):
                    has_refund_perm = (
                        user.has_perm('real_estate.refund_unitbooking')
                        or user.has_perm('customer.add_customerpayment')
                        or user.has_perm('financial.add_journalentry')
                        or user.has_perm('financial.add_paymentvoucher')
                    )
                    if not has_refund_perm:
                        from django.core.exceptions import PermissionDenied
                        raise PermissionDenied(_("غير مصرح لك بصرف واسترداد جدية الحجز المالية."))

            from real_estate.services.accounting_service import RealEstateAccountingService

            if forfeit_deposit:
                if has_deposit:
                    RealEstateAccountingService.post_booking_forfeiture(
                        booking=locked_booking,
                        user=user
                    )
                target_status = UnitBooking.BookingStatus.CANCELLED_FORFEITED
            else:
                if has_deposit:
                    if payment_account:
                        # تسوية مالية فورية
                        RealEstateAccountingService.post_booking_refund(
                            booking=locked_booking,
                            payment_account=payment_account,
                            user=user
                        )
                        target_status = UnitBooking.BookingStatus.CANCELLED_REFUNDED
                    else:
                        # فصل طلب الاسترداد عن اكتماله: الحجز يصبح بانتظار الرد المالي
                        target_status = UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND
                else:
                    target_status = UnitBooking.BookingStatus.CANCELLED_REFUNDED

            # 1. تحديث حالة الحجز
            locked_booking.status = target_status
            locked_booking.notes = f"{locked_booking.notes}\n[سبب الإلغاء: {reason}]".strip()
            locked_booking.save(update_fields=['status', 'notes', 'updated_at'])

            # 2. تحرير الوحدة فقط إذا كانت لا تزال محجوزة لهذا الحجز تحديداً
            if locked_unit.current_booking_id == locked_booking.id:
                locked_unit.status = PropertyUnit.UnitStatus.AVAILABLE
                locked_unit.current_booking = None
                locked_unit.status_version += 1
                locked_unit.save(update_fields=['status', 'current_booking', 'status_version'])

            action_type = "مصادرة" if forfeit_deposit else ("استرداد فوري" if (has_deposit and payment_account) else "طلب استرداد معلق")
            logger.info(
                f"↩️ تم إلغاء الحجز {locked_booking.booking_number} مع {action_type} جدية الحجز "
                f"وإعادة الوحدة {locked_unit.unit_code} للبيع مجدداً."
            )
            return locked_booking

    @classmethod
    def process_booking_refund(
        cls,
        booking_id: int,
        payment_account,
        user=None,
        reference: str = ""
    ) -> UnitBooking:
        """
        التسوية المالية لصرف واسترداد جدية الحجز (Settle Booking Deposit Refund)
        يرحل قيد رد الأمانات (payment_voucher) ويحول الحالة إلى CANCELLED_REFUNDED
        """
        if not payment_account:
            raise BookingValidationError(_("يجب تحديد حساب الخزينة أو البنك لصرف المبلغ المسترد."))

        if user and hasattr(user, 'has_perm') and not (user.is_superuser or getattr(user, 'is_admin', False)):
            has_refund_perm = (
                user.has_perm('real_estate.refund_unitbooking')
                or user.has_perm('customer.add_customerpayment')
                or user.has_perm('financial.add_journalentry')
                or user.has_perm('financial.add_paymentvoucher')
            )
            if not has_refund_perm:
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied(_("غير مصرح لك بإجراء التسوية المالية لرد وصرف جدية الحجز."))

        with transaction.atomic():
            try:
                locked_booking = UnitBooking.objects.select_for_update().get(pk=booking_id)
            except UnitBooking.DoesNotExist:
                raise BookingValidationError(_("استمارة الحجز المطلوبة غير موجودة."))

            allowed_refund_statuses = [
                UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND,
                UnitBooking.BookingStatus.EXPIRED_RELEASED
            ]
            if locked_booking.status not in allowed_refund_statuses:
                raise BookingValidationError(
                    _("لا يمكن صرف استرداد لحجز حالته ليست بانتظار رد جدية الحجز أو منتهياً معلقاً (الحالة الحالية: %(status)s).") % {
                        'status': locked_booking.get_status_display()
                    }
                )

            if locked_booking.holding_deposit <= Decimal('0.00') or not locked_booking.is_deposit_collected:
                raise BookingValidationError(_("لا يوجد مبلغ جدية حجز محصل مسجل على هذا الحجز لصرفه."))

            from real_estate.services.accounting_service import RealEstateAccountingService
            RealEstateAccountingService.post_booking_refund(
                booking=locked_booking,
                payment_account=payment_account,
                user=user,
                reference=reference
            )

            locked_booking.status = UnitBooking.BookingStatus.CANCELLED_REFUNDED
            locked_booking.save(update_fields=['status', 'updated_at'])

            logger.info(
                f"💸 تم صرف واسترداد جدية حجز {locked_booking.booking_number} بنجاح بمبلغ {locked_booking.holding_deposit}"
            )
            return locked_booking
