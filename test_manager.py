#!/usr/bin/env python
"""
مدير الاختبارات المتقدم لنظام MWHEBA ERP
يوفر إدارة شاملة للاختبارات مع تقارير مفصلة وإحصائيات متقدمة
"""

import os
import sys
import subprocess
import time
import json
from datetime import datetime
from pathlib import Path

class TestManager:
    """مدير الاختبارات الرئيسي"""
    
    def __init__(self):
        self.apps = [
            'core', 'product', 'printing_pricing', 'financial',
            'purchase', 'sale', 'utils', 'services'
        ]
        self.results = {}
        self.start_time = None
        self.end_time = None
    
    def print_header(self):
        """طباعة رأس التقرير"""
        print("=" * 80)
        print("🧪 مدير الاختبارات المتقدم - MWHEBA ERP")
        print("=" * 80)
        print(f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📊 عدد التطبيقات: {len(self.apps)}")
        print("=" * 80)
    
    def print_section(self, title, icon="📋"):
        """طباعة عنوان قسم"""
        print(f"\n{icon} {title}")
        print("-" * 60)
    
    def run_command(self, command, description, timeout=300):
        """تشغيل أمر مع عرض النتائج"""
        print(f"🔄 {description}...")
        start_time = time.time()
        
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True,
                timeout=timeout
            )
            
            end_time = time.time()
            duration = end_time - start_time
            
            if result.returncode == 0:
                print(f"✅ {description} - مكتمل ({duration:.2f}s)")
                return True, result.stdout, duration
            else:
                print(f"❌ {description} - فشل ({duration:.2f}s)")
                return False, result.stderr, duration
                
        except subprocess.TimeoutExpired:
            print(f"⏰ {description} - انتهت المهلة الزمنية")
            return False, "انتهت المهلة الزمنية", timeout
        except Exception as e:
            print(f"💥 {description} - خطأ غير متوقع: {str(e)}")
            return False, str(e), 0
    
    def check_test_files(self):
        """فحص ملفات الاختبار المتاحة"""
        self.print_section("فحص ملفات الاختبار", "🔍")
        
        test_summary = {}
        total_files = 0
        
        for app in self.apps:
            test_dir = Path(app) / "tests"
            if test_dir.exists():
                test_files = list(test_dir.glob("test_*.py"))
                test_summary[app] = {
                    'files': [f.name for f in test_files],
                    'count': len(test_files)
                }
                total_files += len(test_files)
                
                print(f"📁 {app}: {len(test_files)} ملف اختبار")
                for file in test_files:
                    print(f"   - {file.name}")
            else:
                test_summary[app] = {'files': [], 'count': 0}
                print(f"⚠️  {app}: مجلد الاختبارات غير موجود")
        
        print(f"\n📊 إجمالي ملفات الاختبار: {total_files}")
        return test_summary
    
    def run_app_tests(self, app_name, verbose=False):
        """تشغيل اختبارات تطبيق محدد"""
        verbosity = " -v 2" if verbose else ""
        command = f"python manage.py test {app_name}{verbosity}"
        
        success, output, duration = self.run_command(
            command, 
            f"اختبار تطبيق {app_name}"
        )
        
        # تحليل النتائج
        test_count = self.parse_test_count(output)
        
        return {
            'success': success,
            'output': output,
            'duration': duration,
            'test_count': test_count
        }
    
    def parse_test_count(self, output):
        """استخراج عدد الاختبارات من النتائج"""
        try:
            # البحث عن نمط "Ran X tests"
            import re
            match = re.search(r'Ran (\d+) tests?', output)
            if match:
                return int(match.group(1))
        except:
            pass
        return 0
    
    def run_all_tests(self, verbose=False):
        """تشغيل اختبارات جميع التطبيقات"""
        self.print_section("تشغيل جميع الاختبارات", "🚀")
        
        self.start_time = time.time()
        self.results = {}
        
        for app in self.apps:
            self.results[app] = self.run_app_tests(app, verbose)
        
        self.end_time = time.time()
        self.generate_summary()
        
        return self.results
    
    def generate_summary(self):
        """إنشاء ملخص النتائج"""
        self.print_section("ملخص النتائج", "📊")
        
        total_duration = self.end_time - self.start_time
        passed_apps = sum(1 for r in self.results.values() if r['success'])
        failed_apps = len(self.results) - passed_apps
        total_tests = sum(r['test_count'] for r in self.results.values())
        
        print(f"📈 إجمالي التطبيقات: {len(self.apps)}")
        print(f"✅ نجح: {passed_apps}")
        print(f"❌ فشل: {failed_apps}")
        print(f"🧪 إجمالي الاختبارات: {total_tests}")
        print(f"⏱️  الوقت الإجمالي: {total_duration:.2f} ثانية")
        print(f"⚡ متوسط الوقت لكل تطبيق: {total_duration/len(self.apps):.2f} ثانية")
        
        if failed_apps > 0:
            self.print_section("التطبيقات التي فشلت", "❌")
            for app, result in self.results.items():
                if not result['success']:
                    print(f"  - {app}: {result['output'][:150]}...")
        
        # إحصائيات مفصلة
        self.print_section("إحصائيات مفصلة", "📋")
        for app, result in self.results.items():
            status = "✅" if result['success'] else "❌"
            print(f"{status} {app}: {result['test_count']} اختبار ({result['duration']:.2f}s)")
    
    def run_with_coverage(self):
        """تشغيل الاختبارات مع تقرير التغطية"""
        self.print_section("اختبار مع تقرير التغطية", "📊")
        
        # تحقق من وجود coverage
        success, _, _ = self.run_command('pip show coverage', 'التحقق من وجود coverage')
        
        if not success:
            print("📦 تثبيت coverage...")
            install_success, _, _ = self.run_command('pip install coverage', 'تثبيت coverage')
            if not install_success:
                print("❌ فشل تثبيت coverage")
                return False
        
        # تشغيل الاختبارات مع coverage
        success, output, duration = self.run_command(
            'coverage run --source="." manage.py test',
            'تشغيل الاختبارات مع تتبع التغطية',
            timeout=600  # 10 دقائق للاختبارات الشاملة
        )
        
        if success:
            # إنشاء تقرير التغطية
            self.run_command('coverage report', 'إنشاء تقرير التغطية')
            self.run_command('coverage html', 'إنشاء تقرير HTML للتغطية')
            self.run_command('coverage xml', 'إنشاء تقرير XML للتغطية')
            
            print("📄 تقارير التغطية متاحة في:")
            print("   - تقرير نصي: في الطرفية أعلاه")
            print("   - تقرير HTML: htmlcov/index.html")
            print("   - تقرير XML: coverage.xml")
        
        return success
    
    def run_specific_test(self, test_path):
        """تشغيل اختبار محدد"""
        self.print_section(f"تشغيل اختبار محدد: {test_path}", "🎯")
        
        success, output, duration = self.run_command(
            f'python manage.py test {test_path} -v 2',
            f'تشغيل {test_path}'
        )
        
        if success:
            print("✅ الاختبار مكتمل بنجاح")
            test_count = self.parse_test_count(output)
            print(f"🧪 عدد الاختبارات: {test_count}")
            print(f"⏱️  المدة: {duration:.2f} ثانية")
        else:
            print("❌ فشل الاختبار")
            print("تفاصيل الخطأ:")
            print(output)
        
        return success
    
    def generate_json_report(self, filename="test_results.json"):
        """إنشاء تقرير JSON للنتائج"""
        if not self.results:
            print("⚠️  لا توجد نتائج لحفظها")
            return
        
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'total_apps': len(self.apps),
            'total_duration': self.end_time - self.start_time if self.end_time and self.start_time else 0,
            'results': self.results,
            'summary': {
                'passed': sum(1 for r in self.results.values() if r['success']),
                'failed': sum(1 for r in self.results.values() if not r['success']),
                'total_tests': sum(r['test_count'] for r in self.results.values())
            }
        }
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            print(f"💾 تم حفظ التقرير في: {filename}")
        except Exception as e:
            print(f"❌ فشل حفظ التقرير: {e}")
    
    def show_help(self):
        """عرض تعليمات الاستخدام"""
        print("🔧 تعليمات الاستخدام:")
        print("  python test_manager.py all              # تشغيل جميع الاختبارات")
        print("  python test_manager.py all --verbose    # تشغيل جميع الاختبارات مع تفاصيل")
        print("  python test_manager.py app <name>       # تشغيل اختبارات تطبيق محدد")
        print("  python test_manager.py coverage         # تشغيل مع تقرير التغطية")
        print("  python test_manager.py test <path>      # تشغيل اختبار محدد")
        print("  python test_manager.py check            # فحص ملفات الاختبار")
        print("  python test_manager.py help             # عرض هذه التعليمات")


def main():
    """الدالة الرئيسية"""
    manager = TestManager()
    manager.print_header()
    
    if len(sys.argv) < 2:
        manager.show_help()
        return
    
    command = sys.argv[1].lower()
    
    if command == 'all':
        verbose = '--verbose' in sys.argv or '-v' in sys.argv
        results = manager.run_all_tests(verbose)
        
        # حفظ التقرير
        manager.generate_json_report()
        
        # تحديد رمز الخروج
        failed_count = sum(1 for r in results.values() if not r['success'])
        sys.exit(failed_count)
        
    elif command == 'app' and len(sys.argv) > 2:
        app_name = sys.argv[2]
        if app_name not in manager.apps:
            print(f"❌ التطبيق '{app_name}' غير موجود")
            print(f"التطبيقات المتاحة: {', '.join(manager.apps)}")
            sys.exit(1)
        
        verbose = '--verbose' in sys.argv or '-v' in sys.argv
        result = manager.run_app_tests(app_name, verbose)
        sys.exit(0 if result['success'] else 1)
        
    elif command == 'coverage':
        success = manager.run_with_coverage()
        sys.exit(0 if success else 1)
        
    elif command == 'test' and len(sys.argv) > 2:
        test_path = sys.argv[2]
        success = manager.run_specific_test(test_path)
        sys.exit(0 if success else 1)
        
    elif command == 'check':
        manager.check_test_files()
        
    elif command == 'help':
        manager.show_help()
        
    else:
        print("❌ أمر غير صحيح")
        manager.show_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
