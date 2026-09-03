"""
حزمة اختبارات التطابق المالي والتشغيلي لكارت الطباعة (Zero-Drift Financial Parity Suite)
تتحقق من:
1. توحيد نوع المطبوع ProductType واشتقاق order_type آلياً.
2. حقل اللوجستيات اليدوي الصريح (extra_cost) وانعدام أي حسابات آلية خفية للمشال أو الكراتين.
3. قراءة أبعاد الفرخ الخام ديناميكياً من جدول PaperSize دون شروط نصية هشة.
4. استقرار وتطابق الحسابات وتفكيك البنود بدقة تامة.
"""
from decimal import Decimal
import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from printing_pricing.models import (
    PrintingOrder, ProductType, ProductSize, PaperSize, PieceSize,
    OrderMaterial, OrderService, OrderSummary
)
from printing_pricing.services.anatomy_persistence_service import OrderAnatomyPersistenceService

User = get_user_model()


class FinancialParityAndCleanArchitectureTest(TestCase):
    """اختبارات التطابق المالي والمعماري بعد التطهير"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='parity_admin',
            password='testpassword123',
            is_staff=True
        )

        # 1. إعداد أنواع المطبوعات
        self.pt_flyer = ProductType.objects.create(
            name="فلاير دعائي",
            base_archetype="flyer",
            is_active=True,
            is_default=True
        )
        self.pt_catalog = ProductType.objects.create(
            name="كتالوج فاخر",
            base_archetype="catalog",
            is_active=True
        )

        # 2. إعداد مقاسات الأفرخ في قاعدة البيانات
        self.paper_size_70_100 = PaperSize.objects.create(
            name="فرخ قياسي 70×100",
            width=Decimal("70.00"),
            height=Decimal("100.00"),
            is_active=True
        )
        self.paper_size_66_88 = PaperSize.objects.create(
            name="فرخ جاير 66×88",
            width=Decimal("66.00"),
            height=Decimal("88.00"),
            is_active=True
        )

        # 3. إعداد مقاس الماكينة / السرير
        self.piece_size_50_70 = PieceSize.objects.create(
            name="نصف فرخ (50×70)",
            width=Decimal("50.00"),
            height=Decimal("70.00"),
            paper_type=self.paper_size_70_100,
            is_default=True
        )

    def test_product_type_auto_derives_order_type(self):
        """التحقق من أن اختيار ProductType يشتق order.order_type آلياً"""
        order = PrintingOrder.objects.create(
            title="بروشور تسويقي",
            product_type=self.pt_catalog,
            quantity=1000,
            created_by=self.user
        )
        self.assertEqual(order.order_type, "catalog")

    def test_manual_logistics_cost_zero_by_default_no_hidden_fees(self):
        """التحقق من أن عدم إدخال لوجستيات لا يضيف أي كراتين أو مشال خفية في الباك إند"""
        order = PrintingOrder.objects.create(
            title="فلاير 1000 نسخة",
            product_type=self.pt_flyer,
            quantity=1000,
            width=Decimal("21.00"),
            height=Decimal("29.70"),
            created_by=self.user
        )
        post_data = {
            'product_type': self.pt_flyer.pk,
            'quantity': 1000,
            'width': 21.0,
            'height': 29.7,
            'sheet_size': str(self.paper_size_70_100.pk),
            'profit_margin': '25.00',
            # extra_cost غير مرسل إطلاقاً
        }

        summary = OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        # يجب أن تكون التكاليف الأخرى (اللوجستيات) صفراً تماماً دون أي زيادات خفية
        self.assertEqual(summary.other_costs, Decimal("0.00"))

    def test_explicit_manual_logistics_cost_preserved_exactly(self):
        """التحقق من أن القيمة المدخلة يدوياً في extra_cost تسجل بالمليم في other_costs"""
        order = PrintingOrder.objects.create(
            title="فلاير مع شحن خاص",
            product_type=self.pt_flyer,
            quantity=2000,
            width=Decimal("21.00"),
            height=Decimal("29.70"),
            created_by=self.user
        )
        post_data = {
            'product_type': self.pt_flyer.pk,
            'quantity': 2000,
            'width': 21.0,
            'height': 29.7,
            'sheet_size': str(self.paper_size_70_100.pk),
            'extra_cost': '135.50',  # تكلفة شحن وانتقالات يدوية صريحة
            'profit_margin': '20.00',
        }

        summary = OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        self.assertEqual(summary.other_costs, Decimal("135.50"))
        # والتكلفة الإجمالية تتضمن بالضبط التكلفة اليدوية
        expected_total = summary.material_cost + summary.printing_cost + summary.finishing_cost + Decimal("135.50")
        self.assertEqual(summary.total_cost, expected_total)

    def test_dynamic_paper_size_lookup_by_pk_and_name(self):
        """التحقق من قراءة أبعاد الورق من جدول PaperSize رقمياً"""
        order = PrintingOrder.objects.create(
            title="شغلانة على فرخ 66x88",
            product_type=self.pt_flyer,
            quantity=500,
            width=Decimal("15.00"),
            height=Decimal("20.00"),
            created_by=self.user
        )
        # إرسال المفتاح الأساسي للفرخ
        post_data = {
            'product_type': self.pt_flyer.pk,
            'quantity': 500,
            'width': 15.0,
            'height': 20.0,
            'sheet_size': str(self.paper_size_66_88.pk),
            'profit_margin': '25.00',
        }

        summary = OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        self.assertIsNotNone(summary)
        paper_mat = OrderMaterial.objects.filter(order=order, material_type='paper').first()
        self.assertIsNotNone(paper_mat)
