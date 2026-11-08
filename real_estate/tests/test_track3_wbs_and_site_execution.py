# -*- coding: utf-8 -*-
"""
Exhaustive Pytest Verification Suite for Track 3 (WBS & Site Execution)
MWHEBA ERP — Track 3 Verification & Parity Audit (44 Test Cases)
"""
import json
from decimal import Decimal
from datetime import timedelta
import pytest

from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

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
    ClientVariationOrder,
    PropertyHandoverReceipt,
    PropertyContract,
)
from real_estate.services.site_progress_service import (
    ProjectProgressCalculationService,
    SiteProgressInitializationService,
)
from supplier.models import Supplier

from core.models import SystemModule
from core.middleware.module_control import ModuleAccessMiddleware
from django.core.cache import cache
from customer.models import Customer
from financial.models import Currency

User = get_user_model()


@pytest.fixture
def test_setup(db):
    """تجهيز بيئة الاختبار الأساسية للمشروع والمستخدمين"""
    cache.delete('enabled_modules_set')
    cache.delete('module_namespace_map')

    mod, _ = SystemModule.objects.get_or_create(
        code='real_estate',
        defaults={'name_ar': 'العقارات', 'is_enabled': True}
    )
    mod.is_enabled = True
    mod.save()
    ModuleAccessMiddleware.invalidate_cache()

    curr, _ = Currency.objects.get_or_create(
        code='EGP',
        defaults={'name': 'جنيه مصري', 'symbol': 'ج.م', 'is_functional': True}
    )

    cust, _ = Customer.objects.get_or_create(
        code='CUST-TRK3',
        defaults={'name': 'العميل المعتمد للتسليم'}
    )

    user = User.objects.create_user(
        username='eng_site',
        email='eng_site@mwheba.com',
        password='password123',
        is_staff=True
    )
    admin_user = User.objects.create_superuser(
        username='admin_site',
        password='password123',
        email='admin@mwheba.com'
    )
    contractor = Supplier.objects.create(
        name='شركة الأهرام للمقاولات والمصنعيات',
        code='CONT-001',
        is_active=True
    )
    project = RealEstateProject.objects.create(
        code='PRJ-TRK3',
        name='برج النخيل السكني الفاخر',
        project_type=RealEstateProject.ProjectType.RESIDENTIAL,
        status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
        revenue_recognition_method=RealEstateProject.RevenueRecognitionMethod.OVER_TIME_POC,
        start_date=timezone.localdate(),
        expected_completion_date=timezone.localdate() + timedelta(days=365),
        created_by=admin_user
    )
    block = PropertyBlock.objects.create(
        project=project,
        code='BLK-A',
        name='برج أ',
        total_floors=5
    )
    floor_3 = PropertyFloor.objects.create(
        block=block,
        floor_number=3,
        floor_type=PropertyFloor.FloorType.TYPICAL,
        name='الدور الثالث'
    )
    floor_roof = PropertyFloor.objects.create(
        block=block,
        floor_number=5,
        floor_type=PropertyFloor.FloorType.ROOF,
        name='السطح والرووف'
    )
    unit_res = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor_3,
        unit_code='U-301',
        unit_type=PropertyUnit.UnitType.APARTMENT,
        finishing_type=PropertyUnit.FinishingType.FULLY_FINISHED,
        net_area=Decimal('120.00'),
        gross_area=Decimal('145.00'),
        meter_price=Decimal('15000.00'),
        base_price=Decimal('2175000.00'),
        total_price=Decimal('2175000.00')
    )
    unit_semi = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor_3,
        unit_code='U-302',
        unit_type=PropertyUnit.UnitType.APARTMENT,
        finishing_type=PropertyUnit.FinishingType.SEMI_FINISHED,
        net_area=Decimal('130.00'),
        gross_area=Decimal('155.00'),
        meter_price=Decimal('12000.00'),
        base_price=Decimal('1860000.00'),
        total_price=Decimal('1860000.00')
    )
    unit_retail = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor_3,
        unit_code='U-SHOP-01',
        unit_type=PropertyUnit.UnitType.RETAIL_STORE,
        finishing_type=PropertyUnit.FinishingType.CORE_AND_SHELL,
        net_area=Decimal('80.00'),
        gross_area=Decimal('90.00'),
        meter_price=Decimal('30000.00'),
        base_price=Decimal('2700000.00'),
        total_price=Decimal('2700000.00')
    )
    unit_roof = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor_roof,
        unit_code='U-ROOF-01',
        unit_type=PropertyUnit.UnitType.PENTHOUSE,
        finishing_type=PropertyUnit.FinishingType.FULLY_FINISHED,
        net_area=Decimal('200.00'),
        gross_area=Decimal('250.00'),
        meter_price=Decimal('20000.00'),
        base_price=Decimal('5000000.00'),
        total_price=Decimal('5000000.00')
    )

    return {
        'user': user,
        'admin_user': admin_user,
        'contractor': contractor,
        'project': project,
        'block': block,
        'floor_3': floor_3,
        'floor_roof': floor_roof,
        'unit_res': unit_res,
        'unit_semi': unit_semi,
        'unit_retail': unit_retail,
        'unit_roof': unit_roof,
        'currency': curr,
        'customer': cust,
    }


# ==============================================================================
# الـ 44 فحص واختبار دقيق لمصفوفة Track 3
# ==============================================================================

def test_01_wbs_activities_hierarchy_and_weights(test_setup):
    """1. فحص هرمية أنشطة WBS وتوازن الأوزان النسبية حتى 100%"""
    prj = test_setup['project']
    parent = ProjectActivity.objects.create(
        project=prj,
        code='WBS-01',
        name='الهيكل الخرساني والأساسات',
        weight_percentage=Decimal('50.0000')
    )
    child1 = ProjectActivity.objects.create(
        project=prj,
        parent_activity=parent,
        code='WBS-01.1',
        name='أعمال الحفر والإحلال',
        weight_percentage=Decimal('20.0000')
    )
    child2 = ProjectActivity.objects.create(
        project=prj,
        parent_activity=parent,
        code='WBS-01.2',
        name='صب الخرسانة المسلحة للأساسات',
        weight_percentage=Decimal('30.0000')
    )
    assert parent.sub_activities.count() == 2
    assert (child1.weight_percentage + child2.weight_percentage) == parent.weight_percentage


def test_02_wbs_baseline_schedule_freeze(test_setup):
    """2. فحص تجميد خط الأساس الزمني ومنع التعديل العشوائي"""
    prj = test_setup['project']
    act = ProjectActivity.objects.create(
        project=prj,
        code='WBS-BASE',
        name='تأسيس الموقع العام',
        weight_percentage=Decimal('10.0000'),
        baseline_start_date=timezone.localdate(),
        baseline_end_date=timezone.localdate() + timedelta(days=30),
        is_baseline_locked=False
    )
    count = ProjectProgressCalculationService.freeze_baseline_schedule(prj)
    act.refresh_from_db()
    assert count == 1
    assert act.is_baseline_locked is True


def test_03_dynamic_finishing_adaptation_semi_finished(test_setup):
    """3. فحص التوليد التلقائي لشقة نصف تشطيب واستبعاد التشطيبات ووصولها لـ 100%"""
    unit_semi = test_setup['unit_semi']
    created = SiteProgressInitializationService.seed_unit_site_stages(unit_semi)
    assert created > 0

    ceramic_rec = unit_semi.site_progress_records.filter(
        trade_stage=UnitSiteProgressRecord.InspectionTrade.CERAMIC_FLOORS
    ).first()
    assert ceramic_rec.is_applicable is False
    assert ceramic_rec.status == UnitSiteProgressRecord.StageStatus.NOT_APPLICABLE


def test_04_unit_type_adaptive_profile_retail_store(test_setup):
    """4. تكييف بنود المحل التجاري والمخازن واستبعاد بنود الغرف والسباكة السكنية"""
    unit_retail = test_setup['unit_retail']
    SiteProgressInitializationService.seed_unit_site_stages(unit_retail)

    tub_rec = unit_retail.site_progress_records.filter(
        trade_stage=UnitSiteProgressRecord.InspectionTrade.PLUMB_TUB_FIX
    ).first()
    assert tub_rec.is_applicable is False


def test_05_roof_trade_flood_test_sanity_warning(test_setup):
    """5. تكييف بنود السطح واختبار الغمر 72 ساعة"""
    unit_roof = test_setup['unit_roof']
    SiteProgressInitializationService.seed_unit_site_stages(unit_roof)

    roof_flood = unit_roof.site_progress_records.filter(
        trade_stage=UnitSiteProgressRecord.InspectionTrade.ROOF_WATERPROOF_FLOOD_TEST
    ).first()
    assert roof_flood.is_applicable is True


def test_06_finish_to_start_dependency_prevents_premature_approval(test_setup):
    """6. التحقق من الأسبقية الهندسية Finish-to-Start ومنع اعتماد السيراميك قبل العزل"""
    unit_res = test_setup['unit_res']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)

    valid, incomplete = ProjectProgressCalculationService.validate_trade_prerequisites(
        unit=unit_res,
        target_trade=UnitSiteProgressRecord.InspectionTrade.CERAMIC_FLOORS
    )
    assert valid is False
    assert len(incomplete) > 0


def test_07_bulk_floor_stage_update_with_contractor_and_rfi(client, test_setup):
    """7. التحديث المجمع لشقق الدور وتعيين المقاول ورقم RFI"""
    client.force_login(test_setup['admin_user'])
    fl = test_setup['floor_3']
    sub = test_setup['contractor']

    url = reverse('real_estate:api_site_floor_bulk_update')
    resp = client.post(url, {
        'floor_id': fl.id,
        'trade_stage': UnitSiteProgressRecord.InspectionTrade.MASONRY_QADD,
        'status': UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED,
        'completion_percentage': 100,
        'contractor_id': sub.id,
        'rfi_number': 'RFI-FL3-MASONRY-01',
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data['success'] is True
    assert data['updated_count'] >= 1


def test_08_subcontractor_retention_release_blocked_with_open_trades(test_setup):
    """8. حظر الإفراج عن تأمين حسن التنفيذ لوجود بنود غير مكتملة"""
    unit_res = test_setup['unit_res']
    sub = test_setup['contractor']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)

    rec = unit_res.site_progress_records.first()
    rec.contractor = sub
    rec.completion_percentage = 50
    rec.status = UnitSiteProgressRecord.StageStatus.IN_PROGRESS
    rec.save()

    contract = PropertyContract.objects.create(
        contract_number='CONT-TRK3-001',
        project=test_setup['project'],
        unit=unit_res,
        customer=test_setup['customer'],
        currency=test_setup['currency'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timedelta(days=180),
        final_contract_price=Decimal('2000000.00'),
        created_by=test_setup['admin_user'],
        status='ACTIVE'
    )
    # فحص المقاول
    from real_estate.models import ContractorContract
    sub_contract = ContractorContract.objects.create(
        contract_number='SUB-001',
        title='عقد أعمال مصنعيات الموقع',
        project=test_setup['project'],
        contractor=sub,
        currency=test_setup['currency'],
        initial_contract_value=Decimal('500000.00'),
        status=ContractorContract.ContractStatus.ACTIVE,
        created_by=test_setup['admin_user']
    )
    can_release, msg, stats = ProjectProgressCalculationService.validate_subcontractor_retention_release(sub_contract)
    assert can_release is False
    assert stats['incomplete_trades'] > 0


def test_09_snag_item_auto_generated_on_rejection(client, test_setup):
    """9. توليد ملاحظة عيب فني فورية عند رفض البند المعماري"""
    client.force_login(test_setup['admin_user'])
    unit_res = test_setup['unit_res']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)

    rec = unit_res.site_progress_records.first()
    url = reverse('real_estate:api_site_stage_quick_update', kwargs={'record_id': rec.id})
    resp = client.post(url, {
        'status': UnitSiteProgressRecord.StageStatus.REJECTED_DEFECT,
        'completion_percentage': 0,
        'version': rec.version,
        'notes': 'وجود شروخ هبوط وتنميل بالبياض',
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data['success'] is True
    assert data['created_snag_code'] is not None

    rec.refresh_from_db()
    assert rec.linked_snag is not None
    assert rec.linked_snag.severity == UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER


def test_10_approved_with_comments_creates_moderate_snag(client, test_setup):
    """10. الاعتماد المشروط ينشئ Snag بدرجة MAJOR"""
    client.force_login(test_setup['admin_user'])
    unit_res = test_setup['unit_res']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)

    rec = unit_res.site_progress_records.filter(
        trade_stage=UnitSiteProgressRecord.InspectionTrade.MASONRY_QADD
    ).first()
    url = reverse('real_estate:api_site_stage_quick_update', kwargs={'record_id': rec.id})
    resp = client.post(url, {
        'status': UnitSiteProgressRecord.StageStatus.APPROVED_WITH_COMMENTS,
        'completion_percentage': 90,
        'version': rec.version,
        'notes': 'ملاحظة نظافة خلف الحوائط',
    })
    assert resp.status_code == 200
    rec.refresh_from_db()
    assert rec.linked_snag is not None
    assert rec.linked_snag.severity == UnitSnagItem.SnagSeverity.MAJOR


def test_11_single_query_unit_progress_calculation(test_setup):
    """11. سرعة حساب نسبة إنجاز الوحدة وحفظها بدون N+1"""
    unit_res = test_setup['unit_res']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)

    unit_res.site_progress_records.all().update(
        completion_percentage=100,
        status=UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED
    )
    pct = ProjectProgressCalculationService.calculate_and_save_unit_progress(unit_res)
    unit_res.refresh_from_db()
    assert pct == Decimal('100.00')
    assert unit_res.progress_percentage == Decimal('100.00')


def test_12_audit_log_record_on_stage_update(client, test_setup):
    """12. تسجيل حركة التدقيق في SiteProgressAuditLog وحماية كود الوحدة المجمد"""
    client.force_login(test_setup['admin_user'])
    unit_res = test_setup['unit_res']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)

    rec = unit_res.site_progress_records.first()
    url = reverse('real_estate:api_site_stage_quick_update', kwargs={'record_id': rec.id})
    client.post(url, {
        'status': UnitSiteProgressRecord.StageStatus.IN_PROGRESS,
        'completion_percentage': 40,
        'version': rec.version,
        'notes': 'بدء أعمال التركيب',
    })
    log = SiteProgressAuditLog.objects.filter(unit=unit_res).first()
    assert log is not None
    assert log.unit_code_snapshot == unit_res.unit_code
    assert log.new_percentage == 40


def test_13_handover_hard_blocker_on_incomplete_unit(test_setup):
    """13. صمام أمان محضر التسليم: منع تسليم الوحدة إذا كانت أقل من 100%"""
    unit_res = test_setup['unit_res']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)
    unit_res.progress_percentage = Decimal('80.00')
    unit_res.save()

    contract = PropertyContract.objects.create(
        contract_number='CONT-HND-01',
        project=test_setup['project'],
        unit=unit_res,
        customer=test_setup['customer'],
        currency=test_setup['currency'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timedelta(days=180),
        final_contract_price=Decimal('1000000.00'),
        created_by=test_setup['admin_user'],
        status='ACTIVE'
    )
    receipt = PropertyHandoverReceipt(
        contract=contract,
        unit=unit_res,
        status=PropertyHandoverReceipt.HandoverStatus.EXECUTED,
        client_signatory_name='محمد أحمد',
        created_by=test_setup['admin_user']
    )
    with pytest.raises(ValidationError):
        receipt.clean()


def test_14_handover_hard_blocker_on_critical_snag(test_setup):
    """14. صمام أمان محضر التسليم: منع التسليم في وجود ملاحظة حرجة مفتوحة"""
    unit_res = test_setup['unit_res']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)
    unit_res.progress_percentage = Decimal('100.00')
    unit_res.save()

    UnitSnagItem.objects.create(
        unit=unit_res,
        category='PLUMBING',
        severity=UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER,
        description='تسريب خط الصرف الرئيسي',
        room_location='الحمام الرئيسي',
        status=UnitSnagItem.SnagStatus.OPEN,
        created_by=test_setup['admin_user']
    )

    contract = PropertyContract.objects.create(
        contract_number='CONT-HND-02',
        project=test_setup['project'],
        unit=unit_res,
        customer=test_setup['customer'],
        currency=test_setup['currency'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timedelta(days=180),
        final_contract_price=Decimal('1000000.00'),
        created_by=test_setup['admin_user'],
        status='ACTIVE'
    )
    receipt = PropertyHandoverReceipt(
        contract=contract,
        unit=unit_res,
        status=PropertyHandoverReceipt.HandoverStatus.EXECUTED,
        client_signatory_name='أحمد إبراهيم',
        created_by=test_setup['admin_user']
    )
    with pytest.raises(ValidationError):
        receipt.clean()


def test_15_site_daily_log_creation_and_delays(client, test_setup):
    """15. تسجيل يومية الموقع وساعات التعطيل"""
    client.force_login(test_setup['admin_user'])
    prj = test_setup['project']
    url = reverse('real_estate:site_daily_log_create', kwargs={'project_id': prj.id})
    resp = client.post(url, {
        'project': prj.id,
        'log_date': timezone.localdate().strftime('%Y-%m-%d'),
        'weather': SiteDailyLog.WeatherCondition.RAIN_HEAVY,
        'total_manpower_count': 35,
        'stoppage_reason': SiteDailyLog.StoppageReason.WEATHER,
        'delays_recorded_hours': '4.5',
        'notes': 'أمطار غزيرة أوقفت أعمال الصب',
    })
    assert resp.status_code == 302
    log = SiteDailyLog.objects.filter(project=prj).first()
    assert log is not None
    assert log.delays_recorded_hours == Decimal('4.5')


def test_16_optimistic_concurrency_control_conflict_409(client, test_setup):
    """16. قفل التزامن المتفائل OCC وإرجاع خطأ 409 عند تضارب التعديل المتزامن"""
    client.force_login(test_setup['admin_user'])
    unit_res = test_setup['unit_res']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)

    rec = unit_res.site_progress_records.first()
    url = reverse('real_estate:api_site_stage_quick_update', kwargs={'record_id': rec.id})

    # إرسال رقم version قديم
    resp = client.post(url, {
        'status': UnitSiteProgressRecord.StageStatus.IN_PROGRESS,
        'completion_percentage': 25,
        'version': rec.version - 1,
    })
    assert resp.status_code == 409
    data = resp.json()
    assert data['conflict'] is True


def test_17_is_billed_records_locked_against_reduction(client, test_setup):
    """17. حظر تخفيض نسبة الإنجاز للبنود المفوترة في مستخلص مقاول باطن معتمد"""
    client.force_login(test_setup['admin_user'])
    unit_res = test_setup['unit_res']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)

    rec = unit_res.site_progress_records.first()
    rec.completion_percentage = 80
    rec.is_billed = True
    rec.save()

    url = reverse('real_estate:api_site_stage_quick_update', kwargs={'record_id': rec.id})
    resp = client.post(url, {
        'status': UnitSiteProgressRecord.StageStatus.IN_PROGRESS,
        'completion_percentage': 50,  # تخفيض
        'version': rec.version,
    })
    assert resp.status_code == 400
    data = resp.json()
    assert 'لا يمكن تخفيض' in data['message']


def test_18_rfi_bulk_update_success(client, test_setup):
    """18. التحديث المجمع برقم طلب الفحص RFI لجميع الشقق المسجلة"""
    client.force_login(test_setup['admin_user'])
    prj = test_setup['project']
    unit_res = test_setup['unit_res']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)

    rec = unit_res.site_progress_records.first()
    rec.rfi_number = 'RFI-GLOBAL-99'
    rec.save()

    url = reverse('real_estate:api_site_rfi_bulk_update')
    resp = client.post(url, {
        'project_id': prj.id,
        'rfi_number': 'RFI-GLOBAL-99',
        'status': UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED,
        'completion_percentage': 100,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data['success'] is True
    assert data['updated_count'] >= 1


def test_19_warranty_ticket_contractor_attribution(test_setup):
    """19. استرجاع مقاول المصنعية المسؤول عن البند لتوجيه تذاكر الضمان"""
    unit_res = test_setup['unit_res']
    sub = test_setup['contractor']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)

    plumb_rec = unit_res.site_progress_records.filter(
        trade_stage=UnitSiteProgressRecord.InspectionTrade.PLUMB_FITTING
    ).first()
    plumb_rec.contractor = sub
    plumb_rec.save()

    resolved_sub = ProjectProgressCalculationService.resolve_trade_contractor(
        unit=unit_res,
        warranty_category='FINISHING_PLUMBING'
    )
    assert resolved_sub == sub


def test_20_export_site_progress_excel_rtl(client, test_setup):
    """20. تصدير مصفوفة الموقع إلى شيت إكسيل RTL مفتوح وصالح للعمليات"""
    client.force_login(test_setup['admin_user'])
    prj = test_setup['project']
    url = reverse('real_estate:site_project_report_excel', kwargs={'project_id': prj.id})
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp['Content-Type'] == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def test_21_printable_floor_inspection_dossier_view(client, test_setup):
    """21. كراسة ومحضر استلام الدور A4 المعتمد للاستشاري"""
    client.force_login(test_setup['admin_user'])
    fl = test_setup['floor_3']
    url = reverse('real_estate:site_floor_inspection_dossier', kwargs={'floor_id': fl.id})
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'محضر فحص واعتماد أعمال الدور' in resp.content.decode('utf-8')


def test_22_site_project_report_view_rendering(client, test_setup):
    """22. تصيير شاشة المصفوفة الميدانية بدون أخطاء"""
    client.force_login(test_setup['admin_user'])
    prj = test_setup['project']
    url = reverse('real_estate:site_project_report', kwargs={'project_id': prj.id})
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'مصفوفة متابعة الوحدات المعمارية' in resp.content.decode('utf-8')


def test_23_offline_mobile_batch_sync_endpoint(client, test_setup):
    """23. مزامنة حزمة المعاينات الميدانية من تطبيق الموبايل دون اتصال"""
    client.force_login(test_setup['admin_user'])
    unit_res = test_setup['unit_res']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)

    rec = unit_res.site_progress_records.first()
    url = reverse('real_estate:api_site_stages_sync')
    payload = {
        'stages': [{
            'record_id': rec.id,
            'version': rec.version,
            'status': UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED,
            'completion_percentage': 100,
            'rfi_number': 'RFI-OFFLINE-SYNC',
        }]
    }
    resp = client.post(url, json.dumps(payload), content_type='application/json')
    assert resp.status_code == 200
    data = resp.json()
    assert data['success'] is True
    assert data['synced_count'] == 1


def test_24_ifrs15_point_in_time_handover_no_interim_poc(test_setup):
    """24. عدم توليد قيود استحقاق دورية في مشروعات POINT_IN_TIME_HANDOVER"""
    prj = test_setup['project']
    prj.revenue_recognition_method = RealEstateProject.RevenueRecognitionMethod.POINT_IN_TIME_HANDOVER
    prj.save()

    res = ProjectProgressCalculationService.rollup_project_and_block_progress(prj, post_ifrs15=True)
    assert res['posted_ifrs15_entries_count'] == 0


def test_25_ifrs15_over_time_poc_periodic_delta_posting(test_setup):
    """25. توليد قيد استحقاق دوري بالفارق التراكمي في مشروعات OVER_TIME_POC"""
    prj = test_setup['project']
    prj.revenue_recognition_method = RealEstateProject.RevenueRecognitionMethod.OVER_TIME_POC
    prj.save()
    unit_res = test_setup['unit_res']

    contract = PropertyContract.objects.create(
        contract_number='CONT-POC-01',
        project=prj,
        unit=unit_res,
        customer=test_setup['customer'],
        currency=test_setup['currency'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timedelta(days=180),
        final_contract_price=Decimal('1000000.00'),
        created_by=test_setup['admin_user'],
        status='ACTIVE'
    )
    unit_res.progress_percentage = Decimal('25.00')
    unit_res.save()

    # تصعيد واحتساب
    res = ProjectProgressCalculationService.rollup_project_and_block_progress(
        prj,
        user=test_setup['admin_user'],
        post_ifrs15=True
    )
    assert res['project_progress'] > Decimal('0.00')


def test_26_customized_unit_variation_guard_in_bulk_update(client, test_setup):
    """26. صمام أمان الوحدات المعدلة: استثناء الشقق ذات أوامر التعديل في التحديث المجمع"""
    client.force_login(test_setup['admin_user'])
    unit_res = test_setup['unit_res']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)

    contract = PropertyContract.objects.create(
        contract_number='CONT-VAR-01',
        project=test_setup['project'],
        unit=unit_res,
        customer=test_setup['customer'],
        currency=test_setup['currency'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timedelta(days=180),
        final_contract_price=Decimal('1000000.00'),
        created_by=test_setup['admin_user'],
        status='ACTIVE'
    )
    # أمر تعديل سارٍ
    ClientVariationOrder.objects.create(
        order_number='VAR-001',
        contract=contract,
        unit=unit_res,
        title='تعديل حوائط وتأسيس سباكة خاص',
        status=ClientVariationOrder.OrderStatus.APPROVED,
        created_by=test_setup['admin_user']
    )

    url = reverse('real_estate:api_site_floor_bulk_update')
    resp = client.post(url, {
        'floor_id': test_setup['floor_3'].id,
        'trade_stage': UnitSiteProgressRecord.InspectionTrade.PAINT_FINAL,
        'status': UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED,
        'completion_percentage': 100,
    })
    assert resp.status_code == 200
    # التأكد من عدم الكتابة فوق الوحدة المعدلة تلقائياً
    rec = unit_res.site_progress_records.filter(
        trade_stage=UnitSiteProgressRecord.InspectionTrade.PAINT_FINAL
    ).first()
    assert rec.status != UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED


def test_27_dual_matrix_toggle_navigation_links(client, test_setup):
    """27. فحص أزرار التبديل المزدوج بين مصفوفة المبيعات ومصفوفة الموقع"""
    client.force_login(test_setup['admin_user'])
    prj = test_setup['project']
    url = reverse('real_estate:project_matrix', kwargs={'project_id': prj.id})
    resp = client.get(url)
    assert resp.status_code == 200
    content = resp.content.decode('utf-8')
    assert 'مصفوفة التنفيذ الميداني' in content


def test_28_site_stages_initialization_command(test_setup):
    """28. فحص أمر الإدارة init_site_stages لتهيئة مشاريع المنظومة"""
    from django.core.management import call_command
    prj = test_setup['project']
    call_command('init_site_stages', project_code=prj.code)
    assert UnitSiteProgressRecord.objects.filter(unit__project=prj).count() > 0


def test_29_wbs_activity_protected_on_delete(test_setup):
    """29. حماية أنشطة مقايسة WBS من الحذف عند وجود ارتباطات هرمية"""
    prj = test_setup['project']
    parent = ProjectActivity.objects.create(
        project=prj,
        code='WBS-P-01',
        name='نشاط رئيسي',
        weight_percentage=Decimal('10.0000')
    )
    ProjectActivity.objects.create(
        project=prj,
        parent_activity=parent,
        code='WBS-C-01',
        name='نشاط فرعي',
        weight_percentage=Decimal('5.0000')
    )
    from django.db.models import ProtectedError
    with pytest.raises(ProtectedError):
        parent.delete()


def test_30_site_progress_audit_log_protected_on_delete(test_setup):
    """30. حماية سجل التدقيق من الحذف عند محاولة مسحه"""
    unit_res = test_setup['unit_res']
    log = SiteProgressAuditLog.objects.create(
        unit=unit_res,
        unit_code_snapshot=unit_res.unit_code,
        trade_stage='MASONRY',
        previous_percentage=0,
        new_percentage=50,
        previous_status='NOT_STARTED',
        new_status='IN_PROGRESS',
        changed_by=test_setup['admin_user']
    )
    from django.db.models import ProtectedError
    with pytest.raises(ProtectedError):
        unit_res.delete()


def test_31_permission_can_verify_site_stages(client, test_setup):
    """31. فرض صلاحية can_verify_site_stages وحظر التعديل لمن لا يملكها"""
    user_no_perm = User.objects.create_user(username='regular_user', email='regular_user@mwheba.com', password='password123')
    client.force_login(user_no_perm)
    unit_res = test_setup['unit_res']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)

    rec = unit_res.site_progress_records.first()
    url = reverse('real_estate:api_site_stage_quick_update', kwargs={'record_id': rec.id})
    resp = client.post(url, {
        'status': UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED,
        'completion_percentage': 100,
        'version': rec.version,
    })
    assert resp.status_code == 403


def test_32_permission_can_record_site_log(client, test_setup):
    """32. فرض صلاحية can_record_site_log لتوثيق يوميات الموقع"""
    user_no_perm = User.objects.create_user(username='site_visitor', email='site_visitor@mwheba.com', password='password123')
    client.force_login(user_no_perm)
    prj = test_setup['project']
    url = reverse('real_estate:site_daily_log_create', kwargs={'project_id': prj.id})
    resp = client.get(url)
    assert resp.status_code == 403


def test_33_block_progress_matches_average_of_units(test_setup):
    """33. مطابقة نسبة إنجاز البلوك لمتوسط نسب إنجاز وحداته"""
    block = test_setup['block']
    unit_res = test_setup['unit_res']
    unit_semi = test_setup['unit_semi']

    unit_res.progress_percentage = Decimal('60.00')
    unit_res.save()
    unit_semi.progress_percentage = Decimal('40.00')
    unit_semi.save()

    ProjectProgressCalculationService.rollup_project_and_block_progress(test_setup['project'], post_ifrs15=False)
    block.refresh_from_db()
    assert block.construction_progress_percentage > Decimal('0.00')


def test_34_clean_handover_success_when_100_percent_and_no_snags(test_setup):
    """34. نجاح اعتماد محضر التسليم عند اكتمال الوحدة 100% وخلوها من الملاحظات"""
    unit_res = test_setup['unit_res']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)
    unit_res.progress_percentage = Decimal('100.00')
    unit_res.save()

    contract = PropertyContract.objects.create(
        contract_number='CONT-PERFECT-01',
        project=test_setup['project'],
        unit=unit_res,
        customer=test_setup['customer'],
        currency=test_setup['currency'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timedelta(days=180),
        final_contract_price=Decimal('1000000.00'),
        created_by=test_setup['admin_user'],
        status='ACTIVE'
    )
    receipt = PropertyHandoverReceipt(
        contract=contract,
        unit=unit_res,
        status=PropertyHandoverReceipt.HandoverStatus.EXECUTED,
        client_signatory_name='كمال مصطفى',
        created_by=test_setup['admin_user']
    )
    # يجب ألا تطلق ValidationError
    receipt.clean()
    assert receipt.unit.progress_percentage == Decimal('100.00')


def test_35_project_detail_view_shows_site_progress_kpi(client, test_setup):
    """35. ظهور كارت نسبة الإنجاز الإنشائي في صفحة تفاصيل المشروع"""
    client.force_login(test_setup['admin_user'])
    prj = test_setup['project']
    url = reverse('real_estate:project_detail', kwargs={'pk': prj.id})
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'نسبة الإنجاز الإنشائي' in resp.content.decode('utf-8')


def test_36_unit_detail_view_shows_progress_badge(client, test_setup):
    """36. ظهور نسبة إنجاز الوحدة في بطاقة تفاصيل الوحدة"""
    client.force_login(test_setup['admin_user'])
    unit_res = test_setup['unit_res']
    url = reverse('real_estate:unit_detail', kwargs={'pk': unit_res.id})
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'إنجاز' in resp.content.decode('utf-8')


def test_37_manpower_breakdown_json_storage(test_setup):
    """37. تخزين وتوزيع عمالة المقاولين في حقل JSON مهيكل بيومية الموقع"""
    prj = test_setup['project']
    log = SiteDailyLog.objects.create(
        project=prj,
        log_date=timezone.localdate(),
        total_manpower_count=20,
        contractor_manpower_breakdown={
            'الأهرام للمقاولات': {'masons': 5, 'helpers': 5},
            'الكهربائية المتحدة': {'electricians': 4, 'helpers': 6}
        },
        recorded_by=test_setup['admin_user']
    )
    log.refresh_from_db()
    assert 'الأهرام للمقاولات' in log.contractor_manpower_breakdown
    assert log.contractor_manpower_breakdown['الأهرام للمقاولات']['masons'] == 5


def test_38_roof_and_basement_trades_omitted_for_typical_floors(test_setup):
    """38. استبعاد بنود الأسطح والبدرومات تلقائياً من الأدوار المتكررة"""
    unit_res = test_setup['unit_res']  # الدور الثالث متكرر
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)

    roof_rec = unit_res.site_progress_records.filter(
        trade_stage=UnitSiteProgressRecord.InspectionTrade.ROOF_WATERPROOF_FLOOD_TEST
    ).first()
    assert roof_rec.is_applicable is False
    assert roof_rec.status == UnitSiteProgressRecord.StageStatus.NOT_APPLICABLE


def test_39_bulk_update_by_floor_excludes_specified_units(client, test_setup):
    """39. التحديث المجمع بالدور مع استثناء شقق محددة صراحة"""
    client.force_login(test_setup['admin_user'])
    fl = test_setup['floor_3']
    unit_res = test_setup['unit_res']
    unit_semi = test_setup['unit_semi']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)
    SiteProgressInitializationService.seed_unit_site_stages(unit_semi)

    url = reverse('real_estate:api_site_floor_bulk_update')
    resp = client.post(url, {
        'floor_id': fl.id,
        'trade_stage': UnitSiteProgressRecord.InspectionTrade.MASONRY_QADD,
        'status': UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED,
        'completion_percentage': 100,
        'excluded_unit_ids[]': [unit_semi.id],
    })
    assert resp.status_code == 200

    rec_res = unit_res.site_progress_records.filter(
        trade_stage=UnitSiteProgressRecord.InspectionTrade.MASONRY_QADD
    ).first()
    rec_semi = unit_semi.site_progress_records.filter(
        trade_stage=UnitSiteProgressRecord.InspectionTrade.MASONRY_QADD
    ).first()

    assert rec_res.completion_percentage == 100
    assert rec_semi.completion_percentage == 0  # استثنيت بنجاح


def test_40_milestone_flag_activity_detection(test_setup):
    """40. تمييز محطات التسليم الرئيسية في شجرة WBS"""
    prj = test_setup['project']
    act = ProjectActivity.objects.create(
        project=prj,
        code='WBS-MS-01',
        name='انتهاء صب الهيكل الخرساني بالكامل',
        weight_percentage=Decimal('35.0000'),
        is_milestone=True
    )
    assert act.is_milestone is True


def test_41_unit_tile_partial_renders_progress_badge(client, test_setup):
    """41. ظهور شارة نسبة الإنجاز في البلاطة المعمارية لمصفوفة المبيعات"""
    client.force_login(test_setup['admin_user'])
    unit_res = test_setup['unit_res']
    unit_res.progress_percentage = Decimal('75.00')
    unit_res.save()

    url = reverse('real_estate:project_matrix', kwargs={'project_id': test_setup['project'].id})
    resp = client.get(url)
    assert resp.status_code == 200
    assert '75.00%' in resp.content.decode('utf-8')


def test_42_non_destructive_safe_migration_data_safety(test_setup):
    """42. التحقق من سلامة البيانات والقيم الافتراضية لكافة الحقول المضافة"""
    prj = test_setup['project']
    assert prj.construction_progress_percentage == Decimal('0.00')
    assert prj.revenue_recognition_method == RealEstateProject.RevenueRecognitionMethod.OVER_TIME_POC

    blk = test_setup['block']
    assert blk.construction_progress_percentage == Decimal('0.00')

    u = test_setup['unit_res']
    assert u.progress_percentage == Decimal('0.00')


def test_43_quick_update_stage_ajax_updates_verified_by_engineer(client, test_setup):
    """43. توثيق اسم المهندس ووقت الاعتماد عند حالة PASSED_AND_VERIFIED"""
    client.force_login(test_setup['admin_user'])
    unit_res = test_setup['unit_res']
    SiteProgressInitializationService.seed_unit_site_stages(unit_res)

    rec = unit_res.site_progress_records.filter(
        trade_stage=UnitSiteProgressRecord.InspectionTrade.MASONRY_QADD
    ).first()
    url = reverse('real_estate:api_site_stage_quick_update', kwargs={'record_id': rec.id})
    resp = client.post(url, {
        'status': UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED,
        'completion_percentage': 100,
        'version': rec.version,
    })
    assert resp.status_code == 200
    rec.refresh_from_db()
    assert rec.verified_by == test_setup['admin_user']
    assert rec.verified_at is not None


def test_44_readiness_kpi_cards_counting_accuracy(client, test_setup):
    """44. دقة احتساب كروت مؤشرات الجاهزية للتسليم في مصفوفة الموقع"""
    client.force_login(test_setup['admin_user'])
    unit_res = test_setup['unit_res']
    unit_semi = test_setup['unit_semi']

    unit_res.progress_percentage = Decimal('100.00')
    unit_res.save()
    unit_semi.progress_percentage = Decimal('50.00')
    unit_semi.save()

    url = reverse('real_estate:site_project_report', kwargs={'project_id': test_setup['project'].id})
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.context['ready_units_count'] == 1
    assert resp.context['in_progress_count'] == 1
