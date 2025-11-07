"""
Command لمعالجة الزيادات السنوية التلقائية
متوافق مع بيئة cPanel
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings
from hr.models import Contract, ContractIncrease, SalaryComponent
from datetime import date
from decimal import Decimal
import logging

# إعداد Logger
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'معالجة الزيادات السنوية المستحقة - متوافق مع cPanel'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='تشغيل تجريبي بدون حفظ في قاعدة البيانات',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='عرض تفاصيل أكثر',
        )
    
    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        verbose = options.get('verbose', False)
        
        start_time = timezone.now()
        self.stdout.write(f"{'='*60}")
        self.stdout.write(f"بدء معالجة الزيادات السنوية")
        self.stdout.write(f"الوقت: {start_time}")
        self.stdout.write(f"وضع التجربة: {'نعم' if dry_run else 'لا'}")
        self.stdout.write(f"{'='*60}\n")
        
        try:
            # إحصائيات
            total_processed = 0
            total_created = 0
            total_errors = 0
            errors_list = []
            
            # البحث عن العقود المستحقة للزيادة
            eligible_contracts = self._get_eligible_contracts()
            
            self.stdout.write(f"✓ تم العثور على {eligible_contracts.count()} عقد مستحق للزيادة\n")
            
            if eligible_contracts.count() == 0:
                self.stdout.write(self.style.WARNING("لا توجد عقود مستحقة للزيادة اليوم"))
                return
            
            # معالجة كل عقد
            for contract in eligible_contracts:
                total_processed += 1
                
                try:
                    if verbose:
                        self.stdout.write(f"\n--- معالجة العقد #{contract.contract_number} ---")
                        emp_name = f"{contract.employee.first_name_ar} {contract.employee.last_name_ar}"
                        self.stdout.write(f"الموظف: {emp_name}")
                        self.stdout.write(f"الراتب الحالي: {contract.basic_salary}")
                        self.stdout.write(f"نسبة الزيادة: {contract.annual_increase_percentage}%")
                        self.stdout.write(f"التكرار: {contract.get_increase_frequency_display()}")
                    
                    # إنشاء وتطبيق الزيادة
                    if not dry_run:
                        increase = self._create_contract_increase(contract)
                        total_created += 1
                        
                        if verbose:
                            # إعادة تحميل العقد لجلب البنود المحدثة
                            contract.refresh_from_db()
                            self.stdout.write(self.style.SUCCESS(
                                f"✓ تم إضافة بند زيادة {increase.increase_percentage}% = {increase.increase_amount} جنيه"
                            ))
                            self.stdout.write(self.style.SUCCESS(
                                f"  الراتب الأساسي: {contract.basic_salary} (ثابت) | "
                                f"الإجمالي: {contract.total_earnings}"
                            ))
                    else:
                        # حساب فقط بدون حفظ
                        percentage = self._calculate_increase_percentage(contract)
                        amount = contract.basic_salary * (percentage / 100)
                        
                        if verbose:
                            self.stdout.write(self.style.WARNING(f"⚠ تجريبي: سيتم إنشاء زيادة {percentage}% = {amount} جنيه"))
                        
                        total_created += 1
                
                except Exception as e:
                    total_errors += 1
                    error_msg = f"خطأ في العقد {contract.contract_number}: {str(e)}"
                    errors_list.append(error_msg)
                    logger.error(error_msg)
                    
                    if verbose:
                        self.stdout.write(self.style.ERROR(f"✗ {error_msg}"))
            
            # النتائج النهائية
            end_time = timezone.now()
            duration = (end_time - start_time).total_seconds()
            
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(self.style.SUCCESS("✓ اكتملت المعالجة"))
            self.stdout.write(f"{'='*60}")
            self.stdout.write(f"إجمالي العقود المعالجة: {total_processed}")
            self.stdout.write(f"الزيادات المطبقة: {total_created}")
            self.stdout.write(f"الأخطاء: {total_errors}")
            self.stdout.write(f"المدة: {duration:.2f} ثانية")
            self.stdout.write(f"{'='*60}")
            if not dry_run and total_created > 0:
                self.stdout.write(self.style.SUCCESS(
                    f"\n✓ تم إضافة {total_created} بند زيادة سنوية للرواتب"
                ))
                self.stdout.write(self.style.SUCCESS(
                    "  ملاحظة: الراتب الأساسي ثابت، الزيادات في بنود منفصلة"
                ))
            self.stdout.write(f"{'='*60}\n")
            
            # إرسال تقرير بالبريد (في حالة الإنتاج فقط)
            if not dry_run and total_created > 0:
                self._send_notification_email(total_created, total_errors, errors_list)
            
            # Log النتائج
            logger.info(
                f"Annual increases processed: {total_created} created, "
                f"{total_errors} errors, duration: {duration:.2f}s"
            )
            
        except Exception as e:
            error_msg = f"خطأ عام في المعالجة: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.stdout.write(self.style.ERROR(f"\n✗ {error_msg}"))
            raise
    
    def _get_eligible_contracts(self):
        """البحث عن العقود المستحقة للزيادة"""
        today = date.today()
        
        contracts = Contract.objects.filter(
            has_annual_increase=True,
            status='active',
            next_increase_date__lte=today,
            annual_increase_percentage__isnull=False,
            annual_increase_percentage__gt=0
        ).select_related('employee', 'job_title', 'department')
        
        return contracts
    
    def _calculate_increase_percentage(self, contract):
        """حساب نسبة الزيادة حسب التكرار"""
        annual_percentage = contract.annual_increase_percentage
        
        # تقسيم النسبة حسب التكرار
        frequency_divisor = {
            'annual': 1,
            'semi_annual': 2,
            'quarterly': 4,
            'monthly': 12,
        }
        
        divisor = frequency_divisor.get(contract.increase_frequency, 1)
        percentage = annual_percentage / divisor
        
        return percentage
    
    @transaction.atomic
    def _create_contract_increase(self, contract):
        """إنشاء وتطبيق زيادة للعقد تلقائياً كـ SalaryComponent"""
        # حساب النسبة
        percentage = self._calculate_increase_percentage(contract)
        
        # التحقق من عدم وجود زيادة بنفس التاريخ
        existing = ContractIncrease.objects.filter(
            contract=contract,
            scheduled_date=contract.next_increase_date,
            status__in=['pending', 'approved', 'applied']
        ).exists()
        
        if existing:
            raise Exception("يوجد زيادة بنفس التاريخ بالفعل")
        
        # حساب قيمة الزيادة من الراتب الإجمالي (الأساسي + البنود)
        current_total = contract.total_earnings
        increase_amount = current_total * (percentage / 100)
        
        # حساب رقم الزيادة
        last_increase = ContractIncrease.objects.filter(contract=contract).order_by('-increase_number').first()
        increase_number = (last_increase.increase_number + 1) if last_increase else 1
        
        # حساب عدد الأشهر من بداية العقد
        months_from_start = ((contract.next_increase_date.year - contract.start_date.year) * 12 + 
                            (contract.next_increase_date.month - contract.start_date.month))
        
        # إنشاء الزيادة (للتوثيق)
        # استخدام created_by من العقد أو None
        created_by = contract.created_by if hasattr(contract, 'created_by') else None
        
        increase = ContractIncrease.objects.create(
            contract=contract,
            increase_number=increase_number,
            increase_type='percentage',
            increase_percentage=percentage,
            increase_amount=increase_amount,
            months_from_start=months_from_start,
            scheduled_date=contract.next_increase_date,
            status='applied',  # مطبقة مباشرة
            applied_date=date.today(),
            applied_amount=increase_amount,
            created_by=created_by,
            notes=f'زيادة سنوية تلقائية - {contract.get_increase_frequency_display()}'
        )
        
        # إضافة البند للموظف (يتبع الموظف مش العقد)
        component_name = f"زيادة سنوية - {contract.next_increase_date.strftime('%B %Y')}"
        
        SalaryComponent.objects.create(
            employee=contract.employee,  # البند يتبع الموظف
            contract=contract,  # للربط فقط
            component_type='earning',
            name=component_name,
            amount=increase_amount,
            order=100,  # في النهاية
            is_basic=False,
            is_taxable=True,
            is_fixed=True,
            notes=f'زيادة تلقائية {percentage}% - تم التطبيق في {date.today()}'
        )
        
        # تحديث تاريخ الزيادة القادمة
        self._update_next_increase_date(contract)
        
        return increase
    
    def _update_next_increase_date(self, contract):
        """تحديث تاريخ الزيادة القادمة"""
        try:
            # استخدام dateutil إذا كان متاح (أدق)
            from dateutil.relativedelta import relativedelta
            
            # حساب الأشهر
            months_map = {
                'annual': 12,
                'semi_annual': 6,
                'quarterly': 3,
                'monthly': 1,
            }
            months = months_map.get(contract.increase_frequency, 12)
            
            # حساب التاريخ القادم
            contract.next_increase_date = contract.next_increase_date + relativedelta(months=months)
            
        except ImportError:
            # Fallback: استخدام timedelta (أقل دقة)
            from datetime import timedelta
            
            months_map = {
                'annual': 12,
                'semi_annual': 6,
                'quarterly': 3,
                'monthly': 1,
            }
            months = months_map.get(contract.increase_frequency, 12)
            days = months * 30  # تقريبي
            
            contract.next_increase_date = contract.next_increase_date + timedelta(days=days)
        
        contract.save(update_fields=['next_increase_date'])
    
    def _send_notification_email(self, total_created, total_errors, errors_list):
        """إرسال إشعار بالبريد الإلكتروني"""
        try:
            subject = f'تقرير الزيادات السنوية - {date.today()}'
            
            message = f"""
تم معالجة الزيادات السنوية التلقائية

النتائج:
- الزيادات المنشأة: {total_created}
- الأخطاء: {total_errors}

"""
            
            if errors_list:
                message += "\nالأخطاء:\n"
                for error in errors_list:
                    message += f"- {error}\n"
            
            message += f"\n\nالتاريخ: {timezone.now()}"
            
            # إرسال للمدير (إذا كان البريد مُعد)
            admin_email = getattr(settings, 'ADMIN_EMAIL', None)
            if admin_email:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [admin_email],
                    fail_silently=True,
                )
                logger.info(f"Notification email sent to {admin_email}")
        
        except Exception as e:
            logger.error(f"Failed to send notification email: {str(e)}")
