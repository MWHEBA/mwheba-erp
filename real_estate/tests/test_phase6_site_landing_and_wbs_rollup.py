# -*- coding: utf-8 -*-
"""
Phase 6 Automated Tests:
Central Site Reports Landing, Auto-Rollup Bridge for WBS & IFRS 15, and Bulk Update Custom Variation Guard.
MWHEBA ERP — Real Estate Parity Master Plan
"""
from datetime import timedelta
from decimal import Decimal
import pytest
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.test import Client

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    UnitSiteProgressRecord,
    ProjectActivity,
    ClientVariationOrder,
    UnitFinishingOrder,
    UnitSnagItem,
)
from real_estate.services.site_progress_service import (
    ProjectProgressCalculationService,
    SiteProgressInitializationService,
)
from real_estate.services.wbs_service import WbsTreeGovernanceService, UnitToWbsBridgeService

User = get_user_model()


@pytest.fixture
def auth_client():
    from core.models import SystemModule
    from core.middleware.module_control import ModuleAccessMiddleware
    mod, _ = SystemModule.objects.get_or_create(
        code='real_estate',
        defaults={'name_ar': 'العقارات', 'is_enabled': True}
    )
    mod.is_enabled = True
    mod.save()
    ModuleAccessMiddleware.invalidate_cache()

    user = User.objects.create_superuser(
        username='phase6_admin',
        email='phase6@mwheba.com',
        password='AdminPassword123!'
    )
    client = Client()
    client.force_login(user)
    return client, user


@pytest.fixture
def site_project_setup(auth_client):
    _, user = auth_client
    project = RealEstateProject.objects.create(
        code="PRJ-P6-01",
        name="برج الفيروز التجاري",
        project_type=RealEstateProject.ProjectType.COMMERCIAL,
        status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
        revenue_recognition_method=RealEstateProject.RevenueRecognitionMethod.OVER_TIME_POC,
        start_date=timezone.localdate(),
        expected_completion_date=timezone.localdate() + timedelta(days=365),
        construction_progress_percentage=Decimal("0.00"),
        created_by=user,
    )
    block = PropertyBlock.objects.create(
        project=project,
        code="B1",
        name="عمارة A",
        construction_progress_percentage=Decimal("0.00"),
    )
    floor = PropertyFloor.objects.create(
        block=block,
        floor_number=1,
        name="الدور الأول",
    )
    unit1 = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="U-P6-101",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.AVAILABLE,
        net_area=Decimal("120.00"),
        gross_area=Decimal("140.00"),
        meter_price=Decimal("10000.00"),
        total_price=Decimal("1400000.00"),
        progress_percentage=Decimal("0.00"),
    )
    unit2 = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="U-P6-102",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.AVAILABLE,
        net_area=Decimal("120.00"),
        gross_area=Decimal("140.00"),
        meter_price=Decimal("10000.00"),
        total_price=Decimal("1400000.00"),
        progress_percentage=Decimal("0.00"),
    )
    return {
        'project': project,
        'block': block,
        'floor': floor,
        'unit1': unit1,
        'unit2': unit2,
    }


@pytest.mark.django_db
def test_site_reports_landing_view(auth_client, site_project_setup):
    """
    اختبار شاشة الهبوط المركزية لمتابعة المواقع:
    - التحقق من كود الاستجابة 200 OK.
    - التحقق من ظهور كروت المؤشرات وكروت المشروعات وعناصر التنقل.
    """
    client, user = auth_client
    project = site_project_setup['project']
    unit1 = site_project_setup['unit1']

    # إضافة ملاحظة فنية للتأكد من حساب المؤشرات
    UnitSnagItem.objects.create(
        unit=unit1,
        room_location="صالة الاستقبال",
        category="CIVIL_MASONRY",
        severity=UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER,
        description="شروخ إنشائية غير مقبولة",
        status=UnitSnagItem.SnagStatus.OPEN,
        created_by=user,
    )

    url = reverse('real_estate:site_reports_landing')
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode('utf-8')
    assert "شاشة هبوط ومتابعة المواقع الميدانية" in content
    assert project.name in content
    assert project.code in content
    assert "PRJ-P6-01" in content
    assert "مصفوفة الـ 32 بنداً" in content

    # فحص فلترة البحث بالاسم أو الكود
    resp_search = client.get(url + "?q=الفيروز")
    assert resp_search.status_code == 200
    assert project.code in resp_search.content.decode('utf-8')

    resp_empty = client.get(url + "?q=مشروع_غير_موجود")
    assert resp_empty.status_code == 200
    assert "لا توجد مشروعات مطابقة" in resp_empty.content.decode('utf-8')


@pytest.mark.django_db
def test_url_reversal_parity():
    """
    اختبار صحة توليد الروابط المستحدثة في المرحلة 6 (Zero NoReverseMatch).
    """
    landing_url = reverse('real_estate:site_reports_landing')
    matrix_url = reverse('real_estate:site_progress_matrix', kwargs={'project_id': 99})
    report_url = reverse('real_estate:site_project_report', kwargs={'project_id': 99})

    assert landing_url == '/real-estate/site-reports/'
    assert matrix_url == '/real-estate/projects/99/site-matrix/'
    assert report_url == '/real-estate/projects/99/site-report/'


@pytest.mark.django_db
def test_automated_live_wbs_rollup_bridge(site_project_setup, auth_client):
    """
    اختبار محرك التصعيد التلقائي بين إنجاز الوحدات وشجرة WBS:
    - التحقق من قيام rollup_project_and_block_progress بمزامنة الأنشطة الورقية تلقائياً
      ثم تصعيد النسب للمشروع ككل.
    """
    _, user = auth_client
    project = site_project_setup['project']
    unit1 = site_project_setup['unit1']
    unit2 = site_project_setup['unit2']

    # 1. إنشاء شجرة WBS: جذر (Root) ونشاط ورقي (Leaf) مرتبط بالمباني
    root_act = ProjectActivity.objects.create(
        project=project,
        code="WBS-ROOT",
        name="الأعمال المعمارية والتشطيبات",
        activity_type=ProjectActivity.ActivityType.GENERAL,
        weight_percentage=Decimal("100.0000"),
        progress_percentage=Decimal("0.00"),
    )
    leaf_act = ProjectActivity.objects.create(
        project=project,
        parent_activity=root_act,
        code="WBS-MASONRY",
        name="بند مباني الطوب والحوائط",
        activity_type=ProjectActivity.ActivityType.TRADE_CATEGORY,
        trade_category=ProjectActivity.TradeCategory.MASONRY,
        weight_percentage=Decimal("100.0000"),
        auto_sync_progress=True,
        progress_percentage=Decimal("0.00"),
    )

    # 2. تهيئة سجلات الفحص الميداني للوحدات
    SiteProgressInitializationService.seed_unit_site_stages(unit1)
    SiteProgressInitializationService.seed_unit_site_stages(unit2)

    # 3. إنجاز بند المباني للوحدتين 100%
    records = UnitSiteProgressRecord.objects.filter(
        unit__in=[unit1, unit2],
        trade_stage__in=[
            UnitSiteProgressRecord.InspectionTrade.MASONRY_QADD,
            UnitSiteProgressRecord.InspectionTrade.MASONRY_FULL,
        ]
    )
    for r in records:
        r.completion_percentage = 100
        r.status = UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED
        r.save()

    # 4. تشغيل محرك التصعيد الشامل
    res = ProjectProgressCalculationService.rollup_project_and_block_progress(project, user=user)

    # 5. التحقق من مزامنة نشاط الـ WBS وتصعيده للمشروع
    leaf_act.refresh_from_db()
    root_act.refresh_from_db()
    project.refresh_from_db()

    assert leaf_act.progress_percentage == Decimal("100.00")
    assert root_act.progress_percentage == Decimal("100.00")
    assert project.construction_progress_percentage == Decimal("100.00")
    assert res['project_progress'] == Decimal("100.00")


@pytest.mark.django_db
def test_bulk_update_floor_stage_custom_variation_guard(auth_client, site_project_setup):
    """
    اختبار حماية الوحدات ذات أوامر التعديل المعمارية الموحدة (CUSTOM_VARIATION)
    من التعديل المجمع التلقائي لدور العمارة (Bulk Floor Approval Guard).
    """
    client, user = auth_client
    floor = site_project_setup['floor']
    unit1 = site_project_setup['unit1']
    unit2 = site_project_setup['unit2']

    # تهيئة مراحل الفحص للوحدتين
    SiteProgressInitializationService.seed_unit_site_stages(unit1)
    SiteProgressInitializationService.seed_unit_site_stages(unit2)

    # إنشاء عميل وعقد وأمر تعديل معماري مخصص للوحدة 1 (CUSTOM_VARIATION)
    from customer.models import Customer
    from financial.models.currency import Currency
    from real_estate.models import PropertyContract

    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "Egyptian Pound", "symbol": "ج.م", "is_functional": True}
    )
    customer = Customer.objects.create(
        name="عميل اختبار التعديلات",
        code="CUST-P6-01",
        phone="01099887766"
    )
    contract = PropertyContract.objects.create(
        contract_number="CNT-P6-101",
        project=site_project_setup['project'],
        unit=unit1,
        customer=customer,
        status="ACTIVE",
        currency=currency,
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timedelta(days=180),
        final_contract_price=Decimal("1400000.00"),
        created_by=user,
    )
    UnitFinishingOrder.objects.create(
        order_number="FO-P6-0001",
        unit=unit1,
        contract=contract,
        customer=customer,
        title="طلب تعديل معماري مخصص",
        order_type=UnitFinishingOrder.OrderType.CUSTOM_VARIATION,
        current_stage=UnitFinishingOrder.OrderStage.IN_EXECUTION,
        created_by=user,
    )

    url = reverse('real_estate:api_site_floor_bulk_update')
    payload = {
        'floor_id': floor.id,
        'trade_stage': UnitSiteProgressRecord.InspectionTrade.MASONRY_QADD,
        'status': UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED,
        'completion_percentage': 100,
    }

    # تنفيذ التحديث المجمع لكامل الدور دون تحديد استثناءات يدوية
    response = client.post(url, data=payload)
    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True

    rec_unit1 = UnitSiteProgressRecord.objects.get(
        unit=unit1,
        trade_stage=UnitSiteProgressRecord.InspectionTrade.MASONRY_QADD
    )
    rec_unit2 = UnitSiteProgressRecord.objects.get(
        unit=unit2,
        trade_stage=UnitSiteProgressRecord.InspectionTrade.MASONRY_QADD
    )

    # الوحدة 1 محمية بأمر التعديل المعماري: يجب ألا تتأثر
    assert rec_unit1.completion_percentage == 0
    assert rec_unit1.status == UnitSiteProgressRecord.StageStatus.NOT_STARTED

    # الوحدة 2 قياسية: تم تحديثها بنجاح
    assert rec_unit2.completion_percentage == 100
    assert rec_unit2.status == UnitSiteProgressRecord.StageStatus.PASSED_AND_VERIFIED
