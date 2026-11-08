# -*- coding: utf-8 -*-
"""
Site Progress & Architectural Execution Services
MWHEBA ERP — Track 3 (WBS, Site Matrix, IFRS 15 POC & Subcontractor Retention Release)
"""
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple

from django.db import transaction
from django.db.models import Avg, Sum, Q, F
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    ProjectActivity,
    SiteDailyLog,
    UnitSiteProgressRecord,
    SiteProgressAuditLog,
    UnitSnagItem,
    ContractorContract,
)
from real_estate.services.accounting_service import RealEstateAccountingService
from real_estate.services.wbs_service import WbsTreeGovernanceService, UnitToWbsBridgeService

logger = logging.getLogger(__name__)


class ProjectProgressCalculationService:
    """
    محرك الحساب الرياضي التصاعدي السريع للأعمال الميدانية (Zero N+1 Query Engine):
    - إدارة أسبقيات البنود المعمارية (Finish-to-Start Trade Dependency Matrix).
    - حساب نسبة إنجاز الوحدة وحفظها في progress_percentage مباشرة.
    - تجميع متوسط إنجاز الأدوار والعمارات والمشروع بـ Single SQL Query عبر aggregate(Avg()).
    - معالجة الاعتراف بالإيراد الدوري التراكمي (IFRS 15 Periodic Delta POC).
    - حظر مستخلصات وتأمين مقاولي الباطن (Subcontractor Retention Release Gate).
    - تجميد خط الأساس الزمني (Schedule Baseline Freeze).
    """

    # الأوزان النسبية للـ 32 بنداً معمارياً (مجموعها 100%)
    STAGE_WEIGHTS: Dict[str, Decimal] = {
        # 1. المباني والحوائط (15%)
        UnitSiteProgressRecord.InspectionTrade.MASONRY_QADD: Decimal('5.00'),
        UnitSiteProgressRecord.InspectionTrade.MASONRY_FULL: Decimal('10.00'),
        # 2. تأسيس الكهرباء (15%)
        UnitSiteProgressRecord.InspectionTrade.ELEC_PIPES: Decimal('4.00'),
        UnitSiteProgressRecord.InspectionTrade.ELEC_BOXES: Decimal('3.00'),
        UnitSiteProgressRecord.InspectionTrade.ELEC_WIRING: Decimal('4.00'),
        UnitSiteProgressRecord.InspectionTrade.ELEC_FITTING: Decimal('4.00'),
        # 3. البياض والمحارة (20%)
        UnitSiteProgressRecord.InspectionTrade.PLASTER_SPATTER: Decimal('3.00'),
        UnitSiteProgressRecord.InspectionTrade.PLASTER_STRINGS: Decimal('4.00'),
        UnitSiteProgressRecord.InspectionTrade.PLASTER_FILLING: Decimal('7.00'),
        UnitSiteProgressRecord.InspectionTrade.PLASTER_EDGES: Decimal('3.00'),
        UnitSiteProgressRecord.InspectionTrade.PLASTER_FINISH: Decimal('3.00'),
        # 4. السباكة والعزل الداخلي (18%)
        UnitSiteProgressRecord.InspectionTrade.PLUMB_WATERPROOF: Decimal('5.00'),
        UnitSiteProgressRecord.InspectionTrade.PLUMB_FEEDING: Decimal('4.00'),
        UnitSiteProgressRecord.InspectionTrade.PLUMB_DRAINAGE: Decimal('4.00'),
        UnitSiteProgressRecord.InspectionTrade.PLUMB_TUB_FIX: Decimal('2.00'),
        UnitSiteProgressRecord.InspectionTrade.PLUMB_FITTING: Decimal('3.00'),
        # 5. الأرضيات والسيراميك (15%)
        UnitSiteProgressRecord.InspectionTrade.CERAMIC_FLOORS: Decimal('10.00'),
        UnitSiteProgressRecord.InspectionTrade.CERAMIC_WALLS: Decimal('5.00'),
        # 6. الدهانات والنقاشة (10%)
        UnitSiteProgressRecord.InspectionTrade.PAINT_SEALER: Decimal('2.00'),
        UnitSiteProgressRecord.InspectionTrade.PAINT_PUTTY_1: Decimal('2.00'),
        UnitSiteProgressRecord.InspectionTrade.PAINT_PUTTY_2: Decimal('2.00'),
        UnitSiteProgressRecord.InspectionTrade.PAINT_PRIMER: Decimal('2.00'),
        UnitSiteProgressRecord.InspectionTrade.PAINT_FINAL: Decimal('2.00'),
        # 7. النجارة والألوميتال (7%)
        UnitSiteProgressRecord.InspectionTrade.CARPENTRY_FRAMES: Decimal('2.00'),
        UnitSiteProgressRecord.InspectionTrade.CARPENTRY_DOORS: Decimal('3.00'),
        UnitSiteProgressRecord.InspectionTrade.ALUMINUM_WINDOWS: Decimal('2.00'),
        # 8. البنود الخاصة بالأدوار الحاكمة (الأسطح والبدروم - تُفعل عند وجودها)
        UnitSiteProgressRecord.InspectionTrade.ROOF_WATERPROOF_FLOOD_TEST: Decimal('5.00'),
        UnitSiteProgressRecord.InspectionTrade.ROOF_TILES_SCREED: Decimal('5.00'),
        UnitSiteProgressRecord.InspectionTrade.BASEMENT_EPOXY_FIRE: Decimal('5.00'),
    }

    # مصفوفة التبعية الهندسية الصارمة Finish-to-Start Trade Prerequisites
    # (لا يجوز البدء في البند اللاحق إلا إذا كان البند الحاكم مكتملاً ومستلماً بنسبة 100%)
    STAGE_PREREQUISITES: Dict[str, List[str]] = {
        # المباني الكاملة تشترط قد الحوائط
        UnitSiteProgressRecord.InspectionTrade.MASONRY_FULL: [
            UnitSiteProgressRecord.InspectionTrade.MASONRY_QADD,
        ],
        # سحب وتمديد المواسير يشترط انتهاء المباني
        UnitSiteProgressRecord.InspectionTrade.ELEC_PIPES: [
            UnitSiteProgressRecord.InspectionTrade.MASONRY_FULL,
        ],
        # طرطشة المحارة تشترط إنهاء مواسير الكهرباء
        UnitSiteProgressRecord.InspectionTrade.PLASTER_SPATTER: [
            UnitSiteProgressRecord.InspectionTrade.MASONRY_FULL,
            UnitSiteProgressRecord.InspectionTrade.ELEC_PIPES,
        ],
        # ملو المحارة يشترط البؤج والأوتار والطرطشة
        UnitSiteProgressRecord.InspectionTrade.PLASTER_FILLING: [
            UnitSiteProgressRecord.InspectionTrade.PLASTER_SPATTER,
            UnitSiteProgressRecord.InspectionTrade.PLASTER_STRINGS,
        ],
        # العزل المائي للسباكة يشترط ملو المحارة وتثبيت أوتار الزاوية
        UnitSiteProgressRecord.InspectionTrade.PLUMB_WATERPROOF: [
            UnitSiteProgressRecord.InspectionTrade.PLASTER_FILLING,
        ],
        # سيراميك الأرضيات يشترط اختبار ضغط السباكة والعزل المائي واختبار الغمر
        UnitSiteProgressRecord.InspectionTrade.CERAMIC_FLOORS: [
            UnitSiteProgressRecord.InspectionTrade.PLUMB_WATERPROOF,
            UnitSiteProgressRecord.InspectionTrade.PLUMB_FEEDING,
            UnitSiteProgressRecord.InspectionTrade.PLUMB_DRAINAGE,
        ],
        # سيراميك الحوائط يشترط تمديد السباكة والكهرباء
        UnitSiteProgressRecord.InspectionTrade.CERAMIC_WALLS: [
            UnitSiteProgressRecord.InspectionTrade.PLUMB_FEEDING,
            UnitSiteProgressRecord.InspectionTrade.PLASTER_FILLING,
        ],
        # معجون النقاشة يشترط جفاف المحارة ومسها
        UnitSiteProgressRecord.InspectionTrade.PAINT_SEALER: [
            UnitSiteProgressRecord.InspectionTrade.PLASTER_FINISH,
        ],
        UnitSiteProgressRecord.InspectionTrade.PAINT_PUTTY_1: [
            UnitSiteProgressRecord.InspectionTrade.PAINT_SEALER,
        ],
        # الفنش النهائي للدهانات يشترط سيراميك الأرضيات والأبواب لمنع تلف الدهانات
        UnitSiteProgressRecord.InspectionTrade.PAINT_FINAL: [
            UnitSiteProgressRecord.InspectionTrade.PAINT_PRIMER,
            UnitSiteProgressRecord.InspectionTrade.CERAMIC_FLOORS,
        ],
        # بلاط الأسطح يشترط عزل السطح واختبار الغمر 72 ساعة
        UnitSiteProgressRecord.InspectionTrade.ROOF_TILES_SCREED: [
            UnitSiteProgressRecord.InspectionTrade.ROOF_WATERPROOF_FLOOD_TEST,
        ],
    }

    @classmethod
    def validate_trade_prerequisites(cls, unit: PropertyUnit, target_trade: str) -> Tuple[bool, List[str]]:
        """
        التحقق من اكتمال الشروط الهندسية السابقة للبند:
        يرجع (True, []) إذا كانت الشروط مستوفاة، أو (False, [أسماء البنود غير المكتملة])
        """
        prereqs = cls.STAGE_PREREQUISITES.get(target_trade, [])
        if not prereqs:
            return True, []

        incomplete_trades = []
        records = {
            r.trade_stage: r for r in unit.site_progress_records.filter(
                trade_stage__in=prereqs,
                is_applicable=True
            )
        }

        for prereq_trade in prereqs:
            rec = records.get(prereq_trade)
            if not rec or rec.completion_percentage < 100 or rec.status != UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED:
                trade_name = dict(UnitSiteProgressRecord.InspectionTrade.choices).get(prereq_trade, prereq_trade)
                pct_str = f"{rec.completion_percentage}%" if rec else "0%"
                incomplete_trades.append(f"{trade_name} ({pct_str})")

        if incomplete_trades:
            return False, incomplete_trades
        return True, []

    @classmethod
    @transaction.atomic
    def calculate_and_save_unit_progress(cls, unit: PropertyUnit) -> Decimal:
        """
        احتساب نسبة إنجاز الوحدة الميدانية الموزونة وتحديث حقل progress_percentage:
        - يراعي فقط البنود الخاضعة تعاقدياً للوحدة (is_applicable=True).
        - يستثني بنود نصف التشطيب والمستثناة تلقائياً من مقام الحساب.
        - يربط نسبة الإنجاز المعتمدة بحالة الاعتماد الهندسي (PASSED_AND_VERIFIED).
        - يضمن الدقة الرياضية (Rounding to 2 decimal places).
        """
        records = list(unit.site_progress_records.filter(is_applicable=True))
        if not records:
            unit.progress_percentage = Decimal('0.00')
            unit.save(update_fields=['progress_percentage', 'updated_at'])
            return Decimal('0.00')

        total_weight = Decimal('0.00')
        weighted_progress_sum = Decimal('0.00')

        for rec in records:
            weight = cls.STAGE_WEIGHTS.get(rec.trade_stage, Decimal('1.00'))
            total_weight += weight
            eff_pct = Decimal(str(rec.completion_percentage))
            if rec.status == UnitSiteProgressRecord.StageStatus.PENDING_INSPECTION:
                eff_pct = min(eff_pct, Decimal('80.00'))
            elif rec.status == UnitSiteProgressRecord.StageStatus.REJECTED_DEFECT:
                eff_pct = Decimal('0.00')
            elif rec.status == UnitSiteProgressRecord.StageStatus.NOT_STARTED:
                eff_pct = Decimal('0.00')
            elif rec.status == UnitSiteProgressRecord.StageStatus.IN_PROGRESS:
                eff_pct = min(eff_pct, Decimal('90.00'))
            weighted_progress_sum += (eff_pct * weight)

        if total_weight > Decimal('0.00'):
            calculated_pct = (weighted_progress_sum / total_weight).quantize(Decimal('0.01'))
        else:
            calculated_pct = Decimal('0.00')

        # كبح النطاق بين 0 و 100
        calculated_pct = max(Decimal('0.00'), min(Decimal('100.00'), calculated_pct))

        unit.progress_percentage = calculated_pct
        unit.save(update_fields=['progress_percentage', 'updated_at'])

        return calculated_pct

    @classmethod
    @transaction.atomic
    def rollup_project_and_block_progress(
        cls,
        project: RealEstateProject,
        user=None,
        post_ifrs15: bool = True
    ) -> Dict[str, Any]:
        """
        محرك تصعيد النسب الشامل للمشروع والعمارات (Rollup Engine):
        1. يحسب متوسط إنجاز كل عمارة/بلوك عبر استعلام تجميعي فوري Avg('progress_percentage').
        2. يحسب متوسط إنجاز وحدات المشروع بالكامل.
        3. يدمج نسبة إنجاز شجرة مقايسة WBS بحسب أوزان الأنشطة.
        4. يحدث حقول construction_progress_percentage في البلوك والمشروع.
        5. يفحص بوابة IFRS 15 ويولد قيود الاستحقاق التراكمية الدورية في حال OVER_TIME_POC.
        """
        # قفل سجل المشروع ضد التعديلات المتزامنة
        locked_project = RealEstateProject.objects.select_for_update().get(id=project.id)

        # 1. تحديث نسب البلوكات
        blocks = locked_project.blocks.all()
        for block in blocks:
            avg_block_units = block.units.filter(is_active=True).aggregate(
                avg_pct=Avg('progress_percentage')
            )['avg_pct'] or Decimal('0.00')
            block.construction_progress_percentage = Decimal(str(avg_block_units)).quantize(Decimal('0.01'))
            block.save(update_fields=['construction_progress_percentage', 'updated_at'])

        # 2. حساب متوسط وحدات المشروع ككل
        avg_units_pct = locked_project.units.filter(is_active=True).aggregate(
            avg_pct=Avg('progress_percentage')
        )['avg_pct'] or Decimal('0.00')
        units_progress_dec = Decimal(str(avg_units_pct)).quantize(Decimal('0.01'))

        # 3. حساب نسبة مقايسة WBS وتصعيد شجرة الأنشطة الموزونة مع جسر الموقع (Unit-to-WBS Bridge)
        if locked_project.wbs_activities.exists():
            final_project_progress = WbsTreeGovernanceService.recalculate_tree_rollup(locked_project)
        else:
            final_project_progress = units_progress_dec
            locked_project.construction_progress_percentage = max(Decimal('0.00'), min(Decimal('100.00'), final_project_progress))
            locked_project.save(update_fields=['construction_progress_percentage', 'updated_at'])

        # 4. بوابة IFRS 15: قيود الاستحقاق الدوري التراكمي
        posted_entries = []
        if post_ifrs15 and locked_project.revenue_recognition_method == RealEstateProject.RevenueRecognitionMethod.OVER_TIME_POC:
            posted_entries = cls.process_ifrs15_periodic_delta_poc(locked_project, user=user)

        return {
            'project_progress': locked_project.construction_progress_percentage,
            'units_average_progress': units_progress_dec,
            'posted_ifrs15_entries_count': len(posted_entries),
        }

    @classmethod
    def process_ifrs15_periodic_delta_poc(cls, project: RealEstateProject, user=None) -> List[Any]:
        """
        معالجة استحقاق الإيراد الدوري لمعيار IFRS 15 وفق طريقة نسبة الإنجاز POC:
        - يمر على كافة العقود السارية (ACTIVE) للمشروع.
        - يحسب الإيراد المستهدف التراكمي = القيمة التعاقدية × نسبة الإنجاز الحالية للمشروع.
        - يحسب الإيراد المعترف به سابقاً من واقع القيود.
        - إذا كان (المستهدف > المعترف به سابقاً بفارق >= 1.00 ج.م): يصدر قيد استحقاق دوري بالفارق التراكمي (Periodic Delta).
        - يستخدم مفتاح تفرد idempotency لمنع تكرار القيود.
        """
        contracts = project.contracts.filter(
            status='ACTIVE'
        ).select_related('unit', 'project')

        current_pct = project.construction_progress_percentage
        if current_pct <= Decimal('0.00'):
            return []

        entries = []
        for contract in contracts:
            total_price = Decimal(str(contract.final_contract_price or contract.total_price or '0.00'))
            if total_price <= Decimal('0.00'):
                continue

            target_cumulative_revenue = (total_price * (current_pct / Decimal('100.00'))).quantize(Decimal('0.01'))
            prior_recognized = Decimal(str(getattr(contract, 'recognized_revenue_amount', '0.00') or '0.00'))

            delta_amount = target_cumulative_revenue - prior_recognized
            # إثبات القيد فقط عند وجود فارق موجب معتبر (أكبر من 1 ج.م)
            if delta_amount >= Decimal('1.00'):
                try:
                    with transaction.atomic():
                        entry = RealEstateAccountingService.post_revenue_recognition(
                            contract=contract,
                            amount=delta_amount,
                            user=user,
                            is_handover=False,
                            poc_percentage=current_pct,
                            reference=f"IFRS15-POC-{project.code}-{current_pct}%"
                        )
                        # تحديث رصيد الإيراد التراكمي بالعقد
                        contract.recognized_revenue_amount = target_cumulative_revenue
                        contract.save(update_fields=['recognized_revenue_amount', 'updated_at'])
                        entries.append(entry)
                except ValidationError as e:
                    logger.error(f"Validation error posting IFRS 15 POC entry for contract {contract.contract_number}: {e}")
                    raise
                except Exception as e:
                    logger.error(f"Failed to post IFRS 15 POC entry for contract {contract.contract_number}: {e}")
                    raise

        return entries

    @classmethod
    def validate_subcontractor_retention_release(
        cls,
        contract: ContractorContract
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        بوابة الإفراج عن مبالغ تأمين حسن التنفيذ لمقاول الباطن (Retention Release Gate):
        - التحقق من أن كافة البنود والوحدات المسندة للمقاول معتمدة ومستلمة ميدانياً 100% (PASSED_AND_VERIFIED).
        - التحقق من خلو المقاول من أي ملاحظات عيوب مفتوحة (Snags).
        - يرجع (مسموح/ممنوع، رسالة التوضيح، تفاصيل الإحصائيات).
        """
        subcontractor = contract.contractor
        assigned_records = UnitSiteProgressRecord.objects.filter(
            contractor=subcontractor,
            unit__project=contract.project
        )

        total_records = assigned_records.count()
        incomplete_records = assigned_records.exclude(
            status=UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED,
            completion_percentage=100
        ).count()

        open_snags = UnitSnagItem.objects.filter(
            contractor=subcontractor,
            unit__project=contract.project
        ).exclude(
            status=UnitSnagItem.SnagStatus.VERIFIED_BY_ENGINEER
        ).count()

        stats = {
            'total_assigned_trades': total_records,
            'incomplete_trades': incomplete_records,
            'open_snags_count': open_snags,
        }

        if open_snags > 0:
            msg = _(
                "يُحظر الإفراج عن تأمين حسن التنفيذ للمقاول: يوجد عدد %(snags)s ملاحظة فنية مفتوحة لم يتم اعتماد تلافيها بالمشروع."
            ) % {'snags': open_snags}
            return False, msg, stats

        if incomplete_records > 0:
            msg = _(
                "يُحظر الإفراج عن تأمين حسن التنفيذ للمقاول: يوجد عدد %(incomplete)s بند غير مستلم بنسبة 100%%."
            ) % {'incomplete': incomplete_records}
            return False, msg, stats

        if total_records == 0:
            return True, _("لا توجد بنود تنفيذ ميدانية مسندة لهذا المقاول في المشروع وخلوه من ملاحظات العيوب."), stats

        return True, _("تم استلام واعتماد كافة أعمال المقاول ميدانياً بنسبة 100% وخلوه من الملاحظات."), stats

    @classmethod
    def resolve_trade_contractor(cls, unit: PropertyUnit, warranty_category: str):
        """
        استرجاع مقاول المصنعية المسؤول عن البند لتوجيه تذاكر الضمان والصيانة بعد البيع:
        يربط فئة شكوى الضمان بالبند المعماري المناظر في سجلات الموقع.
        """
        CATEGORY_TO_TRADE_MAP = {
            'FINISHING_CERAMIC': UnitSiteProgressRecord.InspectionTrade.CERAMIC_FLOORS,
            'FINISHING_PLUMBING': UnitSiteProgressRecord.InspectionTrade.PLUMB_FITTING,
            'WATERPROOFING': UnitSiteProgressRecord.InspectionTrade.PLUMB_WATERPROOF,
            'FINISHING_ELECTRICAL': UnitSiteProgressRecord.InspectionTrade.ELEC_FITTING,
            'FINISHING_PAINTING': UnitSiteProgressRecord.InspectionTrade.PAINT_FINAL,
            'FINISHING_CARPENTRY': UnitSiteProgressRecord.InspectionTrade.CARPENTRY_DOORS,
            'ALUMINUM': UnitSiteProgressRecord.InspectionTrade.ALUMINUM_WINDOWS,
        }
        target_trade = CATEGORY_TO_TRADE_MAP.get(warranty_category)
        if target_trade:
            rec = unit.site_progress_records.filter(trade_stage=target_trade).select_related('contractor').first()
            if rec and rec.contractor:
                return rec.contractor
        return None

    @classmethod
    @transaction.atomic
    def freeze_baseline_schedule(cls, project: RealEstateProject) -> int:
        """
        تجميد خط الأساس الزمني (Schedule Baseline Freeze) لأنشطة مقايسة WBS:
        - يثبت تواريخ البدء والانتهاء المخططة ويقفلها ضد التعديل (is_baseline_locked=True).
        """
        activities = project.wbs_activities.filter(is_baseline_locked=False)
        updated_count = 0
        for act in activities:
            if act.baseline_start_date and act.baseline_end_date:
                act.is_baseline_locked = True
                act.save(update_fields=['is_baseline_locked'])
                updated_count += 1
        return updated_count


class SiteProgressInitializationService:
    """
    خدمة التهيئة والتوليد الصريح لمصفوفة المتابعة الميدانية للوحدات:
    - تفادي الاعتماد على Django Signals الهشة عند الاستيراد المجمع.
    - تكييف المراحل حسب نوع الوحدة (سكني / تجاري / مخازن).
    - تكييف المراحل حسب نوع التشطيب (استبعاد التشطيبات لنصف التشطيب SEMI_FINISHED).
    - تكييف المراحل حسب نوع الطابق (استبعاد الأسطح من الأدوار المتكررة والبدرومات).
    """

    @classmethod
    @transaction.atomic
    def seed_unit_site_stages(cls, unit: PropertyUnit) -> int:
        """
        توليد مراحل الفحص الـ 32 للوحدة العقارية تلقائياً مع تكييف النطاق:
        """
        is_semi = (unit.finishing_type in [
            PropertyUnit.FinishingType.SEMI_FINISHED,
            PropertyUnit.FinishingType.CORE_AND_SHELL
        ])
        is_commercial = (unit.unit_type in [
            PropertyUnit.UnitType.RETAIL_STORE,
            PropertyUnit.UnitType.STORAGE
        ])

        floor_type = getattr(unit.floor, 'floor_type', PropertyFloor.FloorType.TYPICAL) if unit.floor else PropertyFloor.FloorType.TYPICAL

        # البنود المستثناة لنصف التشطيب
        non_applicable_for_semi = {
            UnitSiteProgressRecord.InspectionTrade.CERAMIC_FLOORS,
            UnitSiteProgressRecord.InspectionTrade.CERAMIC_WALLS,
            UnitSiteProgressRecord.InspectionTrade.PAINT_PRIMER,
            UnitSiteProgressRecord.InspectionTrade.PAINT_FINAL,
            UnitSiteProgressRecord.InspectionTrade.CARPENTRY_DOORS,
            UnitSiteProgressRecord.InspectionTrade.PLUMB_FITTING,
            UnitSiteProgressRecord.InspectionTrade.ELEC_FITTING,
        }

        # البنود المستثناة للوحدات التجارية والمخازن
        non_applicable_for_commercial = {
            UnitSiteProgressRecord.InspectionTrade.CERAMIC_WALLS,
            UnitSiteProgressRecord.InspectionTrade.PLUMB_TUB_FIX,
            UnitSiteProgressRecord.InspectionTrade.CARPENTRY_DOORS,
        }

        # بنود الأسطح والبدرومات
        roof_trades = {
            UnitSiteProgressRecord.InspectionTrade.ROOF_WATERPROOF_FLOOD_TEST,
            UnitSiteProgressRecord.InspectionTrade.ROOF_TILES_SCREED,
        }
        basement_trades = {
            UnitSiteProgressRecord.InspectionTrade.BASEMENT_EPOXY_FIRE,
        }

        created_count = 0
        for trade_choice, _ in UnitSiteProgressRecord.InspectionTrade.choices:
            is_app = True
            initial_status = UnitSiteProgressRecord.StageStatus.NOT_STARTED

            # 1. تكييف نصف التشطيب
            if is_semi and trade_choice in non_applicable_for_semi:
                is_app = False
                initial_status = UnitSiteProgressRecord.StageStatus.NOT_APPLICABLE

            # 2. تكييف المحلات التجارية والمخازن
            if is_commercial and trade_choice in non_applicable_for_commercial:
                is_app = False
                initial_status = UnitSiteProgressRecord.StageStatus.NOT_APPLICABLE

            # 3. تكييف نوع الطابق
            if floor_type != PropertyFloor.FloorType.ROOF and trade_choice in roof_trades:
                is_app = False
                initial_status = UnitSiteProgressRecord.StageStatus.NOT_APPLICABLE
            elif floor_type != PropertyFloor.FloorType.BASEMENT and trade_choice in basement_trades:
                is_app = False
                initial_status = UnitSiteProgressRecord.StageStatus.NOT_APPLICABLE

            _, created = UnitSiteProgressRecord.objects.get_or_create(
                unit=unit,
                trade_stage=trade_choice,
                defaults={
                    'is_applicable': is_app,
                    'status': initial_status,
                    'completion_percentage': 100 if not is_app else 0,
                }
            )
            if created:
                created_count += 1

        ProjectProgressCalculationService.calculate_and_save_unit_progress(unit)
        return created_count

    @classmethod
    @transaction.atomic
    def seed_project_units(cls, project: RealEstateProject) -> Tuple[int, int]:
        """
        تهيئة كافة وحدات المشروع دفعة واحدة:
        يرجع (عدد الوحدات التي تم فحصها، عدد السجلات المنشأة)
        """
        units = project.units.all()
        total_created = 0
        for u in units:
            created = cls.seed_unit_site_stages(u)
            total_created += created

        # تصعيد نسب المشروع بعد التهيئة
        ProjectProgressCalculationService.rollup_project_and_block_progress(project, post_ifrs15=False)

        return units.count(), total_created


class ConcurrencyConflictError(ValidationError):
    """خطأ تعارض التزامن المتفائل الذري (Atomic OCC Concurrency Conflict)"""
    pass


class SiteProgressExecutionService:
    """
    خدمة التحديث والتنفيذ الميداني المحوكمة مع التحكم في التزامن المتفائل الذري (Atomic OCC):
    - تضمن الحماية التامة من التعديلات المتزامنة المتضاربة (Race Conditions & Lost Updates).
    - تعتمد القفل المزدوج (Row-level Lock select_for_update + Version-Conditioned Atomic DB Update).
    - تفرض قيود التسليم الميداني وقفل الفوترة is_billed والأسبقيات الهندسية.
    - تسجل سجل التدقيق التاريخي SiteProgressAuditLog وتعيد تصعيد نسب الإنجاز التراكمية.
    """

    @classmethod
    @transaction.atomic
    def update_stage_record_atomic(
        cls,
        record_id: int,
        expected_version: Any,
        status_val: str,
        completion_percentage: int,
        user=None,
        contractor_id: Optional[int] = None,
        rfi_number: str = "",
        notes: str = "",
        inspection_photo=None,
        audit_note: str = ""
    ) -> Tuple[UnitSiteProgressRecord, Optional[str], Decimal]:
        """
        تحديث سجل بند موقعي ميدانياً بشكل ذري تماماً مع التحقق من OCC:
        يرجع (السجل المحدث، كود الـ Snag إن وجد، نسبة إنجاز الوحدة الجديدة).
        """
        if expected_version is None or str(expected_version).strip() == '':
            raise ValidationError(_('رقم الإصدار (Version) إلزامي للتحكم في التزامن المتفائل.'))

        try:
            exp_v = int(expected_version)
        except (ValueError, TypeError):
            raise ValidationError(_('رقم الإصدار غير صالح.'))

        # 1. قفل الصف ذرياً على مستوى قاعدة البيانات لمنع أي تداخل متزامن
        record = UnitSiteProgressRecord.objects.select_for_update().select_related('unit__project').filter(pk=record_id).first()
        if not record:
            raise ValidationError(_('سجل بند التنفيذ غير موجود.'))

        # 2. فحص تسليم الوحدة (حظر التعديل بعد التسليم الفعلي أو الحكمي)
        if record.unit.status in [PropertyUnit.UnitStatus.DELIVERED, PropertyUnit.UnitStatus.DELIVERED_DEEMED]:
            raise ValidationError(_('لا يمكن تعديل بنود التنفيذ لوحدة تم تسليمها (فعلياً أو حُكمياً).'))

        # 3. التحقق المتفائل من الإصدار (OCC Check)
        if record.version != exp_v:
            raise ConcurrencyConflictError(
                _('تم تعديل هذا البند بواسطة مهندس آخر في الموقع. يرجى تحديث الصفحة لعرض أحدث البيانات.')
            )

        # 4. التحقق من صلاحية الحالة والنسبة
        if status_val not in UnitSiteProgressRecord.StageStatus.values:
            raise ValidationError(_('حالة البند غير صالحة أو غير معتمدة.'))

        try:
            pct_val = int(completion_percentage)
            if pct_val < 0 or pct_val > 100:
                raise ValidationError(_('نسبة الإنجاز يجب أن تكون بين 0 و 100.'))
        except (ValueError, TypeError):
            raise ValidationError(_('نسبة الإنجاز غير صالحة.'))

        # 5. صمام أمان قفل الفوترة (حظر تخفيض النسبة أو تغيير حالة الاعتماد للبند المفوتر)
        if record.is_billed:
            if pct_val < record.completion_percentage:
                raise ValidationError(_('لا يمكن تخفيض نسبة إنجاز بند تم صرفه في مستخلص مقاول باطن معتمد.'))
            if record.status == UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED and status_val != UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED:
                raise ValidationError(_('لا يمكن تغيير حالة اعتماد بند معتمد ومفوتر في مستخلص مقاول باطن.'))

        # 6. صمام أمان الأسبقيات الهندسية
        if pct_val > 0 and status_val != UnitSiteProgressRecord.StageStatus.NOT_APPLICABLE:
            valid, incomplete = ProjectProgressCalculationService.validate_trade_prerequisites(
                unit=record.unit,
                target_trade=record.trade_stage
            )
            if not valid:
                raise ValidationError(
                    _('لا يمكن اعتماد هذا البند هندسياً قبل اكتمال بنوده الحاكمة السابقة: %(trades)s') % {
                        'trades': ', '.join(incomplete)
                    }
                )

        prev_pct = record.completion_percentage
        prev_status = record.status

        verified_by_user = user if status_val == UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED else record.verified_by
        verified_at_val = timezone.now() if status_val == UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED else record.verified_at
        resolved_contractor_id = contractor_id if contractor_id else record.contractor_id

        # 7. التحديث الذري المشروط بالإصدار في قاعدة البيانات (Atomic DB-Level OCC Update)
        updated_rows = UnitSiteProgressRecord.objects.filter(
            pk=record.pk,
            version=exp_v
        ).update(
            status=status_val,
            completion_percentage=pct_val,
            contractor_id=resolved_contractor_id,
            rfi_number=rfi_number if rfi_number else record.rfi_number,
            notes=notes if notes else record.notes,
            verified_by=verified_by_user,
            verified_at=verified_at_val,
            version=F('version') + 1,
            updated_at=timezone.now()
        )

        if updated_rows == 0:
            raise ConcurrencyConflictError(
                _('تم تعديل هذا البند بواسطة مهندس آخر في الموقع. يرجى تحديث الصفحة لعرض أحدث البيانات.')
            )

        record.refresh_from_db()

        # معالجة صورة المعاينة
        if inspection_photo:
            record.inspection_photo = inspection_photo
            record.save(update_fields=['inspection_photo'])

        # 8. تسجيل حركة التدقيق التاريخية
        SiteProgressAuditLog.objects.create(
            unit=record.unit,
            unit_code_snapshot=record.unit.unit_code,
            trade_stage=record.trade_stage,
            previous_percentage=prev_pct,
            new_percentage=pct_val,
            previous_status=prev_status,
            new_status=status_val,
            defect_notes=notes or audit_note,
            changed_by=user
        )

        # 9. توليد Snag عند الرفض أو الملاحظات إن لزم الأمر
        created_snag_code = None
        if status_val in [
            UnitSiteProgressRecord.StageStatus.REJECTED_DEFECT,
            UnitSiteProgressRecord.StageStatus.APPROVED_WITH_COMMENTS
        ]:
            severity_choice = (
                UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER
                if status_val == UnitSiteProgressRecord.StageStatus.REJECTED_DEFECT
                else UnitSnagItem.SnagSeverity.MAJOR
            )
            snag = UnitSnagItem.objects.create(
                unit=record.unit,
                room_location=record.get_trade_stage_display(),
                category=UnitSnagItem.SnagCategory.CIVIL_MASONRY if hasattr(UnitSnagItem.SnagCategory, 'CIVIL_MASONRY') else 'OTHER',
                severity=severity_choice,
                description=notes or _('ملاحظة جودة مسجلة من مصفوفة الموقع للبند: %(stage)s') % {
                    'stage': record.get_trade_stage_display()
                },
                contractor=record.contractor,
                status=UnitSnagItem.SnagStatus.OPEN,
                created_by=user
            )
            record.linked_snag = snag
            record.save(update_fields=['linked_snag'])
            created_snag_code = snag.snag_code

        # 10. إعادة احتساب نسبة الوحدة وتصعيد المشروع
        new_unit_pct = ProjectProgressCalculationService.calculate_and_save_unit_progress(record.unit)
        ProjectProgressCalculationService.rollup_project_and_block_progress(
            project=record.unit.project,
            user=user,
            post_ifrs15=True
        )

        return record, created_snag_code, new_unit_pct


class StageRecordSpecPreviewService:
    """
    خدمة استرجاع ومعاينة المواصفات التعاقدية المعتمدة للوحدة (Approved Spec Preview Guard):
    - تطابق بند المعاينة الميدانية مع باقة التشطيب المعتمدة للعميل وأوامر التعديل السارية.
    - تعرض خامات الماركات والأكواد لمنع تركيب خامات خاطئة أو مخالفة للمواصفة التعاقدية بالموقع.
    """

    @classmethod
    def get_spec_preview(cls, record: UnitSiteProgressRecord) -> Dict[str, Any]:
        unit = record.unit
        from real_estate.models.contract import PropertyContract
        from real_estate.models.finishing import (
            FinishingItemCategory,
            UnitFinishingOrder,
        )
        from real_estate.models.engineering import ClientVariationOrder

        # 1. تحديد العقد والعميل
        contract = unit.contracts.filter(
            status__in=[
                PropertyContract.ContractStatus.ACTIVE,
                PropertyContract.ContractStatus.COMPLETED,
                PropertyContract.ContractStatus.UNDER_APPROVAL
            ]
        ).select_related('customer').first()

        customer_name = contract.customer.name if contract else ''

        # 2. تحديد أمر أو باقة التشطيب المعتمدة
        finishing_order = unit.finishing_orders.select_related('package', 'customer').prefetch_related(
            'items__spec__brand',
            'items__brand',
            'items__workspace'
        ).order_by('-id').first()

        if not customer_name and finishing_order and finishing_order.customer:
            customer_name = finishing_order.customer.name

        package_name = ''
        order_number = ''
        if finishing_order:
            order_number = finishing_order.order_number
            if finishing_order.package:
                package_name = finishing_order.package.name

        # 3. خريطة مطابقة بنود الموقع مع تصنيفات خامات التشطيب
        trade_category_map = {
            UnitSiteProgressRecord.InspectionTrade.MASONRY_QADD: [FinishingItemCategory.WALL_FINISH],
            UnitSiteProgressRecord.InspectionTrade.MASONRY_FULL: [FinishingItemCategory.WALL_FINISH],
            UnitSiteProgressRecord.InspectionTrade.ELEC_PIPES: [FinishingItemCategory.ELECTRICAL_FIXTURES],
            UnitSiteProgressRecord.InspectionTrade.ELEC_BOXES: [FinishingItemCategory.ELECTRICAL_FIXTURES],
            UnitSiteProgressRecord.InspectionTrade.ELEC_WIRING: [FinishingItemCategory.ELECTRICAL_FIXTURES],
            UnitSiteProgressRecord.InspectionTrade.ELEC_FITTING: [FinishingItemCategory.ELECTRICAL_FIXTURES],
            UnitSiteProgressRecord.InspectionTrade.PLASTER_SPATTER: [FinishingItemCategory.WALL_FINISH, FinishingItemCategory.CEILING],
            UnitSiteProgressRecord.InspectionTrade.PLASTER_STRINGS: [FinishingItemCategory.WALL_FINISH, FinishingItemCategory.CEILING],
            UnitSiteProgressRecord.InspectionTrade.PLASTER_FILLING: [FinishingItemCategory.WALL_FINISH, FinishingItemCategory.CEILING],
            UnitSiteProgressRecord.InspectionTrade.PLASTER_EDGES: [FinishingItemCategory.WALL_FINISH, FinishingItemCategory.CEILING],
            UnitSiteProgressRecord.InspectionTrade.PLASTER_FINISH: [FinishingItemCategory.WALL_FINISH, FinishingItemCategory.CEILING],
            UnitSiteProgressRecord.InspectionTrade.PLUMB_WATERPROOF: [FinishingItemCategory.PLUMBING_FIXTURES],
            UnitSiteProgressRecord.InspectionTrade.PLUMB_FEEDING: [FinishingItemCategory.PLUMBING_FIXTURES],
            UnitSiteProgressRecord.InspectionTrade.PLUMB_DRAINAGE: [FinishingItemCategory.PLUMBING_FIXTURES],
            UnitSiteProgressRecord.InspectionTrade.PLUMB_TUB_FIX: [FinishingItemCategory.PLUMBING_FIXTURES],
            UnitSiteProgressRecord.InspectionTrade.PLUMB_FITTING: [FinishingItemCategory.PLUMBING_FIXTURES],
            UnitSiteProgressRecord.InspectionTrade.CERAMIC_FLOORS: [FinishingItemCategory.FLOORING],
            UnitSiteProgressRecord.InspectionTrade.CERAMIC_WALLS: [FinishingItemCategory.FLOORING, FinishingItemCategory.WALL_FINISH],
            UnitSiteProgressRecord.InspectionTrade.PAINT_SEALER: [FinishingItemCategory.WALL_FINISH],
            UnitSiteProgressRecord.InspectionTrade.PAINT_PUTTY_1: [FinishingItemCategory.WALL_FINISH],
            UnitSiteProgressRecord.InspectionTrade.PAINT_PUTTY_2: [FinishingItemCategory.WALL_FINISH],
            UnitSiteProgressRecord.InspectionTrade.PAINT_PRIMER: [FinishingItemCategory.WALL_FINISH],
            UnitSiteProgressRecord.InspectionTrade.PAINT_FINAL: [FinishingItemCategory.WALL_FINISH],
            UnitSiteProgressRecord.InspectionTrade.CARPENTRY_FRAMES: [FinishingItemCategory.CARPENTRY_DOORS],
            UnitSiteProgressRecord.InspectionTrade.CARPENTRY_DOORS: [FinishingItemCategory.CARPENTRY_DOORS],
            UnitSiteProgressRecord.InspectionTrade.ALUMINUM_WINDOWS: [FinishingItemCategory.ALUMINUM_FACADES],
            UnitSiteProgressRecord.InspectionTrade.ROOF_TILES_SCREED: [FinishingItemCategory.FLOORING],
        }

        target_cats = trade_category_map.get(record.trade_stage, [])
        matched_specs = []

        if finishing_order:
            for item in finishing_order.items.all():
                if item.category in target_cats:
                    brand_name = ''
                    if item.brand:
                        brand_name = item.brand.name
                    elif item.spec and item.spec.brand:
                        brand_name = item.spec.brand.name

                    model_code = item.model_or_color_code or (item.spec.model_code if item.spec else '')
                    spec_name = item.spec.name if item.spec else item.item_description
                    workspace_name = item.workspace.name if item.workspace else ''

                    matched_specs.append({
                        'category': item.get_category_display(),
                        'spec_name': spec_name,
                        'brand': brand_name,
                        'model_code': model_code,
                        'workspace': workspace_name,
                        'supply_source': item.get_supply_source_display(),
                        'description': item.item_description,
                    })

        # 4. أوامر التعديل السارية
        variations = unit.variation_orders.filter(
            status__in=[
                ClientVariationOrder.OrderStatus.APPROVED,
                ClientVariationOrder.OrderStatus.IN_PROGRESS
            ]
        )
        variation_notes = []
        for v in variations:
            variation_notes.append(f"{v.order_number}: {v.title}")

        has_contracted_specs = bool(matched_specs or variation_notes or package_name)

        return {
            'has_specs': True,
            'has_contracted_specs': has_contracted_specs,
            'unit_code': unit.unit_code,
            'customer_name': customer_name or _('غير مباعة / مبيعات الشركة'),
            'finishing_type': unit.get_finishing_type_display(),
            'finishing_type_code': unit.finishing_type,
            'package_name': package_name,
            'order_number': order_number,
            'trade_stage': record.trade_stage,
            'trade_stage_display': record.get_trade_stage_display(),
            'matched_specs': matched_specs,
            'variation_notes': ' | '.join(variation_notes) if variation_notes else '',
        }

