# -*- coding: utf-8 -*-
"""
WBS Tree Governance & Unit-to-WBS Bridge Services
MWHEBA ERP — Track 3: Architectural WBS, Tree Governance & Unit Execution Bridge
"""
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple

from django.db import transaction
from django.db.models import Avg, Sum, Q, F
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyUnit,
    ProjectActivity,
    UnitSiteProgressRecord,
)

logger = logging.getLogger(__name__)


class UnitToWbsBridgeService:
    """
    جسر الربط الهيكلي بين حزم أعمال الـ WBS ومراحل التشطيب الميدانية للوحدات (Unit-to-WBS Bridge):
    - يربط حزم أعمال المقايسة بأنشطة الموقع المعمارية للـ 32 بنداً.
    - يدعم الحساب على مستوى المشروع ككل أو على مستوى عمارة محددة (Block-specific WBS).
    - يدعم ثلاثة أنماط للربط:
      1. تشطيبات كافة الوحدات (ALL_UNIT_FINISHES): سحب متوسط إنجاز الشقق الحالية.
      2. مجموعة أعمال متخصصة (TRADE_CATEGORY): كالمباني، المحارة، السباكة، السيراميك، الدهانات.
      3. بند تفصيلي محدد (SPECIFIC_TRADE): كسيراميك الأرضيات أو عزل السطح أو قد الحوائط.
    """

    TRADE_CATEGORY_MAP: Dict[str, List[str]] = {
        ProjectActivity.TradeCategory.MASONRY: [
            UnitSiteProgressRecord.InspectionTrade.MASONRY_QADD,
            UnitSiteProgressRecord.InspectionTrade.MASONRY_FULL,
        ],
        ProjectActivity.TradeCategory.ELECTRICAL: [
            UnitSiteProgressRecord.InspectionTrade.ELEC_PIPES,
            UnitSiteProgressRecord.InspectionTrade.ELEC_BOXES,
            UnitSiteProgressRecord.InspectionTrade.ELEC_WIRING,
            UnitSiteProgressRecord.InspectionTrade.ELEC_FITTING,
        ],
        ProjectActivity.TradeCategory.PLASTER: [
            UnitSiteProgressRecord.InspectionTrade.PLASTER_SPATTER,
            UnitSiteProgressRecord.InspectionTrade.PLASTER_STRINGS,
            UnitSiteProgressRecord.InspectionTrade.PLASTER_FILLING,
            UnitSiteProgressRecord.InspectionTrade.PLASTER_EDGES,
            UnitSiteProgressRecord.InspectionTrade.PLASTER_FINISH,
        ],
        ProjectActivity.TradeCategory.PLUMBING: [
            UnitSiteProgressRecord.InspectionTrade.PLUMB_WATERPROOF,
            UnitSiteProgressRecord.InspectionTrade.PLUMB_FEEDING,
            UnitSiteProgressRecord.InspectionTrade.PLUMB_DRAINAGE,
            UnitSiteProgressRecord.InspectionTrade.PLUMB_TUB_FIX,
            UnitSiteProgressRecord.InspectionTrade.PLUMB_FITTING,
        ],
        ProjectActivity.TradeCategory.CERAMIC: [
            UnitSiteProgressRecord.InspectionTrade.CERAMIC_FLOORS,
            UnitSiteProgressRecord.InspectionTrade.CERAMIC_WALLS,
        ],
        ProjectActivity.TradeCategory.PAINT: [
            UnitSiteProgressRecord.InspectionTrade.PAINT_SEALER,
            UnitSiteProgressRecord.InspectionTrade.PAINT_PUTTY_1,
            UnitSiteProgressRecord.InspectionTrade.PAINT_PUTTY_2,
            UnitSiteProgressRecord.InspectionTrade.PAINT_PRIMER,
            UnitSiteProgressRecord.InspectionTrade.PAINT_FINAL,
        ],
        ProjectActivity.TradeCategory.CARPENTRY_ALUMINUM: [
            UnitSiteProgressRecord.InspectionTrade.CARPENTRY_FRAMES,
            UnitSiteProgressRecord.InspectionTrade.CARPENTRY_DOORS,
            UnitSiteProgressRecord.InspectionTrade.ALUMINUM_WINDOWS,
        ],
        ProjectActivity.TradeCategory.ROOF: [
            UnitSiteProgressRecord.InspectionTrade.ROOF_WATERPROOF_FLOOD_TEST,
            UnitSiteProgressRecord.InspectionTrade.ROOF_TILES_SCREED,
        ],
        ProjectActivity.TradeCategory.BASEMENT: [
            UnitSiteProgressRecord.InspectionTrade.BASEMENT_EPOXY_FIRE,
        ],
    }

    # الأوزان الافتراضية للبنود داخل المجموعة لحساب المتوسط الموزون
    STAGE_WEIGHTS: Dict[str, Decimal] = {
        UnitSiteProgressRecord.InspectionTrade.MASONRY_QADD: Decimal('5.00'),
        UnitSiteProgressRecord.InspectionTrade.MASONRY_FULL: Decimal('10.00'),
        UnitSiteProgressRecord.InspectionTrade.ELEC_PIPES: Decimal('4.00'),
        UnitSiteProgressRecord.InspectionTrade.ELEC_BOXES: Decimal('3.00'),
        UnitSiteProgressRecord.InspectionTrade.ELEC_WIRING: Decimal('4.00'),
        UnitSiteProgressRecord.InspectionTrade.ELEC_FITTING: Decimal('4.00'),
        UnitSiteProgressRecord.InspectionTrade.PLASTER_SPATTER: Decimal('3.00'),
        UnitSiteProgressRecord.InspectionTrade.PLASTER_STRINGS: Decimal('4.00'),
        UnitSiteProgressRecord.InspectionTrade.PLASTER_FILLING: Decimal('7.00'),
        UnitSiteProgressRecord.InspectionTrade.PLASTER_EDGES: Decimal('3.00'),
        UnitSiteProgressRecord.InspectionTrade.PLASTER_FINISH: Decimal('3.00'),
        UnitSiteProgressRecord.InspectionTrade.PLUMB_WATERPROOF: Decimal('5.00'),
        UnitSiteProgressRecord.InspectionTrade.PLUMB_FEEDING: Decimal('4.00'),
        UnitSiteProgressRecord.InspectionTrade.PLUMB_DRAINAGE: Decimal('4.00'),
        UnitSiteProgressRecord.InspectionTrade.PLUMB_TUB_FIX: Decimal('2.00'),
        UnitSiteProgressRecord.InspectionTrade.PLUMB_FITTING: Decimal('3.00'),
        UnitSiteProgressRecord.InspectionTrade.CERAMIC_FLOORS: Decimal('10.00'),
        UnitSiteProgressRecord.InspectionTrade.CERAMIC_WALLS: Decimal('5.00'),
        UnitSiteProgressRecord.InspectionTrade.PAINT_SEALER: Decimal('2.00'),
        UnitSiteProgressRecord.InspectionTrade.PAINT_PUTTY_1: Decimal('2.00'),
        UnitSiteProgressRecord.InspectionTrade.PAINT_PUTTY_2: Decimal('2.00'),
        UnitSiteProgressRecord.InspectionTrade.PAINT_PRIMER: Decimal('2.00'),
        UnitSiteProgressRecord.InspectionTrade.PAINT_FINAL: Decimal('2.00'),
        UnitSiteProgressRecord.InspectionTrade.CARPENTRY_FRAMES: Decimal('2.00'),
        UnitSiteProgressRecord.InspectionTrade.CARPENTRY_DOORS: Decimal('3.00'),
        UnitSiteProgressRecord.InspectionTrade.ALUMINUM_WINDOWS: Decimal('2.00'),
        UnitSiteProgressRecord.InspectionTrade.ROOF_WATERPROOF_FLOOD_TEST: Decimal('5.00'),
        UnitSiteProgressRecord.InspectionTrade.ROOF_TILES_SCREED: Decimal('5.00'),
        UnitSiteProgressRecord.InspectionTrade.BASEMENT_EPOXY_FIRE: Decimal('5.00'),
    }

    @classmethod
    def calculate_site_progress_for_activity(cls, activity: ProjectActivity) -> Decimal:
        """
        احتساب نسبة الإنجاز الفعلي لحزمة WBS من واقع سجلات الفحص الميداني:
        يرجع نسبة مئوية Decimal بين 0.00 و 100.00.
        """
        # إذا كان نشاطاً عاماً لا يرتبط بالتنفيذ الميداني أو غير مفعل للمزامنة، نُبقي نسبته المسجلة
        if activity.activity_type == ProjectActivity.ActivityType.GENERAL and not activity.auto_sync_progress:
            return activity.progress_percentage

        target_units = activity.project.units.filter(is_active=True)
        if activity.block_id:
            target_units = target_units.filter(block_id=activity.block_id)

        if not target_units.exists():
            return Decimal('0.00')

        # 1. نمط إجمالي تشطيبات الشقق
        if activity.activity_type == ProjectActivity.ActivityType.ALL_UNIT_FINISHES:
            avg_pct = target_units.aggregate(avg=Avg('progress_percentage'))['avg'] or Decimal('0.00')
            return Decimal(str(avg_pct)).quantize(Decimal('0.01'))

        # 2. نمط بند معماري تفصيلي محدد
        if activity.activity_type == ProjectActivity.ActivityType.SPECIFIC_TRADE:
            target_trade = activity.trade_stage
            if not target_trade:
                return activity.progress_percentage

            target_unit_ids = set(target_units.values_list('id', flat=True))
            if not target_unit_ids:
                return Decimal('0.00')

            all_records = UnitSiteProgressRecord.objects.filter(
                unit_id__in=target_unit_ids,
                trade_stage=target_trade,
            )
            rec_map = {r.unit_id: r for r in all_records}

            total_eff = Decimal('0.00')
            scope_count = 0

            for u_id in target_unit_ids:
                rec = rec_map.get(u_id)
                if rec and not rec.is_applicable:
                    # استبعاد موثق للبند لهذه الوحدة (Documented exclusion)
                    continue

                scope_count += 1
                if rec and rec.is_applicable:
                    eff_pct = Decimal(str(rec.completion_percentage))
                    if rec.status == UnitSiteProgressRecord.StageStatus.PENDING_INSPECTION:
                        eff_pct = min(eff_pct, Decimal('80.00'))
                    elif rec.status in [UnitSiteProgressRecord.StageStatus.REJECTED_DEFECT, UnitSiteProgressRecord.StageStatus.NOT_STARTED]:
                        eff_pct = Decimal('0.00')
                    elif rec.status == UnitSiteProgressRecord.StageStatus.IN_PROGRESS:
                        eff_pct = min(eff_pct, Decimal('90.00'))
                    total_eff += eff_pct
                else:
                    # وحدة مستهدفة لم تُهيأ لها سجلات تنفيذ بعد (Uninitialized): تحتسب بنسبة 0% ضمن المقام
                    pass

            if scope_count > 0:
                calc_val = (total_eff / Decimal(scope_count)).quantize(Decimal('0.01'))
                return max(Decimal('0.00'), min(Decimal('100.00'), calc_val))
            return Decimal('0.00')

        # 3. نمط مجموعة أعمال معمارية متخصصة
        if activity.activity_type == ProjectActivity.ActivityType.TRADE_CATEGORY:
            target_cat = activity.trade_category
            stages = cls.TRADE_CATEGORY_MAP.get(target_cat, [])
            if not stages:
                return activity.progress_percentage

            target_unit_ids = set(target_units.values_list('id', flat=True))
            if not target_unit_ids:
                return Decimal('0.00')

            all_records = list(UnitSiteProgressRecord.objects.filter(
                unit_id__in=target_unit_ids,
                trade_stage__in=stages,
            ))
            rec_map = {(r.unit_id, r.trade_stage): r for r in all_records}

            weighted_sum = Decimal('0.00')
            total_weight = Decimal('0.00')

            for u_id in target_unit_ids:
                for stage in stages:
                    rec = rec_map.get((u_id, stage))
                    if rec and not rec.is_applicable:
                        # استبعاد موثق للبند من هذه الوحدة
                        continue

                    w = cls.STAGE_WEIGHTS.get(stage, Decimal('1.00'))
                    total_weight += w

                    if rec and rec.is_applicable:
                        eff_pct = Decimal(str(rec.completion_percentage))
                        if rec.status == UnitSiteProgressRecord.StageStatus.PENDING_INSPECTION:
                            eff_pct = min(eff_pct, Decimal('80.00'))
                        elif rec.status in [UnitSiteProgressRecord.StageStatus.REJECTED_DEFECT, UnitSiteProgressRecord.StageStatus.NOT_STARTED]:
                            eff_pct = Decimal('0.00')
                        elif rec.status == UnitSiteProgressRecord.StageStatus.IN_PROGRESS:
                            eff_pct = min(eff_pct, Decimal('90.00'))
                        weighted_sum += (eff_pct * w)
                    else:
                        # بند لوحدة مستهدفة غير مهيأ بعد: يحتسب بنسبة 0% مع حفظ الوزن في المقام
                        pass

            if total_weight > Decimal('0.00'):
                calc_val = (weighted_sum / total_weight).quantize(Decimal('0.01'))
                return max(Decimal('0.00'), min(Decimal('100.00'), calc_val))
            return Decimal('0.00')

        return activity.progress_percentage

    @classmethod
    @transaction.atomic
    def sync_unit_progress_to_wbs(cls, project: RealEstateProject) -> int:
        """
        مزامنة كافة أنشطة WBS المربوطة بتنفيذ الوحدات في المشروع:
        يرجع عدد الأنشطة التي تمت مزامنتها.
        """
        # نركز على الأنشطة الورقية (Leaf activities) التي تحتوي على إعداد مزامنة
        leaf_activities = [
            act for act in project.wbs_activities.all()
            if act.is_leaf and (act.auto_sync_progress or act.activity_type != ProjectActivity.ActivityType.GENERAL)
        ]

        synced_count = 0
        for act in leaf_activities:
            new_pct = cls.calculate_site_progress_for_activity(act)
            if new_pct != act.progress_percentage:
                act.progress_percentage = new_pct
                act.save(update_fields=['progress_percentage'])
                synced_count += 1

        return synced_count


class WbsTreeGovernanceService:
    """
    خدمة حوكمة شجرة مقايسة المشروع الهرمية WBS:
    - فحص ومطابقة الأوزان النسبية للأنشطة الرئيسية والفرعية ومنع تجاوز الـ 100%.
    - تصعيد نسب الإنجاز التراكمية تصاعدياً من الأوراق للجذور للمشروع.
    - إعادة الموازنة النسبية لأوزان الأنشطة الفرعية.
    - بناء بيانات العرض الهرمي للواجهات والتقارير.
    """

    @classmethod
    def validate_tree_weights(cls, project: RealEstateProject) -> Dict[str, Any]:
        """
        تدقيق أوزان أنشطة WBS للمشروع:
        - التحقق من أن مجموع أوزان الأنشطة الجذرية (Root) <= 100.0000%.
        - التحقق من أن مجموع أوزان الأنشطة التابعة لكل نشاط أب لا تتجاوز وزن النشاط الأب.
        """
        errors: List[str] = []
        warnings: List[str] = []

        root_activities = list(project.wbs_activities.filter(parent_activity__isnull=True))
        total_root_weight = sum((r.weight_percentage for r in root_activities), Decimal('0.0000'))

        if total_root_weight > Decimal('100.0000'):
            errors.append(
                _("إجمالي أوزان الأنشطة الجذرية (%(total)s%%) يتجاوز سقف المشروع المحدد بـ 100.0000%%.") % {
                    'total': total_root_weight
                }
            )
        elif total_root_weight < Decimal('100.0000') and root_activities:
            warnings.append(
                _("إجمالي أوزان الأنشطة الجذرية (%(total)s%%) أقل من 100.0000%% (متبقي %(rem)s%%).") % {
                    'total': total_root_weight,
                    'rem': Decimal('100.0000') - total_root_weight
                }
            )

        # التحقق من أوزان الأبناء لكل نشاط رئيسي
        all_activities = list(project.wbs_activities.prefetch_related('sub_activities').all())
        for act in all_activities:
            children = list(act.sub_activities.all())
            if children:
                child_weight_sum = sum((c.weight_percentage for c in children), Decimal('0.0000'))
                if child_weight_sum > act.weight_percentage:
                    errors.append(
                        _("مجموع أوزان الأنشطة الفرعية للنشاط %(code)s (%(child_sum)s%%) يتجاوز وزن النشاط الرئيسي (%(parent_weight)s%%).") % {
                            'code': act.code,
                            'child_sum': child_weight_sum,
                            'parent_weight': act.weight_percentage
                        }
                    )
                elif child_weight_sum < act.weight_percentage:
                    warnings.append(
                        _("مجموع أوزان الأنشطة الفرعية للنشاط %(code)s (%(child_sum)s%%) أقل من وزن النشاط الرئيسي (%(parent_weight)s%%).") % {
                            'code': act.code,
                            'child_sum': child_weight_sum,
                            'parent_weight': act.weight_percentage
                        }
                    )

        return {
            'is_valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'total_root_weight': total_root_weight,
            'root_count': len(root_activities),
            'total_activities_count': len(all_activities),
        }

    @classmethod
    @transaction.atomic
    def recalculate_tree_rollup(cls, project: RealEstateProject) -> Decimal:
        """
        إعادة احتساب وتصعيد نسبة إنجاز شجرة WBS بالكامل bottom-up:
        1. مزامنة أنشطة التشطيبات المربوطة بسجلات الموقع عبر UnitToWbsBridgeService.
        2. تصعيد النسب من الأنشطة الورقية إلى الأنشطة الأب ثم الجذور.
        3. احتساب النسبة الإجمالية للمشروع وتحديث construction_progress_percentage.
        """
        # 1. مزامنة الأنشطة الورقية مع الموقع
        UnitToWbsBridgeService.sync_unit_progress_to_wbs(project)

        # 2. تصعيد هرمي تكراري
        def rollup_activity(act: ProjectActivity) -> Decimal:
            children = list(act.sub_activities.all())
            if not children:
                return act.progress_percentage

            child_weights = sum((c.weight_percentage for c in children), Decimal('0.0000'))
            if child_weights > Decimal('0.0000'):
                child_sum = sum(
                    (rollup_activity(c) * (c.weight_percentage / Decimal('100.0000')) for c in children),
                    Decimal('0.0000')
                )
                act_pct = (child_sum / (child_weights / Decimal('100.0000'))).quantize(Decimal('0.01'))
            else:
                child_sum = sum((rollup_activity(c) for c in children), Decimal('0.00'))
                act_pct = (child_sum / Decimal(len(children))).quantize(Decimal('0.01'))

            act_pct = max(Decimal('0.00'), min(Decimal('100.00'), act_pct))
            if act.progress_percentage != act_pct:
                act.progress_percentage = act_pct
                act.save(update_fields=['progress_percentage'])
            return act_pct

        root_activities = list(project.wbs_activities.filter(parent_activity__isnull=True))
        if not root_activities:
            # إذا لم توجد أنشطة WBS، نعتمد على متوسط وحدات المشروع
            avg_units = project.units.filter(is_active=True).aggregate(avg=Avg('progress_percentage'))['avg'] or Decimal('0.00')
            final_progress = Decimal(str(avg_units)).quantize(Decimal('0.01'))
        else:
            total_root_weight = sum((r.weight_percentage for r in root_activities), Decimal('0.0000'))
            weighted_root_sum = Decimal('0.0000')
            for root in root_activities:
                root_pct = rollup_activity(root)
                weighted_root_sum += (root_pct * (root.weight_percentage / Decimal('100.0000')))

            if total_root_weight > Decimal('0.0000'):
                final_progress = (weighted_root_sum / (total_root_weight / Decimal('100.0000'))).quantize(Decimal('0.01'))
            else:
                avg_roots = sum((r.progress_percentage for r in root_activities), Decimal('0.00')) / Decimal(len(root_activities))
                final_progress = avg_roots.quantize(Decimal('0.01'))

        final_progress = max(Decimal('0.00'), min(Decimal('100.00'), final_progress))
        project.construction_progress_percentage = final_progress
        project.save(update_fields=['construction_progress_percentage', 'updated_at'])

        # 3. تقييم محطات الإنجاز التلقائي وتفعيل تنبيهات تحصيل الأقساط للمحطات المنجزة 100%
        try:
            from real_estate.services.milestone_service import MilestoneCollectionBridgeService
            MilestoneCollectionBridgeService.evaluate_project_milestones_and_trigger(project)
        except Exception as e:
            logger.warning("Failed evaluating project milestones for project %s: %s", project.id, e)

        return final_progress

    @classmethod
    @transaction.atomic
    def rebalance_child_weights_proportionally(cls, parent_activity: ProjectActivity) -> None:
        """
        إعادة موازنة أوزان الأنشطة الفرعية بحيث يتساوى مجموعها تماماً مع وزن النشاط الأب.
        """
        children = list(parent_activity.sub_activities.all())
        if not children:
            return

        current_sum = sum((c.weight_percentage for c in children), Decimal('0.0000'))
        if current_sum <= Decimal('0.0000'):
            # توزيع متساوٍ
            equal_weight = (parent_activity.weight_percentage / Decimal(len(children))).quantize(Decimal('0.0001'))
            for c in children:
                c.weight_percentage = equal_weight
                c.save(update_fields=['weight_percentage'])
            return

        # توزيع نسبي
        factor = parent_activity.weight_percentage / current_sum
        running_sum = Decimal('0.0000')
        for i, c in enumerate(children):
            if i == len(children) - 1:
                # النشاط الأخير يأخذ الفارق لتجنب أخطاء التقريب
                new_w = parent_activity.weight_percentage - running_sum
            else:
                new_w = (c.weight_percentage * factor).quantize(Decimal('0.0001'))
                running_sum += new_w
            c.weight_percentage = new_w
            c.save(update_fields=['weight_percentage'])

    @classmethod
    def build_wbs_tree_hierarchy(cls, project: RealEstateProject) -> List[Dict[str, Any]]:
        """
        بناء هيكل شجرة WBS بشكل متداخل لعرضه في الواجهات والتقارير:
        يرجع قائمة بالعقد الجذرية وكل عقدة تحتوي على قائمة children الخاصة بها.
        """
        activities = list(project.wbs_activities.select_related('block', 'master_boq_item').order_by('code', 'id'))
        activity_map: Dict[int, Dict[str, Any]] = {}
        from real_estate.services.evm_service import EarnedValueManagementService

        for act in activities:
            evm_info = EarnedValueManagementService.calculate_activity_evm(act)
            activity_map[act.id] = {
                'id': act.id,
                'code': act.code,
                'name': act.name,
                'level': act.get_level(),
                'weight_percentage': act.weight_percentage,
                'progress_percentage': act.progress_percentage,
                'is_milestone': act.is_milestone,
                'is_baseline_locked': act.is_baseline_locked,
                'baseline_start_date': act.baseline_start_date,
                'baseline_end_date': act.baseline_end_date,
                'actual_start_date': act.actual_start_date,
                'actual_end_date': act.actual_end_date,
                'activity_type': act.activity_type,
                'activity_type_display': act.get_activity_type_display(),
                'trade_category': act.trade_category,
                'trade_category_display': act.get_trade_category_display() if act.trade_category else '',
                'trade_stage': act.trade_stage,
                'auto_sync_progress': act.auto_sync_progress,
                'budget_cost': act.budget_cost,
                'actual_cost': act.actual_cost,
                'block_name': act.block.name if act.block else '',
                'master_boq_code': act.master_boq_item.item_code if act.master_boq_item else '',
                'is_leaf': act.is_leaf,
                'evm': evm_info,
                'children': [],
            }

        tree: List[Dict[str, Any]] = []
        for act in activities:
            node = activity_map[act.id]
            if act.parent_activity_id and act.parent_activity_id in activity_map:
                activity_map[act.parent_activity_id]['children'].append(node)
            else:
                tree.append(node)

        return tree
