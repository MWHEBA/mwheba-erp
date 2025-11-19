"""
خدمة معالجة الرواتب
"""
from django.db import transaction
from datetime import date
from decimal import Decimal
from ..models import Payroll, Employee, Advance
from .attendance_service import AttendanceService
from .advance_service import AdvanceService
import logging

logger = logging.getLogger(__name__)


class PayrollService:
    """خدمة معالجة الرواتب"""
    
    @staticmethod
    @transaction.atomic
    def calculate_payroll(employee, month, processed_by):
        """
        Calculate payroll for an employee for a specific month.
        
        This is the main entry point for payroll calculation. It delegates to
        the new system implementation (_calculate_payroll_new_system) which uses
        SalaryComponent and PayrollLine models for flexible salary calculations.
        
        Args:
            employee (Employee): The employee to calculate payroll for
            month (date): The payroll month as a date object
            processed_by (User): The user processing the payroll
        
        Returns:
            Payroll: The calculated payroll record with status 'calculated'
            
        Raises:
            ValueError: If employee has no active contract, no salary components,
                       or if payroll already exists for this month
            Exception: For unexpected errors during calculation
        """
        try:
            logger.info(f"بدء حساب راتب {employee.get_full_name_ar()} لشهر {month.strftime('%Y-%m')}")
            
            return PayrollService._calculate_payroll_new_system(employee, month, processed_by)
            
        except ValueError as e:
            logger.error(f"خطأ في البيانات عند حساب راتب {employee.get_full_name_ar()}: {str(e)}")
            raise
        except Exception as e:
            logger.exception(f"خطأ غير متوقع في حساب راتب {employee.get_full_name_ar()}: {str(e)}")
            raise
    
    @staticmethod
    @transaction.atomic
    def _calculate_payroll_new_system(employee, month, processed_by):
        """
        Calculate payroll using the new system (SalaryComponent + PayrollLine).
        
        This method handles the complete payroll calculation including:
        - Retrieving active contract and salary components
        - Calculating attendance and worked days
        - Creating payroll record with all components
        - Calculating advance deductions
        - Computing final totals
        
        Args:
            employee (Employee): The employee to calculate payroll for
            month (date): The payroll month as a date object
            processed_by (User): The user processing the payroll
            
        Returns:
            Payroll: The calculated payroll record with status 'calculated'
            
        Raises:
            ValueError: If employee has no active contract, no salary components,
                       or if payroll already exists for this month
            Exception: For unexpected errors during calculation
        """
        from ..models import PayrollLine
        from django.db.models import Q
        
        # 1. الحصول على العقد النشط
        contract = employee.contracts.filter(status='active').first()
        if not contract:
            logger.error(f"لا يوجد عقد نشط للموظف {employee.get_full_name_ar()}")
            raise ValueError('لا يوجد عقد نشط للموظف')
        
        # 2. الحصول على بنود الراتب النشطة (يدعم الموظفين المعينين في منتصف الشهر)
        from calendar import monthrange
        last_day = monthrange(month.year, month.month)[1]
        month_end_date = month.replace(day=last_day)
        
        components = employee.salary_components.filter(
            is_active=True,
            effective_from__lte=month_end_date  # بدأ قبل أو خلال الشهر
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=month)  # لم ينتهي أو ينتهي بعد بداية الشهر
        ).order_by('component_type', 'order')
        
        if not components.exists():
            logger.error(f"لا توجد بنود راتب نشطة للموظف {employee.get_full_name_ar()}")
            logger.error(f"   الفلتر: effective_from <= {month_end_date}, effective_to >= {month} أو NULL")
            # طباعة جميع البنود للتشخيص
            all_components = employee.salary_components.all()
            logger.error(f"   إجمالي البنود: {all_components.count()}")
            for comp in all_components:
                logger.error(f"      - {comp.name}: is_active={comp.is_active}, effective_from={comp.effective_from}, effective_to={comp.effective_to}")
            raise ValueError('لا توجد بنود راتب نشطة للموظف')
        
        # 3. حساب الراتب الأساسي من العقد أولاً مع تجبير الكسور
        if contract.basic_salary:
            basic_salary = Decimal(str(contract.basic_salary))
            # تجبير الراتب الأساسي لأقرب رقم صحيح
            from decimal import ROUND_HALF_UP
            basic_salary = basic_salary.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        else:
            # إذا لم يكن موجود في العقد، جربه من البند
            basic_component = components.filter(is_basic=True).first()
            basic_salary = basic_component.amount if basic_component else Decimal('0')
            # تجبير الراتب الأساسي لأقرب رقم صحيح
            from decimal import ROUND_HALF_UP
            basic_salary = basic_salary.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        
        # 4. حساب الحضور وأيام العمل الفعلية
        attendance_stats = AttendanceService.calculate_monthly_attendance(employee, month)
        
        # حساب أيام العمل الفعلية بناءً على تاريخ التعيين (استخدام last_day من أعلى)
        total_days_in_month = last_day
        
        # إذا كان الموظف معين في منتصف الشهر، احسب الأيام من تاريخ التعيين
        contract_start = contract.start_date
        if contract_start.year == month.year and contract_start.month == month.month:
            # معين في نفس الشهر - راتب جزئي
            days_from_start = total_days_in_month - contract_start.day + 1
            worked_days = days_from_start
            logger.info(f"راتب جزئي: الموظف {employee.get_full_name_ar()} معين من {contract_start} - أيام العمل: {worked_days}/{total_days_in_month}")
        else:
            # الشهر كامل - استخدام أيام الحضور الفعلية
            worked_days = attendance_stats.get('present_days', 0)
            if worked_days == 0:
                # التحقق من إعداد النظام لسلوك عدم وجود بيانات حضور
                from core.models import SystemSetting
                no_attendance_behavior = SystemSetting.get_setting('payroll_no_attendance_behavior', 'full_salary')
                
                if no_attendance_behavior == 'zero_salary':
                    logger.warning(f"⚠️ لا توجد بيانات حضور للموظف {employee.get_full_name_ar()} في شهر {month.strftime('%Y-%m')} - سيتم احتساب راتب صفر")
                    worked_days = 0
                elif no_attendance_behavior == 'error':
                    logger.error(f"❌ لا توجد بيانات حضور للموظف {employee.get_full_name_ar()} في شهر {month.strftime('%Y-%m')}")
                    raise ValueError(f'لا توجد بيانات حضور للموظف {employee.get_full_name_ar()} في شهر {month.strftime("%Y-%m")}')
                else:  # 'full_salary' (افتراضي)
                    logger.warning(f"⚠️ لا توجد بيانات حضور للموظف {employee.get_full_name_ar()} في شهر {month.strftime('%Y-%m')} - سيتم احتساب راتب كامل افتراضياً")
                    worked_days = total_days_in_month
        
        # 5. التحقق من وجود راتب سابق لنفس الموظف والشهر
        existing_payroll = Payroll.objects.filter(
            employee=employee,
            month=month
        ).first()
        
        if existing_payroll:
            logger.warning(f"يوجد راتب سابق للموظف {employee.get_full_name_ar()} لشهر {month.strftime('%Y-%m')}")
            raise ValueError(f'يوجد راتب سابق للموظف لشهر {month.strftime("%Y-%m")}')
        
        # 6. إنشاء قسيمة الراتب
        payroll = Payroll.objects.create(
            employee=employee,
            month=month,
            contract=contract,
            basic_salary=basic_salary,
            processed_by=processed_by,
            status='draft',
            # حقول قديمة للتوافق
            allowances=Decimal('0'),
            overtime_hours=Decimal(str(attendance_stats.get('total_overtime_hours', 0))),
            overtime_rate=Decimal('0'),
            overtime_amount=Decimal('0'),
            absence_days=attendance_stats.get('absent_days', 0),
            absence_deduction=Decimal('0'),
            social_insurance=Decimal('0'),
            tax=Decimal('0'),
            advance_deduction=Decimal('0'),
            gross_salary=basic_salary,
            total_additions=Decimal('0'),
            total_deductions=Decimal('0'),
            net_salary=basic_salary,
        )
        
        # 7. إنشاء PayrollLine لكل بند (ماعدا الراتب الأساسي لأنه محفوظ في basic_salary)
        context = {
            'basic_salary': basic_salary,
            'worked_days': worked_days,
            'month': month,
            'gross_salary': Decimal('0'),  # سيتم تحديثه
        }
        
        # استبعاد بند الراتب الأساسي لأنه محفوظ بالفعل في payroll.basic_salary
        non_basic_components = components.exclude(is_basic=True)
        
        for component in non_basic_components:
            amount = component.calculate_amount(context)
            
            # تقريب المبلغ لأقرب رقم صحيح
            from decimal import ROUND_HALF_UP
            amount = amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
                        
            PayrollLine.objects.create(
                payroll=payroll,
                salary_component=component,
                code=component.code,
                name=component.name,
                component_type=component.component_type,
                amount=amount,
                calculation_details={
                    'method': component.calculation_method,
                    'formula': component.formula if component.formula else None,
                    'percentage': str(component.percentage) if component.percentage else None,
                    'context': {
                        'basic_salary': str(basic_salary),
                        'worked_days': worked_days,
                    }
                },
                order=component.order
            )
        
        # 7. حساب خصم السلف وإضافته كـ PayrollLine
        advance_deduction = PayrollService._calculate_advance_deduction(employee, month)
        if advance_deduction > 0:
            # تقريب خصم السلف لأقرب رقم صحيح
            from decimal import ROUND_HALF_UP
            advance_deduction = advance_deduction.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            
            PayrollLine.objects.create(
                payroll=payroll,
                code='ADVANCE_DEDUCTION',
                name='خصم السلف',
                component_type='deduction',
                amount=advance_deduction,
                calculation_details={'source': 'advance_installments'},
                order=200
            )
        
        # 8. حساب الإجماليات من PayrollLine
        payroll.calculate_totals_from_lines()
        payroll.status = 'calculated'
        payroll.save()
        
        logger.info(
            f"تم حساب الراتب بنجاح (النظام الجديد) - الموظف: {employee.get_full_name_ar()}, "
            f"عدد البنود: {payroll.lines.count()}, "
            f"الإجمالي: {payroll.gross_salary}, الصافي: {payroll.net_salary}"
        )
        
        return payroll
    
    
    @staticmethod
    def _calculate_advance_deduction(employee, month):
        """
        Calculate advance payment deductions using AdvanceService.
        
        This method delegates to AdvanceService to calculate the total
        advance deduction amount for an employee in a specific month.
        
        Args:
            employee (Employee): The employee to calculate deductions for
            month (date): The payroll month as a date object
        
        Returns:
            Decimal: Total advance deduction amount for this month
            
        Raises:
            Exception: If AdvanceService encounters an error
        """
        # استخدام AdvanceService لحساب الخصم
        total_deduction, advances_list = AdvanceService.calculate_advance_deduction(
            employee=employee,
            payroll_month=month
        )
        
        logger.info(
            f"إجمالي خصم السلف للموظف {employee.get_full_name_ar()} في شهر {month}: "
            f"{total_deduction} ج.م من {len(advances_list)} سلفة"
        )
        
        return total_deduction
    
    @staticmethod
    @transaction.atomic
    def process_monthly_payroll(month, processed_by, employees=None):
        """
        Process payroll for multiple employees for a specific month.
        
        This method processes payroll for all active employees (or a specific
        list of employees) and returns detailed results for each employee.
        Employees who already have payroll for the month are automatically excluded.
        
        Args:
            month (date): The payroll month as a date object
            processed_by (User): The user processing the payroll
            employees (QuerySet, optional): Specific employees to process.
                                           If None, processes all active employees
                                           without existing payroll for the month.
        
        Returns:
            list: List of dictionaries containing:
                - employee: Employee instance
                - payroll: Payroll instance (if successful)
                - error: Error message (if failed)
                - success: Boolean indicating success/failure
                
        Raises:
            Exception: Critical errors are logged but not raised to allow
                      processing of remaining employees
        """
        logger.info(f"بدء معالجة رواتب شهر {month.strftime('%Y-%m')} بواسطة {processed_by.username}")
        
        # إذا لم يتم تمرير قائمة موظفين، جلب جميع الموظفين النشطين
        if employees is None:
            employees = Employee.objects.filter(status='active')
            # استبعاد الموظفين اللي عندهم راتب في نفس الشهر
            processed_employee_ids = Payroll.objects.filter(
                month=month
            ).values_list('employee_id', flat=True)
            employees = employees.exclude(id__in=processed_employee_ids)
        
        results = []
        success_count = 0
        fail_count = 0
        
        for employee in employees:
            try:
                payroll = PayrollService.calculate_payroll(employee, month, processed_by)
                results.append({
                    'employee': employee,
                    'payroll': payroll,
                    'success': True
                })
                success_count += 1
            except Exception as e:
                logger.error(f"فشل حساب راتب {employee.get_full_name_ar()}: {str(e)}")
                results.append({
                    'employee': employee,
                    'error': str(e),
                    'success': False
                })
                fail_count += 1
        
        logger.info(
            f"انتهت معالجة الرواتب - النجاح: {success_count}, الفشل: {fail_count}, "
            f"الإجمالي: {len(results)}"
        )
        
        return results
    
    @staticmethod
    @transaction.atomic
    def approve_payroll(payroll, approved_by):
        """
        Approve a calculated payroll record (without creating journal entry).
        
        This method changes the payroll status from 'calculated' to 'approved'
        and records the approver and approval timestamp. Journal entries are
        created separately during the payment process.
        
        Args:
            payroll (Payroll): The payroll record to approve
            approved_by (User): The user approving the payroll
        
        Returns:
            Payroll: The approved payroll record with updated status
            
        Raises:
            ValueError: If payroll status is not 'calculated'
        """
        from django.utils import timezone
        import logging
        
        logger = logging.getLogger(__name__)
        
        # التحقق من الحالة
        if payroll.status != 'calculated':
            raise ValueError('يجب أن تكون قسيمة الراتب محسوبة للاعتماد')
        
        # ✅ الاعتماد فقط - بدون قيد محاسبي
        payroll.status = 'approved'
        payroll.approved_by = approved_by
        payroll.approved_at = timezone.now()
        payroll.save()
        
        logger.info(f"تم اعتماد قسيمة راتب {payroll.employee.get_full_name_ar()} - {payroll.month}")
        
        return payroll
    
    @staticmethod
    def _create_journal_entry(payroll):
        """
        Create a journal entry for a payroll record (legacy method).
        
        Note: This is a legacy method. New implementations should use
        _create_individual_journal_entry instead.
        
        Args:
            payroll (Payroll): The payroll record to create entry for
        
        Returns:
            JournalEntry: The created journal entry
            
        Raises:
            ValueError: If required accounts are not found in chart of accounts
        """
        from financial.models import JournalEntry, JournalEntryLine, ChartOfAccounts
        
        # إنشاء القيد
        entry = JournalEntry.objects.create(
                debit=0,
                credit=payroll.net_salary
            )
        
        # إلى حـ/ التأمينات
        insurance_account = ChartOfAccounts.objects.filter(code='2103').first()
        if insurance_account:
            JournalEntryLine.objects.create(
                journal_entry=entry,
                account=insurance_account,
                debit=0,
                credit=payroll.social_insurance
            )
        
        # إلى حـ/ الضرائب
        tax_account = ChartOfAccounts.objects.filter(code='2104').first()
        if tax_account:
            JournalEntryLine.objects.create(
                journal_entry=entry,
                account=tax_account,
                debit=0,
                credit=payroll.tax
            )
        
        return entry
    
    @staticmethod
    def _create_individual_journal_entry(payroll, created_by):
        """
        Create an individual journal entry for a single payroll payment.
        
        This method creates a complete journal entry with:
        - Debit to salary expense accounts (basic + dynamic earnings)
        - Credit to payment account (net salary)
        - Credit to liability accounts (all deductions)
        
        Args:
            payroll (Payroll): The payroll record to create entry for
            created_by (User): The user creating the journal entry
        
        Returns:
            JournalEntry: The created journal entry
            
        Raises:
            ValueError: If salary expense account (52020) is not found
            Exception: If account lookup or entry creation fails
        """
        from financial.models import JournalEntry, JournalEntryLine, ChartOfAccounts
        from decimal import Decimal
        
        # إنشاء القيد
        entry = JournalEntry.objects.create(
            date=payroll.month,
            description=f'راتب {payroll.employee.get_full_name_ar()} - {payroll.month.strftime("%Y-%m")}',
            created_by=created_by
        )
        
        # من حـ/ مصروف الرواتب والأجور
        salary_expense_account = ChartOfAccounts.objects.filter(code='52020').first()
        if not salary_expense_account:
            raise ValueError('حساب الرواتب والأجور (52020) غير موجود في دليل الحسابات')
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=salary_expense_account,
            debit=payroll.basic_salary,
            credit=Decimal('0'),
            description=f'راتب أساسي - {payroll.employee.get_full_name_ar()}'
        )
        
        # معالجة المستحقات الديناميكية من PayrollLine
        PayrollService._process_dynamic_earnings(entry, payroll)
        
        # إلى حـ/ الصندوق/البنك (الصافي)
        if payroll.payment_account:
            JournalEntryLine.objects.create(
                journal_entry=entry,
                account=payroll.payment_account,
                debit=Decimal('0'),
                credit=payroll.net_salary,
                description=f'صافي راتب {payroll.employee.get_full_name_ar()}'
            )
        
        # معالجة جميع أنواع الخصومات بشكل منفصل
        PayrollService._process_payroll_deductions(entry, payroll)
        
        # معالجة الخصومات الديناميكية من PayrollLine
        PayrollService._process_dynamic_deductions(entry, payroll)
        
        return entry
    
    @staticmethod
    def _process_payroll_deductions(journal_entry, payroll):
        """
        Process all deduction types and route them to correct accounting accounts.
        
        This method handles various deduction types including:
        - Social insurance (account 2103)
        - Income tax (account 2104)
        - Absence deductions (account 21020)
        - Late deductions (account 21020)
        - Advance deductions (account 21030)
        - Other deductions (account 21020)
        
        Args:
            journal_entry (JournalEntry): The journal entry to add lines to
            payroll (Payroll): The payroll record containing deduction amounts
            
        Raises:
            Exception: If account lookup fails (logged but not raised)
        """
        from financial.models import JournalEntryLine, ChartOfAccounts
        from decimal import Decimal
        
        # خريطة الخصومات والحسابات المحاسبية المقابلة
        deduction_mapping = {
            'social_insurance': {
                'account_code': '2103',
                'account_name': 'التأمينات الاجتماعية',
                'description': 'تأمينات اجتماعية'
            },
            'tax': {
                'account_code': '2104', 
                'account_name': 'ضرائب الدخل',
                'description': 'ضرائب دخل'
            },
            'absence_deduction': {
                'account_code': '21020',
                'account_name': 'مستحقات الرواتب',
                'description': 'خصم غياب'
            },
            'late_deduction': {
                'account_code': '21020',
                'account_name': 'مستحقات الرواتب', 
                'description': 'خصم تأخير'
            },
            'advance_deduction': {
                'account_code': '21030',
                'account_name': 'سلف الموظفين',
                'description': 'خصم سلفة'
            },
            'other_deductions': {
                'account_code': '21020',
                'account_name': 'مستحقات الرواتب',
                'description': 'خصومات أخرى'
            }
        }
        
        # معالجة كل نوع خصم
        for field_name, mapping in deduction_mapping.items():
            deduction_amount = getattr(payroll, field_name, Decimal('0'))
            
            if deduction_amount and deduction_amount > 0:
                # البحث عن الحساب أو إنشاؤه
                account = PayrollService._get_safe_account_only(
                    mapping['account_code']
                )
                
                if account:
                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=account,
                        debit=Decimal('0'),
                        credit=deduction_amount,
                        description=f"{mapping['description']} - {payroll.employee.get_full_name_ar()}"
                    )
    
    @staticmethod
    def _get_safe_account_only(account_code):
        """
        Safely retrieve an existing account without creating new ones.
        
        This method implements a security measure by only returning accounts
        that are explicitly allowed for payroll operations and already exist
        in the chart of accounts. It will not create new accounts automatically.
        
        Args:
            account_code (str): The account code to look up
            
        Returns:
            ChartOfAccounts: The account if found and allowed, None otherwise
            
        Raises:
            None: Errors are logged but not raised
        """
        from financial.models import ChartOfAccounts
        from .secure_payroll_service import SecurePayrollService
        import logging
        
        logger = logging.getLogger(__name__)
        
        # التحقق من أن الحساب مسموح
        if account_code not in SecurePayrollService.ALLOWED_PAYROLL_ACCOUNTS:
            logger.error(f"❌ محاولة استخدام حساب غير مسموح: {account_code}")
            logger.info(f"الحسابات المسموحة: {list(SecurePayrollService.ALLOWED_PAYROLL_ACCOUNTS.keys())}")
            return None
        
        # البحث عن الحساب الموجود فقط
        account = ChartOfAccounts.objects.filter(code=account_code).first()
        
        if not account:
            logger.error(f"❌ الحساب المطلوب غير موجود في النظام: {account_code}")
            logger.warning("⚠️ النظام الآمن لا ينشئ حسابات جديدة تلقائياً")
            return None
        
        logger.info(f"✅ تم العثور على حساب آمن: {account_code} - {account.name}")
        return account
    
    @staticmethod
    def _process_dynamic_earnings(journal_entry, payroll):
        """
        Process dynamic earnings from PayrollLine based on SalaryComponent.
        
        This method creates journal entry lines for all earning-type components
        in the payroll, routing each to its appropriate expense account based
        on the component's configuration.
        
        Args:
            journal_entry (JournalEntry): The journal entry to add lines to
            payroll (Payroll): The payroll record containing earning lines
            
        Raises:
            Exception: If account determination fails (logged but not raised)
        """
        from financial.models import JournalEntryLine, ChartOfAccounts
        from decimal import Decimal
        import logging
        
        logger = logging.getLogger(__name__)
        
        # الحصول على جميع خطوط المستحقات في قسيمة الراتب
        earning_lines = payroll.lines.filter(component_type='earning')
        
        for line in earning_lines:
            if line.amount and line.amount > 0:
                # تحديد الحساب المحاسبي بناءً على SalaryComponent
                account = PayrollService._determine_account_for_component(line)
                
                if account:
                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=account,
                        debit=line.amount,
                        credit=Decimal('0'),
                        description=f"{line.name} - {payroll.employee.get_full_name_ar()}"
                    )
                    logger.info(f"تم إضافة مستحق ديناميكي: {line.name} - {line.amount} ج.م")
                else:
                    logger.warning(f"لم يتم العثور على حساب محاسبي للمستحق: {line.name}")

    @staticmethod
    def _process_dynamic_deductions(journal_entry, payroll):
        """
        Process dynamic deductions from PayrollLine based on SalaryComponent.
        
        This method creates journal entry lines for all deduction-type components
        in the payroll, routing each to its appropriate liability account based
        on the component's configuration.
        
        Args:
            journal_entry (JournalEntry): The journal entry to add lines to
            payroll (Payroll): The payroll record containing deduction lines
            
        Raises:
            Exception: If account determination fails (logged but not raised)
        """
        from financial.models import JournalEntryLine, ChartOfAccounts
        from decimal import Decimal
        import logging
        
        logger = logging.getLogger(__name__)
        
        # الحصول على جميع خطوط الخصومات في قسيمة الراتب
        deduction_lines = payroll.lines.filter(component_type='deduction')
        
        for line in deduction_lines:
            if line.amount and line.amount > 0:
                # تحديد الحساب المحاسبي بناءً على SalaryComponent
                account = PayrollService._determine_account_for_component(line)
                
                if account:
                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=account,
                        debit=Decimal('0'),
                        credit=line.amount,
                        description=f"{line.name} - {payroll.employee.get_full_name_ar()}"
                    )
                    logger.info(f"تم إضافة خصم ديناميكي: {line.name} - {line.amount} ج.م")
                else:
                    logger.warning(f"لم يتم العثور على حساب محاسبي للخصم: {line.name}")
    
    @staticmethod
    def _determine_account_for_component(payroll_line):
        """
        Determine the appropriate accounting account for a salary component.
        
        This method uses a three-tier approach to find the correct account:
        1. Check if SalaryComponent has an explicit account_code
        2. Use smart pattern matching on component code
        3. Fall back to default payroll liability account (21020)
        
        Args:
            payroll_line (PayrollLine): The payroll line to determine account for
            
        Returns:
            ChartOfAccounts: The determined account, or None if not found
            
        Raises:
            Exception: If account lookup fails (logged but not raised)
        """
        from financial.models import ChartOfAccounts
        import logging
        
        logger = logging.getLogger(__name__)
        
        # 1. إذا كان مرتبط بـ SalaryComponent وله account_code
        if payroll_line.salary_component and payroll_line.salary_component.account_code:
            account = ChartOfAccounts.objects.filter(
                code=payroll_line.salary_component.account_code
            ).first()
            if account:
                return account
        
        # 2. تحديد الحساب بناءً على كود المكون (الذكي)
        component_code = payroll_line.code.lower()
        account_mapping = PayrollService._get_smart_account_mapping()
        
        for pattern, account_info in account_mapping.items():
            if pattern in component_code:
                account = PayrollService._get_safe_account_only(
                    account_info['account_code']
                )
                return account
        
        # 3. الافتراضي: حساب مستحقات الرواتب
        logger.info(f"استخدام الحساب الافتراضي للخصم: {payroll_line.name}")
        return PayrollService._get_safe_account_only('21020')
    
    @staticmethod
    def _get_smart_account_mapping():
        """
        Get smart mapping of component codes to accounting accounts.
        
        This method returns a dictionary that maps component code patterns
        (in both English and Arabic) to their corresponding accounting accounts.
        Used for intelligent account determination when explicit mapping is not available.
        
        Returns:
            dict: Mapping of code patterns to account information containing:
                - account_code: The chart of accounts code
                - account_name: The account name
        """
        return {
            # التأمينات
            'insurance': {
                'account_code': '2103',
                'account_name': 'التأمينات الاجتماعية'
            },
            'social': {
                'account_code': '2103',
                'account_name': 'التأمينات الاجتماعية'
            },
            'تأمين': {
                'account_code': '2103',
                'account_name': 'التأمينات الاجتماعية'
            },
            
            # الضرائب
            'tax': {
                'account_code': '2104',
                'account_name': 'ضرائب الدخل'
            },
            'ضريبة': {
                'account_code': '2104',
                'account_name': 'ضرائب الدخل'
            },
            'ضرائب': {
                'account_code': '2104',
                'account_name': 'ضرائب الدخل'
            },
            
            # السلف
            'advance': {
                'account_code': '21030',
                'account_name': 'سلف الموظفين'
            },
            'loan': {
                'account_code': '21030',
                'account_name': 'سلف الموظفين'
            },
            'سلفة': {
                'account_code': '21030',
                'account_name': 'سلف الموظفين'
            },
            'سلف': {
                'account_code': '21030',
                'account_name': 'سلف الموظفين'
            },
            'قرض': {
                'account_code': '21030',
                'account_name': 'سلف الموظفين'
            },
            
            # الغياب والتأخير
            'absence': {
                'account_code': '21020',
                'account_name': 'مستحقات الرواتب'
            },
            'late': {
                'account_code': '21020',
                'account_name': 'مستحقات الرواتب'
            },
            'غياب': {
                'account_code': '21020',
                'account_name': 'مستحقات الرواتب'
            },
            'تأخير': {
                'account_code': '21020',
                'account_name': 'مستحقات الرواتب'
            },
            
            # النقابة
            'union': {
                'account_code': '2105',
                'account_name': 'اشتراكات النقابة'
            },
            'نقابة': {
                'account_code': '2105',
                'account_name': 'اشتراكات النقابة'
            },
            
            # التأمين الطبي
            'medical': {
                'account_code': '2106',
                'account_name': 'التأمين الطبي'
            },
            'طبي': {
                'account_code': '2106',
                'account_name': 'التأمين الطبي'
            },
        }
    
    @staticmethod
    def _calculate_monthly_totals(paid_payrolls):
        """
        Calculate totals for all deduction types across monthly payrolls.
        
        This method aggregates all salary and deduction amounts from a set
        of paid payroll records to prepare for consolidated journal entry creation.
        
        Args:
            paid_payrolls (QuerySet): QuerySet of paid Payroll records
            
        Returns:
            dict: Dictionary containing totals for:
                - total_gross: Total gross salary
                - total_net: Total net salary
                - total_social_insurance: Total social insurance deductions
                - total_tax: Total tax deductions
                - total_absence_deduction: Total absence deductions
                - total_late_deduction: Total late deductions
                - total_advance_deduction: Total advance deductions
                - total_other_deductions: Total other deductions
        """
        from decimal import Decimal
        
        totals = {
            'total_gross': Decimal('0'),
            'total_net': Decimal('0'),
            'total_social_insurance': Decimal('0'),
            'total_tax': Decimal('0'),
            'total_absence_deduction': Decimal('0'),
            'total_late_deduction': Decimal('0'),
            'total_advance_deduction': Decimal('0'),
            'total_other_deductions': Decimal('0')
        }
        
        for payroll in paid_payrolls:
            totals['total_gross'] += payroll.gross_salary or Decimal('0')
            totals['total_net'] += payroll.net_salary or Decimal('0')
            totals['total_social_insurance'] += payroll.social_insurance or Decimal('0')
            totals['total_tax'] += payroll.tax or Decimal('0')
            totals['total_absence_deduction'] += payroll.absence_deduction or Decimal('0')
            totals['total_late_deduction'] += payroll.late_deduction or Decimal('0')
            totals['total_advance_deduction'] += payroll.advance_deduction or Decimal('0')
            totals['total_other_deductions'] += payroll.other_deductions or Decimal('0')
        
        return totals
    
    @staticmethod
    def _process_monthly_deductions(journal_entry, totals):
        """
        Process all deduction types for monthly consolidated journal entry.
        
        This method creates journal entry lines for aggregated deductions
        from multiple payroll records, routing each deduction type to its
        appropriate liability account.
        
        Args:
            journal_entry (JournalEntry): The journal entry to add lines to
            totals (dict): Dictionary of aggregated totals from _calculate_monthly_totals
            
        Raises:
            Exception: If account lookup fails (logged but not raised)
        """
        from financial.models import JournalEntryLine
        from decimal import Decimal
        
        # خريطة الخصومات الشهرية
        monthly_deductions = {
            'total_social_insurance': {
                'account_code': '2103',
                'account_name': 'التأمينات الاجتماعية',
                'description': 'إجمالي التأمينات الاجتماعية للشهر'
            },
            'total_tax': {
                'account_code': '2104',
                'account_name': 'ضرائب الدخل',
                'description': 'إجمالي ضرائب الدخل للشهر'
            },
            'total_absence_deduction': {
                'account_code': '21020',
                'account_name': 'مستحقات الرواتب',
                'description': 'إجمالي خصومات الغياب للشهر'
            },
            'total_late_deduction': {
                'account_code': '21020',
                'account_name': 'مستحقات الرواتب',
                'description': 'إجمالي خصومات التأخير للشهر'
            },
            'total_advance_deduction': {
                'account_code': '21030',
                'account_name': 'سلف الموظفين',
                'description': 'إجمالي خصومات السلف للشهر'
            },
            'total_other_deductions': {
                'account_code': '21020',
                'account_name': 'مستحقات الرواتب',
                'description': 'إجمالي الخصومات الأخرى للشهر'
            }
        }
        
        # معالجة كل نوع خصم
        for total_key, mapping in monthly_deductions.items():
            total_amount = totals.get(total_key, Decimal('0'))
            
            if total_amount and total_amount > 0:
                account = PayrollService._get_safe_account_only(
                    mapping['account_code']
                )
                
                if account:
                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=account,
                        debit=Decimal('0'),
                        credit=total_amount,
                        description=mapping['description']
                    )
    
    @staticmethod
    @transaction.atomic
    def pay_payroll(payroll, paid_by, payment_account, payment_reference=None):
        """
        Process payment for an approved payroll record.
        
        This method:
        1. Validates payroll status and payment account
        2. Updates payroll status to 'paid' with payment details
        3. Creates individual journal entry for the payment
        4. Automatically posts the journal entry
        
        Args:
            payroll (Payroll): The payroll record to pay
            paid_by (User): The user processing the payment
            payment_account (ChartOfAccounts): The account to pay from (cash/bank)
            payment_reference (str, optional): Payment reference number
        
        Returns:
            Payroll: The paid payroll record with updated status and journal entry
            
        Raises:
            ValueError: If payroll is not approved or payment account is missing
            Exception: Journal entry creation errors are logged but not raised
        """
        from django.utils import timezone
        import logging
        
        logger = logging.getLogger(__name__)
        
        # التحقق من الحالة
        if payroll.status != 'approved':
            raise ValueError('يجب اعتماد قسيمة الراتب أولاً قبل الدفع')
        
        # التحقق من الحساب
        if not payment_account:
            raise ValueError('يجب تحديد حساب الدفع (صندوق أو بنك)')
        
        # ✅ تسجيل الدفع
        payroll.status = 'paid'
        payroll.paid_by = paid_by
        payroll.paid_at = timezone.now()
        payroll.payment_account = payment_account
        payroll.payment_reference = payment_reference or ''
        payroll.save()
        
        # ✅ إنشاء القيد المحاسبي للدفعة الفردية
        try:
            journal_entry = PayrollService._create_individual_journal_entry(payroll, paid_by)
            payroll.journal_entry = journal_entry
            payroll.save()
            
            # ✅ ترحيل القيد تلقائياً
            try:
                from financial.services.expense_income_service import ExpenseIncomeService
                ExpenseIncomeService.post_journal_entry(journal_entry, paid_by)
                
                logger.info(
                    f"تم دفع راتب {payroll.employee.get_full_name_ar()} - {payroll.month} "
                    f"من حساب {payment_account.name} وإنشاء وترحيل القيد المحاسبي رقم {journal_entry.id}"
                )
            except Exception as post_error:
                logger.warning(
                    f"تم إنشاء القيد المحاسبي رقم {journal_entry.id} لكن فشل ترحيله: {str(post_error)}"
                )
                # لا نرفع الخطأ لأن القيد تم إنشاؤه بنجاح
                
        except Exception as e:
            logger.error(
                f"تم دفع الراتب بنجاح لكن فشل إنشاء القيد المحاسبي: {str(e)}"
            )
            # لا نرفع الخطأ لأن الدفع تم بنجاح
        
        return payroll
    
    @staticmethod
    @transaction.atomic
    def create_monthly_payroll_journal_entry(month, paid_payrolls, created_by):
        """
        Create a consolidated journal entry for all paid payrolls in a month.
        
        This method creates a single journal entry that consolidates all
        individual payroll payments for a month, including:
        - Total salary expenses (debit)
        - Total net payments (credit to payment account)
        - All deduction types (credit to liability accounts)
        
        Args:
            month (date): The payroll month as a date object
            paid_payrolls (QuerySet): QuerySet of paid Payroll records
            created_by (User): The user creating the journal entry
        
        Returns:
            JournalEntry: The created and posted journal entry
            
        Raises:
            ValueError: If no paid payrolls exist or salary account (52020) not found
            Exception: Journal posting errors are logged but not raised
        """
        from financial.models import JournalEntry, JournalEntryLine, ChartOfAccounts
        from decimal import Decimal
        import logging
        
        logger = logging.getLogger(__name__)
        
        if not paid_payrolls.exists():
            raise ValueError('لا توجد رواتب مدفوعة لإنشاء قيد محاسبي')
        
        # حساب الإجماليات لجميع أنواع الخصومات
        totals = PayrollService._calculate_monthly_totals(paid_payrolls)
        
        # إنشاء القيد
        entry = JournalEntry.objects.create(
            date=month,
            description=f'مرتبات شهر {month.strftime("%Y-%m")} - {paid_payrolls.count()} موظف',
            created_by=created_by
        )
        
        # من حـ/ مصروف الرواتب والأجور
        salary_account = ChartOfAccounts.objects.filter(code='52020').first()
        if not salary_account:
            raise ValueError('حساب الرواتب والأجور (52020) غير موجود في دليل الحسابات')
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=salary_account,
            debit=totals['total_gross'],
            credit=Decimal('0'),
            description='إجمالي مرتبات الشهر'
        )
        
        # إلى حـ/ الصندوق/البنك (الصافي)
        payment_account = paid_payrolls.first().payment_account
        if payment_account:
            JournalEntryLine.objects.create(
                journal_entry=entry,
                account=payment_account,
                debit=Decimal('0'),
                credit=totals['total_net'],
                description='صافي المرتبات المدفوعة'
            )
        
        # معالجة جميع أنواع الخصومات الشهرية
        PayrollService._process_monthly_deductions(entry, totals)
        
        # ربط القيد بالرواتب
        paid_payrolls.update(journal_entry=entry)
        
        # ✅ ترحيل القيد تلقائياً
        try:
            from financial.services.expense_income_service import ExpenseIncomeService
            ExpenseIncomeService.post_journal_entry(entry, created_by)
            
            logger.info(
                f"تم إنشاء وترحيل قيد محاسبي عام لمرتبات {month.strftime('%Y-%m')} - "
                f"عدد الموظفين: {paid_payrolls.count()}, الإجمالي: {totals['total_gross']}"
            )
        except Exception as post_error:
            logger.warning(
                f"تم إنشاء القيد المحاسبي رقم {entry.id} لكن فشل ترحيله: {str(post_error)}"
            )
            # لا نرفع الخطأ لأن القيد تم إنشاؤه بنجاح
        
        return entry
