"""
Management command: تشخيص استحقاق إجازات موظف محدد
الاستخدام: python manage.py debug_leave_entitlement --emp EMP-01
"""
from django.core.management.base import BaseCommand
from datetime import date
from hr.models import Employee, LeaveBalance, LeaveType
from hr.services.leave_accrual_service import LeaveAccrualService
from core.models import SystemSetting

SEP = "=" * 60


class Command(BaseCommand):
    help = 'تشخيص استحقاق إجازات موظف محدد'

    def add_arguments(self, parser):
        parser.add_argument('--emp', type=str, default='EMP-01', help='رقم الموظف')
        parser.add_argument('--year', type=int, default=date.today().year, help='السنة')

    def handle(self, *args, **options):
        emp_number = options['emp']
        year = options['year']

        # ── 1. جلب الموظف ──────────────────────────────────────
        try:
            emp = Employee.objects.select_related('department', 'job_title').get(
                employee_number=emp_number
            )
        except Employee.DoesNotExist:
            self.stderr.write(f"❌ الموظف {emp_number} مش موجود في قاعدة البيانات!")
            return

        self.stdout.write(SEP)
        self.stdout.write(f"👤 الموظف: {emp.get_full_name_ar()} ({emp.employee_number})")
        self.stdout.write(SEP)

        # ── 2. بيانات الموظف ───────────────────────────────────
        self.stdout.write("\n📋 بيانات الموظف:")
        self.stdout.write(f"   تاريخ الميلاد : {emp.birth_date}")
        self.stdout.write(f"   تاريخ التعيين : {emp.hire_date}")
        self.stdout.write(f"   الحالة        : {emp.status}")

        try:
            age = emp.age
            self.stdout.write(f"   العمر المحسوب : {age} سنة")
        except Exception as e:
            self.stdout.write(f"   ❌ خطأ في حساب العمر: {e}")
            age = None

        try:
            yos = emp.years_of_service
            self.stdout.write(f"   سنوات الخدمة  : {yos} سنة")
        except Exception as e:
            self.stdout.write(f"   ❌ خطأ في حساب سنوات الخدمة: {e}")
            yos = None

        months_worked = LeaveAccrualService.calculate_months_worked(emp.hire_date)
        self.stdout.write(f"   الأشهر المعمولة: {months_worked} شهر")

        # ── 3. إعدادات النظام ──────────────────────────────────
        self.stdout.write("\n⚙️  إعدادات النظام:")
        age_threshold     = int(SystemSetting.get_setting('leave_senior_age_threshold', 50))
        service_threshold = int(SystemSetting.get_setting('leave_senior_service_years', 10))
        partial_after     = int(SystemSetting.get_setting('leave_partial_after_months', 6))

        self.stdout.write(f"   leave_senior_age_threshold    : {age_threshold}")
        self.stdout.write(f"   leave_senior_service_years    : {service_threshold}")
        self.stdout.write(f"   leave_partial_after_months    : {partial_after}")
        self.stdout.write(f"   leave_senior_annual_days      : {SystemSetting.get_setting('leave_senior_annual_days', 30)}")
        self.stdout.write(f"   leave_senior_emergency_days   : {SystemSetting.get_setting('leave_senior_emergency_days', 10)}")

        # ── 4. تشخيص is_senior_employee ────────────────────────
        self.stdout.write("\n🔍 تشخيص is_senior_employee:")

        age_ok = (age is not None and age >= age_threshold)
        yos_ok = (yos is not None and yos >= service_threshold)

        self.stdout.write(
            f"   {'✅' if age_ok else '❌'}  العمر ({age}) >= حد الكبار ({age_threshold}): {age_ok}"
        )
        self.stdout.write(
            f"   {'✅' if yos_ok else '❌'}  سنوات الخدمة ({yos}) >= حد الخدمة ({service_threshold}): {yos_ok}"
        )

        try:
            is_senior = LeaveAccrualService.is_senior_employee(emp)
        except Exception as e:
            self.stdout.write(f"\n   ❌ خطأ في is_senior_employee: {e}")
            is_senior = False

        self.stdout.write(
            f"\n   ➡️  is_senior_employee = {'✅ True (كبير)' if is_senior else '❌ False (مش كبير)'}"
        )

        # ── 5. الاستحقاق لكل نوع إجازة ────────────────────────
        self.stdout.write(f"\n📊 الاستحقاق المحسوب لكل نوع إجازة (سنة {year}):")
        leave_types = LeaveType.objects.filter(
            category__in=['annual', 'emergency'], is_active=True
        )
        for lt in leave_types:
            try:
                entitlement = LeaveAccrualService.get_entitlement_for_employee(emp, lt)
                icon = '✅' if entitlement > 0 else '❌'
                self.stdout.write(f"   {icon}  {lt.name_ar} ({lt.category}): {entitlement} يوم")
            except Exception as e:
                self.stdout.write(f"   ❌  {lt.name_ar}: خطأ — {e}")

        # ── 6. الأرصدة الفعلية في DB ───────────────────────────
        self.stdout.write(f"\n💾 الأرصدة الفعلية في DB (سنة {year}):")
        balances = LeaveBalance.objects.filter(
            employee=emp, year=year
        ).select_related('leave_type')

        if balances.exists():
            for b in balances:
                self.stdout.write(f"   📌 {b.leave_type.name_ar}:")
                self.stdout.write(f"      total_days      = {b.total_days}")
                self.stdout.write(f"      accrued_days    = {b.accrued_days}")
                self.stdout.write(f"      used_days       = {b.used_days}")
                self.stdout.write(f"      remaining_days  = {b.remaining_days}")
                self.stdout.write(f"      last_accrual    = {b.last_accrual_date}")
        else:
            self.stdout.write(f"   ❌ لا توجد أرصدة لهذا الموظف في سنة {year}!")

        # ── 7. الخلاصة ─────────────────────────────────────────
        self.stdout.write(f"\n{SEP}")
        self.stdout.write("🎯 الخلاصة والسبب المحتمل:")

        if age_ok and not is_senior:
            self.stdout.write(
                f"   🐛 BUG: العمر {age} فوق الحد {age_threshold} لكن is_senior_employee بترجع False!"
            )
            self.stdout.write(f"      → راجع employee.age property — birth_date: {emp.birth_date}")
        elif age_ok and is_senior:
            self.stdout.write("   ✅ الموظف يُعتبر كبير — الحساب صح")
            self.stdout.write("   ℹ️  المشكلة في الأرصدة المحفوظة في DB مش محدّثة")
            self.stdout.write("      → الحل: شغّل 'python manage.py update_leave_accruals'")
            self.stdout.write("              أو اضغط 'تحديث الأرصدة' من صفحة أرصدة الإجازات")
        elif not age_ok and not yos_ok:
            self.stdout.write(
                f"   ℹ️  الموظف مش كبير: عمره {age} (الحد {age_threshold}) وخدمته {yos} سنة (الحد {service_threshold})"
            )
            if months_worked < partial_after:
                self.stdout.write(
                    f"   ℹ️  لسه في فترة الاختبار: {months_worked} شهر من {partial_after} مطلوبين"
                )
            else:
                self.stdout.write(
                    f"   ℹ️  تحقق من birth_date في قاعدة البيانات — القيمة الحالية: {emp.birth_date}"
                )

        self.stdout.write(SEP)
