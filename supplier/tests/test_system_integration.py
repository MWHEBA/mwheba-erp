"""
اختبارات التكامل النظامي لوظائف الموردين الأساسية
System Integration Tests for Core Supplier Functionality

هذا الملف يحتوي على اختبارات شاملة للتأكد من أن الوظائف الأساسية للموردين
تعمل بشكل صحيح بعد إزالة الفئات المتقدمة والنماذج المعقدة.
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from decimal import Decimal

from supplier.models import Supplier, SupplierType, SupplierTypeSettings

User = get_user_model()


class CoreSupplierFunctionalityTest(TestCase):
    """
    اختبارات الوظائف الأساسية للموردين
    Tests for core supplier functionality preservation
    """
    
    def setUp(self):
        """إعداد البيانات الأساسية للاختبارات"""
        # إنشاء مستخدم للاختبار
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        
        # إنشاء أنواع موردين أساسية للشركة
        self.educational_type = SupplierType.objects.create(
            name='مورد متخصص',
            code='educational',
            description='موردي المواد والمستلزمات المتخصصة',
            icon='fas fa-book',
            color='#007bff'
        )
        
        self.service_type = SupplierType.objects.create(
            name='مقدم خدمات',
            code='service_provider',
            description='مقدمي خدمات الصيانة والتنظيف',
            icon='fas fa-tools',
            color='#ffc107'
        )
        
        # إنشاء مورد أساسي للاختبار
        self.supplier = Supplier.objects.create(
            name='مورد اختبار',
            code='TEST001',
            phone='+201234567890',
            email='supplier@test.com',
            address='عنوان اختبار',
            primary_type=self.educational_type,
            created_by=self.user
        )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_supplier_model_functionality(self):
        """
        اختبار وظائف نموذج المورد الأساسية
        Test core Supplier model functionality
        """
        print("🧪 اختبار وظائف نموذج المورد...")
        
        # التحقق من إنشاء المورد
        self.assertIsNotNone(self.supplier.id)
        self.assertEqual(self.supplier.name, 'مورد اختبار')
        self.assertEqual(self.supplier.code, 'TEST001')
        self.assertTrue(self.supplier.is_active)
        
        # اختبار طريقة __str__
        self.assertEqual(str(self.supplier), 'مورد اختبار')
        
        # اختبار الرصيد الافتراضي
        self.assertEqual(self.supplier.balance, Decimal('0.00'))
        
        # اختبار actual_balance property
        self.assertEqual(self.supplier.actual_balance, Decimal('0.00'))
        
        # اختبار تصنيف المورد
        self.assertEqual(self.supplier.primary_type.code, 'educational')
        self.assertEqual(self.supplier.get_supplier_type_display_ar(), 'مورد متخصص')
        
        print("   ✅ نموذج المورد يعمل بشكل صحيح")
    
    def test_supplier_type_functionality(self):
        """
        اختبار وظائف نموذج نوع المورد
        Test SupplierType model functionality
        """
        print("🧪 اختبار وظائف نموذج نوع المورد...")
        
        # اختبار طريقة __str__
        self.assertEqual(str(self.service_type), 'مقدم خدمات')
        
        print("   ✅ نموذج نوع المورد يعمل بشكل صحيح")
    
    def test_supplier_type_settings_functionality(self):
        """
        اختبار وظائف نموذج إعدادات نوع المورد
        Test SupplierTypeSettings model functionality
        """
        print("🧪 اختبار وظائف نموذج إعدادات نوع المورد...")
        
        # إنشاء إعدادات نوع مورد جديد
        settings = SupplierTypeSettings.objects.create(
            name='مورد طعام',
            code='food_supplier',
            description='موردي الطعام للكافيتيريا',
            icon='fas fa-utensils',
            color='#fd7e14',
            display_order=5,
            created_by=self.user
        )
        
        # التحقق من الإنشاء
        self.assertIsNotNone(settings.id)
        self.assertEqual(settings.name, 'مورد طعام')
        self.assertEqual(settings.code, 'food_supplier')
        self.assertTrue(settings.is_active)
        self.assertFalse(settings.is_system)
        
        # اختبار طريقة __str__
        self.assertEqual(str(settings), 'مورد طعام')
        
        # اختبار خاصية suppliers_count
        self.assertEqual(settings.suppliers_count, 0)
        
        # اختبار خاصية can_delete
        self.assertTrue(settings.can_delete)
        
        print("   ✅ نموذج إعدادات نوع المورد يعمل بشكل صحيح")
    
    def test_supplier_relationships(self):
        """
        اختبار العلاقات بين النماذج
        Test relationships between models
        """
        print("🧪 اختبار العلاقات بين النماذج...")
        
        # اختبار العلاقة بين المورد والنوع الأساسي
        self.assertEqual(self.supplier.primary_type, self.educational_type)
        self.assertEqual(self.supplier.get_primary_type_display(), 'مورد متخصص')
        
        print("   ✅ العلاقات بين النماذج تعمل بشكل صحيح")
    
    def test_supplier_validation(self):
        """
        اختبار التحقق من صحة بيانات المورد
        Test supplier data validation
        """
        print("🧪 اختبار التحقق من صحة بيانات المورد...")
        
        # اختبار تكرار الكود
        general_type = SupplierType.objects.get_or_create(
            code='general',
            defaults={'name': 'مورد عام'}
        )[0]
        with self.assertRaises(IntegrityError):
            Supplier.objects.create(
                name='مورد آخر',
                code='TEST001',  # نفس الكود
                primary_type=general_type
            )
        
        # اختبار إنشاء مورد بكود فريد
        supplier2 = Supplier.objects.create(
            name='مورد ثاني',
            code='TEST002',
            primary_type=self.service_type
        )
        
        self.assertIsNotNone(supplier2.id)
        self.assertEqual(supplier2.code, 'TEST002')
        
        print("   ✅ التحقق من صحة البيانات يعمل بشكل صحيح")
    
    def test_supplier_company_specific_fields(self):
        """
        اختبار الحقول الخاصة بالشركات
        Test company-specific supplier fields
        """
        print("🧪 اختبار الحقول الخاصة بالشركات...")
        
        # إنشاء مورد متخصص
        edu_supplier = Supplier.objects.create(
            name='مكتبة المعرفة',
            code='EDU001',
            primary_type=self.educational_type
        )
        
        # اختبار وظائف المورد المتخصص
        self.assertTrue(edu_supplier.is_educational_supplier())
        
        # إنشاء مقدم خدمات
        service_provider = Supplier.objects.create(
            name='شركة النظافة',
            code='SERVICE001',
            primary_type=self.service_type
        )
        
        # اختبار وظائف مقدم الخدمات
        self.assertTrue(service_provider.is_service_provider())
        
        print("   ✅ الحقول الخاصة بالشركات تعمل بشكل صحيح")


class SupplierAdminInterfaceTest(TestCase):
    """
    اختبارات واجهة الإدارة للموردين
    Tests for supplier admin interface functionality
    """
    
    def setUp(self):
        """إعداد البيانات الأساسية للاختبارات"""
        # إنشاء مستخدم إداري
        self.admin_user = User.objects.create_superuser(
            username='admin',
            password='adminpass123',
            email='admin@example.com'
        )
        
        # إنشاء نوع مورد
        self.supplier_type = SupplierType.objects.create(
            name='مورد عام',
            code='general',
            description='مورد عام للشركة'
        )
        
        # إنشاء مورد
        self.supplier = Supplier.objects.create(
            name='مورد اختبار الإدارة',
            code='ADMIN001',
            primary_type=self.supplier_type,
            created_by=self.admin_user
        )
        
        self.client = Client()
        self.client.login(username='admin', password='adminpass123')
    
    def test_supplier_admin_list_view(self):
        """
        اختبار عرض قائمة الموردين في الإدارة
        Test supplier admin list view
        """
        print("🧪 اختبار عرض قائمة الموردين في الإدارة...")
        
        response = self.client.get('/admin/supplier/supplier/')
        
        # التحقق من نجاح الاستجابة
        self.assertEqual(response.status_code, 200)
        
        # التحقق من وجود المورد في القائمة
        self.assertContains(response, 'مورد اختبار الإدارة')
        self.assertContains(response, 'ADMIN001')
        
        print("   ✅ عرض قائمة الموردين في الإدارة يعمل بشكل صحيح")
    
    def test_supplier_admin_add_view(self):
        """
        اختبار عرض إضافة مورد في الإدارة
        Test supplier admin add view
        """
        print("🧪 اختبار عرض إضافة مورد في الإدارة...")
        
        response = self.client.get('/admin/supplier/supplier/add/')
        
        # التحقق من نجاح الاستجابة
        self.assertEqual(response.status_code, 200)
        
        # التحقق من وجود الحقول المطلوبة
        self.assertContains(response, 'name')
        self.assertContains(response, 'code')
        self.assertContains(response, 'supplier_type')
        
        print("   ✅ عرض إضافة مورد في الإدارة يعمل بشكل صحيح")
    
    def test_supplier_admin_edit_view(self):
        """
        اختبار عرض تعديل مورد في الإدارة
        Test supplier admin edit view
        """
        print("🧪 اختبار عرض تعديل مورد في الإدارة...")
        
        response = self.client.get(f'/admin/supplier/supplier/{self.supplier.id}/change/')
        
        # التحقق من نجاح الاستجابة
        self.assertEqual(response.status_code, 200)
        
        # التحقق من وجود بيانات المورد
        self.assertContains(response, 'مورد اختبار الإدارة')
        self.assertContains(response, 'ADMIN001')
        
        print("   ✅ عرض تعديل مورد في الإدارة يعمل بشكل صحيح")
    
    def test_supplier_type_settings_admin_list_view(self):
        """
        اختبار عرض قائمة إعدادات أنواع الموردين في الإدارة
        Test SupplierTypeSettings admin list view
        """
        print("🧪 اختبار عرض قائمة إعدادات أنواع الموردين في الإدارة...")
        
        # إنشاء إعدادات نوع مورد
        settings = SupplierTypeSettings.objects.create(
            name='مورد اختبار الإعدادات',
            code='test_settings',
            description='اختبار إعدادات نوع المورد',
            created_by=self.admin_user
        )
        
        response = self.client.get('/admin/supplier/suppliertypesettings/')
        
        # التحقق من نجاح الاستجابة
        self.assertEqual(response.status_code, 200)
        
        # التحقق من وجود الإعدادات في القائمة
        self.assertContains(response, 'مورد اختبار الإعدادات')
        self.assertContains(response, 'test_settings')
        
        print("   ✅ عرض قائمة إعدادات أنواع الموردين في الإدارة يعمل بشكل صحيح")
    
    def test_supplier_type_settings_admin_add_view(self):
        """
        اختبار عرض إضافة إعدادات نوع مورد في الإدارة
        Test SupplierTypeSettings admin add view
        """
        print("🧪 اختبار عرض إضافة إعدادات نوع مورد في الإدارة...")
        
        response = self.client.get('/admin/supplier/suppliertypesettings/add/')
        
        # التحقق من نجاح الاستجابة
        self.assertEqual(response.status_code, 200)
        
        # التحقق من وجود الحقول المطلوبة
        self.assertContains(response, 'name')
        self.assertContains(response, 'code')
        self.assertContains(response, 'icon')
        self.assertContains(response, 'color')
        
        print("   ✅ عرض إضافة إعدادات نوع مورد في الإدارة يعمل بشكل صحيح")


class SupplierSystemIntegrationTest(TestCase):
    """
    اختبارات التكامل النظامي الشاملة
    Comprehensive system integration tests
    """
    
    def setUp(self):
        """إعداد البيانات الأساسية للاختبارات"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_supplier_system_startup(self):
        """
        اختبار بدء تشغيل النظام بدون أخطاء
        Test system startup without errors
        """
        print("🧪 اختبار بدء تشغيل النظام...")
        
        # اختبار استيراد النماذج
        try:
            from supplier.models import Supplier, SupplierType, SupplierTypeSettings
            print("   ✅ استيراد النماذج نجح")
        except ImportError as e:
            self.fail(f"فشل في استيراد النماذج: {e}")
        
        # اختبار إنشاء النماذج
        try:
            supplier_type = SupplierType.objects.create(
                name='اختبار النظام',
                code='system_test'
            )
            
            supplier = Supplier.objects.create(
                name='مورد اختبار النظام',
                code='SYS001',
                primary_type=supplier_type
            )
            
            print("   ✅ إنشاء النماذج نجح")
        except Exception as e:
            self.fail(f"فشل في إنشاء النماذج: {e}")
        
        # اختبار ال��صول للواجهات
        try:
            response = self.client.get('/supplier/')
            self.assertIn(response.status_code, [200, 302])
            print("   ✅ الوصول للواجهات نجح")
        except Exception as e:
            self.fail(f"فشل في الوصول للواجهات: {e}")
    
    def test_supplier_data_integrity(self):
        """
        اختبار سلامة البيانات
        Test data integrity
        """
        print("🧪 اختبار سلامة البيانات...")
        
        # إنشاء بيانات اختبار
        supplier_type = SupplierType.objects.create(
            name='اختبار السلامة',
            code='integrity_test'
        )
        
        supplier = Supplier.objects.create(
            name='مورد اختبار السلامة',
            code='INT001',
            primary_type=supplier_type,
            balance=Decimal('1000.00')
        )
        
        # التحقق من سلامة البيانات
        self.assertEqual(supplier.name, 'مورد اختبار السلامة')
        self.assertEqual(supplier.code, 'INT001')
        self.assertEqual(supplier.balance, Decimal('1000.00'))
        self.assertEqual(supplier.primary_type, supplier_type)
        
        # التحقق من العلاقات
        self.assertIn(supplier, supplier_type.primary_suppliers.all())
        
        print("   ✅ سلامة البيانات محفوظة")
    
    def test_supplier_workflow_complete(self):
        """
        اختبار سير العمل الكامل للموردين
        Test complete supplier workflow
        """
        print("🧪 اختبار سير العمل الكامل للموردين...")
        
        # 1. إنشاء نوع مورد
        supplier_type = SupplierType.objects.create(
            name='مورد سير العمل',
            code='workflow_test',
            description='اختبار سير العمل الكامل'
        )
        
        # 2. إنشاء مورد
        supplier = Supplier.objects.create(
            name='مورد سير العمل الكامل',
            code='WF001',
            phone='+201234567890',
            email='workflow@test.com',
            primary_type=supplier_type,
            educational_specialization='مواد متخصصة'
        )
        
        # 3. إضافة أنواع متعددة
        service_type = SupplierType.objects.create(
            name='خدمات إضافية',
            code='additional_service'
        )
        supplier.supplier_types.add(service_type)
        
        # 4. تحديث بيانات المورد
        supplier.balance = Decimal('500.00')
        supplier.is_preferred = True
        supplier.save()
        
        # 5. التحقق من النتائج
        updated_supplier = Supplier.objects.get(code='WF001')
        self.assertEqual(updated_supplier.name, 'مورد سير العمل الكامل')
        self.assertEqual(updated_supplier.balance, Decimal('500.00'))
        self.assertTrue(updated_supplier.is_preferred)
        self.assertEqual(updated_supplier.supplier_types.count(), 1)
        
        # 6. اختبار الوظائف المتقدمة
        self.assertTrue(updated_supplier.is_educational_supplier())
        edu_info = updated_supplier.get_educational_info()
        self.assertEqual(edu_info['specialization'], 'مواد متخصصة')
        
        print("   ✅ سير العمل الكامل للموردين يعمل بشكل صحيح")


def run_core_functionality_tests():
    """
    تشغيل جميع اختبارات الوظائف الأساسية
    Run all core functionality tests
    """
    print("🚀 بدء اختبارات الوظائف الأساسية للموردين...")
    print("=" * 60)
    
    # تشغيل اختبارات النماذج الأساسية
    test_case = CoreSupplierFunctionalityTest()
    test_case.setUp()
    
    try:
        test_case.test_supplier_model_functionality()
        test_case.test_supplier_type_functionality()
        test_case.test_supplier_type_settings_functionality()
        test_case.test_supplier_relationships()
        test_case.test_supplier_validation()
        test_case.test_supplier_company_specific_fields()
        
        print("✅ جميع اختبارات النماذج الأساسية نجحت")
    except Exception as e:
        print(f"❌ فشل في اختبارات النماذج الأساسية: {e}")
        return False
    
    # تشغيل اختبارات واجهة الإدارة
    admin_test = SupplierAdminInterfaceTest()
    admin_test.setUp()
    
    try:
        admin_test.test_supplier_admin_list_view()
        admin_test.test_supplier_admin_add_view()
        admin_test.test_supplier_admin_edit_view()
        admin_test.test_supplier_type_settings_admin_list_view()
        admin_test.test_supplier_type_settings_admin_add_view()
        
        print("✅ جميع اختبارات واجهة الإدارة نجحت")
    except Exception as e:
        print(f"❌ فشل في اختبارات واجهة الإدارة: {e}")
        return False
    
    # تشغيل اختبارات التكامل النظامي
    integration_test = SupplierSystemIntegrationTest()
    integration_test.setUp()
    
    try:
        integration_test.test_supplier_system_startup()
        integration_test.test_supplier_data_integrity()
        integration_test.test_supplier_workflow_complete()
        
        print("✅ جميع اختبارات التكامل النظامي نجحت")
    except Exception as e:
        print(f"❌ فشل في اختبارات التكامل النظامي: {e}")
        return False
    
    print("=" * 60)
    print("🎉 جميع اختبارات الوظائف الأساسية نجحت بنجاح!")
    return True


if __name__ == '__main__':
    run_core_functionality_tests()