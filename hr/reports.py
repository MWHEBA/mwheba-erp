"""
تقارير وحدة الموارد البشرية
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from datetime import datetime, date
from decimal import Decimal
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill

from .models import Employee, Attendance, Leave, Payroll


@login_required
def reports_home(request):
    """الصفحة الرئيسية للتقارير"""
    return render(request, 'hr/reports/home.html')


@login_required
def attendance_report(request):
    """تقرير الحضور الشهري"""
    month_str = request.GET.get('month', date.today().strftime('%Y-%m'))
    department_id = request.GET.get('department')
    
    try:
        year, month = map(int, month_str.split('-'))
        month_date = date(year, month, 1)
    except:
        month_date = date.today().replace(day=1)
    
    # جلب الحضور بالفترة الفعلية للدورة
    from hr.utils.payroll_helpers import get_payroll_period
    period_start, period_end, _ = get_payroll_period(month_date)
    attendances = Attendance.objects.filter(
        date__gte=period_start,
        date__lte=period_end,
    ).select_related('employee', 'shift')
    
    if department_id:
        attendances = attendances.filter(employee__department_id=department_id)
    
    # حساب الإحصائيات
    stats = {
        'total_days': attendances.count(),
        'present': attendances.filter(status='present').count(),
        'late': attendances.filter(status='late').count(),
        'absent': attendances.filter(status='absent').count(),
        'total_work_hours': sum(float(a.work_hours) for a in attendances),
        'total_overtime': sum(float(a.overtime_hours) for a in attendances),
    }
    
    # تصدير Excel
    if request.GET.get('export') == 'excel':
        return export_attendance_excel(attendances, month_date, stats)
    
    from .models import Department
    departments = Department.objects.filter(is_active=True).order_by('name_ar')

    context = {
        'attendances': attendances,
        'stats': stats,
        'month': month_date,
        'month_str': month_str,
        'departments': departments,
        'selected_department': department_id,
        'page_title': 'تقرير سجلات الحضور والانصراف',
    }
    
    return render(request, 'hr/reports/attendance.html', context)


@login_required
def leave_report(request):
    """تقرير الإجازات"""
    year = request.GET.get('year', date.today().year)
    department_id = request.GET.get('department')
    leave_type_id = request.GET.get('leave_type')
    
    # جلب الإجازات
    leaves = Leave.objects.filter(
        start_date__year=year
    ).select_related('employee', 'leave_type', 'approved_by')
    
    if department_id:
        leaves = leaves.filter(employee__department_id=department_id)
    
    if leave_type_id:
        leaves = leaves.filter(leave_type_id=leave_type_id)
    
    # حساب الإحصائيات
    stats = {
        'total_leaves': leaves.count(),
        'approved': leaves.filter(status='approved').count(),
        'pending': leaves.filter(status='pending').count(),
        'rejected': leaves.filter(status='rejected').count(),
        'total_days': sum(l.days_count for l in leaves),
    }
    
    context = {
        'leaves': leaves,
        'stats': stats,
        'year': year,
    }
    
    # تصدير Excel
    if request.GET.get('export') == 'excel':
        return export_leave_excel(leaves, year, stats)
    
    return render(request, 'hr/reports/leave.html', context)


@login_required
def payroll_report(request):
    """تقرير الرواتب الشهري"""
    month_str = request.GET.get('month', date.today().strftime('%Y-%m'))
    department_id = request.GET.get('department')
    
    try:
        year, month = map(int, month_str.split('-'))
        month_date = date(year, month, 1)
    except:
        month_date = date.today().replace(day=1)
    
    # جلب قسائم الرواتب
    payrolls = Payroll.objects.filter(
        month=month_date
    ).select_related('employee', 'contract', 'processed_by')
    
    if department_id:
        payrolls = payrolls.filter(employee__department_id=department_id)

    # إضافة correct values لكل payroll — استخدام property من الـ model
    payrolls_list = list(payrolls)
    for p in payrolls_list:
        p._correct_gross = p.correct_gross_salary
        p._correct_net = p.correct_net_salary

    from decimal import Decimal as _DecR
    stats = {
        'total_employees': payrolls.count(),
        'total_gross': sum(p._correct_gross for p in payrolls_list),
        'total_deductions': sum(p.total_deductions or _DecR('0') for p in payrolls_list),
        'total_net': sum(p._correct_net for p in payrolls_list),
        'approved': payrolls.filter(status='approved').count(),
        'pending': payrolls.filter(status='calculated').count(),
    }

    context = {
        'payrolls': payrolls_list,
        'stats': stats,
        'month': month_date,
        'month_str': month_str,
    }
    
    # تصدير Excel
    if request.GET.get('export') == 'excel':
        return export_payroll_excel(payrolls, month_date, stats)
    
    return render(request, 'hr/reports/payroll.html', context)


@login_required
def employee_report(request):
    """تقرير الموظفين"""
    department_id = request.GET.get('department')
    status = request.GET.get('status', 'active')
    
    # جلب الموظفين
    employees = Employee.objects.filter(
        status=status
    ).select_related('department', 'job_title')
    
    if department_id:
        employees = employees.filter(department_id=department_id)
    
    # حساب الإحصائيات
    stats = {
        'total_employees': employees.count(),
        'by_gender': {
            'male': employees.filter(gender='male').count(),
            'female': employees.filter(gender='female').count(),
        },
        'by_employment_type': {
            'full_time': employees.filter(employment_type='full_time').count(),
            'part_time': employees.filter(employment_type='part_time').count(),
        },
    }
    
    context = {
        'employees': employees,
        'stats': stats,
        'status': status,
    }
    
    # تصدير Excel
    if request.GET.get('export') == 'excel':
        return export_employee_excel(employees, stats)
    
    return render(request, 'hr/reports/employee.html', context)


# دوال تصدير Excel

def export_attendance_excel(attendances, month, stats=None):
    """تصدير تقرير الحضور التفصيلي إلى Excel شاملاً المقرات والمصادر وساعات الإضافي"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "سجل الحضور اليومي"
    ws.views.sheetView[0].rightToLeft = True
    
    # Title
    ws['A1'] = f"تقرير سجلات الحضور والانصراف - {month.strftime('%Y-%m')}"
    ws['A1'].font = Font(size=14, bold=True)
    ws.merge_cells('A1:N1')
    
    # Header styling
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    center_align = Alignment(horizontal="center", vertical="center")
    
    headers = [
        'كود الموظف',
        'اسم الموظف',
        'القسم',
        'التاريخ',
        'الوردية',
        'المقر الجغرافي',
        'المصدر',
        'الحضور',
        'الانصراف',
        'ساعات العمل',
        'ساعات الإضافي',
        'التأخير (دقيقة)',
        'الحالة',
        'ملاحظات'
    ]
    
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
    
    for row_idx, att in enumerate(attendances, 4):
        loc_name = att.work_location.name_ar if getattr(att, 'work_location', None) else 'المقر الرئيسي'
        source_display = 'ماكينة'
        first_log = att.biometric_logs.first() if hasattr(att, 'biometric_logs') else None
        if first_log:
            source_display = first_log.get_source_display()
            if first_log.is_offline_synced:
                source_display += ' (أوفلاين)'
            if first_log.matched_location:
                loc_name = first_log.matched_location.name_ar
        elif getattr(att, 'is_manual_entry', False):
            source_display = 'يدوي'

        ws.cell(row=row_idx, column=1, value=att.employee.employee_number or '').alignment = center_align
        ws.cell(row=row_idx, column=2, value=att.employee.get_full_name_ar())
        ws.cell(row=row_idx, column=3, value=att.employee.department.name_ar if att.employee.department else '—')
        ws.cell(row=row_idx, column=4, value=att.date.strftime('%Y-%m-%d')).alignment = center_align
        ws.cell(row=row_idx, column=5, value=att.shift.name if att.shift else '—').alignment = center_align
        ws.cell(row=row_idx, column=6, value=loc_name).alignment = center_align
        ws.cell(row=row_idx, column=7, value=source_display).alignment = center_align
        
        if att.status in ['absent', 'on_leave']:
            ws.cell(row=row_idx, column=8, value='—').alignment = center_align
            ws.cell(row=row_idx, column=9, value='—').alignment = center_align
        else:
            ws.cell(row=row_idx, column=8, value=att.check_in.strftime('%H:%M') if att.check_in else '—').alignment = center_align
            ws.cell(row=row_idx, column=9, value=att.check_out.strftime('%H:%M') if att.check_out else '—').alignment = center_align
            
        ws.cell(row=row_idx, column=10, value=float(att.work_hours or 0)).alignment = center_align
        ws.cell(row=row_idx, column=11, value=float(att.overtime_hours or 0)).alignment = center_align
        ws.cell(row=row_idx, column=12, value=int(att.late_minutes or 0)).alignment = center_align
        ws.cell(row=row_idx, column=13, value=att.get_status_display()).alignment = center_align
        ws.cell(row=row_idx, column=14, value=att.notes or '')
    
    # Auto adjust column widths
    from openpyxl.utils import get_column_letter
    for col_idx in range(1, len(headers) + 1):
        col_letter = get_column_letter(col_idx)
        max_len = 0
        for row in range(3, len(attendances) + 4):
            val = ws.cell(row=row, column=col_idx).value
            if val is not None:
                max_len = max(max_len, len(str(val)))
        ws.column_dimensions[col_letter].width = max(max_len + 4, 13)
        
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="attendance_report_{month.strftime("%Y-%m")}.xlsx"'
    wb.save(response)
    return response


def export_attendance_summary_excel(summaries, month):
    """تصدير تقرير ملخصات الحضور الشهرية المعتمدة إلى Excel"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ملخص الحضور الشهري"
    ws.views.sheetView[0].rightToLeft = True
    
    # Title
    ws['A1'] = f"تقرير ملخص الحضور والعمل الإضافي والجزاءات - {month.strftime('%Y-%m')}"
    ws['A1'].font = Font(size=14, bold=True)
    ws.merge_cells('A1:Q1')
    
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    center_align = Alignment(horizontal="center", vertical="center")
    
    headers = [
        'كود الموظف',
        'اسم الموظف',
        'القسم',
        'أيام العمل',
        'الحضور',
        'الغياب',
        'نصف يوم',
        'ساعات العمل',
        'الإضافي المحسوب',
        'الإضافي المعتمد',
        'مبلغ الإضافي',
        'دقائق التأخير الصافية',
        'خصم التأخير',
        'خصم الغياب',
        'خصم الأذونات',
        'الحالة',
        'ملاحظات'
    ]
    
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        
    summaries_list = list(summaries)
    for row_idx, summary in enumerate(summaries_list, 4):
        ws.cell(row=row_idx, column=1, value=summary.employee.employee_number or '').alignment = center_align
        ws.cell(row=row_idx, column=2, value=summary.employee.get_full_name_ar())
        ws.cell(row=row_idx, column=3, value=summary.employee.department.name_ar if summary.employee.department else '—')
        ws.cell(row=row_idx, column=4, value=summary.total_working_days).alignment = center_align
        ws.cell(row=row_idx, column=5, value=summary.present_days).alignment = center_align
        ws.cell(row=row_idx, column=6, value=summary.absent_days).alignment = center_align
        ws.cell(row=row_idx, column=7, value=summary.half_days).alignment = center_align
        ws.cell(row=row_idx, column=8, value=float(summary.total_work_hours or 0)).alignment = center_align
        ws.cell(row=row_idx, column=9, value=float(summary.total_overtime_hours or 0)).alignment = center_align
        ws.cell(row=row_idx, column=10, value=float(summary.approved_overtime_hours) if summary.approved_overtime_hours is not None else float(summary.total_overtime_hours or 0)).alignment = center_align
        ws.cell(row=row_idx, column=11, value=float(summary.overtime_amount or 0)).alignment = center_align
        ws.cell(row=row_idx, column=12, value=int(summary.net_penalizable_minutes or 0)).alignment = center_align
        ws.cell(row=row_idx, column=13, value=float(summary.late_deduction_amount or 0)).alignment = center_align
        ws.cell(row=row_idx, column=14, value=float(summary.absence_deduction_amount or 0)).alignment = center_align
        ws.cell(row=row_idx, column=15, value=float(summary.extra_permissions_deduction_amount or 0)).alignment = center_align
        ws.cell(row=row_idx, column=16, value='معتمد' if summary.is_approved else 'قيد المراجعة').alignment = center_align
        ws.cell(row=row_idx, column=17, value=summary.overtime_override_reason or summary.notes or '')
        
    from openpyxl.utils import get_column_letter
    for col_idx in range(1, len(headers) + 1):
        col_letter = get_column_letter(col_idx)
        max_len = 0
        for row in range(3, len(summaries_list) + 4):
            val = ws.cell(row=row, column=col_idx).value
            if val is not None:
                max_len = max(max_len, len(str(val)))
        ws.column_dimensions[col_letter].width = max(max_len + 4, 13)
        
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="attendance_summary_{month.strftime("%Y-%m")}.xlsx"'
    wb.save(response)
    return response


def export_leave_excel(leaves, year, stats):
    """تصدير تقرير الإجازات إلى Excel"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "تقرير الإجازات"
    
    # العنوان
    ws['A1'] = f"تقرير الإجازات - {year}"
    ws['A1'].font = Font(size=16, bold=True)
    ws.merge_cells('A1:G1')
    
    # العناوين
    headers = ['الموظف', 'نوع الإجازة', 'من', 'إلى', 'عدد الأيام', 'الحالة', 'المعتمد']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
    
    # البيانات
    for row, leave in enumerate(leaves, 4):
        ws.cell(row=row, column=1, value=leave.employee.get_full_name_ar())
        ws.cell(row=row, column=2, value=leave.leave_type.name_ar)
        ws.cell(row=row, column=3, value=leave.start_date.strftime('%Y-%m-%d'))
        ws.cell(row=row, column=4, value=leave.end_date.strftime('%Y-%m-%d'))
        ws.cell(row=row, column=5, value=leave.days_count)
        ws.cell(row=row, column=6, value=leave.get_status_display())
        ws.cell(row=row, column=7, value=leave.approved_by.get_full_name() if leave.approved_by else '')
    
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="leave_report_{year}.xlsx"'
    wb.save(response)
    return response


def export_payroll_excel(payrolls, month, stats):
    """تصدير تقرير الرواتب إلى Excel"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "تقرير الرواتب"
    
    # العنوان
    ws['A1'] = f"تقرير الرواتب - {month.strftime('%Y-%m')}"
    ws['A1'].font = Font(size=16, bold=True)
    ws.merge_cells('A1:H1')
    
    # العناوين
    headers = ['الموظف', 'الأجر الأساسي', 'البدلات', 'الإضافات', 'الخصومات', 'الإجمالي', 'الصافي', 'الحالة']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
    
    # البيانات
    for row, payroll in enumerate(payrolls, 4):
        ws.cell(row=row, column=1, value=payroll.employee.get_full_name_ar())
        ws.cell(row=row, column=2, value=float(payroll.basic_salary))
        ws.cell(row=row, column=3, value=float(payroll.allowances))
        ws.cell(row=row, column=4, value=float(payroll.total_additions))
        ws.cell(row=row, column=5, value=float(payroll.total_deductions))
        ws.cell(row=row, column=6, value=float(payroll._correct_gross))
        ws.cell(row=row, column=7, value=float(payroll._correct_net))
        ws.cell(row=row, column=8, value=payroll.get_status_display())
    
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="payroll_report_{month.strftime("%Y-%m")}.xlsx"'
    wb.save(response)
    return response


def export_employee_excel(employees, stats):
    """تصدير تقرير الموظفين إلى Excel"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "تقرير الموظفين"
    
    # العنوان
    ws['A1'] = "تقرير الموظفين"
    ws['A1'].font = Font(size=16, bold=True)
    ws.merge_cells('A1:H1')
    
    # العناوين
    headers = ['رقم الموظف', 'الاسم', 'القسم', 'الوظيفة', 'تاريخ التعيين', 'نوع التوظيف', 'الحالة', 'البريد']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
    
    # البيانات
    for row, employee in enumerate(employees, 4):
        ws.cell(row=row, column=1, value=employee.employee_number)
        ws.cell(row=row, column=2, value=employee.get_full_name_ar())
        ws.cell(row=row, column=3, value=employee.department.name_ar)
        ws.cell(row=row, column=4, value=employee.job_title.title_ar)
        ws.cell(row=row, column=5, value=employee.hire_date.strftime('%Y-%m-%d'))
        ws.cell(row=row, column=6, value=employee.get_employment_type_display())
        ws.cell(row=row, column=7, value=employee.get_status_display())
        ws.cell(row=row, column=8, value=employee.work_email)
    
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="employee_report.xlsx"'
    wb.save(response)
    return response
