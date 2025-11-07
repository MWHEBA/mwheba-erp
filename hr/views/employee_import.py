"""
Views استيراد وتصدير الموظفين
"""
from .base_imports import *
from ..models import Employee, Department, JobTitle
from ..forms.employee_forms import EmployeeForm

__all__ = [
    'export_employees',
    'employee_import',
    'import_employees_from_csv',
    'import_employees_from_excel',
]


def export_employees(employees, format_type):
    """تصدير قائمة الموظفين إلى CSV أو XLSX"""
    
    if format_type == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = f'attachment; filename="employees_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        response.write('\ufeff')  # BOM for Excel UTF-8 support
        
        writer = csv.writer(response)
        # كتابة الهيدر
        writer.writerow([
            'رقم الموظف',
            'الاسم الأول',
            'اسم العائلة',
            'الرقم القومي',
            'تاريخ الميلاد',
            'الجنس',
            'الحالة الاجتماعية',
            'القسم',
            'المسمى الوظيفي',
            'تاريخ التعيين',
            'الحالة',
            'البريد الإلكتروني',
            'رقم الهاتف',
            'العنوان',
            'المدينة',
        ])
        
        # كتابة البيانات
        for emp in employees:
            status_map = {
                'active': 'نشط',
                'on_leave': 'في إجازة',
                'suspended': 'موقوف',
                'terminated': 'منتهي الخدمة',
            }
            gender_map = {'male': 'ذكر', 'female': 'أنثى'}
            marital_map = {'single': 'أعزب', 'married': 'متزوج', 'divorced': 'مطلق', 'widowed': 'أرمل'}
            
            writer.writerow([
                emp.employee_number or '',
                emp.first_name_ar or '',
                emp.last_name_ar or '',
                emp.national_id or '',
                emp.birth_date.strftime('%Y-%m-%d') if emp.birth_date else '',
                gender_map.get(emp.gender, emp.gender) if emp.gender else '',
                marital_map.get(emp.marital_status, emp.marital_status) if emp.marital_status else '',
                emp.department.name_ar if emp.department else '',
                emp.job_title.title_ar if emp.job_title else '',
                emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
                status_map.get(emp.status, emp.status),
                emp.work_email or '',
                emp.mobile_phone or '',
                emp.address or '',
                emp.city or '',
            ])
        
        return response
    
    elif format_type == 'xlsx':
        # إنشاء ملف Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'الموظفين'
        
        # تنسيق الرؤوس
        header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
        header_font = Font(bold=True, color='FFFFFF', size=12)
        header_alignment = Alignment(horizontal='center', vertical='center')
        
        # كتابة الرؤوس
        headers = [
            'رقم الموظف',
            'الاسم الأول',
            'اسم العائلة',
            'الرقم القومي',
            'تاريخ الميلاد',
            'الجنس',
            'الحالة الاجتماعية',
            'القسم',
            'المسمى الوظيفي',
            'تاريخ التعيين',
            'الحالة',
            'البريد الإلكتروني',
            'رقم الهاتف',
            'العنوان',
            'المدينة',
        ]
        
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_alignment
        
        # كتابة البيانات
        status_map = {
            'active': 'نشط',
            'on_leave': 'في إجازة',
            'suspended': 'موقوف',
            'terminated': 'منتهي الخدمة',
        }
        
        gender_map = {'male': 'ذكر', 'female': 'أنثى'}
        marital_map = {'single': 'أعزب', 'married': 'متزوج', 'divorced': 'مطلق', 'widowed': 'أرمل'}
        
        for row_num, emp in enumerate(employees, 2):
            ws.cell(row=row_num, column=1, value=emp.employee_number or '')
            ws.cell(row=row_num, column=2, value=emp.first_name_ar or '')
            ws.cell(row=row_num, column=3, value=emp.last_name_ar or '')
            ws.cell(row=row_num, column=4, value=emp.national_id or '')
            ws.cell(row=row_num, column=5, value=emp.birth_date.strftime('%Y-%m-%d') if emp.birth_date else '')
            ws.cell(row=row_num, column=6, value=gender_map.get(emp.gender, emp.gender) if emp.gender else '')
            ws.cell(row=row_num, column=7, value=marital_map.get(emp.marital_status, emp.marital_status) if emp.marital_status else '')
            ws.cell(row=row_num, column=8, value=emp.department.name_ar if emp.department else '')
            ws.cell(row=row_num, column=9, value=emp.job_title.title_ar if emp.job_title else '')
            ws.cell(row=row_num, column=10, value=emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '')
            ws.cell(row=row_num, column=11, value=status_map.get(emp.status, emp.status))
            ws.cell(row=row_num, column=12, value=emp.work_email or '')
            ws.cell(row=row_num, column=13, value=emp.mobile_phone or '')
            ws.cell(row=row_num, column=14, value=emp.address or '')
            ws.cell(row=row_num, column=15, value=emp.city or '')
            
            # تنسيق الخلايا
            for col in range(1, 16):
                cell = ws.cell(row=row_num, column=col)
                cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # ضبط عرض الأعمدة
        column_widths = [15, 20, 20, 18, 15, 12, 18, 20, 25, 15, 15, 30, 15, 30, 15]
        for col_num, width in enumerate(column_widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(col_num)].width = width
        
        # حفظ الملف
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="employees_{timezone.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'
        wb.save(response)
        
        return response


@login_required
def employee_import(request):
    """استيراد الموظفين من CSV أو Excel"""
    if request.method == 'POST':
        import_file = request.FILES.get('import_file')
        
        if not import_file:
            messages.error(request, 'الرجاء اختيار ملف للاستيراد')
            return redirect('hr:employee_list')
        
        file_extension = import_file.name.split('.')[-1].lower()
        
        try:
            if file_extension == 'csv':
                result = import_employees_from_csv(import_file, request.user)
            elif file_extension in ['xlsx', 'xls']:
                result = import_employees_from_excel(import_file, request.user)
            else:
                messages.error(request, 'نوع الملف غير مدعوم. الرجاء استخدام CSV أو Excel')
                return redirect('hr:employee_list')
            
            if result['success']:
                # رسالة النجاح الأساسية
                success_msg = f'تم استيراد {result["created"]} موظف جديد وتحديث {result["updated"]} موظف'
                
                # إضافة معلومات عن البيانات المتخطاة
                if result.get('skipped', 0) > 0:
                    success_msg += f' - تم تخطي {result["skipped"]} صف'
                
                messages.success(request, success_msg)
                
                # عرض تفاصيل الأخطاء إذا وجدت
                if result.get('errors'):
                    error_list = '<br>'.join(result['errors'])
                    messages.warning(
                        request,
                        f'تفاصيل البيانات المتخطاة:<br>{error_list}'
                    )
            else:
                messages.error(request, f'حدث خطأ: {result["error"]}')
                
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء الاستيراد: {str(e)}')
            logger.error(f'Import error: {str(e)}')
        
        return redirect('hr:employee_list')
    
    return redirect('hr:employee_list')


def import_employees_from_csv(csv_file, user):
    """استيراد الموظفين من ملف CSV"""
    import io
    
    try:
        # قراءة الملف
        decoded_file = csv_file.read().decode('utf-8-sig')
        io_string = io.StringIO(decoded_file)
        reader = csv.DictReader(io_string)
        
        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_details = []
        
        for row_num, row in enumerate(reader, start=2):  # start=2 لأن الصف 1 هو الهيدر
            employee_number = row.get('رقم الموظف', '').strip()
            
            if not employee_number:
                skipped_count += 1
                error_details.append(f"الصف {row_num}: رقم الموظف مفقود")
                continue
            
            # تحويل الحالة من العربية للإنجليزية
            status_map_reverse = {
                'نشط': 'active',
                'في إجازة': 'on_leave',
                'موقوف': 'suspended',
                'منتهي الخدمة': 'terminated',
            }
            status = status_map_reverse.get(row.get('الحالة', '').strip(), 'active')
            
            # البحث عن القسم
            department = None
            dept_name = row.get('القسم', '').strip()
            if dept_name:
                department = Department.objects.filter(name_ar=dept_name).first()
            
            # البحث عن المسمى الوظيفي
            job_title = None
            job_name = row.get('المسمى الوظيفي', '').strip()
            if job_name:
                job_title = JobTitle.objects.filter(title_ar=job_name).first()
            
            # تحويل تاريخ التعيين
            hire_date = None
            hire_date_str = row.get('تاريخ التعيين', '').strip()
            if hire_date_str:
                try:
                    hire_date = datetime.strptime(hire_date_str, '%Y-%m-%d').date()
                except:
                    pass
            
            # التحقق من الحقول المطلوبة
            if not row.get('الاسم الأول', '').strip() or not row.get('اسم العائلة', '').strip():
                skipped_count += 1
                error_details.append(f"الصف {row_num}: الاسم الأول أو اسم العائلة مفقود")
                continue
            
            # تحويل تاريخ الميلاد
            birth_date = None
            birth_date_str = row.get('تاريخ الميلاد', '').strip()
            if birth_date_str:
                try:
                    birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
                except:
                    pass
            
            # تحويل الجنس
            gender_map_reverse = {'ذكر': 'male', 'أنثى': 'female'}
            gender = gender_map_reverse.get(row.get('الجنس', '').strip(), '')
            
            # تحويل الحالة الاجتماعية
            marital_map_reverse = {'أعزب': 'single', 'متزوج': 'married', 'مطلق': 'divorced', 'أرمل': 'widowed'}
            marital_status = marital_map_reverse.get(row.get('الحالة الاجتماعية', '').strip(), '')
            
            # التحقق من وجود الموظف
            try:
                employee = Employee.objects.get(employee_number=employee_number)
                # تحديث الموظف الموجود
                employee.first_name_ar = row.get('الاسم الأول', '').strip()
                employee.last_name_ar = row.get('اسم العائلة', '').strip()
                employee.status = status
                
                # تحديث الرقم القومي فقط إذا كان مختلف
                new_national_id = row.get('الرقم القومي', '').strip()
                if new_national_id and new_national_id != employee.national_id:
                    # التحقق من عدم وجود الرقم القومي الجديد عند موظف آخر
                    if not Employee.objects.filter(national_id=new_national_id).exclude(id=employee.id).exists():
                        employee.national_id = new_national_id
                
                if birth_date:
                    employee.birth_date = birth_date
                if gender:
                    employee.gender = gender
                if marital_status:
                    employee.marital_status = marital_status
                if department:
                    employee.department = department
                if job_title:
                    employee.job_title = job_title
                if hire_date:
                    employee.hire_date = hire_date
                if row.get('البريد الإلكتروني', '').strip():
                    employee.work_email = row.get('البريد الإلكتروني', '').strip()
                if row.get('رقم الهاتف', '').strip():
                    employee.mobile_phone = row.get('رقم الهاتف', '').strip()
                if row.get('العنوان', '').strip():
                    employee.address = row.get('العنوان', '').strip()
                if row.get('المدينة', '').strip():
                    employee.city = row.get('المدينة', '').strip()
                
                employee.save()
                updated_count += 1
                
            except Employee.DoesNotExist:
                # إنشاء موظف جديد - التحقق من جميع الحقول المطلوبة
                national_id = row.get('الرقم القومي', '').strip()
                work_email = row.get('البريد الإلكتروني', '').strip()
                mobile_phone = row.get('رقم الهاتف', '').strip()
                address = row.get('العنوان', '').strip()
                city = row.get('المدينة', '').strip()
                
                # التحقق من جميع الحقول المطلوبة
                if not all([national_id, birth_date, gender, marital_status, 
                           department, job_title, work_email, mobile_phone, 
                           address, city]):
                    # تخطي إذا كانت أي من الحقول المطلوبة ناقصة
                    skipped_count += 1
                    missing_fields = []
                    if not national_id: missing_fields.append('الرقم القومي')
                    if not birth_date: missing_fields.append('تاريخ الميلاد')
                    if not gender: missing_fields.append('الجنس')
                    if not marital_status: missing_fields.append('الحالة الاجتماعية')
                    if not department: missing_fields.append('القسم')
                    if not job_title: missing_fields.append('المسمى الوظيفي')
                    if not work_email: missing_fields.append('البريد الإلكتروني')
                    if not mobile_phone: missing_fields.append('رقم الهاتف')
                    if not address: missing_fields.append('العنوان')
                    if not city: missing_fields.append('المدينة')
                    error_details.append(f"الصف {row_num}: حقول مفقودة ({', '.join(missing_fields)})")
                    continue
                
                # التحقق من عدم وجود الرقم القومي مسبقاً
                if Employee.objects.filter(national_id=national_id).exists():
                    # تخطي إذا كان الرقم القومي موجود عند موظف آخر
                    skipped_count += 1
                    error_details.append(f"الصف {row_num}: الرقم القومي {national_id} موجود مسبقاً")
                    continue
                
                # إنشاء الموظف الجديد
                employee = Employee.objects.create(
                    employee_number=employee_number,
                    first_name_ar=row.get('الاسم الأول', '').strip(),
                    last_name_ar=row.get('اسم العائلة', '').strip(),
                    national_id=national_id,
                    birth_date=birth_date,
                    gender=gender,
                    marital_status=marital_status,
                    department=department,
                    job_title=job_title,
                    hire_date=hire_date or timezone.now().date(),
                    status=status,
                    work_email=work_email,
                    mobile_phone=mobile_phone,
                    address=address,
                    city=city,
                    created_by=user,
                )
                created_count += 1
        
        return {
            'success': True,
            'created': created_count,
            'updated': updated_count,
            'skipped': skipped_count,
            'errors': error_details[:10]  # أول 10 أخطاء فقط
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def import_employees_from_excel(excel_file, user):
    """استيراد الموظفين من ملف Excel"""
    try:
        wb = openpyxl.load_workbook(excel_file)
        ws = wb.active
        
        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_details = []
        
        # قراءة الرؤوس من الصف الأول
        headers = {}
        for col in range(1, ws.max_column + 1):
            header_value = ws.cell(row=1, column=col).value
            if header_value:
                headers[col] = header_value
        
        # قراءة البيانات
        for row_num in range(2, ws.max_row + 1):
            # جلب القيم حسب الرؤوس
            row_data = {}
            for col, header in headers.items():
                cell_value = ws.cell(row=row_num, column=col).value
                row_data[header] = str(cell_value).strip() if cell_value else ''
            
            employee_number = row_data.get('رقم الموظف', '').strip()
            
            if not employee_number:
                skipped_count += 1
                error_details.append(f"الصف {row_num}: رقم الموظف مفقود")
                continue
            
            # تحويل الحالة من العربية للإنجليزية
            status_map_reverse = {
                'نشط': 'active',
                'في إجازة': 'on_leave',
                'موقوف': 'suspended',
                'منتهي الخدمة': 'terminated',
            }
            status = status_map_reverse.get(row_data.get('الحالة', '').strip(), 'active')
            
            # البحث عن القسم
            department = None
            dept_name = row_data.get('القسم', '').strip()
            if dept_name:
                department = Department.objects.filter(name_ar=dept_name).first()
            
            # البحث عن المسمى الوظيفي
            job_title = None
            job_name = row_data.get('المسمى الوظيفي', '').strip()
            if job_name:
                job_title = JobTitle.objects.filter(title_ar=job_name).first()
            
            # تحويل تاريخ التعيين
            hire_date = None
            hire_date_str = row_data.get('تاريخ التعيين', '').strip()
            if hire_date_str:
                try:
                    hire_date = datetime.strptime(hire_date_str, '%Y-%m-%d').date()
                except:
                    pass
            
            # التحقق من الحقول المطلوبة
            if not row_data.get('الاسم الأول', '').strip() or not row_data.get('اسم العائلة', '').strip():
                skipped_count += 1
                error_details.append(f"الصف {row_num}: الاسم الأول أو اسم العائلة مفقود")
                continue
            
            # تحويل تاريخ الميلاد
            birth_date = None
            birth_date_str = row_data.get('تاريخ الميلاد', '').strip()
            if birth_date_str:
                try:
                    birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
                except:
                    pass
            
            # تحويل الجنس
            gender_map_reverse = {'ذكر': 'male', 'أنثى': 'female'}
            gender = gender_map_reverse.get(row_data.get('الجنس', '').strip(), '')
            
            # تحويل الحالة الاجتماعية
            marital_map_reverse = {'أعزب': 'single', 'متزوج': 'married', 'مطلق': 'divorced', 'أرمل': 'widowed'}
            marital_status = marital_map_reverse.get(row_data.get('الحالة الاجتماعية', '').strip(), '')
            
            # التحقق من وجود الموظف
            try:
                employee = Employee.objects.get(employee_number=employee_number)
                # تحديث الموظف الموجود
                employee.first_name_ar = row_data.get('الاسم الأول', '').strip()
                employee.last_name_ar = row_data.get('اسم العائلة', '').strip()
                employee.status = status
                
                # تحديث الرقم القومي فقط إذا كان مختلف
                new_national_id = row_data.get('الرقم القومي', '').strip()
                if new_national_id and new_national_id != employee.national_id:
                    # التحقق من عدم وجود الرقم القومي الجديد عند موظف آخر
                    if not Employee.objects.filter(national_id=new_national_id).exclude(id=employee.id).exists():
                        employee.national_id = new_national_id
                
                if birth_date:
                    employee.birth_date = birth_date
                if gender:
                    employee.gender = gender
                if marital_status:
                    employee.marital_status = marital_status
                if department:
                    employee.department = department
                if job_title:
                    employee.job_title = job_title
                if hire_date:
                    employee.hire_date = hire_date
                if row_data.get('البريد الإلكتروني', '').strip():
                    employee.work_email = row_data.get('البريد الإلكتروني', '').strip()
                if row_data.get('رقم الهاتف', '').strip():
                    employee.mobile_phone = row_data.get('رقم الهاتف', '').strip()
                if row_data.get('العنوان', '').strip():
                    employee.address = row_data.get('العنوان', '').strip()
                if row_data.get('المدينة', '').strip():
                    employee.city = row_data.get('المدينة', '').strip()
                
                employee.save()
                updated_count += 1
                
            except Employee.DoesNotExist:
                # إنشاء موظف جديد - التحقق من جميع الحقول المطلوبة
                national_id = row_data.get('الرقم القومي', '').strip()
                work_email = row_data.get('البريد الإلكتروني', '').strip()
                mobile_phone = row_data.get('رقم الهاتف', '').strip()
                address = row_data.get('العنوان', '').strip()
                city = row_data.get('المدينة', '').strip()
                
                # التحقق من جميع الحقول المطلوبة
                if not all([national_id, birth_date, gender, marital_status, 
                           department, job_title, work_email, mobile_phone, 
                           address, city]):
                    # تخطي إذا كانت أي من الحقول المطلوبة ناقصة
                    skipped_count += 1
                    missing_fields = []
                    if not national_id: missing_fields.append('الرقم القومي')
                    if not birth_date: missing_fields.append('تاريخ الميلاد')
                    if not gender: missing_fields.append('الجنس')
                    if not marital_status: missing_fields.append('الحالة الاجتماعية')
                    if not department: missing_fields.append('القسم')
                    if not job_title: missing_fields.append('المسمى الوظيفي')
                    if not work_email: missing_fields.append('البريد الإلكتروني')
                    if not mobile_phone: missing_fields.append('رقم الهاتف')
                    if not address: missing_fields.append('العنوان')
                    if not city: missing_fields.append('المدينة')
                    error_details.append(f"الصف {row_num}: حقول مفقودة ({', '.join(missing_fields)})")
                    continue
                
                # التحقق من عدم وجود الرقم القومي مسبقاً
                if Employee.objects.filter(national_id=national_id).exists():
                    # تخطي إذا كان الرقم القومي موجود عند موظف آخر
                    skipped_count += 1
                    error_details.append(f"الصف {row_num}: الرقم القومي {national_id} موجود مسبقاً")
                    continue
                
                # إنشاء الموظف الجديد
                employee = Employee.objects.create(
                    employee_number=employee_number,
                    first_name_ar=row_data.get('الاسم الأول', '').strip(),
                    last_name_ar=row_data.get('اسم العائلة', '').strip(),
                    national_id=national_id,
                    birth_date=birth_date,
                    gender=gender,
                    marital_status=marital_status,
                    department=department,
                    job_title=job_title,
                    hire_date=hire_date or timezone.now().date(),
                    status=status,
                    work_email=work_email,
                    mobile_phone=mobile_phone,
                    address=address,
                    city=city,
                    created_by=user,
                )
                created_count += 1
        
        return {
            'success': True,
            'created': created_count,
            'updated': updated_count,
            'skipped': skipped_count,
            'errors': error_details[:10]  # أول 10 أخطاء فقط
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
