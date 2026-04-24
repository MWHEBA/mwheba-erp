"""
استيراد العقود بشكل جماعي من ملف Excel
"""
from .base_imports import *
from ..models import Contract, Employee, ContractSalaryComponent
from ..forms.contract_forms import ContractForm
from io import BytesIO
from decimal import Decimal, InvalidOperation
from django.db import transaction
import logging

logger = logging.getLogger(__name__)

# ---- Helpers ----

CONTRACT_TYPE_MAP = {
    'دائم': 'permanent',
    'مؤقت': 'temporary',
    'عقد محدد المدة': 'contract',
    'تدريب': 'internship',
    'دوام جزئي': 'part_time',
}

INCREASE_TYPE_MAP = {
    'نسبة': 'percentage',
    'نسبة مئوية': 'percentage',
    'ثابت': 'fixed',
    'قيمة ثابتة': 'fixed',
    'مبلغ': 'fixed',
}

BOOL_MAP = {
    'نعم': True, 'yes': True, '1': True, 'true': True,
    'لا': False, 'no': False, '0': False, 'false': False,
}


def _parse_bool(val):
    if val is None:
        return False
    return BOOL_MAP.get(str(val).strip().lower(), False)


def _parse_decimal(val):
    if val is None or str(val).strip() == '':
        return None
    try:
        return Decimal(str(val).strip().replace(',', ''))
    except InvalidOperation:
        return None


def _parse_date(val):
    if val is None or str(val).strip() == '':
        return None
    if hasattr(val, 'date'):
        return val.date()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            from datetime import datetime as dt
            return dt.strptime(str(val).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _cell(ws, row, col):
    """قراءة قيمة خلية بأمان"""
    val = ws.cell(row=row, column=col).value
    if val is None:
        return ''
    return str(val).strip()


def _build_header_map(ws):
    """بناء خريطة اسم العمود -> رقم العمود من الصف الأول"""
    mapping = {}
    for col in range(1, ws.max_column + 1):
        header = ws.cell(row=1, column=col).value
        if header:
            mapping[str(header).strip()] = col
    return mapping


def _get(hmap, row, ws, *keys):
    """جلب قيمة خلية بأي من الأسماء المحتملة"""
    for key in keys:
        if key in hmap:
            val = ws.cell(row=row, column=hmap[key]).value
            return val
    return None


# ---- Template Download ----

def contract_import_template(request):
    """تحميل قالب Excel للاستيراد"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'استيراد العقود'

    headers = [
        'رقم الموظف *',
        'نوع العقد *',
        'تاريخ البداية *',
        'تاريخ النهاية',
        'تجديد تلقائي',
        'فترة التجربة (بالأشهر)',
        'نوع الزيادة السنوية',
        'قيمة الزيادة السنوية',
        'مسجل التأمينات',
        'الرقم التأميني',
        'الأجر التأميني',
        'الأجر الأساسي *',
        'حصة الموظف في الاستقطاعات',
    ]

    header_fill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF', size=11)

    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = 22

    ws.row_dimensions[1].height = 35

    # صف مثال
    example = [
        'EMP001',
        'عقد محدد المدة',
        '2025-01-01',
        '2026-01-01',
        'نعم',
        '3',
        'نسبة',
        '10',
        'نعم',
        '12345678',
        '3000',
        '5000',
        '11',
    ]
    for col_idx, val in enumerate(example, start=1):
        cell = ws.cell(row=2, column=col_idx, value=val)
        cell.alignment = Alignment(horizontal='center')

    # ورقة مساعدة
    ws2 = wb.create_sheet('قيم مقبولة')
    ws2.column_dimensions['A'].width = 30
    ws2.column_dimensions['B'].width = 40

    notes = [
        ('نوع العقد', 'دائم / مؤقت / عقد محدد المدة / تدريب / دوام جزئي'),
        ('تجديد تلقائي', 'نعم / لا'),
        ('فترة التجربة (بالأشهر)', 'رقم (مثال: 3) - الافتراضي 3 أشهر'),
        ('نوع الزيادة السنوية', 'نسبة / ثابت  (اتركه فارغاً إذا لا توجد زيادة)'),
        ('قيمة الزيادة السنوية', 'رقم (مثال: 10 للنسبة أو 500 للمبلغ الثابت)'),
        ('مسجل التأمينات', 'نعم / لا'),
        ('حصة الموظف في الاستقطاعات', 'رقم (نسبة مئوية مثال: 11)'),
        ('تاريخ البداية / النهاية', 'YYYY-MM-DD أو DD/MM/YYYY'),
    ]
    ws2.cell(row=1, column=1, value='الحقل').font = Font(bold=True)
    ws2.cell(row=1, column=2, value='القيم المقبولة').font = Font(bold=True)
    for i, (field, vals) in enumerate(notes, start=2):
        ws2.cell(row=i, column=1, value=field)
        ws2.cell(row=i, column=2, value=vals)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="contract_import_template.xlsx"'
    return response


# ---- Main Import View ----

@login_required
def contract_import(request):
    """استيراد عقود جماعية من Excel"""
    if request.method == 'POST':
        import_file = request.FILES.get('import_file')
        if not import_file:
            messages.error(request, 'الرجاء اختيار ملف Excel للاستيراد')
            return redirect('hr:contract_import')

        ext = import_file.name.rsplit('.', 1)[-1].lower()
        if ext not in ('xlsx', 'xls'):
            messages.error(request, 'نوع الملف غير مدعوم - استخدم ملف Excel (.xlsx أو .xls)')
            return redirect('hr:contract_import')

        result = _import_contracts_from_excel(import_file, request.user)

        if result['success']:
            msg = f'تم إنشاء {result["created"]} عقد بنجاح'
            if result['skipped']:
                msg += f' - تم تخطي {result["skipped"]} صف'
            messages.success(request, msg)
            if result['errors']:
                messages.warning(request, 'تفاصيل الصفوف المتخطاة:<br>' + '<br>'.join(result['errors'][:15]))
        else:
            messages.error(request, f'حدث خطأ أثناء الاستيراد: {result["error"]}')

        return redirect('hr:contract_list')

    # GET - عرض صفحة الاستيراد
    context = {
        'title': 'استيراد عقود جماعية',
        'subtitle': 'رفع ملف Excel لإنشاء عقود متعددة دفعة واحدة',
        'page_icon': 'fas fa-file-import',
        'header_buttons': [
            {'url': reverse('hr:contract_list'), 'icon': 'fa-arrow-right', 'text': 'رجوع للعقود', 'class': 'btn-secondary'},
            {'url': reverse('hr:contract_import_template'), 'icon': 'fa-download', 'text': 'تحميل القالب', 'class': 'btn-outline-primary'},
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': '/', 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': '/hr/', 'icon': 'fas fa-users'},
            {'title': 'العقود', 'url': reverse('hr:contract_list'), 'icon': 'fas fa-file-contract'},
            {'title': 'استيراد جماعي', 'active': True},
        ],
    }
    return render(request, 'hr/contract/import.html', context)


# ---- Core Import Logic ----

def _import_contracts_from_excel(excel_file, user):
    """منطق الاستيراد الفعلي من Excel"""
    try:
        wb = openpyxl.load_workbook(excel_file, data_only=True)
        ws = wb.active
        hmap = _build_header_map(ws)

        created_count = 0
        skipped_count = 0
        error_details = []

        for row in range(2, ws.max_row + 1):
            # تخطي الصفوف الفارغة
            if all(ws.cell(row=row, column=c).value is None for c in range(1, ws.max_column + 1)):
                continue

            row_errors = []

            # --- رقم الموظف (مطلوب) ---
            emp_number = _get(hmap, row, ws, 'رقم الموظف *', 'رقم الموظف')
            if not emp_number:
                skipped_count += 1
                error_details.append(f'الصف {row}: رقم الموظف مفقود')
                continue

            emp_number = str(emp_number).strip()
            try:
                employee = Employee.objects.get(employee_number=emp_number)
            except Employee.DoesNotExist:
                skipped_count += 1
                error_details.append(f'الصف {row}: الموظف رقم "{emp_number}" غير موجود في النظام')
                continue

            # --- نوع العقد (مطلوب) ---
            contract_type_raw = _get(hmap, row, ws, 'نوع العقد *', 'نوع العقد') or ''
            contract_type = CONTRACT_TYPE_MAP.get(str(contract_type_raw).strip(), '')
            if not contract_type:
                skipped_count += 1
                error_details.append(f'الصف {row} ({emp_number}): نوع العقد "{contract_type_raw}" غير معروف')
                continue

            # --- تاريخ البداية (مطلوب) ---
            start_date = _parse_date(_get(hmap, row, ws, 'تاريخ البداية *', 'تاريخ البداية'))
            if not start_date:
                skipped_count += 1
                error_details.append(f'الصف {row} ({emp_number}): تاريخ البداية مفقود أو غير صحيح')
                continue

            # --- الأجر الأساسي (مطلوب) ---
            basic_salary = _parse_decimal(_get(hmap, row, ws, 'الأجر الأساسي *', 'الأجر الأساسي'))
            if basic_salary is None or basic_salary <= 0:
                skipped_count += 1
                error_details.append(f'الصف {row} ({emp_number}): الأجر الأساسي مفقود أو غير صحيح')
                continue

            # --- الحقول الاختيارية ---
            end_date = _parse_date(_get(hmap, row, ws, 'تاريخ النهاية'))
            auto_renew = _parse_bool(_get(hmap, row, ws, 'تجديد تلقائي', 'تجديد العقد'))
            probation_period_months = _parse_decimal(_get(hmap, row, ws, 'فترة التجربة', 'فترة التجربة (بالأشهر)'))
            probation_period_months = int(probation_period_months) if probation_period_months else 3

            # الزيادة السنوية
            increase_type_raw = _get(hmap, row, ws, 'نوع الزيادة السنوية') or ''
            increase_type = INCREASE_TYPE_MAP.get(str(increase_type_raw).strip(), '')
            increase_value = _parse_decimal(_get(hmap, row, ws, 'قيمة الزيادة السنوية'))
            has_annual_increase = bool(increase_type and increase_value)

            annual_increase_percentage = None
            annual_increase_amount = None
            if has_annual_increase:
                if increase_type == 'percentage':
                    annual_increase_percentage = increase_value
                else:
                    annual_increase_amount = increase_value

            # التأمينات
            is_insured = _parse_bool(_get(hmap, row, ws, 'مسجل التأمينات', 'مسجل التأمينات الاجتماعية'))
            insurance_number = _get(hmap, row, ws, 'الرقم التأميني') or ''
            insurance_salary = _parse_decimal(_get(hmap, row, ws, 'الأجر التأميني'))

            # حصة الموظف في الاستقطاعات
            employee_deduction_share = _parse_decimal(
                _get(hmap, row, ws, 'حصة الموظف في الاستقطاعات', 'حصة الموظف')
            )

            # --- إنشاء العقد ---
            try:
                with transaction.atomic():
                    contract_number = ContractForm.generate_contract_number()

                    contract = Contract(
                        contract_number=contract_number,
                        employee=employee,
                        contract_type=contract_type,
                        job_title=employee.job_title,
                        department=employee.department,
                        start_date=start_date,
                        end_date=end_date,
                        basic_salary=basic_salary,
                        probation_period_months=probation_period_months,
                        auto_renew=auto_renew,
                        has_annual_increase=has_annual_increase,
                        increase_type=increase_type or 'fixed',
                        annual_increase_percentage=annual_increase_percentage,
                        annual_increase_amount=annual_increase_amount,
                        is_social_insurance_enrolled=is_insured,
                        social_insurance_number=str(insurance_number).strip() if insurance_number else '',
                        insurance_salary=insurance_salary,
                        status='draft',
                        created_by=user,
                    )
                    # منع الـ signal من تحويل المسودة لنشطة تلقائياً
                    contract._keep_draft = True
                    contract.save()

                    # بند الأجر الأساسي
                    ContractSalaryComponent.objects.create(
                        contract=contract,
                        component_type='earning',
                        code='BASIC_SALARY',
                        name='الأجر الأساسي',
                        calculation_method='fixed',
                        amount=basic_salary,
                        is_basic=True,
                        is_taxable=True,
                        is_fixed=True,
                        affects_overtime=True,
                        order=0,
                        show_in_payslip=True,
                        notes='تم إضافته تلقائياً من الاستيراد الجماعي',
                    )

                    # بند الأجر التأميني (INSURABLE_SALARY) - مرجعي للـ payroll والقائمة
                    # نفس ما يحدث في الإضافة اليدوية عبر بنود الراتب
                    if is_insured and insurance_salary and insurance_salary > 0:
                        ContractSalaryComponent.objects.create(
                            contract=contract,
                            component_type='earning',
                            code='INSURABLE_SALARY',
                            name='الأجر التأميني',
                            calculation_method='fixed',
                            amount=insurance_salary,
                            is_basic=False,
                            is_taxable=False,
                            is_fixed=True,
                            affects_overtime=False,
                            order=1,
                            show_in_payslip=False,
                            notes='تم إضافته تلقائياً من الاستيراد الجماعي',
                        )

                    # بند حصة الموظف في الاستقطاعات (إذا وُجدت)
                    # يُحسب المبلغ الفعلي = نسبة% × الأجر التأميني ويُحفظ كـ fixed
                    if employee_deduction_share and employee_deduction_share > 0:
                        base_for_insurance = insurance_salary if (is_insured and insurance_salary and insurance_salary > 0) else basic_salary
                        insurance_deduction_amount = (base_for_insurance * employee_deduction_share / Decimal('100')).quantize(Decimal('1'))
                        ContractSalaryComponent.objects.create(
                            contract=contract,
                            component_type='deduction',
                            code='EMP_INSURANCE_SHARE',
                            name='حصة الموظف في التأمينات',
                            calculation_method='fixed',
                            percentage=employee_deduction_share,
                            amount=insurance_deduction_amount,
                            is_basic=False,
                            is_taxable=False,
                            is_fixed=True,
                            order=10,
                            show_in_payslip=True,
                            notes='تم إضافته تلقائياً من الاستيراد الجماعي',
                        )

                    created_count += 1

            except Exception as e:
                skipped_count += 1
                error_details.append(f'الصف {row} ({emp_number}): خطأ أثناء الحفظ - {str(e)}')
                logger.error(f'Contract import error row {row}: {e}')

        return {
            'success': True,
            'created': created_count,
            'skipped': skipped_count,
            'errors': error_details,
        }

    except Exception as e:
        logger.error(f'Contract import fatal error: {e}')
        return {'success': False, 'error': str(e)}
