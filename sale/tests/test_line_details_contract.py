import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone

from utils.text_sanitizer import normalize_line_details
from core.utils import normalize_line_details as core_normalize_line_details
from sale.models import Quotation, QuotationItem, Sale, SaleItem
from sale.models.sales_models import SalesOrder, SalesOrderItem, SalesInvoice, SalesInvoiceItem
from purchase.models import Purchase, PurchaseItem
from purchase.models.procurement_models import PurchaseOrder, PurchaseOrderItem, SupplierBillItem
from api.serializers import PurchaseItemSerializer
from django.contrib.auth import get_user_model
from product.models import Product, Warehouse, Category, Unit
from customer.models import Customer
from supplier.models import Supplier

User = get_user_model()


class TestTextSanitizer:
    """اختبارات مطهر النصوص ومعايير التحقق من صحة تفاصيل البنود"""

    def test_empty_and_none_values(self):
        assert normalize_line_details(None) == ""
        assert normalize_line_details("") == ""
        assert normalize_line_details("   ") == ""
        assert core_normalize_line_details(None) == ""

    def test_whitespace_and_newline_normalization(self):
        raw = "  \r\nبند مخصص مقاس 10*20\r\nخامة ممتازة  \r\n"
        expected = "بند مخصص مقاس 10*20\nخامة ممتازة"
        assert normalize_line_details(raw) == expected

    def test_strip_control_characters_while_preserving_arabic(self):
        # نص عربي مع تشكيل ومسافات وأحرف تحكم ضارة
        raw = "تفاصيل\x00 مع\x07 نص\x1f عربي مُشَكَّل ورمز #123"
        expected = "تفاصيل مع نص عربي مُشَكَّل ورمز #123"
        assert normalize_line_details(raw) == expected

    def test_character_limit_boundary(self):
        # 2000 حرف يجب أن يمر بنجاح
        text_2000 = "أ" * 2000
        assert len(normalize_line_details(text_2000)) == 2000

        # 2001 حرف يجب أن يطلق ValidationError
        text_2001 = "أ" * 2001
        with pytest.raises(ValidationError) as exc:
            normalize_line_details(text_2001, row_index=3)
        assert "السطر 3" in str(exc.value)

    def test_invalid_data_types(self):
        with pytest.raises(ValidationError):
            normalize_line_details(["قائمة", "غير", "صالحة"])
        with pytest.raises(ValidationError):
            normalize_line_details({"مفتاح": "قيمة"})
        with pytest.raises(ValidationError):
            normalize_line_details(12345)


@pytest.mark.django_db
class TestLineDetailsContract:
    """اختبارات العقد البياني الموحد على مستوى النماذج والمرحلات"""

    def test_all_seven_line_models_have_details_field(self):
        models_to_check = [
            QuotationItem,
            SalesOrderItem,
            SaleItem,
            SalesInvoiceItem,
            PurchaseOrderItem,
            PurchaseItem,
            SupplierBillItem,
        ]
        for model_cls in models_to_check:
            field = model_cls._meta.get_field("details")
            assert field is not None, f"Model {model_cls.__name__} is missing 'details' field"
            assert field.default == "", f"Model {model_cls.__name__} 'details' default must be empty string"
            assert field.blank is True, f"Model {model_cls.__name__} 'details' must be blank=True"

    def test_all_six_header_models_have_show_line_details_field(self):
        headers_to_check = [
            Quotation,
            SalesOrder,
            Sale,
            SalesInvoice,
            PurchaseOrder,
            Purchase,
        ]
        for model_cls in headers_to_check:
            field = model_cls._meta.get_field("show_line_details")
            assert field is not None, f"Model {model_cls.__name__} is missing 'show_line_details' field"
            assert field.default is False, f"Model {model_cls.__name__} 'show_line_details' default must be False"

    def test_purchase_item_serializer_includes_details(self):
        serializer = PurchaseItemSerializer()
        assert "details" in serializer.fields
        assert serializer.fields["details"].read_only is False

    def test_persistence_of_line_details_and_header_flag(self):
        # إنشاء مستخدم وتصنيف ووحدة وعميل ومخزن ومنتج للاختبار
        user = User.objects.create_user(username="test_p1_user", password="password123")
        category = Category.objects.create(name="تصنيف مرحلة 1", code="CAT-T1")
        unit = Unit.objects.create(name="قطعة", symbol="PCS")
        customer = Customer.objects.create(name="عميل تجريبي مرحلة 1", phone="01011112222")
        warehouse = Warehouse.objects.create(name="مخزن تجريبي رئيسي", code="WH-T1")
        product = Product.objects.create(
            name="منتج مواصفات خاصة",
            sku="PRD-SPEC-01",
            category=category,
            unit=unit,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            created_by=user,
        )

        # 1. إنشاء عرض سعر وتأكيد تفاصيل البند وحالة الهيدر
        quotation = Quotation.objects.create(
            number="QT-T1-001",
            customer=customer,
            warehouse=warehouse,
            show_line_details=True,
            created_by=user,
        )
        q_item = QuotationItem.objects.create(
            quotation=quotation,
            product=product,
            quantity=Decimal("5.00"),
            unit_price=Decimal("150.00"),
            details="مواصفات توريد خاصة:\n- خامة ستانلس 304\n- تشطيب مطفي",
        )
        q_item.refresh_from_db()
        quotation.refresh_from_db()
        assert quotation.show_line_details is True
        assert "ستانلس 304" in q_item.details

        # 2. إنشاء فاتورة مبيعات مع تفاصيل
        sale = Sale.objects.create(
            number="INV-T1-001",
            date=timezone.now().date(),
            customer=customer,
            warehouse=warehouse,
            subtotal=Decimal("750.00"),
            total=Decimal("750.00"),
            show_line_details=True,
            created_by=user,
        )
        s_item = SaleItem.objects.create(
            sale=sale,
            product=product,
            quantity=Decimal("5.00"),
            unit_price=Decimal("150.00"),
            details="تفاصيل التعبئة:\nكرتون مقوى 5 طبقات",
        )
        s_item.refresh_from_db()
        sale.refresh_from_db()
        assert sale.show_line_details is True
        assert "كرتون مقوى" in s_item.details

        # 3. إنشاء فاتورة مشتريات مع تفاصيل
        supplier = Supplier.objects.create(name="مورد معتمد مرحلة 1", phone="01222223333")
        purchase = Purchase.objects.create(
            number="PUR-T1-001",
            date=timezone.now().date(),
            supplier=supplier,
            warehouse=warehouse,
            subtotal=Decimal("500.00"),
            total=Decimal("500.00"),
            show_line_details=False,
            created_by=user,
        )
        p_item = PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            quantity=5,
            unit_price=Decimal("100.00"),
            details="شهادة منشأ أصلية مطلوبة مع الشحنة",
        )
        p_item.refresh_from_db()
        purchase.refresh_from_db()
        assert purchase.show_line_details is False
        assert "شهادة منشأ" in p_item.details
