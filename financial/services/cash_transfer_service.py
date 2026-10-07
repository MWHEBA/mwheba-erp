# -*- coding: utf-8 -*-
"""
FIN-CORE-025: Central CashTransferService
خدمة تحويل الأموال والرقابة المركزية بين الخزائن النقدية والحسابات البنكية وصناديق العهد
مع الحوكمة الكاملة للعملات المتعددة، التحويل المباشر والمرحلي (In-Transit)،
تصفية فروق العملة المحققة (Realized FX Gain/Loss)، فروق التقريب (Penny Diff 54400)،
وفصل وتوجيه ضريبة القيمة المضافة على المصاريف البنكية (11350 و 52200).
"""
import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from typing import Dict, Any, Optional, Union, List, Tuple
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from financial.models.cash_transfer import CashTransfer, TransferType, TransferStatus
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.currency import Currency
from financial.services.exchange_rate_service import ExchangeRateService
from financial.services.period_control_service import PeriodControlService
from financial.services.role_registry import AccountRoleRegistry
from financial.services.treasury_security_service import TreasurySecurityService
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData
from utils.arabic_numbers import amount_to_arabic_words

logger = logging.getLogger("financial.services.cash_transfer_service")

# حد فروق التقريب المسموح به للتوجيه لحساب 54400 (<= 0.05 EGP)
PENNY_DIFFERENCE_THRESHOLD = Decimal("0.05")
# نسبة ضريبة القيمة المضافة القياسية على المصاريف البنكية
STANDARD_VAT_RATE = Decimal("14.00")


class CashTransferService:
    """
    الخدمة المركزية لإدارة وتنفيذ سندات التحويل المالي متعددة العملات
    """

    @classmethod
    def calculate_transfer_preview(
        cls,
        from_account: Union[ChartOfAccounts, int],
        to_account: Union[ChartOfAccounts, int],
        source_amount: Decimal,
        exchange_rate: Optional[Decimal] = None,
        bank_fee: Decimal = Decimal("0.00"),
        vat_on_fee: Decimal = Decimal("0.00"),
        transfer_type: str = TransferType.DIRECT,
        transfer_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        حساب محاكاة فورية (Live Preview) لعملية التحويل المالي:
        - مبالغ العملة المحلية والأجنبية وأسعار الصرف
        - فروق أسعار الصرف المحققة (FX Gain/Loss) وفروق التقريب (Penny Diff)
        - تفصيل الرسوم البنكية وضريبة القيمة المضافة (14%)
        - محاكاة أسطر قيد اليومية المتوازن
        """
        if isinstance(from_account, (int, str)):
            from_acc = ChartOfAccounts.objects.get(pk=int(from_account))
        else:
            from_acc = from_account

        if isinstance(to_account, (int, str)):
            to_acc = ChartOfAccounts.objects.get(pk=int(to_account))
        else:
            to_acc = to_account

        transfer_date = transfer_date or timezone.now().date()
        source_amount = Decimal(str(source_amount or 0)).quantize(Decimal("0.01"))
        bank_fee = Decimal(str(bank_fee or 0)).quantize(Decimal("0.01"))
        vat_on_fee = Decimal(str(vat_on_fee or 0)).quantize(Decimal("0.01"))

        func_curr = ExchangeRateService.get_functional_currency()
        func_code = func_curr.code if func_curr else "EGP"

        from_curr_code = from_acc.currency_code
        to_curr_code = to_acc.currency_code

        # 1. أسعار الصرف للعملة الوظيفية
        if from_curr_code == func_code:
            from_rate = Decimal("1.000000")
        else:
            from_rate = ExchangeRateService.get_rate(from_curr_code, func_code, date=transfer_date)

        if to_curr_code == func_code:
            to_rate = Decimal("1.000000")
        else:
            to_rate = ExchangeRateService.get_rate(to_curr_code, func_code, date=transfer_date)

        # 2. تحديد سعر الصرف المباشر ومبلغ المستلم
        if from_curr_code == to_curr_code:
            effective_direct_rate = Decimal("1.000000")
            destination_amount = source_amount
        else:
            if exchange_rate and Decimal(str(exchange_rate)) > Decimal("0.00"):
                effective_direct_rate = Decimal(str(exchange_rate)).quantize(Decimal("0.000001"))
            else:
                # Direct rate = from_rate / to_rate
                effective_direct_rate = (from_rate / to_rate).quantize(Decimal("0.000001"))
            destination_amount = (source_amount * effective_direct_rate).quantize(Decimal("0.01"))

        # 3. المبالغ المعادلة بالعملة الوظيفية الأساسية
        source_base_amount = (source_amount * from_rate).quantize(Decimal("0.01"))
        dest_base_amount = (destination_amount * to_rate).quantize(Decimal("0.01"))

        # 4. حساب الفروق المحاسبية
        base_diff = (dest_base_amount - source_base_amount).quantize(Decimal("0.01"))
        fx_gain_loss = Decimal("0.00")
        penny_difference = Decimal("0.00")

        if base_diff != Decimal("0.00"):
            if abs(base_diff) <= PENNY_DIFFERENCE_THRESHOLD:
                penny_difference = base_diff
                fx_gain_loss = Decimal("0.00")
            else:
                fx_gain_loss = base_diff
                penny_difference = Decimal("0.00")

        # 5. حساب الضريبة على العمولة البنكية إن وجدت
        total_fee = (bank_fee + vat_on_fee).quantize(Decimal("0.01"))
        fee_base_amount = (total_fee * from_rate).quantize(Decimal("0.01"))

        # 6. محاكاة أسطر القيد المحاسبي
        simulated_lines = []

        # سطر دائن المصدر (المبلغ المحول + الرسوم)
        total_source_deduction = source_amount + total_fee
        total_source_base = (total_source_deduction * from_rate).quantize(Decimal("0.01"))
        simulated_lines.append({
            "account_code": from_acc.code,
            "account_name": from_acc.name,
            "debit": Decimal("0.00"),
            "credit": source_base_amount,
            "currency": from_curr_code,
            "exchange_rate": from_rate,
            "foreign_amount": source_amount,
            "description": f"تحويل نقدي صادرة إلى {to_acc.name}"
        })

        if transfer_type == TransferType.IN_TRANSIT:
            transit_acc = cls._get_transit_account()
            simulated_lines.append({
                "account_code": transit_acc.code,
                "account_name": transit_acc.name,
                "debit": source_base_amount,
                "credit": Decimal("0.00"),
                "currency": func_code,
                "exchange_rate": Decimal("1.000000"),
                "foreign_amount": source_base_amount,
                "description": f"إرسال نقدية بالطريق إلى {to_acc.name}"
            })
        else:
            # سطر مدين المستلم
            simulated_lines.append({
                "account_code": to_acc.code,
                "account_name": to_acc.name,
                "debit": dest_base_amount,
                "credit": Decimal("0.00"),
                "currency": to_curr_code,
                "exchange_rate": to_rate,
                "foreign_amount": destination_amount,
                "description": f"تحويل نقدي وارد من {from_acc.name}"
            })

            # معالجة فروق الصرف المحققة
            if fx_gain_loss != Decimal("0.00"):
                if fx_gain_loss > Decimal("0.00"):
                    # أرباح فروق عملة محققة (دائن 42300)
                    gain_acc = cls._get_fx_gain_account()
                    simulated_lines.append({
                        "account_code": gain_acc.code,
                        "account_name": gain_acc.name,
                        "debit": Decimal("0.00"),
                        "credit": fx_gain_loss,
                        "currency": func_code,
                        "exchange_rate": Decimal("1.000000"),
                        "foreign_amount": fx_gain_loss,
                        "description": f"أرباح فروق تحويل عملات ({from_curr_code} -> {to_curr_code})"
                    })
                else:
                    # خسائر فروق عملة محققة (مدين 52300)
                    loss_acc = cls._get_fx_loss_account()
                    simulated_lines.append({
                        "account_code": loss_acc.code,
                        "account_name": loss_acc.name,
                        "debit": abs(fx_gain_loss),
                        "credit": Decimal("0.00"),
                        "currency": func_code,
                        "exchange_rate": Decimal("1.000000"),
                        "foreign_amount": abs(fx_gain_loss),
                        "description": f"خسائر فروق تحويل عملات ({from_curr_code} -> {to_curr_code})"
                    })

            # معالجة فروق التقريب (54400)
            if penny_difference != Decimal("0.00"):
                round_acc = cls._get_rounding_account()
                if penny_difference > Decimal("0.00"):
                    simulated_lines.append({
                        "account_code": round_acc.code,
                        "account_name": round_acc.name,
                        "debit": Decimal("0.00"),
                        "credit": penny_difference,
                        "currency": func_code,
                        "exchange_rate": Decimal("1.000000"),
                        "foreign_amount": penny_difference,
                        "description": "فروق تقريب محاسبي ناتجة عن التحويل"
                    })
                else:
                    simulated_lines.append({
                        "account_code": round_acc.code,
                        "account_name": round_acc.name,
                        "debit": abs(penny_difference),
                        "credit": Decimal("0.00"),
                        "currency": func_code,
                        "exchange_rate": Decimal("1.000000"),
                        "foreign_amount": abs(penny_difference),
                        "description": "فروق تقريب محاسبي ناتجة عن التحويل"
                    })

        # معالجة الرسوم البنكية وضريبة القيمة المضافة
        if total_fee > Decimal("0.00"):
            fee_base = (bank_fee * from_rate).quantize(Decimal("0.01"))
            vat_base = (vat_on_fee * from_rate).quantize(Decimal("0.01"))

            # سطر دائن الرسوم من حساب المصدر
            simulated_lines.append({
                "account_code": from_acc.code,
                "account_name": from_acc.name,
                "debit": Decimal("0.00"),
                "credit": fee_base_amount,
                "currency": from_curr_code,
                "exchange_rate": from_rate,
                "foreign_amount": total_fee,
                "description": f"خصم عمولات ومصاريف تحويل إلى {to_acc.name}"
            })

            if bank_fee > Decimal("0.00"):
                fee_acc = cls._get_bank_charges_account()
                simulated_lines.append({
                    "account_code": fee_acc.code,
                    "account_name": fee_acc.name,
                    "debit": fee_base,
                    "credit": Decimal("0.00"),
                    "currency": func_code,
                    "exchange_rate": Decimal("1.000000"),
                    "foreign_amount": fee_base,
                    "description": f"مصاريف وعمولات بنكية - سند تحويل إلى {to_acc.name}"
                })

            if vat_on_fee > Decimal("0.00"):
                vat_acc = cls._get_input_vat_account()
                simulated_lines.append({
                    "account_code": vat_acc.code,
                    "account_name": vat_acc.name,
                    "debit": vat_base,
                    "credit": Decimal("0.00"),
                    "currency": func_code,
                    "exchange_rate": Decimal("1.000000"),
                    "foreign_amount": vat_base,
                    "description": f"ضريبة القيمة المضافة على المصاريف البنكية (14%)"
                })

        return {
            "source_amount": source_amount,
            "source_currency": from_curr_code,
            "source_rate": from_rate,
            "source_base_amount": source_base_amount,
            "destination_amount": destination_amount,
            "destination_currency": to_curr_code,
            "destination_rate": to_rate,
            "dest_base_amount": dest_base_amount,
            "effective_exchange_rate": effective_direct_rate,
            "fx_gain_loss": fx_gain_loss,
            "fx_type": "gain" if fx_gain_loss > Decimal("0.00") else ("loss" if fx_gain_loss < Decimal("0.00") else "none"),
            "penny_difference": penny_difference,
            "bank_fee": bank_fee,
            "vat_on_fee": vat_on_fee,
            "total_fee": total_fee,
            "total_source_deduction": total_source_deduction,
            "amount_in_words": amount_to_arabic_words(source_amount, from_curr_code),
            "simulated_lines": simulated_lines
        }

    @classmethod
    @transaction.atomic
    def execute_transfer(
        cls,
        from_account_id: int,
        to_account_id: int,
        source_amount: Decimal,
        user,
        transfer_type: str = TransferType.DIRECT,
        transfer_date: Optional[date] = None,
        exchange_rate: Optional[Decimal] = None,
        bank_fee: Decimal = Decimal("0.00"),
        is_fee_vat_inclusive: bool = False,
        fee_vat_amount: Optional[Decimal] = None,
        bank_name: str = "",
        account_number: str = "",
        iban: str = "",
        swift_code: str = "",
        bank_reference: str = "",
        bank_slip_attachment=None,
        denominations_breakdown: Optional[dict] = None,
        courier_name: str = "",
        courier_id_number: str = "",
        courier_phone: str = "",
        from_work_location_id: Optional[int] = None,
        to_work_location_id: Optional[int] = None,
        from_cost_center_id: Optional[int] = None,
        to_cost_center_id: Optional[int] = None,
        fee_cost_center_id: Optional[int] = None,
        financial_category_id: Optional[int] = None,
        notes: str = "",
    ) -> CashTransfer:
        """
        تنفيذ عملية تحويل مالي مركزية مع الحوكمة المحاسبية الكاملة:
        - قفل متسلسل للحسابات حسب المعرف لتفادي التعارض التزامني (Deadlock-Free Row Lock)
        - فحص الفترات المحاسبية وحوكمة الصلاحيات
        - تسجيل وتوثيق سند CashTransfer
        - توليد قيود اليومية المتوازنة والمحوكمة عبر AccountingGateway
        """
        if source_amount <= Decimal("0.00"):
            raise ValidationError(_("مبلغ التحويل يجب أن يكون أكبر من صفر."))

        if int(from_account_id) == int(to_account_id):
            raise ValidationError(_("لا يمكن التحويل لنفس الحساب المصدر."))

        transfer_date = transfer_date or timezone.now().date()

        # 1. التحقق من الفترة المحاسبية
        is_open, period = PeriodControlService.validate_period_open(transfer_date)
        if not is_open:
            raise ValidationError(_("لا يمكن تنفيذ التحويل لأن الفترة المحاسبية لتاريخ السند مغلقة."))

        # 2. قفل الحسابين بترتيب المعرف لتفادي الـ Deadlock
        account_ids = sorted([int(from_account_id), int(to_account_id)])
        locked_accounts = {
            acc.id: acc
            for acc in ChartOfAccounts.objects.select_for_update().filter(id__in=account_ids)
        }

        from_acc = locked_accounts.get(int(from_account_id))
        to_acc = locked_accounts.get(int(to_account_id))

        if not from_acc or not to_acc:
            raise ValidationError(_("أحد الحسابات المحددة للتحويل غير موجود."))

        if not from_acc.is_leaf or from_acc.is_control_account or not (from_acc.is_cash_account or from_acc.is_bank_account):
            raise ValidationError(_(f"الحساب المصدر '{from_acc.name}' ليس حساباً نقدياً أو بنكياً تشغيلياً."))

        if not to_acc.is_leaf or to_acc.is_control_account or not (to_acc.is_cash_account or to_acc.is_bank_account):
            raise ValidationError(_(f"الحساب المستلم '{to_acc.name}' ليس حساباً نقدياً أو بنكياً تشغيلياً."))

        # 3. فحص صلاحيات الخزينة
        can_disburse, disburse_err = TreasurySecurityService.can_user_disburse(user, from_acc.id, source_amount, transfer_date)
        if not can_disburse:
            raise ValidationError(disburse_err or _(f"ليس لديك صلاحية صرف من '{from_acc.name}'."))

        if transfer_type == TransferType.DIRECT:
            if not TreasurySecurityService.can_user_deposit(user, to_acc.id, transfer_date):
                raise ValidationError(_(f"ليس لديك صلاحية إيداع في الخزينة المستلمة '{to_acc.name}'."))

        # 4. حساب المعاينة والقيم الرقمية
        bank_fee = Decimal(str(bank_fee or 0)).quantize(Decimal("0.01"))
        
        # حساب ضريبة القيمة المضافة على العمولة
        if fee_vat_amount is not None and Decimal(str(fee_vat_amount)) > Decimal("0.00"):
            vat_on_fee = Decimal(str(fee_vat_amount)).quantize(Decimal("0.01"))
        elif bank_fee > Decimal("0.00"):
            if is_fee_vat_inclusive:
                net_fee = (bank_fee / (Decimal("1.00") + (STANDARD_VAT_RATE / Decimal("100")))).quantize(Decimal("0.01"))
                vat_on_fee = (bank_fee - net_fee).quantize(Decimal("0.01"))
                bank_fee = net_fee
            else:
                vat_on_fee = ((bank_fee * STANDARD_VAT_RATE) / Decimal("100")).quantize(Decimal("0.01"))
        else:
            vat_on_fee = Decimal("0.00")

        preview = cls.calculate_transfer_preview(
            from_account=from_acc,
            to_account=to_acc,
            source_amount=source_amount,
            exchange_rate=exchange_rate,
            bank_fee=bank_fee,
            vat_on_fee=vat_on_fee,
            transfer_type=transfer_type,
            transfer_date=transfer_date
        )

        # 5. توليد رقم السند التسلسلي الذري
        transfer_number = SequenceService.get_next_number(DocumentType.CASH_TRANSFER)
        if not transfer_number:
            # Atomic fallback generator
            year = transfer_date.year
            last_trf = CashTransfer.objects.filter(transfer_number__startswith=f"TRF-{year}-").order_by("-id").first()
            seq = 1
            if last_trf and last_trf.transfer_number:
                try:
                    seq = int(last_trf.transfer_number.split("-")[-1]) + 1
                except Exception:
                    seq = 1
            transfer_number = f"TRF-{year}-{seq:04d}"

        # 6. تجهيز كائن سند التحويل CashTransfer
        transfer = CashTransfer()
        transfer.transfer_number = transfer_number
        transfer.transfer_type = transfer_type
        transfer.status = TransferStatus.IN_TRANSIT if transfer_type == TransferType.IN_TRANSIT else TransferStatus.COMPLETED
        transfer.transfer_date = transfer_date
        transfer.from_account = from_acc
        transfer.to_account = to_acc
        transfer.transit_account = cls._get_transit_account() if transfer_type == TransferType.IN_TRANSIT else None

        transfer.from_work_location_id = from_work_location_id or getattr(from_acc.work_location, "id", None)
        transfer.to_work_location_id = to_work_location_id or getattr(to_acc.work_location, "id", None)
        transfer.from_cost_center_id = from_cost_center_id
        transfer.to_cost_center_id = to_cost_center_id
        transfer.fee_cost_center_id = fee_cost_center_id
        transfer.financial_category_id = financial_category_id

        transfer.source_amount = preview["source_amount"]
        transfer.source_currency = from_acc.currency
        transfer.source_exchange_rate = preview["source_rate"]

        transfer.destination_amount = preview["destination_amount"]
        transfer.destination_currency = to_acc.currency
        transfer.destination_exchange_rate = preview["destination_rate"]
        transfer.custom_exchange_rate = exchange_rate

        transfer.fx_gain_loss_amount = preview["fx_gain_loss"]
        transfer.rounding_difference = preview["penny_difference"]

        transfer.transfer_fee = preview["bank_fee"]
        transfer.is_fee_vat_inclusive = is_fee_vat_inclusive
        transfer.fee_vat_rate = STANDARD_VAT_RATE if preview["bank_fee"] > 0 else Decimal("0.00")
        transfer.fee_vat_amount = preview["vat_on_fee"]
        if preview["bank_fee"] > 0:
            transfer.fee_account = cls._get_bank_charges_account()

        transfer.bank_name = bank_name or from_acc.bank_name or to_acc.bank_name or ""
        transfer.account_number = account_number or from_acc.account_number or to_acc.account_number or ""
        transfer.iban = iban or from_acc.iban or to_acc.iban or ""
        transfer.swift_code = swift_code or from_acc.swift_code or to_acc.swift_code or ""
        transfer.bank_reference = bank_reference
        if bank_slip_attachment:
            transfer.bank_slip_attachment = bank_slip_attachment

        transfer.amount_in_words = preview["amount_in_words"]
        transfer.denominations_breakdown = denominations_breakdown or {}

        if transfer_type == TransferType.IN_TRANSIT:
            transfer.courier_name = courier_name
            transfer.courier_id_number = courier_id_number
            transfer.courier_phone = courier_phone

        transfer.created_by = user
        transfer.notes = notes
        transfer.save()

        # 7. بناء أسطر قيد اليومية وتمريرها لـ AccountingGateway
        lines_data = []
        for line in preview["simulated_lines"]:
            desc = line["description"]
            if bank_reference:
                desc = f"{desc} | مرجع: {bank_reference}"
            lines_data.append(JournalEntryLineData(
                account_code=line["account_code"],
                debit=line["debit"],
                credit=line["credit"],
                description=desc,
                currency=line["currency"],
                exchange_rate=line["exchange_rate"],
                foreign_debit=line["foreign_amount"] if line["debit"] > Decimal("0.00") else Decimal("0.00"),
                foreign_credit=line["foreign_amount"] if line["credit"] > Decimal("0.00") else Decimal("0.00")
            ))

        op_name = "dispatch" if transfer_type == TransferType.IN_TRANSIT else "direct"
        gateway = AccountingGateway()
        entry = gateway.create_journal_entry(
            source_module="financial",
            source_model="CashTransfer",
            source_id=transfer.id,
            date=transfer_date,
            description=f"سند تحويل مالي {transfer.transfer_number}: من {from_acc.name} إلى {to_acc.name} ({transfer.source_amount} {from_acc.currency_code})",
            reference=transfer.transfer_number,
            lines=lines_data,
            idempotency_key=f"JE:financial:CashTransfer:{transfer.id}:{op_name}",
            user=user
        )

        transfer.journal_entry = entry
        transfer.save(update_fields=["journal_entry"])

        # 8. إبطال الكاش الأمني
        TreasurySecurityService.invalidate_all_users_cache()

        logger.info(
            f"✅ Successfully executed Cash Transfer #{transfer.transfer_number} (ID: {transfer.id}, JE: #{entry.id}): "
            f"{from_acc.name} -> {to_acc.name} [{transfer.get_status_display()}]"
        )
        return transfer

    @classmethod
    @transaction.atomic
    def dispatch_transit_transfer(
        cls,
        from_account_id: int,
        to_account_id: int,
        source_amount: Decimal,
        user,
        **kwargs
    ) -> CashTransfer:
        """
        إرسال نقدية مرحلية في الطريق (الخطوة 1 من التحويل المرحلي)
        """
        return cls.execute_transfer(
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            source_amount=source_amount,
            user=user,
            transfer_type=TransferType.IN_TRANSIT,
            **kwargs
        )

    @classmethod
    @transaction.atomic
    def receive_transit_transfer(
        cls,
        transfer_id: int,
        user,
        receive_date: Optional[date] = None,
        received_amount: Optional[Decimal] = None,
        notes: str = ""
    ) -> CashTransfer:
        """
        تأكيد استلام نقدية مرحلية في الخزينة المستهدفة (الخطوة 2 من التحويل المرحلي):
        - فحص مبدأ الفصل بين المهام (Segregation of Duties - SoD)
        - قفل السند والحساب المستلم وحساب النقدية في الطريق
        - تسوية فروق العجز أو الزيادة أو فروق الصرف
        - توليد قيد استلام النقدية المرحلية عبر AccountingGateway
        """
        transfer = CashTransfer.objects.select_for_update().get(pk=transfer_id)

        if transfer.status != TransferStatus.IN_TRANSIT:
            raise ValidationError(_(f"لا يمكن استلام السند لأن حالته الحالية هي '{transfer.get_status_display()}' وليست 'في الطريق'."))

        # تطبيق مبدأ الفصل بين المهام (SoD)
        if transfer.created_by == user and not (user.is_superuser or user.is_staff):
            raise ValidationError(_("مبدأ الفصل بين المهام (SoD): لا يجوز لمحرر التحويل تأكيد استلامه بنفسه في الخزينة المستلمة."))

        receive_date = receive_date or timezone.now().date()

        # التحقق من الفترة المحاسبية
        is_open, period = PeriodControlService.validate_period_open(receive_date)
        if not is_open:
            raise ValidationError(_("لا يمكن تأكيد الاستلام لأن الفترة المحاسبية لتاريخ الاستلام مغلقة."))

        # التحقق من صلاحية الإيداع للمستلم
        if not TreasurySecurityService.can_user_deposit(user, transfer.to_account_id, receive_date):
            raise ValidationError(_(f"ليس لديك صلاحية إيداع واستلام في الخزينة '{transfer.to_account.name}'."))

        # قفل الحسابين
        transit_acc = transfer.transit_account or cls._get_transit_account()
        to_acc = ChartOfAccounts.objects.select_for_update().get(pk=transfer.to_account_id)

        actual_received = received_amount if received_amount is not None else transfer.destination_amount
        actual_received = Decimal(str(actual_received)).quantize(Decimal("0.01"))

        # حساب القيمة الوظيفية
        func_curr = ExchangeRateService.get_functional_currency()
        func_code = func_curr.code if func_curr else "EGP"
        to_curr_code = to_acc.currency_code
        to_rate = transfer.destination_exchange_rate

        dest_base_amount = (actual_received * to_rate).quantize(Decimal("0.01"))
        transit_base_amount = (transfer.source_amount * transfer.source_exchange_rate).quantize(Decimal("0.01"))

        diff_base = (dest_base_amount - transit_base_amount).quantize(Decimal("0.01"))

        lines_data = []

        # 1. سطر دائن حساب النقدية بالطريق (إقفال الوسيط 11150)
        lines_data.append(JournalEntryLineData(
            account_code=transit_acc.code,
            debit=Decimal("0.00"),
            credit=transit_base_amount,
            description=f"إقفال نقدية بالطريق لسند {transfer.transfer_number}",
            currency=func_code,
            exchange_rate=Decimal("1.000000"),
            foreign_credit=transit_base_amount
        ))

        # 2. سطر مدين الخزينة المستلمة
        lines_data.append(JournalEntryLineData(
            account_code=to_acc.code,
            debit=dest_base_amount,
            credit=Decimal("0.00"),
            description=f"استلام نقدية مرحلية من {transfer.from_account.name} (سند {transfer.transfer_number})",
            currency=to_curr_code,
            exchange_rate=to_rate,
            foreign_debit=actual_received
        ))

        # 3. موازنة الفروق إن وجدت
        if diff_base != Decimal("0.00"):
            if abs(diff_base) <= PENNY_DIFFERENCE_THRESHOLD:
                round_acc = cls._get_rounding_account()
                if diff_base > Decimal("0.00"):
                    lines_data.append(JournalEntryLineData(
                        account_code=round_acc.code,
                        debit=Decimal("0.00"),
                        credit=diff_base,
                        description="فروق تقريب استلام تحويل نقدية بالطريق",
                        currency=func_code
                    ))
                else:
                    lines_data.append(JournalEntryLineData(
                        account_code=round_acc.code,
                        debit=abs(diff_base),
                        credit=Decimal("0.00"),
                        description="فروق تقريب استلام تحويل نقدية بالطريق",
                        currency=func_code
                    ))
            else:
                if diff_base > Decimal("0.00"):
                    gain_acc = cls._get_fx_gain_account()
                    lines_data.append(JournalEntryLineData(
                        account_code=gain_acc.code,
                        debit=Decimal("0.00"),
                        credit=diff_base,
                        description="أرباح فروق تسوية استلام نقدية بالطريق",
                        currency=func_code
                    ))
                else:
                    loss_acc = cls._get_fx_loss_account()
                    lines_data.append(JournalEntryLineData(
                        account_code=loss_acc.code,
                        debit=abs(diff_base),
                        credit=Decimal("0.00"),
                        description="خسائر فروق تسوية استلام نقدية بالطريق",
                        currency=func_code
                    ))

        gateway = AccountingGateway()
        entry = gateway.create_journal_entry(
            source_module="financial",
            source_model="CashTransfer",
            source_id=transfer.id,
            date=receive_date,
            description=f"تأكيد استلام نقدية بالطريق {transfer.transfer_number}: في {to_acc.name} ({actual_received} {to_curr_code})",
            reference=f"{transfer.transfer_number}-RCV",
            lines=lines_data,
            idempotency_key=f"JE:financial:CashTransfer:{transfer.id}:receive",
            user=user
        )

        transfer.status = TransferStatus.COMPLETED
        transfer.received_by = user
        transfer.received_at = timezone.now()
        transfer.received_amount = actual_received
        transfer.receipt_journal_entry = entry
        if notes:
            transfer.notes = f"{transfer.notes}\n[ملاحظات الاستلام بواسطة {user}]: {notes}".strip()
        transfer.save()

        TreasurySecurityService.invalidate_all_users_cache()

        logger.info(f"✅ Received Transit Transfer #{transfer.transfer_number} into {to_acc.name} by {user} (JE: #{entry.id})")
        return transfer

    @classmethod
    @transaction.atomic
    def recall_transit_transfer(
        cls,
        transfer_id: int,
        user,
        reason: str = ""
    ) -> CashTransfer:
        """
        استرجاع / إلغاء سند تحويل مرحلي في الطريق قبل استلامه:
        - قفل السند والتأكد من أنه ما زال IN_TRANSIT
        - توليد قيد استرجاع وعكس حركة الإرسال إلى الخزينة المصدر
        - تحديث حالة السند إلى RECALLED
        """
        transfer = CashTransfer.objects.select_for_update().get(pk=transfer_id)

        if transfer.status != TransferStatus.IN_TRANSIT:
            raise ValidationError(_(f"لا يمكن استرجاع السند لأن حالته الحالية هي '{transfer.get_status_display()}' وليست 'في الطريق'."))

        from_acc = ChartOfAccounts.objects.select_for_update().get(pk=transfer.from_account_id)
        transit_acc = transfer.transit_account or cls._get_transit_account()

        func_curr = ExchangeRateService.get_functional_currency()
        func_code = func_curr.code if func_curr else "EGP"
        source_base = (transfer.source_amount * transfer.source_exchange_rate).quantize(Decimal("0.01"))

        lines_data = [
            # إعادة الرصيد للخزينة المصدر (مدين)
            JournalEntryLineData(
                account_code=from_acc.code,
                debit=source_base,
                credit=Decimal("0.00"),
                description=f"استرجاع نقدية بالطريق ملغاة لسند {transfer.transfer_number}",
                currency=transfer.source_currency.code,
                exchange_rate=transfer.source_exchange_rate,
                foreign_debit=transfer.source_amount
            ),
            # إقفال الوسيط (دائن 11150)
            JournalEntryLineData(
                account_code=transit_acc.code,
                debit=Decimal("0.00"),
                credit=source_base,
                description=f"إلغاء نقدية بالطريق لسند {transfer.transfer_number}",
                currency=func_code,
                exchange_rate=Decimal("1.000000"),
                foreign_credit=source_base
            )
        ]

        gateway = AccountingGateway()
        entry = gateway.create_journal_entry(
            source_module="financial",
            source_model="CashTransfer",
            source_id=transfer.id,
            date=timezone.now().date(),
            description=f"استرجاع وإلغاء نقدية بالطريق {transfer.transfer_number} إلى {from_acc.name}",
            reference=f"{transfer.transfer_number}-RCL",
            lines=lines_data,
            idempotency_key=f"JE:financial:CashTransfer:{transfer.id}:recall",
            user=user
        )

        transfer.status = TransferStatus.RECALLED
        transfer.reversal_journal_entry = entry
        transfer.reversal_reason = reason
        transfer.reversed_by = user
        transfer.reversed_at = timezone.now()
        transfer.notes = f"{transfer.notes}\n[تم الاسترجاع بواسطة {user}]: {reason}".strip()
        transfer.save()

        TreasurySecurityService.invalidate_all_users_cache()

        logger.info(f"✅ Recalled Transit Transfer #{transfer.transfer_number} back to {from_acc.name} by {user} (JE: #{entry.id})")
        return transfer

    @classmethod
    @transaction.atomic
    def reverse_transfer(
        cls,
        transfer_id: int,
        user,
        reason: str = ""
    ) -> CashTransfer:
        """
        عكس سند تحويل مالي مكتمل بشكل محوكم (Reversal with Audit Trail):
        - قفل السند والتأكد من أنه COMPLETED
        - فحص صلاحيات المستخدم
        - عكس القيود المحاسبية عبر قيود عكسية مطابقة
        - تحديث حالة السند إلى REVERSED
        """
        transfer = CashTransfer.objects.select_for_update().get(pk=transfer_id)

        if transfer.status != TransferStatus.COMPLETED:
            raise ValidationError(_(f"لا يمكن عكس السند لأن حالته الحالية هي '{transfer.get_status_display()}' وليست 'مكتمل ومرحل'."))

        if not (user.is_superuser or user.is_staff):
            raise ValidationError(_("عكس سندات التحويل المالي يتطلب صلاحيات إدارية عليا."))

        reversal_date = timezone.now().date()
        is_open, period = PeriodControlService.validate_period_open(reversal_date)
        if not is_open:
            raise ValidationError(_("لا يمكن عكس السند لأن الفترة المحاسبية الحالية مغلقة."))

        from_acc = ChartOfAccounts.objects.select_for_update().get(pk=transfer.from_account_id)
        to_acc = ChartOfAccounts.objects.select_for_update().get(pk=transfer.to_account_id)

        # بناء قيد عكسي كامل
        func_curr = ExchangeRateService.get_functional_currency()
        func_code = func_curr.code if func_curr else "EGP"

        source_base = (transfer.source_amount * transfer.source_exchange_rate).quantize(Decimal("0.01"))
        dest_base = (transfer.destination_amount * transfer.destination_exchange_rate).quantize(Decimal("0.01"))

        lines_data = [
            # إعادة المبلغ للخزينة المصدر (مدين)
            JournalEntryLineData(
                account_code=from_acc.code,
                debit=source_base,
                credit=Decimal("0.00"),
                description=f"عكس سند تحويل {transfer.transfer_number} - استرداد للخزينة",
                currency=transfer.source_currency.code,
                exchange_rate=transfer.source_exchange_rate,
                foreign_debit=transfer.source_amount
            ),
            # خصم المبلغ من الخزينة المستلمة (دائن)
            JournalEntryLineData(
                account_code=to_acc.code,
                debit=Decimal("0.00"),
                credit=dest_base,
                description=f"عكس سند تحويل {transfer.transfer_number} - خصم من المستلم",
                currency=transfer.destination_currency.code,
                exchange_rate=transfer.destination_exchange_rate,
                foreign_credit=transfer.destination_amount
            )
        ]

        # عكس فروق العملة أو التقريب إن وجدت
        if transfer.fx_gain_loss_amount != Decimal("0.00"):
            if transfer.fx_gain_loss_amount > Decimal("0.00"):
                # كان ربح (دائن)، العكس (مدين)
                gain_acc = cls._get_fx_gain_account()
                lines_data.append(JournalEntryLineData(
                    account_code=gain_acc.code,
                    debit=transfer.fx_gain_loss_amount,
                    credit=Decimal("0.00"),
                    description=f"عكس أرباح فروق عملة لسند {transfer.transfer_number}",
                    currency=func_code
                ))
            else:
                # كان خسارة (مدين)، العكس (دائن)
                loss_acc = cls._get_fx_loss_account()
                lines_data.append(JournalEntryLineData(
                    account_code=loss_acc.code,
                    debit=Decimal("0.00"),
                    credit=abs(transfer.fx_gain_loss_amount),
                    description=f"عكس خسائر فروق عملة لسند {transfer.transfer_number}",
                    currency=func_code
                ))

        if transfer.rounding_difference != Decimal("0.00"):
            round_acc = cls._get_rounding_account()
            if transfer.rounding_difference > Decimal("0.00"):
                lines_data.append(JournalEntryLineData(
                    account_code=round_acc.code,
                    debit=transfer.rounding_difference,
                    credit=Decimal("0.00"),
                    description=f"عكس فروق تقريب لسند {transfer.transfer_number}",
                    currency=func_code
                ))
            else:
                lines_data.append(JournalEntryLineData(
                    account_code=round_acc.code,
                    debit=Decimal("0.00"),
                    credit=abs(transfer.rounding_difference),
                    description=f"عكس فروق تقريب لسند {transfer.transfer_number}",
                    currency=func_code
                ))

        gateway = AccountingGateway()
        entry = gateway.create_journal_entry(
            source_module="financial",
            source_model="CashTransfer",
            source_id=transfer.id,
            date=reversal_date,
            description=f"قيد عكس سند التحويل المالي {transfer.transfer_number} - {reason}".strip(),
            reference=f"{transfer.transfer_number}-REV",
            lines=lines_data,
            idempotency_key=f"JE:financial:CashTransfer:{transfer.id}:reverse",
            user=user
        )

        transfer.status = TransferStatus.REVERSED
        transfer.reversal_journal_entry = entry
        transfer.reversed_by = user
        transfer.reversed_at = timezone.now()
        transfer.reversal_reason = reason
        transfer.notes = f"{transfer.notes}\n[تم العكس بواسطة {user}]: {reason}".strip()
        transfer.save()

        TreasurySecurityService.invalidate_all_users_cache()

        logger.info(f"✅ Reversed Cash Transfer #{transfer.transfer_number} by {user} (JE: #{entry.id})")
        return transfer

    # ==================== دوال الحسابات الرقابية الحاكمة ====================

    @classmethod
    def _get_transit_account(cls) -> ChartOfAccounts:
        """جلب حساب النقدية في الطريق والتحويلات الوسيطة (11150)"""
        acc = ChartOfAccounts.objects.filter(code="11150", is_active=True).first()
        if not acc:
            acc = AccountRoleRegistry.get_account_by_role("CASH_IN_TRANSIT_CONTROL")
        if not acc:
            acc = ChartOfAccounts.objects.filter(code="11150").first()
        if not acc:
            raise ValidationError(_("لم يتم العثور على حساب 'نقدية بالطريق وتحويلات وسيطة (11150)' في شجرة الحسابات."))
        return acc

    @classmethod
    def _get_fx_gain_account(cls) -> ChartOfAccounts:
        """جلب حساب أرباح فروق تقييم وتحويل العملة (42300)"""
        acc = ChartOfAccounts.objects.filter(code="42300", is_active=True).first()
        if not acc:
            acc = AccountRoleRegistry.get_account_by_role("FX_REALIZED_GAIN")
        if not acc:
            acc = ChartOfAccounts.objects.filter(code="42300").first()
        if not acc:
            raise ValidationError(_("لم يتم العثور على حساب 'أرباح فروق العملة المحققة (42300)'."))
        return acc

    @classmethod
    def _get_fx_loss_account(cls) -> ChartOfAccounts:
        """جلب حساب خسائر فروق تقييم وتحويل العملة (52300)"""
        acc = ChartOfAccounts.objects.filter(code="52300", is_active=True).first()
        if not acc:
            acc = AccountRoleRegistry.get_account_by_role("FX_REALIZED_LOSS")
        if not acc:
            acc = ChartOfAccounts.objects.filter(code="52300").first()
        if not acc:
            raise ValidationError(_("لم يتم العثور على حساب 'خسائر فروق العملة المحققة (52300)'."))
        return acc

    @classmethod
    def _get_rounding_account(cls) -> ChartOfAccounts:
        """جلب حساب فروق التقريب المحاسبي (54400)"""
        acc = ChartOfAccounts.objects.filter(code="54400", is_active=True).first()
        if not acc:
            acc = AccountRoleRegistry.get_account_by_role("ROUNDING_DIFFERENCE_ACCOUNT")
        if not acc:
            acc = ChartOfAccounts.objects.filter(code="54400").first()
        if not acc:
            raise ValidationError(_("لم يتم العثور على حساب 'فروق التقريب المحاسبي (54400)'."))
        return acc

    @classmethod
    def _get_bank_charges_account(cls) -> ChartOfAccounts:
        """جلب حساب المصاريف والعمولات البنكية (52200)"""
        acc = ChartOfAccounts.objects.filter(code="52200", is_active=True).first()
        if not acc:
            acc = AccountRoleRegistry.get_account_by_role("BANK_CHARGES_EXPENSE")
        if not acc:
            acc = ChartOfAccounts.objects.filter(code="52200").first()
        if not acc:
            raise ValidationError(_("لم يتم العثور على حساب 'المصاريف والعمولات البنكية (52200)'."))
        return acc

    @classmethod
    def _get_input_vat_account(cls) -> ChartOfAccounts:
        """جلب حساب ضريبة القيمة المضافة على المدخلات (11350)"""
        acc = ChartOfAccounts.objects.filter(code="11350", is_active=True).first()
        if not acc:
            acc = AccountRoleRegistry.get_account_by_role("VAT_INPUT")
        if not acc:
            acc = ChartOfAccounts.objects.filter(code="11350").first()
        if not acc:
            raise ValidationError(_("لم يتم العثور على حساب 'ضريبة القيمة المضافة على المدخلات (11350)'."))
        return acc
