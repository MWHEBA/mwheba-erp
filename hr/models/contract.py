"""
نموذج العقود
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator
from datetime import date, timedelta

User = get_user_model()

# نموذج العقود مع دعم الزيادات المجدولة والتعديلات
class Contract(models.Model):
    """نموذج عقد الموظف"""
    
    CONTRACT_TYPE_CHOICES = [
        ('permanent', 'دائم'),
        ('temporary', 'مؤقت'),
        ('contract', 'عقد محدد المدة'),
        ('internship', 'تدريب'),
        ('part_time', 'دوام جزئي'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'مسودة'),
        ('active', 'ساري'),
        ('suspended', 'موقوف'),
        ('expired', 'منتهي'),
        ('terminated', 'منهي'),
    ]
    
    # معلومات العقد الأساسية
    contract_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='رقم العقد'
    )
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='contracts',
        verbose_name='الموظف'
    )
    contract_type = models.CharField(
        max_length=20,
        choices=CONTRACT_TYPE_CHOICES,
        verbose_name='نوع العقد'
    )
    
    # بيانات الوظيفة
    job_title = models.ForeignKey(
        'JobTitle',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name='المسمى الوظيفي',
        help_text='الوظيفة في هذا العقد'
    )
    department = models.ForeignKey(
        'Department',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name='القسم',
        help_text='القسم في هذا العقد'
    )
    
    # رقم البصمة (للربط السريع)
    biometric_user_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='رقم البصمة',
        help_text='رقم الموظف في جهاز البصمة (اختياري - سيتم حفظه في ملف الموظف)'
    )
    
    # التواريخ
    start_date = models.DateField(verbose_name='تاريخ البداية')
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='تاريخ النهاية'
    )
    probation_period_months = models.IntegerField(
        default=3,
        null=True,
        blank=True,
        verbose_name='فترة التجربة (بالأشهر)'
    )
    probation_end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='تاريخ انتهاء التجربة'
    )
    
    # الراتب
    basic_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='الراتب الأساسي'
    )
    
    # الزيادة السنوية التلقائية
    INCREASE_FREQUENCY_CHOICES = [
        ('annual', 'سنوي'),
        ('semi_annual', 'نصف سنوي'),
        ('quarterly', 'ربع سنوي'),
        ('monthly', 'شهري'),
    ]
    
    INCREASE_START_CHOICES = [
        ('contract_date', 'تاريخ العقد'),
        ('january', 'يناير'),
        ('july', 'يوليو'),
    ]
    
    has_annual_increase = models.BooleanField(
        default=False,
        verbose_name='يستحق زيادة سنوية'
    )
    annual_increase_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='نسبة الزيادة السنوية (%)',
        help_text='مثال: 10 تعني 10% سنوياً'
    )
    increase_frequency = models.CharField(
        max_length=20,
        choices=INCREASE_FREQUENCY_CHOICES,
        default='annual',
        verbose_name='تكرار الزيادة'
    )
    increase_start_reference = models.CharField(
        max_length=20,
        choices=INCREASE_START_CHOICES,
        default='contract_date',
        verbose_name='بداية احتساب الزيادة'
    )
    next_increase_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='تاريخ الزيادة القادمة'
    )
    
    # البنود والشروط
    terms_and_conditions = models.TextField(
        blank=True,
        verbose_name='البنود والشروط'
    )
    special_clauses = models.TextField(
        blank=True,
        verbose_name='بنود خاصة'
    )
    
    # ملف العقد
    contract_file = models.FileField(
        upload_to='contracts/%Y/%m/',
        null=True,
        blank=True,
        validators=[FileExtensionValidator(['pdf', 'doc', 'docx'])],
        verbose_name='ملف العقد'
    )
    
    # التجديد
    auto_renew = models.BooleanField(
        default=False,
        verbose_name='تجديد تلقائي'
    )
    renewal_notice_days = models.IntegerField(
        default=30,
        null=True,
        blank=True,
        verbose_name='أيام الإشعار قبل التجديد'
    )
    renewed_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='renewed_from',
        verbose_name='تم التجديد إلى'
    )
    
    # الحالة
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name='الحالة'
    )
    
    # ملاحظات
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    
    # التواريخ والمستخدمين
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_contracts',
        verbose_name='أنشئ بواسطة'
    )
    signed_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='تاريخ التوقيع'
    )
    
    class Meta:
        verbose_name = 'عقد'
        verbose_name_plural = 'العقود'
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['contract_number']),
            models.Index(fields=['employee', 'status']),
            models.Index(fields=['start_date', 'end_date']),
        ]
        permissions = [
            ("can_manage_contracts", "إدارة العقود"),
            ("can_sign_contracts", "توقيع العقود"),
            ("can_terminate_contracts", "إنهاء العقود"),
        ]
    
    def __str__(self):
        return f"{self.contract_number} - {self.employee.get_full_name_ar()}"
    
    def clean(self):
        """
        التحقق من صحة البيانات قبل الحفظ
        - منع تداخل العقود لنفس الموظف
        - التأكد من أن تاريخ النهاية بعد تاريخ البداية
        """
        from django.core.exceptions import ValidationError
        
        # التحقق من التواريخ
        if self.end_date and self.start_date and self.end_date <= self.start_date:
            raise ValidationError({
                'end_date': 'تاريخ النهاية يجب أن يكون بعد تاريخ البداية'
            })
        
        # منع تداخل العقود (إلا إذا كان العقد الحالي منتهي أو منهي أو موقوف)
        if self.employee_id and self.start_date:
            # الحالات المسموح بها للعقود المتداخلة
            allowed_statuses = ['expired', 'terminated', 'suspended']
            
            # البحث عن عقود متداخلة
            overlapping_contracts = Contract.objects.filter(
                employee=self.employee
            ).exclude(
                pk=self.pk  # استثناء العقد الحالي عند التعديل
            ).exclude(
                status__in=allowed_statuses  # استثناء العقود المنتهية/المنهية/الموقوفة
            )
            
            # التحقق من التداخل في الفترة الزمنية
            for contract in overlapping_contracts:
                # حالة 1: العقد الموجود مفتوح (بدون تاريخ نهاية)
                if not contract.end_date:
                    raise ValidationError({
                        'start_date': f'يوجد عقد ساري للموظف بدون تاريخ نهاية ({contract.contract_number}). '
                                     f'يجب إنهاء أو إيقاف العقد الحالي أولاً.'
                    })
                
                # حالة 2: العقد الجديد مفتوح (بدون تاريخ نهاية)
                if not self.end_date:
                    raise ValidationError({
                        'end_date': f'يوجد عقد ساري للموظف ({contract.contract_number}) '
                                   f'من {contract.start_date} إلى {contract.end_date}. '
                                   f'لا يمكن إنشاء عقد مفتوح. يجب إنهاء العقد الحالي أولاً.'
                    })
                
                # حالة 3: تداخل في الفترات الزمنية
                # العقد الجديد يبدأ قبل انتهاء العقد الموجود
                if self.start_date <= contract.end_date:
                    # والعقد الجديد ينتهي بعد بداية العقد الموجود (أو مفتوح)
                    if not self.end_date or self.end_date >= contract.start_date:
                        raise ValidationError({
                            'start_date': f'يوجد تداخل مع عقد ساري ({contract.contract_number}) '
                                         f'من {contract.start_date} إلى {contract.end_date}. '
                                         f'يجب إنهاء أو إيقاف العقد الحالي أولاً، '
                                         f'أو استخدام خاصية التجديد.'
                        })
    
    def calculate_next_increase_date(self):
        """حساب تاريخ الزيادة القادمة"""
        if not self.has_annual_increase or not self.annual_increase_percentage:
            return None
        
        if not self.start_date:
            return None
        
        # تحديد نقطة البداية
        if self.increase_start_reference == 'contract_date':
            base_date = self.start_date
        elif self.increase_start_reference == 'january':
            current_year = date.today().year
            base_date = date(current_year, 1, 1)
            # إذا كان يناير فات، استخدم السنة الجاية
            if base_date < self.start_date:
                base_date = date(current_year + 1, 1, 1)
        else:  # july
            current_year = date.today().year
            base_date = date(current_year, 7, 1)
            # إذا كان يوليو فات، استخدم السنة الجاية
            if base_date < self.start_date:
                base_date = date(current_year + 1, 7, 1)
        
        # حساب الفترة بالأشهر
        months_map = {
            'annual': 12,
            'semi_annual': 6,
            'quarterly': 3,
            'monthly': 1,
        }
        months = months_map.get(self.increase_frequency, 12)
        
        # استخدام dateutil إذا متاح (أدق)
        try:
            from dateutil.relativedelta import relativedelta
            
            # حساب التاريخ القادم
            next_date = base_date
            today = date.today()
            
            # إذا base_date في المستقبل، استخدمه مباشرة
            if next_date > today:
                return next_date
            
            # وإلا، احسب التاريخ القادم
            while next_date <= today:
                next_date = next_date + relativedelta(months=months)
            
            return next_date
            
        except ImportError:
            # Fallback: استخدام timedelta (أقل دقة)
            next_date = base_date
            today = date.today()
            
            # إذا base_date في المستقبل، استخدمه مباشرة
            if next_date > today:
                return next_date
            
            # وإلا، احسب التاريخ القادم
            days = months * 30  # تقريبي
            while next_date <= today:
                next_date = next_date + timedelta(days=days)
            
            return next_date
    
    def save(self, *args, **kwargs):
        # التحقق من صحة البيانات
        self.clean()
        
        # حساب تاريخ انتهاء التجربة
        if self.start_date and self.probation_period_months:
            self.probation_end_date = self.start_date + timedelta(
                days=self.probation_period_months * 30
            )
        
        # حساب تاريخ الزيادة القادمة (فقط إذا لم يتم تعديله يدوياً)
        if self.has_annual_increase:
            # التحقق من التعديل اليدوي
            if self.pk:  # عقد موجود
                try:
                    old_instance = Contract.objects.get(pk=self.pk)
                    # إذا تم تعديل التاريخ يدوياً، لا تحسبه تلقائياً
                    if old_instance.next_increase_date != self.next_increase_date:
                        # التاريخ تم تعديله يدوياً، احتفظ به
                        pass
                    else:
                        # التاريخ لم يتغير، احسبه تلقائياً
                        self.next_increase_date = self.calculate_next_increase_date()
                except Contract.DoesNotExist:
                    # عقد جديد، احسب التاريخ
                    self.next_increase_date = self.calculate_next_increase_date()
            else:
                # عقد جديد، احسب التاريخ
                self.next_increase_date = self.calculate_next_increase_date()
        
        super().save(*args, **kwargs)
    
    @property
    def is_active(self):
        """هل العقد ساري"""
        return self.status == 'active'
    
    @property
    def is_expired(self):
        """هل العقد منتهي"""
        if self.end_date:
            return date.today() > self.end_date
        return False
    
    @property
    def days_until_expiry(self):
        """عدد الأيام المتبقية حتى انتهاء العقد"""
        if self.end_date:
            delta = self.end_date - date.today()
            return delta.days if delta.days > 0 else 0
        return None
    
    @property
    def needs_renewal_notice(self):
        """هل يحتاج العقد لإشعار تجديد"""
        if self.end_date and self.days_until_expiry is not None:
            return self.days_until_expiry <= self.renewal_notice_days
        return False
    
    @property
    def duration_months(self):
        """مدة العقد بالأشهر"""
        if self.start_date and self.end_date:
            delta = self.end_date - self.start_date
            return delta.days // 30
        return None
    
    @property
    def total_earnings(self):
        """إجمالي المستحقات (من بنود الموظف)"""
        from decimal import Decimal
        # البنود تتبع الموظف الآن (مش العقد)
        earnings = self.employee.salary_components.filter(component_type='earning')
        total = sum(component.amount for component in earnings)
        return Decimal(str(self.basic_salary)) + Decimal(str(total))
    
    @property
    def total_deductions(self):
        """إجمالي الاستقطاعات (من بنود الموظف)"""
        from decimal import Decimal
        # البنود تتبع الموظف الآن (مش العقد)
        deductions = self.employee.salary_components.filter(component_type='deduction')
        return sum(Decimal(str(component.amount)) for component in deductions)
    
    @property
    def net_salary(self):
        """صافي الراتب"""
        return self.total_earnings - self.total_deductions
    
    def terminate(self, termination_date=None):
        """إنهاء العقد"""
        self.status = 'terminated'
        if termination_date:
            self.end_date = termination_date
        self.save()
    
    def create_increase_schedule(self, annual_percentage, installments, interval_months, created_by):
        """
        إنشاء جدول زيادات مجدولة للعقد
        
        Args:
            annual_percentage: النسبة السنوية الإجمالية (مثال: 15 للزيادة 15%)
            installments: عدد الدفعات (مثال: 2 لدفعتين)
            interval_months: الفترة بين كل دفعة بالأشهر (مثال: 6 لكل 6 أشهر)
            created_by: المستخدم الذي أنشأ الجدول
        
        Returns:
            list: قائمة بالزيادات المجدولة المُنشأة
        """
        from dateutil.relativedelta import relativedelta
        
        # حساب نسبة كل دفعة
        percentage_per_installment = annual_percentage / installments
        
        increases = []
        for i in range(1, installments + 1):
            # حساب عدد الأشهر من بداية العقد
            months_from_start = interval_months * i
            
            # حساب التاريخ المجدول
            scheduled_date = self.start_date + relativedelta(months=months_from_start)
            
            # إنشاء الزيادة
            increase = ContractIncrease.objects.create(
                contract=self,
                increase_number=i,
                increase_type='percentage',
                increase_percentage=percentage_per_installment,
                months_from_start=months_from_start,
                scheduled_date=scheduled_date,
                status='pending',
                created_by=created_by,
                notes=f'زيادة تلقائية {i} من {installments} - {percentage_per_installment}% كل {interval_months} شهور'
            )
            increases.append(increase)
        
        return increases


class ContractAmendment(models.Model):
    """نموذج تعديلات العقد"""
    
    AMENDMENT_TYPE_CHOICES = [
        ('salary_increase', 'زيادة راتب'),
        ('salary_deduction', 'استقطاع'),
        ('position_change', 'تغيير منصب'),
        ('extension', 'تمديد'),
        ('other', 'أخرى'),
    ]
    
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='amendments',
        verbose_name='العقد'
    )
    amendment_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='رقم التعديل'
    )
    amendment_type = models.CharField(
        max_length=20,
        choices=AMENDMENT_TYPE_CHOICES,
        verbose_name='نوع التعديل'
    )
    effective_date = models.DateField(verbose_name='تاريخ السريان')
    description = models.TextField(verbose_name='الوصف')
    
    # التغييرات
    field_name = models.CharField(max_length=100, blank=True, verbose_name='اسم الحقل')
    old_value = models.TextField(blank=True, verbose_name='القيمة القديمة')
    new_value = models.TextField(blank=True, verbose_name='القيمة الجديدة')
    
    # تلقائي أم يدوي
    is_automatic = models.BooleanField(default=False, verbose_name='تلقائي')
    
    # ملف التعديل
    amendment_file = models.FileField(
        upload_to='contract_amendments/%Y/%m/',
        null=True,
        blank=True,
        validators=[FileExtensionValidator(['pdf', 'doc', 'docx'])],
        verbose_name='ملف التعديل'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        verbose_name='أنشئ بواسطة'
    )
    
    class Meta:
        verbose_name = 'تعديل عقد'
        verbose_name_plural = 'تعديلات العقود'
        ordering = ['-effective_date']
    
    def __str__(self):
        return f"{self.amendment_number} - {self.contract.contract_number}"


class ContractDocument(models.Model):
    """مرفقات ووثائق العقد"""
    
    DOCUMENT_TYPE_CHOICES = [
        ('signed_contract', 'العقد الموقع'),
        ('id_copy', 'صورة الهوية'),
        ('certificate', 'الشهادات'),
        ('medical_report', 'التقرير الطبي'),
        ('bank_account', 'بيانات الحساب البنكي'),
        ('other', 'أخرى'),
    ]
    
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name='العقد'
    )
    document_type = models.CharField(
        max_length=50,
        choices=DOCUMENT_TYPE_CHOICES,
        verbose_name='نوع الوثيقة'
    )
    title = models.CharField(
        max_length=200,
        verbose_name='العنوان'
    )
    file = models.FileField(
        upload_to='contract_documents/%Y/%m/',
        validators=[FileExtensionValidator(['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'])],
        verbose_name='الملف'
    )
    description = models.TextField(
        blank=True,
        verbose_name='الوصف'
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='تاريخ الرفع'
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        verbose_name='رفع بواسطة'
    )
    
    class Meta:
        verbose_name = 'وثيقة عقد'
        verbose_name_plural = 'وثائق العقود'
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.get_document_type_display()} - {self.contract.contract_number}"
    
    @property
    def file_extension(self):
        """امتداد الملف"""
        return self.file.name.split('.')[-1].lower() if self.file else None
    
    @property
    def is_image(self):
        """هل الملف صورة"""
        return self.file_extension in ['jpg', 'jpeg', 'png', 'gif']
    
    @property
    def file_size_mb(self):
        """حجم الملف بالميجابايت"""
        if self.file:
            return round(self.file.size / (1024 * 1024), 2)
        return 0


class ContractIncrease(models.Model):
    """جدول الزيادات المجدولة للعقد"""
    
    INCREASE_TYPE_CHOICES = [
        ('percentage', 'نسبة مئوية'),
        ('fixed', 'مبلغ ثابت'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'قيد الانتظار'),
        ('applied', 'تم التطبيق'),
        ('cancelled', 'ملغي'),
    ]
    
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='scheduled_increases',
        verbose_name='العقد'
    )
    increase_number = models.IntegerField(
        verbose_name='رقم الزيادة',
        help_text='الترتيب التسلسلي للزيادة (1، 2، 3...)'
    )
    increase_type = models.CharField(
        max_length=20,
        choices=INCREASE_TYPE_CHOICES,
        default='percentage',
        verbose_name='نوع الزيادة'
    )
    increase_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='نسبة الزيادة (%)',
        help_text='مثال: 7.5 للزيادة 7.5%'
    )
    increase_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='مبلغ الزيادة الثابت'
    )
    months_from_start = models.IntegerField(
        verbose_name='عدد الأشهر من بداية العقد',
        help_text='مثال: 6 للزيادة بعد 6 أشهر من بداية العقد'
    )
    scheduled_date = models.DateField(
        verbose_name='التاريخ المجدول',
        help_text='التاريخ المتوقع لتطبيق الزيادة'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='الحالة'
    )
    applied_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='تاريخ التطبيق الفعلي'
    )
    applied_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='المبلغ المطبق',
        help_text='المبلغ الفعلي الذي تم إضافته للراتب'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='ملاحظات'
    )
    
    # ربط بالتعديل إذا تم إنشاؤه
    amendment = models.OneToOneField(
        ContractAmendment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='increase_schedule',
        verbose_name='التعديل المرتبط'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='created_increases',
        verbose_name='أنشئ بواسطة'
    )
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'زيادة مجدولة'
        verbose_name_plural = 'الزيادات المجدولة'
        ordering = ['contract', 'increase_number']
        unique_together = ['contract', 'increase_number']
    
    def __str__(self):
        if self.increase_type == 'percentage':
            return f"زيادة {self.increase_percentage}% - {self.contract.contract_number} (#{self.increase_number})"
        else:
            return f"زيادة {self.increase_amount} جنيه - {self.contract.contract_number} (#{self.increase_number})"
    
    def calculate_increase_amount(self, current_salary):
        """حساب مبلغ الزيادة بناءً على الراتب الحالي"""
        if self.increase_type == 'percentage':
            return (current_salary * self.increase_percentage) / 100
        else:
            return self.increase_amount or 0
    
    def apply_increase(self, applied_by):
        """تطبيق الزيادة على العقد"""
        from django.utils import timezone
        
        if self.status == 'applied':
            return False, "الزيادة مطبقة بالفعل"
        
        # حساب المبلغ الفعلي
        current_salary = self.contract.basic_salary
        increase_amount = self.calculate_increase_amount(current_salary)
        
        # تحديث راتب العقد
        old_salary = self.contract.basic_salary
        new_salary = old_salary + increase_amount
        self.contract.basic_salary = new_salary
        self.contract.save()
        
        # تحديث حالة الزيادة
        self.status = 'applied'
        self.applied_date = timezone.now().date()
        self.applied_amount = increase_amount
        self.save()
        
        # إنشاء تعديل في العقد
        amendment = ContractAmendment.objects.create(
            contract=self.contract,
            amendment_number=f"{self.contract.contract_number}-INC-{self.increase_number}",
            amendment_type='salary_increase',
            effective_date=self.applied_date,
            description=f"زيادة مجدولة #{self.increase_number}: {self.increase_percentage if self.increase_type == 'percentage' else self.increase_amount}",
            field_name='basic_salary',
            old_value=str(old_salary),
            new_value=str(new_salary),
            is_automatic=True,
            created_by=applied_by
        )
        
        # ربط التعديل بالزيادة
        self.amendment = amendment
        self.save()
        
        return True, f"تم تطبيق الزيادة بنجاح: {increase_amount} جنيه"
    
    def cancel_increase(self):
        """إلغاء الزيادة"""
        if self.status == 'applied':
            return False, "لا يمكن إلغاء زيادة مطبقة بالفعل"
        
        self.status = 'cancelled'
        self.save()
        return True, "تم إلغاء الزيادة"
    
    @property
    def is_due(self):
        """هل حان موعد الزيادة"""
        from django.utils import timezone
        return self.status == 'pending' and self.scheduled_date <= timezone.now().date()
    
    @property
    def days_until_due(self):
        """عدد الأيام المتبقية حتى موعد الزيادة"""
        from django.utils import timezone
        if self.status != 'pending':
            return None
        delta = self.scheduled_date - timezone.now().date()
        return delta.days
