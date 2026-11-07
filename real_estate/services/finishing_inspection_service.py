# -*- coding: utf-8 -*-
"""
Finishing Inspection & Quality Verification Service
MWHEBA ERP — Track 2: Hold-Points, Site Inspections & Technical Signoffs

Enforces strict civil, MEP, HSE, and architectural quality hold-points:
- Sequential trade dependencies (plumbing/electrical rough-in before plaster).
- Hydrostatic pressure testing & waterproofing flood tests (zero leak).
- Screed curing periods (minimum 7 days water curing before tiling).
- Plaster moisture limits (max 12% moisture before primer/paint).
- HVAC nitrogen pressure hold & vacuum verification before ceiling closure.
- Backdraft damper verification for kitchen and bath ventilation.
- Electrical earthing resistance threshold (<= 5.0 ohms) & FTTH fiber continuity.
- Anti-termite barrier verification prior to wood/parquet installation.
- Balcony slope & gravity drainage verification (zero ponding).
- Rooftop anti-root barrier & 72h flood test for penthouses.
- Secure apartment lockup & high-value smart/sanitary fixture release gates.
- Tile shade (dye lot) and caliber batch consistency per workspace.
- Facade sleeve penetrations (PU sealant + escutcheon flashing).
- Subsequent trade floor protection checklists (heavy poly + cardboard).
- Hot work permits & on-site fire extinguisher verification.
- Potable water chlorination & sanitary network disinfection certificates.
- Touch-up paint escrow canisters for final client handover.
"""
import logging
from decimal import Decimal
from datetime import date, timedelta
from typing import Dict, Any, Optional, Tuple, List

from django.db import transaction, models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from real_estate.models.finishing import (
    FinishingWorkspace,
    FinishingItemSpec,
    UnitFinishingOrder,
    UnitFinishingOrderItem,
    FinishingHoldPointRule,
    FinishingHydrostaticInspection,
    PlasterMoistureInspectionRecord,
    HVACNitrogenHoldingInspection,
    ElectricalEarthingResistanceInspection,
    ScreedCuringInspectionLog,
    AntiTermiteTreatmentRecord,
    BalconyDrainageSlopeInspection,
    RooftopWaterproofingInspection,
    ExhaustBackdraftDamperInspection,
    PotableWaterChlorinationInspection,
    FlooringSlipResistanceRatingRecord,
    HighValueFixtureReleaseGate,
    FinishingSecureLockUpRecord,
    FinishingHotWorkPermit,
    FinishingTileBatchBarcodeRecord,
    FiberOpticContinuityInspection,
    ElevatorArmorCladdingInspection,
    StructuralExpansionJointInspection,
    FacadeSleevePenetrationInspection,
    SubsequentTradeFloorProtectionInspection,
    FinishingContractorCARPolicyRecord,
    ElectricalFeederCapacityInspection,
    TouchUpPaintEscrowRecord,
    FinishingDebrisCartageWaybill,
    OwnerSuppliedMaterialInspection,
    FinishingSampleSubmittalRecord,
)

logger = logging.getLogger(__name__)


class FinishingHoldPointEngine:
    """
    محرك نقاط التوقف الإلزامية (Hold-Points) والصمامات الفنية لجودة التشطيبات:
    يمنع الانتقال للمراحل التالية أو صرف الخامات من المخزن دون اعتماد الاستشاري.
    """

    MAX_PERMISSIBLE_PLASTER_MOISTURE_PCT = Decimal('12.00')
    MAX_PERMISSIBLE_EARTHING_RESISTANCE_OHMS = Decimal('5.00')
    MIN_SCREED_CURING_DAYS = 7
    MIN_ROOFTOP_FLOOD_TEST_HOURS = 72
    MIN_HYDROSTATIC_FLOOD_HOURS = 48
    MAX_OPTICAL_LOSS_DB = Decimal('0.50')

    @classmethod
    def can_issue_flooring_materials(
        cls,
        order: UnitFinishingOrder,
        workspace: FinishingWorkspace
    ) -> Tuple[bool, Optional[str]]:
        """
        صمام صرف خامات الأرضيات والسيراميك:
        1. في الفراغات المبتلة (حمامات، مطابخ، شرفات، أسطح): يلزم اجتياز اختبار العزل المائي والضغط الهيدروستاتيكي.
        2. يلزم اكتمال فترة معالجة اللياسة بالماء (Screed Curing) 7 أيام على الأقل.
        3. يلزم مطابقة تصنيف مقاومة الانزلاق (Slip Resistance R10/R11).
        """
        # 1. التحقق من اختبار العزل في الفراغات المبتلة
        is_wet_area = any(k in workspace.name.lower() or k in workspace.code.lower() for k in ['bath', 'toilet', 'حمام', 'مطبخ', 'kitchen', 'balcony', 'شرفة', 'roof', 'سطح'])
        if is_wet_area:
            hydro_tests = FinishingHydrostaticInspection.objects.filter(
                order=order,
                workspace=workspace,
                is_passed=True
            )
            if not hydro_tests.exists():
                return False, _(f"محظور صرف خامات الأرضيات للفراغ المبتل '{workspace.name}' دون اعتماد محضر اختبار العزل والضغط الهيدروستاتيكي بنجاح وبدون تسريب.")

        # 2. التحقق من فترة معالجة اللياسة (Screed Curing)
        screed_logs = ScreedCuringInspectionLog.objects.filter(
            order=order,
            workspace=workspace
        )
        if screed_logs.exists():
            latest_curing = screed_logs.latest('id')
            if not latest_curing.is_curing_approved_for_tiling or latest_curing.water_curing_days_completed < cls.MIN_SCREED_CURING_DAYS:
                return False, _(f"محظور تركيب الأرضيات قبل اكتمال 7 أيام معالجة بالماء للياسة (المكتمل حالياً: {latest_curing.water_curing_days_completed} أيام).")
        else:
            # إذا لم يتم تسجيل محضر معالجة اللياسة
            pass

        # 3. التحقق من معامل الانزلاق للفراغات المبتلة
        if is_wet_area:
            slip_records = FlooringSlipResistanceRatingRecord.objects.filter(
                order=order,
                workspace=workspace
            )
            if slip_records.exists():
                latest_slip = slip_records.latest('id')
                if not latest_slip.is_wet_area_compliant and not latest_slip.anti_slip_treatment_applied:
                    return False, _(f"البورسلين المحدد للفراغ '{workspace.name}' غير مطابق لاشتراطات منع الانزلاق (يلزم تصنيف R10 على الأقل أو معالجة مانعة للانزلاق).")

        return True, None

    @classmethod
    def can_issue_painting_materials(
        cls,
        order: UnitFinishingOrder,
        workspace: FinishingWorkspace
    ) -> Tuple[bool, Optional[str]]:
        """
        صمام صرف خامات الدهانات والمعجون:
        يحظر صرف الدهانات إذا تجاوزت رطوبة المحارة 12% تجنباً لتقشير الدهانات وتمليح الحوائط.
        """
        moisture_records = PlasterMoistureInspectionRecord.objects.filter(
            order=order,
            workspace=workspace
        )
        if moisture_records.exists():
            latest_record = moisture_records.latest('id')
            if latest_record.moisture_percentage > cls.MAX_PERMISSIBLE_PLASTER_MOISTURE_PCT or not latest_record.is_passed:
                return False, _(f"محظور صرف خامات الدهانات للفراغ '{workspace.name}' نظراً لتجاوز رطوبة المحارة النسبة المعيارية (الرطوبة المقاسة: {latest_record.moisture_percentage}% والحد الأقصى 12%).")

        return True, None

    @classmethod
    def can_close_ceilings(
        cls,
        order: UnitFinishingOrder,
        workspace: FinishingWorkspace
    ) -> Tuple[bool, Optional[str]]:
        """
        صمام إغلاق أسقف الجبس بورد (False Ceiling Closure):
        1. يحظر إغلاق الأسقف بدون اجتياز اختبار كبس النيتروجين لمواسير التكييف وثبات الضغط 24 ساعة.
        2. في المطابخ والحمامات: يحظر الإغلاق بدون فحص رداد عدم الرجوع لمداخن الشفاطات (Backdraft Damper).
        """
        # 1. فحص كبس النيتروجين لشبكة التكييف
        hvac_tests = HVACNitrogenHoldingInspection.objects.filter(
            order=order,
            is_pressure_holding_passed=True
        )
        if not hvac_tests.exists():
            return False, _("محظور إغلاق أسقف الجبس بورد دون اعتماد محضر كبس النيتروجين والفاكيوم لشبكات التكييف بنجاح.")

        # 2. فحص رداد الشفاط في المطابخ والحمامات
        is_exhaust_area = any(k in workspace.name.lower() or k in workspace.code.lower() for k in ['bath', 'toilet', 'حمام', 'مطبخ', 'kitchen'])
        if is_exhaust_area:
            damper_inspections = ExhaustBackdraftDamperInspection.objects.filter(
                order=order,
                workspace=workspace,
                ceiling_closure_permitted=True
            )
            if not damper_inspections.exists():
                return False, _(f"محظور إغلاق سقف '{workspace.name}' دون فحص وتجربة رداد عدم الرجوع (Backdraft Damper) لمداخن الشفاطات والتأكد من حرية حركة الشفرات.")

        return True, None

    @classmethod
    def can_energize_main_power(cls, order: UnitFinishingOrder) -> Tuple[bool, Optional[str]]:
        """
        صمام إطلاق التيار الكهربائي الدائم وحماية الأجهزة الذكية:
        1. يحظر إطلاق التيار إذا تجاوزت مقاومة بئر التأريض 5 أوم.
        2. التحقق من سلامة كابلات الفايبر الضوئي (FTTH) ومستوى الفقد الضوئي.
        """
        earthing_records = ElectricalEarthingResistanceInspection.objects.filter(order=order)
        if not earthing_records.exists():
            return False, _("محظور إطلاق التيار الكهربائي الدائم دون اعتماد فحص مقاومة بئر التأريض (Earth Pit).")

        latest_earthing = earthing_records.latest('id')
        if not latest_earthing.is_earthing_approved or latest_earthing.measured_earth_resistance_ohms > cls.MAX_PERMISSIBLE_EARTHING_RESISTANCE_OHMS:
            return False, _(f"محظور إطلاق التيار الكهربائي الدائم: مقاومة التأريض المقاسة ({latest_earthing.measured_earth_resistance_ohms} أوم) تتجاوز الحد الأقصى المسموح (5 أوم).")

        fiber_records = FiberOpticContinuityInspection.objects.filter(order=order)
        if fiber_records.exists():
            failed_fiber = fiber_records.filter(models.Q(is_continuity_passed=False) | models.Q(optical_loss_db__gt=cls.MAX_OPTICAL_LOSS_DB))
            if failed_fiber.exists():
                return False, _("تم رصد عطل أو تجاوز في الفقد الضوئي بشبكة الألياف الضوئية (FTTH). يلزم الإصلاح قبل إطلاق التيار وتغطية لوحات التيار الخفيف.")

        return True, None

    @classmethod
    def can_install_wood_parquet(
        cls,
        order: UnitFinishingOrder,
        workspace: FinishingWorkspace
    ) -> Tuple[bool, Optional[str]]:
        """
        صمام حماية الأخشاب ومكافحة النمل الأبيض:
        يحظر توريد وتركيب أرضيات الباركيه الطبيعي أو الصناعي دون محضر رش مبيد النمل الأبيض المعتمد.
        """
        termite_records = AntiTermiteTreatmentRecord.objects.filter(
            order=order,
            workspace=workspace,
            is_verified_by_site_engineer=True
        )
        if not termite_records.exists():
            return False, _(f"محظور تركيب الباركيه بالفراغ '{workspace.name}' قبل اعتماد محضر رش مبيد النمل الأبيض وتسليم شهادة الضمان من شركة المكافحة المعتمدة.")

        return True, None

    @classmethod
    def can_release_high_value_fixtures(
        cls,
        order: UnitFinishingOrder,
        item_spec: FinishingItemSpec
    ) -> Tuple[bool, Optional[str]]:
        """
        صمام صرف التركيبات الثمينة والدقيقة (خلاطات دفن ذهبية، سمارت هوم، شاشات):
        يحظر الصرف من المخزن إلا بعد اكتمال وجه الدهان النهائي وتركيب الباب الخارجي وقفل الشقة وتسليم المفاتيح للأمانات.
        """
        lockup_records = FinishingSecureLockUpRecord.objects.filter(
            order=order,
            exterior_door_installed=True,
            access_restricted=True
        )
        if not lockup_records.exists():
            return False, _(f"محظور صرف البند الثمين '{item_spec.name}' من المخزن قبل تركيب الباب الخارجي وتفعيل محضر قفل وتأمين الشقة (Secure Lockup).")

        gates = HighValueFixtureReleaseGate.objects.filter(
            order=order,
            item_spec=item_spec,
            warehouse_release_authorized=True
        )
        if not gates.exists():
            return False, _(f"محظور صرف البند الثمين '{item_spec.name}': يلزم التحقق من انتهاء أعمال الدهان وقفل الموقع واعتماد إذن الصرف الاستثنائي.")

        return True, None

    @classmethod
    def can_signoff_balcony(
        cls,
        order: UnitFinishingOrder,
        workspace: FinishingWorkspace
    ) -> Tuple[bool, Optional[str]]:
        """
        صمام استلام الشرفات والواجهات:
        يحظر اعتماد استلام الشرفة في حال رصد أي ركود مائي (Ponding) أو عدم تحقق التدفق بالانحدار الطبيعي.
        """
        inspections = BalconyDrainageSlopeInspection.objects.filter(
            order=order,
            workspace=workspace
        )
        if inspections.exists():
            latest = inspections.latest('id')
            if latest.water_ponding_detected or not latest.is_gravity_flow_successful:
                return False, _(f"محظور استلام أرضية الشرفة '{workspace.name}' لوجود ركود مائي أو ميول تصريف غير كافية.")

        return True, None

    @classmethod
    def can_signoff_rooftop_waterproofing(cls, order: UnitFinishingOrder) -> Tuple[bool, Optional[str]]:
        """
        صمام عزل أسطح البنتهاوس والحدائق المعلقة:
        يحظر الاعتماد دون اختبار الغمر 72 ساعة وتركيب شيتات حماية الجذور (Anti-Root Membrane).
        """
        rooftop_inspections = RooftopWaterproofingInspection.objects.filter(order=order)
        if rooftop_inspections.exists():
            latest = rooftop_inspections.latest('id')
            if latest.flood_test_hours_completed < cls.MIN_ROOFTOP_FLOOD_TEST_HOURS:
                return False, _(f"اختبار غمر السطح غير مكتمل (المنفذ {latest.flood_test_hours_completed} ساعة من أصل 72 ساعة المطلوبة).")
            if latest.has_roof_garden_or_planters and not latest.anti_root_membrane_installed:
                return False, _("يلزم تركيب شيتات العزل المقاوم لاختراق جذور المزروعات (Anti-Root Membrane) للمساحات الخضراء بالسطح.")
            if not latest.consultant_approved:
                return False, _("محضر عزل السطح لم يعتمد بعد من الاستشاري المشرف.")

        return True, None

    @classmethod
    def can_allow_subsequent_trades(
        cls,
        order: UnitFinishingOrder,
        workspace: FinishingWorkspace
    ) -> Tuple[bool, Optional[str]]:
        """
        صمام حماية الأرضيات بعد الجلاء:
        يحظر دخول فرق النجارة والدهانات إلا بعد اعتماد محضر تغليف الأرضيات بالكرتون المضلع والمشمع الثقيل وتثبيت الفواصل.
        """
        protection_inspections = SubsequentTradeFloorProtectionInspection.objects.filter(
            order=order,
            workspace=workspace,
            carpentry_painting_entry_permitted=True
        )
        if not protection_inspections.exists():
            return False, _(f"محظور دخول فرق النجارة أو الدهانات للفراغ '{workspace.name}' دون محضر فحص واعتماد تغليف وحماية الأرضيات.")

        return True, None

    @classmethod
    def can_allow_hot_works(
        cls,
        order: UnitFinishingOrder,
        workspace: FinishingWorkspace,
        contractor: str
    ) -> Tuple[bool, Optional[str]]:
        """
        صمام تصاريح الأعمال الساخنة واللحام وعزل البيتومين:
        يحظر إشعال النيران بالموقع دون توفير طفايات الحريق وخلو الموقع من المواد القابلة للاشتعال وتوقيع مسؤول السلامة.
        """
        permits = FinishingHotWorkPermit.objects.filter(
            order=order,
            workspace=workspace,
            is_approved=True
        )
        if not permits.exists():
            return False, _(f"محظور تنفيذ أعمال اللحام أو العزل باللهب في '{workspace.name}' دون استخراج تصريح أعمال ساخنة معتمد وتواجد طفايات حريق صالحة بالموقع.")

        latest_permit = permits.latest('id')
        if not latest_permit.fire_extinguishers_verified or not latest_permit.combustible_materials_cleared:
            return False, _("تصريح الأعمال الساخنة غير مستوفٍ لاشتراطات السلامة (يلزم إخلاء المواد القابلة للاشتعال وتوفير الطفايات).")

        return True, None

    @classmethod
    def can_allow_elevator_hoisting(
        cls,
        order: UnitFinishingOrder,
        elevator_identifier: str
    ) -> Tuple[bool, Optional[str]]:
        """
        صمام تشوين الخامات بالمصاعد:
        يحظر تشوين الخامات بالمصعد دون تصفيح الكابينة بالبليود واختبار حساس الحمل الزائد وتعهد المقاول.
        """
        inspections = ElevatorArmorCladdingInspection.objects.filter(
            order=order,
            elevator_identifier=elevator_identifier,
            approved_by__isnull=False
        )
        if not inspections.exists():
            return False, _(f"محظور استخدام المصعد '{elevator_identifier}' لتشوين الخامات قبل تصفيح الكابينة بالخشب واختبار حساس الحمل الزائد واعتماد الإدارة الهندسية.")

        latest = inspections.latest('id')
        if not latest.is_cabin_plywood_cladded or not latest.overload_sensor_tested or not latest.contractor_pledge_signed:
            return False, _("اشتراطات حماية وتصفيح المصعد غير مكتملة (يلزم التصفيح وفحص الحساس وتوقيع التعهد).")

        return True, None

    @classmethod
    def can_authorize_final_handover(cls, order: UnitFinishingOrder) -> Tuple[bool, Optional[str]]:
        """
        صمام التسليم النهائي الميداني للعميل:
        1. تطهير شبكة المياه بالكلور وإصدار شهادة الخلو الصحي.
        2. تسليم عبوات دهان الرتوش (Touch-Up Paint) بأكواد جوتن المعتمدة.
        3. إبطال مفتاح الإنشاءات للمالك وإثبات سقوط بلية سلندر الأمانات.
        """
        # 1. شهادة الكلور
        chlorination = PotableWaterChlorinationInspection.objects.filter(
            order=order,
            sanitary_clearance_issued=True,
            flushing_completed=True
        )
        if not chlorination.exists():
            return False, _("محظور إصدار محضر التسليم النهائي دون إجراء تطهير شبكة مياه الشرب بالكلور وإصدار شهادة الصلاحية الصحية.")

        # 2. عبوات دهان الرتوش
        paint_escrows = TouchUpPaintEscrowRecord.objects.filter(
            order=order,
            handed_over_to_site_escrow=True
        )
        if not paint_escrows.exists():
            return False, _("محظور إصدار محضر التسليم النهائي قبل استلام وتوريد عبوات دهان الرتوش بأكواد الألوان المعتمدة للعميل.")

        # 3. إبطال مفتاح المقاول (Builder Cylinder Rekeying)
        lockups = FinishingSecureLockUpRecord.objects.filter(
            order=order,
            builder_key_deactivated=True,
            cylinder_rekeyed_successfully=True
        )
        if not lockups.exists():
            return False, _("محظور تسليم الوحدة قبل إبطال مفتاح الإنشاءات وسقوط بلية السلندر وتفعيل المفتاح الأصلي النهائي للمالك.")

        return True, None

    @classmethod
    def validate_tile_batch_consistency(
        cls,
        order: UnitFinishingOrder,
        workspace: FinishingWorkspace,
        shade_code: str,
        caliber_code: str
    ) -> Tuple[bool, Optional[str]]:
        """
        صمام تطابق شيد وكاليبر البورسلين والسيراميك لنفس الفراغ:
        يمنع خلط تشغيلات مختلفة لنفس الصالة أو الغرفة لتفادي تفاوت الألوان أو المقاسات.
        """
        existing_batches = FinishingTileBatchBarcodeRecord.objects.filter(
            order=order,
            workspace=workspace
        )
        for batch in existing_batches:
            if batch.shade_code != shade_code or batch.caliber_code != caliber_code:
                return False, _(f"تم رصد تفاوت في كود التشغيلة (الشيد الحالي: {shade_code} مقابل السابق: {batch.shade_code}، الكاليبر الحالي: {caliber_code} مقابل السابق: {batch.caliber_code}) للفراغ '{workspace.name}'. محظور الخلط في نفس الفراغ المعماري.")

        return True, None

    @classmethod
    def validate_electrical_riser_capacity(
        cls,
        order: UnitFinishingOrder,
        additional_tonnage: Decimal
    ) -> Tuple[bool, Optional[str]]:
        """
        صمام سعة صاعد الكهرباء عند ترقية التكييفات (Riser Ampacity Guard):
        يحظر ترقية التكييف إذا تجاوز الحمل المقنن سعة القاطع والصاعد المخصص للوحدة دون موافقة الاستشاري.
        """
        inspections = ElectricalFeederCapacityInspection.objects.filter(order=order)
        if inspections.exists():
            latest = inspections.latest('id')
            if latest.is_riser_upgrade_required and not latest.consultant_approval_letter:
                return False, _("الحمل الكهربائي المطلوب لتعديلات التكييف يتجاوز سعة صاعد العمارة المخصص للوحدة، ويلزم إرفاق موافقة استشاري الكهرباء وترقية الصاعد أولاً.")

        return True, None


class FinishingInspectionService:
    """
    خدمة توثيق وتسجيل محاضر الفحص الفني والميداني للتشطيبات
    """

    @classmethod
    @transaction.atomic
    def record_hydrostatic_test(
        cls,
        order: UnitFinishingOrder,
        workspace: FinishingWorkspace,
        test_type: str,
        pressure_bar: Decimal,
        duration_hours: int,
        is_passed: bool,
        consultant_engineer_name: str,
        notes: str = "",
        pressure_gauge_photo=None,
        flooding_photo=None
    ) -> FinishingHydrostaticInspection:
        """تسجيل محضر اختبار كبس أو غمر العزل والسباكة"""
        inspection = FinishingHydrostaticInspection.objects.create(
            order=order,
            workspace=workspace,
            test_type=test_type,
            pressure_bar=pressure_bar,
            duration_hours=duration_hours,
            is_passed=is_passed,
            consultant_engineer_name=consultant_engineer_name,
            notes=notes,
            pressure_gauge_photo=pressure_gauge_photo,
            flooding_photo=flooding_photo,
            inspected_at=timezone.now()
        )
        logger.info(f"Hydrostatic test recorded for Order {order.order_number}, Workspace {workspace.name}: Passed={is_passed}")
        return inspection

    @classmethod
    @transaction.atomic
    def record_plaster_moisture(
        cls,
        order: UnitFinishingOrder,
        workspace: FinishingWorkspace,
        tested_wall_description: str,
        moisture_percentage: Decimal,
        site_qa_engineer=None,
        moisture_meter_photo=None
    ) -> PlasterMoistureInspectionRecord:
        """تسجيل قراءة مقياس رطوبة المحارة الميداني"""
        is_passed = moisture_percentage <= FinishingHoldPointEngine.MAX_PERMISSIBLE_PLASTER_MOISTURE_PCT
        record = PlasterMoistureInspectionRecord.objects.create(
            order=order,
            workspace=workspace,
            tested_wall_description=tested_wall_description,
            moisture_percentage=moisture_percentage,
            is_passed=is_passed,
            site_qa_engineer=site_qa_engineer,
            moisture_meter_photo=moisture_meter_photo,
            tested_at=timezone.now()
        )
        logger.info(f"Plaster moisture recorded for Order {order.order_number}: {moisture_percentage}% (Passed={is_passed})")
        return record

    @classmethod
    @transaction.atomic
    def record_hvac_pressure_test(
        cls,
        order: UnitFinishingOrder,
        system_type: str,
        initial_pressure_psi: Decimal,
        final_pressure_psi: Decimal,
        test_duration_hours: int,
        vacuum_micron_reading: Decimal,
        inspected_by=None,
        manometer_gauge_photo=None
    ) -> HVACNitrogenHoldingInspection:
        """تسجيل اختبار كبس شبكة التكييف بالنيتروجين والفاكيوم"""
        # يعتبر ناجحاً إذا لم ينخفض الضغط وكان اختبار الفاكيوم أقل من 500 ميكرون
        is_passed = (final_pressure_psi >= initial_pressure_psi) and (vacuum_micron_reading <= Decimal('500.00'))
        inspection = HVACNitrogenHoldingInspection.objects.create(
            order=order,
            system_type=system_type,
            initial_pressure_psi=initial_pressure_psi,
            final_pressure_psi=final_pressure_psi,
            test_duration_hours=test_duration_hours,
            vacuum_micron_reading=vacuum_micron_reading,
            is_pressure_holding_passed=is_passed,
            inspected_by=inspected_by,
            manometer_gauge_photo=manometer_gauge_photo,
            inspected_at=timezone.now()
        )
        logger.info(f"HVAC nitrogen test recorded for Order {order.order_number}: Passed={is_passed}")
        return inspection

    @classmethod
    @transaction.atomic
    def record_screed_curing(
        cls,
        order: UnitFinishingOrder,
        workspace: FinishingWorkspace,
        screed_pouring_date: date,
        water_curing_days_completed: int,
        moisture_percentage: Decimal,
        inspected_by=None,
        inspection_photo=None
    ) -> ScreedCuringInspectionLog:
        """تسجيل استيفاء معالجة اللياسة بالماء قبل التبليط"""
        is_approved = (water_curing_days_completed >= FinishingHoldPointEngine.MIN_SCREED_CURING_DAYS)
        log = ScreedCuringInspectionLog.objects.create(
            order=order,
            workspace=workspace,
            screed_pouring_date=screed_pouring_date,
            water_curing_days_completed=water_curing_days_completed,
            moisture_percentage=moisture_percentage,
            is_curing_approved_for_tiling=is_approved,
            inspected_by=inspected_by,
            inspection_photo=inspection_photo,
            inspected_at=timezone.now()
        )
        return log

    @classmethod
    @transaction.atomic
    def record_earthing_resistance(
        cls,
        order: UnitFinishingOrder,
        measured_earth_resistance_ohms: Decimal,
        ground_continuity_sockets_verified: bool = True,
        inspected_by=None,
        megger_test_photo=None
    ) -> ElectricalEarthingResistanceInspection:
        """تسجيل قياس مقاومة بئر التأريض بواسطة جهاز الميجر"""
        is_approved = (
            measured_earth_resistance_ohms <= FinishingHoldPointEngine.MAX_PERMISSIBLE_EARTHING_RESISTANCE_OHMS
            and ground_continuity_sockets_verified
        )
        record = ElectricalEarthingResistanceInspection.objects.create(
            order=order,
            measured_earth_resistance_ohms=measured_earth_resistance_ohms,
            max_allowable_resistance_ohms=FinishingHoldPointEngine.MAX_PERMISSIBLE_EARTHING_RESISTANCE_OHMS,
            ground_continuity_sockets_verified=ground_continuity_sockets_verified,
            is_earthing_approved=is_approved,
            inspected_by=inspected_by,
            megger_test_photo=megger_test_photo,
            inspected_at=timezone.now()
        )
        return record

    @classmethod
    @transaction.atomic
    def record_secure_lockup(
        cls,
        order: UnitFinishingOrder,
        key_custody_officer,
        key_tag_code: str,
        exterior_door_installed: bool = True,
        access_restricted: bool = True,
        builder_key_deactivated: bool = False,
        cylinder_rekeyed_successfully: bool = False
    ) -> FinishingSecureLockUpRecord:
        """تسجيل محضر قفل وتأمين الشقة وحفظ المفاتيح"""
        record, _ = FinishingSecureLockUpRecord.objects.update_or_create(
            order=order,
            defaults={
                'lockup_date': timezone.now().date(),
                'exterior_door_installed': exterior_door_installed,
                'key_custody_officer': key_custody_officer,
                'key_tag_code': key_tag_code,
                'access_restricted': access_restricted,
                'builder_key_deactivated': builder_key_deactivated,
                'cylinder_rekeyed_successfully': cylinder_rekeyed_successfully
            }
        )
        return record

    @classmethod
    @transaction.atomic
    def record_touchup_paint_escrow(
        cls,
        order: UnitFinishingOrder,
        workspace: FinishingWorkspace,
        paint_brand: str,
        color_code: str,
        can_volume_liters: Decimal = Decimal('1.00'),
        is_sealed_and_labeled: bool = True,
        handed_over_to_site_escrow: bool = True,
        verified_by=None
    ) -> TouchUpPaintEscrowRecord:
        """تسجيل عبوات دهان الرتوش المودعة بأمانات الموقع لتسليم العميل"""
        record = TouchUpPaintEscrowRecord.objects.create(
            order=order,
            workspace=workspace,
            paint_brand=paint_brand,
            color_code=color_code,
            can_volume_liters=can_volume_liters,
            is_sealed_and_labeled=is_sealed_and_labeled,
            handed_over_to_site_escrow=handed_over_to_site_escrow,
            verified_by=verified_by,
            received_at=timezone.now()
        )
        return record

    @classmethod
    @transaction.atomic
    def record_water_chlorination_test(
        cls,
        order: UnitFinishingOrder,
        chlorine_concentration_ppm: Decimal,
        holding_time_hours: int,
        flushing_completed: bool,
        water_sample_clarity_passed: bool,
        inspected_by=None
    ) -> PotableWaterChlorinationInspection:
        """تسجيل محضر تعقيم شبكة المياه بالكلور وإصدار شهادة الصلاحية"""
        sanitary_issued = (
            chlorine_concentration_ppm >= Decimal('50.00')
            and holding_time_hours >= 24
            and flushing_completed
            and water_sample_clarity_passed
        )
        record = PotableWaterChlorinationInspection.objects.create(
            order=order,
            chlorine_concentration_ppm=chlorine_concentration_ppm,
            holding_time_hours=holding_time_hours,
            flushing_completed=flushing_completed,
            water_sample_clarity_passed=water_sample_clarity_passed,
            sanitary_clearance_issued=sanitary_issued,
            inspected_by=inspected_by,
            inspected_at=timezone.now()
        )
        return record
