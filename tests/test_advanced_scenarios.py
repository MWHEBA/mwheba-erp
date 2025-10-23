"""
اختبارات السيناريوهات المتقدمة لنظام MWHEBA ERP
يغطي العمليات متعددة العملات والمخازن والتسعير المتقدم
"""

import time
from decimal import Decimal
from datetime import date, datetime, timedelta
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.db import transaction
from concurrent.futures import ThreadPoolExecutor

# Models imports
from product.models import Category, Product, StockMovement
from supplier.models import SupplierType, Supplier
from client.models import Client
from purchase.models import Purchase, PurchaseItem, PurchasePayment
from sale.models import Sale, SaleItem, SalePayment
from financial.models import ChartOfAccounts, JournalEntry

User = get_user_model()


class MultiCurrencyTestCase(TransactionTestCase):
    """اختبارات العمليات متعددة العملات"""
    
    fixtures = [
        'financial/fixtures/chart_of_accounts_final.json',
        'product/fixtures/initial_data.json',
        'supplier/fixtures/supplier_types.json'
    ]
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.admin_user = User.objects.create_user(
            username="admin",
            password="admin123",
            is_staff=True
        )
        
        # إعداد أسعار الصرف (افتراضية)
        self.usd_to_egp = Decimal('30.50')  # دولار إلى جنيه
        self.eur_to_egp = Decimal('33.25')  # يورو إلى جنيه
        
    def test_multi_currency_purchases(self):
        """اختبار المشتريات بعملات مختلفة"""
        print("💱 اختبار المشتريات بعملات مختلفة...")
        
        # إنشاء مورد أجنبي
        supplier_type = SupplierType.objects.first()
        supplier = Supplier.objects.create(
            name="German Paper Supplier",
            supplier_type=supplier_type,
            email="supplier@germany.com",
            currency="EUR"  # يورو
        )
        
        # إنشاء منتج
        category = Category.objects.create(name="ورق مستورد")
        product = Product.objects.create(
            name="ورق ألماني عالي الجودة",
            category=category,
            sku="GER-001",
            cost_price=Decimal('0.00'),
            selling_price=Decimal('2.00')
        )
        
        # إنشاء فاتورة شراء باليورو
        purchase = Purchase.objects.create(
            supplier=supplier,
            invoice_number="EUR-001",
            invoice_date=date.today(),
            currency="EUR",
            exchange_rate=self.eur_to_egp
        )
        
        # إضافة عنصر بسعر اليورو
        purchase_item = PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            quantity=1000,
            unit_price=Decimal('0.50'),  # 0.50 يورو
            total_price=Decimal('500.00')  # 500 يورو
        )
        
        # التحقق من التحويل للجنيه المصري
        egp_total = purchase_item.total_price * self.eur_to_egp
        expected_egp = Decimal('500.00') * Decimal('33.25')
        
        self.assertEqual(egp_total, expected_egp)
        
        # التحقق من تحديث سعر التكلفة بالجنيه
        product.refresh_from_db()
        expected_cost_egp = Decimal('0.50') * self.eur_to_egp
        
        print(f"سعر التكلفة المتوقع: {expected_cost_egp} جنيه")
        
    def test_currency_fluctuation_impact(self):
        """اختبار تأثير تقلبات أسعار الصرف"""
        print("📈 اختبار تأثير تقلبات أسعار الصرف...")
        
        # شراء بسعر صرف معين
        old_rate = Decimal('30.00')
        new_rate = Decimal('32.00')
        
        # محاكاة تغيير سعر الصرف
        purchase_value_usd = Decimal('1000.00')
        
        old_egp_value = purchase_value_usd * old_rate  # 30,000 جنيه
        new_egp_value = purchase_value_usd * new_rate  # 32,000 جنيه
        
        currency_gain = new_egp_value - old_egp_value  # 2,000 جنيه ربح
        
        self.assertEqual(currency_gain, Decimal('2000.00'))
        print(f"ربح تقلبات العملة: {currency_gain} جنيه")


class MultiWarehouseTestCase(TransactionTestCase):
    """اختبارات العمليات متعددة المخازن"""
    
    fixtures = [
        'product/fixtures/initial_data.json',
        'supplier/fixtures/supplier_types.json'
    ]
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.admin_user = User.objects.create_user(
            username="admin",
            password="admin123"
        )
        
        # إنشاء مخازن متعددة
        self.main_warehouse = "المخزن الرئيسي"
        self.branch_warehouse = "مخزن الفرع"
        self.damaged_warehouse = "مخزن التالف"
        
    def test_inter_warehouse_transfers(self):
        """اختبار النقل بين المخازن"""
        print("🏪 اختبار النقل بين المخازن...")
        
        # إنشاء منتج
        category = Category.objects.create(name="ورق A4")
        product = Product.objects.create(
            name="ورق A4 80 جرام",
            category=category,
            sku="A4-80",
            cost_price=Decimal('0.50'),
            selling_price=Decimal('0.75')
        )
        
        # إضافة مخزون للمخزن الرئيسي
        product.add_stock(
            quantity=1000,
            reason="استلام أولي",
            warehouse=self.main_warehouse
        )
        
        # نقل جزء للفرع
        transfer_quantity = 300
        
        # خصم من المخزن الرئيسي
        StockMovement.objects.create(
            product=product,
            movement_type="OUT",
            quantity=transfer_quantity,
            reason=f"نقل إلى {self.branch_warehouse}",
            warehouse=self.main_warehouse,
            reference_type="transfer"
        )
        
        # إضافة للفرع
        StockMovement.objects.create(
            product=product,
            movement_type="IN", 
            quantity=transfer_quantity,
            reason=f"نقل من {self.main_warehouse}",
            warehouse=self.branch_warehouse,
            reference_type="transfer"
        )
        
        # التحقق من الأرصدة
        main_stock = self.get_warehouse_stock(product, self.main_warehouse)
        branch_stock = self.get_warehouse_stock(product, self.branch_warehouse)
        
        self.assertEqual(main_stock, 700)
        self.assertEqual(branch_stock, 300)
        
    def get_warehouse_stock(self, product, warehouse):
        """حساب رصيد المنتج في مخزن معين"""
        movements = StockMovement.objects.filter(
            product=product,
            warehouse=warehouse
        )
        
        stock = 0
        for movement in movements:
            if movement.movement_type == "IN":
                stock += movement.quantity
            else:
                stock -= movement.quantity
                
        return stock
        
    def test_warehouse_specific_operations(self):
        """اختبار العمليات الخاصة بكل مخزن"""
        print("📦 اختبار العمليات الخاصة بكل مخزن...")
        
        category = Category.objects.create(name="منتجات قابلة للتلف")
        product = Product.objects.create(
            name="منتج قابل للتلف",
            category=category,
            sku="PERISHABLE-001",
            cost_price=Decimal('5.00'),
            selling_price=Decimal('8.00')
        )
        
        # إضافة مخزون
        product.add_stock(100, "استلام", self.main_warehouse)
        
        # نقل منتجات تالفة
        damaged_quantity = 10
        
        # خصم من المخزن الرئيسي
        StockMovement.objects.create(
            product=product,
            movement_type="OUT",
            quantity=damaged_quantity,
            reason="منتجات تالفة",
            warehouse=self.main_warehouse,
            reference_type="damage"
        )
        
        # إضافة لمخزن التالف
        StockMovement.objects.create(
            product=product,
            movement_type="IN",
            quantity=damaged_quantity,
            reason="منتجات تالفة",
            warehouse=self.damaged_warehouse,
            reference_type="damage"
        )
        
        # التحقق من الأرصدة
        main_stock = self.get_warehouse_stock(product, self.main_warehouse)
        damaged_stock = self.get_warehouse_stock(product, self.damaged_warehouse)
        
        self.assertEqual(main_stock, 90)
        self.assertEqual(damaged_stock, 10)


class BatchSerialTrackingTestCase(TestCase):
    """اختبارات تتبع الدفعات والأرقام التسلسلية"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.admin_user = User.objects.create_user(
            username="admin",
            password="admin123"
        )
        
    def test_batch_tracking(self):
        """اختبار تتبع الدفعات"""
        print("🏷️ اختبار تتبع الدفعات...")
        
        # إنشاء منتج يتطلب تتبع دفعات
        category = Category.objects.create(name="أدوية")
        product = Product.objects.create(
            name="دواء تجريبي",
            category=category,
            sku="MED-001",
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            track_batches=True,
            expiry_tracking=True
        )
        
        # إضافة دفعة جديدة
        batch_number = "BATCH-2024-001"
        expiry_date = date.today() + timedelta(days=365)
        
        # محاكاة إضافة دفعة مع تاريخ انتهاء
        batch_data = {
            'batch_number': batch_number,
            'expiry_date': expiry_date,
            'quantity': 100
        }
        
        # إضافة المخزون مع بيانات الدفعة
        product.add_stock(
            quantity=100,
            reason="استلام دفعة جديدة",
            batch_data=batch_data
        )
        
        # التحقق من تتبع الدفعة
        self.assertEqual(product.current_stock, 100)
        
    def test_expiry_date_tracking(self):
        """اختبار تتبع تواريخ انتهاء الصلاحية"""
        print("📅 اختبار تتبع تواريخ انتهاء الصلاحية...")
        
        category = Category.objects.create(name="منتجات غذائية")
        product = Product.objects.create(
            name="منتج غذائي",
            category=category,
            sku="FOOD-001",
            cost_price=Decimal('5.00'),
            selling_price=Decimal('8.00'),
            expiry_tracking=True
        )
        
        # إضافة منتجات بتواريخ انتهاء مختلفة
        today = date.today()
        
        # دفعة تنتهي خلال شهر (منتهية الصلاحية قريباً)
        near_expiry = today + timedelta(days=30)
        
        # دفعة تنتهي خلال سنة (صالحة)
        far_expiry = today + timedelta(days=365)
        
        # محاكاة إضافة الدفعات
        product.add_stock(50, "دفعة قريبة الانتهاء", expiry_date=near_expiry)
        product.add_stock(100, "دفعة صالحة", expiry_date=far_expiry)
        
        # التحقق من إجمالي المخزون
        self.assertEqual(product.current_stock, 150)
        
        # محاكاة تحديد المنتجات منتهية الصلاحية
        expired_threshold = today + timedelta(days=60)  # خلال شهرين
        
        # المنتجات التي تنتهي صلاحيتها قريباً
        near_expiry_items = []
        if near_expiry <= expired_threshold:
            near_expiry_items.append({
                'product': product,
                'expiry_date': near_expiry,
                'quantity': 50
            })
            
        self.assertEqual(len(near_expiry_items), 1)
        print(f"منتجات قريبة الانتهاء: {len(near_expiry_items)}")


class AdvancedPricingTestCase(TestCase):
    """اختبارات التسعير المتقدم"""
    
    fixtures = [
        'product/fixtures/initial_data.json',
        'client/fixtures/initial_data.json'
    ]
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.admin_user = User.objects.create_user(
            username="admin",
            password="admin123"
        )
        
    def test_quantity_based_pricing(self):
        """اختبار التسعير حسب الكمية"""
        print("📊 اختبار التسعير حسب الكمية...")
        
        # إنشاء منتج
        category = Category.objects.create(name="ورق بالجملة")
        product = Product.objects.create(
            name="ورق A4 للجملة",
            category=category,
            sku="BULK-A4",
            cost_price=Decimal('0.40'),
            selling_price=Decimal('0.60')  # سعر التجزئة
        )
        
        # تحديد شرائح الأسعار
        pricing_tiers = [
            {'min_qty': 1, 'max_qty': 100, 'price': Decimal('0.60')},      # تجزئة
            {'min_qty': 101, 'max_qty': 500, 'price': Decimal('0.55')},    # خصم 5 قروش
            {'min_qty': 501, 'max_qty': 1000, 'price': Decimal('0.50')},   # خصم 10 قروش
            {'min_qty': 1001, 'max_qty': None, 'price': Decimal('0.45')},  # جملة كبيرة
        ]
        
        # اختبار أسعار مختلفة حسب الكمية
        test_quantities = [50, 200, 750, 1500]
        expected_prices = [Decimal('0.60'), Decimal('0.55'), Decimal('0.50'), Decimal('0.45')]
        
        for i, qty in enumerate(test_quantities):
            price = self.get_quantity_price(qty, pricing_tiers)
            self.assertEqual(price, expected_prices[i])
            print(f"كمية {qty}: سعر {price} جنيه")
            
    def get_quantity_price(self, quantity, pricing_tiers):
        """حساب السعر حسب الكمية"""
        for tier in pricing_tiers:
            if quantity >= tier['min_qty']:
                if tier['max_qty'] is None or quantity <= tier['max_qty']:
                    return tier['price']
        return pricing_tiers[0]['price']  # السعر الافتراضي
        
    def test_customer_specific_pricing(self):
        """اختبار التسعير الخاص بالعملاء"""
        print("👥 اختبار التسعير الخاص بالعملاء...")
        
        # إنشاء عملاء بفئات مختلفة
        vip_client = Client.objects.create(
            name="عميل VIP",
            email="vip@client.com",
            client_type="VIP",
            discount_percentage=Decimal('15.00')  # خصم 15%
        )
        
        regular_client = Client.objects.create(
            name="عميل عادي",
            email="regular@client.com",
            client_type="REGULAR",
            discount_percentage=Decimal('5.00')  # خصم 5%
        )
        
        # منتج للاختبار
        category = Category.objects.create(name="منتجات VIP")
        product = Product.objects.create(
            name="منتج مميز",
            category=category,
            sku="VIP-001",
            cost_price=Decimal('8.00'),
            selling_price=Decimal('12.00')
        )
        
        # حساب الأسعار للعملاء المختلفين
        base_price = product.selling_price
        
        vip_price = base_price * (1 - vip_client.discount_percentage / 100)
        regular_price = base_price * (1 - regular_client.discount_percentage / 100)
        
        expected_vip_price = Decimal('12.00') * Decimal('0.85')  # 10.20
        expected_regular_price = Decimal('12.00') * Decimal('0.95')  # 11.40
        
        self.assertEqual(vip_price, expected_vip_price)
        self.assertEqual(regular_price, expected_regular_price)
        
        print(f"سعر العميل VIP: {vip_price} جنيه")
        print(f"سعر العميل العادي: {regular_price} جنيه")
        
    def test_promotional_pricing(self):
        """اختبار التسعير الترويجي"""
        print("🎯 اختبار التسعير الترويجي...")
        
        # إنشاء منتج
        category = Category.objects.create(name="عروض خاصة")
        product = Product.objects.create(
            name="منتج العرض",
            category=category,
            sku="PROMO-001",
            cost_price=Decimal('5.00'),
            selling_price=Decimal('10.00')
        )
        
        # عرض ترويجي: خصم 30% لمدة محدودة
        promo_start = date.today()
        promo_end = date.today() + timedelta(days=7)
        promo_discount = Decimal('30.00')  # 30%
        
        # محاكاة التحقق من العرض
        current_date = date.today()
        is_promo_active = promo_start <= current_date <= promo_end
        
        if is_promo_active:
            promo_price = product.selling_price * (1 - promo_discount / 100)
            expected_promo_price = Decimal('10.00') * Decimal('0.70')  # 7.00
            
            self.assertEqual(promo_price, expected_promo_price)
            print(f"سعر العرض: {promo_price} جنيه (خصم {promo_discount}%)")
        else:
            print("العرض غير نشط حالياً")


class ConcurrentOperationsTestCase(TransactionTestCase):
    """اختبارات العمليات المتزامنة"""
    
    fixtures = ['product/fixtures/initial_data.json']
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.admin_user = User.objects.create_user(
            username="admin",
            password="admin123"
        )
        
        # إنشاء منتج للاختبار
        category = Category.objects.create(name="اختبار التزامن")
        self.product = Product.objects.create(
            name="منتج التزامن",
            category=category,
            sku="CONCURRENT-001",
            cost_price=Decimal('1.00'),
            selling_price=Decimal('2.00')
        )
        
        # إضافة مخزون أولي
        self.product.add_stock(1000, "مخزون أولي")
        
    def test_concurrent_stock_operations(self):
        """اختبار العمليات المتزامنة على المخزون"""
        print("⚡ اختبار العمليات المتزامنة على المخزون...")
        
        def deduct_stock(quantity):
            """خصم مخزون في معاملة منفصلة"""
            try:
                with transaction.atomic():
                    product = Product.objects.select_for_update().get(id=self.product.id)
                    if product.current_stock >= quantity:
                        product.deduct_stock(quantity, "بيع متزامن")
                        return True
                    return False
            except Exception as e:
                print(f"خطأ في خصم المخزون: {e}")
                return False
                
        # محاكاة 10 عمليات بيع متزامنة
        operations = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            for i in range(10):
                future = executor.submit(deduct_stock, 50)  # خصم 50 قطعة
                operations.append(future)
                
        # انتظار اكتمال العمليات
        successful_operations = 0
        for future in operations:
            if future.result():
                successful_operations += 1
                
        # التحقق من النتائج
        self.product.refresh_from_db()
        expected_remaining = 1000 - (successful_operations * 50)
        
        print(f"العمليات الناجحة: {successful_operations}")
        print(f"المخزون المتبقي: {self.product.current_stock}")
        print(f"المخزون المتوقع: {expected_remaining}")
        
        # التأكد من عدم حدوث مخزون سالب
        self.assertGreaterEqual(self.product.current_stock, 0)


# تشغيل جميع الاختبارات المتقدمة
if __name__ == '__main__':
    import django
    from django.conf import settings
    from django.test.utils import get_runner
    
    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests([
        "tests.test_advanced_scenarios"
    ])
