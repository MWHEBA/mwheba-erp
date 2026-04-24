"""
Command: deduct_leaves_from_excel
يقرأ ملف Leaves.xlsx ويطرح الأيام المستخدمة من أرصدة الإجازات
الاعتيادية والعارضة لكل موظف.

الاستخدام:
    python manage.py deduct_leaves_from_excel
    python manage.py deduct_leaves_from_excel --dry-run       # معاينة بدون حفظ
    python manage.py deduct_leaves_from_excel --file path/to/file.xlsx
"""
import os
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'طرح أيام الإجازات من ملف Excel من أرصدة الموظفين'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='معاينة التغييرات بدون حفظ')
        parser.add_argument('--file', type=str, default='Leaves.xlsx', help='مسار ملف Excel')

    def handle(self, *args, **options):
        try:
            import openpyxl
        except ImportError:
            self.stderr.write(self.style.ERROR('openpyxl غير مثبت. شغل: pip install openpyxl'))
            return

        from hr.models import Employee, LeaveBalance, LeaveType
        # نخزنهم في الـ instance عشان _deduct تقدر تستخدمهم
        self.LeaveBalance = LeaveBalance

        file_path = options['file']
        dry_run = options['dry_run']

        if not os.path.exists(file_path):
            self.stderr.write(self.style.ERROR(f'الملف غير موجود: {file_path}'))
            return

        # جلب أنواع الإجازات
        annual_type = LeaveType.objects.filter(category='annual', is_active=True).first()
        emergency_type = LeaveType.objects.filter(category='emergency', is_active=True).first()

        if not annual_type:
            self.stderr.write(self.style.ERROR('لم يتم العثور على نوع إجازة اعتيادية (annual)'))
            return
        if not emergency_type:
            self.stderr.write(self.style.ERROR('لم يتم العثور على نوع إجازة عارضة (emergency)'))
            return

        self.stdout.write(f'نوع الاعتيادية: {annual_type.name_ar}')
        self.stdout.write(f'نوع العارضة: {emergency_type.name_ar}')
        self.stdout.write(f'{"[DRY RUN] " if dry_run else ""}جاري المعالجة...\n')

        wb = openpyxl.load_workbook(file_path)
        ws = wb.active

        results = {
            'updated': 0,
            'skipped_no_employee': [],
            'skipped_no_balance': [],
            'skipped_zero': [],
            'errors': [],
        }

        rows = [row for row in ws.iter_rows(min_row=2, values_only=True) if row[0]]

        with transaction.atomic():
            for row in rows:
                emp_number = str(row[0]).strip()
                annual_deduct = int(row[2] or 0)
                emergency_deduct = int(row[3] or 0)

                # جيب الموظف
                try:
                    employee = Employee.objects.get(employee_number=emp_number)
                except Employee.DoesNotExist:
                    results['skipped_no_employee'].append(emp_number)
                    continue

                if annual_deduct == 0 and emergency_deduct == 0:
                    results['skipped_zero'].append(emp_number)
                    continue

                # طرح الاعتيادية
                if annual_deduct > 0:
                    self._deduct(employee, annual_type, annual_deduct, dry_run, results)

                # طرح العارضة
                if emergency_deduct > 0:
                    self._deduct(employee, emergency_type, emergency_deduct, dry_run, results)

                results['updated'] += 1
                self.stdout.write(
                    f'  {"[DRY] " if dry_run else "✓ "}{emp_number}: '
                    f'اعتيادية -{annual_deduct} | عارضة -{emergency_deduct}'
                )

            if dry_run:
                transaction.set_rollback(True)

        # ملخص
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS(f'تم تحديث: {results["updated"]} موظف'))

        if results['skipped_no_employee']:
            self.stdout.write(self.style.WARNING(
                f'موظفون غير موجودون ({len(results["skipped_no_employee"])}): '
                f'{", ".join(results["skipped_no_employee"])}'
            ))
        if results['skipped_no_balance']:
            self.stdout.write(self.style.WARNING(
                f'بدون رصيد ({len(results["skipped_no_balance"])}): '
                f'{", ".join(results["skipped_no_balance"])}'
            ))
        if results['errors']:
            for err in results['errors']:
                self.stdout.write(self.style.ERROR(f'خطأ: {err}'))
        if dry_run:
            self.stdout.write(self.style.WARNING('\n[DRY RUN] لم يتم حفظ أي تغييرات'))

    def _deduct(self, employee, leave_type, days, dry_run, results):
        """طرح الأيام من رصيد الموظف"""
        balance = self.LeaveBalance.objects.filter(
            employee=employee,
            leave_type=leave_type,
        ).first()

        if not balance:
            results['skipped_no_balance'].append(
                f'{employee.employee_number} ({leave_type.name_ar})'
            )
            return

        balance.used_days = (balance.used_days or 0) + days
        balance.remaining_days = max(0, (balance.accrued_days or 0) - balance.used_days)

        if not dry_run:
            balance.save()
