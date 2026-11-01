# -*- coding: utf-8 -*-
"""
ContractDebtClearanceService - خدمة المخالصة المالية المستقلة للعقود العقارية (Wave 1 Phase 3.5)
مفصولة تماماً عن مديونيات فواتير المبيعات التجارية وتفحص التزامات العقد وأقساطه وشيكاته بشكل معزول ومحكم.
"""

import logging
import hashlib
from decimal import Decimal
from typing import Dict, Any, Optional
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from real_estate.models.contract import PropertyContract
from cheques.models.cheque import ChequeStatus

logger = logging.getLogger(__name__)


class ContractDebtClearanceService:
    """
    محرك تدقيق براءة الذمة والمخالصة المالية التامة للوحدات والعقود العقارية
    """

    @classmethod
    def get_verified_down_payment(cls, contract: PropertyContract) -> Decimal:
        """
        اشتقاق مبلغ مقدم التعاقد المحصل فعلياً من القيود المحاسبية وإيصالات السداد المعتمدة
        الخاصة بمقدم التعاقد حصراً، مع عزل تام وتفادي تداخلها مع تحصيلات الأقساط.
        في حال غياب أي إثبات تحصيل معتمد، يرجع صفر قطعي لمنع منح المخالصة بدون سداد.
        """
        from financial.models.journal_entry import JournalEntry
        from real_estate.models.contract import ContractPaymentReceipt
        from real_estate.models.booking import UnitBooking
        from django.db.models import Q

        # 1. فحص إيصالات سداد العقد المباشرة (ContractPaymentReceipt) الخاصة بالمقدم حصراً (بدون قسط)
        direct_receipts = ContractPaymentReceipt.objects.filter(
            contract=contract,
            installment_item__isnull=True
        ).select_related('customer_payment')
        if direct_receipts.exists():
            receipt_amount = sum(
                Decimal(str(r.customer_payment.amount)) for r in direct_receipts if r.customer_payment
            )
            if receipt_amount > Decimal('0.00'):
                return min(contract.down_payment, receipt_amount)

        # 2. قيود اليومية المعتمدة الخاصة بمقدم التعاقد حصراً
        # تشمل قيود تحويل جدية الحجز وسداد استكمال المقدم (booking_conversion / contract_down_payment)
        # وتستبعد صراحةً وبشكل قاطع أي قيود خاصة بالأقساط أو الشيكات أو الاعتراف بالإيراد
        down_payment_entries = JournalEntry.objects.filter(
            source_module='real_estate',
            source_model='PropertyContract',
            source_id=contract.id
        ).exclude(
            status='cancelled'
        ).filter(
            Q(idempotency_key__icontains='booking_conversion') |
            Q(idempotency_key__icontains='down_payment') |
            Q(description__icontains='مقدم') |
            Q(lines__description__icontains='مقدم') |
            Q(lines__description__icontains='جدية الحجز')
        ).exclude(
            Q(idempotency_key__icontains='cash_installment') |
            Q(idempotency_key__icontains='contract_cheques') |
            Q(idempotency_key__icontains='revenue_recognition') |
            Q(description__icontains='قسط')
        ).distinct()

        if down_payment_entries.exists():
            verified_amount = Decimal('0.00')
            for je in down_payment_entries:
                for line in je.lines.all():
                    if line.account and (line.account.code.startswith('21102') or line.account.code.startswith('2110')):
                        desc = (line.description or "") + (je.description or "")
                        if "قسط" not in desc:
                            if contract.currency and not contract.currency.is_functional and line.foreign_credit > Decimal('0.00'):
                                verified_amount += line.foreign_credit
                            elif line.credit > Decimal('0.00'):
                                verified_amount += line.credit
            if verified_amount > Decimal('0.00'):
                return min(contract.down_payment, verified_amount)

        # 3. فحص الحجوزات السابقة للوحدة والعميل التي تم إثبات تحصيلها محاسبياً
        bookings = UnitBooking.objects.filter(
            unit=contract.unit,
            customer=contract.customer,
            is_deposit_collected=True
        )
        if bookings.exists():
            collected_holding = sum(
                b.holding_deposit for b in bookings if b.holding_deposit > Decimal('0.00')
            )
            if collected_holding > Decimal('0.00'):
                return min(contract.down_payment, collected_holding)

        # 4. في حال غياب أي إثبات تحصيل محاسبي أو إيصال معتمد، يعتبر المقدم غير محصل (0.00)
        return Decimal('0.00')

    @classmethod
    def evaluate_contract_clearance(cls, contract: PropertyContract) -> Dict[str, Any]:
        """
        فحص تفصيلي للذمة المالية للعقد وخطة الأقساط المرتبطة والشيكات
        """
        verified_dp = cls.get_verified_down_payment(contract)

        if not contract.installment_plan:
            # إذا لم تكن هناك خطة أقساط، يتم الفحص بناءً على سداد كامل قيمة العقد
            is_fully_paid = verified_dp >= contract.final_contract_price
            return {
                'is_cleared': is_fully_paid,
                'total_contract_price': contract.final_contract_price,
                'total_paid': verified_dp,
                'remaining_balance': max(Decimal('0.00'), contract.final_contract_price - verified_dp),
                'unpaid_installments_count': 0,
                'bounced_cheques_count': 0,
                'can_issue_clearance_certificate': is_fully_paid and contract.status in [PropertyContract.ContractStatus.ACTIVE, PropertyContract.ContractStatus.COMPLETED]
            }

        plan = contract.installment_plan
        items = plan.items.all()

        total_plan_amount = plan.total_amount
        total_paid = sum(Decimal(str(item.paid_amount)) for item in items) + verified_dp
        remaining_balance = max(Decimal('0.00'), contract.final_contract_price - total_paid)

        unpaid_items = [item for item in items if item.paid_amount < item.total_amount]

        # فحص الشيكات المرتدة أو المرفوضة المرتبطة بأقساط هذا العقد
        from cheques.models.allocation import ChequeInvoiceAllocation
        contract_allocations = ChequeInvoiceAllocation.objects.filter(
            installment_item__plan=plan,
            allocation_status='APPLIED'
        ).select_related('cheque')

        bounced_statuses = [
            ChequeStatus.BOUNCED,
            ChequeStatus.LEGAL_ACTION,
            ChequeStatus.ENDORSED_BOUNCED
        ]
        bounced_cheques = [
            alloc.cheque for alloc in contract_allocations 
            if alloc.cheque.status in bounced_statuses
        ]

        is_cleared = (
            remaining_balance <= Decimal('0.05') and 
            len(unpaid_items) == 0 and 
            len(bounced_cheques) == 0
        )

        can_issue = (
            is_cleared and 
            contract.status in [PropertyContract.ContractStatus.ACTIVE, PropertyContract.ContractStatus.COMPLETED]
        )

        # تحديث حالة سداد العقد تلقائياً إذا ثبتت المخالصة
        if is_cleared and not contract.installments_settled:
            contract.on_installments_completed()

        return {
            'is_cleared': is_cleared,
            'total_contract_price': contract.final_contract_price,
            'total_paid': total_paid,
            'remaining_balance': remaining_balance,
            'unpaid_installments_count': len(unpaid_items),
            'bounced_cheques_count': len(bounced_cheques),
            'can_issue_clearance_certificate': can_issue
        }

    @classmethod
    def issue_clearance_certificate(cls, contract: PropertyContract, user, notes: str = "") -> Dict[str, Any]:
        """
        إصدار شهادة المخالصة المالية النهائية المعتمدة بعد التحقق الصارم من انعدام المديونية
        """
        evaluation = cls.evaluate_contract_clearance(contract)
        if not evaluation['can_issue_clearance_certificate']:
            raise ValidationError(
                _("لا يمكن إصدار شهادة المخالصة: المديونية المتبقية %(rem)s، عدد الأقساط غير المسددة %(unpaid)s، الشيكات المرتدة %(bounced)s.") % {
                    'rem': evaluation['remaining_balance'],
                    'unpaid': evaluation['unpaid_installments_count'],
                    'bounced': evaluation['bounced_cheques_count']
                }
            )

        contract.status = PropertyContract.ContractStatus.COMPLETED
        contract.installments_settled = True
        contract.save(update_fields=['status', 'installments_settled', 'updated_at'])

        issue_dt = timezone.localdate()
        raw_payload = f"{contract.contract_number}:{contract.customer.id}:{contract.final_contract_price}:{issue_dt}"
        verification_hash = hashlib.sha256(raw_payload.encode('utf-8')).hexdigest()

        certificate_data = {
            'certificate_number': f"CLR-{contract.contract_number}",
            'contract_number': contract.contract_number,
            'customer_name': contract.customer.name,
            'unit_code': contract.unit.unit_code,
            'project_name': contract.project.name,
            'issue_date': issue_dt,
            'issued_by': getattr(user, 'username', 'system'),
            'total_contract_price': str(contract.final_contract_price),
            'verification_hash': verification_hash,
            'verification_token': verification_hash[:16].upper(),
            'notes': notes or "تمت المخالصة المالية التامة وسداد كامل المستحقات التعاقدية دون أدنى قيد أو شرط."
        }

        logger.info(f"Financial debt clearance certificate issued for contract {contract.contract_number}")
        return certificate_data
