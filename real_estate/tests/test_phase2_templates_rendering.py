# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from django.urls import reverse
from django.test import Client
from django.contrib.auth import get_user_model
from real_estate.models import RealEstateProject, PropertyBlock, PropertyFloor, PropertyUnit
from core.models import SystemModule

User = get_user_model()


@pytest.fixture
def test_setup(db):
    # Enable real estate module
    mod, _ = SystemModule.objects.get_or_create(code='real_estate', defaults={'name_ar': 'العقارات', 'is_enabled': True})
    mod.is_enabled = True
    mod.save()

    # Create admin user
    user = User.objects.create_superuser(username='admin_ui_test', password='password123', email='admin@test.com')
    client = Client()
    client.login(username='admin_ui_test', password='password123')

    # Create sample project, block, floor, unit
    project = RealEstateProject.objects.create(
        code='PRJ-PHASE2',
        name='مشروع النرجس التست',
        project_type=RealEstateProject.ProjectType.RESIDENTIAL,
        status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
        total_land_area=1500,
        gross_built_area=3500,
        start_date='2026-01-01',
        expected_completion_date='2027-01-01',
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, code='B1', name='عمارة 1')
    floor = PropertyFloor.objects.create(block=block, floor_number=1, name='الدور الأول')
    unit1 = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code='U101',
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.AVAILABLE,
        gross_area=Decimal('120.00'),
        meter_price=Decimal('20000.00'),
        total_price=Decimal('2400000.00')
    )
    unit2 = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code='U102',
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.RESERVED,
        gross_area=Decimal('130.00'),
        meter_price=Decimal('21000.00'),
        total_price=Decimal('2730000.00')
    )

    return {
        'client': client,
        'user': user,
        'project': project,
        'block': block,
        'floor': floor,
        'unit1': unit1,
        'unit2': unit2
    }


@pytest.mark.django_db
def test_project_list_view_renders_correctly(test_setup):
    client = test_setup['client']
    url = reverse('real_estate:project_list')
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'real_estate/project_list.html' in [t.name for t in resp.templates]
    assert 'PRJ-PHASE2' in resp.content.decode('utf-8')
    assert 'مشروع النرجس التست' in resp.content.decode('utf-8')


@pytest.mark.django_db
def test_project_list_ajax_search(test_setup):
    client = test_setup['client']
    url = reverse('real_estate:project_list') + '?q=النرجس&ajax=1'
    resp = client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp.status_code == 200
    data = resp.json()
    assert data['success'] is True
    assert 'table_html' in data
    assert 'PRJ-PHASE2' in data['table_html']


@pytest.mark.django_db
def test_project_detail_view_renders_correctly(test_setup):
    client = test_setup['client']
    project = test_setup['project']
    url = reverse('real_estate:project_detail', kwargs={'pk': project.id})
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'real_estate/project_detail.html' in [t.name for t in resp.templates]
    content = resp.content.decode('utf-8')
    assert project.name in content
    assert 'عمارة 1' in content
    assert 'U101' in content


@pytest.mark.django_db
def test_project_create_and_update_views(test_setup):
    client = test_setup['client']
    project = test_setup['project']

    # GET create
    resp_create = client.get(reverse('real_estate:project_create'))
    assert resp_create.status_code == 200
    assert 'real_estate/project_form.html' in [t.name for t in resp_create.templates]

    # GET update
    resp_update = client.get(reverse('real_estate:project_update', kwargs={'pk': project.id}))
    assert resp_update.status_code == 200
    assert 'real_estate/project_form.html' in [t.name for t in resp_update.templates]
    assert project.name in resp_update.content.decode('utf-8')


@pytest.mark.django_db
def test_project_matrix_view_renders_correctly(test_setup):
    client = test_setup['client']
    project = test_setup['project']
    url = reverse('real_estate:project_matrix', kwargs={'project_id': project.id})
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'real_estate/matrix.html' in [t.name for t in resp.templates]
    content = resp.content.decode('utf-8')
    assert 'U101' in content
    assert 'U102' in content
    assert 'الدور الأول' in content
