# -*- coding: utf-8 -*-
"""
ContractInstallmentBindingService - خدمة ربط خطط التقسيط بالعقود العقارية
تضمن قفل الحركات المالية وحظر التبديل بعد بدء السداد أو التخصيص، وتطبق بروتوكول الأقفال الهرمي.
"""
import logging
from django.db import transaction, models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from sale.models.installments import InstallmentPlan

logger = logging.getLogger(__name__)


class ContractBindingIntegrityError(ValidationError):
    """خطأ حوكمة سلامة ربط خطة الأقساط بالعقد"""
    pass


class ContractInstallmentBindingService:
    """
    خدمة الربط الذرية المحكمة بين العقود وخطط التقسيط
    """

    @classmethod
    def _has_financial_activity(cls, target_plan) -> bool:
        """
        التحقق الدقيق والشامل من وجود أي حركة مالية (سواء كانت سارية حالياً أو حركات تاريخية معكوسة).
        بمجرد دخول الخطة في قيود أو دفاتر الأستاذ، تصبح ملكيتها ومصدرها غير قابلين للتغيير.
        """
        from cheques.models.allocation import ChequeInvoiceAllocation, AllocationStatus
        from sale.models.installments import InstallmentSettlement, InstallmentRescheduleLog

        # 1. الحركات السارية القائمة (Active Financial Movements)
        if target_plan.items.filter(paid_amount__gt=0).exists():
            return True
        if target_plan.items.filter(coverage_cheque_amount__gt=0).exists():
            return True
        if target_plan.items.exclude(paper_coverage='UNCOVERED').exists():
            return True
        if ChequeInvoiceAllocation.objects.filter(
            installment_item__plan=target_plan, 
            allocation_status=AllocationStatus.APPLIED
        ).exists():
            return True

        # 2. الحركات التاريخية والمعكوسة (Historical & Reversed Financial Audit Trail)
        # حظر التغيير يشمل الحركات المعكوسة لأن الخطة أصبحت جزءاً من سجلات المحاسبة والتدقيق الضريبي
        if ChequeInvoiceAllocation.objects.filter(installment_item__plan=target_plan).exists():
            return True
        if target_plan.items.filter(payments__isnull=False).exists():
            return True
        if InstallmentSettlement.objects.filter(
            models.Q(plan=target_plan) | models.Q(installment_item__plan=target_plan)
        ).exists():
            return True
        if InstallmentRescheduleLog.objects.filter(installment__plan=target_plan).exists():
            return True

        return False

    @classmethod
    def validate_plan_ownership(cls, contract, target_plan):
        """
        التحقق الاستباقي الصارم من تطابق ملكية الخطة قبل الحفظ
        """
        if not target_plan:
            return
        if target_plan.sale_id is not None:
            raise ContractBindingIntegrityError(
                _("خطة الأقساط رقم #%(plan_id)s مرتبطة بالفعل بفاتورة بيع.") % {'plan_id': target_plan.id}
            )
        if getattr(contract, 'customer_id', None) and target_plan.customer_id != contract.customer_id:
            raise ContractBindingIntegrityError(
                _("خطة التقسيط تنتمي لعميل مختلف (#%(plan_cust)s) عن عميل العقد (#%(contract_cust)s).") % {
                    'plan_cust': target_plan.customer_id,
                    'contract_cust': contract.customer_id
                }
            )
        # التحقق من أن الخطة غير مرتبطة بعقد عقاري آخر
        other_contract = getattr(target_plan, 'property_contract', None)
        if other_contract and other_contract.id != getattr(contract, 'id', None):
            raise ContractBindingIntegrityError(
                _("خطة الأقساط رقم #%(plan_id)s مرتبطة بالفعل بعقد عقاري آخر رقم #%(contract_id)s.") % {
                    'plan_id': target_plan.id,
                    'contract_id': other_contract.id
                }
            )

    @classmethod
    def validate_plan_switch(cls, contract, old_plan_id, new_plan):
        """
        التحقق الصارم وقفل الخطة القديمة والجديدة قبل كتابة تغيير الخطة في قاعدة البيانات
        حماية صارمة: منع تبديل أي خطة بدأت بها حركات سداد أو شيكات حتى لنفس العميل
        """
        with transaction.atomic():
            if old_plan_id:
                old_plan = InstallmentPlan.objects.select_for_update().filter(pk=old_plan_id).first()
                if old_plan and cls._has_financial_activity(old_plan):
                    raise ContractBindingIntegrityError(
                        _("حظر تبديل الخطة: الخطة الحالية للعقد #%(plan_id)s دخلت في مسار مالي مسجل (حركات قائمة أو تاريخية).") % {
                            'plan_id': old_plan.id
                        }
                    )

            if new_plan:
                cls.validate_plan_ownership(contract=contract, target_plan=new_plan)
                locked_new_plan = InstallmentPlan.objects.select_for_update().filter(pk=new_plan.pk).first()
                if locked_new_plan and cls._has_financial_activity(locked_new_plan):
                    raise ContractBindingIntegrityError(
                        _("حظر الربط: الخطة المستهدفة #%(plan_id)s محملة بحركات سداد أو تخصيص أوراق قبض سابقة.") % {
                            'plan_id': locked_new_plan.id
                        }
                    )

    @classmethod
    def bind_contract_to_plan(cls, contract, target_plan, user=None):
        """اسم بديل للتوافق مع استدعاءات نماذج العقود"""
        return cls.bind_plan_to_contract(contract=contract, new_plan=target_plan)

    @classmethod
    def bind_plan_to_contract(cls, contract, new_plan):
        """
        ربط خطة تقسيط بعقد عقاري مع حراسة تزامنية صارمة وبروتوكول أقفال هرمي
        """
        # 0. التحقق الصارم من صحة ملكية الخطة وتطابق العميل دائماً حتى قبل الفحص التكراري
        cls.validate_plan_ownership(contract=contract, target_plan=new_plan)

        with transaction.atomic():
            # 1. Idempotency Guard: التحقق من الحالة المحفوظة في قاعدة البيانات
            persisted_plan_id = None
            if contract.pk:
                from real_estate.models.contract import PropertyContract
                persisted_plan_id = PropertyContract.objects.filter(
                    pk=contract.pk
                ).values_list('installment_plan_id', flat=True).first()

            if persisted_plan_id == new_plan.pk and getattr(contract, 'installment_plan_id', None) == new_plan.pk:
                return contract

            # 2. Hierarchical Deadlock-Free Lock Ordering (بروتوكول الأقفال الهرمي الصاعد)
            current_plan_id = getattr(contract, 'installment_plan_id', None)
            plan_ids = sorted(filter(None, [current_plan_id, new_plan.pk]))
            locked_plans = {
                p.id: p for p in InstallmentPlan.objects.filter(id__in=plan_ids).select_for_update().order_by('id')
            }
            locked_new_plan = locked_plans[new_plan.pk]

            # 3. Prohibit switching plan after financial movements started (Even for the same customer)
            if current_plan_id is not None:
                old_plan = locked_plans.get(current_plan_id)
                if old_plan and cls._has_financial_activity(old_plan):
                    raise ContractBindingIntegrityError(
                        _("حظر تبديل الخطة: الخطة الحالية للعقد #%(plan_id)s دخلت في مسار مالي مسجل (حركات قائمة أو تاريخية).") % {
                            'plan_id': old_plan.id
                        }
                    )

            # 4. Prohibit binding to a new plan that already has prior financial movements
            if cls._has_financial_activity(locked_new_plan):
                raise ContractBindingIntegrityError(
                    _("حظر الربط: الخطة المستهدفة #%(plan_id)s محملة بحركات سداد أو تخصيص أوراق قبض سابقة.") % {
                        'plan_id': locked_new_plan.id
                    }
                )

            # 5. Prohibit linking a plan already owned by a merchandise invoice (Sale)
            if locked_new_plan.sale_id is not None:
                raise ContractBindingIntegrityError(
                    _("خطة الأقساط رقم #%(plan_id)s مرتبطة بالفعل بفاتورة بيع #%(sale_id)s ولا يمكن ربطها بعقد.") % {
                        'plan_id': locked_new_plan.id,
                        'sale_id': locked_new_plan.sale_id
                    }
                )

            # 6. Prohibit linking a plan already owned by another property contract
            if hasattr(locked_new_plan, 'property_contract') and locked_new_plan.property_contract.id != getattr(contract, 'id', None):
                raise ContractBindingIntegrityError(
                    _("خطة الأقساط رقم #%(plan_id)s مرتبطة بالفعل بعقد عقاري آخر رقم #%(contract_id)s.") % {
                        'plan_id': locked_new_plan.id,
                        'contract_id': locked_new_plan.property_contract.id
                    }
                )

            # 7. Customer identity verification
            if getattr(contract, 'customer_id', None) and locked_new_plan.customer_id != contract.customer_id:
                raise ContractBindingIntegrityError(
                    _("لا يمكن ربط خطة أقساط خاصة بعميل آخر (#%(plan_cust)s) بهذا العقد (#%(contract_cust)s).") % {
                        'plan_cust': locked_new_plan.customer_id,
                        'contract_cust': contract.customer_id
                    }
                )

            # 8. Atomic Binding Execution
            contract.installment_plan = locked_new_plan
            if hasattr(contract, 'save'):
                contract.save(update_fields=['installment_plan'])
            return contract
