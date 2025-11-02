#!/usr/bin/env python
"""
اختبارات شاملة لجميع تقارير المخزون
تشمل: ABC للمنتجات، معدل الدوران، نقطة إعادة الطلب
"""
import os
import sys
import django

# إضافة المسار الحالي للـ Python path
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, current_dir)

# إعداد Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mwheba_erp.settings')
django.setup()


class InventoryReportsTestSuite:
    """مجموعة اختبارات شاملة لتقارير المخزون"""
    
    def __init__(self):
        self.results = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'errors': []
        }
    
    def print_header(self, title):
        """طباعة عنوان مميز"""
        print("\n" + "=" * 80)
        print(f"  {title}")
        print("=" * 80)
    
    def print_test(self, name, status, details=""):
        """طباعة نتيجة اختبار"""
        self.results['total'] += 1
        if status:
            self.results['passed'] += 1
            icon = "[OK]"
        else:
            self.results['failed'] += 1
            icon = "[FAIL]"
            self.results['errors'].append(f"{name}: {details}")
        
        print(f"{icon} {name}")
        if details and not status:
            print(f"   خطأ: {details}")
    
    def test_abc_analysis_products(self):
        """اختبار تحليل ABC للمنتجات"""
        self.print_header("[1] اختبار تحليل ABC للمنتجات (حسب المبيعات)")
        
        try:
            from product.services.advanced_reports_service import AdvancedReportsService
            
            # اختبار 1: استدعاء الخدمة
            try:
                result = AdvancedReportsService.abc_analysis(period_months=12)
                has_data = 'analysis_data' in result and 'summary' in result
                self.print_test("استدعاء خدمة ABC للمنتجات", has_data)
                
                if has_data:
                    print(f"   - عدد المنتجات: {result['summary']['total_products']}")
                    print(f"   - فئة A: {result['summary']['category_a_count']}")
                    print(f"   - فئة B: {result['summary']['category_b_count']}")
                    print(f"   - فئة C: {result['summary']['category_c_count']}")
                    
            except Exception as e:
                self.print_test("استدعاء خدمة ABC للمنتجات", False, str(e))
            
            # اختبار 2: التحقق من البيانات
            if 'analysis_data' in result:
                try:
                    for item in result['analysis_data'][:3]:
                        required_fields = ['product', 'sales_value', 'category', 'cumulative_percentage']
                        has_all_fields = all(field in item for field in required_fields)
                        
                        if not has_all_fields:
                            missing = [f for f in required_fields if f not in item]
                            self.print_test("التحقق من حقول البيانات", False, f"حقول مفقودة: {missing}")
                            break
                    else:
                        self.print_test("التحقق من حقول البيانات", True)
                except Exception as e:
                    self.print_test("التحقق من حقول البيانات", False, str(e))
            
            # اختبار 3: اختبار View
            try:
                from product.views_modules.inventory_views import abc_analysis_report
                from django.test import RequestFactory
                from django.contrib.auth import get_user_model
                
                User = get_user_model()
                
                factory = RequestFactory()
                request = factory.get('/products/reports/abc-analysis/')
                request.user = User.objects.first()
                
                response = abc_analysis_report(request)
                success = response.status_code == 200
                self.print_test("اختبار View تحليل ABC", success)
                
            except Exception as e:
                self.print_test("اختبار View تحليل ABC", False, str(e))
                
        except ImportError as e:
            self.print_test("استيراد خدمة ABC للمنتجات", False, str(e))
    
    def test_inventory_turnover(self):
        """اختبار معدل دوران المخزون"""
        self.print_header("[2] اختبار معدل دوران المخزون (Inventory Turnover)")
        
        try:
            from product.services.advanced_reports_service import AdvancedReportsService
            
            # اختبار 1: استدعاء الخدمة
            try:
                result = AdvancedReportsService.inventory_turnover_analysis(period_months=12)
                has_data = 'analysis_data' in result and 'summary' in result
                self.print_test("استدعاء خدمة معدل الدوران", has_data)
                
                if has_data:
                    print(f"   - عدد المنتجات: {result['summary']['total_products']}")
                    print(f"   - متوسط معدل الدوران: {result['summary']['avg_turnover']}")
                    print(f"   - سريع: {result['summary']['fast_count']}")
                    print(f"   - متوسط: {result['summary']['medium_count']}")
                    print(f"   - بطيء: {result['summary']['slow_count']}")
                    print(f"   - راكد: {result['summary']['stagnant_count']}")
                    
            except Exception as e:
                self.print_test("استدعاء خدمة معدل الدوران", False, str(e))
            
            # اختبار 2: التحقق من البيانات
            if 'analysis_data' in result and result['analysis_data']:
                try:
                    item = result['analysis_data'][0]
                    required_fields = ['product', 'turnover_ratio', 'days_in_inventory', 'category']
                    has_all_fields = all(field in item for field in required_fields)
                    self.print_test("التحقق من حقول معدل الدوران", has_all_fields)
                except Exception as e:
                    self.print_test("التحقق من حقول معدل الدوران", False, str(e))
            
            # اختبار 3: اختبار View
            try:
                from product.views_modules.inventory_views import inventory_turnover_report
                from django.test import RequestFactory
                from django.contrib.auth import get_user_model
                
                User = get_user_model()
                
                factory = RequestFactory()
                request = factory.get('/products/reports/inventory-turnover/')
                request.user = User.objects.first()
                
                response = inventory_turnover_report(request)
                success = response.status_code == 200
                self.print_test("اختبار View معدل الدوران", success)
                
            except Exception as e:
                self.print_test("اختبار View معدل الدوران", False, str(e))
                
        except ImportError as e:
            self.print_test("استيراد خدمة معدل الدوران", False, str(e))
    
    def test_reorder_point(self):
        """اختبار نقطة إعادة الطلب"""
        self.print_header("[3] اختبار نقطة إعادة الطلب (Reorder Point)")
        
        try:
            from product.services.advanced_reports_service import AdvancedReportsService
            
            # اختبار 1: استدعاء الخدمة
            try:
                result = AdvancedReportsService.reorder_point_analysis(
                    analysis_days=30,
                    lead_time_days=7,
                    safety_stock_days=3
                )
                has_data = 'analysis_data' in result and 'summary' in result
                self.print_test("استدعاء خدمة نقطة إعادة الطلب", has_data)
                
                if has_data:
                    print(f"   - عدد المنتجات: {result['summary']['total_products']}")
                    print(f"   - نفد المخزون: {result['summary']['out_of_stock']}")
                    print(f"   - يحتاج طلب: {result['summary']['need_reorder']}")
                    print(f"   - مراقبة: {result['summary']['under_watch']}")
                    print(f"   - طبيعي: {result['summary']['normal']}")
                    
            except Exception as e:
                self.print_test("استدعاء خدمة نقطة إعادة الطلب", False, str(e))
            
            # اختبار 2: التحقق من البيانات
            if 'analysis_data' in result and result['analysis_data']:
                try:
                    item = result['analysis_data'][0]
                    required_fields = ['product', 'current_stock', 'reorder_point', 
                                     'suggested_order_qty', 'status', 'days_remaining']
                    has_all_fields = all(field in item for field in required_fields)
                    self.print_test("التحقق من حقول نقطة إعادة الطلب", has_all_fields)
                    
                    if has_all_fields:
                        print(f"   - مثال: {item['product'].name}")
                        print(f"     * المخزون: {item['current_stock']}")
                        print(f"     * نقطة الطلب: {item['reorder_point']}")
                        print(f"     * الحالة: {item['status_label']}")
                        
                except Exception as e:
                    self.print_test("التحقق من حقول نقطة إعادة الطلب", False, str(e))
            
            # اختبار 3: اختبار View
            try:
                from product.views_modules.inventory_views import reorder_point_report
                from django.test import RequestFactory
                from django.contrib.auth import get_user_model
                
                User = get_user_model()
                
                factory = RequestFactory()
                request = factory.get('/products/reports/reorder-point/')
                request.user = User.objects.first()
                
                response = reorder_point_report(request)
                success = response.status_code == 200
                self.print_test("اختبار View نقطة إعادة الطلب", success)
                
            except Exception as e:
                self.print_test("اختبار View نقطة إعادة الطلب", False, str(e))
                
        except ImportError as e:
            self.print_test("استيراد خدمة نقطة إعادة الطلب", False, str(e))
    
    def print_summary(self):
        """طباعة ملخص النتائج"""
        self.print_header("ملخص نتائج اختبارات المخزون")
        
        print(f"\nإجمالي الاختبارات: {self.results['total']}")
        print(f"[OK] نجح: {self.results['passed']}")
        print(f"[FAIL] فشل: {self.results['failed']}")
        
        if self.results['total'] > 0:
            success_rate = (self.results['passed'] / self.results['total']) * 100
            print(f"نسبة النجاح: {success_rate:.1f}%")
        
        if self.results['errors']:
            print("\n[FAIL] الأخطاء:")
            for error in self.results['errors']:
                print(f"   - {error}")
        
        print("\n" + "=" * 80)
        
        return self.results['failed'] == 0
    
    def run_all_tests(self):
        """تشغيل جميع الاختبارات"""
        print("\n" + "=" * 80)
        print("  اختبارات شاملة لتقارير المخزون")
        print("=" * 80)
        
        self.test_abc_analysis_products()
        self.test_inventory_turnover()
        self.test_reorder_point()
        
        return self.print_summary()


if __name__ == "__main__":
    suite = InventoryReportsTestSuite()
    success = suite.run_all_tests()
    
    sys.exit(0 if success else 1)
