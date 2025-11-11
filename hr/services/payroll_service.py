"""
خدمة معالجة الرواتب
"""
from django.db import transaction
from datetime import date
from decimal import Decimal
from ..models import Payroll, Employee, Advance
from .attendance_service import AttendanceService
import logging

logger = logging.getLogger(__name__)


class PayrollService:
    """خدمة معالجة الرواتب"""
    
    @staticmethod
    @transaction.atomic
    def calculate_payroll(employee, month, processed_by):
        """
        حساب راتب موظف لشهر معين
        
        Args:
            employee: الموظف
            month: الشهر (datetime.date)
            processed_by: المستخدم الذي عالج الراتب
        
        Returns:
            Payroll: قسيمة الراتب
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
        """حساب الراتب بالنظام الجديد (SalaryComponent + PayrollLine)"""
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
        
        # 3. حساب الراتب الأساسي من العقد أولاً
        if contract.basic_salary:
            basic_salary = Decimal(str(contract.basic_salary))
        else:
            # إذا لم يكن موجود في العقد، جربه من البند
            basic_component = components.filter(is_basic=True).first()
            basic_salary = basic_component.amount if basic_component else Decimal('0')
        
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
            # الشهر كامل
            worked_days = attendance_stats.get('present_days', total_days_in_month)
            if worked_days == 0:
                worked_days = total_days_in_month  # افتراضي إذا لم يكن هناك حضور مسجل
        
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
            gross_salary=Decimal('0'),
            total_additions=Decimal('0'),
            total_deductions=Decimal('0'),
            net_salary=Decimal('0'),
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
        خصم السلف - نظام الأقساط المحسّن
        يخصم قسط شهري من كل سلفة نشطة
        
        Args:
            employee: الموظف
            month: الشهر (datetime.date)
        
        Returns:
            Decimal: إجمالي خصم السلف لهذا الشهر
        """
        from ..models import AdvanceInstallment
        
        # الحصول على السلف النشطة (مدفوعة أو قيد الخصم)
        advances = Advance.objects.filter(
            employee=employee,
            status__in=['paid', 'in_progress'],
            deduction_start_month__lte=month
        ).exclude(
            status='completed'
        ).order_by('deduction_start_month')
        
        if not advances.exists():
            logger.debug(f"لا توجد سلف نشطة للموظف {employee.get_full_name_ar()} في شهر {month}")
            return Decimal('0')
        
        total_deduction = Decimal('0')
        
        for advance in advances:
            # التحقق من عدم وجود قسط لهذا الشهر بالفعل
            existing_installment = AdvanceInstallment.objects.filter(
                advance=advance,
                month=month
            ).exists()
            
            if existing_installment:
                logger.warning(
                    f"قسط موجود بالفعل للسلفة {advance.id} للموظف {employee.get_full_name_ar()} "
                    f"في شهر {month}"
                )
                continue
            
            # الحصول على قيمة القسط التالي
            installment_amount = advance.get_next_installment_amount()
            
            if installment_amount > 0:
                try:
                    # تسجيل القسط
                    advance.record_installment_payment(month, installment_amount)
                    total_deduction += installment_amount
                    
                    logger.info(
                        f"تم خصم قسط {installment_amount} ج.م من السلفة {advance.id} "
                        f"للموظف {employee.get_full_name_ar()} - "
                        f"القسط {advance.paid_installments}/{advance.installments_count}"
                    )
                except Exception as e:
                    logger.error(
                        f"خطأ في خصم قسط السلفة {advance.id} للموظف {employee.get_full_name_ar()}: {str(e)}"
                    )
                    # نستمر مع السلف الأخرى
                    continue
        
        logger.info(
            f"إجمالي خصم السلف للموظف {employee.get_full_name_ar()} في شهر {month}: "
            f"{total_deduction} ج.م"
        )
        
        return total_deduction
    
    @staticmethod
    @transaction.atomic
    def process_monthly_payroll(month, processed_by, employees=None):
        """
        معالجة رواتب الموظفين لشهر معين
        
        Args:
            month: الشهر (datetime.date)
            processed_by: المستخدم الذي عالج الرواتب
            employees: قائمة الموظفين المراد معالجة رواتبهم (اختياري)
        
        Returns:
            list: نتائج المعالجة
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
        اعتماد قسيمة راتب (بدون إنشاء قيد محاسبي)
        
        Args:
            payroll: قسيمة الراتب
            approved_by: المعتمد
        
        Returns:
            Payroll: قسيمة الراتب المعتمدة
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
        إنشاء قيد محاسبي للراتب
        
        Args:
            payroll: قسيمة الراتب
        
        Returns:
            JournalEntry: القيد المحاسبي
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
        إنشاء قيد محاسبي للراتب الفردي (محسن للدفعة الفردية)
        
        Args:
            payroll: قسيمة الراتب
            created_by: منشئ القيد
        
        Returns:
            JournalEntry: القيد المحاسبي
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
        معالجة جميع أنواع الخصومات وتوجيهها للحسابات المحاسبية الصحيحة
        
        Args:
            journal_entry: القيد المحاسبي
            payroll: قسيمة الراتب
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
        البحث عن حساب موجود فقط - لا ينشئ حسابات جديدة (نظام آمن)
        
        Args:
            account_code: رمز الحساب
            
        Returns:
            ChartOfAccounts: الحساب المحاسبي أو None
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
        معالجة المستحقات الديناميكية من PayrollLine بناءً على SalaryComponent
        
        Args:
            journal_entry: القيد المحاسبي
            payroll: قسيمة الراتب
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
        معالجة الخصومات الديناميكية من PayrollLine بناءً على SalaryComponent
        
        Args:
            journal_entry: القيد المحاسبي
            payroll: قسيمة الراتب
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
        تحديد الحساب المحاسبي المناسب لمكون الراتب
        
        Args:
            payroll_line: سطر قسيمة الراتب
            
        Returns:
            ChartOfAccounts: الحساب المحاسبي أو None
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
        خريطة ذكية لربط أكواد المكونات بالحسابات المحاسبية
        
        Returns:
            dict: خريطة الربط الذكي
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
        حساب إجماليات جميع أنواع الخصومات للرواتب الشهرية
        
        Args:
            paid_payrolls: QuerySet من الرواتب المدفوعة
            
        Returns:
            dict: قاموس يحتوي على جميع الإجماليات
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
        معالجة جميع أنواع الخصومات للقيد الشهري
        
        Args:
            journal_entry: القيد المحاسبي
            totals: قاموس الإجماليات
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
        دفع قسيمة راتب (مع تسجيل معلومات الدفع وإنشاء قيد محاسبي)
        
        Args:
            payroll: قسيمة الراتب
            paid_by: من دفع
            payment_account: الحساب المدفوع منه (صندوق/بنك)
            payment_reference: مرجع الدفع (اختياري)
        
        Returns:
            Payroll: قسيمة الراتب المدفوعة
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
            
            logger.info(
                f"تم دفع راتب {payroll.employee.get_full_name_ar()} - {payroll.month} "
                f"من حساب {payment_account.name} وإنشاء القيد المحاسبي رقم {journal_entry.id}"
            )
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
        إنشاء قيد محاسبي عام لجميع رواتب الشهر المدفوعة
        
        Args:
            month: الشهر (datetime.date)
            paid_payrolls: QuerySet من الرواتب المدفوعة
            created_by: منشئ القيد
        
        Returns:
            JournalEntry: القيد المحاسبي
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
        
        logger.info(
            f"تم إنشاء قيد محاسبي عام لمرتبات {month.strftime('%Y-%m')} - "
            f"عدد الموظفين: {paid_payrolls.count()}, الإجمالي: {totals['total_gross']}"
        )
        
        return entry
