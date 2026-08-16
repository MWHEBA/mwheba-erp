import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('84.247.179.163', port=2951, username='mwhebaco', password='MedooAlnems2008')

venv = '/home/mwhebaco/virtualenv/test_erp/3.11/bin/python'
app_path = '/home/mwhebaco/test_erp'

def run_remote(cmd, label=""):
    if label:
        print(f"--> {label}...")
    full_cmd = f"cd {app_path} && {venv} {cmd}"
    stdin, stdout, stderr = ssh.exec_command(full_cmd, timeout=120)
    out = stdout.read().decode('utf-8', errors='ignore').strip()
    err = stderr.read().decode('utf-8', errors='ignore').strip()
    status = stdout.channel.recv_exit_status()
    if status == 0:
        print(f"  [OK] {label}")
        if out:
            print(f"       {out[:150]}")
    else:
        print(f"  [WARN/ERR] {label}")
        if err:
            print(f"       ERR: {err[:200]}")
        elif out:
            print(f"       OUT: {out[:200]}")
    return status == 0

print("="*60)
print("  بدء تثبيت البيانات المبدئية الأولية الضرورية على بيئة test")
print("="*60)

# 1. Core fixtures
run_remote("manage.py loaddata core/fixtures/system_modules.json", "1. موديولات النظام (system_modules)")
run_remote("manage.py loaddata core/fixtures/system_settings_final.json", "2. إعدادات النظام (system_settings_final)")

# 2. Roles & Users
run_remote("manage.py loaddata users/fixtures/roles.json", "3. الأدوار الأساسية (roles)")
run_remote("manage.py loaddata users/fixtures/initial_data.json", "4. بيانات المستخدمين (initial_data)")

# 3. Financial fixtures
run_remote("manage.py loaddata financial/fixtures/chart_of_accounts.json", "5. دليل الحسابات (chart_of_accounts)")
run_remote("manage.py loaddata financial/fixtures/financial_categories.json", "6. التصنيفات المالية (financial_categories)")
run_remote("manage.py loaddata financial/fixtures/financial_subcategories.json", "7. التصنيفات الفرعية المالية (financial_subcategories)")
run_remote("manage.py loaddata financial/fixtures/payment_sync_rules.json", "8. قواعد مزامنة المدفوعات (payment_sync_rules)")
run_remote("manage.py loaddata financial/fixtures/accounting_periods.json", "9. الفترات المحاسبية (accounting_periods)")

# 4. HR fixtures
run_remote("manage.py loaddata hr/fixtures/departments.json", "10. أقسام الموارد البشرية (departments)")
run_remote("manage.py loaddata hr/fixtures/job_titles.json", "11. المسميات الوظيفية (job_titles)")
run_remote("manage.py loaddata hr/fixtures/employees.json", "12. الموظفين (employees)")
run_remote("manage.py loaddata hr/fixtures/leave_types.json", "13. أنواع الإجازات (leave_types)")
run_remote("manage.py loaddata hr/fixtures/permission_types.json", "14. أنواع الأذونات (permission_types)")
run_remote("manage.py loaddata hr/fixtures/attendance_penalties.json", "15. عقوبات الحضور (attendance_penalties)")
run_remote("manage.py loaddata hr/fixtures/initial_data.json", "16. بيانات HR الأولية (hr initial_data)")

# 5. Suppliers & Products
run_remote("manage.py loaddata supplier/fixtures/supplier_types.json", "17. أنواع الموردين (supplier_types)")
run_remote("manage.py loaddata supplier/fixtures/service_types.json", "18. أنواع الخدمات (service_types)")
run_remote("manage.py loaddata product/fixtures/initial_warehouses.json", "19. المستودعات (initial_warehouses)")
run_remote("manage.py loaddata product/fixtures/units.json", "20. وحدات القياس (units)")

# 6. Printing & Pricing
printing_files = [
    ("paper_origins.json", "مناشئ الورق"),
    ("paper_sizes.json", "مقاسات الورق"),
    ("paper_weights.json", "أوزان الورق"),
    ("offset_sheet_sizes.json", "مقاسات أوفست"),
    ("digital_sheet_sizes.json", "مقاسات ديجيتال"),
    ("offset_machines.json", "ماكينات أوفست"),
    ("digital_machines.json", "ماكينات ديجيتال"),
    ("coating_finishing.json", "التغليف والتشطيب"),
    ("piece_plate_sizes.json", "مقاسات الألواح"),
    ("product_types_sizes.json", "أنواع وأحجام المنتجات"),
    ("print_settings.json", "إعدادات الطباعة"),
    ("printing_pricing_settings.json", "إعدادات التسعير"),
]
for fname, desc in printing_files:
    run_remote(f"manage.py loaddata printing_pricing/fixtures/{fname}", f"طباعة وتسعير: {desc}")

# 7. Activate Governance
run_remote("manage.py activate_governance --silent", "تفعيل موديول الحوكمة والأمان (Governance)")

# 8. Seed Period, Admin & Assign Roles
seed_script = """
import django
from datetime import date
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from financial.models import AccountingPeriod
from users.models import Role
from supplier.models import Supplier, SupplierType

User = get_user_model()

# 1. Admin Superuser & Password
admin_user, created = User.objects.get_or_create(username='admin', defaults={'email': 'info@mwheba.co.uk'})
admin_user.is_superuser = True
admin_user.is_staff = True
admin_user.is_active = True
admin_user.password = make_password('MedooAlnems2008')
admin_role = Role.objects.filter(name='admin').first()
if admin_role:
    admin_user.role = admin_role
admin_user.save()
print('Admin user ready with role and password.')

# 2. Accounting period check
if not AccountingPeriod.objects.filter(status='open').exists():
    AccountingPeriod.objects.create(
        name='السنة المالية 2025/2026',
        start_date=date(2025, 9, 1),
        end_date=date(2026, 8, 31),
        status='open',
        created_by=admin_user
    )
    print('Created open accounting period 2025/2026')
else:
    print('Open accounting period exists.')
"""
run_remote(f'manage.py shell -c "{seed_script}"', "تهيئة حساب الإدارة والفترة المحاسبية")

# 9. Restart
print("--> إعادة تشغيل التطبيق...")
ssh.exec_command('touch /home/mwhebaco/test_erp/passenger_wsgi.py')
ssh.exec_command('/usr/sbin/cloudlinux-selector restart --json --interpreter python --app-root test_erp')
print("[OK] تم إعادة تشغيل التطبيق بنجاح.")

ssh.close()
print("="*60)
print("  اكتمل تثبيت كافة البيانات المبدئية بنجاح!")
print("="*60)
