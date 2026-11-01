# -*- coding: utf-8 -*-
import datetime
import json
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.core.cache import cache

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    UnitBooking,
    PropertyContract,
)
from real_estate.services.booking_service import (
    UnitBookingService,
    ConcurrencyBookingConflictError,
    BookingValidationError,
)
from real_estate.services.booking_sweep_service import UnitBookingSweepService
from customer.models import Customer
from financial.models import ChartOfAccounts, AccountType, AccountingPeriod, Currency
from core.models import SystemModule

User = get_user_model()


class RealEstatePhase2ConcurrencyAndMatrixTests(TestCase):
    """
    اختبارات معمارية شاملة للمرحلة الثانية (Wave 1 - Phase 2 Concurrency, Booking Engine & Visual Matrix)
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='sales_agent_1',
            password='AgentPassword123!',
            is_superuser=True
        )
        self.client = Client()
        self.client.force_login(self.user)

        # تفعيل الموديول في قاعدة بيانات الاختبار وإخلاء الكاش لضمان مرور الميدلوير
        SystemModule.objects.update_or_create(
            code='real_estate',
            defaults={
                'name_ar': 'إدارة التطوير العقاري',
                'name_en': 'Real Estate Development',
                'url_namespace': 'real_estate',
                'is_enabled': True
            }
        )
        cache.clear()

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
        self.escrow_acc, _ = ChartOfAccounts.objects.get_or_create(
            code='10205',
            defaults={'name': 'حساب الضمان البنكي', 'account_type': self.acc_type, 'is_active': True}
        )
        self.egp, _ = Currency.objects.get_or_create(
            code='EGP',
            defaults={'name': 'جنيه مصري', 'is_functional': True}
        )

        self.customer1 = Customer.objects.create(
            code='CUST-RE-101',
            name='خالد محيي الدين',
            phone='01122334455',
            financial_account=self.receivable_acc_1
        )
        self.customer2 = Customer.objects.create(
            code='CUST-RE-102',
            name='محمود الجندي',
            phone='01199887766',
            financial_account=self.receivable_acc_2
        )

        self.project = RealEstateProject.objects.create(
            code='PRJ-HORIZON',
            name='أبراج الأفق الجديدة',
            project_type=RealEstateProject.ProjectType.RESIDENTIAL,
            status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
            escrow_account=self.escrow_acc,
            total_land_area=Decimal('25000.00'),
            gross_built_area=Decimal('80000.00'),
            start_date=datetime.date(2026, 1, 1),
            expected_completion_date=datetime.date(2028, 12, 31),
            created_by=self.user,
        )

        self.block = PropertyBlock.objects.create(
            project=self.project,
            code='TWR-1',
            name='برج النيل 1',
            total_floors=10,
        )
        self.floor = PropertyFloor.objects.create(
            block=self.block,
            floor_number=3,
            floor_type=PropertyFloor.FloorType.TYPICAL,
        )

        self.unit = PropertyUnit.objects.create(
            project=self.project,
            block=self.block,
            floor=self.floor,
            unit_code='U-T1-301',
            unit_type=PropertyUnit.UnitType.APARTMENT,
            net_area=Decimal('120.00'),
            gross_area=Decimal('150.00'),
            meter_price=Decimal('30000.00'),
            base_price=Decimal('4500000.00'),
            total_price=Decimal('4500000.00'),
            status=PropertyUnit.UnitStatus.AVAILABLE,
        )

    def test_atomic_booking_concurrency_lock_and_race_condition(self):
        """
        التحقق من القفل التزامني الذري:
        - المحاولة الأولى تنجح وتغير حالة الوحدة إلى RESERVED.
        - أي محاولة ثانية متزامنة لحجز نفس الوحدة تفشل وترفع ConcurrencyBookingConflictError.
        """
        old_version = self.unit.status_version
        expiry = timezone.localdate() + datetime.timedelta(days=7)

        # الحجز الأول بنجاح
        booking1 = UnitBookingService.create_booking(
            unit_id=self.unit.id,
            customer=self.customer1,
            holding_deposit=Decimal('100000.00'),
            expiry_date=expiry,
            notes='حجز أول',
            user=self.user,
        )

        self.assertIsNotNone(booking1)
        self.assertEqual(booking1.status, UnitBooking.BookingStatus.ACTIVE)

        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, PropertyUnit.UnitStatus.RESERVED)
        self.assertEqual(self.unit.current_booking, booking1)
        self.assertGreater(self.unit.status_version, old_version)

        # المحاولة الثانية لحجز نفس الوحدة لنفس أو لعميل آخر يجب أن تفشل فوراً بتعارض تزامن
        with self.assertRaises(ConcurrencyBookingConflictError) as cm:
            UnitBookingService.create_booking(
                unit_id=self.unit.id,
                customer=self.customer2,
                holding_deposit=Decimal('100000.00'),
                expiry_date=expiry + datetime.timedelta(days=2),
                notes='محاولة حجز متزامنة على وحدة محجوزة',
                user=self.user,
            )
        self.assertIn("غير متاحة حالياً", str(cm.exception))

    def test_convert_booking_to_contract_lifecycle(self):
        """
        التحقق من تحويل الحجز الساري إلى تعاقد بيع نهائي (SPA)
        وتحديث حالة الحجز إلى CONVERTED_TO_CONTRACT والوحدة إلى CONTRACTED
        """
        expiry = timezone.localdate() + datetime.timedelta(days=7)
        booking = UnitBookingService.create_booking(
            unit_id=self.unit.id,
            customer=self.customer1,
            holding_deposit=Decimal('100000.00'),
            expiry_date=expiry,
            user=self.user,
        )

        contract = UnitBookingService.convert_booking_to_contract(
            booking_id=booking.id,
            final_contract_price=Decimal('4500000.00'),
            down_payment=Decimal('450000.00'),
            contract_date=timezone.localdate(),
            delivery_date=timezone.localdate() + datetime.timedelta(days=730),
            currency=self.egp,
            user=self.user,
        )

        self.assertIsNotNone(contract)
        self.assertEqual(contract.unit, self.unit)
        self.assertEqual(contract.customer, self.customer1)
        self.assertEqual(contract.final_contract_price, Decimal('4500000.00'))

        booking.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(booking.status, UnitBooking.BookingStatus.CONVERTED_TO_CONTRACT)
        self.assertEqual(self.unit.status, PropertyUnit.UnitStatus.CONTRACTED)
        self.assertIsNone(self.unit.current_booking)

        # محاولة تحويل نفس الحجز مرة ثانية يجب أن ترفض
        with self.assertRaises(BookingValidationError):
            UnitBookingService.convert_booking_to_contract(
                booking_id=booking.id,
                user=self.user,
            )

    def test_cancel_booking_and_clean_resale_lifecycle(self):
        """
        التحقق من إلغاء الحجز وإعادة الوحدة لدورة البيع (Resale Lifecycle):
        - تحرير الوحدة إلى AVAILABLE ومسح current_booking.
        - إمكانية إعادة حجز الوحدة مجدداً برقم استمارة جديد لعميل آخر دون أي تعارض فريد.
        """
        expiry = timezone.localdate() + datetime.timedelta(days=7)
        booking = UnitBookingService.create_booking(
            unit_id=self.unit.id,
            customer=self.customer1,
            holding_deposit=Decimal('50000.00'),
            expiry_date=expiry,
            user=self.user,
        )

        # إلغاء الحجز مع فصل طلب الاسترداد عن الصرف الفعلي
        cancelled_booking = UnitBookingService.cancel_booking(
            booking_id=booking.id,
            reason='طلب العميل استرداد الحجز لظروف خاصة',
            forfeit_deposit=False,
            user=self.user,
        )

        self.assertEqual(cancelled_booking.status, UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND)

        # تنفيذ الصرف والتسوية المالية الفعلية لرد جدية الحجز
        refunded_booking = UnitBookingService.process_booking_refund(
            booking_id=cancelled_booking.id,
            payment_account=self.escrow_acc,
            user=self.user
        )
        self.assertEqual(refunded_booking.status, UnitBooking.BookingStatus.CANCELLED_REFUNDED)

        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, PropertyUnit.UnitStatus.AVAILABLE)
        self.assertIsNone(self.unit.current_booking)

        # إعادة حجز الوحدة بنجاح للعميل الثاني (Resale Cycle)
        new_booking = UnitBookingService.create_booking(
            unit_id=self.unit.id,
            customer=self.customer2,
            holding_deposit=Decimal('60000.00'),
            expiry_date=timezone.localdate() + datetime.timedelta(days=14),
            user=self.user,
        )

        self.assertIsNotNone(new_booking)
        self.assertEqual(new_booking.customer, self.customer2)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, PropertyUnit.UnitStatus.RESERVED)
        self.assertEqual(self.unit.current_booking, new_booking)

    def test_booking_sweeper_atomic_double_lock_guard(self):
        """
        التحقق من كنس الحجوزات المنتهية مع الحماية التزامنية المزدوجة (Double-Lock Concurrency Guard):
        1. الحجز المنتهي للوحدة المحجوزة يتم كنسه وتحرير الوحدة إلى AVAILABLE.
        2. الحجز المنتهي الذي تم تحويل وحدته لتعاقد (CONTRACTED) يتم تفادي تحريرها قطعياً.
        """
        today = timezone.localdate()
        past_date = today - datetime.timedelta(days=10)
        past_expiry = today - datetime.timedelta(days=2)

        # حجز 1: منتهي الصلاحية والوحدة لا تزال RESERVED له
        booking_expired = UnitBookingService.create_booking(
            unit_id=self.unit.id,
            customer=self.customer1,
            holding_deposit=Decimal('50000.00'),
            expiry_date=past_expiry,
            booking_date=past_date,
            user=self.user,
        )

        # تشغيل الكنس بتاريخ اليوم
        swept = UnitBookingSweepService.sweep_expired_bookings(as_of_date=today)
        self.assertEqual(swept, 1)

        booking_expired.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(booking_expired.status, UnitBooking.BookingStatus.EXPIRED_RELEASED)
        self.assertEqual(self.unit.status, PropertyUnit.UnitStatus.AVAILABLE)
        self.assertIsNone(self.unit.current_booking)

        # سيناريو سباق التزامن: حجز منتهي ولكن تم تحويل الوحدة تعاقدياً بالتزامن
        booking_race = UnitBookingService.create_booking(
            unit_id=self.unit.id,
            customer=self.customer2,
            holding_deposit=Decimal('50000.00'),
            expiry_date=today + datetime.timedelta(days=5),
            booking_date=today,
            user=self.user,
        )

        # تحويل الوحدة بالتزامن لعقد
        UnitBookingService.convert_booking_to_contract(
            booking_id=booking_race.id,
            user=self.user,
        )

        # إعادة حالة الحجز اصطناعياً إلى ACTIVE وتاريخ منتهي لمحاكاة سباق عمال الخلفية
        UnitBooking.objects.filter(pk=booking_race.id).update(
            status=UnitBooking.BookingStatus.ACTIVE,
            expiry_date=today - datetime.timedelta(days=1)
        )

        # تشغيل الكنس: الحارس المزدوج يجب أن يكتشف أن الوحدة CONTRACTED وليست RESERVED ويرفض تحريرها
        swept_race = UnitBookingSweepService.sweep_expired_bookings(as_of_date=today)
        self.assertEqual(swept_race, 0)

        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, PropertyUnit.UnitStatus.CONTRACTED)

    def test_visual_matrix_page_load_and_query_efficiency(self):
        """
        التحقق من كفاءة استعلامات المصفوفة المعمارية (Section 6.11):
        - منع مشكلة N+1 بالكامل: ثبات عدد الاستعلامات تماماً مهما زاد عدد الوحدات والطوابق.
        """
        url = reverse('real_estate:project_matrix', kwargs={'project_id': self.project.id})
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        # طلب تمهيدي لتهيئة كاش الجلسة والإعدادات العامة (Warm-up Request)
        self.client.get(url)

        # التحميل الأول مع وحدة واحدة
        with CaptureQueriesContext(connection) as ctx1:
            res1 = self.client.get(url)
        self.assertEqual(res1.status_code, 200)

        # إضافة 30 وحدة إضافية عبر طوابق وبلوكات متعددة لاختبار استقرار الاستعلامات
        more_units = [
            PropertyUnit(
                project=self.project,
                block=self.block,
                floor=self.floor,
                unit_code=f'U-T1-BENCH-{i}',
                unit_type=PropertyUnit.UnitType.APARTMENT,
                net_area=Decimal('100.00'),
                gross_area=Decimal('125.00'),
                meter_price=Decimal('25000.00'),
                base_price=Decimal('3125000.00'),
                total_price=Decimal('3125000.00'),
                status=PropertyUnit.UnitStatus.AVAILABLE,
            )
            for i in range(1, 31)
        ]
        PropertyUnit.objects.bulk_create(more_units)

        # التحميل الثاني مع 31 وحدة: عدد الاستعلامات يجب أن يظل ثابتاً بالكامل (Zero N+1 Query Regressions)
        with CaptureQueriesContext(connection) as ctx2:
            res2 = self.client.get(url)
        self.assertEqual(res2.status_code, 200)

        self.assertEqual(len(ctx1), len(ctx2))
        self.assertContains(res2, 'المصفوفة المعمارية لطوابق المشروع')
        self.assertContains(res2, 'U-T1-301')
        self.assertContains(res2, 'U-T1-BENCH-30')
        self.assertContains(res2, 'أبراج الأفق الجديدة')

    def test_api_unit_detail_and_instant_booking(self):
        """
        التحقق من مسارات الـ AJAX الخاصة بالمصفوفة:
        - api_unit_detail يجلب تفاصيل الوحدة بصيغة JSON.
        - api_book_unit يحجز الوحدة ويرجع استجابة JSON 200 أو 409 عند التعارض.
        - api_cancel_booking يلغي الحجز ويحرر الوحدة.
        """
        # 1. جلب التفاصيل
        detail_url = reverse('real_estate:api_unit_detail', kwargs={'unit_id': self.unit.id})
        res = self.client.get(detail_url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['unit']['unit_code'], 'U-T1-301')
        self.assertEqual(data['unit']['status'], 'AVAILABLE')

        # 2. الحجز عبر API
        book_url = reverse('real_estate:api_book_unit', kwargs={'unit_id': self.unit.id})
        payload = {
            'customer_id': self.customer1.id,
            'holding_deposit': '75000.00',
            'expiry_date': (timezone.localdate() + datetime.timedelta(days=7)).strftime('%Y-%m-%d'),
            'notes': 'حجز عبر واجهة المصفوفة'
        }
        book_res = self.client.post(
            book_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(book_res.status_code, 200)
        book_data = book_res.json()
        self.assertTrue(book_data['success'])
        self.assertEqual(book_data['unit_status'], 'RESERVED')
        booking_id = book_data['booking_id']

        # 3. محاولة حجز نفس الوحدة مرة أخرى يجب أن ترجع 409 Conflict
        book_conflict_res = self.client.post(
            book_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(book_conflict_res.status_code, 409)
        self.assertFalse(book_conflict_res.json()['success'])

        # 4. إلغاء الحجز عبر API
        cancel_url = reverse('real_estate:api_cancel_booking', kwargs={'booking_id': booking_id})
        cancel_res = self.client.post(
            cancel_url,
            data=json.dumps({'reason': 'إلغاء تجريبي', 'forfeit_deposit': False}),
            content_type='application/json'
        )
        self.assertEqual(cancel_res.status_code, 200)
        self.assertTrue(cancel_res.json()['success'])
        self.assertEqual(cancel_res.json()['unit_status'], 'AVAILABLE')

        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, PropertyUnit.UnitStatus.AVAILABLE)
