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
        finishing_package=None,
        finishing_meter_rate: Decimal = None,
        total_finishing_amount: Decimal = None,
        utilities_deposit_amount: Decimal = None,
        parking_slot_code: str = None,
        parking_slot_price: Decimal = None,
        storage_locker_code: str = None,
        storage_locker_price: Decimal = None,
        partner=None,
        company_share_percentage: Decimal = None,
        partner_share_percentage: Decimal = None,
        sales_channel: str = None,
        marketing_lead_source: str = None,
        collection_method: str = 'CASH',
        cheque_number: str = None,
        due_date=None,
        drawer_bank_name: str = None,
        call_specialist=None,
        visit_specialist=None,
        site_specialist=None,
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
            # 0. قفل المشروع إن وُجد للحفاظ على الترتيب الهرمي للأقفال
            if unit_id:
                target_unit_peek = PropertyUnit.objects.filter(pk=unit_id).values_list('project_id', flat=True).first()
                if target_unit_peek:
                    from real_estate.models.project import RealEstateProject
                    RealEstateProject.objects.select_for_update().filter(pk=target_unit_peek).first()

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

            # فحص تصادم بايكات الجراج والمخازن السريعة داخل نطاق المشروع
            contract_ownership_statuses = [
                PropertyContract.ContractStatus.ACTIVE,
                PropertyContract.ContractStatus.COMPLETED,
                PropertyContract.ContractStatus.UNDER_APPROVAL,
                PropertyContract.ContractStatus.SUSPENDED,
            ]
            if parking_slot_code and locked_unit.project_id:
                clean_slot = str(parking_slot_code).strip()
                if clean_slot:
                    slot_in_booking = UnitBooking.objects.filter(
                        unit__project_id=locked_unit.project_id,
                        parking_slot_code=clean_slot,
                        status=UnitBooking.BookingStatus.ACTIVE
                    ).exists()
                    slot_in_contract = PropertyContract.objects.filter(
                        project_id=locked_unit.project_id,
                        parking_slot_code=clean_slot,
                        status__in=contract_ownership_statuses
                    ).exists()
                    if slot_in_booking or slot_in_contract:
                        raise BookingValidationError(
                            _("بايكة الجراج '%(slot)s' محجوزة أو متعاقد عليها بالفعل في هذا المشروع.") % {'slot': clean_slot}
                        )

            if storage_locker_code and locked_unit.project_id:
                clean_locker = str(storage_locker_code).strip()
                if clean_locker:
                    locker_in_booking = UnitBooking.objects.filter(
                        unit__project_id=locked_unit.project_id,
                        storage_locker_code=clean_locker,
                        status=UnitBooking.BookingStatus.ACTIVE
                    ).exists()
                    locker_in_contract = PropertyContract.objects.filter(
                        project_id=locked_unit.project_id,
                        storage_locker_code=clean_locker,
                        status__in=contract_ownership_statuses
                    ).exists()
                    if locker_in_booking or locker_in_contract:
                        raise BookingValidationError(
                            _("المخزن السريع '%(locker)s' محجوز أو متعاقد عليه بالفعل في هذا المشروع.") % {'locker': clean_locker}
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
                finishing_package=finishing_package,
                finishing_meter_rate=finishing_meter_rate or Decimal('0.00'),
                total_finishing_amount=total_finishing_amount or Decimal('0.00'),
                utilities_deposit_amount=utilities_deposit_amount or Decimal('0.00'),
                parking_slot_code=str(parking_slot_code).strip() if parking_slot_code else '',
                parking_slot_price=parking_slot_price or Decimal('0.00'),
                storage_locker_code=str(storage_locker_code).strip() if storage_locker_code else '',
                storage_locker_price=storage_locker_price or Decimal('0.00'),
                partner=partner,
                company_share_percentage=company_share_percentage if company_share_percentage is not None else Decimal('100.00'),
                partner_share_percentage=partner_share_percentage if partner_share_percentage is not None else Decimal('0.00'),
                sales_channel=sales_channel or '',
                marketing_lead_source=marketing_lead_source or '',
                call_specialist=call_specialist,
                visit_specialist=visit_specialist,
                site_specialist=site_specialist,
                created_by=user
            )

            # 5. إثبات تحصيل جدية الحجز محاسبياً وإصدار إيصال السداد أو الشيك في دفتر الأستاذ العام
            if holding_deposit > Decimal('0.00'):
                if collection_method == 'CHEQUE':
                    if not cheque_number or not due_date or not drawer_bank_name:
                        raise BookingValidationError(_("بيانات الشيك (رقم الشيك، تاريخ الاستحقاق، واسم البنك) إلزامية للتحصيل بشيك."))

                    from cheques.models.cheque import Cheque, ChequeType, ChequeStatus, ChequePurpose
                    from datetime import datetime as dt
                    c_due = dt.strptime(due_date, '%Y-%m-%d').date() if isinstance(due_date, str) else due_date

                    chq_curr = currency or getattr(locked_unit.project, 'currency', None)
                    if not chq_curr:
                        from financial.models.currency import Currency
                        chq_curr = Currency.objects.filter(is_functional=True).first() or Currency.objects.filter(code='EGP').first()

                    chq = Cheque.objects.create(
                        cheque_type=ChequeType.RECEIVABLE,
                        purpose=ChequePurpose.ADVANCE_PAYMENT,
                        status=ChequeStatus.IN_PORTFOLIO,
                        customer=customer,
                        amount=holding_deposit,
                        currency=chq_curr,
                        original_exchange_rate=exchange_rate or Decimal('1.000000'),
                        issue_date=b_date,
                        due_date=c_due,
                        cheque_number=str(cheque_number).strip(),
                        drawer_bank_name=str(drawer_bank_name).strip(),
                        drawer_name=customer.name,
                        payee_name=getattr(locked_unit.project, 'name', 'MWHEBA Real Estate'),
                        deposit_bank_account=payment_account,
                        portfolio_account=payment_account,
                        notes=f"[BOOKING_ID:{booking.id}] [BOOKING_NUM:{booking.booking_number}] حجز الوحدة {locked_unit.unit_code}",
                        created_by=user,
                    )
                    booking.notes = f"{booking.notes or ''} [CHEQUE_ID:{chq.id}] [CHEQUE_NUM:{chq.cheque_number}]".strip()
                    booking.is_deposit_collected = False
                    booking.save(update_fields=['is_deposit_collected', 'notes'])
                else:
                    deposit_acc = payment_account
                    if not deposit_acc:
                        if locked_unit.project and locked_unit.project.escrow_account:
                            deposit_acc = locked_unit.project.escrow_account
                        else:
                            from real_estate.services.accounting_service import RealEstateAccountingService
                            from financial.services.role_registry import AccountRoleNames
                            deposit_acc = RealEstateAccountingService.get_or_resolve_account(
                                AccountRoleNames.DEFAULT_CASH_DRAWER.value,
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
    def get_effective_collected_deposit(cls, booking: UnitBooking) -> Decimal:
        """
        احتساب صافي المبلغ المحصل فعلياً لجدية الحجز عبر دورة حياة الشيك أو الحسابات
        مع مراعاة التحصيل الجزئي وحالات الارتداد والعكس.
        """
        if not booking or (booking.holding_deposit or Decimal('0.00')) <= Decimal('0.00'):
            return Decimal('0.00')

        from cheques.models.cheque import Cheque, ChequeStatus
        from financial.models.journal_entry import JournalEntry
        import re

        # 1. التحقق من الشيك المرتبط بالحجز إن وجد
        linked_cheque = Cheque.objects.filter(
            notes__contains=f"[BOOKING_ID:{booking.id}]"
        ).first()

        if not linked_cheque and booking.notes and '[CHEQUE_ID:' in booking.notes:
            try:
                chq_match = re.search(r'\[CHEQUE_ID:(\d+)\]', booking.notes)
                if chq_match:
                    linked_cheque = Cheque.objects.filter(id=int(chq_match.group(1))).first()
            except Exception:
                pass

        if linked_cheque:
            chq_amt = linked_cheque.collected_amount or Decimal('0.00')
            uncollected_statuses = [
                ChequeStatus.CANCELLED,
                getattr(ChequeStatus, 'RETURNED_TO_DRAWER', 'RETURNED_TO_DRAWER'),
            ]
            # إذا أُلغي الشيك أو أعيد للساحب أو رصيده المحصل صفر بالكامل (مثل ارتداد كامل دون أي تحصيل)
            if linked_cheque.status in uncollected_statuses or chq_amt <= Decimal('0.00'):
                if booking.is_deposit_collected:
                    booking.is_deposit_collected = False
                    booking.save(update_fields=['is_deposit_collected'])
                return Decimal('0.00')

            if linked_cheque.customer_id == booking.customer_id and chq_amt > Decimal('0.00'):
                collect_logs = linked_cheque.action_logs.filter(
                    action='COLLECT',
                    journal_entry__isnull=False
                ).order_by('-id')

                active_je = None
                for log in collect_logs:
                    je = log.journal_entry
                    is_je_rev = (
                        getattr(je, 'reversed_by_entry_id', None) is not None or
                        getattr(je, 'is_reversal', False) or
                        je.reversal_entries.exists() or
                        getattr(je, 'status', None) == 'cancelled'
                    )
                    if not is_je_rev:
                        active_je = je
                        break

                if active_je or chq_amt > Decimal('0.00'):
                    eff_amt = min(chq_amt, booking.holding_deposit)
                    if not booking.is_deposit_collected:
                        booking.is_deposit_collected = True
                    if active_je and booking.journal_entry_id != active_je.id:
                        booking.journal_entry = active_je
                    booking.save(update_fields=['is_deposit_collected', 'journal_entry'])
                    return eff_amt
                else:
                    if booking.is_deposit_collected:
                        booking.is_deposit_collected = False
                        booking.save(update_fields=['is_deposit_collected'])
                    return Decimal('0.00')

        # 2. في حال عدم وجود شيك: التحقق من قيد الحسابات المباشر للحجز
        direct_je = JournalEntry.objects.filter(
            source_module='real_estate',
            source_model='UnitBooking',
            source_id=booking.id
        ).order_by('-id').first()

        if direct_je:
            is_reversed = (
                getattr(direct_je, 'reversed_by_entry_id', None) is not None or
                getattr(direct_je, 'is_reversal', False) or
                direct_je.reversal_entries.exists() or
                getattr(direct_je, 'status', None) == 'cancelled'
            )
            if is_reversed:
                if booking.is_deposit_collected:
                    booking.is_deposit_collected = False
                    booking.save(update_fields=['is_deposit_collected'])
                return Decimal('0.00')

            if direct_je.status == 'posted':
                if not booking.is_deposit_collected:
                    booking.is_deposit_collected = True
                    if not booking.journal_entry_id:
                        booking.journal_entry = direct_je
                    booking.save(update_fields=['is_deposit_collected', 'journal_entry'])
                return booking.holding_deposit

        # 3. إذا لم يوجد شيك ولا قيد، ولكن الحجز معلم صراحة كـ is_deposit_collected (حالات الاختبار المباشر أو السندات السابقة)
        if booking.is_deposit_collected:
            return booking.holding_deposit

        return Decimal('0.00')

    @classmethod
    def sync_booking_collection_state(cls, booking: UnitBooking) -> bool:
        """
        مزامنة حالة تحصيل جدية الحجز (سواء كانت نقداً أو بنكاً أو شيكاً برسم التحصيل)
        مع التحقق من القيود المحاسبية الصالحة وغير المعكوسة.
        """
        eff = cls.get_effective_collected_deposit(booking)
        return eff > Decimal('0.00')

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
        contract_tax_structure: str = None,
        has_decoupled_finishing: bool = False,
        primary_owner_share: Decimal = None,
        co_owners_data: list = None,
        number_of_installments: int = None,
        installment_frequency: str = None,
        first_installment_date: datetime.date = None,
        broker=None,
        broker_commission_rate: Decimal = None,
        finishing_installments_count: int = None,
        finishing_installment_frequency: int = None,
        ceo_override_token: str = None,
        ceo_override_reason: str = None,
        parking_slot_code: str = None,
        parking_slot_price: Decimal = None,
        storage_locker_code: str = None,
        storage_locker_price: Decimal = None,
        finishing_meter_rate: Decimal = None,
        finishing_total_amount: Decimal = None,
        utilities_deposit_amount: Decimal = None,
        maintenance_deposit_amount: Decimal = None,
        call_specialist=None,
        visit_specialist=None,
        site_specialist=None,
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

            # التحقق الصارم من منظومة الاعتماد المالي والرقابي الثنائي
            if not (locked_booking.is_confirmed_audit or locked_booking.is_legacy_pre_audit or locked_booking.audit_bypassed):
                raise BookingValidationError(
                    _("لا يمكن تحويل الحجز لعقد: الحجز لم يحصل على الاعتماد المالي والرقابي الثنائي، ولم يتم استثناؤه إدارياً.")
                )

            # التحقق الصارم من دورة الاعتماد المالي والرقابي الثنائي والفصل الرقابي الكامل (SoD)
            if not (locked_booking.is_legacy_pre_audit or locked_booking.audit_bypassed):
                if not (locked_booking.is_reviewed_sales and locked_booking.reviewed_by_id and locked_booking.reviewed_at):
                    raise BookingValidationError(
                        _("لا يمكن تحويل الحجز لعقد: دورة مراجعة المبيعات غير مكتملة (تتطلب علامة المراجعة، والمراجع المسؤول، وتاريخ المراجعة).")
                    )
                if not (locked_booking.is_confirmed_audit and locked_booking.confirmed_by_id and locked_booking.confirmed_at):
                    raise BookingValidationError(
                        _("لا يمكن تحويل الحجز لعقد: دورة الاعتماد الرقابي غير مكتملة (تتطلب علامة الاعتماد، والمعتمد المسؤول، وتاريخ الاعتماد).")
                    )
                if locked_booking.created_by_id and locked_booking.reviewed_by_id == locked_booking.created_by_id:
                    raise BookingValidationError(
                        _("قيد الفصل الرقابي (Segregation of Duties): لا يجوز لمنشئ الحجز مراجعة حجزه بنفسه.")
                    )
                if locked_booking.reviewed_by_id == locked_booking.confirmed_by_id:
                    raise BookingValidationError(
                        _("قيد الفصل الرقابي (Segregation of Duties): لا يجوز لنفس المستخدم تسجيل مراجعة المبيعات والاعتماد الرقابي معاً.")
                    )

            if locked_unit.status != PropertyUnit.UnitStatus.RESERVED or locked_unit.current_booking_id != locked_booking.id:
                raise BookingValidationError(_("حالة الوحدة لا تتوافق مع بيانات الحجز الحالي."))

            # التحقق الصارم من إثبات تحصيل جدية الحجز محاسبياً قبل اعتمادها كمقدم تعاقد
            cls.sync_booking_collection_state(locked_booking)

            if locked_booking.holding_deposit > Decimal('0.00') and not locked_booking.is_deposit_collected:
                raise BookingValidationError(
                    _("لا يمكن تحويل الحجز لعقد: لم يتم إثبات تحصيل جدية الحجز محاسبياً وإصدار إيصال السداد.")
                )

            if isinstance(contract_date, str):
                from datetime import datetime as dt
                try:
                    c_date = dt.strptime(contract_date, '%Y-%m-%d').date()
                except Exception:
                    c_date = timezone.localdate()
            else:
                c_date = contract_date or timezone.localdate()

            if isinstance(delivery_date, str):
                from datetime import datetime as dt
                try:
                    d_date = dt.strptime(delivery_date, '%Y-%m-%d').date()
                except Exception:
                    d_date = c_date + datetime.timedelta(days=730)
            else:
                d_date = delivery_date or (c_date + datetime.timedelta(days=730))

            if isinstance(first_installment_date, str):
                from datetime import datetime as dt
                try:
                    first_installment_date = dt.strptime(first_installment_date, '%Y-%m-%d').date() if first_installment_date else None
                except Exception:
                    first_installment_date = None

            price = final_contract_price or locked_unit.total_price

            curr = currency or getattr(locked_unit.project, 'currency', None)
            if not curr:
                from financial.models import Currency
                curr = Currency.objects.filter(is_functional=True).first()

            cnt_rate = Decimal(str(exchange_rate or getattr(locked_unit.project, 'exchange_rate', '1.000000') or '1.000000'))

            from financial.models import Currency
            func_curr = Currency.objects.filter(is_functional=True).first()
            func_curr_code = getattr(func_curr, 'code', 'EGP') if func_curr else 'EGP'

            # احتساب معادل جدية الحجز المحصلة بعملة العقد التعاقدية
            eff_deposit = cls.get_effective_collected_deposit(locked_booking)
            booking_curr = getattr(locked_booking, 'currency', None)
            booking_curr_code = getattr(booking_curr, 'code', func_curr_code) if booking_curr else func_curr_code
            booking_rate = Decimal(str(getattr(locked_booking, 'exchange_rate', '1.000000') or '1.000000'))
            contract_curr_code = getattr(curr, 'code', func_curr_code) if curr else func_curr_code

            # حساب القيمة الوظيفية لجدية الحجز المسددة
            if booking_curr_code != func_curr_code and booking_rate > Decimal('0.00'):
                func_holding = (eff_deposit * booking_rate).quantize(Decimal('0.01'))
            else:
                func_holding = eff_deposit

            # تحويل القيمة الوظيفية إلى عملة العقد المقومة به
            if contract_curr_code == booking_curr_code:
                contract_holding = eff_deposit
            elif contract_curr_code != func_curr_code and cnt_rate > Decimal('0.00'):
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
            is_decoupled = bool(
                has_decoupled_finishing
                or (contract_tax_structure == PropertyContract.ContractTaxStructure.SPLIT_SPA_FINISHING_ANNEX)
            )

            # التحقق الصارم من تكامل ونطاق نسب الملكية
            p_share = Decimal(str(primary_owner_share)).quantize(Decimal('0.01')) if primary_owner_share is not None else Decimal('100.00')
            if p_share < Decimal('0.00') or p_share > Decimal('100.00'):
                raise BookingValidationError(
                    _("نسبة ملكية العميل الرئيسي يجب أن تكون بين 0.00%% و 100.00%% (القيمة المدخلة: %(p)s%%).") % {
                        'p': p_share
                    }
                )

            for item in (co_owners_data or []):
                c_share = Decimal(str(item.get('share_percentage', '0'))).quantize(Decimal('0.01'))
                if c_share <= Decimal('0.00') or c_share > Decimal('100.00'):
                    raise BookingValidationError(
                        _("نسبة ملكية الشريك يجب أن تكون أكبر من 0%% وحتى 100.00%% (القيمة المدخلة: %(c)s%%).") % {
                            'c': c_share
                        }
                    )

            co_share_sum = sum(
                Decimal(str(item.get('share_percentage', '0'))).quantize(Decimal('0.01'))
                for item in (co_owners_data or [])
            )
            if p_share + co_share_sum != Decimal('100.00'):
                raise BookingValidationError(
                    _("إجمالي نسب الملكية في العقد يجب أن يساوي 100.00%% بالضبط (المالك الرئيسي: %(p)s%% + الشركاء: %(c)s%% = %(t)s%%).") % {
                        'p': p_share,
                        'c': co_share_sum,
                        't': p_share + co_share_sum
                    }
                )

            final_parking_code = str(parking_slot_code).strip() if parking_slot_code is not None else locked_booking.parking_slot_code
            final_parking_price = parking_slot_price if parking_slot_price is not None else locked_booking.parking_slot_price
            final_storage_code = str(storage_locker_code).strip() if storage_locker_code is not None else locked_booking.storage_locker_code
            final_storage_price = storage_locker_price if storage_locker_price is not None else locked_booking.storage_locker_price
            final_finishing_rate = finishing_meter_rate if finishing_meter_rate is not None else locked_booking.finishing_meter_rate
            final_finishing_amount = finishing_total_amount if finishing_total_amount is not None else locked_booking.total_finishing_amount
            final_utilities_amount = utilities_deposit_amount if utilities_deposit_amount is not None else locked_booking.utilities_deposit_amount
            final_maintenance_amount = maintenance_deposit_amount if maintenance_deposit_amount is not None else getattr(locked_booking, 'maintenance_deposit_amount', Decimal('0.00'))
            final_call_specialist = call_specialist or locked_booking.call_specialist
            final_visit_specialist = visit_specialist or locked_booking.visit_specialist
            final_site_specialist = site_specialist or locked_booking.site_specialist

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
                contract_tax_structure=contract_tax_structure or PropertyContract.ContractTaxStructure.UNIFIED_SPA,
                primary_owner_share=p_share,
                has_decoupled_finishing=is_decoupled,
                finishing_meter_rate=final_finishing_rate,
                finishing_total_amount=final_finishing_amount,
                utilities_deposit_amount=final_utilities_amount,
                maintenance_deposit_amount=final_maintenance_amount,
                parking_slot_code=final_parking_code,
                parking_slot_price=final_parking_price,
                storage_locker_code=final_storage_code,
                storage_locker_price=final_storage_price,
                call_specialist=final_call_specialist,
                visit_specialist=final_visit_specialist,
                site_specialist=final_site_specialist,
                created_by=user
            )

            # مزامنة المشترين المتضامنين ونسب الملكية إن وُجدت
            if co_owners_data:
                from real_estate.services.contract_service import PropertyContractService
                PropertyContractService.sync_contract_ownership(
                    contract_id=contract.id,
                    co_owners_data=co_owners_data,
                    primary_owner_share=p_share,
                    user=user
                )

            contract.refresh_from_db()
            contract.validate_ownership_integrity()

            # 4. إعادة تصنيف مقدم الحجز محاسبياً ونقله إلى التزام العقد وتحصيل أي فرق إضافي ذرياً (Event 1b)
            if contract_holding > Decimal('0.00') or additional_to_collect > Decimal('0.00'):
                from real_estate.services.accounting_service import RealEstateAccountingService
                RealEstateAccountingService.post_booking_conversion(
                    booking=locked_booking,
                    contract=contract,
                    user=user,
                    additional_down_payment=additional_to_collect,
                    payment_account=payment_account,
                    reference=contract.contract_number,
                    converted_holding_deposit=eff_deposit
                )

            # 5. توليد جدول الأقساط الإلزامي للعقد الساري إن لم يكن مرتبطاً بجدول مسبقاً
            if not contract.installment_plan_id:
                from sale.models.installments import InstallmentPlan, InstallmentItem
                tot_price = contract.final_contract_price if contract.final_contract_price > Decimal('0.00') else Decimal('1000.00')
                net_financed = max(Decimal('0.00'), tot_price - (contract.down_payment or Decimal('0.00')))

                if net_financed <= Decimal('0.00'):
                    # سداد نقدي كامل 100% بالمقدم - خطة منتهية ومكتملة فوراً
                    plan = InstallmentPlan.objects.create(
                        customer=contract.customer,
                        total_principal=Decimal('0.00'),
                        total_markup=Decimal('0.00'),
                        total_amount=tot_price,
                        down_payment=tot_price,
                        number_of_installments=1,
                        frequency='CUSTOM',
                        start_date=c_date,
                        status=InstallmentPlan.PlanStatus.DRAFT,
                        created_by=user or contract.created_by,
                    )
                    InstallmentItem.objects.create(
                        plan=plan,
                        installment_number=1,
                        trigger_type=InstallmentItem.TriggerType.DATE_BASED,
                        due_date=c_date,
                        principal_amount=Decimal('0.00'),
                        interest_amount=Decimal('0.00'),
                        total_amount=Decimal('0.00'),
                        paid_amount=Decimal('0.00'),
                    )
                    contract.installment_plan = plan
                    contract.save(update_fields=['installment_plan', 'updated_at'])
                    plan.status = InstallmentPlan.PlanStatus.COMPLETED
                    plan.save(update_fields=['status'])
                else:
                    num_inst = number_of_installments if (number_of_installments and number_of_installments > 0) else 4
                    freq = installment_frequency or 'QUARTERLY'
                    start_d = first_installment_date or c_date
                    months_step = {
                        'MONTHLY': 1,
                        'QUARTERLY': 3,
                        'SEMI_ANNUAL': 6,
                        'ANNUAL': 12,
                    }.get(freq, 3)

                    plan = InstallmentPlan.objects.create(
                        customer=contract.customer,
                        total_principal=net_financed,
                        total_markup=Decimal('0.00'),
                        total_amount=tot_price,
                        down_payment=contract.down_payment or Decimal('0.00'),
                        number_of_installments=num_inst,
                        frequency=freq,
                        start_date=start_d,
                        status=InstallmentPlan.PlanStatus.DRAFT,
                        created_by=user or contract.created_by,
                    )
                    base_inst_val = (net_financed / Decimal(num_inst)).quantize(Decimal('0.01'))
                    running_sum = Decimal('0.00')
                    inst_due = start_d
                    for idx in range(1, num_inst + 1):
                        if idx == num_inst:
                            item_val = net_financed - running_sum
                        else:
                            item_val = base_inst_val
                            running_sum += item_val
                        InstallmentItem.objects.create(
                            plan=plan,
                            installment_number=idx,
                            trigger_type=InstallmentItem.TriggerType.DATE_BASED,
                            due_date=inst_due,
                            principal_amount=item_val,
                            interest_amount=Decimal('0.00'),
                            total_amount=item_val,
                        )
                        y = inst_due.year + (inst_due.month + months_step - 1) // 12
                        m = (inst_due.month + months_step - 1) % 12 + 1
                        d = min(inst_due.day, 28)
                        inst_due = datetime.date(y, m, d)

                    contract.installment_plan = plan
                    contract.save(update_fields=['installment_plan', 'updated_at'])
                    plan.status = InstallmentPlan.PlanStatus.ACTIVE
                    plan.save(update_fields=['status'])

            # 5b. ربط الوسيط العقاري إن وُجد (Broker Commission Service)
            if broker:
                from real_estate.services.broker_service import BrokerCommissionService
                BrokerCommissionService.assign_broker_to_contract(
                    contract=contract,
                    broker=broker,
                    commission_rate=broker_commission_rate,
                    user=user,
                    ceo_override_token=ceo_override_token,
                    ceo_override_reason=ceo_override_reason or ""
                )

            # 6. إنشاء أمر تشطيب ملحق وخطة سداد مستقلة عند اختيار هيكلة فصل التشطيب
            if contract.contract_tax_structure == PropertyContract.ContractTaxStructure.SPLIT_SPA_FINISHING_ANNEX or contract.has_decoupled_finishing:
                fin_total = contract.finishing_total_amount or locked_booking.total_finishing_amount or Decimal('0.00')
                if fin_total > Decimal('0.00'):
                    from real_estate.models.finishing import UnitFinishingOrder
                    from real_estate.services.finishing_financial_service import FinishingFinancialService

                    order_num = f"FO-{contract.contract_number}"
                    fin_order, created = UnitFinishingOrder.objects.get_or_create(
                        contract=contract,
                        defaults={
                            'order_number': order_num,
                            'unit': locked_unit,
                            'customer': contract.customer,
                            'title': f"أمر تشطيب ملحق للعقد {contract.contract_number}",
                            'gross_finishing_amount': fin_total,
                            'net_finishing_price': fin_total,
                            'remaining_balance': fin_total,
                            'created_by': user or contract.created_by,
                        }
                    )
                    if not fin_order.finishing_installment_plan_id:
                        fin_inst_count = int(finishing_installments_count or 4)
                        fin_freq = int(finishing_installment_frequency or 3)
                        FinishingFinancialService.generate_segregated_installment_plan(
                            order=fin_order,
                            number_of_installments=fin_inst_count,
                            frequency_months=fin_freq,
                            start_date=c_date,
                            user=user or contract.created_by
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
        approved_deduction_fees: Decimal = Decimal('0.00'),
        user=None,
        payment_account=None,
    ) -> UnitBooking:
        """
        إلغاء الحجز وإعادة إتاحة الوحدة للبيع مجدداً في دورة إعادة البيع (Resale Lifecycle)
        مع حراسة الصلاحيات وفصل طلب الاسترداد عن اكتماله الفعلي واحتساب المصاريف الإدارية المعتمدة.
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

            # احتساب صافي المبلغ المحصل فعلياً عبر دورة حياة الشيك أو الحسابات
            eff_deposit = cls.get_effective_collected_deposit(locked_booking)
            has_deposit = (eff_deposit > Decimal('0.00'))

            allowed_cancel_statuses = [UnitBooking.BookingStatus.ACTIVE]
            if has_deposit or locked_booking.is_deposit_collected:
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

            from real_estate.models.refund import BookingCancellationSettlement, RefundDisbursementPayment
            from real_estate.services.accounting_service import RealEstateAccountingService

            if forfeit_deposit:
                if has_deposit:
                    RealEstateAccountingService.post_booking_forfeiture(
                        booking=locked_booking,
                        user=user,
                        amount=eff_deposit
                    )
                target_status = UnitBooking.BookingStatus.CANCELLED_FORFEITED
            else:
                if has_deposit:
                    deduction = min(Decimal(str(approved_deduction_fees or '0.00')), eff_deposit)
                    net_refundable = max(Decimal('0.00'), eff_deposit - deduction)

                    settlement = locked_booking.active_cancellation_settlement
                    if not settlement:
                        from financial.services.exchange_rate_service import ExchangeRateService
                        settle_curr = locked_booking.currency or ExchangeRateService.get_functional_currency()
                        settlement = BookingCancellationSettlement.objects.create(
                            booking=locked_booking,
                            currency=settle_curr,
                            exchange_rate=locked_booking.exchange_rate or Decimal('1.000000'),
                            total_deposit_paid=eff_deposit,
                            approved_deduction_fees=deduction,
                            net_refundable_amount=net_refundable,
                            remaining_disbursable_amount=net_refundable,
                            cancellation_reason='FINANCIAL_HARDSHIP',
                            notes=f"إلغاء حجز: {reason}",
                            processed_by=user or locked_booking.created_by,
                        )
                        locked_booking.active_cancellation_settlement = settlement
                        locked_booking.save(update_fields=['active_cancellation_settlement', 'updated_at'])
                    else:
                        settlement.total_deposit_paid = eff_deposit
                        settlement.approved_deduction_fees = deduction
                        settlement.net_refundable_amount = net_refundable
                        settlement.remaining_disbursable_amount = net_refundable
                        settlement.save(update_fields=['total_deposit_paid', 'approved_deduction_fees', 'net_refundable_amount', 'remaining_disbursable_amount', 'updated_at'])

                    # إثبات قيد خصم المصاريف الإدارية المعتمَدة إن وُجدت
                    if deduction > Decimal('0.00') and not settlement.forfeiture_journal_entry:
                        try:
                            deduct_entry = RealEstateAccountingService.post_booking_forfeiture(
                                booking=locked_booking,
                                user=user,
                                amount=deduction,
                                reference=f"DEDUCT-{locked_booking.booking_number}"
                            )
                            settlement.forfeiture_journal_entry = deduct_entry
                            settlement.save(update_fields=['forfeiture_journal_entry', 'updated_at'])
                        except Exception as fee_err:
                            logger.error(f"Error posting booking cancellation deduction fee: {fee_err}")

                    if payment_account and settlement.remaining_disbursable_amount > Decimal('0.00'):
                        # تسوية مالية فورية
                        pay_method = RefundDisbursementPayment.DisbursementMethod.BANK_TRANSFER
                        if payment_account and getattr(payment_account, 'code', '').startswith('1111'):
                            pay_method = RefundDisbursementPayment.DisbursementMethod.CASH

                        RealEstateAccountingService.disburse_refund(
                            settlement_id=settlement.id,
                            requested_amount=settlement.remaining_disbursable_amount,
                            payout_currency=settlement.currency,
                            method=pay_method,
                            payment_account=payment_account,
                            user=user,
                            idempotency_key=f"REFUND-SETTLE-{settlement.id}",
                        )
                        target_status = UnitBooking.BookingStatus.CANCELLED_REFUNDED
                    else:
                        # فصل طلب الاسترداد عن اكتماله: الحجز يصبح بانتظار الرد المالي
                        target_status = UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND
                else:
                    target_status = UnitBooking.BookingStatus.EXPIRED_RELEASED
                    if locked_booking.active_cancellation_settlement:
                        settle = locked_booking.active_cancellation_settlement
                        settle.total_deposit_paid = Decimal('0.00')
                        settle.net_refundable_amount = Decimal('0.00')
                        settle.remaining_disbursable_amount = Decimal('0.00')
                        settle.save(update_fields=['total_deposit_paid', 'net_refundable_amount', 'remaining_disbursable_amount', 'updated_at'])

            # 1. تحديث حالة الحجز
            locked_booking.status = target_status
            locked_booking.notes = f"{locked_booking.notes}\n[سبب الإلغاء: {reason}]".strip()
            locked_booking.save(update_fields=['status', 'notes', 'active_cancellation_settlement', 'updated_at'])

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
        payment_account=None,
        method: str = None,
        cheque_data: dict = None,
        user=None,
        reference: str = ""
    ) -> UnitBooking:
        """
        التسوية المالية لصرف واسترداد جدية الحجز (Settle Booking Deposit Refund)
        يرحل قيد رد الأمانات (payment_voucher أو محرك الشيكات) ويحول الحالة إلى CANCELLED_REFUNDED
        يدعم وسيلة الصرف نقد / بنك / شيكات بمفتاح منع تكرار حتمي محكم.
        """
        from real_estate.models.refund import BookingCancellationSettlement, RefundDisbursementPayment
        from real_estate.services.accounting_service import RealEstateAccountingService

        pay_method = method or (
            RefundDisbursementPayment.DisbursementMethod.CASH
            if payment_account and getattr(payment_account, 'code', '').startswith('1111')
            else RefundDisbursementPayment.DisbursementMethod.BANK_TRANSFER
        )

        if pay_method in [RefundDisbursementPayment.DisbursementMethod.CASH, RefundDisbursementPayment.DisbursementMethod.BANK_TRANSFER] and not payment_account:
            raise BookingValidationError(_("يجب تحديد حساب الخزينة أو البنك لصرف المبلغ المسترد."))

        if pay_method == RefundDisbursementPayment.DisbursementMethod.CHEQUE:
            if not cheque_data or not cheque_data.get('cheque_number'):
                raise BookingValidationError(_("بيانات ورقم الشيك إلزامية للصرف بشيك مصرفي."))

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

            # مزامنة حالة التحصيل للشيكات والقيود المحاسبية
            cls.sync_booking_collection_state(locked_booking)

            if locked_booking.holding_deposit <= Decimal('0.00') or not locked_booking.is_deposit_collected:
                raise BookingValidationError(_("لا يوجد مبلغ جدية حجز محصل مسجل على هذا الحجز لصرفه."))

            # حراسة عدم الصرف المزدوج وعدم التكرار (Idempotency & Double-Refund Guard)
            settlement = locked_booking.active_cancellation_settlement
            if settlement:
                if settlement.remaining_disbursable_amount <= Decimal('0.00'):
                    logger.info(
                        f"⚠️ تسوية الحجز {locked_booking.booking_number} مصروفة بالكامل بالفعل ({settlement.settlement_number})."
                    )
                    return locked_booking
            elif locked_booking.status == UnitBooking.BookingStatus.CANCELLED_REFUNDED:
                return locked_booking

            # التحقق من أن حالة الحجز مؤهلة للصرف إن لم توجد تسوية مسبقة ذات رصيد
            if not settlement:
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

            if not settlement:
                from financial.services.exchange_rate_service import ExchangeRateService
                settle_curr = locked_booking.currency or ExchangeRateService.get_functional_currency()
                settlement = BookingCancellationSettlement.objects.create(
                    booking=locked_booking,
                    currency=settle_curr,
                    exchange_rate=locked_booking.exchange_rate or Decimal('1.000000'),
                    total_deposit_paid=locked_booking.holding_deposit,
                    net_refundable_amount=locked_booking.holding_deposit,
                    remaining_disbursable_amount=locked_booking.holding_deposit,
                    cancellation_reason='FINANCIAL_HARDSHIP',
                    notes=f"تسوية صرف استرداد لحجز {locked_booking.booking_number}",
                    processed_by=user or locked_booking.created_by,
                )
                locked_booking.active_cancellation_settlement = settlement
                locked_booking.save(update_fields=['active_cancellation_settlement', 'updated_at'])

            if settlement.remaining_disbursable_amount > Decimal('0.00'):
                RealEstateAccountingService.disburse_refund(
                    settlement_id=settlement.id,
                    requested_amount=settlement.remaining_disbursable_amount,
                    payout_currency=settlement.currency,
                    method=pay_method,
                    payment_account=payment_account,
                    cheque_data=cheque_data,
                    user=user,
                    idempotency_key=f"REFUND-SETTLE-{settlement.id}",
                )

            locked_booking.status = UnitBooking.BookingStatus.CANCELLED_REFUNDED
            locked_booking.save(update_fields=['status', 'updated_at'])
            locked_booking.refresh_from_db()
            return locked_booking

    @classmethod
    def review_booking_sales(cls, booking_id: int, user) -> UnitBooking:
        """
        تسجيل مراجعة المبيعات والحسابات للحجز
        التحقق من حالة الحجز وتطبيق قيد الفصل الرقابي (Segregation of Duties).
        """
        if not user or not user.is_authenticated:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied(_("يجب تسجيل الدخول لإجراء مراجعة المبيعات."))

        if hasattr(user, 'has_perm') and not (user.is_superuser or getattr(user, 'is_admin', False)):
            if not user.has_perm('real_estate.change_unitbooking'):
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied(_("غير مصرح لك بإجراء مراجعة المبيعات على استمارة الحجز."))

        with transaction.atomic():
            try:
                locked_booking = UnitBooking.objects.select_for_update().get(pk=booking_id)
            except UnitBooking.DoesNotExist:
                raise BookingValidationError(_("استمارة الحجز المطلوبة غير موجودة."))

            if locked_booking.status != UnitBooking.BookingStatus.ACTIVE:
                raise BookingValidationError(
                    _("لا يمكن مراجعة حجز غير نشط (الحالة الحالية: %(status)s).") % {
                        'status': locked_booking.get_status_display()
                    }
                )

            if locked_booking.is_reviewed_sales:
                return locked_booking

            # قيد الفصل الرقابي: لا يجوز لمنشئ الحجز مراجعة حجزه بنفسه
            if locked_booking.created_by_id and user.id == locked_booking.created_by_id and not (user.is_superuser or getattr(user, 'is_admin', False)):
                raise BookingValidationError(_("قيد الفصل الرقابي (Segregation of Duties): لا يجوز لمنشئ الحجز مراجعة حجزه بنفسه."))

            locked_booking.is_reviewed_sales = True
            locked_booking.reviewed_by = user
            locked_booking.reviewed_at = timezone.now()
            locked_booking.save(force_audit_update=True)

            logger.info(
                f"✅ تمت مراجعة المبيعات للحجز {locked_booking.booking_number} بواسطة المستخدم {user}."
            )
            return locked_booking

    @classmethod
    def confirm_booking_audit(cls, booking_id: int, user) -> UnitBooking:
        """
        تسجيل الاعتماد المالي والرقابي للحجز
        يشترط استيفاء مراجعة المبيعات مسبقاً وتطبيق قيد الفصل الرقابي الثنائي الكامل.
        """
        if not user or not user.is_authenticated:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied(_("يجب تسجيل الدخول لإجراء الاعتماد الرقابي."))

        if hasattr(user, 'has_perm') and not (user.is_superuser or getattr(user, 'is_admin', False)):
            if not user.has_perm('real_estate.change_unitbooking'):
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied(_("غير مصرح لك بالاعتماد المالي والرقابي على استمارة الحجز."))

        with transaction.atomic():
            try:
                locked_booking = UnitBooking.objects.select_for_update().get(pk=booking_id)
            except UnitBooking.DoesNotExist:
                raise BookingValidationError(_("استمارة الحجز المطلوبة غير موجودة."))

            if locked_booking.status != UnitBooking.BookingStatus.ACTIVE:
                raise BookingValidationError(
                    _("لا يمكن اعتماد حجز غير نشط (الحالة الحالية: %(status)s).") % {
                        'status': locked_booking.get_status_display()
                    }
                )

            if locked_booking.is_confirmed_audit:
                return locked_booking

            if not locked_booking.is_reviewed_sales:
                raise BookingValidationError(_("لا يجوز الاعتماد الرقابي لحجز لم تستوفَ فيه مراجعة المبيعات أولاً."))

            # قيد الفصل الرقابي: لا يجوز لنفس المستخدم مراجعة المبيعات والاعتماد الرقابي معاً
            if locked_booking.reviewed_by_id and user.id == locked_booking.reviewed_by_id and not (user.is_superuser or getattr(user, 'is_admin', False)):
                raise BookingValidationError(_("قيد الفصل الرقابي (Segregation of Duties): لا يجوز لنفس المستخدم تسجيل مراجعة المبيعات والاعتماد الرقابي معاً."))

            # قيد الفصل الرقابي: لا يجوز لمنشئ الحجز اعتماده رقابياً بنفسه
            if locked_booking.created_by_id and user.id == locked_booking.created_by_id and not (user.is_superuser or getattr(user, 'is_admin', False)):
                raise BookingValidationError(_("قيد الفصل الرقابي (Segregation of Duties): لا يجوز لمنشئ الحجز اعتماده رقابياً بنفسه."))

            locked_booking.is_confirmed_audit = True
            locked_booking.confirmed_by = user
            locked_booking.confirmed_at = timezone.now()
            locked_booking.save(force_audit_update=True)

            logger.info(
                f"✅ تم الاعتماد المالي والرقابي للحجز {locked_booking.booking_number} بواسطة المستخدم {user}."
            )
            return locked_booking

    @classmethod
    def bypass_booking_audit(cls, booking_id: int, user, reason: str) -> UnitBooking:
        """
        التجاوز الإداري الاستثنائي المبرر لقيد الفصل الرقابي
        متاح حصراً للسوبر يوزر أو الحاصلين على صلاحية can_override_sod أو مسؤولي النظام مع توثيق السبب إجبارياً.
        """
        if not user or not user.is_authenticated:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied(_("يجب تسجيل الدخول لإجراء التجاوز الإداري."))

        is_authorized = (
            user.is_superuser
            or getattr(user, 'is_admin', False)
            or (hasattr(user, 'has_perm') and user.has_perm('real_estate.can_override_sod'))
        )
        if not is_authorized:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied(_("غير مصرح لك بالتجاوز الإداري الاستثنائي لمنظومة الاعتماد الرقابي (real_estate.can_override_sod)."))

        clean_reason = str(reason or '').strip()
        if not clean_reason:
            raise BookingValidationError(_("يجب توثيق سبب التجاوز الإداري الاستثنائي بدقة ولا يمكن تركه فارغاً."))

        with transaction.atomic():
            try:
                locked_booking = UnitBooking.objects.select_for_update().get(pk=booking_id)
            except UnitBooking.DoesNotExist:
                raise BookingValidationError(_("استمارة الحجز المطلوبة غير موجودة."))

            if locked_booking.status != UnitBooking.BookingStatus.ACTIVE:
                raise BookingValidationError(
                    _("لا يمكن تطبيق التجاوز الإداري على حجز غير نشط (الحالة الحالية: %(status)s).") % {
                        'status': locked_booking.get_status_display()
                    }
                )

            locked_booking.audit_bypassed = True
            locked_booking.audit_bypass_reason = clean_reason
            locked_booking.audit_bypassed_by = user
            locked_booking.save(force_audit_update=True)

            logger.warning(
                f"⚠️ تم التجاوز الإداري الاستثنائي للرقابة الثنائية على الحجز {locked_booking.booking_number} "
                f"بواسطة {user}. السبب: {clean_reason}"
            )
            return locked_booking
