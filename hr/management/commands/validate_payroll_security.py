"""
أمر للتحقق من أمان نظام الرواتب
"""
from django.core.management.base import BaseCommand
from hr.services.secure_payroll_service import SecurePayrollService
from hr.models import SalaryComponentTemplate, Payroll
from financial.models import ChartOfAccounts


class Command(BaseCommand):
    help = 'التحقق من أمان نظام الرواتب والتأكد من عدم وجود ثغرات'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix-templates',
            action='store_true',
            help='إصلاح القوالب التي تستخدم حسابات غير آمنة',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🔒 فحص أمان نظام الرواتب')
        )
        self.stdout.write('=' * 60)
        
        # 1. فحص الحسابات المسموحة
        self._check_allowed_accounts()
        
        # 2. فحص القوالب
        self._check_templates(fix=options['fix_templates'])
        
        # 3. فحص الرواتب الموجودة
        self._check_existing_payrolls()
        
        # 4. عرض التوصيات
        self._show_recommendations()

    def _check_allowed_accounts(self):
        """فحص الحسابات المسموحة"""
        self.stdout.write('\n🏦 فحص الحسابات المسموحة:')
        
        allowed_accounts = SecurePayrollService.ALLOWED_PAYROLL_ACCOUNTS
        missing_accounts = []
        existing_accounts = []
        
        for code, name in allowed_accounts.items():
            account = ChartOfAccounts.objects.filter(code=code).first()
            if account:
                existing_accounts.append(f"{code} - {account.name}")
            else:
                missing_accounts.append(f"{code} - {name}")
        
        self.stdout.write(f'✅ الحسابات الموجودة ({len(existing_accounts)}):')
        for account in existing_accounts:
            self.stdout.write(f'  {account}')
        
        if missing_accounts:
            self.stdout.write(f'\n❌ الحسابات المفقودة ({len(missing_accounts)}):')
            for account in missing_accounts:
                self.stdout.write(
                    self.style.ERROR(f'  {account}')
                )
        else:
            self.stdout.write(
                self.style.SUCCESS('\n✅ جميع الحسابات المطلوبة موجودة')
            )

    def _check_templates(self, fix=False):
        """فحص القوالب"""
        self.stdout.write('\n📋 فحص قوالب مكونات الراتب:')
        
        templates = SalaryComponentTemplate.objects.all()
        safe_templates = []
        unsafe_templates = []
        
        allowed_accounts = SecurePayrollService.ALLOWED_PAYROLL_ACCOUNTS
        
        for template in templates:
            account_code = template.default_account_code
            
            if account_code in allowed_accounts:
                safe_templates.append(template)
            else:
                unsafe_templates.append(template)
        
        self.stdout.write(f'✅ القوالب الآمنة ({len(safe_templates)}):')
        for template in safe_templates:
            self.stdout.write(
                f'  {template.name} → {template.default_account_code}'
            )
        
        if unsafe_templates:
            self.stdout.write(f'\n⚠️ القوالب غير الآمنة ({len(unsafe_templates)}):')
            for template in unsafe_templates:
                self.stdout.write(
                    self.style.WARNING(
                        f'  {template.name} → {template.default_account_code}'
                    )
                )
            
            if fix:
                self._fix_unsafe_templates(unsafe_templates)
        else:
            self.stdout.write(
                self.style.SUCCESS('\n✅ جميع القوالب تستخدم حسابات آمنة')
            )

    def _fix_unsafe_templates(self, unsafe_templates):
        """إصلاح القوالب غير الآمنة"""
        self.stdout.write('\n🔧 إصلاح القوالب غير الآمنة:')
        
        component_mapping = SecurePayrollService.COMPONENT_ACCOUNT_MAPPING
        fallback_accounts = SecurePayrollService.DEFAULT_FALLBACK_ACCOUNTS
        
        fixed_count = 0
        
        for template in unsafe_templates:
            # البحث عن الحساب الصحيح
            correct_account = component_mapping.get(template.code)
            
            if not correct_account:
                # استخدام الحساب الافتراضي
                correct_account = fallback_accounts.get(template.component_type)
            
            if correct_account:
                old_account = template.default_account_code
                template.default_account_code = correct_account
                template.save()
                fixed_count += 1
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✅ {template.name}: {old_account} → {correct_account}'
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f'  ❌ لا يمكن إصلاح: {template.name}'
                    )
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'\n🎉 تم إصلاح {fixed_count} قالب')
        )

    def _check_existing_payrolls(self):
        """فحص الرواتب الموجودة"""
        self.stdout.write('\n💰 فحص الرواتب الموجودة:')
        
        recent_payrolls = Payroll.objects.filter(status='paid').order_by('-id')[:5]
        
        if not recent_payrolls.exists():
            self.stdout.write('  لا توجد رواتب مدفوعة للفحص')
            return
        
        for payroll in recent_payrolls:
            validation = SecurePayrollService.validate_payroll_accounts(payroll)
            
            status = '✅' if validation['is_valid'] else '❌'
            self.stdout.write(
                f'  {status} راتب #{payroll.id} - {payroll.employee.get_full_name_ar()}'
            )
            
            if validation['errors']:
                for error in validation['errors']:
                    self.stdout.write(
                        self.style.ERROR(f'    ❌ {error}')
                    )
            
            if validation['warnings']:
                for warning in validation['warnings']:
                    self.stdout.write(
                        self.style.WARNING(f'    ⚠️ {warning}')
                    )

    def _show_recommendations(self):
        """عرض التوصيات الأمنية"""
        self.stdout.write('\n💡 التوصيات الأمنية:')
        self.stdout.write('=' * 40)
        
        recommendations = [
            '1. استخدم SecurePayrollService لإنشاء القيود المحاسبية',
            '2. تحقق من القوالب دورياً باستخدام --fix-templates',
            '3. لا تسمح بإنشاء حسابات جديدة تلقائياً',
            '4. راجع الرواتب المدفوعة للتأكد من صحة الحسابات',
            '5. استخدم الحسابات المحددة مسبقاً فقط',
        ]
        
        for recommendation in recommendations:
            self.stdout.write(f'  {recommendation}')
        
        # عرض ملخص الحسابات المسموحة
        summary = SecurePayrollService.get_allowed_accounts_summary()
        
        self.stdout.write(f'\n📊 ملخص النظام الآمن:')
        self.stdout.write(f'  - إجمالي الحسابات المسموحة: {summary["total_allowed"]}')
        self.stdout.write(f'  - قوالب المكونات: {len(summary["component_mapping"])}')
        self.stdout.write(f'  - الحسابات الافتراضية: {len(summary["fallback_accounts"])}')
        
        self.stdout.write(
            self.style.SUCCESS('\n🔒 النظام الآمن جاهز للاستخدام!')
        )
