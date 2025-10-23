from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from product.models import (
    Category,
    Brand,
    Unit,
    Product,
    Warehouse,
    Stock,
    StockMovement,
    ProductImage,
)
from decimal import Decimal
import json
import unittest
import sys

User = get_user_model()


class ProductViewsTest(TestCase):
    """
    اختبارات عروض صفحات المنتجات
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
            email="test@example.com",
            is_staff=True,
        )
        self.client.login(username="testuser", password="testpass123")

        # إنشاء بيانات اختبار
        self.category = Category.objects.create(
            name="فئة اختبار", description="وصف فئة الاختبار"
        )

        self.brand = Brand.objects.create(
            name="علامة اختبار", description="وصف علامة الاختبار"
        )

        self.unit = Unit.objects.create(
            name="وحدة اختبار", symbol="وح"
        )

        self.product = Product.objects.create(
            name="منتج اختبار",
            sku="TEST001",
            description="وصف منتج الاختبار",
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            created_by=self.user
        )

        self.warehouse = Warehouse.objects.create(
            name="مخزن اختبار", code="TST001", manager=self.user
        )

        self.stock = Stock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=50,
            created_by=self.user
        )

    def test_product_list_view(self):
        """
        اختبار صفحة قائمة المنتجات
        """
        url = reverse("product:product_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "product/product_list.html")
        self.assertContains(response, "منتج اختبار")
        self.assertContains(response, "TEST001")

    def test_product_detail_view(self):
        """
        اختبار صفحة تفاصيل المنتج
        """
        url = reverse("product:product_detail", args=[self.product.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "product/product_detail.html")
        self.assertContains(response, "منتج اختبار")
        self.assertContains(response, "TEST001")
        # Price displayed without trailing zeros
        self.assertContains(response, "150")

    def test_product_create_view_get(self):
        """
        اختبار طلب GET لصفحة إنشاء منتج جديد
        """
        url = reverse("product:product_create")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "product/product_form.html")
        self.assertContains(response, "إضافة منتج جديد")

    def test_product_create_view_post(self):
        """
        اختبار طلب POST لإنشاء منتج جديد
        """
        url = reverse("product:product_create")
        data = {
            "name": "منتج جديد",
            "sku": "NEW001",
            "description": "وصف المنتج الجديد",
            "category": self.category.pk,
            "brand": self.brand.pk,
            "unit": self.unit.pk,
            "cost_price": "120.00",
            "selling_price": "180.00",
            "min_stock": 5,
            "max_stock": 50,
        }

        response = self.client.post(url, data)

        # يجب أن يتم التحويل بعد الإنشاء بنجاح
        self.assertEqual(response.status_code, 302)

        # التحقق من إنشاء المنتج
        self.assertTrue(Product.objects.filter(sku="NEW001").exists())
        new_product = Product.objects.get(sku="NEW001")
        self.assertEqual(new_product.name, "منتج جديد")
        self.assertEqual(new_product.cost_price, Decimal("120.00"))

    def test_product_edit_view(self):
        """
        اختبار تعديل منتج
        """
        url = reverse("product:product_edit", args=[self.product.pk])

        # اختبار طلب GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "product/product_form.html")
        self.assertContains(response, "منتج اختبار")

        # اختبار طلب POST
        data = {
            "name": "منتج اختبار محدث",
            "sku": "TEST001",
            "description": "وصف محدث",
            "category": self.category.pk,
            "brand": self.brand.pk,
            "unit": self.unit.pk,
            "cost_price": "110.00",
            "selling_price": "160.00",
            "min_stock": 15,
            "max_stock": 120,
        }

        response = self.client.post(url, data)

        # يجب أن يتم التحويل بعد التحديث بنجاح
        self.assertEqual(response.status_code, 302)

        # التحقق من تحديث المنتج
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "منتج اختبار محدث")
        self.assertEqual(self.product.description, "وصف محدث")
        self.assertEqual(self.product.cost_price, Decimal("110.00"))
        self.assertEqual(self.product.selling_price, Decimal("160.00"))

    def test_product_delete_view(self):
        """
        اختبار حذف منتج
        """
        url = reverse("product:product_delete", args=[self.product.pk])

        # اختبار طلب GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "product/product_confirm_delete.html")

        # اختبار طلب POST
        response = self.client.post(url)

        # يجب أن يتم التحويل بعد الحذف بنجاح
        self.assertEqual(response.status_code, 302)

        # التحقق من حذف المنتج (hard delete - soft delete not implemented)
        self.assertFalse(Product.objects.filter(pk=self.product.pk).exists())


class CategoryViewsTest(TestCase):
    """
    اختبارات عروض صفحات التصنيفات
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
            email="test@example.com",
            is_staff=True,
        )
        self.client.login(username="testuser", password="testpass123")

        # إنشاء بيانات اختبار
        self.parent_category = Category.objects.create(
            name="فئة رئيسية اختبار",
            description="وصف التصنيف الرئيسية",
        )

        self.child_category = Category.objects.create(
            name="فئة فرعية اختبار",
            description="وصف التصنيف الفرعية",
            parent=self.parent_category,
        )

    def test_category_list_view(self):
        """
        اختبار صفحة قائمة التصنيفات
        """
        url = reverse("product:category_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "product/category_list.html")
        self.assertContains(response, "فئة رئيسية اختبار")
        self.assertContains(response, "فئة فرعية اختبار")

    def test_category_create_view(self):
        """
        اختبار إنشاء فئة جديدة
        """
        url = reverse("product:category_create")

        # اختبار طلب GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "product/category_form.html")

        # اختبار طلب POST
        data = {
            "name": "فئة جديدة",
            "description": "وصف التصنيف الجديدة",
            "parent": self.parent_category.pk,
        }

        response = self.client.post(url, data)

        # يجب أن يتم التحويل بعد الإنشاء بنجاح
        self.assertEqual(response.status_code, 302)

        # التحقق من إنشاء التصنيف
        self.assertTrue(Category.objects.filter(name="فئة جديدة").exists())
        new_category = Category.objects.get(name="فئة جديدة")
        self.assertEqual(new_category.description, "وصف التصنيف الجديدة")
        self.assertEqual(new_category.parent, self.parent_category)


class WarehouseViewsTest(TestCase):
    """
    اختبارات عروض صفحات المخازن
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
            email="test@example.com",
            is_staff=True,
        )
        self.client.login(username="testuser", password="testpass123")

        # إنشاء بيانات اختبار
        self.warehouse = Warehouse.objects.create(
            name="مخزن اختبار",
            code="TST001",
            location="موقع اختبار",
            manager=self.user,
            description="وصف مخزن الاختبار"
        )

    def test_warehouse_list_view(self):
        """
        اختبار صفحة قائمة المخازن
        """
        url = reverse("product:warehouse_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "product/warehouse_list.html")
        self.assertContains(response, "مخزن اختبار")
        self.assertContains(response, "TST001")

    def test_warehouse_detail_view(self):
        """
        اختبار صفحة تفاصيل المخزن
        """
        url = reverse("product:warehouse_detail", args=[self.warehouse.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "product/warehouse_detail.html")
        self.assertContains(response, "مخزن اختبار")
        self.assertContains(response, "TST001")
        # Manager username is "testuser"
        self.assertContains(response, "testuser")


class StockViewsTest(TestCase):
    """
    اختبارات عروض صفحات المخزون
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
            email="test@example.com",
            is_staff=True,
        )
        self.client.login(username="testuser", password="testpass123")

        # إنشاء بيانات اختبار
        self.category = Category.objects.create(name="فئة اختبار")

        self.unit = Unit.objects.create(
            name="وحدة اختبار", symbol="وح"
        )

        self.product = Product.objects.create(
            name="منتج اختبار",
            sku="TEST001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            created_by=self.user
        )

        self.warehouse = Warehouse.objects.create(
            name="مخزن اختبار", code="TST001", manager=self.user
        )

        self.stock = Stock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=50,
            created_by=self.user
        )

    def test_stock_list_view(self):
        """
        اختبار صفحة قائمة المخزون
        """
        url = reverse("product:stock_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "product/stock_list.html")
        self.assertContains(response, "منتج اختبار")
        self.assertContains(response, "مخزن اختبار")

    def test_stock_detail_view(self):
        """
        اختبار صفحة تفاصيل المخزون
        """
        url = reverse("product:stock_detail", args=[self.stock.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "product/stock_detail.html")
        self.assertContains(response, "منتج اختبار")
        self.assertContains(response, "مخزن اختبار")
        self.assertContains(response, "50")  # الكمية

    def test_stock_adjust_view(self):
        """Test stock adjustment view"""
        url = reverse("product:stock_adjust", args=[self.stock.pk])

        # اختبار طلب GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "تسوية المخزون")
        self.assertContains(response, "منتج اختبار")

        # اختبار طلب POST
        data = {"quantity": 75, "notes": "تعديل المخزون من خلال الاختبار"}

        response = self.client.post(url, data)

        # يجب أن يتم التحويل بعد التسوية بنجاح
        self.assertEqual(response.status_code, 302)

        # التحقق من تحديث المخزون
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 75)

        # التحقق من إنشاء حركة مخزون
        movement = StockMovement.objects.filter(
            product=self.product, warehouse=self.warehouse, movement_type="adjustment"
        ).latest("timestamp")

        # Movement stores the new quantity, not the difference
        self.assertEqual(movement.quantity, 75)
        self.assertEqual(movement.quantity_before, 50)
        self.assertEqual(movement.quantity_after, 75)
        self.assertEqual(movement.notes, "تعديل المخزون من خلال الاختبار")
