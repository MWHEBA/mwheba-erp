import pytest
from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from supplier.models import Supplier, SupplierType, ServiceType, SupplierService, ServicePriceHistory
from financial.models import Currency

User = get_user_model()


class ServicePriceGovernanceModelTest(TestCase):
    """
    اختبارات حوكمة صلاحية الأسعار وتتبع تاريخ أسعار خدمات الموردين
    """

    def setUp(self):
        self.user = User.objects.create_user(username='pricing_officer', password='password123', is_staff=True)

        self.supplier_type = SupplierType.objects.create(name="مورد ورق", code="paper_supplier")
        self.supplier = Supplier.objects.create(name="شركة الأهرام للورق", code="SUPP_PAPER_01", primary_type=self.supplier_type)

        self.service_type_paper = ServiceType.objects.create(
            name="توريد ورق",
            code="paper",
            category="manufacturing",
            default_validity_days=15
        )

        self.service_type_general = ServiceType.objects.create(
            name="خدمة عامة",
            code="general_service",
            category="general",
            default_validity_days=30
        )

    def test_default_validity_days_staleness_calculation(self):
        """اختبار حساب تقادم السعر بالاعتماد على default_validity_days لنوع الخدمة"""
        today = timezone.now()
        # خدمة حُدث سعرها قبل 20 يوماً (نوع الخدمة صلاحيته 15 يوماً فقط للورق)
        service = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_paper,
            name="ورق كوشيه 150 جرام 70*100",
            pricing_formula="PER_TON",
            price_per_ton=Decimal("45000.00"),
            base_price=Decimal("45.00"),
            price_updated_at=today - timedelta(days=20),
            price_valid_until=None
        )

        self.assertTrue(service.is_price_stale)
        self.assertEqual(service.price_staleness_status, 'stale')
        self.assertEqual(service.price_age_days, 20)

    def test_explicit_validity_date_takes_precedence(self):
        """تاريخ الصلاحية الصريح price_valid_until له الأولوية القصوى"""
        today = timezone.now().date()
        # تاريخ الصلاحية ينتهي بعد 3 أيام
        service = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_general,
            name="تجليد فاخر",
            pricing_formula="PER_PIECE",
            base_price=Decimal("15.00"),
            price_updated_at=timezone.now(),
            price_valid_until=today + timedelta(days=3)
        )

        self.assertFalse(service.is_price_stale)
        self.assertEqual(service.price_staleness_status, 'expiring_soon')

        # لو تاريخ الصلاحية بالأمس
        service.price_valid_until = today - timedelta(days=1)
        service.save()
        self.assertTrue(service.is_price_stale)
        self.assertEqual(service.price_staleness_status, 'stale')

    def test_fresh_price_status(self):
        """اختبار السعر الطازج الساري"""
        today = timezone.now().date()
        service = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_general,
            name="سلوفان مط",
            pricing_formula="PER_SHEET",
            base_price=Decimal("0.85"),
            price_updated_at=timezone.now(),
            price_valid_until=today + timedelta(days=25)
        )

        self.assertFalse(service.is_price_stale)
        self.assertEqual(service.price_staleness_status, 'fresh')

    def test_log_price_change_creates_immutable_history(self):
        """اختبار تسجيل حركة تغيير السعر في ServicePriceHistory واحتساب نسبة التغير"""
        service = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_paper,
            name="ورق طبع 80 جرام",
            pricing_formula="PER_TON",
            price_per_ton=Decimal("40000.00"),
            base_price=Decimal("40.00")
        )

        old_snap = service.pricing_snapshot

        # تحديث السعر
        service.price_per_ton = Decimal("44000.00")
        service.price_updated_at = timezone.now()
        service.save()

        history = ServicePriceHistory.log_price_change(
            service=service,
            user=self.user,
            source='MANUAL',
            quote_reference='QUO-2026-001',
            notes='زيادة سنوية من المورد',
            old_snapshot=old_snap
        )

        self.assertEqual(history.service, service)
        self.assertEqual(history.supplier, self.supplier)
        self.assertEqual(history.changed_by, self.user)
        self.assertEqual(history.change_source, 'MANUAL')
        self.assertEqual(history.quote_reference, 'QUO-2026-001')
        self.assertEqual(history.old_unit_price, Decimal('40000.00'))
        self.assertEqual(history.new_unit_price, Decimal('44000.00'))
        # نسبة التغير = ((44000 - 40000) / 40000) * 100 = 10.00%
        self.assertEqual(history.price_variance_percentage, Decimal('10.00'))
        self.assertIn('service_id', history.new_snapshot)
        self.assertIn('pricing_formula', history.new_snapshot)

    def test_fx_rate_stale_under_ias21(self):
        """فحص عمر سعر الصرف للعملات الأجنبية وفق قاعدة 7 أيام في معيار IAS 21"""
        from financial.models.currency import ExchangeRate
        egp, _ = Currency.objects.get_or_create(
            code='EGP',
            defaults={
                'name': 'جنيه مصري',
                'symbol': 'ج.م',
                'is_functional': True,
            }
        )
        usd, _ = Currency.objects.get_or_create(
            code='USD',
            defaults={
                'name': 'دولار أمريكي',
                'symbol': '$',
                'is_functional': False,
            }
        )
        # تسجيل سعر صرف قديم (قبل 10 أيام - متجاوز لقاعدة 7 أيام)
        rate_date = timezone.now().date() - timedelta(days=10)
        ExchangeRate.objects.create(
            from_currency=usd,
            to_currency=egp,
            rate=Decimal('50.000000'),
            effective_date=rate_date
        )

        service = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_paper,
            name="ورق مستورد بالدولار",
            pricing_formula="PER_TON",
            price_per_ton=Decimal("900.00"),
            currency=usd
        )

        self.assertTrue(service.is_foreign_currency)
        self.assertTrue(service.is_fx_rate_stale)

    def test_quick_renew_endpoint(self):
        """اختبار مسار التجديد والتأكيد السريع لسريان السعر"""
        from django.urls import reverse
        from core.models import SystemModule
        SystemModule.objects.update_or_create(code='printing_pricing', defaults={'name': 'تسعير المطبوعات', 'is_enabled': True})

        self.client.login(username='pricing_officer', password='password123')
        today = timezone.now()
        service = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_paper,
            name="ورق كوشيه 115 جرام",
            pricing_formula="PER_TON",
            price_per_ton=Decimal("42000.00"),
            base_price=Decimal("42.00"),
            price_updated_at=today - timedelta(days=25)
        )
        self.assertTrue(service.is_price_stale)

        url = reverse('supplier:supplier_service_quick_renew_price', kwargs={'pk': self.supplier.pk, 'service_pk': service.pk})
        response = self.client.post(url, {'days': 45, 'ajax': '1'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        service.refresh_from_db()
        self.assertFalse(service.is_price_stale)
        self.assertEqual(service.price_staleness_status, 'fresh')
        expected_date = (timezone.now() + timedelta(days=45)).date()
        self.assertEqual(service.price_valid_until, expected_date)

        # التحقق من تسجيل الحركة في سجل التاريخ
        hist = ServicePriceHistory.objects.filter(service=service, change_source='QUICK_RENEW').first()
        self.assertIsNotNone(hist)
        self.assertEqual(hist.changed_by, self.user)
        self.assertIn('45 يوماً', hist.notes)

    def test_service_detail_context_has_histories(self):
        """التحقق من تمرير سجل التاريخ في سياق عرض تفاصيل الخدمة"""
        from django.urls import reverse
        from core.models import SystemModule
        SystemModule.objects.update_or_create(code='printing_pricing', defaults={'name': 'تسعير المطبوعات', 'is_enabled': True})

        self.client.login(username='pricing_officer', password='password123')
        service = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_paper,
            name="ورق كوشيه 200 جرام",
            pricing_formula="PER_TON",
            price_per_ton=Decimal("46000.00"),
            base_price=Decimal("46.00")
        )

        ServicePriceHistory.log_price_change(
            service=service,
            user=self.user,
            source='INITIAL',
            notes='تسجيل أولي'
        )

        url = reverse('supplier:supplier_service_detail', kwargs={'pk': self.supplier.pk, 'service_pk': service.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('price_histories', response.context)
        self.assertEqual(len(response.context['price_histories']), 1)

    def test_best_market_prices_excludes_stale_prices(self):
        """التحقق من استبعاد الأسعار المتقادمة من الفوز بشارة الأفضل سعراً في مصفوفة الأسعار"""
        from supplier.views_settings.service_pricing_views import _compute_best_market_prices

        # مورد ثان للمنافسة
        supp2 = Supplier.objects.create(name="شركة النيل للورق", code="SUPP_PAPER_02", primary_type=self.supplier_type)

        # المورد 1 لديه سعر رخيص جداً لكنه منتهي الصلاحية (قديم)
        s1 = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_paper,
            name="ورق 80 جم أبيض",
            pricing_formula="PER_TON",
            price_per_ton=Decimal("30000.00"),
            base_price=Decimal("30.00"),
            price_valid_until=timezone.now().date() - timedelta(days=5) # منتهي
        )
        self.assertTrue(s1.is_price_stale)

        # المورد 2 لديه سعر أعلى قليلاً لكنه ساري ومحدث
        s2 = SupplierService.objects.create(
            supplier=supp2,
            service_type=self.service_type_paper,
            name="ورق 80 جم أبيض",
            pricing_formula="PER_TON",
            price_per_ton=Decimal("35000.00"),
            base_price=Decimal("35.00"),
            price_valid_until=timezone.now().date() + timedelta(days=20) # ساري
        )
        self.assertFalse(s2.is_price_stale)

        rates_map = {}
        qs = [s1, s2]
        best_ids = _compute_best_market_prices(qs, rates_map)

        # لا يجب أن يفوز s1 لأن سعره منتهي، ولا يفوز s2 لأنه لا يوجد منافس آخر بسعر ساري (>= 2)
        self.assertNotIn(s1.id, best_ids)

    def test_bulk_price_updater_service_logs_history(self):
        """التحقق من تسجيل حركات الأسعار في سجل التاريخ عند التحديث الفردي أو المجمع بنسبة مئوية"""
        from printing_pricing.services.bulk_price_updater import BulkPriceUpdaterService

        service = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_paper,
            name="ورق برستول 300 جرام",
            pricing_formula="PER_TON",
            price_per_ton=Decimal("50000.00"),
            base_price=Decimal("50.00")
        )

        # 1. تحديث فردي
        BulkPriceUpdaterService.update_single_service(
            service,
            price_per_ton=Decimal("55000.00"),
            user=self.user
        )
        service.refresh_from_db()
        self.assertEqual(service.price_per_ton, Decimal("55000.00"))

        hist1 = ServicePriceHistory.objects.filter(service=service, change_source='MANUAL').first()
        self.assertIsNotNone(hist1)
        self.assertEqual(hist1.old_unit_price, Decimal("50000.00"))
        self.assertEqual(hist1.new_unit_price, Decimal("55000.00"))
        self.assertEqual(hist1.price_variance_percentage, Decimal("10.00"))

        # 2. تحديث مجمع بنسبة +10%
        result = BulkPriceUpdaterService.bulk_update_supplier_services(
            service_ids=[service.id],
            percentage_change=Decimal("10.00"),
            user=self.user
        )
        self.assertTrue(result['success'])
        service.refresh_from_db()
        self.assertEqual(service.price_per_ton, Decimal("60500.00"))

        hist2 = ServicePriceHistory.objects.filter(service=service, change_source='BULK_PERCENTAGE').first()
        self.assertIsNotNone(hist2)
        self.assertEqual(hist2.new_unit_price, Decimal("60500.00"))
        self.assertEqual(hist2.price_variance_percentage, Decimal("10.00"))


