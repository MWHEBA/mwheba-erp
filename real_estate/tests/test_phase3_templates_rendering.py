# -*- coding: utf-8 -*-
from decimal import Decimal
import pytest
from django.urls import reverse
from django.test import Client
from django.contrib.auth import get_user_model
from real_estate.models import RealEstateProject, PropertyBlock, PropertyFloor, PropertyUnit
from core.models import SystemModule

User = get_user_model()


@pytest.fixture
def phase3_setup(db):
    mod, _ = SystemModule.objects.get_or_create(code='real_estate', defaults={'name_ar': 'العقارات', 'is_enabled': True})
    mod.is_enabled = True
    mod.save()

    user = User.objects.create_superuser(username='admin_phase3_test', password='password123', email='admin3@test.com')
    client = Client()
    client.login(username='admin_phase3_test', password='password123')

    project = RealEstateProject.objects.create(
        code='PRJ-P3',
        name='مشروع الياسمين التست',
        project_type=RealEstateProject.ProjectType.RESIDENTIAL,
        status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
        total_land_area=2000,
        gross_built_area=5000,
        start_date='2026-01-01',
        expected_completion_date='2027-01-01',
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, code='B2', name='عمارة 2')
    floor = PropertyFloor.objects.create(block=block, floor_number=2, name='الدور الثاني')
    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code='U201-P3',
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.AVAILABLE,
        gross_area=Decimal('150.00'),
        meter_price=Decimal('25000.00'),
        total_price=Decimal('3750000.00')
    )

    return {
        'client': client,
        'user': user,
        'project': project,
        'block': block,
        'floor': floor,
        'unit': unit
    }


@pytest.mark.django_db
def test_unit_list_view_renders_correctly(phase3_setup):
    client = phase3_setup['client']
    url = reverse('real_estate:unit_list')
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'real_estate/unit_list.html' in [t.name for t in resp.templates]
    assert 'U201-P3' in resp.content.decode('utf-8')


@pytest.mark.django_db
def test_unit_list_ajax_search(phase3_setup):
    client = phase3_setup['client']
    url = reverse('real_estate:unit_list') + '?q=U201&ajax=1'
    resp = client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp.status_code == 200
    data = resp.json()
    assert data['success'] is True
    assert 'table_html' in data
    assert 'U201-P3' in data['table_html']


@pytest.mark.django_db
def test_unit_detail_view_renders_correctly(phase3_setup):
    client = phase3_setup['client']
    unit = phase3_setup['unit']
    url = reverse('real_estate:unit_detail', kwargs={'pk': unit.id})
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'real_estate/unit_detail.html' in [t.name for t in resp.templates]
    content = resp.content.decode('utf-8')
    assert unit.unit_code in content
    assert 'المواصفات الفنية والمعمارية' in content


@pytest.mark.django_db
def test_unit_create_and_update_views(phase3_setup):
    client = phase3_setup['client']
    unit = phase3_setup['unit']

    # GET create
    resp_create = client.get(reverse('real_estate:unit_create'))
    assert resp_create.status_code == 200
    assert 'real_estate/unit_form.html' in [t.name for t in resp_create.templates]

    # GET update
    resp_update = client.get(reverse('real_estate:unit_update', kwargs={'pk': unit.id}))
    assert resp_update.status_code == 200
    assert 'real_estate/unit_form.html' in [t.name for t in resp_update.templates]
    assert unit.unit_code in resp_update.content.decode('utf-8')


@pytest.mark.django_db
def test_pricing_matrix_view_renders_correctly(phase3_setup):
    client = phase3_setup['client']
    project = phase3_setup['project']
    url = reverse('real_estate:project_pricing', kwargs={'project_id': project.id})
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'real_estate/pricing_matrix.html' in [t.name for t in resp.templates]
    content = resp.content.decode('utf-8')
    assert project.name in content
    assert 'مصفوفة التسعير الآلي للوحدات' in content
