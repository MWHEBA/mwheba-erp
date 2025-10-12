from django.core.management.base import BaseCommand
from django.test.runner import DiscoverRunner
from django.conf import settings
import os
import datetime
import sys
import io
import unittest
import xml.etree.ElementTree as ET
from django.utils.timezone import now


class TestReportRunner(DiscoverRunner):
    """
    رانر مخصص للاختبارات مع إمكانية إنشاء تقارير
    """
    def run_tests(self, test_labels, extra_tests=None, **kwargs):
        """
        تشغيل الاختبارات وإنشاء تقرير
        """
        # تهيئة مخرجات الاختبارات
        self.buffer = io.StringIO()
        self.test_result = None
        
        # حفظ المخرج الأصلي
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        
        # توجيه المخرجات إلى ذاكرة مؤقتة
        sys.stdout = sys.stderr = self.buffer
        
        # تشغيل الاختبارات
        try:
            result = super().run_tests(test_labels, extra_tests, **kwargs)
            self.test_result = result
            return result
        finally:
            # استعادة المخرجات الأصلية
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            
            # إنشاء تقرير
            self._generate_report()
    
    def _generate_report(self):
        """
        إنشاء تقرير بنتائج الاختبارات
        """
        if self.test_result is None:
            return
        
        # تحضير ملف التقرير
        reports_dir = os.path.join(settings.BASE_DIR, 'test_reports')
        os.makedirs(reports_dir, exist_ok=True)
        
        # إنشاء اسم الملف بتاريخ الوقت الحالي
        timestamp = now().strftime('%Y%m%d_%H%M%S')
        report_file = os.path.join(reports_dir, f'test_report_{timestamp}.txt')
        
        # كتابة التقرير
        with open(report_file, 'w', encoding='utf-8') as f:
            # معلومات الرأس
            f.write('=' * 80 + '\n')
            f.write(f'تقرير اختبارات نظام MWHEBA ERP\n')
            f.write(f'تاريخ التشغيل: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write('=' * 80 + '\n\n')
            
            # ملخص النتائج
            f.write('ملخص النتائج:\n')
            f.write('-' * 50 + '\n')
            f.write(f'عدد الاختبارات الناجحة: {self.test_result.testsRun - len(self.test_result.errors) - len(self.test_result.failures)}\n')
            f.write(f'عدد الاختبارات الفاشلة: {len(self.test_result.failures)}\n')
            f.write(f'عدد الأخطاء: {len(self.test_result.errors)}\n')
            f.write(f'إجمالي الاختبارات: {self.test_result.testsRun}\n')
            f.write('\n')
            
            # تفاصيل الأخطاء
            if self.test_result.errors:
                f.write('تفاصيل الأخطاء:\n')
                f.write('-' * 50 + '\n')
                for i, (test, error) in enumerate(self.test_result.errors, 1):
                    f.write(f'خطأ {i}: {test}\n')
                    f.write(f'{error}\n')
                    f.write('-' * 50 + '\n')
                f.write('\n')
            
            # تفاصيل الفشل
            if self.test_result.failures:
                f.write('تفاصيل الفشل:\n')
                f.write('-' * 50 + '\n')
                for i, (test, failure) in enumerate(self.test_result.failures, 1):
                    f.write(f'فشل {i}: {test}\n')
                    f.write(f'{failure}\n')
                    f.write('-' * 50 + '\n')
                f.write('\n')
            
            # مخرجات الاختبارات
            f.write('مخرجات الاختبارات:\n')
            f.write('-' * 50 + '\n')
            f.write(self.buffer.getvalue())
        
        # إنشاء تقرير XML (JUnit format)
        xml_report_file = os.path.join(reports_dir, f'test_report_{timestamp}.xml')
        self._generate_xml_report(xml_report_file)
        
        print(f'\nتم إنشاء تقرير الاختبارات في:\n{report_file}\n{xml_report_file}')

    def _generate_xml_report(self, xml_file_path):
        """
        إنشاء تقرير بتنسيق XML متوافق مع JUnit
        """
        root = ET.Element('testsuites')
        testsuite = ET.SubElement(root, 'testsuite')
        testsuite.set('name', 'MWHEBA ERP Tests')
        testsuite.set('tests', str(self.test_result.testsRun))
        testsuite.set('failures', str(len(self.test_result.failures)))
        testsuite.set('errors', str(len(self.test_result.errors)))
        testsuite.set('time', '0')
        
        # تعيين تفاصيل الفشل
        for test, failure in self.test_result.failures:
            testcase = ET.SubElement(testsuite, 'testcase')
            testcase.set('name', str(test))
            testcase.set('classname', test.__class__.__name__)
            testcase.set('time', '0')
            
            fail = ET.SubElement(testcase, 'failure')
            fail.set('message', 'Test failed')
            fail.text = failure
        
        # تعيين تفاصيل الأخطاء
        for test, error in self.test_result.errors:
            testcase = ET.SubElement(testsuite, 'testcase')
            testcase.set('name', str(test))
            testcase.set('classname', test.__class__.__name__)
            testcase.set('time', '0')
            
            err = ET.SubElement(testcase, 'error')
            err.set('message', 'Test error')
            err.text = error
        
        # إضافة الاختبارات الناجحة
        passed_count = self.test_result.testsRun - len(self.test_result.failures) - len(self.test_result.errors)
        if passed_count > 0:
            # لا نعرف بالضبط أي الاختبارات نجحت، لذا نضيف فقط إجمالي الناجحين
            testcase = ET.SubElement(testsuite, 'testcase')
            testcase.set('name', 'Passed Tests')
            testcase.set('classname', 'PassedTests')
            testcase.set('time', '0')
        
        # كتابة الملف
        tree = ET.ElementTree(root)
        tree.write(xml_file_path, encoding='utf-8', xml_declaration=True)


class Command(BaseCommand):
    help = 'تشغيل اختبارات النظام وإنشاء تقرير مفصل بالنتائج'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'test_labels',
            nargs='*',
            help='حزم ونماذج ودوال الاختبار التي سيتم تشغيلها'
        )
    
    def handle(self, *args, **options):
        # استخدام رانر مخصص للاختبارات
        test_runner = TestReportRunner(
            verbosity=options['verbosity'],
            interactive=options['interactive'],
            keepdb=options.get('keepdb', False),
            debug_mode=options.get('debug_mode', False),
            debug_sql=options.get('debug_sql', False),
            parallel=options.get('parallel', 0),
            tags=options.get('tags', None),
            exclude_tags=options.get('exclude_tags', None),
            test_name_patterns=options.get('test_name_patterns', None),
        )
        
        # تشغيل الاختبارات
        failures = test_runner.run_tests(options['test_labels'] or None)
        
        if failures:
            self.stdout.write(self.style.ERROR('بعض الاختبارات فشلت!'))
        else:
            self.stdout.write(self.style.SUCCESS('جميع الاختبارات نجحت!'))
        
        # إرجاع عدد الاختبارات الفاشلة كقيمة خروج
        sys.exit(bool(failures)) 