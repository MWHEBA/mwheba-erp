# -*- coding: utf-8 -*-
import datetime
import uuid
from decimal import Decimal

from django.test import TestCase, Client
from django.utils import timezone
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse

from core.models import SystemModule
from users.models import User
from customer.models import Customer
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    UnitPricingMatrixConfig,
    PropertyContract
)
from real_estate.services.pricing_service import BulkPricingGeneratorService


class RealEstatePhase4PricingMatrixTests(TestCase):
    """
    مجموعة الاختبارات الشاملة للمرحلة 4 (Wave 2 Phase 4):
    1. نموذج إعدادات مصفوفة التسعير (UnitPricingMatrixConfig).
    2. علاوة تدرج الأدوار التصاعدية (Floor Rise Modifier).
    3. علاوات الواجهات والاتجاهات (Orientation Premiums).
    4. علاوات وخصومات الإطلالات والفيو (View Premiums & Discounts).
    5. علاوة الوحدات الناصية (Corner Units).
    6. فروق مستويات التشطيب (Finishing Add-ons).
    7. حسابات الجراج والحدائق الخاصة ووديعة الصيانة القانونية.
    8. حماية الوحدات المباعة والمسلمة تعاقدياً من التعديل العرضي.
    9. خدمة التسعير الجماعي (BulkPricingGeneratorService) في وضعي المعاينة والتنفيذ.
    10. واجهات الويب ونقاط الـ API وأمر الإدارة (Management Command).
    """

    def setUp(self):
        cache.clear()
        SystemModule.objects.update_or_create(
            code='real_estate',
            defaults={'name_ar': 'القطاع العقاري', 'name_en': 'Real Estate', 'is_enabled': True}
        )

        self.user = User.objects.create_superuser(
            username='pricing_admin_p4',
            email='pricing_admin@example.com',
            password='password123'
        )
        self.client = Client()
        self.client.force_login(self.user)

        self.asset_type, _ = AccountType.objects.get_or_create(
            code='asset',
            defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
        )
        self.escrow_acc, _ = ChartOfAccounts.objects.get_or_create(
            code='11160099',
            defaults={'name': 'حساب ضمان مشروع التسعير', 'account_type': self.asset_type, 'is_active': True, 'is_leaf': True}
        )
        self.egp, _ = Currency.objects.get_or_create(
            code='EGP',
            defaults={'name': 'جنيه مصري', 'symbol': 'ج.م', 'is_functional': True}
        )

        # إنشاء المشروع والمبنى والطوابق
        self.project = RealEstateProject.objects.create(
            code='PRJ-P4-MATRIX',
            name='برج النخبة 4 للتسعير',
            escrow_account=self.escrow_acc,
            start_date=timezone.localdate(),
            expected_completion_date=timezone.localdate() + datetime.timedelta(days=730),
            created_by=self.user
        )
        self.block = PropertyBlock.objects.create(
            project=self.project,
            code='BLK-A',
            name='المبنى أ'
        )

        self.floor1 = PropertyFloor.objects.create(block=self.block, floor_number=1, name='الدور الأول')
        self.floor2 = PropertyFloor.objects.create(block=self.block, floor_number=2, name='الدور الثاني')
        self.floor5 = PropertyFloor.objects.create(block=self.block, floor_number=5, name='الدور الخامس')

        # إنشاء وحدات بنماذج مختلفة
        # وحدة 1: دور أول، بحري، شارع رئيسي، نصف تشطيب
        self.unit1 = PropertyUnit.objects.create(
            project=self.project,
            block=self.block,
            floor=self.floor1,
            unit_code='U101',
            gross_area=Decimal('100.00'),
            net_area=Decimal('80.00'),
            meter_price=Decimal('20000.00'),
            orientation=PropertyUnit.Orientation.NORTH,
            view_type=PropertyUnit.ViewType.MAIN_STREET,
            is_corner=False,
            finishing_type=PropertyUnit.FinishingType.SEMI_FINISHED
        )

        # وحدة 2: دور ثاني، بحري، ناصية، حديقة خاصة، جراج 1
        self.unit2 = PropertyUnit.objects.create(
            project=self.project,
            block=self.block,
            floor=self.floor2,
            unit_code='U201',
            gross_area=Decimal('120.00'),
            net_area=Decimal('100.00'),
            meter_price=Decimal('20000.00'),
            orientation=PropertyUnit.Orientation.NORTH,
            view_type=PropertyUnit.ViewType.GARDEN_PARK,
            is_corner=True,
            garden_area=Decimal('50.00'),
            parking_slots_count=1,
            finishing_type=PropertyUnit.FinishingType.SEMI_FINISHED
        )

        # وحدة 3: دور خامس، قبلي، منور داخلي (خصم)، تشطيب كامل
        self.unit3 = PropertyUnit.objects.create(
            project=self.project,
            block=self.block,
            floor=self.floor5,
            unit_code='U501',
            gross_area=Decimal('150.00'),
            net_area=Decimal('120.00'),
            meter_price=Decimal('20000.00'),
            orientation=PropertyUnit.Orientation.SOUTH,
            view_type=PropertyUnit.ViewType.INTERNAL_COURT,
            is_corner=False,
            finishing_type=PropertyUnit.FinishingType.FULLY_FINISHED
        )

        # إعداد مصفوفة التسعير المعتمدة
        self.config = UnitPricingMatrixConfig.objects.create(
            project=self.project,
            name='لائحة تسعير البرج 2026',
            is_active=True,
            base_meter_price=Decimal('20000.00'),
            base_floor_number=1,
            floor_rise_rate=Decimal('2.00'),           # 2% لكل دور أعلى الأول
            north_orientation_premium=Decimal('5.00'),  # 5% بحري
            south_orientation_premium=Decimal('0.00'),  # 0% قبلي
            main_street_view_premium=Decimal('6.00'),   # 6% شارع رئيسي
            garden_park_view_premium=Decimal('5.00'),   # 5% حديقة
            internal_court_discount=Decimal('5.00'),    # 5% خصم منور
            corner_unit_premium=Decimal('4.00'),        # 4% ناصية
            garden_meter_price=Decimal('5000.00'),      # 5,000 ج.م لمتر الحديقة
            parking_slot_price=Decimal('150000.00'),    # 150,000 ج.م للباكية
            fully_finished_meter_addon=Decimal('4000.00'), # 4,000 ج.م للمتر
            maintenance_deposit_rate=Decimal('8.00'),   # 8% وديعة صيانة
            created_by=self.user
        )

    def test_pricing_matrix_config_creation_and_single_active_constraint(self):
        """
        التحقق من إنشاء إعدادات مصفوفة التسعير وضمان وجود لائحة نشطة واحدة للمشروع
        """
        self.assertTrue(self.config.is_active)
        self.assertEqual(self.config.base_meter_price, Decimal('20000.00'))

        # إنشاء لائحة ثانية وتفعيلها -> يجب أن تلغي تفعيل اللائحة الأولى تلقائياً
        config2 = UnitPricingMatrixConfig.objects.create(
            project=self.project,
            name='لائحة جديدة 2027',
            is_active=True,
            base_meter_price=Decimal('25000.00'),
            created_by=self.user
        )

        self.config.refresh_from_db()
        self.assertFalse(self.config.is_active)
        self.assertTrue(config2.is_active)

    def test_calculate_unit_1_base_floor_premiums(self):
        """
        اختبار احتساب سعر الوحدة 1:
        الدور الأول (0% فرق دور) + بحري (5%) + شارع رئيسي (6%) = 11% إجمالي علاوة
        سعر المتر = 20,000 * 1.11 = 22,200 ج.م
        سعر الوحدة = 100 م² * 22,200 = 2,220,000 ج.م
        وديعة الصيانة (8%) = 177,600 ج.م
        """
        calc = BulkPricingGeneratorService.calculate_unit_price(self.unit1, self.config)

        self.assertEqual(Decimal(calc['floor_rise_rate']), Decimal('0.00'))
        self.assertEqual(Decimal(calc['orientation_rate']), Decimal('5.00'))
        self.assertEqual(Decimal(calc['view_rate']), Decimal('6.00'))
        self.assertEqual(Decimal(calc['corner_rate']), Decimal('0.00'))
        self.assertEqual(Decimal(calc['total_premium_rate']), Decimal('11.00'))

        expected_meter_price = Decimal('22200.00')
        self.assertEqual(calc['final_meter_price'], expected_meter_price)

        expected_total_price = Decimal('2220000.00')
        self.assertEqual(calc['total_unit_price'], expected_total_price)

        expected_maintenance = (expected_total_price * Decimal('0.08')).quantize(Decimal('0.01'))
        self.assertEqual(calc['maintenance_deposit'], expected_maintenance)

    def test_calculate_unit_2_floor_rise_corner_garden_parking(self):
        """
        اختبار احتساب سعر الوحدة 2:
        الدور الثاني (2% فرق دور) + بحري (5%) + فيو حديقة (5%) + ناصية (4%) = 16% علاوة
        سعر المتر = 20,000 * 1.16 = 23,200 ج.م
        سعر المباني = 120 م² * 23,200 = 2,784,000 ج.م
        سعر الحديقة = 50 م² * 5,000 = 250,000 ج.م
        سعر الجراج = 1 باكية * 150,000 = 150,000 ج.م
        إجمالي سعر الوحدة = 2,784,000 + 250,000 + 150,000 = 3,184,000 ج.م
        """
        calc = BulkPricingGeneratorService.calculate_unit_price(self.unit2, self.config)

        self.assertEqual(Decimal(calc['floor_rise_rate']), Decimal('2.00'))
        self.assertEqual(Decimal(calc['orientation_rate']), Decimal('5.00'))
        self.assertEqual(Decimal(calc['view_rate']), Decimal('5.00'))
        self.assertEqual(Decimal(calc['corner_rate']), Decimal('4.00'))
        self.assertEqual(Decimal(calc['total_premium_rate']), Decimal('16.00'))

        self.assertEqual(calc['final_meter_price'], Decimal('23200.00'))
        self.assertEqual(calc['base_unit_price'], Decimal('2784000.00'))
        self.assertEqual(calc['garden_price'], Decimal('250000.00'))
        self.assertEqual(calc['parking_price'], Decimal('150000.00'))
        self.assertEqual(calc['total_unit_price'], Decimal('3184000.00'))

    def test_calculate_unit_3_floor_rise_internal_court_discount_and_finishing(self):
        """
        اختبار احتساب سعر الوحدة 3:
        الدور الخامس (فرق 4 أدوار * 2% = 8%) + قبلي (0%) + منور داخلي (-5% خصم) = 3% علاوة
        سعر المتر قبل التشطيب = 20,000 * 1.03 = 20,600 ج.م
        إضافة التشطيب الكامل = +4,000 ج.م/م²
        سعر المتر النهائي = 24,600 ج.م
        سعر الوحدة = 150 م² * 24,600 = 3,690,000 ج.م
        """
        calc = BulkPricingGeneratorService.calculate_unit_price(self.unit3, self.config)

        self.assertEqual(Decimal(calc['floor_rise_rate']), Decimal('8.00'))
        self.assertEqual(Decimal(calc['view_rate']), Decimal('-5.00'))
        self.assertEqual(Decimal(calc['total_premium_rate']), Decimal('3.00'))

        self.assertEqual(calc['final_meter_price'], Decimal('24600.00'))
        self.assertEqual(calc['total_unit_price'], Decimal('3690000.00'))

    def test_apply_pricing_to_unit_safety_guard_blocks_contracted_units(self):
        """
        اختبار الحماية الصارمة: منع إعادة تسعير الوحدات المباعة أو المسلمة تعاقدياً
        """
        # تحويل الوحدة لحالة CONTRACTED
        self.unit1.status = PropertyUnit.UnitStatus.CONTRACTED
        self.unit1.save()

        with self.assertRaises(ValidationError) as ctx:
            BulkPricingGeneratorService.apply_pricing_to_unit(self.unit1, self.config)

        self.assertIn("لا يمكن إعادة تسعير الوحدة", str(ctx.exception))

    def test_bulk_pricing_generator_dry_run_and_execution(self):
        """
        اختبار التسعير الجماعي:
        1. وضع Dry Run لا يغير البيانات في قاعدة البيانات.
        2. وضع التنفيذ يغير الأسعار ويستثني الوحدات المباعة.
        """
        # جعل وحدة 3 مباعة
        self.unit3.status = PropertyUnit.UnitStatus.CONTRACTED
        self.unit3.save()

        # 1. تشغيل تجريبي (Dry Run)
        report_dry = BulkPricingGeneratorService.bulk_generate_pricing(
            project=self.project,
            dry_run=True,
            user=self.user
        )

        self.assertTrue(report_dry['dry_run'])
        self.assertEqual(report_dry['total_units_evaluated'], 3)
        self.assertEqual(report_dry['total_units_updated'], 2)
        self.assertEqual(report_dry['skipped_contracted_units'], 1)

        # التأكد من عدم تعديل الأسعار في قاعدة البيانات
        self.unit1.refresh_from_db()
        self.assertEqual(self.unit1.meter_price, Decimal('20000.00'))

        # 2. تشغيل فعلي (Execution)
        report_exec = BulkPricingGeneratorService.bulk_generate_pricing(
            project=self.project,
            dry_run=False,
            user=self.user
        )

        self.assertFalse(report_exec['dry_run'])
        self.assertEqual(report_exec['total_units_updated'], 2)

        # التحقق من حفظ الأسعار في قاعدة البيانات
        self.unit1.refresh_from_db()
        self.unit2.refresh_from_db()
        self.unit3.refresh_from_db()

        self.assertEqual(self.unit1.meter_price, Decimal('22200.00'))
        self.assertEqual(self.unit1.total_price, Decimal('2220000.00'))
        self.assertEqual(self.unit2.total_price, Decimal('3184000.00'))
        # الوحدة 3 المباعة لم تتغير
        self.assertEqual(self.unit3.meter_price, Decimal('20000.00'))

    def test_views_project_pricing_and_apis(self):
        """
        اختبار واجهات الويب ونقاط الـ AJAX API الخاصة بمصفوفة التسعير:
        1. شاشة مصفوفة التسعير الرئيسية (HTTP 200).
        2. حفظ إعدادات جديدة عبر POST.
        3. معاينة الأسعار عبر API Preview.
        4. تطبيق التسعير الجماعي عبر API Apply.
        """
        url_page = reverse('real_estate:project_pricing', kwargs={'project_id': self.project.id})
        res_page = self.client.get(url_page)
        self.assertEqual(res_page.status_code, 200)
        self.assertContains(res_page, "مصفوفة التسعير الآلي للوحدات")

        # حفظ إعدادات
        post_data = {
            'name': 'لائحة محدثة عبر الواجهة',
            'base_meter_price': '22000.00',
            'base_floor_number': '1',
            'floor_rise_rate': '2.00',
            'north_orientation_premium': '5.00',
            'main_street_view_premium': '6.00',
            'garden_park_view_premium': '5.00',
            'pool_water_view_premium': '7.00',
            'internal_court_discount': '5.00',
            'corner_unit_premium': '4.00',
            'parking_slot_price': '150000.00',
            'fully_finished_meter_addon': '4000.00',
            'maintenance_deposit_rate': '8.00'
        }
        res_post = self.client.post(url_page, post_data)
        self.assertEqual(res_post.status_code, 200)
        json_post = res_post.json()
        self.assertTrue(json_post['success'])

        # API Preview
        url_preview = reverse('real_estate:api_preview_pricing', kwargs={'project_id': self.project.id})
        res_preview = self.client.get(url_preview)
        self.assertEqual(res_preview.status_code, 200)
        json_preview = res_preview.json()
        self.assertTrue(json_preview['success'])
        self.assertIn('report', json_preview)

        # API Apply
        url_apply = reverse('real_estate:api_apply_bulk_pricing', kwargs={'project_id': self.project.id})
        res_apply = self.client.post(url_apply)
        self.assertEqual(res_apply.status_code, 200)
        json_apply = res_apply.json()
        self.assertTrue(json_apply['success'])

    def test_management_command_apply_unit_pricing_matrix(self):
        """
        اختبار أمر الإدارة من سطر الأوامر (apply_unit_pricing_matrix)
        """
        # تشغيل تجريبي عبر Command
        call_command('apply_unit_pricing_matrix', project_code=self.project.code, dry_run=True)

        # تشغيل فعلي عبر Command
        call_command('apply_unit_pricing_matrix', project_code=self.project.code)

        self.unit1.refresh_from_db()
        self.assertEqual(self.unit1.meter_price, Decimal('22200.00'))
