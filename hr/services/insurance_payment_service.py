"""
خدمة دفعات تأمين الموظفين الخارجيين
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone as tz


class InsurancePaymentService:

    @staticmethod
    def generate_monthly_payments(month):
        """
        توليد InsurancePayment لكل موظف is_insurance_only نشط.
        المبلغ يُجلب من SalaryComponent بكود INSURANCE_TOTAL.
        لو مش موجود → total_amount = 0 (يعدّله المحاسب يدوياً).
        يتجاهل الموظفين اللي عندهم سجل بالفعل لنفس الشهر.

        Returns:
            tuple: (created_list, skipped_list)
        """
        from ..models import Employee, InsurancePayment

        employees = Employee.objects.filter(
            is_insurance_only=True,
            status='active'
        ).prefetch_related('salary_components')

        created, skipped = [], []

        for emp in employees:
            component = emp.salary_components.filter(
                code='INSURANCE_TOTAL',
                is_active=True
            ).first()
            amount = component.amount if component else Decimal('0')

            obj, is_new = InsurancePayment.objects.get_or_create(
                employee=emp,
                month=month,
                defaults={'total_amount': amount}
            )
            (created if is_new else skipped).append(obj)

        return created, skipped

    @staticmethod
    @transaction.atomic
    def record_payment(insurance_payment, payment_account, received_by, payment_date=None):
        """
        تسجيل دفع الموظف + إنشاء القيد المحاسبي عبر AccountingGateway.

        القيد:
            مدين: خزنة (payment_account.code)
            دائن: التأمينات مستحقة الدفع (20210)

        Args:
            insurance_payment: InsurancePayment instance
            payment_account: ChartOfAccounts instance (خزنة أو بنك)
            received_by: User instance
            payment_date: date (اختياري — افتراضي اليوم)

        Returns:
            InsurancePayment: السجل المحدّث
        """
        from governance.services.accounting_gateway import (
            AccountingGateway, JournalEntryLineData
        )

        if insurance_payment.status == 'paid':
            raise ValueError('تم تسجيل هذه الدفعة مسبقاً')

        if insurance_payment.total_amount <= 0:
            raise ValueError('المبلغ يجب أن يكون أكبر من صفر — يرجى تحديث المبلغ أولاً')

        actual_date = payment_date or tz.now().date()
        emp_name = insurance_payment.employee.get_full_name_ar()
        month_str = insurance_payment.month.strftime('%Y-%m')

        lines = [
            JournalEntryLineData(
                account_code=payment_account.code,
                debit=insurance_payment.total_amount,
                credit=Decimal('0'),
                description=f'تأمين {emp_name} - {month_str}'
            ),
            JournalEntryLineData(
                account_code='20210',
                debit=Decimal('0'),
                credit=insurance_payment.total_amount,
                description=f'التزام تأمين {emp_name} - {month_str}'
            ),
        ]

        entry = AccountingGateway().create_journal_entry(
            source_module='hr',
            source_model='InsurancePayment',
            source_id=insurance_payment.id,
            lines=lines,
            idempotency_key=f'JE:hr:InsurancePayment:{insurance_payment.id}:pay',
            user=received_by,
            entry_type='cash_receipt',
            description=f'تأمين {emp_name} - {month_str}',
            date=actual_date,
        )

        insurance_payment.status = 'paid'
        insurance_payment.payment_date = actual_date
        insurance_payment.payment_account = payment_account
        insurance_payment.journal_entry = entry
        insurance_payment.received_by = received_by
        insurance_payment.save()

        return insurance_payment
