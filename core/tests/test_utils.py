from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from core.utils import (
    generate_invoice_number, calculate_total, validate_phone_number,
    format_currency, get_financial_period, get_date_range,
    format_date, format_number, calculate_due_date, is_arabic_text,
    get_default_currency, get_tax_rate, get_model_permissions, create_user_group,
    generate_report
)
from decimal import Decimal
from datetime import date, timedelta
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

User = get_user_model()

class UtilsTestCase(TestCase):
    """
    اختبارات الأدوات المساعدة والوظائف العامة في النظام
    """
    def setUp(self):
        """
        إعداد البيانات المطلوبة للاختبارات
        """
        self.user = User.objects.create_user(
            username='utilsuser',
            email='utils@example.com',
            password='utils123'
        )
        
        # تواريخ للاختبارات
        self.today = date.today()
        self.yesterday = self.today - timedelta(days=1)
        self.last_week = self.today - timedelta(days=7)
        self.last_month = self.today - timedelta(days=30)
    
    def test_generate_invoice_number(self):
        """
        اختبار توليد رقم فاتورة فريد
        """
        # توليد رقم فاتورة للمبيعات
        invoice_sales_1 = generate_invoice_number('sales')
        invoice_sales_2 = generate_invoice_number('sales')
        
        # التحقق من أن الرقمين مختلفان
        self.assertNotEqual(invoice_sales_1, invoice_sales_2)
        
        # التحقق من أن الرقم يبدأ بالبادئة الصحيحة
        self.assertTrue(invoice_sales_1.startswith('INV-'))
        
        # توليد رقم فاتورة للمشتريات
        invoice_purchase = generate_invoice_number('purchase')
        
        # التحقق من أن الرقم يبدأ بالبادئة الصحيحة
        self.assertTrue(invoice_purchase.startswith('PO-'))
        
        # التحقق من طول الرقم
        self.assertEqual(len(invoice_sales_1), 12)  # مثال: INV-20230615-001
    
    def test_calculate_total(self):
        """
        اختبار حساب المجموع
        """
        # قائمة عناصر مع سعر وكمية
        items = [
            {'price': Decimal('100.00'), 'quantity': 2},
            {'price': Decimal('150.00'), 'quantity': 3},
            {'price': Decimal('200.00'), 'quantity': 1}
        ]
        
        # حساب المجموع
        total = calculate_total(items)
        
        # المجموع المتوقع: (100 * 2) + (150 * 3) + (200 * 1) = 200 + 450 + 200 = 850
        expected_total = Decimal('850.00')
        self.assertEqual(total, expected_total)
        
        # اختبار حساب المجموع مع خصم
        total_with_discount = calculate_total(items, discount=Decimal('50.00'))
        
        # المجموع المتوقع مع الخصم: 850 - 50 = 800
        expected_with_discount = Decimal('800.00')
        self.assertEqual(total_with_discount, expected_with_discount)
        
        # اختبار حساب المجموع مع ضريبة
        total_with_tax = calculate_total(items, tax_rate=Decimal('0.15'))
        
        # المجموع المتوقع مع الضريبة: 850 + (850 * 0.15) = 850 + 127.5 = 977.5
        expected_with_tax = Decimal('977.50')
        self.assertEqual(total_with_tax, expected_with_tax)
        
        # اختبار حساب المجموع مع خصم وضريبة
        total_with_discount_and_tax = calculate_total(
            items, discount=Decimal('50.00'), tax_rate=Decimal('0.15')
        )
        
        # المجموع المتوقع مع الخصم والضريبة: (850 - 50) + ((850 - 50) * 0.15) = 800 + 120 = 920
        expected_with_discount_and_tax = Decimal('920.00')
        self.assertEqual(total_with_discount_and_tax, expected_with_discount_and_tax)
    
    def test_validate_phone_number(self):
        """
        اختبار التحقق من صحة رقم الهاتف
        """
        # أرقام هاتف صحيحة
        valid_numbers = [
            '01234567890',     # رقم مصري 11 رقم
            '+201234567890',   # رقم مصري مع كود الدولة
            '0123456789',      # رقم 10 أرقام
            '0123-456-789',    # رقم مع واصلات
            '(0123) 456 789',  # رقم مع أقواس ومسافات
        ]
        
        for number in valid_numbers:
            # يجب أن يمر التحقق بدون أخطاء
            try:
                validate_phone_number(number)
            except ValidationError:
                self.fail(f"ValidationError raised for valid phone number: {number}")
        
        # أرقام هاتف غير صحيحة
        invalid_numbers = [
            '123',             # رقم قصير جداً
            'abc1234567890',   # يحتوي على حروف
            '+9876543210abcd', # يحتوي على حروف
            '9' * 20,          # رقم طويل جداً
        ]
        
        for number in invalid_numbers:
            # يجب أن يرفع خطأ التحقق
            with self.assertRaises(ValidationError):
                validate_phone_number(number)
    
    def test_format_currency(self):
        """
        اختبار تنسيق المبالغ المالية
        """
        # اختبار تنسيق مبلغ عشري
        amount = Decimal('1234.56')
        formatted = format_currency(amount)
        self.assertEqual(formatted, '1,234.56 جنيه')
        
        # اختبار تنسيق مبلغ صحيح
        amount = Decimal('1000.00')
        formatted = format_currency(amount)
        self.assertEqual(formatted, '1,000.00 جنيه')
        
        # اختبار تنسيق مبلغ مع عملة مختلفة
        amount = Decimal('500.75')
        formatted = format_currency(amount, currency='دولار')
        self.assertEqual(formatted, '500.75 دولار')
        
        # اختبار تنسيق مبلغ بدون كسور
        amount = Decimal('750')
        formatted = format_currency(amount, decimal_places=0)
        self.assertEqual(formatted, '750 جنيه')
        
        # اختبار تنسيق مبلغ سالب
        amount = Decimal('-250.50')
        formatted = format_currency(amount)
        self.assertEqual(formatted, '-250.50 جنيه')
    
    def test_get_financial_period(self):
        """
        اختبار الحصول على الفترة المالية
        """
        # اختبار الفترة اليومية
        daily = get_financial_period('daily', self.today)
        self.assertEqual(daily['start_date'], self.today)
        self.assertEqual(daily['end_date'], self.today)
        self.assertEqual(daily['title'], f'تقرير يوم {self.today.strftime("%Y-%m-%d")}')
        
        # اختبار الفترة الأسبوعية
        weekly = get_financial_period('weekly', self.today)
        # الأسبوع يبدأ عادة من يوم الاثنين
        # لذلك نحتاج للتأكد من أن تاريخ البداية هو أول يوم في الأسبوع
        # وتاريخ النهاية هو آخر يوم في الأسبوع
        self.assertLessEqual((weekly['end_date'] - weekly['start_date']).days, 6)
        self.assertGreaterEqual(weekly['end_date'], self.today)
        
        # اختبار الفترة الشهرية
        monthly = get_financial_period('monthly', self.today)
        self.assertEqual(monthly['start_date'].day, 1)
        self.assertEqual(monthly['start_date'].month, self.today.month)
        self.assertEqual(monthly['start_date'].year, self.today.year)
        
        # اختبار الفترة السنوية
        yearly = get_financial_period('yearly', self.today)
        self.assertEqual(yearly['start_date'].day, 1)
        self.assertEqual(yearly['start_date'].month, 1)
        self.assertEqual(yearly['start_date'].year, self.today.year)
        self.assertEqual(yearly['end_date'].month, 12)
        self.assertEqual(yearly['end_date'].day, 31)
    
    def test_get_date_range(self):
        """
        اختبار الحصول على نطاق تاريخي
        """
        # اختبار نطاق من تاريخ إلى تاريخ
        start_date = date(2023, 1, 1)
        end_date = date(2023, 1, 31)
        
        date_range = get_date_range(start_date, end_date)
        
        # يجب أن يكون عدد الأيام في النطاق هو 31 يوم
        self.assertEqual(len(date_range), 31)
        self.assertEqual(date_range[0], start_date)
        self.assertEqual(date_range[-1], end_date)
        
        # اختبار نطاق لشهر واحد
        month_range = get_date_range(month=1, year=2023)
        
        # يجب أن يكون عدد الأيام في النطاق هو 31 يوم (يناير)
        self.assertEqual(len(month_range), 31)
        self.assertEqual(month_range[0], date(2023, 1, 1))
        self.assertEqual(month_range[-1], date(2023, 1, 31))
        
        # اختبار نطاق لسنة كاملة
        year_range = get_date_range(year=2023)
        
        # يجب أن يكون عدد الأيام في النطاق هو 365 يوم (2023 ليست سنة كبيسة)
        self.assertEqual(len(year_range), 365)
        self.assertEqual(year_range[0], date(2023, 1, 1))
        self.assertEqual(year_range[-1], date(2023, 12, 31))
        
        # اختبار نطاق للأسبوع الحالي
        week_range = get_date_range(week=True, reference_date=self.today)
        
        # يجب أن يكون عدد الأيام في النطاق هو 7 أيام
        self.assertEqual(len(week_range), 7)
        
        # اختبار الحصول على أيام الأسبوع بناءً على تاريخ مرجعي
        # (بغض النظر عن اليوم الأول في الأسبوع حسب الإعدادات)
        self.assertLessEqual((week_range[-1] - week_range[0]).days, 6)

class FormatFunctionsTest(TestCase):
    """
    اختبارات وظائف التنسيق
    """
    
    def test_format_currency(self):
        """
        اختبار تنسيق العملات
        """
        # اختبار تنسيق العملة المصرية
        self.assertEqual(format_currency(1000, 'EGP'), '1,000.00 ج.م')
        self.assertEqual(format_currency(1000.5, 'EGP'), '1,000.50 ج.م')
        self.assertEqual(format_currency(Decimal('1000.5'), 'EGP'), '1,000.50 ج.م')
        
        # اختبار تنسيق الدولار الأمريكي
        self.assertEqual(format_currency(1000, 'USD'), '$1,000.00')
        self.assertEqual(format_currency(1000.5, 'USD'), '$1,000.50')
        
        # اختبار تنسيق بدون رمز العملة
        self.assertEqual(format_currency(1000, 'EGP', show_symbol=False), '1,000.00')
        
        # اختبار مع عدد مختلف من المنازل العشرية
        self.assertEqual(format_currency(1000, 'EGP', decimal_places=0), '1,000 ج.م')
        self.assertEqual(format_currency(1000.567, 'EGP', decimal_places=3), '1,000.567 ج.م')
    
    def test_format_number(self):
        """
        اختبار تنسيق الأرقام
        """
        # اختبار تنسيق الأرقام العادية
        self.assertEqual(format_number(1000), '1,000')
        self.assertEqual(format_number(1000.5), '1,000.5')
        self.assertEqual(format_number(Decimal('1000.5')), '1,000.5')
        
        # اختبار مع عدد محدد من المنازل العشرية
        self.assertEqual(format_number(1000, decimal_places=0), '1,000')
        self.assertEqual(format_number(1000.5, decimal_places=0), '1,001')  # تقريب لأقرب رقم صحيح
        self.assertEqual(format_number(1000.5, decimal_places=2), '1,000.50')
        self.assertEqual(format_number(1000.567, decimal_places=2), '1,000.57')  # تقريب لأقرب منزلتين عشريتين
        
        # اختبار مع تنسيقات مختلفة
        self.assertEqual(format_number(1000, thousand_separator=' '), '1 000')
        self.assertEqual(format_number(1000.5, decimal_separator=','), '1,000,5')
        self.assertEqual(format_number(1000.5, thousand_separator=' ', decimal_separator=','), '1 000,5')
    
    def test_format_date(self):
        """
        اختبار تنسيق التواريخ
        """
        # إنشاء تاريخ للاختبار
        test_date = date(2023, 12, 31)
        
        # اختبار تنسيق التاريخ العادي
        self.assertEqual(format_date(test_date), '2023-12-31')
        
        # اختبار أنماط التنسيق المختلفة
        self.assertEqual(format_date(test_date, 'short'), '31/12/2023')
        self.assertEqual(format_date(test_date, 'long'), '31 ديسمبر 2023')
        
        # اختبار إذا كانت الدالة تتعامل مع كائنات datetime
        test_datetime = date(2023, 12, 31)
        self.assertEqual(format_date(test_datetime), '2023-12-31')
        
        # اختبار إذا كانت الدالة تتعامل مع القيم العددية
        self.assertRaises(TypeError, format_date, 123)

class CalculationFunctionsTest(TestCase):
    """
    اختبارات وظائف الحساب
    """
    
    def test_calculate_total(self):
        """
        اختبار حساب المجموع
        """
        # إنشاء قائمة عناصر للاختبار
        items = [
            {'price': 100, 'quantity': 2},  # 200
            {'price': 50, 'quantity': 3},   # 150
            {'price': 75, 'quantity': 1}    # 75
        ]
        
        # اختبار حساب المجموع الإجمالي
        self.assertEqual(calculate_total(items), 425)
        
        # اختبار حساب المجموع مع خصم
        self.assertEqual(calculate_total(items, discount=25), 400)  # 425 - 25 = 400
        
        # اختبار حساب المجموع مع ضريبة
        self.assertEqual(calculate_total(items, tax_rate=10), 467.5)  # 425 + (425 * 0.1) = 467.5
        
        # اختبار حساب المجموع مع خصم وضريبة
        self.assertEqual(calculate_total(items, discount=25, tax_rate=10), 440)  # (425 - 25) + ((425 - 25) * 0.1) = 440
        
        # اختبار مع قيم عشرية
        items_decimal = [
            {'price': Decimal('100.50'), 'quantity': 2},  # 201
            {'price': Decimal('50.25'), 'quantity': 3},   # 150.75
            {'price': Decimal('75.75'), 'quantity': 1}    # 75.75
        ]
        self.assertEqual(calculate_total(items_decimal), Decimal('427.50'))
    
    def test_calculate_due_date(self):
        """
        اختبار حساب تاريخ الاستحقاق
        """
        # تعيين تاريخ البداية
        start_date = date(2023, 1, 15)
        
        # اختبار حساب تاريخ الاستحقاق بعدد أيام محدد
        self.assertEqual(calculate_due_date(start_date, 10), date(2023, 1, 25))
        
        # اختبار حساب تاريخ الاستحقاق بعدد أيام سالب (يجب أن يرجع التاريخ الأصلي)
        self.assertEqual(calculate_due_date(start_date, -5), start_date)
        
        # اختبار حساب تاريخ الاستحقاق عندما يكون التاريخ هو None
        self.assertIsNone(calculate_due_date(None, 10))
        
        # اختبار حساب تاريخ الاستحقاق مع كائن datetime
        start_datetime = date(2023, 1, 15)
        self.assertEqual(calculate_due_date(start_datetime, 10), date(2023, 1, 25))

class TextUtilsTest(TestCase):
    """
    اختبارات وظائف معالجة النصوص
    """
    
    def test_is_arabic_text(self):
        """
        اختبار التحقق من النص العربي
        """
        # اختبار نص عربي كامل
        self.assertTrue(is_arabic_text('مرحبا بالعالم'))
        
        # اختبار نص غير عربي
        self.assertFalse(is_arabic_text('Hello World'))
        
        # اختبار نص مختلط (عربي وإنجليزي)
        self.assertFalse(is_arabic_text('مرحبا World'))
        
        # اختبار نص عربي مع أرقام وعلامات ترقيم
        self.assertTrue(is_arabic_text('مرحبا 123!'))
        
        # اختبار نص فارغ
        self.assertFalse(is_arabic_text(''))
        
        # اختبار مع كائن None
        self.assertFalse(is_arabic_text(None))

class GeneratorFunctionsTest(TestCase):
    """
    اختبارات وظائف التوليد
    """
    
    def test_generate_invoice_number(self):
        """
        اختبار توليد رقم الفاتورة
        """
        # اختبار توليد رقم الفاتورة بالإعدادات الافتراضية
        invoice_number = generate_invoice_number()
        self.assertIsNotNone(invoice_number)
        
        # التحقق من أن رقم الفاتورة يحتوي على السنة الحالية
        current_year = str(timezone.now().year)
        self.assertIn(current_year, invoice_number)
        
        # اختبار توليد رقم الفاتورة مع بادئة مخصصة
        invoice_number = generate_invoice_number(prefix='INV')
        self.assertTrue(invoice_number.startswith('INV'))
        
        # اختبار توليد رقم الفاتورة مع طول محدد
        invoice_number = generate_invoice_number(length=8)
        # التحقق من الطول الإجمالي (البادئة + الفاصل + الرقم)
        # ملاحظة: الطول سيكون أكبر بسبب البادئة والفاصل
        self.assertTrue(len(invoice_number) >= 8)

class ConfigFunctionsTest(TestCase):
    """
    اختبارات وظائف التكوين
    """
    
    def test_get_default_currency(self):
        """
        اختبار استرجاع العملة الافتراضية
        """
        # اختبار استرجاع العملة الافتراضية
        currency = get_default_currency()
        self.assertIsNotNone(currency)
        
        # التحقق من أن العملة الافتراضية نص غير فارغ
        self.assertTrue(isinstance(currency, str))
        self.assertTrue(len(currency) > 0)
    
    def test_get_tax_rate(self):
        """
        اختبار استرجاع معدل الضريبة
        """
        # اختبار استرجاع معدل الضريبة
        tax_rate = get_tax_rate()
        self.assertIsNotNone(tax_rate)
        
        # التحقق من أن معدل الضريبة رقم غير سالب
        self.assertTrue(isinstance(tax_rate, (int, float, Decimal)))
        self.assertTrue(tax_rate >= 0)
        
        # التحقق من أن معدل الضريبة أقل من أو يساوي 100%
        self.assertTrue(tax_rate <= 100)

class UtilsTests(TestCase):
    """
    اختبارات للأدوات المساعدة في التطبيق الأساسي
    """
    
    def setUp(self):
        """
        إعداد بيئة الاختبار
        """
        # إنشاء مستخدم للاختبار
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        
        # إنشاء نموذج للاختبار
        self.content_type = ContentType.objects.get_for_model(User)
        
        # إنشاء بعض الأذونات للاختبار
        self.permission1 = Permission.objects.create(
            codename='can_test',
            name='Can Test',
            content_type=self.content_type
        )
        self.permission2 = Permission.objects.create(
            codename='can_test_advanced',
            name='Can Test Advanced',
            content_type=self.content_type
        )

    def test_get_model_permissions(self):
        """
        اختبار الحصول على أذونات النموذج
        """
        # الحصول على أذونات نموذج المستخدم
        permissions = get_model_permissions(User)
        
        # التحقق من أن الأذونات تتضمن الأذونات التي أنشأناها
        self.assertIn(self.permission1, permissions)
        self.assertIn(self.permission2, permissions)
        
        # التحقق من عدد الأذونات (يجب أن يكون هناك 2 على الأقل)
        self.assertGreaterEqual(len(permissions), 2)
        
        # التحقق من أن جميع الأذونات تنتمي إلى نموذج المستخدم
        for perm in permissions:
            self.assertEqual(perm.content_type, self.content_type)

    def test_create_user_group(self):
        """
        اختبار إنشاء مجموعة مستخدمين
        """
        # إنشاء مجموعة مستخدمين جديدة
        group_name = 'Test Group'
        permissions = [self.permission1, self.permission2]
        
        group = create_user_group(group_name, permissions)
        
        # التحقق من إنشاء المجموعة بشكل صحيح
        self.assertEqual(group.name, group_name)
        
        # التحقق من إضافة الأذونات بشكل صحيح
        self.assertEqual(group.permissions.count(), 2)
        self.assertIn(self.permission1, group.permissions.all())
        self.assertIn(self.permission2, group.permissions.all())
        
        # التحقق من عدم إنشاء مجموعة جديدة إذا كانت موجودة بالفعل
        existing_group = create_user_group(group_name, [self.permission1])
        
        # يجب أن تكون هي نفس المجموعة السابقة
        self.assertEqual(existing_group.id, group.id)
        
        # الأذونات لا يجب أن تتغير
        self.assertEqual(existing_group.permissions.count(), 2)

    def test_generate_report(self):
        """
        اختبار توليد التقارير
        """
        # إنشاء بيانات اختبار
        start_date = timezone.now().date() - timedelta(days=10)
        end_date = timezone.now().date()
        
        # تحديد معلمات التقرير
        report_type = 'user_activity'
        filters = {'is_active': True}
        
        # توليد التقرير
        report_data = generate_report(
            model=User,
            report_type=report_type,
            start_date=start_date,
            end_date=end_date,
            filters=filters
        )
        
        # التحقق من استخدام النموذج الصحيح
        self.assertEqual(report_data['model'], 'User')
        
        # التحقق من وجود حقول التقرير المتوقعة
        self.assertIn('data', report_data)
        self.assertIn('metadata', report_data)
        self.assertIn('report_type', report_data['metadata'])
        self.assertEqual(report_data['metadata']['report_type'], report_type)
        
        # التحقق من تاريخ بدء ونهاية التقرير
        self.assertEqual(report_data['metadata']['start_date'], start_date)
        self.assertEqual(report_data['metadata']['end_date'], end_date)
        
        # التحقق من تطبيق المرشحات
        self.assertEqual(report_data['metadata']['filters'], filters) 