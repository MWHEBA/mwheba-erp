# -*- coding: utf-8 -*-
"""
FinishingService & Pricing Engine
MWHEBA ERP — Track 2: Finishing Packages, Specs Directory, and Governed Dual-Speed Workflow
"""
import logging
from decimal import Decimal
from datetime import date, timedelta
from typing import Dict, Any, Optional, Tuple, List

from django.db import transaction, models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from real_estate.models.unit import PropertyUnit
from real_estate.models.contract import PropertyContract, ContractCoOwner
from real_estate.models.pricing import UnitPricingMatrixConfig
from real_estate.models.booking import UnitBooking
from real_estate.models.finishing import (
    FinishingWorkspace,
    FinishingBrand,
    ContractualCreditSchedule,
    FinishingItemSpec,
    FinishingPackageTemplate,
    FinishingPackageItem,
    UnitFinishingOrder,
    UnitFinishingOrderItem,
    BookingPreContractVariationStudy,
    FinishingAdvanceDeposit,
)
from sale.models.installments import InstallmentItem
from financial.models import EnterpriseApprovalRequest, EnterpriseApprovalRule

logger = logging.getLogger(__name__)


class FinishingPricingService:
    """
    خدمة تسعير المقايسات الميدانية وتجميد الأسعار:
    - حساب التكلفة المادية التراكمية، المصنعيات، التكسير، ونسب الإشراف الهندسي.
    - احتساب رصيد استرداد بنود نصف التشطيب التعاقدية (Core & Shell Credit) وخصمه.
    - احتساب الدفعة المقدمة القانونية الإلزامية (35%).
    - تجميد الأسعار وإدارة مهلة صلاحية العرض.
    - توليد الفراغات المعمارية القياسية للمشاريع منعاً للشاشات البيضاء.
    """

    @classmethod
    @transaction.atomic
    def provision_default_workspaces(cls, project) -> List[FinishingWorkspace]:
        """
        الوقاية من الشاشات البيضاء (Auto-Provisioning of Workspaces):
        توليد آلي للفراغات المعمارية القياسية للمشروع في حال عدم وجود فراغات مسجلة مسبقاً.
        """
        if FinishingWorkspace.objects.filter(project=project).exists():
            return list(FinishingWorkspace.objects.filter(project=project, is_active=True).order_by('sort_order', 'id'))

        default_defs = [
            {'name': 'الريسبشن والاستقبال', 'code': 'REC', 'is_wet_area': False, 'standard_height_meters': Decimal('2.90'), 'sort_order': 1},
            {'name': 'غرفة نوم رئيسية (ماستر)', 'code': 'MBR', 'is_wet_area': False, 'standard_height_meters': Decimal('2.90'), 'sort_order': 2},
            {'name': 'غرفة نوم أطفال / ضيوف', 'code': 'BR2', 'is_wet_area': False, 'standard_height_meters': Decimal('2.90'), 'sort_order': 3},
            {'name': 'المطبخ', 'code': 'KIT', 'is_wet_area': True, 'standard_height_meters': Decimal('2.90'), 'sort_order': 4},
            {'name': 'حمام رئيسي', 'code': 'BTH_MAIN', 'is_wet_area': True, 'standard_height_meters': Decimal('2.90'), 'sort_order': 5},
            {'name': 'حمام ضيوف', 'code': 'BTH_GUEST', 'is_wet_area': True, 'standard_height_meters': Decimal('2.90'), 'sort_order': 6},
            {'name': 'تراس / شرفة', 'code': 'TERRACE', 'is_wet_area': False, 'standard_height_meters': Decimal('2.90'), 'sort_order': 7},
        ]
        created = []
        for d in default_defs:
            ws, _ = FinishingWorkspace.objects.get_or_create(
                project=project,
                code=d['code'],
                defaults={
                    'name': d['name'],
                    'is_wet_area': d['is_wet_area'],
                    'standard_height_meters': d['standard_height_meters'],
                    'sort_order': d['sort_order'],
                    'is_active': True,
                }
            )
            created.append(ws)
        logger.info(f"Auto-provisioned {len(created)} default workspaces for project {project.name}")
        return created

    @classmethod
    @transaction.atomic
    def calculate_order_pricing(cls, order: UnitFinishingOrder) -> Dict[str, Decimal]:
        """
        حساب تسعير أمر التشطيب وتحديث الموديل بناءً على بنود المقايسة التفصيلية.
        """
        if cls.is_price_frozen_and_valid(order):
            logger.info(f"Order {order.order_number} pricing is frozen and currently valid until {order.offer_expires_at}. Preserving approved prices.")
            return {
                'material_total': order.material_cost_total or Decimal('0.00'),
                'labor_total': order.labor_cost_total or Decimal('0.00'),
                'demolition_total': order.demolition_cost_total or Decimal('0.00'),
                'supervision_fee': order.supervision_fee_total or Decimal('0.00'),
                'credit_total': order.core_shell_credit_total or Decimal('0.00'),
                'gross_amount': order.gross_finishing_amount or Decimal('0.00'),
                'net_price': order.net_finishing_price or Decimal('0.00'),
                'advance_required': order.advance_deposit_required or Decimal('0.00'),
            }

        items = order.items.select_related('spec', 'spec__credit_schedule').all()

        material_total = Decimal('0.00')
        labor_total = Decimal('0.00')
        demolition_total = Decimal('0.00')
        specialty_total = Decimal('0.00')
        credit_total = Decimal('0.00')
        items_selling_total = Decimal('0.00')

        for item in items:
            # 1. حساب الكمية الإجمالية متضمنة نسبة الهالك
            scrap_rate = item.scrap_rate or Decimal('0.00')
            qty = item.quantity or Decimal('0.00')
            gross_qty = (qty * (Decimal('1.00') + (scrap_rate / Decimal('100.00')))).quantize(Decimal('0.01'))
            item.gross_quantity = gross_qty

            # 2. حساب إجمالي سعر البيع للبند
            unit_price = item.unit_selling_price or (item.spec.client_selling_rate if item.spec else Decimal('0.00'))
            item.unit_selling_price = unit_price
            item_total = (gross_qty * unit_price).quantize(Decimal('0.01'))
            item.total_selling_price = item_total
            items_selling_total += item_total

            # 3. فصل التكاليف (مواد / مصنعية / تكسير / تخصصي / خامات العميل)
            if item.supply_source == 'OWNER_SUPPLIED':
                # خامات العميل الموردة: لا تكلفة مواد على الشركة
                if item.spec:
                    item_lab = (gross_qty * (item.spec.standard_labor_cost or Decimal('0.00'))).quantize(Decimal('0.01'))
                    labor_total += item_lab
            elif item.is_demolition_rework:
                demolition_total += item_total
            elif item.is_custom_specialty:
                specialty_total += item_total
            elif item.spec:
                item_mat = (gross_qty * (item.spec.standard_material_cost or Decimal('0.00'))).quantize(Decimal('0.01'))
                item_lab = (gross_qty * (item.spec.standard_labor_cost or Decimal('0.00'))).quantize(Decimal('0.01'))
                material_total += item_mat
                labor_total += item_lab
            else:
                specialty_total += item_total

            # 4. احتساب رصيد نصف التشطيب المسترد (Core & Shell Credit)
            if item.spec and item.spec.credit_schedule and not item.is_demolition_rework:
                credit_rate = getattr(item.spec.credit_schedule, 'contractual_credit_rate', Decimal('0.00')) or Decimal('0.00')
                item_credit = (gross_qty * credit_rate).quantize(Decimal('0.01'))
                item.core_shell_credit = item_credit
                credit_total += item_credit
            else:
                item.core_shell_credit = Decimal('0.00')

            item.save(update_fields=['gross_quantity', 'unit_selling_price', 'total_selling_price', 'core_shell_credit'])

        # 5. نسبة الإشراف الهندسي (تطبق على تكاليف التنفيذ)
        supervision_base = material_total + labor_total + demolition_total + specialty_total
        supervision_rate = Decimal('10.00')  # 10% standard supervision
        supervision_fee = (supervision_base * (supervision_rate / Decimal('100.00'))).quantize(Decimal('0.01'))

        # 6. المجموع الإجمالي والصافي
        gross_amount = (supervision_base + supervision_fee - credit_total).quantize(Decimal('0.01'))
        if gross_amount < Decimal('0.00'):
            gross_amount = Decimal('0.00')

        discount = order.promotional_discount or Decimal('0.00')
        net_price = (gross_amount - discount).quantize(Decimal('0.01'))
        if net_price < Decimal('0.00'):
            net_price = Decimal('0.00')

        # 7. الدفعة المقدمة القانونية 35%
        advance_required = (net_price * Decimal('0.35')).quantize(Decimal('0.01'))

        # 8. حفظ النتائج في أمر التشطيب
        order.material_cost_total = material_total
        order.labor_cost_total = labor_total
        order.demolition_cost_total = demolition_total
        order.supervision_fee_total = supervision_fee
        order.core_shell_credit_total = credit_total
        order.gross_finishing_amount = gross_amount
        order.net_finishing_price = net_price
        order.advance_deposit_required = advance_required
        order.remaining_balance = (net_price - (order.total_deposit_paid or Decimal('0.00'))).quantize(Decimal('0.01'))

        order.save(update_fields=[
            'material_cost_total',
            'labor_cost_total',
            'demolition_cost_total',
            'supervision_fee_total',
            'core_shell_credit_total',
            'gross_finishing_amount',
            'net_finishing_price',
            'advance_deposit_required',
            'remaining_balance'
        ])

        return {
            'material_total': material_total,
            'labor_total': labor_total,
            'demolition_total': demolition_total,
            'supervision_fee': supervision_fee,
            'credit_total': credit_total,
            'gross_amount': gross_amount,
            'net_price': net_price,
            'advance_required': advance_required,
        }

    @classmethod
    def freeze_pricing(cls, order: UnitFinishingOrder, validity_days: int = 15) -> UnitFinishingOrder:
        """
        تجميد أسعار المقايسة لمهلة محددة (افتراضياً 15 يوماً).
        يحظر تعديل الأساس المالي أو تباعد الأقساط إذا تم إنشاء قيد استحقاق مالي مرحل للطلب.
        """
        if order.accrual_journal_entry_id or cls.is_price_frozen_and_valid(order):
            logger.info(f"Order {order.order_number} has an existing accrual or active freeze. Preserving approved prices.")
            now = timezone.now()
            order.price_freeze_date = order.price_freeze_date or now
            order.offer_validity_days = validity_days
            order.offer_expires_at = now.date() + timedelta(days=validity_days)
            order.save(update_fields=['price_freeze_date', 'offer_validity_days', 'offer_expires_at'])
            return order

        order.price_freeze_date = None
        order.offer_expires_at = None
        cls.calculate_order_pricing(order)
        now = timezone.now()
        order.price_freeze_date = now
        order.offer_validity_days = validity_days
        order.offer_expires_at = now.date() + timedelta(days=validity_days)
        order.save(update_fields=['price_freeze_date', 'offer_validity_days', 'offer_expires_at'])
        logger.info(f"Order {order.order_number} pricing frozen until {order.offer_expires_at}")
        return order

    @classmethod
    def is_price_frozen_and_valid(cls, order: UnitFinishingOrder) -> bool:
        """
        التحقق من سريان تجميد الأسعار وعدم انتهاء مهلة العرض.
        """
        if not order.price_freeze_date or not order.offer_expires_at:
            return False
        return order.offer_expires_at >= timezone.now().date()


class FinishingWorkflowEngine:
    """
    محرك مسار الاعتماد المزدوج وحوكمة صمامات الأمان:
    - إدارة المسار السداسي المحوكم (MAJOR_GOVERNED) والمسار السريع (FAST_TRACK).
    - صمام فحص تعثر الأقساط القديمة (Arrears Hard Lock).
    - صمام توقيع الشركاء على الشيوع والتوكيلات (Joint Ownership Signatory Guard).
    - صمام تمديد موعد التسليم التعاقدي وإسقاط غرامات التأخير.
    - الربط مع محرك الاعتماد المركزي للمؤسسة (EnterpriseApprovalRequest).
    """

    STAGE_HIERARCHY = [
        'CUSTOMER_SERVICE',
        'TECHNICAL_OFFICE',
        'CHANGES_MANAGER',
        'COST_ACCOUNTING',
        'FINANCE_CFO',
        'CLIENT_APPROVAL',
        'IN_EXECUTION',
        'COMPLETED',
        'CANCELLED'
    ]

    @classmethod
    def is_fast_track_eligible(cls, order: UnitFinishingOrder) -> bool:
        """
        التحقق من استحقاق المسار السريع:
        1. القيمة الإجمالية لا تتجاوز 25,000 ج.م
        2. خلو الطلب تماماً من أي أعمال تكسير أو تعديل إنشائي
        3. كافة البنود تكون ديكورية / تشطيب سطحي
        """
        if order.gross_finishing_amount > Decimal('25000.00'):
            return False
        if order.demolition_cost_total > Decimal('0.00'):
            return False
        has_demolition = order.items.filter(is_demolition_rework=True).exists()
        if has_demolition:
            return False
        return True

    @classmethod
    def validate_stage_transition(
        cls,
        order: UnitFinishingOrder,
        target_stage: str,
        user=None
    ) -> Tuple[bool, Optional[str]]:
        """
        التدقيق في شروط وصمامات الانتقال بين المراحل.
        """
        current_stage = order.current_stage

        if target_stage not in cls.STAGE_HIERARCHY:
            return False, _(f"مرحلة الهدف {target_stage} غير معتمدة بالنظام.")

        # حظر إعادة فتح أو استئناف الطلبات الملغاة أو المكتملة عبر الانتقال العادي
        if current_stage in ['CANCELLED', 'COMPLETED']:
            return False, _(f"لا يمكن الانتقال من المرحلة النهائية '{current_stage}'. يتطلب ذلك إجراء إعادة فتح معتمد ومستقل.")

        if target_stage == 'CANCELLED':
            return True, None

        # 1. صمام فحص تعثر الأقساط (Arrears Hard Lock)
        if order.contract and order.contract.installment_plan:
            overdue_items = InstallmentItem.objects.filter(
                plan=order.contract.installment_plan,
                due_date__lt=timezone.now().date(),
                paid_amount__lt=models.F('total_amount')
            )
            if overdue_items.exists() and not order.cfo_overdue_override:
                return False, _("يوجد أقساط مستحقة متأخرة على الوحدة العقارية بالعقد. يلزم سدادها أو الحصول على تأشيرة تجاوز من المدير المالي.")

        # 2. التحقق من صلاحية تجميد الأسعار عند الوصول للاعتماد المالي والعميل
        if target_stage in ['FINANCE_CFO', 'CLIENT_APPROVAL']:
            if not FinishingPricingService.is_price_frozen_and_valid(order):
                return False, _("مهلة تجميد أسعار المقايسة منتهية أو لم يتم تجميدها بعد. يلزم إعادة التسعير والتجميد أولاً.")

        # 3. صمام تعدد الملاك وتوقيع الشركاء على الشيوع واعتماد الإدارة المالية
        if target_stage == 'CLIENT_APPROVAL':
            # التحقق من اعتماد المدير المالي إذا كان هناك طلب اعتماد معلق
            if order.approval_request and order.approval_request.status != 'APPROVED':
                return False, _("طلب الاعتماد المالي لا يزال قيد المراجعة أو غير معتمد من المدير المالي (CFO).")

            if order.contract and order.contract.co_owners.exists():
                if not order.all_co_owners_signed and not bool(order.co_owners_power_of_attorney_file):
                    return False, _("يلزم توقيع كافة الملاك الشركاء على الشيوع أو إرفاق توكيل رسمي مسجل ومعتمد للمالك الحاضر.")

            # صمام تمديد موعد التسليم وإسقاط غرامات التأخير
            if not order.delay_penalty_waiver_signed:
                return False, _("يلزم توقيع إقرار تمديد موعد التسليم التعاقدي وإسقاط غرامات التأخير الناتجة عن التشطيبات.")

        # 4. صمام الدفعة المقدمة 35% قبل التحويل للتنفيذ الميداني
        if target_stage == 'IN_EXECUTION':
            deposit_paid = order.total_deposit_paid or Decimal('0.00')
            required = order.advance_deposit_required or Decimal('0.00')
            if deposit_paid < required:
                return False, _(f"لا يمكن بدء التنفيذ الميداني قبل سداد الدفعة المقدمة المقررة 35% (المسدد: {deposit_paid} من {required} ج.م).")

        # 5. منطق المسار السريع Fast-Track مقابل المسار السداسي المحوكم
        if order.workflow_speed == 'FAST_TRACK':
            if not cls.is_fast_track_eligible(order):
                return False, _("الطلب لا يستوفي شروط المسار السريع (تجاوز المبلغ 25 ألف ج.م أو وجود تكسير). يلزم تحويله للمسار السداسي.")
            # لا يسمح بالقفز المباشر إلى المكتمل دون المرور بالعميل والتنفيذ
            if target_stage == 'COMPLETED' and current_stage not in ['IN_EXECUTION']:
                return False, _("لا يمكن إنهاء وتسليم الطلب في المسار السريع إلا بعد موافقة العميل والتنفيذ الميداني.")
            if target_stage == 'IN_EXECUTION' and current_stage not in ['CLIENT_APPROVAL']:
                return False, _("لا يمكن بدء التنفيذ الميداني في المسار السريع إلا بعد موافقة العميل.")
            return True, None

        # في المسار السداسي، نلزم بالتتابع
        curr_idx = cls.STAGE_HIERARCHY.index(current_stage) if current_stage in cls.STAGE_HIERARCHY else 0
        target_idx = cls.STAGE_HIERARCHY.index(target_stage)
        if target_idx > curr_idx + 1 and target_stage != 'CANCELLED':
            return False, _(f"لا يمكن تخطي المراحل في المسار السداسي المحوكم. المرحلة الحالية: {current_stage}")

        return True, None

    @classmethod
    @transaction.atomic
    def transition_order_stage(
        cls,
        order: UnitFinishingOrder,
        target_stage: str,
        user=None,
        notes: str = ""
    ) -> UnitFinishingOrder:
        """
        تنفيذ انتقال المرحلة وإطلاق الأحداث المرتبطة (مثل الاعتماد المركزي).
        """
        can_move, error_msg = cls.validate_stage_transition(order, target_stage, user)
        if not can_move:
            raise ValidationError(error_msg)

        old_stage = order.current_stage
        order.current_stage = target_stage

        # إذا كانت المرحلة FINANCE_CFO ننشئ طلب اعتماد مركزي
        if target_stage == 'FINANCE_CFO':
            rule, _created = EnterpriseApprovalRule.objects.get_or_create(
                module='REAL_ESTATE',
                approver_role='CFO',
                defaults={
                    'rule_name': 'اعتماد مقايسات وتشطيبات التطوير العقاري',
                    'min_amount': Decimal('0.00'),
                    'max_amount': Decimal('999999999.00'),
                    'currency': 'EGP',
                    'approval_level': 1,
                    'is_active': True
                }
            )
            approval_req = EnterpriseApprovalRequest.objects.create(
                module='REAL_ESTATE',
                reference_id=str(order.order_number),
                rule=rule,
                requested_by=user or order.created_by,
                status='PENDING',
                comments=f"اعتماد مقايسة تشطيب للوحدة {order.unit.unit_code} بقيمة إجمالية {order.net_finishing_price} ج.م"
            )
            order.approval_request = approval_req

        # ترحيل تاريخ التسليم التعاقدي عند توقيع العميل (مرة واحدة فقط لضمان الـ Idempotence)
        if target_stage == 'CLIENT_APPROVAL':
            if order.contract and order.contract.delivery_date:
                if order.original_contract_delivery_date is None:
                    order.original_contract_delivery_date = order.contract.delivery_date
                    duration = order.execution_duration_days or 90
                    amended_date = order.contract.delivery_date + timedelta(days=duration)
                    order.amended_contract_delivery_date = amended_date
                    order.contract.delivery_date = amended_date
                    order.contract.save(update_fields=['delivery_date'])

        order.save(update_fields=[
            'current_stage',
            'approval_request',
            'original_contract_delivery_date',
            'amended_contract_delivery_date',
            'updated_at'
        ])

        logger.info(f"Order {order.order_number} transitioned from {old_stage} to {target_stage} by {user}")
        return order


class FinishingBulkPricingSyncService:
    """
    خدمة مزامنة تسعير التشطيب في مصفوفة الوحدات:
    - دمج باقات وسعر متر التشطيب ضمن جدول تسعير الوحدات الجماعي UnitPricingMatrixConfig.
    - حساب القيمة الإجمالية للوحدة متضمنة سعر المتر التشطيبي.
    """

    @classmethod
    @transaction.atomic
    def sync_pricing_matrix_with_finishing(cls, pricing_config: UnitPricingMatrixConfig) -> int:
        """
        مزامنة جدول تسعير الوحدات وإضافة تكلفة التشطيب المعتمدة لكل وحدة تابعة.
        """
        finishing_rate = pricing_config.finishing_meter_rate or Decimal('0.00')
        package = pricing_config.default_finishing_package

        if package and finishing_rate == Decimal('0.00'):
            finishing_rate = package.price_per_square_meter or Decimal('0.00')

        units_qs = PropertyUnit.objects.filter(project=pricing_config.project)
        if pricing_config.block:
            units_qs = units_qs.filter(block=pricing_config.block)

        updated_count = 0
        for unit in units_qs:
            gross = unit.gross_area or Decimal('0.00')
            finishing_addon = (gross * finishing_rate).quantize(Decimal('0.01'))

            # تحديث تفصيل التسعير
            breakdown = unit.pricing_breakdown or {}
            breakdown['finishing_meter_rate'] = str(finishing_rate)
            breakdown['finishing_total_addon'] = str(finishing_addon)
            if package:
                breakdown['finishing_package_name'] = package.name

            unit.pricing_breakdown = breakdown
            unit.save(update_fields=['pricing_breakdown'])
            updated_count += 1

        logger.info(f"Synchronized finishing pricing for {updated_count} units under config {pricing_config.name}")
        return updated_count

    @classmethod
    def generate_unit_finishing_estimate(
        cls,
        unit: PropertyUnit,
        package: FinishingPackageTemplate
    ) -> Decimal:
        """
        حساب التكلفة التقديرية لتشطيب الوحدة بباقة معينة.
        """
        gross = unit.gross_area or Decimal('0.00')
        rate = package.price_per_square_meter or Decimal('0.00')
        return (gross * rate).quantize(Decimal('0.01'))


class FinishingPreContractBookingStudyService:
    """
    خدمة دراسة جدوى تعديلات الحجز المبدئي للوحدات:
    - تسجيل وتوثيق طلبات التعديل المعماري للعميل أثناء مرحلة الحجز المبدئي وقبل التعاقد.
    - دراسة الجدوى الهندسية والتكلفة التقديرية لمنع الوعود الشفهية.
    - تحويل دراسة الجدوى المعتمدة إلى أمر تشطيب رسمي فور تحرير العقد.
    """

    @classmethod
    def create_study_for_booking(
        cls,
        booking: UnitBooking,
        requested_changes_summary: str,
        preliminary_estimated_cost: Decimal = Decimal('0.00'),
        user=None
    ) -> BookingPreContractVariationStudy:
        """
        إنشاء دراسة جدوى هندسية لحجز مبدئي.
        """
        study = BookingPreContractVariationStudy.objects.create(
            booking=booking,
            unit=booking.unit,
            requested_changes_summary=requested_changes_summary,
            is_architecturally_feasible=True,
            preliminary_estimated_cost=preliminary_estimated_cost,
            reviewed_by=user,
            reviewed_at=timezone.now()
        )
        logger.info(f"Created pre-contract study {study.id} for booking {booking.booking_number}")
        return study

    @classmethod
    @transaction.atomic
    def convert_study_to_finishing_order(
        cls,
        study: BookingPreContractVariationStudy,
        contract: PropertyContract,
        user=None
    ) -> UnitFinishingOrder:
        """
        تحويل دراسة الجدوى المعتمدة إلى أمر تشطيب رسمي عند توقيع العقد.
        """
        if not study.is_architecturally_feasible:
            raise ValidationError(_("لا يمكن تحويل دراسة غير مجدية هندسياً إلى أمر تشطيب رسمي."))

        order_num = f"FO-{contract.contract_number}"
        order, created = UnitFinishingOrder.objects.get_or_create(
            order_number=order_num,
            defaults={
                'unit': study.unit,
                'contract': contract,
                'customer': contract.customer,
                'title': f"تعديلات الحجز المحولة - {contract.contract_number}",
                'order_type': 'CUSTOM_VARIATION',
                'pricing_mode': 'FIXED_PRICE_BOQ',
                'workflow_speed': 'MAJOR_GOVERNED',
                'current_stage': 'TECHNICAL_OFFICE',
                'gross_finishing_amount': study.preliminary_estimated_cost,
                'advance_deposit_required': (study.preliminary_estimated_cost * Decimal('0.35')).quantize(Decimal('0.01')),
                'notes': f"تم تحويل هذا الطلب تلقائياً من دراسة الحجز المبدئي رقم {study.id}:\n{study.requested_changes_summary}",
                'created_by': user or contract.created_by
            }
        )

        logger.info(f"Converted study {study.id} to finishing order {order.order_number}")
        return order
