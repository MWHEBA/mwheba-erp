# -*- coding: utf-8 -*-
"""
RealEstateAccountingService - محرك المعالجة المحاسبية العقارية المتوافق مع معيار IFRS 15
(Wave 1 Phase 3 - Day-1 Event Accounting Engine)
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntry
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData
from governance.exceptions import IdempotencyError, ValidationError as GovValidationError

logger = logging.getLogger(__name__)


class RealEstateAccountingService:
    """
    الخدمة المركزية لإصدار قيود اليومية للقطاع العقاري وفق معيار IFRS 15
    تمرر جميع المعاملات حصراً عبر AccountingGateway وتضمن حماية Idempotency وبصمة البيانات المالية.
    """

    @classmethod
    def get_or_resolve_account(cls, role_name: str, fallback_code: str = "11110") -> ChartOfAccounts:
        """
        جلب الحساب المحاسبي عبر سجل الأدوار الموحد مع إنشاء الحساب الافتراضي إذا لم يكن موجوداً
        """
        account = AccountRoleRegistry.get_account(role_name)
        if not account:
            account = ChartOfAccounts.objects.filter(code=fallback_code).first()
        if not account or not account.is_active:
            raise ValidationError(
                _("الحساب المحاسبي للدور '%(role)s' غير مهيأ أو غير نشط في دليل الحسابات.") % {'role': role_name}
            )
        return account

    @classmethod
    def post_booking_holding_fee(
        cls,
        booking,
        payment_account: ChartOfAccounts,
        user,
        reference: str = ""
    ) -> JournalEntry:
        """
        Event 1: إثبات تحصيل جدية الحجز (Booking Holding Fee)
        Dr: Cash / Bank (111xx)
        Cr: Customer Booking Advances (21101)
        """
        deposit_amt = getattr(booking, 'holding_deposit', None)
        if deposit_amt is None:
            deposit_amt = getattr(booking, 'deposit_amount', Decimal('0.00'))
        deposit_dec = Decimal(str(deposit_amt))

        if deposit_dec <= Decimal("0.00"):
            raise ValidationError(_("مبلغ جدية الحجز يجب أن يكون أكبر من الصفر."))

        booking_advance_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_BOOKING_ADVANCE.value,
            fallback_code="21101"
        )

        curr_code = getattr(booking, 'currency', None)
        currency_str = getattr(curr_code, 'code', 'EGP') if curr_code else 'EGP'
        rate = Decimal(str(getattr(booking, 'exchange_rate', '1.000000') or '1.000000'))
        is_foreign = (currency_str != 'EGP')

        if is_foreign and rate > Decimal("0.00"):
            functional_deposit = (deposit_dec * rate).quantize(Decimal('0.01'))
            foreign_deposit = deposit_dec
        else:
            functional_deposit = deposit_dec
            foreign_deposit = Decimal('0.00')

        lines = [
            JournalEntryLineData(
                account_code=payment_account.code,
                debit=functional_deposit,
                credit=Decimal("0.00"),
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=foreign_deposit if is_foreign else Decimal('0.00'),
                foreign_credit=Decimal("0.00"),
                description=f"تحصيل جدية حجز الوحدة {booking.unit.unit_code} - إيصال {booking.booking_number}",
                project=booking.unit.project.code if booking.unit and booking.unit.project else None
            ),
            JournalEntryLineData(
                account_code=booking_advance_account.code,
                debit=Decimal("0.00"),
                credit=functional_deposit,
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=Decimal("0.00"),
                foreign_credit=foreign_deposit if is_foreign else Decimal('0.00'),
                description=f"أمانات جدية حجز معلقة - العميل {booking.customer.name}",
                project=booking.unit.project.code if booking.unit and booking.unit.project else None
            ),
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='UnitBooking',
            object_id=booking.id,
            operation='holding_fee'
        )

        gateway = AccountingGateway()
        return gateway.create_journal_entry(
            source_module='real_estate',
            source_model='UnitBooking',
            source_id=booking.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='receipt_voucher',
            description=f"تحصيل جدية حجز الوحدة {booking.unit.unit_code} للعميل {booking.customer.name}",
            reference=reference or booking.booking_number,
            date=booking.booking_date
        )

    @classmethod
    def post_booking_conversion(
        cls,
        booking,
        contract,
        user,
        additional_down_payment: Decimal = Decimal("0.00"),
        payment_account: Optional[ChartOfAccounts] = None,
        reference: str = ""
    ) -> JournalEntry:
        """
        Event 1b: تحويل جدية الحجز إلى دفعة مقدمة تعاقدية رسمية (Booking Conversion to Down Payment)
        Dr: Customer Booking Advances (21101) [بمبلغ جدية الحجز المحول]
        Dr: Cash / Bank (111xx) [بالمبلغ الإضافي لمقدم التعاقد إن وُجد]
        Cr: Real Estate Contract Liability - Down Payment (21102) [بإجمالي مقدم التعاقد]
        """
        booking_advance_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_BOOKING_ADVANCE.value,
            fallback_code="21101"
        )
        contract_liability_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_CONTRACT_LIABILITY.value,
            fallback_code="21102"
        )

        dep_val = getattr(booking, 'holding_deposit', None)
        if dep_val is None:
            dep_val = getattr(booking, 'deposit_amount', Decimal('0.00'))
        holding_fee = Decimal(str(dep_val))
        extra_down = Decimal(str(additional_down_payment or Decimal("0.00")))
        total_down_payment = holding_fee + extra_down

        if total_down_payment <= Decimal("0.00"):
            raise ValidationError(_("إجمالي مقدم التعاقد المحول يجب أن يكون أكبر من الصفر."))

        if extra_down > Decimal("0.00") and not payment_account:
            raise ValidationError(_("يجب تحديد حساب الخزينة أو البنك لتحصيل الدفعة النقدية الإضافية."))

        # استخراج بيانات عملة وسعر صرف جدية الحجز الأصلية
        booking_curr = getattr(booking, 'currency', None)
        booking_curr_str = getattr(booking_curr, 'code', 'EGP') if booking_curr else 'EGP'
        booking_rate = Decimal(str(getattr(booking, 'exchange_rate', '1.000000') or '1.000000'))
        booking_is_foreign = (booking_curr_str != 'EGP')

        # القيمة الوظيفية الدقيقة لجدية الحجز المسجلة بحساب أمانات الحجز 21101 لإقفاله تماماً دون أي تشويه
        if booking_is_foreign and booking_rate > Decimal("0.00"):
            func_holding = (holding_fee * booking_rate).quantize(Decimal('0.01'))
            foreign_holding = holding_fee
        else:
            func_holding = holding_fee
            foreign_holding = Decimal('0.00')

        # استخراج بيانات عملة وسعر صرف العقد النهائي
        curr_code = getattr(contract, 'currency', None)
        currency_str = getattr(curr_code, 'code', 'EGP') if curr_code else 'EGP'
        rate = Decimal(str(getattr(contract, 'exchange_rate', '1.000000') or '1.000000'))
        proj_code = contract.project.code if contract.project else None
        is_foreign = (currency_str != 'EGP')

        # احتساب معادل جدية الحجز بعملة العقد
        if currency_str == booking_curr_str:
            contract_holding_fee = holding_fee
        else:
            if is_foreign and rate > Decimal("0.00"):
                contract_holding_fee = (func_holding / rate).quantize(Decimal('0.01'))
            else:
                contract_holding_fee = func_holding

        # احتساب القيمة الوظيفية والمحلية للدفعة الإضافية
        if is_foreign and rate > Decimal("0.00"):
            func_extra = (extra_down * rate).quantize(Decimal('0.01'))
            foreign_extra = extra_down
        else:
            func_extra = extra_down
            foreign_extra = Decimal('0.00')

        func_total = func_holding + func_extra
        foreign_total_down = (contract_holding_fee + foreign_extra) if is_foreign else Decimal('0.00')

        lines: List[JournalEntryLineData] = []
        if holding_fee > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=booking_advance_account.code,
                    debit=func_holding,
                    credit=Decimal("0.00"),
                    currency=booking_curr_str,
                    exchange_rate=booking_rate,
                    foreign_debit=foreign_holding if booking_is_foreign else Decimal('0.00'),
                    foreign_credit=Decimal("0.00"),
                    description=f"تحويل جدية الحجز {booking.booking_number} لمقدم تعاقد العقد {contract.contract_number}",
                    project=proj_code
                )
            )

        if extra_down > Decimal("0.00") and payment_account:
            lines.append(
                JournalEntryLineData(
                    account_code=payment_account.code,
                    debit=func_extra,
                    credit=Decimal("0.00"),
                    currency=currency_str,
                    exchange_rate=rate,
                    foreign_debit=foreign_extra if is_foreign else Decimal('0.00'),
                    foreign_credit=Decimal("0.00"),
                    description=f"سداد استكمال مقدم التعاقد للعقد {contract.contract_number}",
                    project=proj_code
                )
            )

        lines.append(
            JournalEntryLineData(
                account_code=contract_liability_account.code,
                debit=Decimal("0.00"),
                credit=func_total,
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=Decimal("0.00"),
                foreign_credit=foreign_total_down if is_foreign else Decimal('0.00'),
                description=f"التزامات عقد بيع وحدة - مقدم تعاقد العقد {contract.contract_number}",
                project=proj_code
            )
        )

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='PropertyContract',
            object_id=contract.id,
            operation='booking_conversion'
        )

        gateway = AccountingGateway()
        return gateway.create_journal_entry(
            source_module='real_estate',
            source_model='PropertyContract',
            source_id=contract.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='sales_invoice',
            description=f"تسوية مقدم التعاقد للعقد {contract.contract_number} للعميل {contract.customer.name}",
            reference=reference or contract.contract_number,
            date=contract.contract_date
        )

    @classmethod
    def post_booking_refund(
        cls,
        booking,
        payment_account: ChartOfAccounts,
        user,
        reference: str = ""
    ) -> JournalEntry:
        """
        Event 1c: إثبات رد وصرف جدية الحجز للعميل عند إلغاء الحجز (Booking Holding Fee Refund)
        Dr: Customer Booking Advances (21101) [إقفال الأمانات]
        Cr: Cash / Bank (111xx) [صرف المبلغ للعميل]
        """
        deposit_amt = getattr(booking, 'holding_deposit', Decimal('0.00'))
        deposit_dec = Decimal(str(deposit_amt))
        if deposit_dec <= Decimal("0.00"):
            raise ValidationError(_("مبلغ جدية الحجز المطلوب رده يجب أن يكون أكبر من الصفر."))

        booking_advance_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_BOOKING_ADVANCE.value,
            fallback_code="21101"
        )

        curr_code = getattr(booking, 'currency', None)
        currency_str = getattr(curr_code, 'code', 'EGP') if curr_code else 'EGP'
        rate = Decimal(str(getattr(booking, 'exchange_rate', '1.000000') or '1.000000'))
        is_foreign = (currency_str != 'EGP')

        if is_foreign and rate > Decimal("0.00"):
            functional_deposit = (deposit_dec * rate).quantize(Decimal('0.01'))
            foreign_deposit = deposit_dec
        else:
            functional_deposit = deposit_dec
            foreign_deposit = Decimal('0.00')

        proj_code = booking.unit.project.code if booking.unit and booking.unit.project else None

        lines = [
            JournalEntryLineData(
                account_code=booking_advance_account.code,
                debit=functional_deposit,
                credit=Decimal("0.00"),
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=foreign_deposit if is_foreign else Decimal('0.00'),
                foreign_credit=Decimal("0.00"),
                description=f"رد أمانات جدية حجز الوحدة {booking.unit.unit_code} للعميل {booking.customer.name}",
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=payment_account.code,
                debit=Decimal("0.00"),
                credit=functional_deposit,
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=Decimal("0.00"),
                foreign_credit=foreign_deposit if is_foreign else Decimal('0.00'),
                description=f"صرف واسترداد جدية حجز الوحدة {booking.unit.unit_code} - استمارة {booking.booking_number}",
                project=proj_code
            ),
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='UnitBooking',
            object_id=booking.id,
            operation='holding_fee_refund'
        )

        gateway = AccountingGateway()
        return gateway.create_journal_entry(
            source_module='real_estate',
            source_model='UnitBooking',
            source_id=booking.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='payment_voucher',
            description=f"رد واسترداد جدية حجز الوحدة {booking.unit.unit_code} للعميل {booking.customer.name}",
            reference=reference or f"REF-{booking.booking_number}",
            date=timezone.localdate()
        )

    @classmethod
    def post_booking_forfeiture(
        cls,
        booking,
        user,
        reference: str = ""
    ) -> JournalEntry:
        """
        Event 1d: إثبات مصادرة جدية الحجز كإيرادات عند إلغاء الحجز (Booking Holding Fee Forfeiture)
        Dr: Customer Booking Advances (21101) [إقفال الأمانات]
        Cr: Penalty Income / Forfeited Fee (42201) [إيرادات غرامات ومصادرات]
        """
        deposit_amt = getattr(booking, 'holding_deposit', Decimal('0.00'))
        deposit_dec = Decimal(str(deposit_amt))
        if deposit_dec <= Decimal("0.00"):
            raise ValidationError(_("مبلغ جدية الحجز المطلوب مصادرته يجب أن يكون أكبر من الصفر."))

        booking_advance_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_BOOKING_ADVANCE.value,
            fallback_code="21101"
        )
        penalty_income_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_FORFEITED_INCOME.value,
            fallback_code="42201"
        )

        curr_code = getattr(booking, 'currency', None)
        currency_str = getattr(curr_code, 'code', 'EGP') if curr_code else 'EGP'
        rate = Decimal(str(getattr(booking, 'exchange_rate', '1.000000') or '1.000000'))
        is_foreign = (currency_str != 'EGP')

        if is_foreign and rate > Decimal("0.00"):
            functional_deposit = (deposit_dec * rate).quantize(Decimal('0.01'))
            foreign_deposit = deposit_dec
        else:
            functional_deposit = deposit_dec
            foreign_deposit = Decimal('0.00')

        proj_code = booking.unit.project.code if booking.unit and booking.unit.project else None

        lines = [
            JournalEntryLineData(
                account_code=booking_advance_account.code,
                debit=functional_deposit,
                credit=Decimal("0.00"),
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=foreign_deposit if is_foreign else Decimal('0.00'),
                foreign_credit=Decimal("0.00"),
                description=f"مصادرة جدية حجز الوحدة {booking.unit.unit_code} للعميل {booking.customer.name}",
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=penalty_income_account.code,
                debit=Decimal("0.00"),
                credit=functional_deposit,
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=Decimal("0.00"),
                foreign_credit=foreign_deposit if is_foreign else Decimal('0.00'),
                description=f"إيرادات مصادرة جدية حجز - استمارة {booking.booking_number}",
                project=proj_code
            ),
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='UnitBooking',
            object_id=booking.id,
            operation='holding_fee_forfeiture'
        )

        gateway = AccountingGateway()
        return gateway.create_journal_entry(
            source_module='real_estate',
            source_model='UnitBooking',
            source_id=booking.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='journal_voucher',
            description=f"مصادرة جدية حجز الوحدة {booking.unit.unit_code} للعميل {booking.customer.name}",
            reference=reference or f"FORF-{booking.booking_number}",
            date=timezone.localdate()
        )

    @classmethod
    def _verify_idempotency_fingerprint(
        cls,
        payment,
        settlement_id: int,
        requested_amount: Decimal,
        payout_currency,
        method: str,
        payment_account,
        cheque_data: dict = None
    ) -> bool:
        """مطابقة البصمة الشاملة للمعلمات المالية والتشغيلية لمنع التكرار"""
        if payment.settlement_id != settlement_id:
            return False
        if payment.amount != requested_amount:
            return False
        if payment.payout_currency_id != payout_currency.id:
            return False
        if payment.method != method:
            return False
        if payment_account and payment.payment_account_id != payment_account.id:
            return False
        from real_estate.models.refund import RefundDisbursementPayment
        if method == RefundDisbursementPayment.DisbursementMethod.CHEQUE and cheque_data:
            req_chq_num = (cheque_data.get('cheque_number') or '').strip()
            if payment.cheque and payment.cheque.cheque_number != req_chq_num:
                return False
        return True

    @classmethod
    def disburse_refund(
        cls,
        settlement_id: int,
        requested_amount: Decimal,
        payout_currency,
        method: str,
        payment_account=None,
        cheque_data: dict = None,
        idempotency_key: str = None,
        payment_date=None,
        is_full_sweep: bool = False,
        user=None
    ):
        """
        صرف استرداد الحجز (نقداً، بنكياً، أو بشيك) بالخوارزمية الدقيقة V14:
        1. التحقق الاستباقي الصارم من وسيلة الصرف وإيجابية المبلغ.
        2. الفحص السريع قبل الأقفال (Pre-Lock Fast Path) لمفتاح منع التكرار.
        3. حيازة الأقفال بالترتيب الهرمي الصارم (Level 1: payment_account, Level 2: settlement).
        4. فحص اتساق المؤشر النشط.
        5. فحص مفتاح التكرار فوراً بعد القفل (Post-Lock Idempotency First).
        6. حراسة الرصيد الصفري للطلبات الجديدة حصراً.
        7. حل أسعار الصرف الثنائية والحساب بدقة كاملة وتأجيل التقريب.
        8. الحصر الصارم لسماحية التقريب باشتراط التصفية الكاملة صراحة (is_full_sweep=True).
        9. التفكيك الرياضي المتوازن للانحراف المحاسبي (pure_fx_diff + rounding_amount_func).
        10. التنفيذ المحاسبي والتشغيلي (محرك الشيكات أو قيود النقد/البنك مع مطابقة الأستاذ المساعد).
        11. إنشاء سجل الصرف وتحديث أرصدة وحالة التسوية.
        """
        from real_estate.models.refund import BookingCancellationSettlement, RefundDisbursementPayment
        from cheques.models.cheque import Cheque, ChequeType, ChequeStatus, ChequePurpose
        from cheques.services.accounting_service import ChequeAccountingService
        from financial.services.exchange_rate_service import ExchangeRateService

        # 1. التحقق الاستباقي الصارم من وسيلة الصرف وإيجابية المبلغ المطلوب
        if method not in RefundDisbursementPayment.DisbursementMethod.values:
            raise ValidationError(
                _("وسيلة الصرف '%(m)s' غير مقبولة. الوسائل المعتمدة: نقد، تحويل بنكي، شيك.") % {'m': method}
            )

        idempotency_key = (idempotency_key or '').strip()
        if not idempotency_key:
            raise ValidationError(_("مفتاح منع التكرار (idempotency_key) إلزامي لكافة عمليات الصرف."))

        if requested_amount <= Decimal('0.00'):
            raise ValidationError(_("يجب أن يكون مبلغ الصرف أكبر من الصفر."))

        if payment_date is None:
            payment_date = timezone.localdate()

        # 2. الفحص السريع قبل الأقفال (Pre-Lock Fast Path)
        existing = RefundDisbursementPayment.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            if cls._verify_idempotency_fingerprint(existing, settlement_id, requested_amount, payout_currency, method, payment_account, cheque_data):
                return existing
            raise ValidationError(_("تعارض في مفتاح منع التكرار: المفتاح مستخدم مسبقاً لعملية صرف بمعلمات مختلفة."))

        # 3. حيازة الأقفال بالترتيب الهرمي الصارم (Hierarchical Lock Acquisition)
        with transaction.atomic():
            # المستوى الأول: قفل حساب البنك/الخزينة إن وُجد
            locked_account = None
            if payment_account:
                locked_account = ChartOfAccounts.objects.select_for_update().get(pk=payment_account.pk)
            elif method in [RefundDisbursementPayment.DisbursementMethod.CASH, RefundDisbursementPayment.DisbursementMethod.BANK_TRANSFER]:
                raise ValidationError(_("يجب تحديد حساب الخزينة أو البنك المنصرف منه."))

            # المستوى الثاني: قفل صف التسوية
            try:
                locked_settlement = BookingCancellationSettlement.objects.select_for_update().get(pk=settlement_id)
            except BookingCancellationSettlement.DoesNotExist:
                raise ValidationError(_("قرار تسوية الإلغاء المطلوب غير موجود."))

            # فحص اتساق المؤشر النشط
            if not locked_settlement.is_active or (locked_settlement.booking and locked_settlement.booking.active_cancellation_settlement_id != locked_settlement.id):
                raise ValidationError(_("التسوية المحددة ليست التسوية السارية لهذا الحجز."))

            # 4. إعادة فحص مفتاح التكرار فوراً بعد القفل (Post-Lock Idempotency First)
            existing_locked = RefundDisbursementPayment.objects.filter(idempotency_key=idempotency_key).first()
            if existing_locked:
                if cls._verify_idempotency_fingerprint(existing_locked, settlement_id, requested_amount, payout_currency, method, payment_account, cheque_data):
                    return existing_locked
                raise ValidationError(_("تعارض في مفتاح منع التكرار: المفتاح مستخدم مسبقاً لعملية صرف بمعلمات مختلفة."))

            # 5. حراسة الرصيد الصفري الصارمة للطلبات الجديدة حصراً
            if locked_settlement.remaining_disbursable_amount <= Decimal('0.00'):
                raise ValidationError(
                    _("لا يوجد رصيد متبقٍ متاح للصرف في قرار التسوية (المتبقي: %(rem)s %(curr)s).") % {
                        'rem': locked_settlement.remaining_disbursable_amount,
                        'curr': locked_settlement.currency.code
                    }
                )

            # 6. حل أسعار الصرف الثنائية والحساب بدقة كاملة
            func_curr = ExchangeRateService.get_functional_currency()

            payout_to_func_rate = ExchangeRateService.get_rate(
                from_code=payout_currency.code,
                to_code=func_curr.code,
                date=payment_date
            ) if payout_currency.code != func_curr.code else Decimal('1.000000')

            settlement_to_func_rate = ExchangeRateService.get_rate(
                from_code=locked_settlement.currency.code,
                to_code=func_curr.code,
                date=payment_date
            ) if locked_settlement.currency.code != func_curr.code else Decimal('1.000000')

            # احتساب المعادل بدقة كاملة وتأجيل التقريب
            penny_rounding_diff = Decimal('0.0000')
            if payout_currency.id == locked_settlement.currency_id:
                settlement_currency_equivalent = requested_amount
            else:
                raw_equivalent = (requested_amount * payout_to_func_rate) / settlement_to_func_rate
                prec = Decimal('10') ** -getattr(locked_settlement.currency, 'decimal_places', 2)
                settlement_currency_equivalent = raw_equivalent.quantize(prec, rounding=ROUND_HALF_UP)

                if settlement_currency_equivalent <= Decimal('0.00'):
                    raise ValidationError(_("المعادل بعملة التسوية المحسوب غير صالح (أقل من أو يساوي الصفر)."))

                # الحصر الصارم لسماحية التقريب باشتراط التصفية الكاملة صراحة (is_full_sweep=True)
                tolerance = getattr(locked_settlement.currency, 'rounding_tolerance', Decimal('0.05'))
                diff_from_rem = settlement_currency_equivalent - locked_settlement.remaining_disbursable_amount
                if Decimal('0.00') < diff_from_rem <= tolerance and is_full_sweep:
                    penny_rounding_diff = diff_from_rem
                    settlement_currency_equivalent = locked_settlement.remaining_disbursable_amount

            if settlement_currency_equivalent > locked_settlement.remaining_disbursable_amount:
                raise ValidationError(
                    _("المعادل بعملة التسوية (%(equiv)s %(curr)s) يتجاوز الرصيد المتبقي المتاح للصرف (%(rem)s %(curr)s).") % {
                        'equiv': settlement_currency_equivalent,
                        'rem': locked_settlement.remaining_disbursable_amount,
                        'curr': locked_settlement.currency.code
                    }
                )

            # 7. التفكيك الرياضي المتوازن للانحراف المحاسبي
            functional_payout = (requested_amount * payout_to_func_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            functional_advance_settled = (settlement_currency_equivalent * locked_settlement.exchange_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            total_variance = functional_payout - functional_advance_settled

            rounding_amount_func = Decimal('0.00')
            if penny_rounding_diff > Decimal('0.0000'):
                rounding_amount_func = (penny_rounding_diff * locked_settlement.exchange_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            pure_fx_diff = total_variance - rounding_amount_func

            # 8. التنفيذ المحاسبي والتشغيلي بحسب وسيلة الصرف
            cheque_obj = None
            journal_entry_obj = None
            clearing_entry_obj = None
            payment_status = RefundDisbursementPayment.PaymentStatus.ISSUED

            booking_advance_account = cls.get_or_resolve_account(
                AccountRoleNames.REAL_ESTATE_BOOKING_ADVANCE.value,
                fallback_code="21101"
            )

            # حساب المبلغ والعملة الأجنبية للأمانات المستردة
            advance_foreign_amount = settlement_currency_equivalent if not locked_settlement.currency.is_functional else Decimal('0.00')

            if method == RefundDisbursementPayment.DisbursementMethod.CHEQUE:
                if not cheque_data or not cheque_data.get('cheque_number'):
                    raise ValidationError(_("بيانات الشيك ورقم الشيك إلزامية للصرف بشيك."))

                # أ. إنشاء الشيك بحالة مسودة DRAFT بالحقول الفعلية
                cheque_obj = Cheque.objects.create(
                    cheque_type=ChequeType.PAYABLE,
                    purpose=ChequePurpose.CUSTOMER_REFUND,
                    status=ChequeStatus.DRAFT,
                    customer=locked_settlement.booking.customer,
                    amount=requested_amount,
                    currency=payout_currency,
                    original_exchange_rate=payout_to_func_rate,
                    issue_date=payment_date,
                    due_date=cheque_data.get('due_date', payment_date),
                    cheque_number=str(cheque_data.get('cheque_number')).strip(),
                    drawer_bank_name=cheque_data.get('drawer_bank_name') or (locked_account.name if locked_account else ''),
                    payee_name=cheque_data.get('payee_name') or locked_settlement.booking.customer.name,
                    deposit_bank_account=locked_account,
                    created_by=user,
                )

                # ب. استدعاء حركة الإصدار مع تمرير بيانات الأمانات الأجنبية الكاملة لمطابقة الأستاذ المساعد
                issue_result = ChequeAccountingService.issue_cheque(
                    cheque_or_id=cheque_obj.id,
                    user=user,
                    idempotency_key=f"ISS-REFUND-{idempotency_key}",
                    bank_account_id=locked_account.id if locked_account else None,
                    booking_advance_account_id=booking_advance_account.id,
                    advance_currency_code=locked_settlement.currency.code,
                    advance_exchange_rate=locked_settlement.exchange_rate,
                    advance_foreign_amount=advance_foreign_amount,
                    advance_book_value_functional=functional_advance_settled,
                    pure_fx_diff=pure_fx_diff,
                    rounding_amount_func=rounding_amount_func
                )
                cheque_obj = issue_result["cheque"]
                journal_entry_obj = issue_result.get("journal_entry")
                payment_status = RefundDisbursementPayment.PaymentStatus.ISSUED

            elif method in [RefundDisbursementPayment.DisbursementMethod.CASH, RefundDisbursementPayment.DisbursementMethod.BANK_TRANSFER]:
                # إعداد أسطر القيد المحاسبي المتوازن تماماً
                proj_code = (
                    locked_settlement.booking.unit.project.code
                    if locked_settlement.booking and locked_settlement.booking.unit and locked_settlement.booking.unit.project
                    else None
                )
                lines = [
                    JournalEntryLineData(
                        account_code=booking_advance_account.code,
                        debit=functional_advance_settled,
                        credit=Decimal("0.00"),
                        currency=locked_settlement.currency.code,
                        exchange_rate=locked_settlement.exchange_rate,
                        foreign_debit=advance_foreign_amount,
                        foreign_credit=Decimal("0.00"),
                        description=f"رد جدية حجز - حجز {locked_settlement.booking.booking_number} - تسوية {locked_settlement.settlement_number}",
                        project=proj_code
                    ),
                    JournalEntryLineData(
                        account_code=locked_account.code,
                        debit=Decimal("0.00"),
                        credit=functional_payout,
                        currency=payout_currency.code,
                        exchange_rate=payout_to_func_rate,
                        foreign_debit=Decimal("0.00"),
                        foreign_credit=requested_amount if not payout_currency.is_functional else Decimal('0.00'),
                        description=f"صرف استرداد حجز نقد/بنك - تسوية {locked_settlement.settlement_number}",
                        project=proj_code
                    )
                ]

                if pure_fx_diff > Decimal('0.00'):
                    fx_loss_acc = cls.get_or_resolve_account(AccountRoleNames.FX_REALIZED_LOSS.value, fallback_code="54300")
                    lines.append(JournalEntryLineData(
                        account_code=fx_loss_acc.code,
                        debit=pure_fx_diff,
                        credit=Decimal("0.00"),
                        currency=func_curr.code,
                        exchange_rate=Decimal("1.000000"),
                        description=f"خسائر فروق عملة محققة - تسوية {locked_settlement.settlement_number}"
                    ))
                elif pure_fx_diff < Decimal('0.00'):
                    fx_gain_acc = cls.get_or_resolve_account(AccountRoleNames.FX_REALIZED_GAIN.value, fallback_code="43100")
                    lines.append(JournalEntryLineData(
                        account_code=fx_gain_acc.code,
                        debit=Decimal("0.00"),
                        credit=abs(pure_fx_diff),
                        currency=func_curr.code,
                        exchange_rate=Decimal("1.000000"),
                        description=f"أرباح فروق عملة محققة - تسوية {locked_settlement.settlement_number}"
                    ))

                if rounding_amount_func > Decimal('0.00'):
                    round_acc = cls.get_or_resolve_account(AccountRoleNames.ROUNDING_DIFFERENCE_ACCOUNT.value, fallback_code="54400")
                    lines.append(JournalEntryLineData(
                        account_code=round_acc.code,
                        debit=rounding_amount_func,
                        credit=Decimal("0.00"),
                        currency=func_curr.code,
                        exchange_rate=Decimal("1.000000"),
                        description=f"فروق تقريب كسور العملة عند تصفية الاسترداد - تسوية {locked_settlement.settlement_number}"
                    ))

                gateway = AccountingGateway()
                journal_entry_obj = gateway.create_journal_entry(
                    source_module='real_estate',
                    source_model='BookingCancellationSettlement',
                    source_id=locked_settlement.id,
                    lines=lines,
                    idempotency_key=f"JE:real_estate:BookingCancellationSettlement:{locked_settlement.id}:refund_{idempotency_key}",
                    user=user,
                    entry_type='payment_voucher',
                    description=f"صرف رد حجز {locked_settlement.booking.booking_number} عبر {locked_account.name}",
                    reference=f"REFUND-{locked_settlement.settlement_number}",
                    date=payment_date
                )
                clearing_entry_obj = journal_entry_obj
                payment_status = RefundDisbursementPayment.PaymentStatus.CLEARED

            # 9. إنشاء سجل الصرف
            payment = RefundDisbursementPayment.objects.create(
                idempotency_key=idempotency_key,
                settlement=locked_settlement,
                method=method,
                status=payment_status,
                payment_date=payment_date,
                amount=requested_amount,
                payout_currency=payout_currency,
                payout_exchange_rate=payout_to_func_rate,
                settlement_currency_equivalent=settlement_currency_equivalent,
                functional_amount=functional_payout,
                realized_fx_gain_loss=pure_fx_diff,
                rounding_difference=penny_rounding_diff,
                cheque=cheque_obj,
                payment_account=locked_account,
                journal_entry=journal_entry_obj,
                clearing_journal_entry=clearing_entry_obj,
                processed_by=user
            )

            # 10. تحديث أرصدة وحالة التسوية
            locked_settlement.recalculate_balances()
            locked_settlement.save(update_fields=['committed_amount', 'cleared_amount', 'remaining_disbursable_amount', 'status'])
            return payment

    @classmethod
    def post_contract_execution_cheques(
        cls,
        contract,
        cheques: list,
        user,
        reference: str = ""
    ) -> JournalEntry:
        """
        Event 2: إثبات استلام شيكات أقساط العقد المؤجلة بالخزينة (Contract Execution & Cheque Draw)
        Dr: Undeposited Cheques in Vault (11220 / 11301)
        Cr: Real Estate Contract Liability - Deferred Installments (21102)

        يطبق بروتوكول عزل حساب الضمان (Escrow Isolation Protocol):
        إذا كان للمشروع حساب ضمان escrow_account، تقيد الشيكات بحساب الضمان الخاص بالمشروع.
        """
        if not cheques:
            raise ValidationError(_("يجب تمرير قائمة الشيكات المستلمة الخاصة بالعقد."))

        total_cheques_amount = sum(Decimal(str(c.amount)) for c in cheques)
        if total_cheques_amount <= Decimal("0.00"):
            raise ValidationError(_("إجمالي مبالغ الشيكات يجب أن يكون أكبر من الصفر."))

        # بروتوكول عزل حساب الضمان البنكي للشيكات
        if contract.project and contract.project.escrow_account:
            escrow_acc = contract.project.escrow_account
            for chq in cheques:
                if getattr(chq, 'deposit_bank_account_id', None) != escrow_acc.id:
                    chq.deposit_bank_account = escrow_acc
                    chq.save(update_fields=['deposit_bank_account'])

        vault_cheques_account = cls.get_or_resolve_account(
            AccountRoleNames.NOTES_RECEIVABLE_CONTROL.value,
            fallback_code="11220"
        )
        contract_liability_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_CONTRACT_LIABILITY.value,
            fallback_code="21102"
        )

        curr_code = getattr(contract, 'currency', None)
        currency_str = getattr(curr_code, 'code', 'EGP') if curr_code else 'EGP'
        rate = Decimal(str(getattr(contract, 'exchange_rate', '1.000000') or '1.000000'))
        proj_code = contract.project.code if contract.project else None
        is_foreign = (currency_str != 'EGP')

        if is_foreign and rate > Decimal("0.00"):
            functional_cheques = (total_cheques_amount * rate).quantize(Decimal('0.01'))
            foreign_cheques = total_cheques_amount
        else:
            functional_cheques = total_cheques_amount
            foreign_cheques = Decimal('0.00')

        lines = [
            JournalEntryLineData(
                account_code=vault_cheques_account.code,
                debit=functional_cheques,
                credit=Decimal("0.00"),
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=foreign_cheques if is_foreign else Decimal('0.00'),
                foreign_credit=Decimal("0.00"),
                description=f"استلام حافظة شيكات آجلة ({len(cheques)} شيك) للعقد {contract.contract_number}",
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=contract_liability_account.code,
                debit=Decimal("0.00"),
                credit=functional_cheques,
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=Decimal("0.00"),
                foreign_credit=foreign_cheques if is_foreign else Decimal('0.00'),
                description=f"التزامات تعاقدية مؤجلة مقابل شيكات بالخزينة - العقد {contract.contract_number}",
                project=proj_code
            )
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='PropertyContract',
            object_id=contract.id,
            operation='contract_cheques'
        )

        gateway = AccountingGateway()
        return gateway.create_journal_entry(
            source_module='real_estate',
            source_model='PropertyContract',
            source_id=contract.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='sales_invoice',
            description=f"إثبات شيكات الأقساط المؤجلة للعقد {contract.contract_number}",
            reference=reference or contract.contract_number,
            date=contract.contract_date
        )

    @classmethod
    def post_direct_cash_installment(
        cls,
        contract,
        installment_item,
        amount: Decimal,
        payment_account: ChartOfAccounts,
        user,
        reference: str = "",
        payment_date=None,
        payment_id=None,
        surplus_amount: Decimal = Decimal('0.00')
    ) -> JournalEntry:
        """
        Event 3a: تحصيل قسط نقدي مباشر في حساب الضمان أو الخزينة (Direct Cash Installment)
        مع دعم العملات الأجنبية والتحويل للعملة الوظيفية، وعزل فائض السداد في حساب أمانات مستقل.
        Dr: Bank Escrow Account / Cash Drawer (111xx) [بالمبلغ الوظيفي EGP]
        Cr: Real Estate Contract Liability (21102) [بالمبلغ الوظيفي لأصل القسط]
        Cr: Customer Booking Advances / Overpayment Escrow (21101) [بفائض السداد إن وُجد]
        """
        amount_dec = Decimal(str(amount))
        if amount_dec <= Decimal("0.00"):
            raise ValidationError(_("مبلغ القسط المحصل يجب أن يكون أكبر من الصفر."))

        contract_liability_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_CONTRACT_LIABILITY.value,
            fallback_code="21102"
        )
        booking_advance_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_BOOKING_ADVANCE.value,
            fallback_code="21101"
        )

        curr_code = getattr(contract, 'currency', None)
        currency_str = getattr(curr_code, 'code', 'EGP') if curr_code else 'EGP'
        rate = Decimal(str(getattr(contract, 'exchange_rate', '1.000000') or '1.000000'))
        proj_code = contract.project.code if contract.project else None

        # حساب المبلغ الوظيفي (EGP) والمبلغ الأجنبي
        is_foreign = (currency_str != 'EGP')
        if is_foreign and rate > Decimal("0.00"):
            functional_total = (amount_dec * rate).quantize(Decimal('0.01'))
            foreign_total = amount_dec
        else:
            functional_total = amount_dec
            foreign_total = Decimal('0.00')

        surplus_dec = Decimal(str(surplus_amount or '0.00'))
        allocated_principal = amount_dec - surplus_dec
        if allocated_principal < Decimal('0.00'):
            allocated_principal = amount_dec
            surplus_dec = Decimal('0.00')

        if is_foreign and rate > Decimal("0.00"):
            functional_allocated = (allocated_principal * rate).quantize(Decimal('0.01'))
            functional_surplus = functional_total - functional_allocated
            foreign_allocated = allocated_principal
            foreign_surplus = surplus_dec
        else:
            functional_allocated = allocated_principal
            functional_surplus = surplus_dec
            foreign_allocated = Decimal('0.00')
            foreign_surplus = Decimal('0.00')

        lines = [
            JournalEntryLineData(
                account_code=payment_account.code,
                debit=functional_total,
                credit=Decimal("0.00"),
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=foreign_total if is_foreign else Decimal('0.00'),
                foreign_credit=Decimal("0.00"),
                description=f"تحصيل نقدي مباشر للقسط {installment_item.installment_number} - العقد {contract.contract_number}",
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=contract_liability_account.code,
                debit=Decimal("0.00"),
                credit=functional_allocated,
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=Decimal("0.00"),
                foreign_credit=foreign_allocated if is_foreign else Decimal('0.00'),
                description=f"سداد التزام تعاقدي نقدي - قسط {installment_item.installment_number} العقد {contract.contract_number}",
                project=proj_code
            )
        ]

        if surplus_dec > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=booking_advance_account.code,
                    debit=Decimal("0.00"),
                    credit=functional_surplus,
                    currency=currency_str,
                    exchange_rate=rate,
                    foreign_debit=Decimal("0.00"),
                    foreign_credit=foreign_surplus if is_foreign else Decimal('0.00'),
                    description=f"أمانات وفائض سداد معزول للقسط الأخير - العقد {contract.contract_number}",
                    project=proj_code
                )
            )

        # مفتاح فريد وثابت لطلب التحصيل لمنع الازدواج
        op_suffix = f"_{reference}" if reference else (f"_{payment_id}" if payment_id else "")
        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='PropertyContract',
            object_id=contract.id,
            operation=f"cash_installment_{installment_item.id}{op_suffix}"
        )

        gateway = AccountingGateway()
        return gateway.create_journal_entry(
            source_module='real_estate',
            source_model='PropertyContract',
            source_id=contract.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='receipt_voucher',
            description=f"تحصيل القسط {installment_item.installment_number} للعقد {contract.contract_number}",
            reference=reference or f"INST-{installment_item.id}",
            date=payment_date or timezone.localdate()
        )

    @classmethod
    def post_cheque_replacement_cash(
        cls,
        contract,
        cheque,
        amount: Decimal,
        payment_account: ChartOfAccounts,
        user,
        reference: str = ""
    ) -> JournalEntry:
        """
        Event 3c: استبدال شيك نقداً (Cheque Replacement by Cash - Anti-Duplication Rule)
        Dr: Bank Escrow / Cash Drawer (111xx)
        Cr: Undeposited Cheques in Vault (11220 / 11301)

        قاعدة منع الازدواج الصارمة (Anti-Duplication Rule):
        بما أن التزامات العقد 21102 تم إثباتها بالفعل عند استلام الشيك (Event 2)،
        فإن استبدال الشيك بنقدية يُلغي الأصل الورقي (تخفيض شيكات بالخزينة 11220)
        ولا يجوز إطلاقاً إعادة إضافة دائنية جديدة لحساب التزامات العقد 21102 منعاً لتضخيم الالتزامات!
        """
        amount_dec = Decimal(str(amount))
        if amount_dec <= Decimal("0.00"):
            raise ValidationError(_("مبلغ الاستبدال النقدي يجب أن يكون أكبر من الصفر."))

        vault_cheques_account = cls.get_or_resolve_account(
            AccountRoleNames.NOTES_RECEIVABLE_CONTROL.value,
            fallback_code="11220"
        )

        curr_code = getattr(cheque, 'currency', None) or getattr(contract, 'currency', None)
        currency_str = getattr(curr_code, 'code', 'EGP') if curr_code else 'EGP'
        rate = Decimal(str(getattr(contract, 'exchange_rate', '1.000000') or '1.000000'))
        proj_code = contract.project.code if contract.project else None
        is_foreign = (currency_str != 'EGP')

        if is_foreign and rate > Decimal("0.00"):
            functional_amount = (amount_dec * rate).quantize(Decimal('0.01'))
            foreign_amount = amount_dec
        else:
            functional_amount = amount_dec
            foreign_amount = Decimal('0.00')

        lines = [
            JournalEntryLineData(
                account_code=payment_account.code,
                debit=functional_amount,
                credit=Decimal("0.00"),
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=foreign_amount if is_foreign else Decimal('0.00'),
                foreign_credit=Decimal("0.00"),
                description=f"تحصيل نقدي بدل استرداد شيك ورقي رقم {cheque.cheque_number} - العقد {contract.contract_number}",
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=vault_cheques_account.code,
                debit=Decimal("0.00"),
                credit=functional_amount,
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=Decimal("0.00"),
                foreign_credit=foreign_amount if is_foreign else Decimal('0.00'),
                description=f"إلغاء وخروج الشيك الورقي {cheque.cheque_number} من الخزينة مقابل السداد النقدي",
                project=proj_code
            )
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='PropertyContract',
            object_id=contract.id,
            operation=f"cheque_replace_{cheque.id}"
        )

        gateway = AccountingGateway()
        return gateway.create_journal_entry(
            source_module='real_estate',
            source_model='PropertyContract',
            source_id=contract.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='receipt_voucher',
            description=f"استبدال نقدي للشيك {cheque.cheque_number} للعقد {contract.contract_number}",
            reference=reference or f"REPL-CHQ-{cheque.id}",
            date=timezone.localdate()
        )

    @classmethod
    def post_revenue_recognition(
        cls,
        contract,
        amount: Decimal,
        user,
        is_handover: bool = False,
        poc_percentage: Optional[Decimal] = None,
        reference: str = ""
    ) -> JournalEntry:
        """
        Event 4: الاعتراف بالإيراد وفق معيار IFRS 15 (Revenue Recognition Gate)
        Dr: Real Estate Contract Liability (21102)
        Cr: Realized Real Estate Revenue (41101)

        بوابة التقييم المحاسبي لمعيار IFRS 15:
        1. Point in Time (POINT_IN_TIME): يستلزم التسليم الفعلي أو الحكمي للوحدة (Handover Protocol).
        2. Over Time (OVER_TIME): يستلزم نسبة إنجاز معتمدة بمستخلص فني (Percentage of Completion).
        """
        amount_dec = Decimal(str(amount))
        if amount_dec <= Decimal("0.00"):
            raise ValidationError(_("مبلغ الإيراد المعترف به يجب أن يكون أكبر من الصفر."))

        # التحقق من بوابة IFRS 15
        if contract.revenue_recognition_method == contract.RevenueMethod.POINT_IN_TIME:
            has_executed_receipt = hasattr(contract, 'handover_receipts') and contract.handover_receipts.filter(
                status='EXECUTED'
            ).exists()
            is_unit_delivered = contract.unit.status in [
                contract.unit.UnitStatus.DELIVERED,
                contract.unit.UnitStatus.DELIVERED_DEEMED
            ]
            if not (is_handover or (has_executed_receipt and is_unit_delivered)):
                raise ValidationError(
                    _("لا يجوز الاعتراف بالإيراد لطريقة (Point in Time) إلا عند التسليم الفعلي أو الحكمي للوحدة بموجب محضر تسليم معتمد.")
                )
            op_tag = f"handover_{reference or 'final'}"
        else:
            if poc_percentage is None or poc_percentage <= Decimal("0.00") or poc_percentage > Decimal("100.00"):
                raise ValidationError(
                    _("طريقة نسبة الإنجاز (Over Time) تتطلب تحديد نسبة إنجاز معتمدة بين 0% و 100%.")
                )
            prior_rec_tag = getattr(contract, 'recognized_revenue_amount', Decimal('0.00')) or Decimal('0.00')
            op_tag = f"poc_{poc_percentage}_from_{prior_rec_tag}_amt_{amount_dec}"

        contract_liability_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_CONTRACT_LIABILITY.value,
            fallback_code="21102"
        )
        realized_revenue_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_REVENUE.value,
            fallback_code="41101"
        )

        curr_code = getattr(contract, 'currency', None)
        currency_str = getattr(curr_code, 'code', 'EGP') if curr_code else 'EGP'
        rate = Decimal(str(getattr(contract, 'exchange_rate', '1.000000') or '1.000000'))
        proj_code = contract.project.code if contract.project else None
        is_foreign = (currency_str != 'EGP')

        if is_foreign and rate > Decimal("0.00"):
            functional_amount = (amount_dec * rate).quantize(Decimal('0.01'))
            foreign_amount = amount_dec
        else:
            functional_amount = amount_dec
            foreign_amount = Decimal('0.00')

        lines = [
            JournalEntryLineData(
                account_code=contract_liability_account.code,
                debit=functional_amount,
                credit=Decimal("0.00"),
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=foreign_amount if is_foreign else Decimal('0.00'),
                foreign_credit=Decimal("0.00"),
                description=f"تسوية التزامات العقد وتحويلها لإيراد محقق - العقد {contract.contract_number}",
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=realized_revenue_account.code,
                debit=Decimal("0.00"),
                credit=functional_amount,
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=Decimal("0.00"),
                foreign_credit=foreign_amount if is_foreign else Decimal('0.00'),
                description=f"إيراد بيع عقاري محقق وفق IFRS 15 ({contract.revenue_recognition_method}) - العقد {contract.contract_number}",
                project=proj_code
            )
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='PropertyContract',
            object_id=contract.id,
            operation=f"rev_rec_{op_tag}"
        )

        gateway = AccountingGateway()
        return gateway.create_journal_entry(
            source_module='real_estate',
            source_model='PropertyContract',
            source_id=contract.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='sales_invoice',
            description=f"الاعتراف بإيراد العقد العقاري {contract.contract_number}",
            reference=reference or f"REV-REC-{contract.contract_number}",
            date=timezone.localdate()
        )

    @classmethod
    def post_contract_cancellation(
        cls,
        contract,
        penalty_amount: Decimal,
        refund_amount: Decimal,
        uncashed_cheques_amount: Decimal,
        refund_account: Optional[ChartOfAccounts] = None,
        forfeited_pending_resale: Decimal = Decimal("0.00"),
        user = None,
        reference: str = ""
    ) -> JournalEntry:
        """
        Event 5: فسخ وإلغاء العقد العقاري (Contract Rescission & Cancellation)
        Dr: Real Estate Contract Liability (21102) [بإجمالي الالتزام الملغى بالكامل]
        Cr: Undeposited Cheques in Vault (11220) [بمبلغ الشيكات غير المحصلة المعاد تسليمها للعميل]
        Cr: Penalty Income / Forfeited Fee (42201) [بمبلغ الغرامة الإدارية المحتجزة لصالح الشركة]
        Cr: Bank / Cash (111xx) [بمبلغ المسترد الفعلي للعميل بشيك أو تحويل]
        Cr: Forfeited Contract Balances Pending Resale (21701) [بالمبالغ المحتجزة المعلقة لحين إعادة بيع الوحدة]
        """
        penalty_dec = Decimal(str(penalty_amount or Decimal("0.00")))
        refund_dec = Decimal(str(refund_amount or Decimal("0.00")))
        uncashed_dec = Decimal(str(uncashed_cheques_amount or Decimal("0.00")))
        forfeited_dec = Decimal(str(forfeited_pending_resale or Decimal("0.00")))

        total_liability_cleared = penalty_dec + refund_dec + uncashed_dec + forfeited_dec
        if total_liability_cleared <= Decimal("0.00"):
            raise ValidationError(_("إجمالي مبالغ تسوية الفسخ يجب أن يكون أكبر من الصفر."))

        if refund_dec > Decimal("0.00") and not refund_account:
            raise ValidationError(_("يجب تحديد حساب بنكي أو خزينة لصرف المبلغ المسترد للعميل."))

        contract_liability_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_CONTRACT_LIABILITY.value,
            fallback_code="21102"
        )
        vault_cheques_account = cls.get_or_resolve_account(
            AccountRoleNames.NOTES_RECEIVABLE_CONTROL.value,
            fallback_code="11220"
        )
        penalty_income_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_FORFEITED_INCOME.value,
            fallback_code="42201"
        )
        forfeited_balances_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_FORFEITED_BALANCES.value,
            fallback_code="21701"
        )

        curr_code = getattr(contract, 'currency', None)
        currency_str = getattr(curr_code, 'code', 'EGP') if curr_code else 'EGP'
        rate = Decimal(str(getattr(contract, 'exchange_rate', '1.000000') or '1.000000'))
        proj_code = contract.project.code if contract.project else None
        is_foreign = (currency_str != 'EGP')

        def to_functional(val):
            if is_foreign and rate > Decimal("0.00"):
                return (val * rate).quantize(Decimal('0.01'))
            return val

        func_penalty = to_functional(penalty_dec)
        func_refund = to_functional(refund_dec)
        func_uncashed = to_functional(uncashed_dec)
        func_forfeited = to_functional(forfeited_dec)
        func_total = func_penalty + func_refund + func_uncashed + func_forfeited

        lines = [
            JournalEntryLineData(
                account_code=contract_liability_account.code,
                debit=func_total,
                credit=Decimal("0.00"),
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=total_liability_cleared if is_foreign else Decimal('0.00'),
                foreign_credit=Decimal("0.00"),
                description=f"إلغاء وتصفية التزامات العقد العقاري المفسوخ {contract.contract_number}",
                project=proj_code
            )
        ]

        if uncashed_dec > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=vault_cheques_account.code,
                    debit=Decimal("0.00"),
                    credit=func_uncashed,
                    currency=currency_str,
                    exchange_rate=rate,
                    foreign_debit=Decimal("0.00"),
                    foreign_credit=uncashed_dec if is_foreign else Decimal('0.00'),
                    description=f"رد وإلغاء شيكات آجلة غير محصلة بالخزينة للعقد {contract.contract_number}",
                    project=proj_code
                )
            )

        if penalty_dec > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=penalty_income_account.code,
                    debit=Decimal("0.00"),
                    credit=func_penalty,
                    currency=currency_str,
                    exchange_rate=rate,
                    foreign_debit=Decimal("0.00"),
                    foreign_credit=penalty_dec if is_foreign else Decimal('0.00'),
                    description=f"إثبات إيرادات غرامات ومصاريف إدارية ناتجة عن فسخ العقد {contract.contract_number}",
                    project=proj_code
                )
            )

        if refund_dec > Decimal("0.00") and refund_account:
            lines.append(
                JournalEntryLineData(
                    account_code=refund_account.code,
                    debit=Decimal("0.00"),
                    credit=func_refund,
                    currency=currency_str,
                    exchange_rate=rate,
                    foreign_debit=Decimal("0.00"),
                    foreign_credit=refund_dec if is_foreign else Decimal('0.00'),
                    description=f"صرف المبلغ المسترد للعميل {contract.customer.name} بعد فسخ العقد {contract.contract_number}",
                    project=proj_code
                )
            )

        if forfeited_dec > Decimal("0.00"):
            lines.append(
                JournalEntryLineData(
                    account_code=forfeited_balances_account.code,
                    debit=Decimal("0.00"),
                    credit=func_forfeited,
                    currency=currency_str,
                    exchange_rate=rate,
                    foreign_debit=Decimal("0.00"),
                    foreign_credit=forfeited_dec if is_foreign else Decimal('0.00'),
                    description=f"أمانات محتجزة معلقة لحين إعادة بيع الوحدة للعقد {contract.contract_number}",
                    project=proj_code
                )
            )

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='PropertyContract',
            object_id=contract.id,
            operation='cancellation'
        )

        gateway = AccountingGateway()
        cancel_entry = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='PropertyContract',
            source_id=contract.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='sales_return',
            description=f"تصفية وإلغاء قيود العقد العقاري المفسوخ {contract.contract_number}",
            reference=reference or f"CAN-{contract.contract_number}",
            date=timezone.localdate()
        )

        # استرداد عمولات الوسطاء آلياً (Commission Clawback) إن وُجدت
        from real_estate.services.broker_service import BrokerCommissionService
        BrokerCommissionService.execute_commission_clawback(
            contract=contract,
            reason=f"فسخ العقد العقاري {contract.contract_number}",
            user=user
        )

        return cancel_entry

    @classmethod
    def post_handover_interim_cogs(
        cls,
        receipt,
        cogs_amount: Decimal,
        user=None,
        reference: str = ""
    ) -> JournalEntry:
        """
        Event 4b: إثبات تكلفة المبيعات المقدرة عند تسليم الوحدة (Interim COGS Allocation)
        Dr: Cost of Real Estate Sold (COGS_EXPENSE / 51100)
        Cr: Work in Progress / Project Asset (REAL_ESTATE_WIP_CONSTRUCTION / 12101)
        """
        amount_dec = Decimal(str(cogs_amount))
        if amount_dec <= Decimal("0.00"):
            raise ValidationError(_("مبلغ تكلفة مبيعات الوحدة المقدرة يجب أن يكون أكبر من الصفر."))

        cogs_account = cls.get_or_resolve_account(
            AccountRoleNames.COGS_EXPENSE.value,
            fallback_code="51100"
        )
        wip_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_WIP_CONSTRUCTION.value,
            fallback_code="12101"
        )

        contract = receipt.contract
        unit = receipt.unit
        project = contract.project if contract else getattr(unit, 'project', None)
        proj_code = project.code if project else None

        curr_code = getattr(contract, 'currency', None)
        currency_str = getattr(curr_code, 'code', 'EGP') if curr_code else 'EGP'

        lines = [
            JournalEntryLineData(
                account_code=cogs_account.code,
                debit=amount_dec,
                credit=Decimal("0.00"),
                currency=currency_str,
                description=f"تكلفة مبيعات تقديرية لتسليم الوحدة {unit.unit_code} - محضر {receipt.receipt_number}",
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=wip_account.code,
                debit=Decimal("0.00"),
                credit=amount_dec,
                currency=currency_str,
                description=f"تخفيض مشروعات تحت التنفيذ بتسليم الوحدة {unit.unit_code} - مشروع {proj_code}",
                project=proj_code
            )
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='PropertyHandoverReceipt',
            object_id=receipt.id,
            operation='interim_cogs'
        )

        gateway = AccountingGateway()
        return gateway.create_journal_entry(
            source_module='real_estate',
            source_model='PropertyHandoverReceipt',
            source_id=receipt.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='inventory_operation',
            description=f"إثبات تكلفة مبيعات تسليم الوحدة {unit.unit_code}",
            reference=reference or f"COGS-{receipt.receipt_number}",
            date=timezone.localdate()
        )

    @classmethod
    def post_project_cost_true_up(
        cls,
        project,
        variance_amount: Decimal,
        user=None,
        reference: str = ""
    ) -> Optional[JournalEntry]:
        """
        Event 4c: تسوية فروق التكلفة الختامية للمشروع (Project Completion Cost True-Up)
        Variance = Actual Total WIP Incurred - Sum(Recognized Interim COGS)
        - إذا كان هناك عجز/تجاوز تكلفة (variance > 0):
          Dr: Cost of Real Estate Sold (COGS_EXPENSE / 51100)
          Cr: Work in Progress (REAL_ESTATE_WIP_CONSTRUCTION / 12101)
        - إذا كان هناك وفر/توفير (variance < 0):
          Dr: Work in Progress (REAL_ESTATE_WIP_CONSTRUCTION / 12101)
          Cr: Cost of Real Estate Sold (COGS_EXPENSE / 51100)
        """
        variance_dec = Decimal(str(variance_amount))
        if variance_dec == Decimal("0.00"):
            return None

        cogs_account = cls.get_or_resolve_account(
            AccountRoleNames.COGS_EXPENSE.value,
            fallback_code="51100"
        )
        wip_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_WIP_CONSTRUCTION.value,
            fallback_code="12101"
        )

        proj_code = project.code
        currency_str = 'EGP'
        abs_variance = abs(variance_dec)

        if variance_dec > Decimal("0.00"):
            # تجاوز تكلفة: زيادة في تكلفة المبيعات وتخفيض الـ WIP
            lines = [
                JournalEntryLineData(
                    account_code=cogs_account.code,
                    debit=abs_variance,
                    credit=Decimal("0.00"),
                    currency=currency_str,
                    description=f"تسوية ختامية - زيادة تكاليف فعلية عن التقديري للمشروع {project.name}",
                    project=proj_code
                ),
                JournalEntryLineData(
                    account_code=wip_account.code,
                    debit=Decimal("0.00"),
                    credit=abs_variance,
                    currency=currency_str,
                    description=f"إقفال رصيد مشروعات تحت التنفيذ للمشروع المكتمل {project.name}",
                    project=proj_code
                )
            ]
        else:
            # وفر في التكاليف: تخفيض تكلفة المبيعات وزيادة رصيد الـ WIP للتسوية
            lines = [
                JournalEntryLineData(
                    account_code=wip_account.code,
                    debit=abs_variance,
                    credit=Decimal("0.00"),
                    currency=currency_str,
                    description=f"تسوية ختامية - وفر في تكاليف الإنشاء للمشروع {project.name}",
                    project=proj_code
                ),
                JournalEntryLineData(
                    account_code=cogs_account.code,
                    debit=Decimal("0.00"),
                    credit=abs_variance,
                    currency=currency_str,
                    description=f"تسوية وفر التكاليف لصالح تكلفة المبيعات للمشروع {project.name}",
                    project=proj_code
                )
            ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='RealEstateProject',
            object_id=project.id,
            operation='cost_true_up'
        )

        gateway = AccountingGateway()
        return gateway.create_journal_entry(
            source_module='real_estate',
            source_model='RealEstateProject',
            source_id=project.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='closing_entry',
            description=f"تسوية فروق التكلفة الختامية لمشروع {project.name}",
            reference=reference or f"TRUEUP-{project.code}",
            date=timezone.localdate()
        )

    @classmethod
    def post_unit_swap_administrative_fee(
        cls,
        swap_record,
        payment_account: ChartOfAccounts,
        user,
        reference: str = ""
    ) -> Optional[JournalEntry]:
        """
        إثبات تحصيل رسوم الاستبدال الإدارية (Unit Swap Administrative Fee):
        Dr: Cash / Bank (111xx)
        Cr: Other Income / Administrative Fees (42202 / 42200)
        """
        fee_amount = Decimal(str(swap_record.administrative_fee or Decimal("0.00")))
        if fee_amount <= Decimal("0.00"):
            return None

        fee_income_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_TRANSFER_FEE_INCOME.value,
            fallback_code="42202"
        )

        contract = swap_record.contract
        curr_code = getattr(contract, 'currency', None)
        currency_str = getattr(curr_code, 'code', 'EGP') if curr_code else 'EGP'
        rate = Decimal(str(getattr(contract, 'exchange_rate', '1.000000') or '1.000000'))
        project = getattr(swap_record.new_unit, 'project', None)
        proj_code = project.code if project else None
        is_foreign = (currency_str != 'EGP')

        if is_foreign and rate > Decimal("0.00"):
            functional_fee = (fee_amount * rate).quantize(Decimal('0.01'))
            foreign_fee = fee_amount
        else:
            functional_fee = fee_amount
            foreign_fee = Decimal('0.00')

        lines = [
            JournalEntryLineData(
                account_code=payment_account.code,
                debit=functional_fee,
                credit=Decimal("0.00"),
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=foreign_fee if is_foreign else Decimal('0.00'),
                foreign_credit=Decimal("0.00"),
                description=f"تحصيل رسوم استبدال الوحدة {swap_record.old_unit.unit_code} بالوحدة {swap_record.new_unit.unit_code} - محضر {swap_record.swap_number}",
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=fee_income_account.code,
                debit=Decimal("0.00"),
                credit=functional_fee,
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=Decimal("0.00"),
                foreign_credit=foreign_fee if is_foreign else Decimal('0.00'),
                description=f"إيرادات إدارية - رسوم استبدال وحدة العميل {swap_record.customer.name}",
                project=proj_code
            ),
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='UnitSwapRecord',
            object_id=swap_record.id,
            operation='admin_fee'
        )

        gateway = AccountingGateway()
        return gateway.create_journal_entry(
            source_module='real_estate',
            source_model='UnitSwapRecord',
            source_id=swap_record.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='transaction',
            description=f"إثبات رسوم استبدال الوحدة {swap_record.old_unit.unit_code} بالوحدة {swap_record.new_unit.unit_code}",
            reference=reference or swap_record.swap_number,
            date=swap_record.swap_date or timezone.localdate()
        )

    @classmethod
    def post_contract_assignment_subledger_transfer(
        cls,
        endorsement,
        user,
        reference: str = ""
    ) -> Optional[JournalEntry]:
        """
        نقل التزام العقد العقاري للمتنازل إليه في دفتر الأستاذ المساعد:
        Dr: Contract Liabilities 21102 (Partner: Assignor)
        Cr: Contract Liabilities 21102 (Partner: Assignee)
        """
        paid_amount = Decimal(str(endorsement.paid_amount_at_assignment or Decimal("0.00")))
        if paid_amount <= Decimal("0.00"):
            return None

        liability_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_CONTRACT_LIABILITY.value,
            fallback_code="21102"
        )

        contract = endorsement.contract
        curr_code = getattr(contract, 'currency', None)
        currency_str = getattr(curr_code, 'code', 'EGP') if curr_code else 'EGP'
        rate = Decimal(str(getattr(contract, 'exchange_rate', '1.000000') or '1.000000'))
        project = getattr(contract, 'project', None)
        proj_code = project.code if project else None
        is_foreign = (currency_str != 'EGP')

        if is_foreign and rate > Decimal("0.00"):
            functional_paid = (paid_amount * rate).quantize(Decimal('0.01'))
            foreign_paid = paid_amount
        else:
            functional_paid = paid_amount
            foreign_paid = Decimal('0.00')

        lines = [
            JournalEntryLineData(
                account_code=liability_account.code,
                debit=functional_paid,
                credit=Decimal("0.00"),
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=foreign_paid if is_foreign else Decimal('0.00'),
                foreign_credit=Decimal("0.00"),
                description=f"نقل التزام تعاقدي للمتنازل إليه - العميل المتنازل: {endorsement.assignor_customer.name}",
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=liability_account.code,
                debit=Decimal("0.00"),
                credit=functional_paid,
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=Decimal("0.00"),
                foreign_credit=foreign_paid if is_foreign else Decimal('0.00'),
                description=f"إثبات التزام تعاقدي منقول للمتنازل إليه: {endorsement.assignee_customer.name}",
                project=proj_code
            ),
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='ContractAssignmentEndorsement',
            object_id=endorsement.id,
            operation='subledger_transfer'
        )

        gateway = AccountingGateway()
        return gateway.create_journal_entry(
            source_module='real_estate',
            source_model='ContractAssignmentEndorsement',
            source_id=endorsement.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='transaction',
            description=f"نقل التزام تعاقدي - تنازل عن العقد {contract.contract_number} من {endorsement.assignor_customer.name} إلى {endorsement.assignee_customer.name}",
            reference=reference or endorsement.assignment_number,
            date=endorsement.assignment_date or timezone.localdate()
        )

    @classmethod
    def post_contract_assignment_administrative_fee(
        cls,
        endorsement,
        payment_account: ChartOfAccounts,
        user,
        reference: str = ""
    ) -> Optional[JournalEntry]:
        """
        إثبات تحصيل رسوم التنازل الإدارية (Contract Assignment Fee):
        Dr: Cash / Bank (111xx)
        Cr: Other Income / Administrative Fees (42202 / 42200)
        """
        fee_amount = Decimal(str(endorsement.administrative_fee or Decimal("0.00")))
        if fee_amount <= Decimal("0.00"):
            return None

        fee_income_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_TRANSFER_FEE_INCOME.value,
            fallback_code="42202"
        )

        contract = endorsement.contract
        curr_code = getattr(contract, 'currency', None)
        currency_str = getattr(curr_code, 'code', 'EGP') if curr_code else 'EGP'
        rate = Decimal(str(getattr(contract, 'exchange_rate', '1.000000') or '1.000000'))
        project = getattr(contract, 'project', None)
        proj_code = project.code if project else None
        is_foreign = (currency_str != 'EGP')

        if is_foreign and rate > Decimal("0.00"):
            functional_fee = (fee_amount * rate).quantize(Decimal('0.01'))
            foreign_fee = fee_amount
        else:
            functional_fee = fee_amount
            foreign_fee = Decimal('0.00')

        lines = [
            JournalEntryLineData(
                account_code=payment_account.code,
                debit=functional_fee,
                credit=Decimal("0.00"),
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=foreign_fee if is_foreign else Decimal('0.00'),
                foreign_credit=Decimal("0.00"),
                description=f"تحصيل رسوم التنازل عن العقد {contract.contract_number} - ملحق {endorsement.assignment_number}",
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=fee_income_account.code,
                debit=Decimal("0.00"),
                credit=functional_fee,
                currency=currency_str,
                exchange_rate=rate,
                foreign_debit=Decimal("0.00"),
                foreign_credit=foreign_fee if is_foreign else Decimal('0.00'),
                description=f"إيرادات إدارية - رسوم تنازل الوحدة {contract.unit.unit_code} للعميل {endorsement.assignee_customer.name}",
                project=proj_code
            ),
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='ContractAssignmentEndorsement',
            object_id=endorsement.id,
            operation='admin_fee'
        )

        gateway = AccountingGateway()
        return gateway.create_journal_entry(
            source_module='real_estate',
            source_model='ContractAssignmentEndorsement',
            source_id=endorsement.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='transaction',
            description=f"إثبات رسوم التنازل الإدارية للعقد {contract.contract_number} - ملحق {endorsement.assignment_number}",
            reference=reference or endorsement.assignment_number,
            date=endorsement.assignment_date or timezone.localdate()
        )

    @classmethod
    def post_infrastructure_cost_apportionment(
        cls,
        apportionment,
        user,
        reference: str = ""
    ) -> JournalEntry:
        """
        توزيع تكاليف البنية التحتية المركزية المشتركة على المشروعات المستفيدة:
        Dr: Real Estate WIP Construction (12101) - لكل مشروع مستفيد بحصته
        Cr: Infrastructure Asset Account (12390 / 12101) - بإجمالي المبلغ الموزع
        """
        total_amount = Decimal(str(apportionment.total_apportioned_amount or Decimal("0.00")))
        if total_amount <= Decimal("0.00"):
            raise ValidationError(_("إجمالي المبلغ المراد توزيعه يجب أن يكون أكبر من الصفر."))

        wip_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_WIP_CONSTRUCTION.value,
            fallback_code="12101"
        )
        infra_asset_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_INFRASTRUCTURE_ASSET.value,
            fallback_code="12390"
        )

        lines = []
        for line in apportionment.lines.all():
            proj_code = line.beneficiary_project.code if line.beneficiary_project else None
            lines.append(
                JournalEntryLineData(
                    account_code=wip_account.code,
                    debit=line.allocated_amount,
                    credit=Decimal("0.00"),
                    currency="EGP",
                    description=f"تحميل حصة إنشاءات البنية التحتية ({apportionment.infrastructure_asset.name}) للمشروع {line.beneficiary_project.name}",
                    project=proj_code
                )
            )

        # سطر دائن بإجمالي تكلفة البنية التحتية المنقولة
        lines.append(
            JournalEntryLineData(
                account_code=infra_asset_account.code,
                debit=Decimal("0.00"),
                credit=total_amount,
                currency="EGP",
                description=f"توزيع وتخفيض تكاليف محطة {apportionment.infrastructure_asset.name} الدفترية",
                project=None
            )
        )

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='SharedInfrastructureApportionment',
            object_id=apportionment.id,
            operation='apportionment'
        )

        gateway = AccountingGateway()
        return gateway.create_journal_entry(
            source_module='real_estate',
            source_model='SharedInfrastructureApportionment',
            source_id=apportionment.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='transaction',
            description=f"توزيع تكاليف البنية التحتية المركزية ({apportionment.infrastructure_asset.name})",
            reference=reference or apportionment.apportionment_number,
            date=apportionment.apportionment_date or timezone.localdate()
        )

    @classmethod
    def post_resale_contingent_refund_disbursement(
        cls,
        refund_record,
        payment_account: ChartOfAccounts,
        user,
        reference: str = ""
    ) -> JournalEntry:
        """
        صرف مستحقات العميل المفسوخ عقده بعد إعادة طرح الوحدة وتوافر السيولة من المشتري الجديد:
        Dr: Forfeited Contract Balances Payable (21701)
        Cr: Cash / Bank (111xx)
        """
        amount = Decimal(str(refund_record.net_refundable_amount or Decimal("0.00")))
        if amount <= Decimal("0.00"):
            raise ValidationError(_("مبلغ المستحقات المصرح بصرفه يجب أن يكون أكبر من الصفر."))

        liability_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_FORFEITED_BALANCES.value,
            fallback_code="21701"
        )

        unit = refund_record.unit
        proj_code = unit.project.code if unit and unit.project else None

        lines = [
            JournalEntryLineData(
                account_code=liability_account.code,
                debit=amount,
                credit=Decimal("0.00"),
                currency="EGP",
                description=f"صرف مستحقات عميل عقد مفسوخ بعد إعادة البيع - العميل: {refund_record.customer.name}",
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=payment_account.code,
                debit=Decimal("0.00"),
                credit=amount,
                currency="EGP",
                description=f"سداد مستحقات فسخ الوحدة {unit.unit_code} للعميل {refund_record.customer.name}",
                project=proj_code
            ),
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='ResaleContingentRefund',
            object_id=refund_record.id,
            operation='disbursement'
        )

        gateway = AccountingGateway()
        return gateway.create_journal_entry(
            source_module='real_estate',
            source_model='ResaleContingentRefund',
            source_id=refund_record.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='transaction',
            description=f"صرف مستحقات فسخ وإعادة بيع الوحدة {unit.unit_code}",
            reference=reference or refund_record.refund_number,
            date=timezone.localdate()
        )
