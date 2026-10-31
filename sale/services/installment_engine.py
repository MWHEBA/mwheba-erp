# -*- coding: utf-8 -*-
"""
Installment Engine - محرك أقساط المبيعات والرياضيات المالية الحاكمة
مسؤول عن:
1. توليد جداول الأقساط وحساب الفوائد التمويلية وضبط فروق الكسور (Penny Difference) على القسط الأول.
2. استيعاب عربون أمر البيع السابق (SalesOrder.paid_down_payment) والدفعة المقدمة واستبعادها من وعاء الفائدة.
3. التوارث الديناميكي لفترات السماح من الملف الائتماني للعميل ومراعاة العطلات المصرفية المصرية (Next Business Day).
4. السداد النسبي (Pro-Rata) وشلال الفائض الأمامي، وتوجيه فائض القسط الأخير للرصيد المسبق (PREPAID_BALANCE).
5. احتساب غرامات التأخير اليومية على أصل الدين غير المسدد فقط وفقاً للمادة 232 من القانون المدني المصري.
"""
import logging
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from datetime import date, timedelta
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from sale.models.installments import InstallmentPlan, InstallmentItem
from sale.models.sale import Sale
from sale.models.payment import SalePayment

logger = logging.getLogger(__name__)


class InstallmentEngine:
    """
    محرك الرياضيات المالية والجدولة لحسابات تقسيط المبيعات
    """

    WEEKEND_DAYS = {4, 5}  # Friday=4, Saturday=5 in Python weekday() (Monday=0)

    @classmethod
    def adjust_for_banking_calendar(cls, target_date: date) -> date:
        """
        ترحيل مواعيد الاستحقاق المصرفي إذا صادف عطلة نهاية الأسبوع (الجمعة أو السبت في مصر)
        إلى أول يوم عمل مصرفي رسمي لاحق (الأحد) - Next Business Day Rule
        """
        curr = target_date
        while curr.weekday() in cls.WEEKEND_DAYS:
            curr += timedelta(days=1)
        return curr

    @classmethod
    def calculate_installment_schedule(
        cls,
        sale: Sale,
        number_of_installments: int,
        markup_rate: Decimal = Decimal('0.000'),
        fresh_down_payment: Decimal = Decimal('0.00'),
        frequency: str = 'MONTHLY',
        start_date: date = None,
        grace_period_days: int = None,
    ) -> dict:
        """
        حساب جدول الأقساط الدقيق وضبط كسور الجنيه بالمليم (Penny Rounding Precision)
        """
        if number_of_installments <= 0:
            raise ValidationError(_("عدد الأقساط يجب أن يكون أكبر من الصفر."))

        if not start_date:
            start_date = timezone.now().date()

        # استيعاب عربون أمر البيع السابق (إن وجد)
        so_down_payment = Decimal('0.00')
        if hasattr(sale, 'sales_order') and sale.sales_order:
            so_down_payment = getattr(sale.sales_order, 'paid_down_payment', Decimal('0.00')) or Decimal('0.00')

        effective_down_payment = (fresh_down_payment + so_down_payment).quantize(Decimal('0.01'))

        # 1. المطالبة الضريبية الشاملة للسلع والخدمات (Subtotal - Discount + VAT - WHT)
        # sale.total يمثل الصافي بعد الخصومات والضرائب وخصم ضريبة الـ WHT
        tax_inclusive_claim = (sale.total or Decimal('0.00')).quantize(Decimal('0.01'))

        if effective_down_payment > tax_inclusive_claim:
            raise ValidationError(_("إجمالي الدفعة المقدمة والعربون يتجاوز قيمة الفاتورة الإجمالية."))

        # 2. أصل الدين الممول المتبقي للجدولة
        net_financed_principal = (tax_inclusive_claim - effective_down_payment).quantize(Decimal('0.01'))

        # 3. وعاء احتساب الفائدة التمويلية: صافي البضاعة التجارية مستبعداً منه المقدم والعربون
        # لحماية العميل والالتزام بالقانون الضريبي بعدم فرض فوائد على الضرائب
        subtotal_less_discount = (sale.subtotal - (sale.discount or Decimal('0.00'))).quantize(Decimal('0.01'))
        interest_base = max(Decimal('0.00'), subtotal_less_discount - effective_down_payment)

        # 4. إجمالي الفائدة التمويلية
        total_markup = (interest_base * (markup_rate / Decimal('100.000'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # 5. المبلغ التعاقدي الشامل للتقسيط
        contract_total = (tax_inclusive_claim + total_markup).quantize(Decimal('0.01'))
        total_scheduled_amount = (net_financed_principal + total_markup).quantize(Decimal('0.01'))

        # 6. توزيع أصل الأقساط والفوائد مع معادلة البيني (Penny Difference)
        n = Decimal(str(number_of_installments))
        base_principal = (net_financed_principal / n).quantize(Decimal('0.01'), rounding=ROUND_FLOOR)
        base_interest = (total_markup / n).quantize(Decimal('0.01'), rounding=ROUND_FLOOR)

        principal_penny = net_financed_principal - (base_principal * n)
        interest_penny = total_markup - (base_interest * n)

        # توارث فترة السماح من الملف الائتماني للعميل
        if grace_period_days is None:
            if hasattr(sale.customer, 'credit_profile') and sale.customer.credit_profile:
                grace_period_days = sale.customer.credit_profile.grace_period_days
            else:
                grace_period_days = 3

        items_schedule = []
        for i in range(1, number_of_installments + 1):
            # تحميل فرق الكسور على القسط الأول لضمان توازن الأستاذ العام
            p_amt = base_principal + (principal_penny if i == 1 else Decimal('0.00'))
            i_amt = base_interest + (interest_penny if i == 1 else Decimal('0.00'))
            tot_amt = p_amt + i_amt

            # حساب تاريخ الاستحقاق بحسب الدورية
            if frequency == 'MONTHLY':
                # إضافة أشهر تقريبية (30 يوماً لكل قسط)
                calc_date = start_date + timedelta(days=30 * (i - 1))
            elif frequency == 'QUARTERLY':
                calc_date = start_date + timedelta(days=90 * (i - 1))
            elif frequency == 'BIWEEKLY':
                calc_date = start_date + timedelta(days=14 * (i - 1))
            else:
                calc_date = start_date + timedelta(days=30 * (i - 1))

            due_date = cls.adjust_for_banking_calendar(calc_date)

            items_schedule.append({
                'installment_number': i,
                'due_date': due_date,
                'original_due_date': due_date,
                'principal_amount': p_amt,
                'interest_amount': i_amt,
                'total_amount': tot_amt,
                'grace_period_days': grace_period_days,
            })

        return {
            'tax_inclusive_claim': tax_inclusive_claim,
            'effective_down_payment': effective_down_payment,
            'net_financed_principal': net_financed_principal,
            'interest_base': interest_base,
            'total_markup': total_markup,
            'contract_total': contract_total,
            'total_scheduled_amount': total_scheduled_amount,
            'items': items_schedule,
            'grace_period_days': grace_period_days,
        }

    @classmethod
    @transaction.atomic
    def generate_installment_plan(
        cls,
        sale: Sale,
        user,
        number_of_installments: int,
        markup_rate: Decimal = Decimal('0.000'),
        fresh_down_payment: Decimal = Decimal('0.00'),
        down_payment_account=None,
        plan_type: str = InstallmentPlan.PlanType.ASSET_FINANCING,
        frequency: str = 'MONTHLY',
        start_date: date = None,
        max_tolerance_percent: Decimal = Decimal('5.00'),
        collateral_cheque=None,
        collateral_lg_number: str = None,
        collateral_lg_expiry_date: date = None,
        collateral_lg_bank: str = None,
        guarantor_name: str = None,
        guarantor_national_id: str = None,
        guarantor_phone: str = None,
        guarantor_address: str = None,
        notes: str = "",
    ) -> InstallmentPlan:
        """
        إنشاء خطة التقسيط وجدول الأقساط وسند الدفعة المقدمة بحماية ذرية كاملة
        """
        if hasattr(sale, 'installment_plan') and sale.installment_plan:
            raise ValidationError(_("يوجد جدول تقسيط مسجل بالفعل لهذه الفاتورة."))

        calc_result = cls.calculate_installment_schedule(
            sale=sale,
            number_of_installments=number_of_installments,
            markup_rate=markup_rate,
            fresh_down_payment=fresh_down_payment,
            frequency=frequency,
            start_date=start_date,
        )

        # تحديث حقول الفاتورة لتطابق العقد التقسيطي
        rate = Decimal(str(sale.exchange_rate or '1.000000'))
        sale.is_installment_sale = True
        sale.markup_rate = markup_rate
        sale.markup_amount = calc_result['total_markup']
        sale.contract_total = calc_result['contract_total']
        sale.contract_total_functional = (calc_result['contract_total'] * rate).quantize(Decimal('0.01'))
        sale.save(update_fields=[
            'is_installment_sale', 'markup_rate', 'markup_amount',
            'contract_total', 'contract_total_functional'
        ])

        # إنشاء خطة التقسيط
        plan = InstallmentPlan.objects.create(
            sale=sale,
            customer=sale.customer,
            plan_type=plan_type,
            total_principal=calc_result['net_financed_principal'],
            markup_rate=markup_rate,
            total_markup=calc_result['total_markup'],
            total_amount=calc_result['contract_total'],
            down_payment=calc_result['effective_down_payment'],
            number_of_installments=number_of_installments,
            frequency=frequency,
            max_tolerance_percent=max_tolerance_percent,
            start_date=calc_result['items'][0]['due_date'] if calc_result['items'] else timezone.now().date(),
            status=InstallmentPlan.PlanStatus.ACTIVE,
            collateral_cheque=collateral_cheque,
            collateral_lg_number=collateral_lg_number,
            collateral_lg_expiry_date=collateral_lg_expiry_date,
            collateral_lg_bank=collateral_lg_bank,
            guarantor_name=guarantor_name,
            guarantor_national_id=guarantor_national_id,
            guarantor_phone=guarantor_phone,
            guarantor_address=guarantor_address,
            notes=notes,
            created_by=user,
        )

        # إنشاء بنود الأقساط
        for item_data in calc_result['items']:
            InstallmentItem.objects.create(
                plan=plan,
                installment_number=item_data['installment_number'],
                due_date=item_data['due_date'],
                original_due_date=item_data['original_due_date'],
                principal_amount=item_data['principal_amount'],
                interest_amount=item_data['interest_amount'],
                total_amount=item_data['total_amount'],
                grace_period_days=item_data['grace_period_days'],
                paper_coverage=InstallmentItem.PaperCoverage.UNCOVERED,
                cash_status=InstallmentItem.CashStatus.PENDING,
            )

        # ميكنة سند الدفعة المقدمة (إن وجدت نقدية جديدة مسددة)
        if fresh_down_payment > Decimal('0.00'):
            payment = SalePayment.objects.create(
                sale=sale,
                amount=fresh_down_payment,
                amount_settled_invoice_currency=fresh_down_payment,
                amount_functional=(fresh_down_payment * rate).quantize(Decimal('0.01')),
                payment_date=timezone.now().date(),
                payment_method='cash' if not down_payment_account else str(down_payment_account.code),
                financial_account=down_payment_account,
                reference_number=f"DP-{sale.number}",
                notes=_("[INSTALLMENT_DOWN_PAYMENT] دفعة مقدمة معتمدة لعقد التقسيط"),
                status='posted',
                created_by=user,
            )
            # تحديث حالة سداد الفاتورة ورصيد العميل
            sale.update_payment_status()
            from sale.signals import recalculate_customer_balance
            recalculate_customer_balance(sale.customer)

        logger.info(f"✅ تم إنشاء خطة التقسيط رقم {plan.id} بنجاح للفاتورة {sale.number}")
        return plan

    @classmethod
    @transaction.atomic
    def record_installment_payment(
        cls,
        installment_item: InstallmentItem,
        amount: Decimal,
        payment_date: date,
        user,
        payment_method: str = 'cash',
        financial_account=None,
        reference_number: str = None,
        notes: str = None,
    ) -> SalePayment:
        """
        تسجيل سداد القسط مع تطبيق خوارزمية التوزيع النسبي (Pro-Rata)
        وشلال الفائض الأمامي (Forward Spillover) وتوجيه فائض القسط الأخير للرصيد المسبق
        """
        if amount <= Decimal('0.00'):
            raise ValidationError(_("مبلغ السداد يجب أن يكون أكبر من الصفر."))

        item = InstallmentItem.objects.select_for_update().get(pk=installment_item.pk)
        plan = item.plan
        sale = plan.sale

        due_on_item = item.remaining_balance
        allocated_to_current = min(amount, due_on_item)
        surplus = amount - allocated_to_current

        # التوزيع النسبي (Pro-Rata) بين أصل القسط والفوائد للدفعة المسددة على هذا القسط
        if allocated_to_current >= due_on_item:
            # إقفال تام لكامل المتبقي على القسط بالمليم
            p_alloc = item.remaining_principal
            i_alloc = item.remaining_interest
        elif item.total_amount > Decimal('0.00'):
            principal_ratio = item.principal_amount / item.total_amount
            p_alloc = (allocated_to_current * principal_ratio).quantize(Decimal('0.01'), rounding=ROUND_FLOOR)
            p_alloc = min(p_alloc, item.remaining_principal)
            i_alloc = allocated_to_current - p_alloc
        else:
            p_alloc = allocated_to_current
            i_alloc = Decimal('0.00')

        # تحديث حقول القسط الحالي
        item.paid_principal += p_alloc
        item.paid_interest += i_alloc
        item.paid_amount += allocated_to_current
        item.paid_date = payment_date

        if item.remaining_balance <= Decimal('0.00'):
            item.cash_status = InstallmentItem.CashStatus.COLLECTED
        else:
            item.cash_status = InstallmentItem.CashStatus.PARTIALLY_PAID
        item.save()

        # إنشاء سند الدفع الرئيسي
        has_next_item = plan.items.filter(
            installment_number__gt=item.installment_number
        ).exists() if plan else False
        actual_payment_amount = allocated_to_current if has_next_item else amount

        rate = Decimal(str(sale.exchange_rate or '1.000000'))
        payment = SalePayment.objects.create(
            sale=sale,
            installment_item=item,
            amount=actual_payment_amount,
            amount_settled_invoice_currency=actual_payment_amount,
            amount_functional=(actual_payment_amount * rate).quantize(Decimal('0.01')),
            payment_date=payment_date,
            payment_method=payment_method,
            financial_account=financial_account,
            reference_number=reference_number or f"INST-{item.installment_number}-{sale.number}",
            notes=notes or f"سداد قسط #{item.installment_number} للفاتورة {sale.number}",
            status='posted',
            source_type='INSTALLMENT',
            financial_status='synced',
            created_by=user,
        )

        # ترحيل القيد المحاسبي للدفعة في دفتر الأستاذ العام
        try:
            from sale.services.sale_service import SaleService
            je = SaleService._create_payment_journal_entry(payment, user)
            if je:
                payment.financial_transaction = je
                payment.save(update_fields=['financial_transaction'])
        except Exception as je_err:
            logger.warning(f"ملاحظة أثناء إنشاء قيد تحصيل القسط #{item.installment_number}: {je_err}")

        # شلال الفائض الأمامي (Forward Spillover)
        if surplus > Decimal('0.00'):
            next_item = plan.items.filter(
                installment_number__gt=item.installment_number
            ).order_by('installment_number').first()

            if next_item:
                # سداد القسط التالي تلقائياً
                cls.record_installment_payment(
                    installment_item=next_item,
                    amount=surplus,
                    payment_date=payment_date,
                    user=user,
                    payment_method=payment_method,
                    financial_account=financial_account,
                    reference_number=f"SPILLOVER-{next_item.installment_number}-{sale.number}",
                    notes=f"فائض محول من القسط #{item.installment_number}",
                )
            else:
                # فائض القسط الأخير: يوجه تلقائياً كرصيد مسبق للعميل (PREPAID_BALANCE)
                customer = sale.customer
                customer.balance = (customer.balance - surplus).quantize(Decimal('0.01'))
                customer.save(update_fields=['balance'])
                # تسجيل إشعار دفعة مقدمة في سجلات العميل
                logger.info(f"تم توجيه فائض القسط الأخير {surplus} كرصيد مسبق للعميل {customer.name}")

        # تحديث حالة الخطة والفاتورة
        cls.evaluate_plan_closure(plan)
        return payment

    @classmethod
    def evaluate_plan_closure(cls, plan: InstallmentPlan):
        """
        فحص تصفير الخطة وإغلاقها كـ COMPLETED والفاتورة كـ paid
        """
        all_items = list(plan.items.all())
        total_remaining = sum(it.remaining_balance for it in all_items)

        if total_remaining <= Decimal('0.00'):
            plan.status = InstallmentPlan.PlanStatus.COMPLETED
            plan.save(update_fields=['status'])
            plan.sale.payment_status = 'paid'
            plan.sale.save(update_fields=['payment_status'])
        else:
            has_rework = any(it.cash_status == InstallmentItem.CashStatus.HOLD_REWORK for it in all_items)
            if has_rework:
                plan.status = InstallmentPlan.PlanStatus.DISPUTED
            else:
                plan.status = InstallmentPlan.PlanStatus.ACTIVE
            plan.save(update_fields=['status'])
            plan.sale.payment_status = 'partially_paid' if any(it.paid_amount > 0 for it in all_items) else 'unpaid'
            plan.sale.save(update_fields=['payment_status'])

    @classmethod
    def calculate_article_232_penalty(
        cls,
        installment_item: InstallmentItem,
        current_date: date = None,
        annual_rate_percent: Decimal = Decimal('12.00'),
    ) -> Decimal:
        """
        حساب غرامة التأخير المشروعة تطبيقاً للمادة 232 من القانون المدني المصري:
        1. تحسب حصراً على أصل الدين غير المسدد (Unpaid Principal Only) مستبعداً منها أي فوائد تقسيط.
        2. حظر احتساب فائدة على متجمد الفوائد أو غرامات سابقة.
        3. سقف الغرامة لا يتجاوز أصل الدين (Penalty Cap).
        4. تتوقف الغرامة تماماً إذا كان القسط معلقاً لإعادة تشغيل (HOLD_REWORK) أو مسقطاً (WAIVED).
        """
        if installment_item.cash_status in [
            InstallmentItem.CashStatus.HOLD_REWORK,
            InstallmentItem.CashStatus.WAIVED,
            InstallmentItem.CashStatus.COLLECTED,
            InstallmentItem.CashStatus.COLLECTED_CONTRA,
        ] or installment_item.is_retention_guarantee:
            return Decimal('0.00')

        if not current_date:
            current_date = timezone.now().date()

        due_date = installment_item.due_date
        grace_days = installment_item.grace_period_days

        # تاريخ بدء احتساب التأخير الفعلي بعد فترة السماح
        penalty_start_date = due_date + timedelta(days=grace_days)
        if current_date <= penalty_start_date:
            return Decimal('0.00')

        overdue_days = (current_date - penalty_start_date).days
        unpaid_principal = installment_item.remaining_principal

        if unpaid_principal <= Decimal('0.00'):
            return Decimal('0.00')

        daily_rate = (annual_rate_percent / Decimal('100.00')) / Decimal('365.00')
        raw_penalty = (unpaid_principal * daily_rate * Decimal(str(overdue_days))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # سقف الغرامة: لا يتجاوز أصل الدين غير المسدد
        return min(unpaid_principal, raw_penalty)
