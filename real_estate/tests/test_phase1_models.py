# -*- coding: utf-8 -*-
import datetime
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    ContractCoOwner,
)
from customer.models import Customer
from financial.models import ChartOfAccounts, AccountType, AccountingPeriod, Currency
from sale.models.installments import InstallmentPlan

User = get_user_model()


class RealEstatePhase1ModelTests(TestCase):
    """
    اختبارات معمارية شاملة لنماذج المرحلة الأولى (Wave 1 - Phase 1 Foundation)
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='real_estate_admin',
            password='AdminPassword123!',
            is_superuser=True
        )
        AccountingPeriod.objects.get_or_create(
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 12, 31),
            defaults={'name': 'فترة 2026', 'status': 'open'}
        )
        self.acc_type, _ = AccountType.objects.get_or_create(
            code='ASSET',
            defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
        )
        self.receivable_acc_1, _ = ChartOfAccounts.objects.get_or_create(
            code='10301',
            defaults={'name': 'عملاء عقارات 1', 'account_type': self.acc_type, 'is_active': True}
        )
        self.receivable_acc_2, _ = ChartOfAccounts.objects.get_or_create(
            code='10302',
            defaults={'name': 'عملاء عقارات 2', 'account_type': self.acc_type, 'is_active': True}
        )
        self.receivable_acc_3, _ = ChartOfAccounts.objects.get_or_create(
            code='10303',
            defaults={'name': 'عملاء عقارات 3', 'account_type': self.acc_type, 'is_active': True}
        )
        self.escrow_acc, _ = ChartOfAccounts.objects.get_or_create(
            code='10205',
            defaults={'name': 'حساب الضمان البنكي للمشروع', 'account_type': self.acc_type, 'is_active': True}
        )
        self.egp, _ = Currency.objects.get_or_create(
            code='EGP',
            defaults={'name': 'جنيه مصري', 'is_functional': True}
        )

        self.customer = Customer.objects.create(
            code='CUST-RE-01',
            name='أحمد المنشاوي',
            phone='01099887766',
            financial_account=self.receivable_acc_1
        )
        self.co_owner_customer = Customer.objects.create(
            code='CUST-RE-02',
            name='فاطمة الزهراء',
            phone='01055443322',
            financial_account=self.receivable_acc_2
        )

        # إنشاء مشروع عقاري نموذجي
        self.project = RealEstateProject.objects.create(
            code='PRJ-NEW-CAIRO',
            name='كمبوند جاردينيا هايتس',
            project_type=RealEstateProject.ProjectType.RESIDENTIAL,
            status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
            escrow_account=self.escrow_acc,
            total_land_area=Decimal('50000.00'),
            gross_built_area=Decimal('120000.00'),
            start_date=datetime.date(2026, 1, 1),
            expected_completion_date=datetime.date(2028, 12, 31),
            created_by=self.user,
        )

        # إنشاء بلوك وطابق
        self.block = PropertyBlock.objects.create(
            project=self.project,
            code='BLK-A',
            name='عمارة رقم 101',
            total_floors=5,
        )
        self.floor = PropertyFloor.objects.create(
            block=self.block,
            floor_number=2,
            floor_type=PropertyFloor.FloorType.TYPICAL,
        )

    def test_project_and_topology_creation_and_uniqueness(self):
        """
        التحقق من إنشاء المشروع والعمارة والطابق وإنفاذ القيود الفريدة
        """
        self.assertIn("PRJ-NEW-CAIRO", str(self.project))
        self.assertIn("عمارة رقم 101", str(self.block))
        self.assertIn("متكرر (2)", str(self.floor))

        # تكرار كود البلوك لنفس المشروع يجب أن يفشل
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                PropertyBlock.objects.create(
                    project=self.project,
                    code='BLK-A',
                    name='عمارة مكررة',
                )

        # تكرار رقم الطابق لنفس البلوك يجب أن يفشل
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                PropertyFloor.objects.create(
                    block=self.block,
                    floor_number=2,
                    floor_type=PropertyFloor.FloorType.TYPICAL,
                )

    def test_property_unit_creation_and_auto_pricing(self):
        """
        التحقق من إنشاء الوحدة العقارية واحتساب السعر الإجمالي ونسبة التحميل تلقائياً
        """
        unit = PropertyUnit.objects.create(
            project=self.project,
            block=self.block,
            floor=self.floor,
            unit_code='U-A-201',
            unit_type=PropertyUnit.UnitType.APARTMENT,
            net_area=Decimal('160.00'),
            gross_area=Decimal('200.00'),
            meter_price=Decimal('25000.00'),
            base_price=Decimal('0.00'),
            total_price=Decimal('0.00'),
        )

        # 200 * 25000 = 5,000,000
        self.assertEqual(unit.base_price, Decimal('5000000.00'))
        self.assertEqual(unit.total_price, Decimal('5000000.00'))
        # ((200 - 160) / 160) * 100 = 25.00%
        self.assertEqual(unit.loading_ratio, Decimal('25.00'))
        self.assertEqual(unit.status, PropertyUnit.UnitStatus.AVAILABLE)

    def test_unit_gross_area_gte_net_area_constraint(self):
        """
        التحقق من قيد المساحة: المساحة البيعية الإجمالية لا تقل عن الصافية
        """
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                PropertyUnit.objects.create(
                    project=self.project,
                    block=self.block,
                    floor=self.floor,
                    unit_code='U-A-INVALID-AREA',
                    unit_type=PropertyUnit.UnitType.APARTMENT,
                    net_area=Decimal('200.00'),
                    gross_area=Decimal('150.00'),  # خطأ: الإجمالي أقل من الصافي
                    meter_price=Decimal('25000.00'),
                    base_price=Decimal('3750000.00'),
                    total_price=Decimal('3750000.00'),
                )

    def test_property_contract_creation_and_unit_status_lifecycle(self):
        """
        التحقق من دورة حياة العقد وتحديث حالة الوحدة العقارية تلقائياً
        """
        unit = PropertyUnit.objects.create(
            project=self.project,
            block=self.block,
            floor=self.floor,
            unit_code='U-A-202',
            unit_type=PropertyUnit.UnitType.APARTMENT,
            net_area=Decimal('150.00'),
            gross_area=Decimal('180.00'),
            meter_price=Decimal('20000.00'),
            base_price=Decimal('3600000.00'),
            total_price=Decimal('3600000.00'),
        )

        contract = PropertyContract.objects.create(
            contract_number='CNT-2026-001',
            project=self.project,
            unit=unit,
            customer=self.customer,
            status=PropertyContract.ContractStatus.DRAFT,
            contract_date=datetime.date(2026, 1, 15),
            delivery_date=datetime.date(2028, 6, 30),
            final_contract_price=Decimal('3600000.00'),
            down_payment=Decimal('360000.00'),
            currency=self.egp,
            created_by=self.user,
        )

        self.assertFalse(contract.installments_settled)
        # الوحدة تظل AVAILABLE أثناء مرحلة المسودة
        unit.refresh_from_db()
        self.assertEqual(unit.status, PropertyUnit.UnitStatus.AVAILABLE)

        # تفعيل العقد ينقل الوحدة إلى CONTRACTED ويزيد status_version لضبط التزامن
        old_version = unit.status_version
        contract.status = PropertyContract.ContractStatus.ACTIVE
        contract.save()

        unit.refresh_from_db()
        self.assertEqual(unit.status, PropertyUnit.UnitStatus.CONTRACTED)
        self.assertGreater(unit.status_version, old_version)

    def test_contract_installment_plan_binding_and_completion(self):
        """
        التحقق من ربط خطة أقساط مستقلة بالعقد وإغلاق العقد عند اكتمال السداد
        """
        unit = PropertyUnit.objects.create(
            project=self.project,
            block=self.block,
            floor=self.floor,
            unit_code='U-A-203',
            unit_type=PropertyUnit.UnitType.APARTMENT,
            net_area=Decimal('100.00'),
            gross_area=Decimal('120.00'),
            meter_price=Decimal('20000.00'),
            base_price=Decimal('2400000.00'),
            total_price=Decimal('2400000.00'),
        )

        plan = InstallmentPlan.objects.create(
            sale=None,
            customer=self.customer,
            total_principal=Decimal('2000000.00'),
            total_markup=Decimal('400000.00'),
            total_amount=Decimal('2400000.00'),
            number_of_installments=24,
            start_date=datetime.date(2026, 2, 1),
            status=InstallmentPlan.PlanStatus.DRAFT,
            created_by=self.user,
        )

        contract = PropertyContract.objects.create(
            contract_number='CNT-2026-002',
            project=self.project,
            unit=unit,
            customer=self.customer,
            installment_plan=plan,
            status=PropertyContract.ContractStatus.ACTIVE,
            contract_date=datetime.date(2026, 1, 15),
            delivery_date=datetime.date(2028, 6, 30),
            final_contract_price=Decimal('2400000.00'),
            down_payment=Decimal('200000.00'),
            currency=self.egp,
            created_by=self.user,
        )

        # التحقق من أن الخطة ارتبطت بالعقد
        plan.refresh_from_db()
        self.assertEqual(plan.property_contract, contract)

        # محاكاة إشعار سداد كامل الأقساط
        contract.on_installments_completed()
        contract.refresh_from_db()
        self.assertTrue(contract.installments_settled)

    def test_binding_plan_with_different_customer_fails(self):
        """
        التحقق من رفض ربط خطة أقساط تخص عميلاً آخر بالعقد
        """
        unit = PropertyUnit.objects.create(
            project=self.project,
            block=self.block,
            floor=self.floor,
            unit_code='U-A-204',
            unit_type=PropertyUnit.UnitType.APARTMENT,
            net_area=Decimal('100.00'),
            gross_area=Decimal('120.00'),
            meter_price=Decimal('20000.00'),
            base_price=Decimal('2400000.00'),
            total_price=Decimal('2400000.00'),
        )

        other_customer = Customer.objects.create(
            code='CUST-RE-03',
            name='عميل آخر',
            phone='01012345678',
            financial_account=self.receivable_acc_3
        )

        foreign_plan = InstallmentPlan.objects.create(
            sale=None,
            customer=other_customer,
            total_principal=Decimal('1000000.00'),
            total_markup=Decimal('0.00'),
            total_amount=Decimal('1000000.00'),
            number_of_installments=12,
            start_date=datetime.date(2026, 2, 1),
            status=InstallmentPlan.PlanStatus.DRAFT,
            created_by=self.user,
        )

        contract = PropertyContract(
            contract_number='CNT-2026-DIFF-CUST',
            project=self.project,
            unit=unit,
            customer=self.customer,
            installment_plan=foreign_plan,
            status=PropertyContract.ContractStatus.DRAFT,
            contract_date=datetime.date(2026, 1, 15),
            delivery_date=datetime.date(2028, 6, 30),
            final_contract_price=Decimal('2400000.00'),
            down_payment=Decimal('200000.00'),
            currency=self.egp,
            created_by=self.user,
        )

        with self.assertRaises(ValidationError) as cm:
            contract.clean()
        self.assertIn("خطة التقسيط تنتمي لعميل مختلف", str(cm.exception))

    def test_co_owners_management_and_guarantee(self):
        """
        التحقق من إضافة الشركاء في الملكية ونسب التوزيع وحظر التكرار
        """
        unit = PropertyUnit.objects.create(
            project=self.project,
            block=self.block,
            floor=self.floor,
            unit_code='U-A-COOWNER',
            unit_type=PropertyUnit.UnitType.APARTMENT,
            net_area=Decimal('100.00'),
            gross_area=Decimal('120.00'),
            meter_price=Decimal('20000.00'),
            base_price=Decimal('2400000.00'),
            total_price=Decimal('2400000.00'),
        )

        contract = PropertyContract.objects.create(
            contract_number='CNT-COOWN-001',
            project=self.project,
            unit=unit,
            customer=self.customer,
            status=PropertyContract.ContractStatus.ACTIVE,
            contract_date=datetime.date(2026, 1, 15),
            delivery_date=datetime.date(2028, 6, 30),
            final_contract_price=Decimal('2400000.00'),
            down_payment=Decimal('200000.00'),
            currency=self.egp,
            created_by=self.user,
        )

        co_owner = ContractCoOwner.objects.create(
            contract=contract,
            co_owner=self.co_owner_customer,
            share_percentage=Decimal('50.00'),
            is_joint_and_several_guarantor=True,
        )

        self.assertEqual(co_owner.share_percentage, Decimal('50.00'))
        self.assertTrue(co_owner.is_joint_and_several_guarantor)
        self.assertIn("فاطمة الزهراء", str(co_owner))

        # تكرار نفس الشريك على نفس العقد يجب أن يمنعه قيد قاعدة البيانات
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                ContractCoOwner.objects.create(
                    contract=contract,
                    co_owner=self.co_owner_customer,
                    share_percentage=Decimal('25.00'),
                )
