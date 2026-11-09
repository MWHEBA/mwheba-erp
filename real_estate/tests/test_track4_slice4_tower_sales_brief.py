# -*- coding: utf-8 -*-
"""
Tests for Track 4 Slice 4: Tower Sales Brief Report & Excel Export
"""
import io
from decimal import Decimal
from datetime import timedelta
import pytest
import openpyxl
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.test import Client

from core.models import SystemModule
from customer.models import Customer
from financial.models import Currency, ChartOfAccounts, AccountType
from financial.services.exchange_rate_service import ExchangeRateService
from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    UnitBooking,
    PropertyContract,
)
from real_estate.services.booking_service import UnitBookingService
from real_estate.services.reporting_service import RealEstateReportingService

User = get_user_model()


@pytest.fixture
def slice4_setup(db):
    user_admin = User.objects.create_superuser(username='sl4_admin', password='password123', email='admin4@test.com')
    user_closer = User.objects.create_user(
        username='sl4_closer',
        password='password123',
        first_name='كريم',
        last_name='المهندس',
        email='closer4@test.com'
    )

    SystemModule.objects.update_or_create(
        code='real_estate',
        defaults={'name_ar': 'القطاع العقاري', 'is_enabled': True}
    )

    asset_type, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "أصول", "category": "asset", "nature": "debit"})
    liability_type, _ = AccountType.objects.get_or_create(code="LIABILITY", defaults={"name": "خصوم", "category": "liability", "nature": "credit"})
    revenue_type, _ = AccountType.objects.get_or_create(code="REVENUE", defaults={"name": "إيرادات", "category": "revenue", "nature": "credit"})
    expense_type, _ = AccountType.objects.get_or_create(code="EXPENSE", defaults={"name": "مصروفات", "category": "expense", "nature": "debit"})

    egp, _ = Currency.objects.get_or_create(
        code='EGP',
        defaults={'name': 'Egyptian Pound', 'symbol': '£', 'is_functional': True, 'decimal_places': 2}
    )
    usd, _ = Currency.objects.get_or_create(
        code='USD',
        defaults={'name': 'US Dollar', 'symbol': '$', 'is_functional': False, 'decimal_places': 2}
    )

    ExchangeRateService.set_rate('USD', 'EGP', Decimal('50.000000'), user=user_admin)

    cash_acc, _ = ChartOfAccounts.objects.get_or_create(
        code='11101',
        defaults={'name': 'الخزينة الرئيسية', 'account_type': asset_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    bank_acc, _ = ChartOfAccounts.objects.get_or_create(
        code='11102',
        defaults={'name': 'البنك التجاري', 'account_type': asset_type, 'currency': egp, 'is_active': True, 'is_leaf': True, 'is_bank_account': True}
    )
    advance_acc, _ = ChartOfAccounts.objects.get_or_create(
        code='21101',
        defaults={'name': 'أمانات جدية حجز العملاء', 'account_type': liability_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    contract_liab, _ = ChartOfAccounts.objects.get_or_create(
        code='21102',
        defaults={'name': 'التزامات عقود العملاء', 'account_type': liability_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    ChartOfAccounts.objects.get_or_create(
        code='21120',
        defaults={'name': 'أوراق الدفع - شيكات صادرة', 'account_type': liability_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    ChartOfAccounts.objects.get_or_create(
        code='21301',
        defaults={'name': 'أوراق الدفع البديل', 'account_type': liability_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    ChartOfAccounts.objects.get_or_create(
        code='11220',
        defaults={'name': 'أوراق القبض', 'account_type': asset_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    ChartOfAccounts.objects.get_or_create(
        code='11190',
        defaults={'name': 'شيكات برسم التحصيل', 'account_type': asset_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    ChartOfAccounts.objects.get_or_create(
        code='54300',
        defaults={'name': 'خسائر فروق عملة محققة', 'account_type': expense_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    ChartOfAccounts.objects.get_or_create(
        code='43100',
        defaults={'name': 'أرباح فروق عملة محققة', 'account_type': revenue_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )
    ChartOfAccounts.objects.get_or_create(
        code='54400',
        defaults={'name': 'أرباح وخسائر تقريب العملات', 'account_type': expense_type, 'currency': egp, 'is_active': True, 'is_leaf': True}
    )

    project = RealEstateProject.objects.create(
        name="Slice 4 Capital Heights",
        code="SL4-PRJ",
        start_date=timezone.localdate(),
        expected_completion_date=timezone.localdate() + timedelta(days=730),
        created_by=user_admin
    )
    block1 = PropertyBlock.objects.create(
        project=project,
        code="BLK-T1",
        name="برج الماسة 1",
        total_floors=10,
        construction_progress_percentage=Decimal("65.50")
    )
    block2 = PropertyBlock.objects.create(
        project=project,
        code="BLK-T2",
        name="برج الزمرد 2",
        total_floors=8,
        construction_progress_percentage=Decimal("40.00")
    )
    floor1 = PropertyFloor.objects.create(block=block1, floor_number=1, name="الطابق الأول")
    floor2 = PropertyFloor.objects.create(block=block1, floor_number=2, name="الطابق الثاني")

    # Units in Block 1
    # U1: Contracted (EGP)
    u1 = PropertyUnit.objects.create(
        project=project, block=block1, floor=floor1, unit_code="T1-U101",
        unit_type=PropertyUnit.UnitType.APARTMENT, net_area=Decimal("100.00"),
        gross_area=Decimal("120.00"), meter_price=Decimal("25000.00"),
        base_price=Decimal("3000000.00"), status=PropertyUnit.UnitStatus.AVAILABLE
    )
    # U2: Reserved (USD foreign currency)
    u2 = PropertyUnit.objects.create(
        project=project, block=block1, floor=floor1, unit_code="T1-U102",
        unit_type=PropertyUnit.UnitType.APARTMENT, net_area=Decimal("110.00"),
        gross_area=Decimal("130.00"), meter_price=Decimal("25000.00"),
        base_price=Decimal("3250000.00"), status=PropertyUnit.UnitStatus.AVAILABLE
    )
    # U3: Available
    u3 = PropertyUnit.objects.create(
        project=project, block=block1, floor=floor2, unit_code="T1-U201",
        unit_type=PropertyUnit.UnitType.APARTMENT, net_area=Decimal("120.00"),
        gross_area=Decimal("140.00"), meter_price=Decimal("25000.00"),
        base_price=Decimal("3500000.00"), status=PropertyUnit.UnitStatus.AVAILABLE
    )
    # U4: Blocked / Landowner
    u4 = PropertyUnit.objects.create(
        project=project, block=block1, floor=floor2, unit_code="T1-U202",
        unit_type=PropertyUnit.UnitType.APARTMENT, net_area=Decimal("130.00"),
        gross_area=Decimal("150.00"), meter_price=Decimal("25000.00"),
        base_price=Decimal("3750000.00"), status=PropertyUnit.UnitStatus.LANDOWNER_ALLOCATED
    )

    cust1 = Customer.objects.create(name="أحمد عزت الشريف", code="CUST-SL4-01", phone="01011112222")
    cust2 = Customer.objects.create(name="مؤسسة النور العالمية", code="CUST-SL4-02", phone="01033334444")

    # U1 Booking then Converted to Contract
    b1 = UnitBookingService.create_booking(
        unit_id=u1.id, customer=cust1, holding_deposit=Decimal("100000.00"),
        expiry_date=timezone.localdate() + timedelta(days=14), user=user_admin
    )
    b1.is_confirmed_audit = True
    b1.is_legacy_pre_audit = True
    b1.visit_specialist = user_closer
    b1.save()
    contract1 = UnitBookingService.convert_booking_to_contract(
        booking_id=b1.id, user=user_admin,
        final_contract_price=Decimal("3000000.00"),
        down_payment=Decimal("300000.00"),
        payment_account=cash_acc
    )
    # Set visit_specialist as closer
    contract1.visit_specialist = user_closer
    contract1.save(update_fields=['visit_specialist'])

    # U2 Active Booking in USD
    b2 = UnitBooking.objects.create(
        booking_number="BKG-SL4-USD-01",
        unit=u2,
        customer=cust2,
        holding_deposit=Decimal("10000.00"),  # 10,000 USD @ 50 = 500,000 EGP
        currency=usd,
        status=UnitBooking.BookingStatus.ACTIVE,
        booking_date=timezone.localdate(),
        expiry_date=timezone.localdate() + timedelta(days=14),
        is_confirmed_audit=True,
        is_legacy_pre_audit=True,
        visit_specialist=user_closer,
        created_by=user_closer
    )
    u2.status = PropertyUnit.UnitStatus.RESERVED
    u2.save(update_fields=['status'])

    client = Client()
    client.force_login(user_admin)

    return {
        'admin': user_admin,
        'closer': user_closer,
        'client': client,
        'project': project,
        'block1': block1,
        'block2': block2,
        'u1': u1,
        'u2': u2,
        'u3': u3,
        'u4': u4,
        'contract1': contract1,
        'booking2': b2,
        'egp': egp,
        'usd': usd,
        'cash_acc': cash_acc,
    }


@pytest.mark.django_db
class TestRealEstateReportingServiceTowerSalesBrief:
    """اختبارات محرك تقارير الموقف التنفيذي ومبيعات الأبراج"""

    def test_tower_sales_brief_filter_by_block(self, slice4_setup):
        s = slice4_setup
        report = RealEstateReportingService.get_tower_sales_brief_report(block_id=s['block1'].id)

        assert report['target_block'] == s['block1']
        assert report['target_project'] == s['project']
        # نسبة الإنجاز الميداني من البرج
        assert report['construction_progress'] == Decimal("65.50")

        # إحصائيات المخزون
        assert report['total_units_count'] == 4
        assert report['total_units_area'] == Decimal("540.00")
        assert report['contracted_count'] == 1
        assert report['reserved_count'] == 1
        assert report['available_count'] == 1
        assert report['blocked_count'] == 1

        # معدلات الاستيعاب
        assert report['absorption_rate'] == Decimal("25.00")
        assert report['reservation_rate'] == Decimal("25.00")
        assert report['available_rate'] == Decimal("25.00")

        # المؤشرات المالية
        assert report['total_contracted_sales_func'] == Decimal("3000000.00")
        assert report['total_down_payments_collected_func'] == Decimal("300000.00")
        # أمانات حجز بالدولار 10,000 USD * 50 = 500,000 EGP
        assert report['total_active_holding_deposits_func'] == Decimal("500000.00")
        # السيولة المحصلة = 300,000 + 500,000 = 800,000 EGP
        assert report['total_collected_liquidity_func'] == Decimal("800000.00")
        # المتبقي للتحصيل = 3,000,000 - 300,000 = 2,700,000 EGP
        assert report['total_remaining_receivables_func'] == Decimal("2700000.00")

        # عزل العملات الأجنبية (USD)
        assert len(report['foreign_currencies']) == 1
        fc = report['foreign_currencies'][0]
        assert fc['currency_code'] == 'USD'
        assert fc['bookings_count'] == 1
        assert fc['foreign_collected_amount'] == Decimal("10000.00")

        # مصفوفة Closer
        assert len(report['closer_matrix']) >= 1
        closer_entry = report['closer_matrix'][0]
        assert closer_entry['name'] == s['closer'].get_full_name()
        assert closer_entry['contracts_count'] == 1
        assert closer_entry['active_bookings_count'] == 1
        assert closer_entry['total_sales_volume'] == Decimal("3000000.00")
        assert closer_entry['contribution_percentage'] == Decimal("100.00")

    def test_tower_sales_brief_filter_by_project(self, slice4_setup):
        s = slice4_setup
        report = RealEstateReportingService.get_tower_sales_brief_report(project_id=s['project'].id)

        assert report['target_block'] is None
        assert report['target_project'] == s['project']
        # متوسط نسبة الإنجاز للبرجين (65.50 + 40.00) / 2 = 52.75%
        assert report['construction_progress'] == Decimal("52.75")
        assert report['total_units_count'] == 4


@pytest.mark.django_db
class TestTowerSalesBriefViewsAndExport:
    """اختبارات شاشات العرض والطباعة وتصدير الإكسيل المعتمد"""

    def test_tower_sales_brief_view_get(self, slice4_setup):
        s = slice4_setup
        url = reverse('real_estate:report_tower_sales_brief') + f"?block={s['block1'].id}"
        response = s['client'].get(url)

        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert "المحور الأول: الموقف الإنشائي" in content
        assert "المحور الثاني: المحفظة المالية" in content
        assert "المحور الثالث: مصفوفة إغلاق صفقات فريق المبيعات" in content
        assert "برج الماسة 1" in content
        assert "65.50%" in content
        assert "T1-U101" in content
        assert "أحمد عزت الشريف" in content

    def test_tower_sales_brief_print_view_get(self, slice4_setup):
        s = slice4_setup
        url = reverse('real_estate:report_tower_sales_brief_print') + f"?block={s['block1'].id}"
        response = s['client'].get(url)

        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert "تقرير الموقف التنفيذي ومصفوفة مبيعات الأبراج" in content
        assert "برج الماسة 1" in content
        assert "T1-U101" in content
        assert "window.print()" in content

    def test_tower_sales_brief_excel_export_openpyxl(self, slice4_setup):
        s = slice4_setup
        url = reverse('real_estate:report_tower_sales_brief_export') + f"?block={s['block1'].id}"
        response = s['client'].get(url)

        assert response.status_code == 200
        assert response['Content-Type'] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert "attachment; filename=\"Tower_Sales_Brief_BLK-T1_" in response['Content-Disposition']

        # قراءة محتوى ملف الإكسيل والتحقق من المعايير الحوكمية
        excel_bytes = io.BytesIO(response.content)
        wb = openpyxl.load_workbook(excel_bytes)
        ws = wb.active

        # التحقق الإلزامي من تفعيل اتجاه RTL
        assert ws.views.sheetView[0].rightToLeft is True

        # التحقق من نصوص الترويسة والأقسام
        sheet_text = []
        for row in ws.iter_rows(values_only=True):
            for cell in row:
                if cell is not None:
                    sheet_text.append(str(cell))
        all_text = " ".join(sheet_text)

        assert "تقرير الموقف التنفيذي ومبيعات الأبراج" in all_text
        assert "برج الماسة 1" in all_text
        assert "أولاً: الملخص التنفيذي وحركة استيعاب المخزون العقاري" in all_text
        assert "ثانياً: الموقف المالي والمحصلات بالعملة الوظيفية" in all_text
        assert "ثالثاً: مصفوفة إغلاق صفقات فريق البيع (Closer Matrix)" in all_text
        assert "رابعاً: سجل جرد وموقف الوحدات التفصيلي" in all_text
        assert "T1-U101" in all_text
        assert "أحمد عزت الشريف" in all_text
