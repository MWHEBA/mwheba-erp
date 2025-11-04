"""
Views لوحدة الموارد البشرية
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import models
from django.db.models import Count, Sum, Q
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from datetime import date, timedelta, datetime
import logging
import hmac

# Django REST Framework imports
from rest_framework.decorators import api_view, permission_classes, authentication_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

# Local imports
from .models import Employee, Department, JobTitle, Attendance, Leave, LeaveBalance, LeaveType, Payroll, Shift, Advance, Contract, BiometricDevice, BiometricLog, BiometricSyncLog
from .forms.employee_forms import EmployeeForm, DepartmentForm
from .forms.attendance_forms import AttendanceForm
from .forms.leave_forms import LeaveRequestForm
from .forms.payroll_forms import PayrollProcessForm
from .services.attendance_service import AttendanceService
from .services.leave_service import LeaveService
from .services.payroll_service import PayrollService
from .reports import (
    reports_home, attendance_report, leave_report,
    payroll_report, employee_report
)

# Logger
logger = logging.getLogger(__name__)


@login_required
def dashboard(request):
    """Dashboard الموارد البشرية"""
    context = {
        'total_employees': Employee.objects.filter(status='active').count(),
        'total_departments': Department.objects.filter(is_active=True).count(),
        'pending_leaves': Leave.objects.filter(status='pending').count(),
        'today_attendance': Attendance.objects.filter(date=date.today()).count(),
    }
    return render(request, 'hr/dashboard.html', context)


@login_required
def employee_list(request):
    """قائمة الموظفين"""
    # جلب جميع الموظفين مع العلاقات
    employees = Employee.objects.select_related('department', 'job_title').all()
    
    # الفلترة حسب البحث
    search = request.GET.get('search', '')
    if search:
        employees = employees.filter(
            Q(first_name_ar__icontains=search) |
            Q(last_name_ar__icontains=search) |
            Q(employee_number__icontains=search)
        )
    
    # الفلترة حسب القسم
    department = request.GET.get('department', '')
    if department:
        employees = employees.filter(department_id=department)
    
    # الفلترة حسب الحالة
    status = request.GET.get('status', '')
    if status:
        employees = employees.filter(status=status)
    
    # الفلترة حسب المسمى الوظيفي
    job_title = request.GET.get('job_title', '')
    if job_title:
        employees = employees.filter(job_title_id=job_title)
    
    # جلب الأقسام والمسميات الوظيفية للفلترة
    departments = Department.objects.filter(is_active=True)
    job_titles = JobTitle.objects.filter(is_active=True)
    
    # الإحصائيات
    total_employees = Employee.objects.count()
    active_employees = Employee.objects.filter(status='active').count()
    total_departments = Department.objects.filter(is_active=True).count()
    total_job_titles = JobTitle.objects.filter(is_active=True).count()
    
    # تعريف رؤوس الجدول
    table_headers = [
        {'key': 'employee_number', 'label': 'رقم الموظف', 'sortable': True, 'class': 'text-center'},
        {'key': 'full_name_display', 'label': 'الاسم', 'sortable': True, 'format': 'html'},
        {'key': 'department_name', 'label': 'القسم', 'sortable': True, 'class': 'text-center'},
        {'key': 'job_title_name', 'label': 'المسمى الوظيفي', 'sortable': True, 'class': 'text-center'},
        {'key': 'hire_date', 'label': 'تاريخ التعيين', 'sortable': True, 'format': 'date', 'class': 'text-center'},
        {'key': 'status_display', 'label': 'الحالة', 'sortable': True, 'format': 'html', 'class': 'text-center'},
    ]
    
    # تعريف أزرار الإجراءات
    table_actions = [
        {'url': 'hr:employee_detail', 'icon': 'fa-eye', 'label': 'عرض', 'class': 'action-view'},
        {'url': 'hr:employee_form_edit', 'icon': 'fa-edit', 'label': 'تعديل', 'class': 'action-edit'},
        {'url': 'hr:employee_delete', 'icon': 'fa-trash', 'label': 'حذف', 'class': 'action-delete'},
    ]
    
    # إضافة بيانات إضافية للعرض في الجدول
    for employee in employees:
        # عرض الاسم الكامل مع الصورة
        if employee.photo:
            photo_html = f'<img src="{employee.photo.url}" class="rounded-circle me-2" width="32" height="32">'
        else:
            first_letter = employee.first_name_ar[0] if employee.first_name_ar else 'م'
            photo_html = f'<div class="avatar-placeholder rounded-circle bg-primary text-white d-inline-flex align-items-center justify-content-center me-2" style="width: 32px; height: 32px;">{first_letter}</div>'
        
        employee.full_name_display = f'<div class="d-flex align-items-center">{photo_html}<strong>{employee.get_full_name_ar()}</strong></div>'
        
        # اسم القسم
        employee.department_name = employee.department.name_ar if employee.department else '-'
        
        # اسم المسمى الوظيفي
        employee.job_title_name = employee.job_title.title_ar if employee.job_title else '-'
        
        # عرض الحالة
        status_badges = {
            'active': '<span class="badge bg-success">نشط</span>',
            'on_leave': '<span class="badge bg-warning text-dark">في إجازة</span>',
            'suspended': '<span class="badge bg-secondary">موقوف</span>',
            'terminated': '<span class="badge bg-danger">منتهي الخدمة</span>',
        }
        employee.status_display = status_badges.get(employee.status, '<span class="badge bg-secondary">غير محدد</span>')
    
    context = {
        'employees': employees,
        'departments': departments,
        'job_titles': job_titles,
        'total_employees': total_employees,
        'active_employees': active_employees,
        'total_departments': total_departments,
        'total_job_titles': total_job_titles,
        'show_stats': True,
        'table_headers': table_headers,
        'table_actions': table_actions,
    }
    return render(request, 'hr/employee/list.html', context)


@login_required
def employee_detail(request, pk):
    """تفاصيل الموظف"""
    from .services.user_employee_service import UserEmployeeService
    
    employee = get_object_or_404(Employee, pk=pk)
    
    # جلب المستخدمين غير المرتبطين للربط
    unlinked_users = UserEmployeeService.get_unlinked_users()
    
    context = {
        'employee': employee,
        'unlinked_users': unlinked_users,
    }
    return render(request, 'hr/employee/detail.html', context)


@login_required
def employee_delete(request, pk):
    """حذف موظف"""
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        employee.status = 'terminated'
        employee.save()
        messages.success(request, 'تم إنهاء خدمة الموظف')
        return redirect('hr:employee_list')
    
    # تجهيز البيانات للمودال الموحد
    item_fields = [
        {'label': 'الاسم', 'value': employee.get_full_name_ar()},
        {'label': 'رقم الموظف', 'value': employee.employee_number},
        {'label': 'القسم', 'value': employee.department.name_ar},
        {'label': 'الوظيفة', 'value': employee.job_title.title_ar},
    ]
    
    context = {
        'employee': employee,
        'item_fields': item_fields,
    }
    return render(request, 'hr/employee/delete_modal.html', context)


@login_required
def employee_form(request, pk=None):
    """نموذج موحد لإضافة/تعديل موظف"""
    employee = get_object_or_404(Employee, pk=pk) if pk else None
    
    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES, instance=employee)
        if form.is_valid():
            employee_obj = form.save(commit=False)
            
            # توليد رقم الموظف تلقائياً إذا لم يتم إدخاله (للإضافة فقط)
            if not pk and not employee_obj.employee_number:
                employee_obj.employee_number = EmployeeForm.generate_employee_number()
            
            # تعيين المستخدم الذي أنشأ السجل (للإضافة فقط)
            if not pk:
                employee_obj.created_by = request.user
            
            employee_obj.save()
            
            if pk:
                messages.success(request, 'تم تحديث بيانات الموظف بنجاح')
            else:
                messages.success(request, f'تم إضافة الموظف بنجاح - الرقم: {employee_obj.employee_number}')
            
            return redirect('hr:employee_detail', pk=employee_obj.pk)
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = EmployeeForm(instance=employee)
    
    # جلب الأقسام والمسميات الوظيفية
    departments = Department.objects.filter(is_active=True)
    job_titles = JobTitle.objects.filter(is_active=True)
    
    # توليد رقم الموظف المقترح (للإضافة فقط)
    next_employee_number = EmployeeForm.generate_employee_number() if not pk else None
    
    context = {
        'form': form,
        'employee': employee,
        'departments': departments,
        'job_titles': job_titles,
        'next_employee_number': next_employee_number,
    }
    return render(request, 'hr/employee/form.html', context)


@login_required
def department_list(request):
    """قائمة الأقسام"""
    departments = Department.objects.all().select_related('manager', 'parent')
    context = {
        'departments': departments,
        'total_departments': departments.count(),
        'active_departments': departments.filter(is_active=True).count(),
        'total_employees': Employee.objects.filter(status='active').count(),
    }
    return render(request, 'hr/department/list.html', context)


@login_required
def department_delete(request, pk):
    """حذف قسم"""
    department = get_object_or_404(Department, pk=pk)
    
    if request.method == 'POST':
        dept_name = department.name_ar
        department.delete()
        messages.success(request, f'تم حذف القسم "{dept_name}" بنجاح')
        return redirect('hr:department_list')
    
    # تجهيز البيانات للمودال الموحد
    employees_count = department.employees.count()
    sub_departments_count = department.sub_departments.count()
    total_related = employees_count + sub_departments_count
    
    item_fields = [
        {'label': 'الاسم (عربي)', 'value': department.name_ar},
        {'label': 'الاسم (إنجليزي)', 'value': department.name_en or '-'},
        {'label': 'الكود', 'value': department.code},
        {'label': 'القسم الرئيسي', 'value': department.parent or '-'},
        {'label': 'المدير', 'value': department.manager.get_full_name_ar() if department.manager else '-'},
        {'label': 'الحالة', 'value': 'نشط' if department.is_active else 'غير نشط'},
    ]
    
    # بناء رسالة التحذير
    warning_parts = []
    if employees_count > 0:
        warning_parts.append(f'يوجد {employees_count} موظف مرتبط بهذا القسم')
    if sub_departments_count > 0:
        warning_parts.append(f'يوجد {sub_departments_count} قسم فرعي تابع لهذا القسم')
    
    warning_message = '<ul class="mb-0">' + ''.join([f'<li>{part}</li>' for part in warning_parts]) + '</ul>'
    
    context = {
        'department': department,
        'item_fields': item_fields,
        'total_related': total_related,
        'warning_message': warning_message,
        'show_final_warning': total_related > 0,
    }
    return render(request, 'hr/department/delete_modal.html', context)


@login_required
def department_form(request, pk=None):
    """نموذج موحد لإضافة/تعديل قسم"""
    department = get_object_or_404(Department, pk=pk) if pk else None
    
    # توليد الكود التلقائي (للإضافة فقط)
    next_code = None
    if not pk:
        last_dept = Department.objects.order_by('-id').first()
        if last_dept and last_dept.code.startswith('DEPT'):
            try:
                last_num = int(last_dept.code.replace('DEPT', ''))
                next_code = f'DEPT{str(last_num + 1).zfill(3)}'
            except:
                next_code = 'DEPT001'
        else:
            next_code = 'DEPT001'
    
    if request.method == 'POST':
        if not pk:
            # للإضافة: التأكد من عدم تكرار الكود
            code = request.POST.get('code', next_code)
            if Department.objects.filter(code=code).exists():
                last_dept = Department.objects.order_by('-id').first()
                if last_dept and last_dept.code.startswith('DEPT'):
                    try:
                        last_num = int(last_dept.code.replace('DEPT', ''))
                        code = f'DEPT{str(last_num + 1).zfill(3)}'
                    except:
                        code = f'DEPT{str(Department.objects.count() + 1).zfill(3)}'
                else:
                    code = f'DEPT{str(Department.objects.count() + 1).zfill(3)}'
            
            post_data = request.POST.copy()
            post_data['code'] = code
            form = DepartmentForm(post_data)
        else:
            # للتعديل
            form = DepartmentForm(request.POST, instance=department)
        
        if form.is_valid():
            dept = form.save()
            if pk:
                messages.success(request, 'تم تحديث القسم بنجاح')
            else:
                messages.success(request, f'تم إضافة القسم بنجاح - الكود: {dept.code}')
            return redirect('hr:department_list')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = DepartmentForm(instance=department)
    
    # استبعاد القسم الحالي من قائمة الأقسام الرئيسية (للتعديل)
    if pk:
        departments = Department.objects.filter(is_active=True).exclude(pk=pk)
    else:
        departments = Department.objects.filter(is_active=True)
    
    context = {
        'form': form,
        'department': department,
        'next_code': next_code,
        'departments': departments,
        'employees': Employee.objects.filter(status='active'),
    }
    return render(request, 'hr/department/form.html', context)


@login_required
def attendance_list(request):
    """قائمة الحضور"""
    attendances = Attendance.objects.select_related('employee', 'shift').filter(date=date.today())
    context = {
        'attendances': attendances,
        'today': date.today()
    }
    return render(request, 'hr/attendance/list.html', context)


@login_required
def attendance_check_in(request):
    """تسجيل الحضور"""
    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        shift_id = request.POST.get('shift_id')
        
        if employee_id:
            try:
                employee = Employee.objects.get(pk=employee_id)
                shift = Shift.objects.get(pk=shift_id) if shift_id else None
                
                attendance = AttendanceService.check_in(employee, shift)
                messages.success(request, f'تم تسجيل حضور {employee.get_full_name_ar()} بنجاح')
                return redirect('hr:attendance_list')
            except Exception as e:
                messages.error(request, f'خطأ: {str(e)}')
        else:
            messages.error(request, 'يرجى اختيار الموظف')
    
    context = {
        'employees': Employee.objects.filter(status='active'),
        'shifts': Shift.objects.filter(is_active=True)
    }
    return render(request, 'hr/attendance/check_in.html', context)


@login_required
def attendance_check_out(request):
    """تسجيل الانصراف"""
    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        
        if employee_id:
            try:
                employee = Employee.objects.get(pk=employee_id)
                attendance = AttendanceService.check_out(employee)
                messages.success(request, f'تم تسجيل انصراف {employee.get_full_name_ar()} بنجاح')
                return redirect('hr:attendance_list')
            except Exception as e:
                messages.error(request, f'خطأ: {str(e)}')
        else:
            messages.error(request, 'يرجى اختيار الموظف')
    
    context = {
        'employees': Employee.objects.filter(status='active')
    }
    return render(request, 'hr/attendance/check_out.html', context)


# ==================== الورديات ====================

@login_required
def shift_list(request):
    """قائمة الورديات"""
    shifts = Shift.objects.all().order_by('start_time')
    
    # إحصائيات
    stats = {
        'total_shifts': shifts.count(),
        'active_shifts': shifts.filter(is_active=True).count(),
        'morning_shifts': shifts.filter(shift_type='morning').count(),
        'evening_shifts': shifts.filter(shift_type='evening').count(),
        'night_shifts': shifts.filter(shift_type='night').count(),
    }
    
    context = {
        'shifts': shifts,
        'stats': stats,
    }
    return render(request, 'hr/shift/list.html', context)


@login_required
def shift_delete(request, pk):
    """حذف وردية"""
    shift = get_object_or_404(Shift, pk=pk)
    
    if request.method == 'POST':
        shift.is_active = False
        shift.save()
        messages.success(request, 'تم إلغاء تفعيل الوردية')
        return redirect('hr:shift_list')
    
    # عدد الموظفين المرتبطين
    employees_count = Attendance.objects.filter(shift=shift).values('employee').distinct().count()
    
    # تجهيز البيانات للمودال الموحد
    item_fields = [
        {'label': 'اسم الوردية', 'value': shift.name},
        {'label': 'النوع', 'value': shift.get_shift_type_display()},
        {'label': 'الوقت', 'value': f"{shift.start_time.strftime('%H:%M')} - {shift.end_time.strftime('%H:%M')}"},
        {'label': 'عدد الموظفين المرتبطين', 'value': employees_count},
    ]
    
    warning_message = f'تحذير: يوجد {employees_count} موظف مرتبط بهذه الوردية. سيتم إلغاء تفعيل الوردية فقط وليس حذفها نهائياً.'
    
    context = {
        'shift': shift,
        'item_fields': item_fields,
        'employees_count': employees_count,
        'warning_message': warning_message,
    }
    return render(request, 'hr/shift/delete_modal.html', context)


@login_required
def shift_assign_employees(request, pk):
    """تعيين موظفين للوردية"""
    shift = get_object_or_404(Shift, pk=pk)
    
    if request.method == 'POST':
        employee_ids = request.POST.getlist('employees')
        # هنا يمكن إضافة جدول لربط الموظفين بالورديات
        messages.success(request, f'تم تعيين {len(employee_ids)} موظف للوردية')
        return redirect('hr:shift_list')
    
    employees = Employee.objects.filter(status='active')
    context = {
        'shift': shift,
        'employees': employees,
    }
    return render(request, 'hr/shift/assign.html', context)


@login_required
def shift_form(request, pk=None):
    """نموذج موحد لإضافة/تعديل وردية"""
    from .forms.attendance_forms import ShiftForm
    
    shift = get_object_or_404(Shift, pk=pk) if pk else None
    
    if request.method == 'POST':
        form = ShiftForm(request.POST, instance=shift)
        if form.is_valid():
            form.save()
            if pk:
                messages.success(request, 'تم تحديث الوردية بنجاح')
            else:
                messages.success(request, 'تم إضافة الوردية بنجاح')
            return redirect('hr:shift_list')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = ShiftForm(instance=shift)
    
    return render(request, 'hr/shift/form.html', {'form': form, 'shift': shift})


# ==================== ماكينات البصمة ====================

@login_required
def biometric_device_list(request):
    """قائمة ماكينات البصمة - جدول موحد"""
    devices = BiometricDevice.objects.select_related('department', 'created_by').all()
    
    # إحصائيات
    stats = {
        'total_devices': devices.count(),
        'active_devices': devices.filter(is_active=True, status='active').count(),
        'offline_devices': devices.filter(status='error').count(),
        'total_users': devices.aggregate(Sum('total_users'))['total_users__sum'] or 0,
        'total_records': devices.aggregate(Sum('total_records'))['total_records__sum'] or 0,
    }
    
    # Headers للجدول الموحد
    headers = [
        {'key': 'device_name', 'label': 'اسم الماكينة', 'width': '20%', 'template': 'hr/biometric/cells/device_name.html'},
        {'key': 'device_type', 'label': 'النوع', 'width': '10%', 'template': 'hr/biometric/cells/device_type.html'},
        {'key': 'location', 'label': 'الموقع', 'width': '15%', 'template': 'hr/biometric/cells/location.html'},
        {'key': 'ip_address', 'label': 'IP Address', 'width': '12%', 'template': 'hr/biometric/cells/ip_address.html'},
        {'key': 'status', 'label': 'الحالة', 'width': '12%', 'class': 'text-center', 'template': 'hr/biometric/cells/status.html'},
        {'key': 'last_connection', 'label': 'آخر اتصال', 'width': '13%', 'template': 'hr/biometric/cells/last_connection.html'},
        {'key': 'total_users', 'label': 'المستخدمين', 'width': '8%', 'template': 'hr/biometric/cells/total_users.html'},
    ]
    
    # أزرار الإجراءات
    action_buttons = [
        {
            'url': 'hr:biometric_device_detail',
            'icon': 'fa-eye',
            'class': 'btn-info',
            'label': 'عرض'
        },
        {
            'url': 'hr:biometric_device_form_edit',
            'icon': 'fa-edit',
            'class': 'btn-warning',
            'label': 'تعديل'
        }
    ]
    
    context = {
        'devices': devices,
        'stats': stats,
        'headers': headers,
        'action_buttons': action_buttons,
    }
    return render(request, 'hr/biometric/device_list.html', context)

@login_required
def biometric_device_detail(request, pk):
    """تفاصيل ماكينة البصمة - محسّن"""
    device = get_object_or_404(BiometricDevice, pk=pk)
    
    # العدد الافتراضي للسجلات
    default_logs_count = 10
    
    # آخر السجلات
    recent_logs = BiometricLog.objects.filter(device=device).select_related('employee')[:default_logs_count]
    
    # آخر عمليات المزامنة
    sync_logs = BiometricSyncLog.objects.filter(device=device).order_by('-started_at')[:10]
    
    # Headers للجدول الموحد - سجلات البصمة
    log_headers = [
        {'key': 'timestamp', 'label': 'الوقت', 'format': 'datetime', 'width': '20%'},
        {'key': 'user_id', 'label': 'معرف المستخدم', 'width': '15%'},
        {'key': 'employee', 'label': 'الموظف', 'width': '25%', 'template': 'hr/biometric/cells/log_employee.html'},
        {'key': 'log_type', 'label': 'النوع', 'width': '20%', 'template': 'hr/biometric/cells/log_type.html'},
        {'key': 'is_processed', 'label': 'حالة المعالجة', 'width': '20%', 'template': 'hr/biometric/cells/log_status.html'},
    ]
    
    context = {
        'device': device,
        'recent_logs': recent_logs,
        'sync_logs': sync_logs,
        'log_headers': log_headers,
        'logs_count': default_logs_count,  # إضافة العدد للـ context
    }
    return render(request, 'hr/biometric/device_detail.html', context)


@login_required
def biometric_device_logs_ajax(request, pk):
    """جلب سجلات البصمة ديناميكياً حسب العدد المطلوب"""
    device = get_object_or_404(BiometricDevice, pk=pk)
    
    # الحصول على العدد المطلوب من الـ query parameter
    limit = int(request.GET.get('limit', 10))
    
    # جلب السجلات
    recent_logs = BiometricLog.objects.filter(device=device).select_related('employee')[:limit]
    
    # Headers للجدول
    log_headers = [
        {'key': 'timestamp', 'label': 'الوقت', 'format': 'datetime', 'width': '20%'},
        {'key': 'user_id', 'label': 'معرف المستخدم', 'width': '15%'},
        {'key': 'employee', 'label': 'الموظف', 'width': '25%', 'template': 'hr/biometric/cells/log_employee.html'},
        {'key': 'log_type', 'label': 'النوع', 'width': '20%', 'template': 'hr/biometric/cells/log_type.html'},
        {'key': 'is_processed', 'label': 'حالة المعالجة', 'width': '20%', 'template': 'hr/biometric/cells/log_status.html'},
    ]
    
    context = {
        'data': recent_logs,
        'headers': log_headers,
        'empty_message': 'لا توجد سجلات بصمة',
        'empty_icon': 'fingerprint',
        'primary_key': 'id',
        'table_id': 'biometric-logs-table',
        'length_options': '5,10,20,50',
        'default_length': str(limit),  # القيمة المختارة حالياً
    }
    
    return render(request, 'components/data_table.html', context)


@login_required
def biometric_device_form(request, pk=None):
    """نموذج موحد لإضافة/تعديل ماكينة بصمة"""
    from .forms.biometric_forms import BiometricDeviceForm
    
    device = get_object_or_404(BiometricDevice, pk=pk) if pk else None
    
    if request.method == 'POST':
        form = BiometricDeviceForm(request.POST, instance=device)
        if form.is_valid():
            device_obj = form.save(commit=False)
            if not pk:
                device_obj.created_by = request.user
            device_obj.save()
            
            if pk:
                messages.success(request, 'تم تحديث الماكينة بنجاح')
                return redirect('hr:biometric_device_detail', pk=pk)
            else:
                messages.success(request, f'تم إضافة الماكينة بنجاح - الكود: {device_obj.device_code}')
                return redirect('hr:biometric_device_detail', pk=device_obj.pk)
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = BiometricDeviceForm(instance=device)
    
    return render(request, 'hr/biometric/device_form.html', {'form': form, 'device': device})


@login_required
def biometric_device_delete(request, pk):
    """حذف ماكينة البصمة"""
    device = get_object_or_404(BiometricDevice, pk=pk)
    
    if request.method == 'POST':
        device.is_active = False
        device.status = 'inactive'
        device.save()
        messages.success(request, 'تم إلغاء تفعيل الماكينة')
        return redirect('hr:biometric_device_list')
    
    logs_count = BiometricLog.objects.filter(device=device).count()
    
    # تجهيز البيانات للمودال الموحد
    item_fields = [
        {'label': 'اسم الماكينة', 'value': device.device_name},
        {'label': 'الموقع', 'value': device.location},
        {'label': 'IP Address', 'value': device.connection_string},
        {'label': 'عدد السجلات', 'value': logs_count},
    ]
    
    warning_message = 'سيتم إلغاء تفعيل الماكينة فقط. السجلات ستبقى محفوظة.' if logs_count > 0 else ''
    
    context = {
        'device': device,
        'item_fields': item_fields,
        'logs_count': logs_count,
        'warning_message': warning_message,
    }
    return render(request, 'hr/biometric/device_delete_modal.html', context)




@login_required
def biometric_device_test(request, pk):
    """اختبار الاتصال بالماكينة - AJAX Modal"""
    from .bridge_agent_utils import test_device_connection
    
    device = get_object_or_404(BiometricDevice, pk=pk)
    
    if request.method == 'GET':
        # عرض المودال
        context = {'device': device}
        return render(request, 'hr/biometric/device_test_modal.html', context)
    
    # POST - تنفيذ الاختبار
    if request.method == 'POST':
        success, message, details = test_device_connection(device)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            response_data = {
                'success': success,
                'message': message
            }
            if details:
                response_data['details'] = details
            return JsonResponse(response_data)
        
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
    
    return redirect('hr:biometric_device_detail', pk=pk)


@login_required
def biometric_agent_setup(request, pk):
    """صفحة إرشادات إعداد Bridge Agent"""
    device = get_object_or_404(BiometricDevice, pk=pk)
    
    context = {
        'device': device,
        'page_title': 'إعداد Bridge Agent',
    }
    
    return render(request, 'hr/biometric_agent_setup.html', context)


@login_required
def biometric_device_download_agent(request, pk):
    """تحميل ملف إعدادات Bridge Agent"""
    from .bridge_agent_utils import generate_agent_config, create_agent_zip_package, create_download_response
    
    device = get_object_or_404(BiometricDevice, pk=pk)
    
    # توليد الإعدادات
    config, agent_secret = generate_agent_config(device, request)
    
    # إنشاء ملف ZIP
    zip_buffer = create_agent_zip_package(device, config)
    
    # عرض رسالة للمستخدم
    messages.success(
        request,
        f'تم تحميل Bridge Agent. لا تنسى إضافة المفتاح السري في settings.py:\n'
        f'BRIDGE_AGENTS = {{\'{device.device_code}\': \'{agent_secret}\'}}'
    )
    
    # إرجاع الملف
    return create_download_response(device, zip_buffer)


@login_required
def biometric_log_list(request):
    """قائمة سجلات البصمات"""
    logs = BiometricLog.objects.select_related(
        'device', 'employee', 'attendance'
    )
    
    # فلترة أولاً
    device_id = request.GET.get('device')
    if device_id:
        logs = logs.filter(device_id=device_id)
    
    employee_id = request.GET.get('employee')
    if employee_id:
        logs = logs.filter(employee_id=employee_id)
    
    is_processed = request.GET.get('processed')
    if is_processed:
        logs = logs.filter(is_processed=is_processed == 'true')
    
    # ثم الترتيب والـ limit
    logs = logs.order_by('-timestamp')[:500]
    
    devices = BiometricDevice.objects.filter(is_active=True)
    
    context = {
        'logs': logs,
        'devices': devices,
    }
    return render(request, 'hr/biometric/log_list.html', context)


# ==================== Bridge Agent API ====================

class BridgeSyncThrottle(AnonRateThrottle):
    """Rate limiting for Bridge Agent API"""
    rate = '100/hour'  # 100 requests per hour

@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([BridgeSyncThrottle])
def biometric_bridge_sync(request):
    """
    API لاستقبال البيانات من Bridge Agent
    """
    # Logging بدلاً من print
    logger.info("=" * 60)
    logger.info("Bridge Sync Request Received!")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Data: {request.data}")
    logger.info("=" * 60)
    
    # التحقق من Agent Code و Secret
    auth_header = request.headers.get('Authorization', '')
    agent_code = request.data.get('agent_code')
    
    if not auth_header.startswith('Bearer '):
        return Response({'error': 'Invalid authorization header'}, status=401)
    
    agent_secret = auth_header.replace('Bearer ', '')
    
    # التحقق من Agent (يمكن تخزين الـ Agents في قاعدة البيانات)
    # هنا نستخدم إعدادات بسيطة
    from django.conf import settings
    valid_agents = getattr(settings, 'BRIDGE_AGENTS', {})
    
    # Debug logging
    logger.info(f"Agent Code: {agent_code}")
    logger.info(f"Agent Secret Received: {agent_secret}")
    logger.info(f"Valid Agents: {valid_agents}")
    
    if agent_code not in valid_agents:
        logger.error(f"Agent code '{agent_code}' not found in valid agents")
        return Response({'error': 'Invalid agent credentials'}, status=401)
    
    expected_secret = valid_agents[agent_code]
    # استخدام hmac.compare_digest لمنع timing attacks
    if not hmac.compare_digest(expected_secret, agent_secret):
        logger.error(f"Secret mismatch!")
        logger.error(f"  Agent Code: {agent_code}")
        return Response({'error': 'Invalid agent credentials'}, status=401)
    
    # جلب السجلات
    records = request.data.get('records', [])
    
    if not records:
        return Response({'message': 'No records to process', 'processed': 0})
    
    # البحث عن الماكينة المرتبطة بالـ Agent
    try:
        device = BiometricDevice.objects.get(device_code=agent_code)
    except BiometricDevice.DoesNotExist:
        return Response({'error': 'Device not found for this agent'}, status=404)
    
    # معالجة السجلات
    processed = 0
    skipped = 0
    
    for record in records:
        try:
            user_id = record.get('user_id')
            timestamp_str = record.get('timestamp')
            
            # تحويل التاريخ
            from dateutil import parser
            timestamp = parser.parse(timestamp_str)
            
            # محاولة ربط بالموظف
            employee = None
            try:
                employee = Employee.objects.get(employee_number=user_id)
            except Employee.DoesNotExist:
                pass
            
            # استخدام get_or_create لمنع race condition
            log, created = BiometricLog.objects.get_or_create(
                device=device,
                user_id=user_id,
                timestamp=timestamp,
                defaults={
                    'employee': employee,
                    'log_type': 'check_in',
                    'is_processed': False,
                    'raw_data': record
                }
            )
            
            if created:
                processed += 1
            else:
                skipped += 1
                
        except Exception as e:
            logger.error(f"Error processing record: {e}")
            continue
    
    # تحديث إحصائيات الماكينة
    from django.utils import timezone
    device.total_records = BiometricLog.objects.filter(device=device).count()
    device.last_sync = timezone.now()
    device.last_connection = timezone.now()
    device.status = 'active'
    device.save()
    
    return Response({
        'success': True,
        'message': f'Processed {processed} records',
        'processed': processed,
        'skipped': skipped,
        'total': len(records)
    })


@login_required
def leave_list(request):
    """قائمة الإجازات"""
    leaves = Leave.objects.select_related('employee', 'leave_type').all()
    return render(request, 'hr/leave/list.html', {'leaves': leaves})


@login_required
def leave_request(request):
    """طلب إجازة جديد"""
    from .services.leave_service import LeaveService
    
    # جلب الموظف الحالي
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'لا يوجد حساب موظف مرتبط بحسابك')
        return redirect('hr:dashboard')
    
    # جلب أرصدة الإجازات للموظف
    current_year = date.today().year
    balances = LeaveBalance.objects.filter(
        employee=employee,
        year=current_year
    ).select_related('leave_type')
    
    # تحديث الأرصدة المستحقة
    for balance in balances:
        balance.update_accrued_days()
    
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST, request.FILES)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.employee = employee
            leave.requested_by = request.user
            
            # حساب عدد الأيام
            days_count = (leave.end_date - leave.start_date).days + 1
            leave.days_count = days_count
            
            # التحقق من الرصيد المتاح
            balance = balances.filter(leave_type=leave.leave_type).first()
            if balance and balance.remaining_days < days_count:
                messages.error(request, f'رصيدك غير كافٍ. المتبقي: {balance.remaining_days} يوم، المطلوب: {days_count} يوم')
            else:
                leave.save()
                messages.success(request, 'تم تقديم طلب الإجازة بنجاح')
                return redirect('hr:leave_detail', pk=leave.pk)
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = LeaveRequestForm()
    
    context = {
        'form': form,
        'employee': employee,
        'balances': balances,
        'current_year': current_year,
    }
    return render(request, 'hr/leave/request.html', context)


@login_required
def leave_detail(request, pk):
    """تفاصيل الإجازة"""
    leave = get_object_or_404(Leave, pk=pk)
    return render(request, 'hr/leave/detail.html', {'leave': leave})


@login_required
def leave_approve(request, pk):
    """اعتماد الإجازة"""
    leave = get_object_or_404(Leave, pk=pk)
    if request.method == 'POST':
        review_notes = request.POST.get('review_notes', '')
        try:
            LeaveService.approve_leave(leave, request.user, review_notes)
            messages.success(request, 'تم اعتماد الإجازة بنجاح')
            return redirect('hr:leave_detail', pk=pk)
        except Exception as e:
            messages.error(request, f'خطأ: {str(e)}')
    return render(request, 'hr/leave/approve.html', {'leave': leave})


@login_required
def leave_reject(request, pk):
    """رفض الإجازة"""
    leave = get_object_or_404(Leave, pk=pk)
    if request.method == 'POST':
        review_notes = request.POST.get('review_notes', '')
        try:
            LeaveService.reject_leave(leave, request.user, review_notes)
            messages.success(request, 'تم رفض الإجازة')
            return redirect('hr:leave_detail', pk=pk)
        except Exception as e:
            messages.error(request, f'خطأ: {str(e)}')
    return render(request, 'hr/leave/reject.html', {'leave': leave})


# ==================== أرصدة الإجازات ====================

@login_required
def leave_balance_list(request):
    """قائمة أرصدة الإجازات"""
    from core.models import SystemSetting
    from collections import defaultdict
    
    current_year = date.today().year
    year = request.GET.get('year', current_year)
    
    balances = LeaveBalance.objects.filter(year=year).select_related(
        'employee', 'employee__department', 'employee__job_title', 'leave_type'
    ).order_by('employee__employee_number')
    
    # تجميع الأرصدة حسب الموظف
    employees_balances = defaultdict(list)
    for balance in balances:
        employees_balances[balance.employee].append(balance)
    
    # تحويل إلى قائمة مرتبة
    grouped_balances = [
        {
            'employee': employee,
            'balances': employee_balances,
            'total_remaining': sum(b.remaining_days for b in employee_balances),
            'total_used': sum(b.used_days for b in employee_balances),
        }
        for employee, employee_balances in employees_balances.items()
    ]
    
    # ترتيب حسب رقم الموظف
    grouped_balances.sort(key=lambda x: x['employee'].employee_number)
    
    # إحصائيات
    from django.db.models import Sum, Avg
    stats = balances.aggregate(
        total_employees=Count('employee', distinct=True),
        total_days=Sum('total_days'),
        total_used=Sum('used_days'),
        total_remaining=Sum('remaining_days'),
        avg_remaining=Avg('remaining_days')
    )
    
    # جلب إعدادات الترحيل
    rollover_enabled = SystemSetting.get_setting('leave_rollover_enabled', False)
    
    context = {
        'balances': balances,
        'grouped_balances': grouped_balances,
        'stats': stats,
        'current_year': current_year,
        'selected_year': int(year),
        'years': range(current_year - 2, current_year + 2),
        'rollover_enabled': rollover_enabled,
    }
    return render(request, 'hr/leave_balance/list.html', context)


@login_required
def leave_balance_employee(request, employee_id):
    """أرصدة إجازات موظف محدد"""
    employee = get_object_or_404(Employee, pk=employee_id)
    current_year = date.today().year
    
    balances = LeaveBalance.objects.filter(
        employee=employee,
        year=current_year
    ).select_related('leave_type')
    
    # سجل الإجازات
    leaves = Leave.objects.filter(
        employee=employee,
        start_date__year=current_year
    ).select_related('leave_type').order_by('-start_date')
    
    context = {
        'employee': employee,
        'balances': balances,
        'leaves': leaves,
        'current_year': current_year,
    }
    return render(request, 'hr/leave_balance/employee.html', context)


@login_required
def leave_balance_update(request):
    """تحديث أرصدة الإجازات"""
    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        leave_type_id = request.POST.get('leave_type_id')
        year = request.POST.get('year', date.today().year)
        total_days = request.POST.get('total_days')
        
        try:
            balance, created = LeaveBalance.objects.get_or_create(
                employee_id=employee_id,
                leave_type_id=leave_type_id,
                year=year,
                defaults={'total_days': total_days, 'remaining_days': total_days}
            )
            
            if not created:
                balance.total_days = int(total_days)
                balance.update_balance()
            
            messages.success(request, 'تم تحديث الرصيد بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ: {str(e)}')
        
        return redirect('hr:leave_balance_list')
    
    employees = Employee.objects.filter(status='active')
    leave_types = LeaveType.objects.filter(is_active=True)
    
    context = {
        'employees': employees,
        'leave_types': leave_types,
        'current_year': date.today().year,
    }
    return render(request, 'hr/leave_balance/update.html', context)


@login_required
def leave_balance_rollover(request):
    """ترحيل أرصدة الإجازات للسنة الجديدة"""
    from core.models import SystemSetting
    
    # التحقق من تفعيل الترحيل في الإعدادات
    rollover_enabled = SystemSetting.get_setting('leave_rollover_enabled', False)
    max_rollover_days = SystemSetting.get_setting('leave_rollover_max_days', 7)
    
    # جلب نوع الإجازة السنوية للأمثلة (أو أي نوع نشط)
    annual_leave = LeaveType.objects.filter(code='ANNUAL', is_active=True).first()
    if not annual_leave:
        # إذا لم توجد إجازة سنوية، خذ أول نوع نشط
        annual_leave = LeaveType.objects.filter(is_active=True).first()
    annual_days = annual_leave.max_days_per_year if annual_leave else 0
    
    if request.method == 'POST':
        if not rollover_enabled:
            messages.warning(request, 'ترحيل الإجازات غير مفعل في الإعدادات. يرجى تفعيله من إعدادات الموارد البشرية.')
            return redirect('hr:leave_balance_list')
        
        from_year = int(request.POST.get('from_year'))
        to_year = int(request.POST.get('to_year'))
        rollover_unused = request.POST.get('rollover_unused') == 'on'
        
        try:
            employees = Employee.objects.filter(status='active')
            leave_types = LeaveType.objects.filter(is_active=True)
            created_count = 0
            total_rollover_days = 0
            
            for employee in employees:
                for leave_type in leave_types:
                    # الحصول على الرصيد القديم
                    old_balance = LeaveBalance.objects.filter(
                        employee=employee,
                        leave_type=leave_type,
                        year=from_year
                    ).first()
                    
                    # حساب الرصيد الجديد
                    total_days = leave_type.max_days_per_year
                    if rollover_unused and old_balance and old_balance.remaining_days > 0:
                        # تطبيق الحد الأقصى للأيام المرحلة
                        rollover_days = min(old_balance.remaining_days, max_rollover_days)
                        total_days += rollover_days
                        total_rollover_days += rollover_days
                    
                    # إنشاء الرصيد الجديد
                    LeaveBalance.objects.get_or_create(
                        employee=employee,
                        leave_type=leave_type,
                        year=to_year,
                        defaults={
                            'total_days': total_days,
                            'remaining_days': total_days
                        }
                    )
                    created_count += 1
            
            if total_rollover_days > 0:
                messages.success(request, f'تم ترحيل {created_count} رصيد بنجاح (تم ترحيل {total_rollover_days} يوم بحد أقصى {max_rollover_days} يوم لكل رصيد)')
            else:
                messages.success(request, f'تم إنشاء {created_count} رصيد جديد بنجاح')
            return redirect('hr:leave_balance_list')
        except Exception as e:
            messages.error(request, f'خطأ: {str(e)}')
    
    current_year = date.today().year
    context = {
        'current_year': current_year,
        'years': range(current_year - 2, current_year + 3),
        'rollover_enabled': rollover_enabled,
        'max_rollover_days': max_rollover_days,
        'annual_days': annual_days,
    }
    return render(request, 'hr/leave_balance/rollover.html', context)


@login_required
def leave_balance_accrual_status(request, employee_id):
    """عرض حالة استحقاق إجازات موظف محدد"""
    from .services.leave_accrual_service import LeaveAccrualService
    from core.models import SystemSetting
    
    employee = get_object_or_404(Employee, pk=employee_id)
    status = LeaveAccrualService.get_employee_accrual_status(employee)
    
    # جلب الإعدادات للعرض في الـ template
    leave_settings = {
        'probation_months': SystemSetting.get_setting('leave_accrual_probation_months', 3),
        'partial_percentage': SystemSetting.get_setting('leave_accrual_partial_percentage', 25),
        'full_months': SystemSetting.get_setting('leave_accrual_full_months', 6),
    }
    
    context = {
        'employee': employee,
        'status': status,
        'leave_settings': leave_settings,
    }
    return render(request, 'hr/leave_balance/accrual_status.html', context)


@login_required
def payroll_list(request):
    """قائمة كشوف الرواتب"""
    payrolls = Payroll.objects.select_related('employee', 'salary').all()
    return render(request, 'hr/payroll/list.html', {'payrolls': payrolls})


@login_required
def payroll_run_list(request):
    """قائمة مسيرات الرواتب"""
    # جمع الرواتب حسب الشهر
    from django.db.models import Count, Sum
    payroll_runs = Payroll.objects.values('month').annotate(
        total_employees=Count('id'),
        total_amount=Sum('net_salary'),
        paid_count=Count('id', filter=models.Q(status='paid'))
    ).order_by('-month')
    
    return render(request, 'hr/payroll/run_list.html', {'payroll_runs': payroll_runs})


@login_required
def payroll_run_process(request):
    """معالجة مسيرة رواتب جديدة"""
    if request.method == 'POST':
        form = PayrollProcessForm(request.POST)
        if form.is_valid():
            try:
                month_str = form.cleaned_data['month']
                department = form.cleaned_data.get('department')
                
                payrolls = PayrollService.process_monthly_payroll(
                    month_str,
                    department,
                    request.user
                )
                messages.success(request, f'تم معالجة {len(payrolls)} كشف راتب بنجاح')
                return redirect('hr:payroll_run_detail', month=month_str)
            except Exception as e:
                messages.error(request, f'خطأ: {str(e)}')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = PayrollProcessForm()
    
    return render(request, 'hr/payroll/run_process.html', {'form': form})


@login_required
def payroll_run_detail(request, month):
    """تفاصيل مسيرة رواتب شهر محدد"""
    from django.db.models import Sum
    
    payrolls = Payroll.objects.filter(month=month).select_related('employee', 'salary')
    
    stats = payrolls.aggregate(
        total_employees=Count('id'),
        total_gross=Sum('gross_salary'),
        total_deductions=Sum('total_deductions'),
        total_net=Sum('net_salary'),
        paid_count=Count('id', filter=models.Q(status='paid'))
    )
    
    context = {
        'month': month,
        'payrolls': payrolls,
        'stats': stats,
    }
    return render(request, 'hr/payroll/run_detail.html', context)


@login_required
def payroll_detail(request, pk):
    """تفاصيل كشف الراتب"""
    payroll = get_object_or_404(Payroll, pk=pk)
    return render(request, 'hr/payroll/detail.html', {'payroll': payroll})


# ==================== السلف ====================

@login_required
def advance_list(request):
    """قائمة السلف"""
    advances = Advance.objects.select_related('employee').all()
    return render(request, 'hr/advance/list.html', {'advances': advances})


@login_required
def advance_request(request):
    """طلب سلفة جديدة"""
    if request.method == 'POST':
        # سيتم إضافة النموذج لاحقاً
        messages.success(request, 'تم تقديم طلب السلفة بنجاح')
        return redirect('hr:advance_list')
    return render(request, 'hr/advance/request.html')


@login_required
def advance_detail(request, pk):
    """تفاصيل السلفة"""
    advance = get_object_or_404(Advance, pk=pk)
    return render(request, 'hr/advance/detail.html', {'advance': advance})


@login_required
def advance_approve(request, pk):
    """اعتماد السلفة"""
    advance = get_object_or_404(Advance, pk=pk)
    if request.method == 'POST':
        advance.status = 'approved'
        advance.approved_by = request.user
        advance.approved_at = date.today()
        advance.save()
        messages.success(request, 'تم اعتماد السلفة بنجاح')
        return redirect('hr:advance_detail', pk=pk)
    return render(request, 'hr/advance/approve.html', {'advance': advance})


@login_required
def advance_reject(request, pk):
    """رفض السلفة"""
    advance = get_object_or_404(Advance, pk=pk)
    if request.method == 'POST':
        advance.status = 'rejected'
        advance.save()
        messages.success(request, 'تم رفض السلفة')
        return redirect('hr:advance_detail', pk=pk)
    return render(request, 'hr/advance/reject.html', {'advance': advance})


@login_required
def salary_settings(request):
    """إعدادات الرواتب"""
    from .models import Salary
    salaries = Salary.objects.all()
    return render(request, 'hr/salary/settings.html', {'salaries': salaries})


# ==================== العقود ====================

@login_required
def contract_list(request):
    """قائمة العقود"""
    contracts = Contract.objects.select_related('employee').all()
    return render(request, 'hr/contract/list.html', {'contracts': contracts})


@login_required
def contract_detail(request, pk):
    """تفاصيل العقد"""
    contract = get_object_or_404(Contract, pk=pk)
    return render(request, 'hr/contract/detail.html', {'contract': contract})


@login_required
def contract_form(request, pk=None):
    """نموذج موحد لإضافة/تعديل عقد"""
    from .forms.contract_forms import ContractForm
    from .models import SalaryComponent
    
    contract = get_object_or_404(Contract, pk=pk) if pk else None
    
    if request.method == 'POST':
        form = ContractForm(request.POST, instance=contract)
        if form.is_valid():
            contract_obj = form.save(commit=False)
            
            # توليد رقم العقد تلقائياً إذا لم يتم إدخاله (للإضافة فقط)
            if not pk and not contract_obj.contract_number:
                contract_obj.contract_number = ContractForm.generate_contract_number()
            
            # تعيين المستخدم الذي أنشأ السجل (للإضافة فقط)
            if not pk:
                contract_obj.created_by = request.user
                # تعيين نوع العقد الافتراضي (عقد محدد المدة)
                if not contract_obj.contract_type:
                    contract_obj.contract_type = 'contract'
            
            contract_obj.save()
            
            # حفظ مكونات الراتب
            if pk:
                # حذف المكونات القديمة (ما عدا الأساسية)
                contract_obj.salary_components.filter(is_basic=False).delete()
            
            # حفظ المستحقات
            for key, value in request.POST.items():
                if key.startswith('earning_name_'):
                    counter = key.split('_')[-1]
                    name = request.POST.get(f'earning_name_{counter}')
                    formula = request.POST.get(f'earning_formula_{counter}', '')
                    amount = request.POST.get(f'earning_amount_{counter}')
                    order = request.POST.get(f'earning_order_{counter}', 0)
                    
                    if name and amount:
                        SalaryComponent.objects.create(
                            contract=contract_obj,
                            component_type='earning',
                            name=name,
                            formula=formula,
                            amount=amount,
                            order=order
                        )
            
            # حفظ الاستقطاعات
            for key, value in request.POST.items():
                if key.startswith('deduction_name_'):
                    counter = key.split('_')[-1]
                    name = request.POST.get(f'deduction_name_{counter}')
                    formula = request.POST.get(f'deduction_formula_{counter}', '')
                    amount = request.POST.get(f'deduction_amount_{counter}')
                    order = request.POST.get(f'deduction_order_{counter}', 0)
                    
                    if name and amount:
                        SalaryComponent.objects.create(
                            contract=contract_obj,
                            component_type='deduction',
                            name=name,
                            formula=formula,
                            amount=amount,
                            order=order
                        )
            
            if pk:
                messages.success(request, 'تم تحديث العقد بنجاح')
            else:
                messages.success(request, f'تم إضافة العقد بنجاح - الرقم: {contract_obj.contract_number}')
            return redirect('hr:contract_list')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = ContractForm(instance=contract)
    
    # توليد رقم العقد المقترح (للإضافة فقط)
    next_contract_number = ContractForm.generate_contract_number() if not pk else None
    
    # جلب مكونات الراتب الموجودة (للتعديل)
    earnings = []
    deductions = []
    if contract:
        earnings = contract.salary_components.filter(component_type='earning', is_basic=False)
        deductions = contract.salary_components.filter(component_type='deduction')
    
    # جلب إعدادات النظام
    from core.models import SystemSetting
    try:
        currency_symbol = SystemSetting.objects.filter(key='currency_symbol').first()
        system_settings = {
            'currency_symbol': currency_symbol.value if currency_symbol else 'جنيه'
        }
    except:
        system_settings = {'currency_symbol': 'جنيه'}
    
    context = {
        'form': form,
        'contract': contract,
        'next_contract_number': next_contract_number,
        'earnings': earnings,
        'deductions': deductions,
        'system_settings': system_settings,
    }
    return render(request, 'hr/contract/form.html', context)


@login_required
def get_salary_component_templates(request):
    """API لجلب قوالب مكونات الراتب"""
    from django.http import JsonResponse
    from .models import SalaryComponentTemplate
    
    component_type = request.GET.get('type', 'earning')
    
    templates = SalaryComponentTemplate.objects.filter(
        component_type=component_type,
        is_active=True
    ).order_by('order', 'name')
    
    data = [{
        'id': t.id,
        'name': t.name,
        'formula': t.formula,
        'default_amount': str(t.default_amount),
        'description': t.description
    } for t in templates]
    
    return JsonResponse({'success': True, 'templates': data})


@login_required
def contract_renew(request, pk):
    """تجديد العقد"""
    contract = get_object_or_404(Contract, pk=pk)
    if request.method == 'POST':
        new_end_date = request.POST.get('new_end_date')
        if new_end_date:
            new_contract = contract.renew(new_end_date, request.user)
            messages.success(request, f'تم تجديد العقد بنجاح. رقم العقد الجديد: {new_contract.contract_number}')
            return redirect('hr:contract_detail', pk=new_contract.pk)
    return render(request, 'hr/contract/renew.html', {'contract': contract})


@login_required
def contract_terminate(request, pk):
    """إنهاء العقد"""
    contract = get_object_or_404(Contract, pk=pk)
    if request.method == 'POST':
        termination_date = request.POST.get('termination_date')
        contract.terminate(termination_date)
        messages.success(request, 'تم إنهاء العقد بنجاح')
        return redirect('hr:contract_detail', pk=pk)
    return render(request, 'hr/contract/terminate.html', {'contract': contract})


@login_required
def contract_expiring(request):
    """العقود قرب الانتهاء"""
    # العقود التي ستنتهي خلال 60 يوم
    expiry_date = date.today() + timedelta(days=60)
    contracts = Contract.objects.filter(
        status='active',
        end_date__lte=expiry_date,
        end_date__gte=date.today()
    ).select_related('employee').order_by('end_date')
    
    return render(request, 'hr/contract/expiring.html', {'contracts': contracts})


# ==================== المسميات الوظيفية ====================

@login_required
def job_title_list(request):
    """قائمة المسميات الوظيفية"""
    job_titles = JobTitle.objects.select_related('department').filter(is_active=True)
    return render(request, 'hr/job_title/list.html', {'job_titles': job_titles})


@login_required
def job_title_delete(request, pk):
    """حذف مسمى وظيفي"""
    job_title = get_object_or_404(JobTitle, pk=pk)
    if request.method == 'POST':
        # التحقق من عدم وجود موظفين مرتبطين بهذه الوظيفة
        if job_title.employees.exists():
            messages.error(request, 'لا يمكن حذف هذه الوظيفة لأن هناك موظفين مرتبطين بها')
            return redirect('hr:job_title_list')
        
        # حذف نهائي (Hard Delete)
        job_title.delete()
        messages.success(request, 'تم حذف المسمى الوظيفي نهائياً')
        return redirect('hr:job_title_list')
    
    # تجهيز البيانات للمودال الموحد
    employees_count = job_title.employees.count()
    
    item_fields = [
        {'label': 'الكود', 'value': job_title.code},
        {'label': 'المسمى (عربي)', 'value': job_title.title_ar},
        {'label': 'المسمى (إنجليزي)', 'value': job_title.title_en or '-'},
        {'label': 'القسم', 'value': job_title.department.name_ar},
        {'label': 'عدد الموظفين', 'value': employees_count},
    ]
    
    warning_message = f'تحذير: يوجد {employees_count} موظف مرتبط بهذا المسمى الوظيفي. سيتم إلغاء تفعيل المسمى فقط وليس حذفه نهائياً.'
    
    context = {
        'job_title': job_title,
        'item_fields': item_fields,
        'employees_count': employees_count,
        'warning_message': warning_message,
    }
    return render(request, 'hr/job_title/delete_modal.html', context)


@login_required
def job_title_form(request, pk=None):
    """نموذج موحد لإضافة/تعديل مسمى وظيفي"""
    from .forms.employee_forms import JobTitleForm
    
    job_title = get_object_or_404(JobTitle, pk=pk) if pk else None
    
    if request.method == 'POST':
        form = JobTitleForm(request.POST, instance=job_title)
        if form.is_valid():
            form.save()
            if pk:
                messages.success(request, 'تم تحديث المسمى الوظيفي بنجاح')
            else:
                messages.success(request, 'تم إضافة المسمى الوظيفي بنجاح')
            return redirect('hr:job_title_list')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = JobTitleForm(instance=job_title)
    
    return render(request, 'hr/job_title/form.html', {'form': form, 'job_title': job_title})


# ==================== الهيكل التنظيمي ====================

@login_required
def organization_chart(request):
    """عرض الهيكل التنظيمي"""
    # جلب الأقسام الرئيسية (التي ليس لها قسم أب)
    root_departments = Department.objects.filter(parent=None, is_active=True).prefetch_related('sub_departments')
    
    context = {
        'root_departments': root_departments,
        'total_departments': Department.objects.filter(is_active=True).count(),
        'total_employees': Employee.objects.filter(status='active').count(),
        'total_job_titles': JobTitle.objects.filter(is_active=True).count(),
    }
    return render(request, 'hr/organization/chart.html', context)


# ==================== إعدادات الموارد البشرية ====================

@login_required
def hr_settings(request):
    """صفحة إعدادات الموارد البشرية"""
    from core.models import SystemSetting
    
    if request.method == 'POST':
        # حفظ إعدادات الإجازات
        
        # الحقول النصية والرقمية
        numeric_settings = [
            'leave_accrual_probation_months',
            'leave_accrual_partial_percentage',
            'leave_accrual_full_months',
            'leave_rollover_max_days',
        ]
        
        for setting_key in numeric_settings:
            if setting_key in request.POST:
                value = request.POST.get(setting_key)
                SystemSetting.objects.filter(key=setting_key).update(value=value)
        
        # الـ checkboxes (تحتاج معالجة خاصة)
        checkbox_settings = [
            'leave_auto_create_balances',
            'leave_rollover_enabled',
        ]
        
        for setting_key in checkbox_settings:
            # checkbox يرسل 'on' إذا كان محدد، ولا يرسل شيء إذا لم يكن محدد
            value = 'true' if setting_key in request.POST else 'false'
            SystemSetting.objects.filter(key=setting_key).update(value=value)
        
        # حفظ عدد أيام أنواع الإجازات
        leave_types = LeaveType.objects.filter(is_active=True)
        for leave_type in leave_types:
            field_name = f'leave_type_{leave_type.id}_days'
            if field_name in request.POST:
                new_days = int(request.POST.get(field_name))
                if new_days != leave_type.max_days_per_year:
                    leave_type.max_days_per_year = new_days
                    leave_type.save()
        
        messages.success(request, 'تم حفظ إعدادات الإجازات بنجاح')
        return redirect('hr:hr_settings')
    
    # جلب إعدادات الإجازات
    leave_settings = {
        'probation_months': SystemSetting.get_setting('leave_accrual_probation_months', 3),
        'partial_percentage': SystemSetting.get_setting('leave_accrual_partial_percentage', 25),
        'full_months': SystemSetting.get_setting('leave_accrual_full_months', 6),
        'auto_create': SystemSetting.get_setting('leave_auto_create_balances', True),
        'rollover_enabled': SystemSetting.get_setting('leave_rollover_enabled', False),
        'rollover_max_days': SystemSetting.get_setting('leave_rollover_max_days', 7),
    }
    
    # جلب أنواع الإجازات
    leave_types = LeaveType.objects.filter(is_active=True).order_by('code')
    
    # إحصائيات قوالب مكونات الراتب
    from .models import SalaryComponentTemplate
    salary_templates_earnings = SalaryComponentTemplate.objects.filter(component_type='earning', is_active=True).count()
    salary_templates_deductions = SalaryComponentTemplate.objects.filter(component_type='deduction', is_active=True).count()
    
    context = {
        'active_menu': 'hr',
        'leave_settings': leave_settings,
        'leave_types': leave_types,
        
        # إحصائيات الأقسام
        'departments_count': Department.objects.filter(is_active=True).count(),
        'total_departments': Department.objects.count(),
        
        # إحصائيات المسميات الوظيفية
        'job_titles_count': JobTitle.objects.filter(is_active=True).count(),
        'total_job_titles': JobTitle.objects.count(),
        
        # إحصائيات الورديات
        'shifts_count': Shift.objects.filter(is_active=True).count(),
        'total_shifts': Shift.objects.count(),
        
        # إحصائيات ماكينات البصمة
        'biometric_devices_count': BiometricDevice.objects.filter(is_active=True).count(),
        'total_biometric_devices': BiometricDevice.objects.count(),
        
        # إحصائيات أرصدة الإجازات
        'leave_balances_count': LeaveBalance.objects.count(),
        'employees_with_balance': LeaveBalance.objects.values('employee').distinct().count(),
        
        # إحصائيات قوالب مكونات الراتب
        'salary_templates_earnings': salary_templates_earnings,
        'salary_templates_deductions': salary_templates_deductions,
    }
    return render(request, 'hr/settings.html', context)


# ==================== ربط الموظفين بالمستخدمين ====================

@login_required
def employee_create_user(request, pk):
    """إنشاء حساب مستخدم لموظف"""
    from .services.user_employee_service import UserEmployeeService
    
    employee = get_object_or_404(Employee, pk=pk)
    
    if employee.user:
        messages.warning(request, 'الموظف مرتبط بمستخدم بالفعل')
        return redirect('hr:employee_detail', pk=pk)
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        send_email = request.POST.get('send_email') == 'on'
        
        try:
            user, created_password = UserEmployeeService.create_user_for_employee(
                employee=employee,
                username=username,
                password=password,
                send_email=send_email
            )
            
            if send_email:
                messages.success(request, f'تم إنشاء الحساب بنجاح وإرسال البيانات للبريد: {employee.work_email}')
            else:
                messages.success(request, f'تم إنشاء الحساب بنجاح - اسم المستخدم: {username}')
            
        except Exception as e:
            messages.error(request, f'خطأ: {str(e)}')
    
    return redirect('hr:employee_detail', pk=pk)


@login_required
def employee_link_user(request, pk):
    """ربط موظف بمستخدم موجود"""
    from .services.user_employee_service import UserEmployeeService
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    employee = get_object_or_404(Employee, pk=pk)
    
    if employee.user:
        messages.warning(request, 'الموظف مرتبط بمستخدم بالفعل')
        return redirect('hr:employee_detail', pk=pk)
    
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        
        try:
            user = User.objects.get(pk=user_id)
            UserEmployeeService.link_existing_user_to_employee(employee, user)
            messages.success(request, f'تم ربط الموظف بالمستخدم: {user.username}')
        except User.DoesNotExist:
            messages.error(request, 'المستخدم غير موجود')
        except Exception as e:
            messages.error(request, f'خطأ: {str(e)}')
    
    return redirect('hr:employee_detail', pk=pk)


@login_required
def employee_unlink_user(request, pk):
    """فك ربط موظف من مستخدم"""
    employee = get_object_or_404(Employee, pk=pk)
    
    if not employee.user:
        messages.warning(request, 'الموظف غير مرتبط بمستخدم')
        return redirect('hr:employee_detail', pk=pk)
    
    if request.method == 'POST':
        username = employee.user.username
        employee.user = None
        employee.save()
        messages.success(request, f'تم فك الربط من المستخدم: {username}')
    
    return redirect('hr:employee_detail', pk=pk)


# ==================== API للتحقق من التكرار ====================

@login_required
def check_employee_email(request):
    """التحقق من تكرار البريد الإلكتروني"""
    email = request.GET.get('email', '')
    employee_id = request.GET.get('employee_id', None)
    
    if not email:
        return JsonResponse({'available': True})
    
    # التحقق من وجود البريد
    query = Employee.objects.filter(work_email=email)
    if employee_id:
        query = query.exclude(pk=employee_id)
    
    exists = query.exists()
    
    return JsonResponse({
        'available': not exists,
        'message': 'هذا البريد الإلكتروني مستخدم بالفعل' if exists else 'البريد الإلكتروني متاح'
    })


@login_required
def check_employee_mobile(request):
    """التحقق من تكرار رقم الموبايل"""
    mobile = request.GET.get('mobile', '')
    employee_id = request.GET.get('employee_id', None)
    
    if not mobile:
        return JsonResponse({'available': True})
    
    # التحقق من وجود الرقم
    query = Employee.objects.filter(mobile_phone=mobile)
    if employee_id:
        query = query.exclude(pk=employee_id)
    
    exists = query.exists()
    
    return JsonResponse({
        'available': not exists,
        'message': 'رقم الموبايل مستخدم بالفعل' if exists else 'رقم الموبايل متاح'
    })


@login_required
def check_employee_national_id(request):
    """التحقق من تكرار الرقم القومي"""
    national_id = request.GET.get('national_id', '')
    employee_id = request.GET.get('employee_id', None)
    
    if not national_id:
        return JsonResponse({'available': True})
    
    # التحقق من وجود الرقم القومي
    query = Employee.objects.filter(national_id=national_id)
    if employee_id:
        query = query.exclude(pk=employee_id)
    
    exists = query.exists()
    
    return JsonResponse({
        'available': not exists,
        'message': 'هذا الرقم القومي مستخدم بالفعل' if exists else 'الرقم القومي متاح'
    })


# ==================== التقارير ====================

@login_required
def reports_home(request):
    """الصفحة الرئيسية للتقارير"""
    return render(request, 'hr/reports/home.html')


@login_required
def attendance_report(request):
    """تقرير الحضور"""
    return render(request, 'hr/reports/attendance.html')


@login_required
def leave_report(request):
    """تقرير الإجازات"""
    return render(request, 'hr/reports/leave.html')


@login_required
def payroll_report(request):
    """تقرير الرواتب"""
    return render(request, 'hr/reports/payroll.html')


@login_required
def employee_report(request):
    """تقرير الموظفين"""
    return render(request, 'hr/reports/employee.html')


# ==================== Salary Component Templates ====================

@login_required
def salary_component_templates_list(request):
    """قائمة قوالب مكونات الراتب"""
    from .models import SalaryComponentTemplate
    
    templates = SalaryComponentTemplate.objects.all().order_by('component_type', 'order', 'name')
    
    context = {
        'templates': templates,
        'earnings': templates.filter(component_type='earning'),
        'deductions': templates.filter(component_type='deduction'),
    }
    return render(request, 'hr/salary_component_templates/list.html', context)


@login_required
def salary_component_template_form(request, pk=None):
    """نموذج إضافة/تعديل قالب مكون الراتب"""
    from .models import SalaryComponentTemplate
    from .forms.salary_component_template_forms import SalaryComponentTemplateForm
    
    template = None
    if pk:
        template = get_object_or_404(SalaryComponentTemplate, pk=pk)
    
    if request.method == 'POST':
        form = SalaryComponentTemplateForm(request.POST, instance=template)
        if form.is_valid():
            template = form.save()
            messages.success(request, f'تم {"تعديل" if pk else "إضافة"} القالب بنجاح')
            return redirect('hr:salary_component_templates_list')
    else:
        form = SalaryComponentTemplateForm(instance=template)
    
    context = {
        'form': form,
        'template': template,
        'is_edit': pk is not None
    }
    return render(request, 'hr/salary_component_templates/form.html', context)


@login_required
def salary_component_template_delete(request, pk):
    """حذف قالب مكون الراتب"""
    from .models import SalaryComponentTemplate
    
    template = get_object_or_404(SalaryComponentTemplate, pk=pk)
    
    if request.method == 'POST':
        template_name = template.name
        template.delete()
        messages.success(request, f'تم حذف القالب "{template_name}" بنجاح')
        return redirect('hr:salary_component_templates_list')
    
    # تجهيز البيانات للمودال الموحد
    item_fields = [
        {'label': 'الاسم', 'value': template.name},
        {'label': 'النوع', 'value': template.get_component_type_display()},
    ]
    
    if template.formula:
        item_fields.append({'label': 'الصيغة', 'value': template.formula})
    if template.default_amount:
        item_fields.append({'label': 'المبلغ', 'value': template.default_amount})
    
    context = {
        'template': template,
        'item_fields': item_fields,
    }
    return render(request, 'hr/salary_component_templates/delete_modal.html', context)
