#!/usr/bin/env python
"""
سكريبت تنفيذ الاختبارات الشاملة
Comprehensive Tests Execution Script

هذا السكريبت ينفذ جميع الاختبارات المتاحة بشكل متسلسل
"""

import os
import sys
import django
from datetime import date, datetime
import subprocess

# إعداد Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'corporate_erp.settings')
django.setup()


class ComprehensiveTestRunner:
    """منفذ الاختبارات الشاملة"""
    
    def __init__(self):
        self.results = []
        self.total_tests = 0
        self.passed_tests = 0
        self.failed_tests = 0
    
    def run_script(self, script_name, description):
        """تنفيذ سكريبت اختبار"""
        print(f"\n🔄 تنفيذ {description}...")
        print("=" * 60)
        
        try:
            result = subprocess.run([
                sys.executable, f"scripts/{script_name}"
            ], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
            if result.returncode == 0:
                print(result.stdout)
                # استخراج النتائج من المخرجات
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'معدل النجاح:' in line:
                        success_rate = line.split(':')[1].strip().replace('%', '')
                        try:
                            success_rate = float(success_rate)
                            self.results.append({
                                'script': script_name,
                                'description': description,
                                'success_rate': success_rate,
                                'status': 'PASS' if success_rate == 100.0 else 'PARTIAL'
                            })
                        except:
                            pass
                        break
                else:
                    # إذا لم نجد معدل النجاح، نعتبر الاختبار نجح
                    self.results.append({
                        'script': script_name,
                        'description': description,
                        'success_rate': 100.0,
                        'status': 'PASS'
                    })
            else:
                print(f"❌ فشل في تنفيذ {description}")
                print("STDOUT:", result.stdout)
                print("STDERR:", result.stderr)
                self.results.append({
                    'script': script_name,
                    'description': description,
                    'success_rate': 0.0,
                    'status': 'FAIL',
                    'error': result.stderr
                })
                
        except Exception as e:
            print(f"❌ خطأ في تنفيذ {description}: {str(e)}")
            self.results.append({
                'script': script_name,
                'description': description,
                'success_rate': 0.0,
                'status': 'FAIL',
                'error': str(e)
            })
    
    def run_all_tests(self):
        """تنفيذ جميع الاختبارات"""
        print("🚀 بدء تنفيذ الاختبارات الشاملة...")
        print(f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        # قائمة الاختبارات المتاحة
        test_scripts = [
            ("run_foundation_tests.py", "الاختبارات التأسيسية (T001-T005)"),
            ("run_users_financial_tests.py", "اختبارات المستخدمين والمالي (T006-T009)"),
            ("run_basic_integration_test.py", "اختبار التكامل الأساسي"),
        ]
        
        # تنفيذ كل اختبار
        for script_name, description in test_scripts:
            self.run_script(script_name, description)
        
        # طباعة الملخص النهائي
        self.print_final_summary()
    
    def print_final_summary(self):
        """طباعة الملخص النهائي"""
        print("\n" + "=" * 80)
        print("📊 الملخص النهائي للاختبارات الشاملة")
        print("=" * 80)
        
        total_scripts = len(self.results)
        passed_scripts = len([r for r in self.results if r['status'] == 'PASS'])
        partial_scripts = len([r for r in self.results if r['status'] == 'PARTIAL'])
        failed_scripts = len([r for r in self.results if r['status'] == 'FAIL'])
        
        print(f"📈 إجمالي السكريبتات: {total_scripts}")
        print(f"✅ نجح بالكامل: {passed_scripts}")
        print(f"⚠️ نجح جزئياً: {partial_scripts}")
        print(f"❌ فشل: {failed_scripts}")
        
        if total_scripts > 0:
            overall_success = (passed_scripts + partial_scripts) / total_scripts * 100
            print(f"🎯 معدل النجاح الإجمالي: {overall_success:.1f}%")
        
        print("\n📋 تفاصيل النتائج:")
        print("-" * 80)
        
        for result in self.results:
            status_icon = "✅" if result['status'] == 'PASS' else "⚠️" if result['status'] == 'PARTIAL' else "❌"
            print(f"{status_icon} {result['description']}")
            print(f"   📊 معدل النجاح: {result['success_rate']:.1f}%")
            if 'error' in result:
                print(f"   🔍 الخطأ: {result['error'][:100]}...")
            print()
        
        # توصيات
        print("💡 التوصيات:")
        if failed_scripts > 0:
            print("   - راجع الأخطاء في السكريبتات الفاشلة وأصلحها")
        if partial_scripts > 0:
            print("   - راجع الاختبارات الجزئية وأكمل الاختبارات الناقصة")
        if passed_scripts == total_scripts:
            print("   - ممتاز! جميع الاختبارات نجحت. يمكنك الانتقال للمرحلة التالية")
        
        print("\n🎉 انتهى تنفيذ الاختبارات الشاملة")
        print("=" * 80)


if __name__ == "__main__":
    runner = ComprehensiveTestRunner()
    runner.run_all_tests()