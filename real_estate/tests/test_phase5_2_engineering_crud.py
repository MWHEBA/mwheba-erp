# -*- coding: utf-8 -*-
"""
Tests for Phase 5.2 - Engineering & Quality (Variation Orders & Field Snagging)
MWHEBA ERP — Real Estate Architectural Variations, Milestone Cut-Off & Offline Snagging
"""
import uuid
import json
import pytest
from decimal import Decimal
from datetime import date
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from customer.models import Customer
from core.models import SystemModule
from core.middleware.module_control import ModuleAccessMiddleware
from django.core.cache import cache
from financial.models import Currency
from sale.models.installments import InstallmentPlan, InstallmentItem
from real_estate.models.project import RealEstateProject
from real_estate.models.topology import PropertyBlock, PropertyFloor
from real_estate.models.unit import PropertyUnit
from real_estate.models.contract import PropertyContract
from real_estate.models.engineering import ClientVariationOrder, UnitSnagItem
from supplier.models import Supplier

User = get_user_model()


@pytest.fixture
def engineering_setup(db):
    cache.delete('enabled_modules_set')
    cache.delete('module_namespace_map')

    mod, _ = SystemModule.objects.get_or_create(code='real_estate', defaults={'name_ar': 'العقارات', 'is_enabled': True})
    mod.is_enabled = True
    mod.save()
    ModuleAccessMiddleware.invalidate_cache()

    user = User.objects.create_superuser(
        username="super_architect",
        email="architect@test.com",
        password="password123"
    )
    currency, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True})

    customer = Customer.objects.create(
        code="CUST-ENG-01",
        name="م. عمر الخواجة",
        default_currency=currency
    )

    project = RealEstateProject.objects.create(
        code="PRJ-ENG-01",
        name="كمبوند المروة بلازا",
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        total_land_area=Decimal("15000.00"),
        gross_built_area=Decimal("50000.00"),
        created_by=user
    )

    block = PropertyBlock.objects.create(project=project, code="B-ENG-01", name="بلوك 1")
    floor = PropertyFloor.objects.create(block=block, floor_number=3, name="الدور الثالث")

    unit = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="MW-U301",
        gross_area=Decimal("180.00"),
        net_area=Decimal("150.00"),
        meter_price=Decimal("40000.00"),
        total_price=Decimal("7200000.00"),
        status=PropertyUnit.UnitStatus.CONTRACTED
    )

    plan = InstallmentPlan.objects.create(
        sale=None,
        total_principal=Decimal("6000000.00"),
        total_amount=Decimal("6000000.00"),
        number_of_installments=4,
        start_date=date(2026, 1, 1),
        customer=customer,
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=user
    )

    contract = PropertyContract.objects.create(
        contract_number="CTR-MW-2026-301",
        project=project,
        unit=unit,
        customer=customer,
        installment_plan=plan,
        contract_date=date(2026, 1, 1),
        delivery_date=date(2027, 12, 31),
        final_contract_price=Decimal("7200000.00"),
        down_payment=Decimal("1200000.00"),
        currency=currency,
        created_by=user,
        status=PropertyContract.ContractStatus.ACTIVE
    )

    contractor = Supplier.objects.create(
        name="شركة الأهرام للمقاولات العامة",
        code="CONTR-ENG-01",
        is_active=True
    )

    return {
        "user": user,
        "customer": customer,
        "project": project,
        "unit": unit,
        "plan": plan,
        "contract": contract,
        "contractor": contractor
    }


@pytest.mark.django_db
class TestPhase52VariationOrders:
    """اختبارات دورة حياة أوامر التعديلات المعمارية وفرملة مراحل البناء الهندسية"""

    def test_variation_list_view(self, client, engineering_setup):
        user = engineering_setup["user"]
        contract = engineering_setup["contract"]
        client.force_login(user)

        # Create sample variation order
        ClientVariationOrder.objects.create(
            order_number="VO-TEST-001",
            contract=contract,
            unit=contract.unit,
            variation_type=ClientVariationOrder.VariationType.FINISHING_COSMETIC,
            stage_at_request=ClientVariationOrder.ProjectStage.UNDER_CONSTRUCTION,
            title="تعديل رخام الحمام الرئيسي",
            description="توريد رخام كرارا إيطالي",
            material_cost=Decimal("25000.00"),
            labor_cost=Decimal("5000.00"),
            supervision_fee=Decimal("3000.00"),
            created_by=user
        )

        url = reverse('real_estate:variation_list')
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert "VO-TEST-001" in content
        assert "تعديل رخام الحمام الرئيسي" in content
        assert "33,000.00" in content

    def test_create_variation_order_under_construction_success(self, client, engineering_setup):
        user = engineering_setup["user"]
        contract = engineering_setup["contract"]
        client.force_login(user)

        url = reverse('real_estate:variation_create')
        # GET form
        resp_get = client.get(url)
        assert resp_get.status_code == 200

        # POST valid order during open structure stage
        payload = {
            'contract': contract.id,
            'variation_type': ClientVariationOrder.VariationType.STRUCTURAL,
            'stage_at_request': ClientVariationOrder.ProjectStage.UNDER_CONSTRUCTION,
            'title': 'فتح غرفة الملابس على الحمام',
            'description': 'إزالة القاطع المباني وتعديل فتحة الباب',
            'demolition_rework_cost': '10000.00',
            'material_cost': '15000.00',
            'labor_cost': '8000.00',
            'supervision_fee': '4000.00'
        }
        resp_post = client.post(url, data=payload)
        assert resp_post.status_code == 302

        order = ClientVariationOrder.objects.get(title='فتح غرفة الملابس على الحمام')
        assert order.status == ClientVariationOrder.OrderStatus.ENGINEERING_REVIEW
        assert order.demolition_rework_cost == Decimal('10000.00')
        assert order.total_cost == Decimal('37000.00')

    def test_create_variation_order_milestone_guard_blocks_structural_post_rough_in(self, client, engineering_setup):
        """التحقق من أن فرملة المراحل الهندسية تمنع التعديلات الإنشائية بعد مرحلة تأسيس السباكة"""
        user = engineering_setup["user"]
        contract = engineering_setup["contract"]
        client.force_login(user)

        url = reverse('real_estate:variation_create')
        payload = {
            'contract': contract.id,
            'variation_type': ClientVariationOrder.VariationType.STRUCTURAL,
            'stage_at_request': ClientVariationOrder.ProjectStage.POST_ROUGH_IN,  # 🚫 ممنوع
            'title': 'محاولة تكسير حائط بعد تمديد السباكة والعزل',
            'description': 'طلب غير مطابق هندسياً',
            'demolition_rework_cost': '20000.00',
            'material_cost': '5000.00',
            'labor_cost': '5000.00',
            'supervision_fee': '2000.00'
        }
        resp = client.post(url, data=payload)
        # Should stay on page and show error
        assert resp.status_code == 200
        content = resp.content.decode('utf-8')
        assert "يُحظر إجراء أي تعديلات إنشائية أو كهروميكانيكية" in content
        assert not ClientVariationOrder.objects.filter(title='محاولة تكسير حائط بعد تمديد السباكة والعزل').exists()

    def test_approve_and_schedule_variation_order(self, client, engineering_setup):
        """اختبار اعتماد أمر التعديل وجدولة قيمته كقسط ملحق إضافي في خطة الأقساط"""
        user = engineering_setup["user"]
        contract = engineering_setup["contract"]
        plan = engineering_setup["plan"]
        client.force_login(user)

        order = ClientVariationOrder.objects.create(
            order_number="VO-APP-001",
            contract=contract,
            unit=contract.unit,
            variation_type=ClientVariationOrder.VariationType.FINISHING_COSMETIC,
            stage_at_request=ClientVariationOrder.ProjectStage.FINAL_FINISHING,
            title="إضافة إضاءة مخفية وبانوهات خشبية",
            description="أعمال تشطيبات ديكورية",
            material_cost=Decimal("40000.00"),
            labor_cost=Decimal("15000.00"),
            supervision_fee=Decimal("5000.00"),
            created_by=user
        )
        assert order.total_cost == Decimal("60000.00")

        initial_installments_count = plan.items.count()
        initial_principal = plan.total_principal

        approve_url = reverse('real_estate:variation_approve', kwargs={'pk': order.pk})
        resp = client.post(approve_url, data={'due_date': '2027-11-15'})
        assert resp.status_code == 302

        order.refresh_from_db()
        assert order.status == ClientVariationOrder.OrderStatus.APPROVED
        assert order.approved_by == user
        assert order.supplemental_installment_item is not None

        supplemental_item = order.supplemental_installment_item
        assert supplemental_item.is_supplemental is True
        assert supplemental_item.total_amount == Decimal("60000.00")
        assert supplemental_item.due_date == date(2027, 11, 15)

        plan.refresh_from_db()
        assert plan.items.count() == initial_installments_count + 1
        assert plan.total_principal == initial_principal + Decimal("60000.00")

    def test_reject_variation_order(self, client, engineering_setup):
        user = engineering_setup["user"]
        contract = engineering_setup["contract"]
        client.force_login(user)

        order = ClientVariationOrder.objects.create(
            order_number="VO-REJ-001",
            contract=contract,
            unit=contract.unit,
            variation_type=ClientVariationOrder.VariationType.ELECTRICAL,
            stage_at_request=ClientVariationOrder.ProjectStage.UNDER_CONSTRUCTION,
            title="تعديل لوحة القواطع الرئيسية",
            description="طلب حمولة إضافية",
            material_cost=Decimal("10000.00"),
            labor_cost=Decimal("2000.00"),
            created_by=user
        )

        reject_url = reverse('real_estate:variation_reject', kwargs={'pk': order.pk})
        resp = client.post(reject_url, data={'rejection_reason': 'القدرة الكهربائية للمحول لا تتحمل هذه الزيادة'})
        assert resp.status_code == 302

        order.refresh_from_db()
        assert order.status == ClientVariationOrder.OrderStatus.REJECTED
        assert order.rejection_reason == 'القدرة الكهربائية للمحول لا تتحمل هذه الزيادة'

    def test_variation_detail_view(self, client, engineering_setup):
        user = engineering_setup["user"]
        contract = engineering_setup["contract"]
        client.force_login(user)

        order = ClientVariationOrder.objects.create(
            order_number="VO-DTL-001",
            contract=contract,
            unit=contract.unit,
            variation_type=ClientVariationOrder.VariationType.FINISHING_COSMETIC,
            stage_at_request=ClientVariationOrder.ProjectStage.UNDER_CONSTRUCTION,
            title="تجليد حوائط خشب طبيعي",
            description="خشب جوز تركي مع عزل صوتي",
            demolition_rework_cost=Decimal("5000.00"),
            material_cost=Decimal("30000.00"),
            labor_cost=Decimal("12000.00"),
            supervision_fee=Decimal("3000.00"),
            created_by=user
        )

        detail_url = reverse('real_estate:variation_detail', kwargs={'pk': order.pk})
        resp = client.get(detail_url)
        assert resp.status_code == 200
        content = resp.content.decode('utf-8')
        assert "VO-DTL-001" in content
        assert "تجليد حوائط خشب طبيعي" in content
        assert "50,000.00" in content

    def test_variation_update_view(self, client, engineering_setup):
        user = engineering_setup["user"]
        contract = engineering_setup["contract"]
        client.force_login(user)

        order = ClientVariationOrder.objects.create(
            order_number="VO-UPD-001",
            contract=contract,
            unit=contract.unit,
            variation_type=ClientVariationOrder.VariationType.FINISHING_COSMETIC,
            stage_at_request=ClientVariationOrder.ProjectStage.UNDER_CONSTRUCTION,
            title="تعديل ورق حائط",
            description="ورق حائط ألماني",
            material_cost=Decimal("15000.00"),
            labor_cost=Decimal("4000.00"),
            created_by=user
        )

        update_url = reverse('real_estate:variation_update', kwargs={'pk': order.pk})
        # GET form
        resp_get = client.get(update_url)
        assert resp_get.status_code == 200

        # POST update
        payload = {
            'variation_type': ClientVariationOrder.VariationType.FINISHING_COSMETIC,
            'stage_at_request': ClientVariationOrder.ProjectStage.UNDER_CONSTRUCTION,
            'title': 'تعديل ورق حائط مجسم 3D',
            'description': 'ورق حائط ألماني مجسم مقاوم للرطوبة',
            'demolition_rework_cost': '0.00',
            'material_cost': '22000.00',
            'labor_cost': '6000.00',
            'supervision_fee': '2000.00'
        }
        resp_post = client.post(update_url, data=payload)
        assert resp_post.status_code == 302

        order.refresh_from_db()
        assert order.title == 'تعديل ورق حائط مجسم 3D'
        assert order.total_cost == Decimal('30000.00')


@pytest.mark.django_db
class TestPhase52SnagItems:
    """اختبارات بنود فحص الموقع وملاحظات الاستلام الميدانية والـ Offline Sync"""

    def test_snag_list_view(self, client, engineering_setup):
        user = engineering_setup["user"]
        unit = engineering_setup["unit"]
        contract = engineering_setup["contract"]
        client.force_login(user)

        # Create 2 snags (one minor, one blocker)
        UnitSnagItem.objects.create(
            unit=unit,
            contract=contract,
            room_location="غرفة النوم الرئيسية",
            category=UnitSnagItem.SnagCategory.PAINTING,
            severity=UnitSnagItem.SnagSeverity.MINOR,
            description="خدوش بسيطة في دهان الحائط",
            status=UnitSnagItem.SnagStatus.OPEN,
            created_by=user
        )

        UnitSnagItem.objects.create(
            unit=unit,
            contract=contract,
            room_location="الحمام الرئيسي",
            category=UnitSnagItem.SnagCategory.PLUMBING,
            severity=UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER,
            description="تسريب في محبس الدفن الرئيسي",
            status=UnitSnagItem.SnagStatus.OPEN,
            created_by=user
        )

        url = reverse('real_estate:snag_list')
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode('utf-8')
        assert "غرفة النوم الرئيسية" in content
        assert "الحمام الرئيسي" in content
        assert "مانعة للتسليم" in content

    def test_snag_create_view(self, client, engineering_setup):
        user = engineering_setup["user"]
        unit = engineering_setup["unit"]
        contractor = engineering_setup["contractor"]
        client.force_login(user)

        url = reverse('real_estate:snag_create')
        payload = {
            'unit': unit.id,
            'room_location': 'ريسبشن',
            'category': UnitSnagItem.SnagCategory.ALUMINUM_GLASS,
            'severity': UnitSnagItem.SnagSeverity.MAJOR,
            'description': 'صعوبة في فتح وضلفة شباك الألوميتال',
            'contractor': contractor.id
        }
        resp = client.post(url, data=payload)
        assert resp.status_code == 302

        snag = UnitSnagItem.objects.get(description='صعوبة في فتح وضلفة شباك الألوميتال')
        assert snag.unit == unit
        assert snag.contract == engineering_setup["contract"]
        assert snag.contractor == contractor
        assert snag.created_by == user
        assert snag.status == UnitSnagItem.SnagStatus.OPEN

    def test_snag_resolve_view(self, client, engineering_setup):
        user = engineering_setup["user"]
        unit = engineering_setup["unit"]
        client.force_login(user)

        snag = UnitSnagItem.objects.create(
            unit=unit,
            room_location="بلكونة المطبخ",
            category=UnitSnagItem.SnagCategory.FLOORING,
            severity=UnitSnagItem.SnagSeverity.MINOR,
            description="بلاطة سيراميك مكسورة",
            status=UnitSnagItem.SnagStatus.OPEN,
            created_by=user
        )

        resolve_url = reverse('real_estate:snag_resolve', kwargs={'pk': snag.pk})
        resp = client.post(resolve_url, data={'resolution_notes': 'تم تغيير البلاطة وتطبيق الترويبة بنجاح'})
        assert resp.status_code == 302

        snag.refresh_from_db()
        assert snag.status == UnitSnagItem.SnagStatus.VERIFIED_BY_ENGINEER
        assert snag.resolution_notes == 'تم تغيير البلاطة وتطبيق الترويبة بنجاح'
        assert snag.verified_at is not None

    def test_offline_snag_sync_api(self, client, engineering_setup):
        user = engineering_setup["user"]
        unit = engineering_setup["unit"]
        client.force_login(user)

        offline_uuid = str(uuid.uuid4())
        payload = {
            'snags': [
                {
                    'client_snag_uuid': offline_uuid,
                    'unit_id': unit.id,
                    'room_location': 'غرفة الأطفال',
                    'category': 'CARPENTRY',
                    'severity': 'MINOR',
                    'description': 'كالون الباب يحتاج ضبط',
                    'status': 'OPEN'
                }
            ]
        }

        api_url = reverse('real_estate:api_snag_sync')
        resp = client.post(api_url, data=json.dumps(payload), content_type='application/json')
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert data['result']['created_count'] == 1

        snag = UnitSnagItem.objects.get(client_snag_uuid=offline_uuid)
        assert snag.room_location == 'غرفة الأطفال'
        assert snag.description == 'كالون الباب يحتاج ضبط'
