# -*- coding: utf-8 -*-
"""
Tests for Phase 5.3 - Customer Service, Handover Protocols & Warranty Retentions
MWHEBA ERP — Real Estate Handover Protocols, IFRS 15 Revenue & Warranty Retentions
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache

from core.models import SystemModule
from core.middleware.module_control import ModuleAccessMiddleware
from customer.models import Customer
from supplier.models import Supplier
from financial.models import Currency, ChartOfAccounts, AccountType
from sale.models.installments import InstallmentPlan

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    PropertyHandoverReceipt,
    LegalNotice,
    ContractorProgressCertificate,
    UnitSnagItem,
    WarrantyTicket,
)

User = get_user_model()


@pytest.fixture
def service_setup(db):
    cache.delete('enabled_modules_set')
    cache.delete('module_namespace_map')

    mod, _ = SystemModule.objects.get_or_create(code='real_estate', defaults={'name_ar': 'العقارات', 'is_enabled': True})
    mod.is_enabled = True
    mod.save()
    ModuleAccessMiddleware.invalidate_cache()

    user = User.objects.create_superuser(
        username="service_manager",
        email="service_manager@test.com",
        password="password123"
    )

    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True}
    )

    asset_type, _ = AccountType.objects.get_or_create(code='asset', defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'})
    liability_type, _ = AccountType.objects.get_or_create(code='liability', defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'})
    revenue_type, _ = AccountType.objects.get_or_create(code='revenue', defaults={'name': 'إيرادات', 'category': 'revenue', 'nature': 'credit'})
    expense_type, _ = AccountType.objects.get_or_create(code='expense', defaults={'name': 'مصروفات', 'category': 'expense', 'nature': 'debit'})

    # Accounts for IFRS 15 & Handover
    ChartOfAccounts.objects.get_or_create(
        code="21102",
        defaults={"name": "التزامات عقود التطوير العقاري", "account_type": liability_type, "is_active": True}
    )
    ChartOfAccounts.objects.get_or_create(
        code="41101",
        defaults={"name": "إيرادات بيع وتطوير عقاري محققة", "account_type": revenue_type, "is_active": True}
    )
    ChartOfAccounts.objects.get_or_create(
        code="51100",
        defaults={"name": "تكلفة مبيعات التطوير العقاري", "account_type": expense_type, "is_active": True}
    )

    # Accounts for Warranty Retention Debit
    retention_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21310",
        defaults={"name": "تأمينات مقاولي الباطن المحتجزة", "account_type": liability_type, "is_active": True}
    )
    cash_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11110",
        defaults={"name": "خزينة المشروع الرئيسية", "account_type": asset_type, "is_active": True}
    )

    customer = Customer.objects.create(
        code="CUST-SRV-01",
        name="م. طارق السعدني",
        default_currency=currency
    )

    project = RealEstateProject.objects.create(
        code="PRJ-SRV-01",
        name="كمبوند لا فيستا ريزيدنس",
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        total_land_area=Decimal("20000.00"),
        gross_built_area=Decimal("60000.00"),
        created_by=user
    )

    block = PropertyBlock.objects.create(project=project, code="B-SRV-01", name="عمارة النرجس")
    floor = PropertyFloor.objects.create(block=block, floor_number=4, name="الدور الرابع")

    unit = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="LV-U401",
        gross_area=Decimal("200.00"),
        net_area=Decimal("170.00"),
        meter_price=Decimal("45000.00"),
        total_price=Decimal("9000000.00"),
        status=PropertyUnit.UnitStatus.CONTRACTED
    )

    contract = PropertyContract.objects.create(
        contract_number="CTR-LV-2026-401",
        project=project,
        unit=unit,
        customer=customer,
        contract_date=date(2026, 1, 1),
        delivery_date=date(2027, 12, 31),
        final_contract_price=Decimal("9000000.00"),
        down_payment=Decimal("1500000.00"),
        currency=currency,
        created_by=user,
        status=PropertyContract.ContractStatus.ACTIVE
    )

    contractor = Supplier.objects.create(
        name="الشركة الهندسية للإنشاءات التخصصية",
        code="CONTR-SRV-01",
        is_active=True
    )

    # إنشاء مستخلص معتمد للمقاول ليكون له رصيد تأمين أعمال محتجز (21310)
    ContractorProgressCertificate.objects.create(
        certificate_number="CERT-SRV-001",
        project=project,
        contractor=contractor,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        gross_certified_work=Decimal("1000000.00"),
        retention_rate=Decimal("5.00"),
        retention_amount=Decimal("50000.00"),
        net_amount=Decimal("950000.00"),
        currency=currency,
        status=ContractorProgressCertificate.CertificateStatus.APPROVED,
        created_by=user
    )

    return {
        "user": user,
        "customer": customer,
        "project": project,
        "unit": unit,
        "contract": contract,
        "contractor": contractor,
        "cash_acc": cash_acc,
        "retention_acc": retention_acc,
    }


@pytest.mark.django_db
class TestPhase53HandoverProtocols:
    """اختبارات دورة محاضر الاستلام والتسليم الفعلي والحُكمي ومعيار IFRS 15"""

    def test_handover_list_view(self, client, service_setup):
        user = service_setup["user"]
        contract = service_setup["contract"]
        client.force_login(user)

        # Create sample handover receipt
        PropertyHandoverReceipt.objects.create(
            contract=contract,
            unit=contract.unit,
            handover_type=PropertyHandoverReceipt.HandoverType.PHYSICAL,
            status=PropertyHandoverReceipt.HandoverStatus.DRAFT,
            handover_date=date(2027, 11, 1),
            client_signatory_name="م. طارق السعدني",
            created_by=user
        )

        url = reverse('real_estate:handover_list')
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode('utf-8')
        assert "م. طارق السعدني" in content
        assert "LV-U401" in content

    def test_handover_create_view(self, client, service_setup):
        user = service_setup["user"]
        contract = service_setup["contract"]
        client.force_login(user)

        url = reverse('real_estate:handover_create')
        resp_get = client.get(url)
        assert resp_get.status_code == 200

        payload = {
            'contract': contract.id,
            'handover_type': PropertyHandoverReceipt.HandoverType.PHYSICAL,
            'handover_date': '2027-11-01',
            'client_signatory_name': 'م. طارق السعدني',
            'client_signatory_national_id': '29001011234567',
            'power_of_attorney_number': '',
            'electric_meter_reading': '120.50',
            'water_meter_reading': '15.00',
            'gas_meter_reading': '8.20',
            'keys_handed_over_count': '4',
            'access_cards_count': '2',
            'notes': 'تم استلام الوحدة وكافة الملحقات بحالة ممتازة.'
        }
        resp_post = client.post(url, data=payload)
        assert resp_post.status_code == 302

        receipt = PropertyHandoverReceipt.objects.get(contract=contract)
        assert receipt.client_signatory_name == 'م. طارق السعدني'
        assert receipt.electric_meter_reading == Decimal('120.50')
        assert receipt.keys_handed_over_count == 4

    def test_execute_physical_handover_blocked_by_critical_snag(self, client, service_setup):
        """فحص حظر تسليم الوحدة في حال وجود ملاحظات فنية حرجة (CRITICAL_BLOCKER)"""
        user = service_setup["user"]
        contract = service_setup["contract"]
        unit = service_setup["unit"]
        client.force_login(user)

        # إضافة ملاحظة حرجة غير مغلقة بالوحدة
        UnitSnagItem.objects.create(
            unit=unit,
            room_location="حمام الماستر",
            category=UnitSnagItem.SnagCategory.PLUMBING,
            severity=UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER,
            description="تسريب في محبس الدفن الرئيسي",
            status=UnitSnagItem.SnagStatus.OPEN,
            created_by=user
        )

        receipt = PropertyHandoverReceipt.objects.create(
            contract=contract,
            unit=unit,
            handover_type=PropertyHandoverReceipt.HandoverType.PHYSICAL,
            status=PropertyHandoverReceipt.HandoverStatus.DRAFT,
            handover_date=date(2027, 11, 1),
            client_signatory_name="م. طارق السعدني",
            created_by=user
        )

        execute_url = reverse('real_estate:handover_execute', kwargs={'pk': receipt.pk})
        resp = client.post(execute_url)
        assert resp.status_code == 302

        receipt.refresh_from_db()
        # محضر التسليم لا يتم تنفيذه
        assert receipt.status != PropertyHandoverReceipt.HandoverStatus.EXECUTED
        assert unit.status != PropertyUnit.UnitStatus.DELIVERED

    def test_execute_physical_handover_success_with_sha_seal_and_ifrs15(self, client, service_setup):
        """اعتماد التسليم الفعلي بعد التحقق من خلو الوحدة من العيوب وتوليد البصمة المشفرة"""
        user = service_setup["user"]
        contract = service_setup["contract"]
        unit = service_setup["unit"]
        client.force_login(user)

        receipt = PropertyHandoverReceipt.objects.create(
            contract=contract,
            unit=unit,
            handover_type=PropertyHandoverReceipt.HandoverType.PHYSICAL,
            status=PropertyHandoverReceipt.HandoverStatus.DRAFT,
            handover_date=date(2027, 11, 1),
            client_signatory_name="م. طارق السعدني",
            created_by=user
        )

        execute_url = reverse('real_estate:handover_execute', kwargs={'pk': receipt.pk})
        resp = client.post(execute_url)
        assert resp.status_code == 302

        receipt.refresh_from_db()
        unit.refresh_from_db()

        assert receipt.status == PropertyHandoverReceipt.HandoverStatus.EXECUTED
        assert unit.status == PropertyUnit.UnitStatus.DELIVERED
        assert len(receipt.verification_hash) == 64  # SHA-256 seal
        assert receipt.recognized_revenue_amount == Decimal("9000000.00")

    def test_handover_print_view(self, client, service_setup):
        user = service_setup["user"]
        contract = service_setup["contract"]
        client.force_login(user)

        receipt = PropertyHandoverReceipt.objects.create(
            contract=contract,
            unit=contract.unit,
            handover_type=PropertyHandoverReceipt.HandoverType.PHYSICAL,
            status=PropertyHandoverReceipt.HandoverStatus.EXECUTED,
            handover_date=date(2027, 11, 1),
            client_signatory_name="م. طارق السعدني",
            created_by=user
        )

        print_url = reverse('real_estate:handover_print', kwargs={'pk': receipt.pk})
        resp = client.get(print_url)
        assert resp.status_code == 200
        content = resp.content.decode('utf-8')
        assert "محضر استلام وتسليم وحدة عقارية نهائي" in content
        assert "م. طارق السعدني" in content

    def test_handover_update_view(self, client, service_setup):
        user = service_setup["user"]
        contract = service_setup["contract"]
        client.force_login(user)

        receipt = PropertyHandoverReceipt.objects.create(
            contract=contract,
            unit=contract.unit,
            handover_type=PropertyHandoverReceipt.HandoverType.PHYSICAL,
            status=PropertyHandoverReceipt.HandoverStatus.DRAFT,
            handover_date=date(2027, 11, 1),
            client_signatory_name="م. طارق السعدني",
            created_by=user
        )

        update_url = reverse('real_estate:handover_update', kwargs={'pk': receipt.pk})
        resp_get = client.get(update_url)
        assert resp_get.status_code == 200

        payload = {
            'handover_date': '2027-11-05',
            'client_signatory_name': 'م. طارق كمال السعدني',
            'electric_meter_reading': '150.00',
            'water_meter_reading': '20.00',
            'gas_meter_reading': '10.00',
            'keys_handed_over_count': '5',
            'access_cards_count': '3',
            'notes': 'تم تعديل أرقام العدادات بعد المعاينة المشتركة'
        }
        resp_post = client.post(update_url, data=payload)
        assert resp_post.status_code == 302

        receipt.refresh_from_db()
        assert receipt.client_signatory_name == 'م. طارق كمال السعدني'
        assert receipt.electric_meter_reading == Decimal('150.00')
        assert receipt.keys_handed_over_count == 5


@pytest.mark.django_db
class TestPhase53WarrantyTickets:
    """اختبارات دورة تذاكر الضمان وخصم تأمينات المقاولين"""

    def test_warranty_list_view(self, client, service_setup):
        user = service_setup["user"]
        contract = service_setup["contract"]
        unit = service_setup["unit"]
        unit.status = PropertyUnit.UnitStatus.DELIVERED
        unit.save()

        # إنشاء محضر تسليم معتمد لحساب فترة الضمان
        PropertyHandoverReceipt.objects.create(
            contract=contract,
            unit=unit,
            handover_type=PropertyHandoverReceipt.HandoverType.PHYSICAL,
            status=PropertyHandoverReceipt.HandoverStatus.EXECUTED,
            handover_date=date(2026, 5, 1),
            client_signatory_name="م. طارق السعدني",
            created_by=user
        )

        client.force_login(user)

        WarrantyTicket.objects.create(
            unit=unit,
            contract=contract,
            customer=contract.customer,
            category=WarrantyTicket.TicketCategory.FINISHING_PLUMBING,
            priority=WarrantyTicket.TicketPriority.HIGH,
            title="تسريب أسفل خلاط المطبخ",
            description="رشح مياه في كوع الصرف",
            created_by=user
        )

        url = reverse('real_estate:warranty_list')
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode('utf-8')
        assert "تسريب أسفل خلاط المطبخ" in content
        assert "LV-U401" in content

    def test_warranty_create_view_and_guard(self, client, service_setup):
        user = service_setup["user"]
        contract = service_setup["contract"]
        unit = service_setup["unit"]
        client.force_login(user)

        # الوحدة مسلّمة
        unit.status = PropertyUnit.UnitStatus.DELIVERED
        unit.save()

        PropertyHandoverReceipt.objects.create(
            contract=contract,
            unit=unit,
            handover_type=PropertyHandoverReceipt.HandoverType.PHYSICAL,
            status=PropertyHandoverReceipt.HandoverStatus.EXECUTED,
            handover_date=date(2026, 5, 1),
            client_signatory_name="م. طارق السعدني",
            created_by=user
        )

        url = reverse('real_estate:warranty_create')
        payload = {
            'unit': unit.id,
            'category': WarrantyTicket.TicketCategory.FINISHING_ELECTRICAL,
            'priority': WarrantyTicket.TicketPriority.MEDIUM,
            'warranty_type': WarrantyTicket.WarrantyType.FINISHING_ONE_YEAR,
            'title': 'مفتاح إنارة الممر لا يعمل',
            'description': 'عطل في مفتاح الإضاءة الرئيسي'
        }
        resp = client.post(url, data=payload)
        assert resp.status_code == 302

        ticket = WarrantyTicket.objects.get(title='مفتاح إنارة الممر لا يعمل')
        assert ticket.status == WarrantyTicket.TicketStatus.REPORTED
        assert ticket.customer == contract.customer

    def test_warranty_assign_and_resolve_by_contractor(self, client, service_setup):
        """إسناد التذكرة للمقاول ثم قيام المقاول بالإصلاح المجاني (Zero Cost)"""
        user = service_setup["user"]
        contract = service_setup["contract"]
        unit = service_setup["unit"]
        contractor = service_setup["contractor"]
        client.force_login(user)

        unit.status = PropertyUnit.UnitStatus.DELIVERED
        unit.save()

        PropertyHandoverReceipt.objects.create(
            contract=contract,
            unit=unit,
            handover_type=PropertyHandoverReceipt.HandoverType.PHYSICAL,
            status=PropertyHandoverReceipt.HandoverStatus.EXECUTED,
            handover_date=date(2026, 5, 1),
            client_signatory_name="م. طارق السعدني",
            created_by=user
        )

        ticket = WarrantyTicket.objects.create(
            unit=unit,
            contract=contract,
            customer=contract.customer,
            category=WarrantyTicket.TicketCategory.FINISHING_PAINTING,
            title="تقشير دهان الحائط",
            description="تقشير دهانات في صالة الاستقبال",
            created_by=user
        )

        # 1. إسناد للمقاول
        assign_url = reverse('real_estate:warranty_assign', kwargs={'pk': ticket.pk})
        resp_assign = client.post(assign_url, data={
            'responsible_contractor': contractor.id,
            'sla_days': '5',
            'priority': 'HIGH',
            'engineer_notes': 'معاينة الموقع تؤكد وجود عيب تصنيع بالدهان'
        })
        assert resp_assign.status_code == 302

        ticket.refresh_from_db()
        assert ticket.status == WarrantyTicket.TicketStatus.CONTRACTOR_NOTIFIED
        assert ticket.responsible_contractor == contractor
        assert ticket.contractor_sla_deadline is not None

        # 2. إثبات إصلاح المقاول
        resolve_url = reverse('real_estate:warranty_resolve', kwargs={'pk': ticket.pk})
        resp_resolve = client.post(resolve_url, data={
            'resolution_notes': 'قام المقاول بإعادة الدهان وتسليم العميل'
        })
        assert resp_resolve.status_code == 302

        ticket.refresh_from_db()
        assert ticket.status == WarrantyTicket.TicketStatus.RESOLVED_BY_CONTRACTOR
        assert ticket.closure_notes == 'قام المقاول بإعادة الدهان وتسليم العميل'

    def test_warranty_contractor_default_and_debit_retention(self, client, service_setup):
        """إثبات تقاعس المقاول والخصم من تأمين الأعمال (21310) مع العزل المالي"""
        user = service_setup["user"]
        contract = service_setup["contract"]
        unit = service_setup["unit"]
        contractor = service_setup["contractor"]
        cash_acc = service_setup["cash_acc"]
        client.force_login(user)

        unit.status = PropertyUnit.UnitStatus.DELIVERED
        unit.save()

        PropertyHandoverReceipt.objects.create(
            contract=contract,
            unit=unit,
            handover_type=PropertyHandoverReceipt.HandoverType.PHYSICAL,
            status=PropertyHandoverReceipt.HandoverStatus.EXECUTED,
            handover_date=date(2026, 5, 1),
            client_signatory_name="م. طارق السعدني",
            created_by=user
        )

        ticket = WarrantyTicket.objects.create(
            unit=unit,
            contract=contract,
            customer=contract.customer,
            category=WarrantyTicket.TicketCategory.FINISHING_PLUMBING,
            responsible_contractor=contractor,
            title="انسداد ماسورة الصرف الخارجية",
            description="رفض المقاول الحضور للإصلاح",
            created_by=user
        )

        debit_url = reverse('real_estate:warranty_debit_retention', kwargs={'pk': ticket.pk})
        payload = {
            'repair_cost': '8500.00',
            'settlement_account': cash_acc.id,
            'closure_notes': 'تم استدعاء شركة صيانة متخصصة وإصلاح الانسداد وخصم التكلفة من تأمين المقاول'
        }
        resp = client.post(debit_url, data=payload)
        assert resp.status_code == 302

        ticket.refresh_from_db()
        assert ticket.status == WarrantyTicket.TicketStatus.CLOSED_DEBITED
        assert ticket.actual_repair_cost == Decimal('8500.00')
        assert ticket.retention_journal_entry is not None
        assert ticket.settlement_account == cash_acc

    def test_warranty_detail_view(self, client, service_setup):
        user = service_setup["user"]
        contract = service_setup["contract"]
        unit = service_setup["unit"]
        contractor = service_setup["contractor"]
        client.force_login(user)

        unit.status = PropertyUnit.UnitStatus.DELIVERED
        unit.save()

        PropertyHandoverReceipt.objects.create(
            contract=contract,
            unit=unit,
            handover_type=PropertyHandoverReceipt.HandoverType.PHYSICAL,
            status=PropertyHandoverReceipt.HandoverStatus.EXECUTED,
            handover_date=date(2026, 5, 1),
            client_signatory_name="م. طارق السعدني",
            created_by=user
        )

        ticket = WarrantyTicket.objects.create(
            unit=unit,
            contract=contract,
            customer=contract.customer,
            category=WarrantyTicket.TicketCategory.FINISHING_PLUMBING,
            responsible_contractor=contractor,
            title="شرخ في حوض الضيوف",
            description="شرخ سطحي في الخزف",
            created_by=user
        )

        detail_url = reverse('real_estate:warranty_detail', kwargs={'pk': ticket.pk})
        resp = client.get(detail_url)
        assert resp.status_code == 200
        content = resp.content.decode('utf-8')
        assert "شرخ في حوض الضيوف" in content
        assert "50,000.00" in content  # available contractor retention balance displayed in card!
