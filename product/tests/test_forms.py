from django.test import TestCase
from django.contrib.auth import get_user_model
from product.forms import ProductForm, CategoryForm, StockAdjustmentForm
from product.models import Category, Brand, Unit, Product, Warehouse, Stock
from decimal import Decimal

User = get_user_model()


class ProductFormTest(TestCase):
    """
    اختبارات نموذج إدخال المنتج
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )

        self.category = Category.objects.create(
            name="فئة اختبار", description="وصف التصنيف", created_by=self.user
        )

        self.brand = Brand.objects.create(
            name="علامة تجارية", description="وصف العلامة", created_by=self.user
        )

        self.unit = Unit.objects.create(
            name="قطعة", abbreviation="ق", created_by=self.user
        )

    def test_valid_product_form(self):
        """
        اختبار صحة نموذج المنتج بالبيانات الصحيحة
        """
        form_data = {
            "name": "منتج اختبار",
            "code": "TEST001",
            "barcode": "1234567890123",
            "description": "وصف المنتج",
            "category": self.category.id,
            "brand": self.brand.id,
            "unit": self.unit.id,
            "purchase_price": "100.00",
            "sale_price": "150.00",
            "min_stock": 10,
            "max_stock": 100,
        }

        form = ProductForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_invalid_product_form(self):
        """
        اختبار رفض نموذج المنتج بالبيانات غير الصحيحة
        """
        # نموذج بدون اسم
        form_data = {
            "code": "TEST001",
            "category": self.category.id,
            "unit": self.unit.id,
            "purchase_price": "100.00",
            "sale_price": "150.00",
        }

        form = ProductForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

        # سعر بيع أقل من سعر الشراء
        form_data = {
            "name": "منتج اختبار",
            "code": "TEST001",
            "category": self.category.id,
            "unit": self.unit.id,
            "purchase_price": "200.00",
            "sale_price": "150.00",
        }

        form = ProductForm(data=form_data)
        self.assertFalse(form.is_valid())
        # التحقق من وجود خطأ في الحقول (يعتمد على طريقة التحقق المستخدمة)
        self.assertTrue(any("سعر البيع" in str(err) for err in form.non_field_errors()))

    def test_duplicate_product_code(self):
        """
        اختبار رفض كود منتج مكرر
        """
        # إنشاء منتج أول
        Product.objects.create(
            name="منتج أول",
            code="TEST001",
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            purchase_price=Decimal("100.00"),
            sale_price=Decimal("150.00"),
            created_by=self.user,
        )

        # محاولة إنشاء منتج ثاني بنفس الكود
        form_data = {
            "name": "منتج ثاني",
            "code": "TEST001",  # كود مكرر
            "category": self.category.id,
            "unit": self.unit.id,
            "purchase_price": "100.00",
            "sale_price": "150.00",
        }

        form = ProductForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("code", form.errors)


class CategoryFormTest(TestCase):
    """
    اختبارات نموذج إدخال التصنيف
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )

        self.parent_category = Category.objects.create(
            name="فئة رئيسية", description="وصف التصنيف الرئيسية", created_by=self.user
        )

    def test_valid_category_form(self):
        """
        اختبار صحة نموذج التصنيف بالبيانات الصحيحة
        """
        form_data = {
            "name": "فئة فرعية",
            "description": "وصف التصنيف الفرعية",
            "parent": self.parent_category.id,
        }

        form = CategoryForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_invalid_category_form(self):
        """
        اختبار رفض نموذج التصنيف بالبيانات غير الصحيحة
        """
        # نموذج بدون اسم
        form_data = {
            "description": "وصف التصنيف",
        }

        form = CategoryForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_category_as_own_parent(self):
        """
        اختبار رفض تعيين التصنيف كأب لنفسها
        """
        # إنشاء فئة أولاً
        category = Category.objects.create(
            name="فئة اختبار", description="وصف التصنيف", created_by=self.user
        )

        # محاولة تعيينها كأب لنفسها
        form_data = {
            "name": "فئة اختبار",
            "description": "وصف التصنيف",
            "parent": category.id,
        }

        form = CategoryForm(data=form_data, instance=category)
        self.assertFalse(form.is_valid())
        self.assertIn("parent", form.errors)


class StockAdjustmentFormTest(TestCase):
    """
    اختبارات نموذج تسوية المخزون
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )

        self.category = Category.objects.create(name="فئة اختبار", created_by=self.user)

        self.unit = Unit.objects.create(
            name="قطعة", abbreviation="ق", created_by=self.user
        )

        self.product = Product.objects.create(
            name="منتج اختبار",
            code="TEST001",
            category=self.category,
            unit=self.unit,
            purchase_price=Decimal("100.00"),
            sale_price=Decimal("150.00"),
            created_by=self.user,
        )

        self.warehouse = Warehouse.objects.create(
            name="مخزن اختبار", code="WH001", created_by=self.user
        )

        self.stock = Stock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=50,
            created_by=self.user,
        )

    def test_valid_stock_adjustment_form(self):
        """
        اختبار صحة نموذج تسوية المخزون بالبيانات الصحيحة
        """
        form_data = {
            "quantity": 60,  # الكمية الجديدة
            "notes": "تسوية المخزون للاختبار",
        }

        form = StockAdjustmentForm(
            data=form_data, initial={"current_quantity": self.stock.quantity}
        )
        self.assertTrue(form.is_valid())

    def test_invalid_stock_adjustment_form(self):
        """
        اختبار رفض نموذج تسوية المخزون بالبيانات غير الصحيحة
        """
        # كمية سالبة
        form_data = {"quantity": -10, "notes": "كمية غير صالحة"}

        form = StockAdjustmentForm(
            data=form_data, initial={"current_quantity": self.stock.quantity}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("quantity", form.errors)

        # بدون ملاحظات (إذا كانت إلزامية)
        form_data = {"quantity": 60}

        form = StockAdjustmentForm(
            data=form_data, initial={"current_quantity": self.stock.quantity}
        )
        # التحقق من الخطأ (يعتمد على إعدادات النموذج)
        if "notes" in form.fields and form.fields["notes"].required:
            self.assertFalse(form.is_valid())
            self.assertIn("notes", form.errors)
