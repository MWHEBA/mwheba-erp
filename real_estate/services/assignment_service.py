# -*- coding: utf-8 -*-
"""
ContractAssignmentService - محرك التنازل عن العقود العقارية للغير ونقل الملكية وإعادة البيع
(Wave 3 Phase 13 - Resale & Contract Assignment Engine)
"""

import logging
from decimal import Decimal
from typing import Tuple, Optional, Dict, Any

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from customer.models import Customer
from real_estate.models.contract import PropertyContract
from real_estate.models.resale import ContractAssignmentEndorsement
from real_estate.services.accounting_service import RealEstateAccountingService

logger = logging.getLogger(__name__)


class ContractAssignmentService:
    """
    خدمة الحوكمة والرقابة على عمليات التنازل عن العقود العقارية وإعادة البيع (Resale Transfers):
    - فحص أهلية العقد والتحقق من عدم وجود أقساط متأخرة واجبة السداد
    - التأكد من استيفاء نسبة السداد الدنيا المسموح بها للتنازل (Min Paid Percentage)
    - إصدار ملحق التنازل الرسمي وتوليد بصمة التحقق الرقمية SHA-256
    - نقل ملكية العقد وخطة التقسيط دفترياً للمشتري المتنازل إليه
    - مناقلة رصيد التزامات العقد (Contract Liability Subledger 21102) بين العملاء
    - إثبات وتحصيل رسوم التنازل الإدارية (Transfer Fee) وإيداعها كإيرادات أخرى
    """

    @classmethod
    def calculate_paid_and_remaining(cls, contract: PropertyContract) -> Tuple[Decimal, Decimal]:
        """
        حساب إجمالي المبالغ المسددة والرصيد المتبقي على العقد
        """
        down_payment = Decimal(str(contract.down_payment or Decimal('0.00')))
        installments_paid = Decimal('0.00')

        if contract.installment_plan:
            for item in contract.installment_plan.items.all():
                installments_paid += Decimal(str(item.paid_amount or Decimal('0.00')))

        total_paid = down_payment + installments_paid
        total_price = Decimal(str(contract.final_contract_price or Decimal('0.00')))
        remaining = max(Decimal('0.00'), total_price - total_paid)
        return total_paid, remaining

    @classmethod
    def validate_assignment_eligibility(
        cls,
        contract: PropertyContract,
        assignee_customer: Customer,
        min_paid_percentage: Decimal = Decimal('10.00')
    ) -> None:
        """
        التحقق من أهلية العقد للتنازل
        """
        if contract.status != PropertyContract.ContractStatus.ACTIVE:
            raise ValidationError(
                _("لا يمكن إجراء تنازل لعقد غير سارٍ (الحالة الحالية: %(status)s).") % {
                    'status': contract.get_status_display()
                }
            )

        if contract.customer_id == assignee_customer.id:
            raise ValidationError(_("لا يجوز التنازل لنفس العميل المشتري الأصلي المقيد بالعقد."))

        # فحص الأقساط المتأخرة
        if contract.installment_plan:
            from sale.models.installments import InstallmentItem
            overdue_exists = contract.installment_plan.items.exclude(
                cash_status=InstallmentItem.CashStatus.COLLECTED
            ).filter(
                due_date__lt=timezone.localdate()
            ).exists()
            if overdue_exists:
                raise ValidationError(
                    _("لا يمكن إتمام التنازل عن الوحدة لوجود أقساط مستحقة ومتأخرة عن السداد. يلزم تسوية المتأخرات أولاً.")
                )

        # فحص الحد الأدنى للمبالغ المسددة
        total_paid, remaining_amt = cls.calculate_paid_and_remaining(contract)
        total_price = Decimal(str(contract.final_contract_price or Decimal('0.00')))
        if total_price > Decimal('0.00'):
            paid_pct = (total_paid / total_price) * Decimal('100.00')
            if paid_pct < min_paid_percentage:
                raise ValidationError(
                    _("نسبة المسدد من قيمة العقد (%(paid).2f%%) أقل من النسبة المشروطة للتنازل (%(min).2f%%).") % {
                        'paid': paid_pct,
                        'min': min_paid_percentage
                    }
                )

    @classmethod
    def create_assignment_endorsement(
        cls,
        contract: PropertyContract,
        assignee_customer: Customer,
        administrative_fee_percentage: Decimal = Decimal('2.50'),
        resale_price: Optional[Decimal] = None,
        fee_payer: str = ContractAssignmentEndorsement.FeePayer.ASSIGNOR,
        min_paid_percentage: Decimal = Decimal('10.00'),
        notes: str = "",
        user=None
    ) -> ContractAssignmentEndorsement:
        """
        إنشاء ملحق تنازل رسمي جديد في حالة مسودة أو قيد الاعتماد
        """
        cls.validate_assignment_eligibility(contract, assignee_customer, min_paid_percentage)

        try:
            assignment_number = SequenceService.get_next_number(
                document_type=DocumentType.CONTRACT_ASSIGNMENT,
                date=timezone.localdate()
            )
        except Exception as exc:
            logger.warning(f"Failed to generate sequence via SequenceService: {exc}")
            assignment_number = f"TRF-{timezone.now().strftime('%Y%m%d%H%M%S')}-{contract.id}"

        total_paid, remaining_balance = cls.calculate_paid_and_remaining(contract)
        contract_price = Decimal(str(contract.final_contract_price))
        fee_pct = Decimal(str(administrative_fee_percentage or Decimal('0.00')))
        admin_fee = ((contract_price * fee_pct) / Decimal('100.00')).quantize(Decimal('0.01'))

        endorsement = ContractAssignmentEndorsement.objects.create(
            assignment_number=assignment_number,
            contract=contract,
            assignor_customer=contract.customer,
            assignee_customer=assignee_customer,
            assignment_date=timezone.localdate(),
            status=ContractAssignmentEndorsement.AssignmentStatus.DRAFT,
            original_contract_price=contract_price,
            paid_amount_at_assignment=total_paid,
            remaining_balance_at_assignment=remaining_balance,
            resale_price=resale_price,
            administrative_fee_percentage=fee_pct,
            administrative_fee=admin_fee,
            fee_payer=fee_payer,
            notes=notes,
            created_by=user
        )
        return endorsement

    @classmethod
    def approve_assignment(
        cls,
        endorsement: ContractAssignmentEndorsement,
        approver_user
    ) -> ContractAssignmentEndorsement:
        """
        اعتماد ملحق التنازل من الإدارة القانونية والمالية
        """
        if endorsement.status not in [
            ContractAssignmentEndorsement.AssignmentStatus.DRAFT,
            ContractAssignmentEndorsement.AssignmentStatus.UNDER_APPROVAL
        ]:
            raise ValidationError(
                _("لا يمكن اعتماد ملحق تنازل في حالة: %(status)s") % {
                    'status': endorsement.get_status_display()
                }
            )

        endorsement.status = ContractAssignmentEndorsement.AssignmentStatus.APPROVED
        endorsement.approved_by = approver_user
        endorsement.save(update_fields=['status', 'approved_by', 'updated_at'])
        return endorsement

    @classmethod
    def execute_contract_assignment(
        cls,
        endorsement: ContractAssignmentEndorsement,
        user,
        payment_account=None
    ) -> ContractAssignmentEndorsement:
        """
        تنفيذ التنازل وترحيله دفترياً:
        1. قفل السجلات ذرياً
        2. نقل ملكية العقد للعميل المتنازل إليه
        3. تحديث خطة الأقساط المرتبطة
        4. نقل التزام العقد (21102) في دفتر الأستاذ المساعد للعميل الجديد
        5. إثبات وتحصيل رسوم التنازل الإدارية
        6. تحديث حالة ملحق التنازل إلى منفذ ومرحل EXECUTED
        """
        with transaction.atomic():
            locked_endorsement = ContractAssignmentEndorsement.objects.select_for_update().get(pk=endorsement.pk)
            if locked_endorsement.status == ContractAssignmentEndorsement.AssignmentStatus.EXECUTED:
                raise ValidationError(_("ملحق التنازل تم تنفيذه وترحيله مسبقاً."))

            if locked_endorsement.status == ContractAssignmentEndorsement.AssignmentStatus.CANCELLED:
                raise ValidationError(_("ملحق التنازل ملغي ولا يمكن تنفيذه."))

            locked_contract = PropertyContract.objects.select_for_update().get(pk=locked_endorsement.contract_id)

            cls.validate_assignment_eligibility(
                locked_contract,
                locked_endorsement.assignee_customer,
                min_paid_percentage=Decimal('0.00')  # Already verified at creation
            )

            # 1. تحديث المشتري بخطة الأقساط التابعة أولاً لضمان اتساق ملكية الخطة مع العقد
            assignor = locked_contract.customer
            assignee = locked_endorsement.assignee_customer

            plan = locked_contract.installment_plan
            if plan:
                plan.customer = assignee
                plan.save(update_fields=['customer'])

            # 2. تحديث المشتري بالعقد العقاري
            locked_contract.customer = assignee
            locked_contract.save(update_fields=['customer', 'updated_at'])

            # 3. مناقلة الالتزام التعاقدي في دفتر الأستاذ المساعد للعملاء
            if locked_endorsement.paid_amount_at_assignment > Decimal("0.00"):
                RealEstateAccountingService.post_contract_assignment_subledger_transfer(
                    endorsement=locked_endorsement,
                    user=user,
                    reference=locked_endorsement.assignment_number
                )

            # 4. إثبات رسوم التنازل الإدارية
            if locked_endorsement.administrative_fee > Decimal("0.00") and payment_account:
                RealEstateAccountingService.post_contract_assignment_administrative_fee(
                    endorsement=locked_endorsement,
                    payment_account=payment_account,
                    user=user,
                    reference=locked_endorsement.assignment_number
                )

            # 5. تحديث حالة ملحق التنازل
            locked_endorsement.status = ContractAssignmentEndorsement.AssignmentStatus.EXECUTED
            locked_endorsement.executed_at = timezone.now()
            locked_endorsement.save(update_fields=['status', 'executed_at', 'updated_at'])

            logger.info(
                f"Contract assignment executed successfully: Contract {locked_contract.contract_number} "
                f"assigned from {assignor.name} to {assignee.name} by {user.username}"
            )
            return locked_endorsement
