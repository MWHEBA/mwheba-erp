"""
أمر Django لفحص تكامل البيانات المالية
يفحص الربط بين الفواتير والدفعات والقيود المحاسبية
"""
from django.core.management.base import BaseCommand
from django.db.models import Sum, Q, Count
from django.utils import timezone
from decimal import Decimal
import logging

from sale.models import Sale, SalePayment
from purchase.models import Purchase, PurchasePayment
from financial.models import JournalEntry, JournalEntryLine, ChartOfAccounts
from financial.models.audit_trail import AuditTrail

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'فحص تكامل البيانات المالية والتأكد من صحة الربط بين الفواتير والدفعات والقيود'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='محاولة إصلاح المشاكل المكتشفة تلقائياً'
        )
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='عرض تفاصيل مفصلة للمشاكل'
        )
        parser.add_argument(
            '--export',
            type=str,
            help='تصدير النتائج إلى ملف CSV'
        )

    def handle(self, *args, **options):
        self.fix_issues = options['fix']
        self.detailed = options['detailed']
        self.export_file = options.get('export')
        
        self.stdout.write(
            self.style.SUCCESS('🔍 بدء فحص تكامل البيانات المالية...\n')
        )
        
        # إحصائيات عامة
        self.issues_found = 0
        self.issues_fixed = 0
        self.report_data = []
        
        # تشغيل جميع الفحوصات
        self.check_invoice_journal_entries()
        self.check_payment_financial_status()
        self.check_journal_entry_balance()
        self.check_orphaned_records()
        self.check_duplicate_entries()
        self.check_account_balances()
        
        # عرض الملخص النهائي
        self.display_summary()
        
        # تصدير النتائج إذا طُلب ذلك
        if self.export_file:
            self.export_results()

    def check_invoice_journal_entries(self):
        """فحص ربط الفواتير بالقيود المحاسبية"""
        self.stdout.write('\n📋 فحص ربط الفواتير بالقيود المحاسبية...')
        
        # فحص فواتير المبيعات
        sales_without_entries = Sale.objects.filter(
            status='confirmed',
            journal_entry__isnull=True
        )
        
        if sales_without_entries.exists():
            count = sales_without_entries.count()
            self.issues_found += count
            self.stdout.write(
                self.style.WARNING(f'⚠️  {count} فاتورة مبيعات مؤكدة بدون قيد محاسبي')
            )
            
            if self.detailed:
                for sale in sales_without_entries[:10]:  # أول 10 فقط
                    self.stdout.write(f'   - فاتورة {sale.number} - {sale.date}')
            
            self.report_data.append({
                'type': 'فواتير مبيعات بدون قيود',
                'count': count,
                'severity': 'متوسط'
            })
        
        # فحص فواتير المشتريات
        purchases_without_entries = Purchase.objects.filter(
            status='confirmed',
            journal_entry__isnull=True
        )
        
        if purchases_without_entries.exists():
            count = purchases_without_entries.count()
            self.issues_found += count
            self.stdout.write(
                self.style.WARNING(f'⚠️  {count} فاتورة مشتريات مؤكدة بدون قيد محاسبي')
            )
            
            if self.detailed:
                for purchase in purchases_without_entries[:10]:
                    self.stdout.write(f'   - فاتورة {purchase.number} - {purchase.date}')
            
            self.report_data.append({
                'type': 'فواتير مشتريات بدون قيود',
                'count': count,
                'severity': 'متوسط'
            })

    def check_payment_financial_status(self):
        """فحص حالة الربط المالي للدفعات"""
        self.stdout.write('\n💳 فحص حالة الربط المالي للدفعات...')
        
        # دفعات مرحّلة لكن غير مربوطة مالياً
        problematic_sale_payments = SalePayment.objects.filter(
            status='posted',
            financial_status__in=['pending', 'failed']
        )
        
        problematic_purchase_payments = PurchasePayment.objects.filter(
            status='posted',
            financial_status__in=['pending', 'failed']
        )
        
        total_problematic = problematic_sale_payments.count() + problematic_purchase_payments.count()
        
        if total_problematic > 0:
            self.issues_found += total_problematic
            self.stdout.write(
                self.style.ERROR(f'❌ {total_problematic} دفعة مرحّلة لكن غير مربوطة مالياً')
            )
            
            if self.detailed:
                for payment in problematic_sale_payments[:5]:
                    self.stdout.write(f'   - دفعة مبيعات #{payment.id} - فاتورة {payment.sale.number}')
                for payment in problematic_purchase_payments[:5]:
                    self.stdout.write(f'   - دفعة مشتريات #{payment.id} - فاتورة {payment.purchase.number}')
            
            self.report_data.append({
                'type': 'دفعات مرحّلة غير مربوطة',
                'count': total_problematic,
                'severity': 'عالي'
            })
        
        # دفعات مربوطة لكن بدون قيد محاسبي
        synced_without_entry_sales = SalePayment.objects.filter(
            financial_status='synced',
            financial_transaction__isnull=True
        )
        
        synced_without_entry_purchases = PurchasePayment.objects.filter(
            financial_status='synced',
            financial_transaction__isnull=True
        )
        
        total_synced_without_entry = synced_without_entry_sales.count() + synced_without_entry_purchases.count()
        
        if total_synced_without_entry > 0:
            self.issues_found += total_synced_without_entry
            self.stdout.write(
                self.style.ERROR(f'❌ {total_synced_without_entry} دفعة مربوطة لكن بدون قيد محاسبي')
            )
            
            self.report_data.append({
                'type': 'دفعات مربوطة بدون قيود',
                'count': total_synced_without_entry,
                'severity': 'عالي'
            })

    def check_journal_entry_balance(self):
        """فحص توازن القيود المحاسبية"""
        self.stdout.write('\n⚖️  فحص توازن القيود المحاسبية...')
        
        unbalanced_entries = []
        
        for entry in JournalEntry.objects.filter(status='posted'):
            if not entry.is_balanced:
                unbalanced_entries.append(entry)
                self.issues_found += 1
        
        if unbalanced_entries:
            count = len(unbalanced_entries)
            self.stdout.write(
                self.style.ERROR(f'❌ {count} قيد محاسبي غير متوازن')
            )
            
            if self.detailed:
                for entry in unbalanced_entries[:10]:
                    self.stdout.write(
                        f'   - قيد {entry.number} - الفرق: {entry.difference}'
                    )
            
            self.report_data.append({
                'type': 'قيود غير متوازنة',
                'count': count,
                'severity': 'عالي جداً'
            })

    def check_orphaned_records(self):
        """فحص السجلات المعزولة"""
        self.stdout.write('\n🔗 فحص السجلات المعزولة...')
        
        # قيود محاسبية بدون مرجع
        orphaned_entries = JournalEntry.objects.filter(
            Q(reference__isnull=True) | Q(reference='')
        ).exclude(entry_type='manual')
        
        if orphaned_entries.exists():
            count = orphaned_entries.count()
            self.issues_found += count
            self.stdout.write(
                self.style.WARNING(f'⚠️  {count} قيد محاسبي بدون مرجع')
            )
            
            self.report_data.append({
                'type': 'قيود بدون مرجع',
                'count': count,
                'severity': 'منخفض'
            })
        
        # بنود قيود بدون حساب صحيح
        invalid_lines = JournalEntryLine.objects.filter(
            account__isnull=True
        )
        
        if invalid_lines.exists():
            count = invalid_lines.count()
            self.issues_found += count
            self.stdout.write(
                self.style.ERROR(f'❌ {count} بند قيد بدون حساب صحيح')
            )
            
            self.report_data.append({
                'type': 'بنود قيود بدون حساب',
                'count': count,
                'severity': 'عالي'
            })

    def check_duplicate_entries(self):
        """فحص القيود المكررة"""
        self.stdout.write('\n🔄 فحص القيود المكررة...')
        
        # البحث عن قيود بنفس المرجع والتاريخ
        duplicates = JournalEntry.objects.values(
            'reference', 'date'
        ).annotate(
            count=Count('id')
        ).filter(
            count__gt=1,
            reference__isnull=False
        ).exclude(reference='')
        
        if duplicates.exists():
            total_duplicates = sum(d['count'] - 1 for d in duplicates)
            self.issues_found += total_duplicates
            self.stdout.write(
                self.style.WARNING(f'⚠️  {total_duplicates} قيد مكرر محتمل')
            )
            
            if self.detailed:
                for dup in duplicates[:5]:
                    self.stdout.write(
                        f'   - مرجع {dup["reference"]} - {dup["date"]} ({dup["count"]} مرات)'
                    )
            
            self.report_data.append({
                'type': 'قيود مكررة محتملة',
                'count': total_duplicates,
                'severity': 'متوسط'
            })

    def check_account_balances(self):
        """فحص أرصدة الحسابات"""
        self.stdout.write('\n💰 فحص أرصدة الحسابات...')
        
        # فحص الحسابات النقدية بأرصدة سالبة
        cash_accounts = ChartOfAccounts.objects.filter(
            Q(name__icontains='صندوق') | Q(name__icontains='خزينة') | Q(name__icontains='بنك')
        )
        
        negative_cash_accounts = []
        for account in cash_accounts:
            try:
                balance = account.get_balance()
                if balance < 0:
                    negative_cash_accounts.append((account, balance))
                    self.issues_found += 1
            except:
                continue
        
        if negative_cash_accounts:
            count = len(negative_cash_accounts)
            self.stdout.write(
                self.style.WARNING(f'⚠️  {count} حساب نقدي برصيد سالب')
            )
            
            if self.detailed:
                for account, balance in negative_cash_accounts[:5]:
                    self.stdout.write(
                        f'   - {account.name} ({account.code}): {balance}'
                    )
            
            self.report_data.append({
                'type': 'حسابات نقدية برصيد سالب',
                'count': count,
                'severity': 'متوسط'
            })

    def display_summary(self):
        """عرض ملخص النتائج"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('📊 ملخص فحص تكامل البيانات المالية'))
        self.stdout.write('='*60)
        
        if self.issues_found == 0:
            self.stdout.write(
                self.style.SUCCESS('✅ تم فحص النظام بنجاح - لا توجد مشاكل!')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'⚠️  تم اكتشاف {self.issues_found} مشكلة')
            )
            
            if self.issues_fixed > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'✅ تم إصلاح {self.issues_fixed} مشكلة')
                )
        
        # عرض تفاصيل المشاكل حسب الأولوية
        severity_order = ['عالي جداً', 'عالي', 'متوسط', 'منخفض']
        
        for severity in severity_order:
            issues_of_severity = [r for r in self.report_data if r['severity'] == severity]
            if issues_of_severity:
                self.stdout.write(f'\n🔴 مشاكل بأولوية {severity}:')
                for issue in issues_of_severity:
                    self.stdout.write(f'   - {issue["type"]}: {issue["count"]}')
        
        # تسجيل النتائج في سجل التدقيق
        AuditTrail.log_action(
            action='integrity_check',
            entity_type='system',
            entity_id=0,
            user=None,
            description=f'فحص تكامل البيانات المالية - {self.issues_found} مشكلة',
            metadata={
                'issues_found': self.issues_found,
                'issues_fixed': self.issues_fixed,
                'report_data': self.report_data,
                'timestamp': timezone.now().isoformat()
            }
        )

    def export_results(self):
        """تصدير النتائج إلى ملف CSV"""
        try:
            import csv
            
            with open(self.export_file, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['نوع المشكلة', 'العدد', 'الأولوية', 'التاريخ']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for issue in self.report_data:
                    writer.writerow({
                        'نوع المشكلة': issue['type'],
                        'العدد': issue['count'],
                        'الأولوية': issue['severity'],
                        'التاريخ': timezone.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
            
            self.stdout.write(
                self.style.SUCCESS(f'📄 تم تصدير النتائج إلى {self.export_file}')
            )
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ خطأ في تصدير النتائج: {str(e)}')
            )
