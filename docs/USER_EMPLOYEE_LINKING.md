# دليل الربط بين المستخدمين والموظفين

## 🎯 الاستراتيجية الموصى بها

### النموذج الحالي: OneToOne Relationship

```python
class Employee(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='employee_profile'
    )
```

**المميزات:**
- ✅ علاقة واحد لواحد (مستخدم واحد لكل موظف)
- ✅ سهولة الوصول: `user.employee_profile` أو `employee.user`
- ✅ أمان: لا يمكن ربط مستخدم بأكثر من موظف
- ✅ Django Best Practice

---

## 📊 سيناريوهات الربط

### 1. إنشاء موظف جديد مع مستخدم

```python
from hr.services.user_employee_service import UserEmployeeService

# إنشاء موظف
employee = Employee.objects.create(
    employee_number='EMP001',
    first_name_ar='محمد',
    last_name_ar='أحمد',
    work_email='mohamed@company.com',
    # ... باقي البيانات
)

# إنشاء مستخدم للموظف
user, password = UserEmployeeService.create_user_for_employee(
    employee=employee,
    username='EMP001',  # اختياري
    password=None,      # سيتم توليدها تلقائياً
    send_email=True     # إرسال بيانات الدخول بالبريد
)

print(f"Username: {user.username}")
print(f"Password: {password}")
```

### 2. ربط مستخدم موجود بموظف موجود

```python
# البحث عن المستخدم والموظف
user = User.objects.get(username='mohamed')
employee = Employee.objects.get(employee_number='EMP001')

# الربط
UserEmployeeService.link_existing_user_to_employee(employee, user)
```

### 3. الربط التلقائي عبر البريد الإلكتروني

```python
# ربط جميع الموظفين بالمستخدمين الذين لهم نفس البريد
linked_count = UserEmployeeService.auto_link_by_email()
print(f"تم ربط {linked_count} موظف")
```

### 4. إنشاء مستخدمين لعدة موظفين دفعة واحدة

```python
# الحصول على الموظفين غير المرتبطين
unlinked_employees = UserEmployeeService.get_unlinked_employees()

# إنشاء مستخدمين لهم
results = UserEmployeeService.bulk_create_users_for_employees(
    employees=unlinked_employees,
    send_email=True
)

# عرض النتائج
for employee, user, password in results:
    if user:
        print(f"{employee.employee_number}: {user.username} - {password}")
    else:
        print(f"{employee.employee_number}: فشل - {password}")
```

---

## 🔍 البحث والوصول

### الوصول من المستخدم للموظف

```python
user = User.objects.get(username='mohamed')

# الطريقة 1: مباشرة
employee = user.employee_profile

# الطريقة 2: آمنة (مع التحقق)
if hasattr(user, 'employee_profile'):
    employee = user.employee_profile
    print(employee.employee_number)
```

### الوصول من الموظف للمستخدم

```python
employee = Employee.objects.get(employee_number='EMP001')

# مباشرة
user = employee.user
print(user.username)
```

### البحث عبر رقم الموظف

```python
user = UserEmployeeService.find_user_by_employee_number('EMP001')
```

### البحث عبر اسم المستخدم

```python
employee = UserEmployeeService.find_employee_by_username('mohamed')
```

---

## 🔗 الربط مع البصمة

### السيناريو 1: معرف البصمة = رقم الموظف

```python
# في BiometricLog
biometric_log = BiometricLog.objects.get(id=123)

# البحث عن الموظف
employee = Employee.objects.get(employee_number=biometric_log.user_id)
```

### السيناريو 2: معرف البصمة مختلف

```python
# إنشاء Mapping
from hr.models import BiometricUserMapping

BiometricUserMapping.objects.create(
    employee=employee,
    biometric_user_id='12345',  # المعرف في البصمة
    device=device
)

# البحث
employee = UserEmployeeService.find_employee_by_biometric_id('12345')
```

---

## 🔄 المزامنة

### مزامنة بيانات المستخدم → الموظف

```python
user = User.objects.get(username='mohamed')
UserEmployeeService.sync_user_data_to_employee(user)
```

### مزامنة بيانات الموظف → المستخدم

```python
employee = Employee.objects.get(employee_number='EMP001')
UserEmployeeService.sync_employee_data_to_user(employee)
```

---

## 🎨 في الواجهات (Templates)

### عرض معلومات الموظف للمستخدم الحالي

```django
{% if request.user.employee_profile %}
    <p>رقم الموظف: {{ request.user.employee_profile.employee_number }}</p>
    <p>القسم: {{ request.user.employee_profile.department.name_ar }}</p>
{% endif %}
```

### عرض معلومات المستخدم في صفحة الموظف

```django
<p>اسم المستخدم: {{ employee.user.username }}</p>
<p>البريد: {{ employee.user.email }}</p>
<p>آخر دخول: {{ employee.user.last_login }}</p>
```

---

## 🛡️ الصلاحيات والأمان

### التحقق من أن المستخدم موظف

```python
from django.contrib.auth.decorators import user_passes_test

def is_employee(user):
    return hasattr(user, 'employee_profile')

@user_passes_test(is_employee)
def employee_only_view(request):
    employee = request.user.employee_profile
    # ...
```

### التحقق من القسم

```python
def is_hr_department(user):
    if hasattr(user, 'employee_profile'):
        return user.employee_profile.department.code == 'HR'
    return False

@user_passes_test(is_hr_department)
def hr_only_view(request):
    # ...
```

---

## 📝 أفضل الممارسات

### 1. استخدم رقم الموظف كـ username

```python
username = employee.employee_number  # EMP001
```

**المميزات:**
- ✅ فريد
- ✅ سهل التذكر
- ✅ يربط مباشرة بالموظف

### 2. استخدم البريد الوظيفي

```python
user.email = employee.work_email
```

### 3. أنشئ المستخدم عند إنشاء الموظف

```python
@receiver(post_save, sender=Employee)
def create_user_for_employee(sender, instance, created, **kwargs):
    if created and not hasattr(instance, 'user'):
        UserEmployeeService.create_user_for_employee(instance)
```

### 4. احذف المستخدم عند حذف الموظف

```python
# Django يفعل هذا تلقائياً بسبب on_delete=CASCADE
```

---

## 🔧 إدارة Django Admin

```python
# في admin.py
from django.contrib import admin
from .models import Employee

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['employee_number', 'get_full_name_ar', 'user', 'department']
    
    def get_full_name_ar(self, obj):
        return obj.get_full_name_ar()
    get_full_name_ar.short_description = 'الاسم'
    
    # إضافة زر لإنشاء مستخدم
    actions = ['create_users_for_selected']
    
    def create_users_for_selected(self, request, queryset):
        results = UserEmployeeService.bulk_create_users_for_employees(
            queryset.filter(user__isnull=True)
        )
        self.message_user(request, f"تم إنشاء {len(results)} مستخدم")
    
    create_users_for_selected.short_description = "إنشاء مستخدمين للموظفين المحددين"
```

---

## 📊 تقارير

### الموظفين بدون مستخدمين

```python
unlinked = Employee.objects.filter(user__isnull=True)
print(f"عدد الموظفين بدون مستخدمين: {unlinked.count()}")
```

### المستخدمين بدون موظفين

```python
unlinked = User.objects.filter(employee_profile__isnull=True)
print(f"عدد المستخدمين بدون موظفين: {unlinked.count()}")
```

---

## 🚀 Migration للربط التلقائي

```python
# في migration file
from django.db import migrations

def link_users_to_employees(apps, schema_editor):
    Employee = apps.get_model('hr', 'Employee')
    User = apps.get_model('auth', 'User')
    
    for employee in Employee.objects.filter(user__isnull=True):
        try:
            user = User.objects.get(email=employee.work_email)
            if not hasattr(user, 'employee_profile'):
                employee.user = user
                employee.save()
        except:
            pass

class Migration(migrations.Migration):
    dependencies = [
        ('hr', '0005_previous_migration'),
    ]
    
    operations = [
        migrations.RunPython(link_users_to_employees),
    ]
```

---

## ✅ Checklist

- [ ] كل موظف له مستخدم
- [ ] username = employee_number
- [ ] email = work_email
- [ ] البصمة مربوطة بالموظف
- [ ] الصلاحيات محددة حسب القسم
- [ ] بيانات الدخول مرسلة بالبريد

---

## 🎯 الخلاصة

**الطريقة الموصى بها:**

```python
# 1. إنشاء موظف
employee = Employee.objects.create(...)

# 2. إنشاء مستخدم
user, password = UserEmployeeService.create_user_for_employee(
    employee,
    send_email=True
)

# 3. الربط تلقائي ✅
# employee.user → User
# user.employee_profile → Employee
```

**بسيطة، آمنة، وفعالة!** 🚀
