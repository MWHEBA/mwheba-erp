# -*- coding: utf-8 -*-
from decimal import Decimal
import pytest
from django.urls import reverse
from django.test import Client
from django.contrib.auth import get_user_model
from django.core.cache import cache
from core.models import SystemModule
from core.middleware.module_control import ModuleAccessMiddleware
from real_estate.models import RealEstateProject, PropertyBlock, PropertyFloor, PropertyUnit, UnitBooking, PropertyContract

User = get_user_model()


@pytest.fixture
def phase5_setup(db):
    cache.delete('enabled_modules_set')
    cache.delete('module_namespace_map')

    mod, _ = SystemModule.objects.get_or_create(code='real_estate', defaults={'name_ar': 'العقارات', 'is_enabled': True})
    mod.is_enabled = True
    mod.save()
    ModuleAccessMiddleware.invalidate_cache()

    user = User.objects.create_superuser(username='admin_phase5_test', password='password123', email='admin5@test.com')
    client = Client()
    client.login(username='admin_phase5_test', password='password123')

    project = RealEstateProject.objects.create(
        code='PRJ-P5',
        name='مشروع الزمردة التست',
        project_type=RealEstateProject.ProjectType.RESIDENTIAL,
        status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
        total_land_area=3000,
        gross_built_area=8000,
        start_date='2026-01-01',
        expected_completion_date='2027-01-01',
        created_by=user
    )

    return {
        'client': client,
        'user': user,
        'project': project,
        'module': mod
    }


@pytest.mark.django_db
def test_real_estate_executive_dashboard_renders(phase5_setup):
    """
    التحقق من تحميل لوحة مؤشرات القطاع العقاري التنفيذية وكافة مؤشراتها المالية
    """
    client = phase5_setup['client']
    url = reverse('real_estate:dashboard')
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'real_estate/dashboard.html' in [t.name for t in resp.templates]
    content = resp.content.decode('utf-8')
    assert 'لوحة المؤشرات والقيادة التنفيذية للقطاع العقاري' in content
    assert 'PRJ-P5' in content
    assert 'إجمالي القيمة التعاقدية' in content


@pytest.mark.django_db
def test_real_estate_module_toggle_complete_lifecycle(phase5_setup):
    """
    التحقق الصارم من سلوك النظام الكامل عند تفعيل وتعطيل تطبيق العقارات من SystemModule:
    1. عند التفعيل: روابط الشريط الجانبي تظهر، ولوحة التحكم تعرض بطاقة العقارات، والمسارات تعمل 200.
    2. عند التعطيل: الروابط تختفي تماماً، ومسارات العقارات تعيد التوجيه (302) للوحة التحكم الرئيسية.
    """
    client = phase5_setup['client']
    mod = phase5_setup['module']

    # 1. حالة التفعيل (ENABLED)
    mod.is_enabled = True
    mod.save()
    ModuleAccessMiddleware.invalidate_cache()

    # Sidebar / Dashboard Home
    resp_home = client.get(reverse('core:dashboard'))
    assert resp_home.status_code == 200
    home_content = resp_home.content.decode('utf-8')
    assert 'real_estate:dashboard' in home_content or 'القطاع العقاري' in home_content

    # المسارات العقارية تعمل بكفاءة
    assert client.get(reverse('real_estate:dashboard')).status_code == 200
    assert client.get(reverse('real_estate:project_list')).status_code == 200
    assert client.get(reverse('real_estate:unit_list')).status_code == 200
    assert client.get(reverse('real_estate:booking_list')).status_code == 200
    assert client.get(reverse('real_estate:contract_list')).status_code == 200

    # 2. حالة التعطيل (DISABLED)
    mod.is_enabled = False
    mod.save()
    ModuleAccessMiddleware.invalidate_cache()

    # Sidebar / Dashboard Home: يجب اختفاء قسم العقارات تماماً
    resp_home_disabled = client.get(reverse('core:dashboard'))
    assert resp_home_disabled.status_code == 200
    disabled_content = resp_home_disabled.content.decode('utf-8')
    # التأكد من اختفاء قائمة الـ sidebar الخاصة بالعقارات
    assert 'real-estate-menu' not in disabled_content
    assert 'quick-real-estate-action' not in disabled_content

    # المسارات العقارية محظورة فورياً وتعيد التوجيه إلى لوحة التحكم الرئيسية 302
    resp_re_dash = client.get(reverse('real_estate:dashboard'))
    assert resp_re_dash.status_code == 302
    assert resp_re_dash.url in ['/dashboard/', '/']

    resp_re_proj = client.get(reverse('real_estate:project_list'))
    assert resp_re_proj.status_code == 302
