"""
Production-Safe HR Journal Entry Backfill Engine.
Generates balanced, atomic journal entries in General Ledger for historical HR records:
1. Advances (Disbursements)
2. Payrolls (Paid slips)
3. External Social Insurance Payments (InsurancePayment)

Supports:
  --dry-run
  --month YYYY-MM
  --post-to-current-open-period
  --default-cash-code 11110
  --only [all|advances|payrolls|insurance]
  --user username
"""

import sys
from decimal import Decimal
from datetime import datetime, date

from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone

from hr.models import Advance, Payroll, InsurancePayment
from financial.models import ChartOfAccounts, JournalEntry, AccountingPeriod
from financial.services.role_registry import AccountRoleRegistry
from financial.services.period_control_service import PeriodControlService
from hr.services.advance_service import AdvanceService
from hr.services.payroll_accounting_service import PayrollAccountingService
from hr.services.insurance_payment_service import InsurancePaymentService

User = get_user_model()


class Command(BaseCommand):
    help = 'ترحيل القيود المحاسبية التاريخية لعمليات الموارد البشرية (سلف، رواتب، تأمينات) إلى الأستاذ العام'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='محاكاة العملية دون كتابة أي قيود في قاعدة البيانات'
        )
        parser.add_argument(
            '--month',
            type=str,
            help='فلترة لشهر معين بصيغة YYYY-MM'
        )
        parser.add_argument(
            '--post-to-current-open-period',
            action='store_true',
            help='في حال كانت الفترة التاريخية مقفلة، ترحيل القيد في أول يوم من الفترة المفتوحة الحالية'
        )
        parser.add_argument(
            '--default-cash-code',
            type=str,
            default='11110',
            help='كود حساب الخزينة الافتراضي في حال عدم وجود حساب صرف بالسجل التاريخي'
        )
        parser.add_argument(
            '--user',
            type=str,
            help='اسم المستخدم المنفذ لعملية الترحيل'
        )
        parser.add_argument(
            '--only',
            type=str,
            choices=['all', 'advances', 'payrolls', 'insurance'],
            default='all',
            help='تحديد نوع العمليات المراد ترحيلها فقط'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        month_filter_str = options.get('month')
        post_open_period = options['post_to_current_open_period']
        default_cash_code = options['default_cash_code']
        username = options.get('user')
        only_choice = options.get('only', 'all')

        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))
        self.stdout.write(self.style.MIGRATE_HEADING("[HR Backfill Engine] اداة الترحيل المحاسبي لعمليات الموارد البشرية"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))

        if dry_run:
            self.stdout.write(self.style.WARNING("[!] وضع المحاكاة (DRY-RUN) مفعل: لن يتم تعديل قاعدة البيانات."))

        # 1. Resolve User
        executing_user = None
        if username:
            executing_user = User.objects.filter(username=username).first()
            if not executing_user:
                self.stdout.write(self.style.ERROR(f"[-] المستخدم '{username}' غير موجود في النظام."))
                return
        else:
            executing_user = User.objects.filter(is_superuser=True).first() or User.objects.first()

        if not executing_user:
            self.stdout.write(self.style.ERROR("[-] لم يتم العثور على أي مستخدم في النظام لتنفيذ الترحيل."))
            return

        self.stdout.write(f"[*] المستخدم المنفذ: {executing_user.username}")

        # 2. Resolve Default Cash Account
        default_cash_acc = AccountRoleRegistry.get_account("DEFAULT_CASH_DRAWER")
        if not default_cash_acc or not default_cash_acc.is_active:
            default_cash_acc = ChartOfAccounts.objects.filter(code=default_cash_code, is_active=True).first()

        if not default_cash_acc:
            self.stdout.write(self.style.ERROR(f"[-] حساب الخزينة الافتراضي '{default_cash_code}' غير موجود."))
            return

        self.stdout.write(f"[*] حساب الخزينة الافتراضي: {default_cash_acc.code} - {default_cash_acc.name}")

        # 3. Parse Month Filter if provided
        month_date = None
        if month_filter_str:
            try:
                month_date = datetime.strptime(month_filter_str, '%Y-%m').date()
                self.stdout.write(f"[*] الفلترة بالشهر: {month_filter_str}")
            except ValueError:
                self.stdout.write(self.style.ERROR("[-] صيغة الشهر غير صحيحة، يرجى استخدام YYYY-MM."))
                return

        # Execution Statistics
        stats = {
            'advances': {'scanned': 0, 'created': 0, 'skipped': 0, 'failed': 0},
            'payrolls': {'scanned': 0, 'created': 0, 'skipped': 0, 'failed': 0},
            'insurance': {'scanned': 0, 'created': 0, 'skipped': 0, 'failed': 0},
        }

        # ══════════════════════════════════════════════════════════════════
        # STEP 1: Process Advances
        # ══════════════════════════════════════════════════════════════════
        if only_choice in ['all', 'advances']:
            self.stdout.write(self.style.MIGRATE_LABEL("\n[1] المرحلة 1: ترحيل قيود صرف السلف (Advances)..."))
            advances_qs = Advance.objects.filter(
                status__in=['paid', 'in_progress', 'completed'],
                journal_entry__isnull=True
            ).select_related('employee', 'employee__department', 'payment_account')

            if month_date:
                advances_qs = advances_qs.filter(deduction_start_month__startswith=month_filter_str)

            adv_count = advances_qs.count()
            self.stdout.write(f"   تم العثور على {adv_count} سلفة بدون قيد محاسبي.")

            for adv in advances_qs:
                stats['advances']['scanned'] += 1
                try:
                    pay_acc = adv.payment_account or default_cash_acc
                    target_date = adv.payment_date or (adv.requested_at.date() if adv.requested_at else timezone.now().date())

                    # Check period lock
                    is_open, period = PeriodControlService.validate_period_open(target_date)
                    if not is_open:
                        if not post_open_period:
                            msg = f"السلفة {adv.id} تقع في فترة غير مفتوحة ({target_date}). استخدم --post-to-current-open-period."
                            self.stdout.write(self.style.WARNING(f"   [تخطي] {msg}"))
                            stats['advances']['skipped'] += 1
                            continue
                        else:
                            target_date = timezone.now().date()

                    if dry_run:
                        self.stdout.write(f"   [محاكاة] سلفة #{adv.id} للموظف {adv.employee.get_full_name_ar()} بمبلغ {adv.amount:,.2f} ج.م -> حساب {pay_acc.code}")
                        stats['advances']['created'] += 1
                    else:
                        with transaction.atomic():
                            adv.payment_date = target_date
                            je = AdvanceService.create_disbursement_journal_entry(
                                advance=adv,
                                payment_account=pay_acc,
                                created_by=executing_user
                            )
                            if je:
                                self.stdout.write(self.style.SUCCESS(f"   [OK] تم إنشاء قيد صرف سلفة #{adv.id}: {je.number}"))
                                stats['advances']['created'] += 1
                            else:
                                stats['advances']['failed'] += 1

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"   [FAIL] فشل ترحيل سلفة #{adv.id}: {e}"))
                    stats['advances']['failed'] += 1

        # ══════════════════════════════════════════════════════════════════
        # STEP 2: Process Payrolls
        # ══════════════════════════════════════════════════════════════════
        if only_choice in ['all', 'payrolls']:
            self.stdout.write(self.style.MIGRATE_LABEL("\n[2] المرحلة 2: ترحيل قيود قسائم الرواتب (Payrolls)..."))
            payroll_qs = Payroll.objects.filter(
                status='paid',
                journal_entry__isnull=True
            ).select_related('employee', 'employee__department', 'payment_account', 'contract')

            if month_date:
                payroll_qs = payroll_qs.filter(month=month_date)

            pay_count = payroll_qs.count()
            self.stdout.write(f"   تم العثور على {pay_count} قسيمة راتب بدون قيد محاسبي.")

            accounting_service = PayrollAccountingService()

            for p in payroll_qs:
                stats['payrolls']['scanned'] += 1
                try:
                    if not p.payment_account:
                        p.payment_account = default_cash_acc
                        if not dry_run:
                            p.save(update_fields=['payment_account'])

                    target_date = p.payment_date or (p.paid_at.date() if p.paid_at else p.month)

                    # Check period lock
                    is_open, period = PeriodControlService.validate_period_open(target_date)
                    if not is_open:
                        if not post_open_period:
                            msg = f"قسيمة راتب {p.id} تقع في فترة غير مفتوحة ({target_date}). استخدم --post-to-current-open-period."
                            self.stdout.write(self.style.WARNING(f"   [تخطي] {msg}"))
                            stats['payrolls']['skipped'] += 1
                            continue
                        else:
                            target_date = timezone.now().date()

                    if dry_run:
                        lines = accounting_service._prepare_journal_lines(p)
                        dr_tot = sum(l.debit for l in lines)
                        cr_tot = sum(l.credit for l in lines)
                        self.stdout.write(f"   [محاكاة] راتب #{p.id} ({p.employee.get_full_name_ar()}) - شهر {p.month} | مدين: {dr_tot:,.2f} | دائن: {cr_tot:,.2f} ({len(lines)} أسطر)")
                        stats['payrolls']['created'] += 1
                    else:
                        with transaction.atomic():
                            p.payment_date = target_date
                            je = accounting_service.create_payroll_journal_entry(p, executing_user)
                            if je:
                                self.stdout.write(self.style.SUCCESS(f"   [OK] تم إنشاء قيد راتب #{p.id}: {je.number}"))
                                stats['payrolls']['created'] += 1
                            else:
                                stats['payrolls']['failed'] += 1

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"   [FAIL] فشل ترحيل قسيمة راتب #{p.id}: {e}"))
                    stats['payrolls']['failed'] += 1

        # ══════════════════════════════════════════════════════════════════
        # STEP 3: Process Insurance Payments
        # ══════════════════════════════════════════════════════════════════
        if only_choice in ['all', 'insurance']:
            self.stdout.write(self.style.MIGRATE_LABEL("\n[3] المرحلة 3: ترحيل تحصيلات تأمينات الموظفين الخارجيين (Insurance Payments)..."))
            ins_qs = InsurancePayment.objects.filter(
                status='paid',
                journal_entry__isnull=True
            ).select_related('employee', 'payment_account')

            if month_date:
                ins_qs = ins_qs.filter(month=month_date)

            ins_count = ins_qs.count()
            self.stdout.write(f"   تم العثور على {ins_count} دفعة تأمين بدون قيد محاسبي.")

            for ins in ins_qs:
                stats['insurance']['scanned'] += 1
                try:
                    pay_acc = ins.payment_account or default_cash_acc
                    target_date = ins.payment_date or (ins.created_at.date() if hasattr(ins, 'created_at') else ins.month)

                    # Check period lock
                    is_open, period = PeriodControlService.validate_period_open(target_date)
                    if not is_open:
                        if not post_open_period:
                            msg = f"دفعة تأمين {ins.id} تقع في فترة غير مفتوحة ({target_date}). استخدم --post-to-current-open-period."
                            self.stdout.write(self.style.WARNING(f"   [تخطي] {msg}"))
                            stats['insurance']['skipped'] += 1
                            continue
                        else:
                            target_date = timezone.now().date()

                    if dry_run:
                        self.stdout.write(f"   [محاكاة] دفعة تأمين #{ins.id} ({ins.employee.get_full_name_ar()}) بمبلغ {ins.total_amount:,.2f} ج.م -> خزينة {pay_acc.code}")
                        stats['insurance']['created'] += 1
                    else:
                        with transaction.atomic():
                            # Reset status temporarily to allow record_payment
                            ins.status = 'pending'
                            ins.save(update_fields=['status'])
                            paid_ins = InsurancePaymentService.record_payment(
                                insurance_payment=ins,
                                payment_account=pay_acc,
                                received_by=executing_user,
                                payment_date=target_date
                            )
                            if paid_ins and paid_ins.journal_entry:
                                self.stdout.write(self.style.SUCCESS(f"   [OK] تم إنشاء قيد تأمين #{ins.id}: {paid_ins.journal_entry.number}"))
                                stats['insurance']['created'] += 1
                            else:
                                stats['insurance']['failed'] += 1

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"   [FAIL] فشل ترحيل دفعة تأمين #{ins.id}: {e}"))
                    stats['insurance']['failed'] += 1

        # ══════════════════════════════════════════════════════════════════
        # Summary Report
        # ══════════════════════════════════════════════════════════════════
        self.stdout.write(self.style.MIGRATE_HEADING("\n" + "=" * 70))
        self.stdout.write(self.style.MIGRATE_HEADING("[Summary] تقرير ملخص عمليات الترحيل المحاسبي"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))

        for section, st in stats.items():
            title = "السلف (Advances)" if section == 'advances' else ("الرواتب (Payrolls)" if section == 'payrolls' else "التأمينات (Insurance)")
            self.stdout.write(
                f"[*] {title:<25}: "
                f"إجمالي: {st['scanned']} | "
                f"تم الترحيل: {st['created']} | "
                f"تم التخطي: {st['skipped']} | "
                f"فشل: {st['failed']}"
            )

        total_created = sum(s['created'] for s in stats.values())
        total_failed = sum(s['failed'] for s in stats.values())

        if total_failed == 0:
            self.stdout.write(self.style.SUCCESS(f"\n[SUCCESS] اكتمل الترحيل بنجاح تام! تم إنشاء/محاكاة {total_created} قيد محاسبي."))
        else:
            self.stdout.write(self.style.WARNING(f"\n[WARNING] اكتمل الترحيل مع وجود {total_failed} أخطاء تحتاج مراجعة."))
