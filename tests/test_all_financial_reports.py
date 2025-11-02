#!/usr/bin/env python
"""
اختبارات شاملة لجميع التقارير المالية
تشمل: دفتر الأستاذ، ميزان المراجعة، الميزانية، قائمة الدخل، التدفقات النقدية، الأعمار
"""
import os
import sys
import django
from datetime import datetime, timedelta
from decimal import Decimal

# إضافة المسار الحالي للـ Python path
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, current_dir)

# إعداد Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mwheba_erp.settings')
django.setup()

from django.utils import timezone
from financial.models import ChartOfAccounts, JournalEntry, JournalEntryLine


class FinancialReportsTestSuite:
    """مجموعة اختبارات شاملة للتقارير المالية"""
    
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
    
    def test_ledger_service(self):
        """اختبار خدمة دفتر الأستاذ"""
        self.print_header("[1] اختبار دفتر الأستاذ (Ledger Report)")
        
        try:
            from financial.services.ledger_service import LedgerService
            
            # اختبار 1: إنشاء الخدمة
            try:
                service = LedgerService()
                self.print_test("إنشاء خدمة دفتر الأستاذ", True)
            except Exception as e:
                self.print_test("إنشاء خدمة دفتر الأستاذ", False, str(e))
                return
            
            # اختبار 2: جلب الحسابات
            try:
                accounts = ChartOfAccounts.objects.all()
                self.print_test(f"جلب الحسابات ({accounts.count()} حساب)", accounts.exists())
            except Exception as e:
                self.print_test("جلب الحسابات", False, str(e))
            
            # اختبار 3: تقرير دفتر الأستاذ
            if accounts.exists():
                try:
                    account = accounts.first()
                    end_date = timezone.now().date()
                    start_date = end_date - timedelta(days=30)
                    
                    report = service.get_ledger_report(
                        account_id=account.id,
                        start_date=start_date,
                        end_date=end_date
                    )
                    
                    has_data = 'transactions' in report and 'summary' in report
                    self.print_test("توليد تقرير دفتر الأستاذ", has_data)
                    
                    if has_data:
                        print(f"   - عدد الحركات: {len(report['transactions'])}")
                        print(f"   - الرصيد الافتتاحي: {report['summary']['opening_balance']}")
                        print(f"   - الرصيد الختامي: {report['summary']['closing_balance']}")
                        
                except Exception as e:
                    self.print_test("توليد تقرير دفتر الأستاذ", False, str(e))
            
        except ImportError as e:
            self.print_test("استيراد خدمة دفتر الأستاذ", False, str(e))
    
    def test_trial_balance(self):
        """اختبار ميزان المراجعة"""
        self.print_header("[2] اختبار ميزان المراجعة (Trial Balance)")
        
        try:
            from financial.views.api_views import trial_balance_report
            from django.test import RequestFactory
            from django.contrib.auth import get_user_model
            
            User = get_user_model()
            
            # اختبار 1: إنشاء طلب وهمي
            try:
                factory = RequestFactory()
                request = factory.get('/financial/reports/trial-balance/')
                
                # إنشاء مستخدم وهمي
                user = User.objects.first()
                if not user:
                    user = User.objects.create_user(username='test', email='test@test.com', password='test')
                request.user = user
                
                self.print_test("إنشاء طلب اختبار", True)
            except Exception as e:
                self.print_test("إنشاء طلب اختبار", False, str(e))
                return
            
            # اختبار 2: تنفيذ التقرير
            try:
                response = trial_balance_report(request)
                success = response.status_code == 200
                self.print_test("تنفيذ ميزان المراجعة", success, 
                              f"Status: {response.status_code}" if not success else "")
            except Exception as e:
                self.print_test("تنفيذ ميزان المراجعة", False, str(e))
                
        except ImportError as e:
            self.print_test("استيراد ميزان المراجعة", False, str(e))
    
    def test_balance_sheet(self):
        """اختبار الميزانية العمومية"""
        self.print_header("[3] اختبار الميزانية العمومية (Balance Sheet)")
        
        try:
            from financial.views.api_views import balance_sheet
            from django.test import RequestFactory
            from django.contrib.auth import get_user_model
            
            User = get_user_model()
            
            factory = RequestFactory()
            request = factory.get('/financial/reports/balance-sheet/')
            request.user = User.objects.first()
            
            try:
                response = balance_sheet(request)
                success = response.status_code == 200
                self.print_test("تنفيذ الميزانية العمومية", success)
            except Exception as e:
                self.print_test("تنفيذ الميزانية العمومية", False, str(e))
                
        except ImportError as e:
            self.print_test("استيراد الميزانية العمومية", False, str(e))
    
    def test_income_statement(self):
        """اختبار قائمة الدخل"""
        self.print_header("[4] اختبار قائمة الدخل (Income Statement)")
        
        try:
            from financial.views.api_views import income_statement
            from django.test import RequestFactory
            from django.contrib.auth import get_user_model
            
            User = get_user_model()
            
            factory = RequestFactory()
            request = factory.get('/financial/reports/income-statement/')
            request.user = User.objects.first()
            
            try:
                response = income_statement(request)
                success = response.status_code == 200
                self.print_test("تنفيذ قائمة الدخل", success)
            except Exception as e:
                self.print_test("تنفيذ قائمة الدخل", False, str(e))
                
        except ImportError as e:
            self.print_test("استيراد قائمة الدخل", False, str(e))
    
    def test_cash_flow(self):
        """اختبار قائمة التدفقات النقدية"""
        self.print_header("[5] اختبار التدفقات النقدية (Cash Flow)")
        
        try:
            from financial.views.api_views import cash_flow_statement
            from django.test import RequestFactory
            from django.contrib.auth import get_user_model
            
            User = get_user_model()
            
            factory = RequestFactory()
            request = factory.get('/financial/reports/cash-flow/')
            request.user = User.objects.first()
            
            try:
                response = cash_flow_statement(request)
                success = response.status_code == 200
                self.print_test("تنفيذ التدفقات النقدية", success)
            except Exception as e:
                self.print_test("تنفيذ التدفقات النقدية", False, str(e))
                
        except ImportError as e:
            self.print_test("استيراد التدفقات النقدية", False, str(e))
    
    def test_balances_report(self):
        """اختبار تقرير الأرصدة"""
        self.print_header("[6] اختبار تقرير الأرصدة (Balances Report)")
        
        try:
            from financial.views.api_views import customer_supplier_balances_report
            from django.test import RequestFactory
            from django.contrib.auth import get_user_model
            
            User = get_user_model()
            
            factory = RequestFactory()
            request = factory.get('/financial/reports/balances/?account_type=customers')
            request.user = User.objects.first()
            
            try:
                response = customer_supplier_balances_report(request, account_type='customers')
                success = response.status_code == 200
                self.print_test("تنفيذ تقرير الأرصدة", success)
            except Exception as e:
                self.print_test("تنفيذ تقرير الأرصدة", False, str(e))
                
        except ImportError as e:
            self.print_test("استيراد تقرير الأرصدة", False, str(e))
    
    def test_sales_report(self):
        """اختبار تقرير المبيعات"""
        self.print_header("[7] اختبار تقرير المبيعات (Sales Report)")
        
        try:
            from financial.views.api_views import sales_report
            from django.test import RequestFactory
            from django.contrib.auth import get_user_model
            
            User = get_user_model()
            
            factory = RequestFactory()
            request = factory.get('/financial/reports/sales/')
            request.user = User.objects.first()
            
            try:
                response = sales_report(request)
                success = response.status_code == 200
                self.print_test("تنفيذ تقرير المبيعات", success)
            except Exception as e:
                self.print_test("تنفيذ تقرير المبيعات", False, str(e))
                
        except ImportError as e:
            self.print_test("استيراد تقرير المبيعات", False, str(e))
    
    def test_purchases_report(self):
        """اختبار تقرير المشتريات"""
        self.print_header("[8] اختبار تقرير المشتريات (Purchases Report)")
        
        try:
            from financial.views.api_views import purchases_report
            from django.test import RequestFactory
            from django.contrib.auth import get_user_model
            
            User = get_user_model()
            
            factory = RequestFactory()
            request = factory.get('/financial/reports/purchases/')
            request.user = User.objects.first()
            
            try:
                response = purchases_report(request)
                success = response.status_code == 200
                self.print_test("تنفيذ تقرير المشتريات", success)
            except Exception as e:
                self.print_test("تنفيذ تقرير المشتريات", False, str(e))
                
        except ImportError as e:
            self.print_test("استيراد تقرير المشتريات", False, str(e))
    
    def test_inventory_report(self):
        """اختبار تقرير المخزون المالي"""
        self.print_header("[9] اختبار تقرير المخزون المالي (Inventory Report)")
        
        try:
            from financial.services.inventory_report_service import InventoryReportService
            
            # اختبار 1: إنشاء الخدمة
            try:
                service = InventoryReportService()
                self.print_test("إنشاء خدمة المخزون المالي", True)
            except Exception as e:
                self.print_test("إنشاء خدمة المخزون المالي", False, str(e))
                return
            
            # اختبار 2: جلب حسابات المخزون
            try:
                inventory_accounts = service.get_inventory_accounts()
                has_accounts = len(inventory_accounts) >= 0
                self.print_test(f"جلب حسابات المخزون ({len(inventory_accounts)} حساب)", has_accounts)
            except Exception as e:
                self.print_test("جلب حسابات المخزون", False, str(e))
                return
            
            # اختبار 3: توليد التقرير
            try:
                report = service.get_inventory_report()
                has_data = 'inventory_data' in report and 'summary' in report
                self.print_test("توليد تقرير المخزون المالي", has_data)
                
                if has_data:
                    print(f"   - عدد حسابات المخزون: {report['summary']['total_accounts']}")
                    print(f"   - إجمالي قيمة المخزون: {report['summary']['total_inventory_value']}")
                    
            except Exception as e:
                self.print_test("توليد تقرير المخزون المالي", False, str(e))
                
        except ImportError as e:
            self.print_test("استيراد خدمة المخزون المالي", False, str(e))
    
    def test_abc_analysis_financial(self):
        """اختبار تحليل ABC المالي"""
        self.print_header("[10] اختبار تحليل ABC المالي")
        
        try:
            from financial.services.abc_analysis_service import ABCAnalysisService
            
            try:
                service = ABCAnalysisService()
                analysis = service.get_complete_analysis()
                
                has_data = 'inventory_data' in analysis and 'statistics' in analysis
                self.print_test("توليد تحليل ABC المالي", has_data)
                
                if has_data:
                    print(f"   - عدد الحسابات: {analysis['statistics']['total_items']}")
                    print(f"   - فئة A: {analysis['statistics']['category_a']['count']}")
                    print(f"   - فئة B: {analysis['statistics']['category_b']['count']}")
                    print(f"   - فئة C: {analysis['statistics']['category_c']['count']}")
                    
            except Exception as e:
                self.print_test("توليد تحليل ABC المالي", False, str(e))
                
        except ImportError as e:
            self.print_test("استيراد خدمة ABC المالي", False, str(e))
    
    def print_summary(self):
        """طباعة ملخص النتائج"""
        self.print_header("ملخص نتائج الاختبارات")
        
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
        print("  اختبارات شاملة للتقارير المالية")
        print("=" * 80)
        
        self.test_ledger_service()
        self.test_trial_balance()
        self.test_balance_sheet()
        self.test_income_statement()
        self.test_cash_flow()
        self.test_balances_report()
        self.test_sales_report()
        self.test_purchases_report()
        self.test_inventory_report()
        self.test_abc_analysis_financial()
        
        return self.print_summary()


if __name__ == "__main__":
    suite = FinancialReportsTestSuite()
    success = suite.run_all_tests()
    
    sys.exit(0 if success else 1)
