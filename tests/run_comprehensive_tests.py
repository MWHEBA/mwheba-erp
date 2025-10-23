"""
تشغيل الاختبارات الشاملة لنظام MWHEBA ERP
يقوم بتنفيذ جميع أنواع الاختبارات وإنشاء تقرير شامل
"""
import os
import sys
import django
from django.test.utils import get_runner
from django.conf import settings
from django.core.management import call_command
import time
from datetime import datetime

# إضافة مسار المشروع
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# إعداد Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mwheba_erp.settings')
django.setup()


class ComprehensiveTestRunner:
    """مشغل الاختبارات الشاملة"""
    
    def __init__(self):
        self.test_results = {
            'total_tests': 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'execution_time': 0,
            'test_categories': {}
        }
        
        # قائمة الاختبارات المتاحة
        self.test_modules = [
            'tests.test_individual_apps',           # جديد - اختبارات التطبيقات الفردية
            'tests.test_user_interface',            # جديد - اختبارات واجهة المستخدم
            'tests.test_advanced_scenarios',        # جديد - السيناريوهات المتقدمة
            'tests.test_complete_business_cycle',
            'tests.test_complex_scenarios', 
            'tests.test_performance_load',
            'tests.test_security_permissions',
            'tests.test_reports_analytics',
            'tests.test_external_integration'
        ]
    
    def run_all_tests(self):
        """تشغيل جميع الاختبارات"""
        print("🚀 بدء تشغيل الاختبارات الشاملة لنظام MWHEBA ERP")
        print("=" * 80)
        
        start_time = time.time()
        
        # تشغيل كل فئة من الاختبارات
        for test_module in self.test_modules:
            self.run_test_category(test_module)
        
        end_time = time.time()
        self.test_results['execution_time'] = end_time - start_time
        
        # طباعة التقرير النهائي
        self.print_final_report()
    
    def run_test_category(self, test_module):
        """تشغيل فئة اختبارات محددة"""
        category_name = test_module.split('.')[-1].replace('test_', '')
        
        print(f"\n📋 تشغيل اختبارات: {category_name}")
        print("-" * 50)
        
        try:
            # تشغيل الاختبارات
            from django.test.runner import DiscoverRunner
            runner = DiscoverRunner(verbosity=2, interactive=False)
            
            # تشغيل اختبارات الوحدة المحددة
            result = runner.run_tests([test_module])
            
            # تسجيل النتائج
            self.test_results['test_categories'][category_name] = {
                'status': 'نجح' if result == 0 else 'فشل',
                'errors': result
            }
            
            if result == 0:
                self.test_results['passed_tests'] += 1
                print(f"✅ {category_name}: نجح")
            else:
                self.test_results['failed_tests'] += 1
                print(f"❌ {category_name}: فشل ({result} أخطاء)")
                
        except Exception as e:
            self.test_results['failed_tests'] += 1
            self.test_results['test_categories'][category_name] = {
                'status': 'خطأ',
                'errors': str(e)
            }
            print(f"⚠️ {category_name}: خطأ - {str(e)}")
        
        self.test_results['total_tests'] += 1
    
    def run_specific_tests(self, test_names):
        """تشغيل اختبارات محددة"""
        print(f"🎯 تشغيل اختبارات محددة: {', '.join(test_names)}")
        print("=" * 80)
        
        start_time = time.time()
        
        for test_name in test_names:
            if test_name in [module.split('.')[-1] for module in self.test_modules]:
                full_module = f"tests.{test_name}"
                self.run_test_category(full_module)
            else:
                print(f"⚠️ اختبار غير موجود: {test_name}")
        
        end_time = time.time()
        self.test_results['execution_time'] = end_time - start_time
        
        self.print_final_report()
    
    def print_final_report(self):
        """طباعة التقرير النهائي"""
        print("\n" + "=" * 80)
        print("📊 تقرير الاختبارات الشاملة - نظام MWHEBA ERP")
        print("=" * 80)
        
        # معلومات عامة
        print(f"📅 تاريخ التشغيل: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⏱️ وقت التنفيذ الإجمالي: {self.test_results['execution_time']:.2f} ثانية")
        print(f"📋 إجمالي فئات الاختبارات: {self.test_results['total_tests']}")
        
        # نتائج الاختبارات
        print(f"\n🎯 نتائج الاختبارات:")
        print(f"   ✅ نجح: {self.test_results['passed_tests']}")
        print(f"   ❌ فشل: {self.test_results['failed_tests']}")
        
        # نسبة النجاح
        if self.test_results['total_tests'] > 0:
            success_rate = (self.test_results['passed_tests'] / self.test_results['total_tests']) * 100
            print(f"   📊 نسبة النجاح: {success_rate:.1f}%")
        
        # تفاصيل كل فئة
        print(f"\n📋 تفاصيل فئات الاختبارات:")
        for category, details in self.test_results['test_categories'].items():
            status_icon = "✅" if details['status'] == 'نجح' else "❌"
            print(f"   {status_icon} {category}: {details['status']}")
            if details['errors'] and details['status'] != 'نجح':
                print(f"      خطأ: {details['errors']}")
        
        # توصيات
        print(f"\n💡 التوصيات:")
        if self.test_results['failed_tests'] == 0:
            print("   🎉 جميع الاختبارات نجحت! النظام جاهز للإنتاج.")
        elif self.test_results['failed_tests'] <= 2:
            print("   👍 معظم الاختبارات نجحت. راجع الأخطاء البسيطة.")
        else:
            print("   ⚠️ عدة اختبارات فشلت. مراجعة شاملة مطلوبة.")
        
        # فئات الاختبارات المُنفذة
        print(f"\n🔍 فئات الاختبارات المُنفذة:")
        test_descriptions = {
            'test_complete_business_cycle': 'دورة الأعمال الكاملة',
            'test_complex_scenarios': 'السيناريوهات المعقدة',
            'test_performance_load': 'الأداء والحمولة',
            'test_security_permissions': 'الأمان والصلاحيات',
            'test_reports_analytics': 'التقارير والتحليلات',
            'test_external_integration': 'التكامل مع الأنظمة الخارجية'
        }
        
        for category in self.test_results['test_categories'].keys():
            full_name = f"test_{category}"
            description = test_descriptions.get(full_name, category)
            print(f"   📌 {description}")
        
        print("=" * 80)
    
    def generate_html_report(self):
        """إنشاء تقرير HTML"""
        html_content = f"""
        <!DOCTYPE html>
        <html dir="rtl" lang="ar">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>تقرير اختبارات MWHEBA ERP</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; }}
                .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 8px; }}
                .summary {{ background: #ecf0f1; padding: 15px; margin: 20px 0; border-radius: 8px; }}
                .test-category {{ margin: 10px 0; padding: 10px; border-left: 4px solid #3498db; }}
                .success {{ border-left-color: #27ae60; background: #d5f4e6; }}
                .failure {{ border-left-color: #e74c3c; background: #fadbd8; }}
                .error {{ border-left-color: #f39c12; background: #fdeaa7; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>تقرير اختبارات نظام MWHEBA ERP</h1>
                <p>تاريخ التشغيل: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div class="summary">
                <h2>ملخص النتائج</h2>
                <p><strong>إجمالي الاختبارات:</strong> {self.test_results['total_tests']}</p>
                <p><strong>نجح:</strong> {self.test_results['passed_tests']}</p>
                <p><strong>فشل:</strong> {self.test_results['failed_tests']}</p>
                <p><strong>وقت التنفيذ:</strong> {self.test_results['execution_time']:.2f} ثانية</p>
            </div>
            
            <h2>تفاصيل الاختبارات</h2>
        """
        
        for category, details in self.test_results['test_categories'].items():
            css_class = 'success' if details['status'] == 'نجح' else 'failure'
            html_content += f"""
            <div class="test-category {css_class}">
                <h3>{category}</h3>
                <p><strong>الحالة:</strong> {details['status']}</p>
                {f"<p><strong>الأخطاء:</strong> {details['errors']}</p>" if details['errors'] and details['status'] != 'نجح' else ""}
            </div>
            """
        
        html_content += """
        </body>
        </html>
        """
        
        # حفظ التقرير
        report_path = 'test_report.html'
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"\n📄 تم إنشاء تقرير HTML: {report_path}")


def main():
    """الدالة الرئيسية"""
    runner = ComprehensiveTestRunner()
    
    # التحقق من المعاملات
    if len(sys.argv) > 1:
        # تشغيل اختبارات محددة
        test_names = sys.argv[1:]
        runner.run_specific_tests(test_names)
    else:
        # تشغيل جميع الاختبارات
        runner.run_all_tests()
    
    # إنشاء تقرير HTML
    runner.generate_html_report()


if __name__ == '__main__':
    main()
