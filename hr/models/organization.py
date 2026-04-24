"""
نماذج الهيكل التنظيمي
"""
from django.db import models


class Department(models.Model):
    """نموذج الأقسام والإدارات"""
    
    code = models.CharField(max_length=20, unique=True, verbose_name='كود القسم')
    name_ar = models.CharField(max_length=200, verbose_name='اسم القسم (عربي)')
    name_en = models.CharField(max_length=200, verbose_name='اسم القسم (إنجليزي)', blank=True)
    description = models.TextField(blank=True, verbose_name='الوصف')
    
    # التسلسل الهرمي
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='sub_departments',
        verbose_name='القسم الأب'
    )
    
    # المدير
    manager = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_departments',
        verbose_name='مدير القسم'
    )

    # مركز التكلفة
    financial_subcategory = models.ForeignKey(
        'financial.FinancialSubcategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='departments',
        verbose_name='مركز التكلفة (التصنيف الفرعي)',
    )
    
    # الحالة
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    
    class Meta:
        verbose_name = 'قسم'
        verbose_name_plural = 'الأقسام'
        ordering = ['code']
    
    def __str__(self):
        return f"{self.code} - {self.name_ar}"
    
    @property
    def employees_count(self):
        """عدد الموظفين النشطين في القسم"""
        return self.employees.filter(status='active').count()
    
    @property
    def full_path(self):
        """المسار الكامل للقسم في الهيكل التنظيمي"""
        if self.parent:
            return f"{self.parent.full_path} > {self.name_ar}"
        return self.name_ar
    
    @classmethod
    def create_default_departments(cls):
        """إنشاء الأقسام الافتراضية للشركة"""
        from django.db import transaction
        
        # الأقسام الافتراضية للشركة
        default_departments = [
            {'code': 'ADM', 'name_ar': 'الإدارة العامة', 'name_en': 'Administration', 'parent_code': None},
            {'code': 'OPS', 'name_ar': 'العمليات', 'name_en': 'Operations', 'parent_code': None},
            {'code': 'SUP', 'name_ar': 'الإشراف والمتابعة', 'name_en': 'Supervision & Follow-up', 'parent_code': None},
            {'code': 'FIN', 'name_ar': 'الشؤون المالية', 'name_en': 'Financial Affairs', 'parent_code': 'ADM'},
            {'code': 'SRV', 'name_ar': 'الخدمات المساندة', 'name_en': 'Support Services', 'parent_code': None},
            
            # أقسام فرعية للعمليات
            {'code': 'OPS-PRD', 'name_ar': 'الإنتاج', 'name_en': 'Production', 'parent_code': 'OPS'},
            {'code': 'OPS-QC', 'name_ar': 'ضبط الجودة', 'name_en': 'Quality Control', 'parent_code': 'OPS'},
            {'code': 'OPS-LOG', 'name_ar': 'اللوجستيات', 'name_en': 'Logistics', 'parent_code': 'OPS'},
            {'code': 'OPS-ACT', 'name_ar': 'الأنشطة', 'name_en': 'Activities', 'parent_code': 'OPS'},
            
            # أقسام فرعية للإشراف
            {'code': 'SUP-TRN', 'name_ar': 'إشراف النقل', 'name_en': 'Transportation Supervision', 'parent_code': 'SUP'},
            {'code': 'SUP-FLD', 'name_ar': 'إشراف الميدان', 'name_en': 'Field Supervision', 'parent_code': 'SUP'},
            {'code': 'SUP-HEALTH', 'name_ar': 'الرعاية الصحية', 'name_en': 'Health Care', 'parent_code': 'SUP'},
        ]
        
        try:
            with transaction.atomic():
                # إنشاء الأقسام الرئيسية أولاً
                for dept_data in default_departments:
                    if dept_data['parent_code'] is None:
                        cls.objects.get_or_create(
                            code=dept_data['code'],
                            defaults={
                                'name_ar': dept_data['name_ar'],
                                'name_en': dept_data['name_en'],
                                'is_active': True
                            }
                        )
                
                # ثم إنشاء الأقسام الفرعية
                for dept_data in default_departments:
                    if dept_data['parent_code'] is not None:
                        parent_dept = cls.objects.get(code=dept_data['parent_code'])
                        cls.objects.get_or_create(
                            code=dept_data['code'],
                            defaults={
                                'name_ar': dept_data['name_ar'],
                                'name_en': dept_data['name_en'],
                                'parent': parent_dept,
                                'is_active': True
                            }
                        )
                
                return True
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"فشل في إنشاء أقسام الشركة: {e}")
            return False


class JobTitle(models.Model):
    """نموذج المسميات الوظيفية"""
    
    code = models.CharField(max_length=20, unique=True, verbose_name='كود الوظيفة')
    title_ar = models.CharField(max_length=200, verbose_name='المسمى (عربي)')
    title_en = models.CharField(max_length=200, verbose_name='المسمى (إنجليزي)', blank=True)
    description = models.TextField(blank=True, verbose_name='الوصف')
    
    # القسم
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='job_titles',
        verbose_name='القسم'
    )
    
    # المسؤوليات والمتطلبات
    responsibilities = models.TextField(verbose_name='المسؤوليات', blank=True)
    requirements = models.TextField(verbose_name='المتطلبات', blank=True)
    
    # الحالة
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    
    class Meta:
        verbose_name = 'مسمى وظيفي'
        verbose_name_plural = 'المسميات الوظيفية'
        ordering = ['code']
    
    def __str__(self):
        return f"{self.code} - {self.title_ar}"
    
    @staticmethod
    def generate_code():
        """توليد كود تلقائي مسلسل للوظيفة"""
        # جلب جميع الوظائف وترتيبها حسب الكود
        job_titles = JobTitle.objects.filter(code__startswith='JOB-').order_by('-code')
        
        if job_titles.exists():
            last_job_title = job_titles.first()
            try:
                last_number = int(last_job_title.code.split('-')[1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = 1
        else:
            new_number = 1
        
        return f"JOB-{new_number:04d}"
    
    def save(self, *args, **kwargs):
        """حفظ الوظيفة مع توليد الكود تلقائياً إذا لم يكن موجوداً"""
        if not self.code:
            self.code = self.generate_code()
        super().save(*args, **kwargs)
    
    @classmethod
    def create_default_job_titles(cls):
        """إنشاء المسميات الوظيفية الافتراضية للشركة"""
        from django.db import transaction
        
        # إنشاء الأقسام أولاً
        Department.create_default_departments()
        
        # المسميات الوظيفية للشركة
        default_job_titles = [
            # الإدارة العليا
            {'code': 'CRP-001', 'title_ar': 'المدير العام', 'title_en': 'General Manager', 'department_code': 'ADM'},
            {'code': 'CRP-002', 'title_ar': 'نائب المدير', 'title_en': 'Deputy Manager', 'department_code': 'ADM'},
            {'code': 'CRP-003', 'title_ar': 'مدير تنفيذي', 'title_en': 'Executive Director', 'department_code': 'ADM'},
            
            # العمليات
            {'code': 'CRP-101', 'title_ar': 'مشرف عمليات', 'title_en': 'Operations Supervisor', 'department_code': 'OPS'},
            {'code': 'CRP-102', 'title_ar': 'مسؤول عمليات', 'title_en': 'Operations Officer', 'department_code': 'OPS'},
            {'code': 'CRP-103', 'title_ar': 'مساعد عمليات', 'title_en': 'Operations Assistant', 'department_code': 'OPS'},
            {'code': 'CRP-104', 'title_ar': 'منسق أنشطة', 'title_en': 'Activities Coordinator', 'department_code': 'OPS'},
            {'code': 'CRP-105', 'title_ar': 'مسؤول جودة', 'title_en': 'Quality Officer', 'department_code': 'OPS'},
            {'code': 'CRP-106', 'title_ar': 'مسؤول لوجستيات', 'title_en': 'Logistics Officer', 'department_code': 'OPS'},
            
            # الإشراف والمتابعة
            {'code': 'CRP-201', 'title_ar': 'مشرف نقل', 'title_en': 'Transport Supervisor', 'department_code': 'SUP'},
            {'code': 'CRP-202', 'title_ar': 'مشرف ميداني', 'title_en': 'Field Supervisor', 'department_code': 'SUP'},
            {'code': 'CRP-203', 'title_ar': 'مشرف أنشطة', 'title_en': 'Activities Supervisor', 'department_code': 'SUP'},
            {'code': 'CRP-204', 'title_ar': 'مسؤول صحة وسلامة', 'title_en': 'Health & Safety Officer', 'department_code': 'SUP'},
            
            # الإدارة والخدمات
            {'code': 'CRP-301', 'title_ar': 'سكرتير إداري', 'title_en': 'Administrative Secretary', 'department_code': 'ADM'},
            {'code': 'CRP-302', 'title_ar': 'محاسب', 'title_en': 'Accountant', 'department_code': 'FIN'},
            {'code': 'CRP-303', 'title_ar': 'مسؤول أرشيف', 'title_en': 'Archive Officer', 'department_code': 'ADM'},
            {'code': 'CRP-304', 'title_ar': 'موظف استقبال', 'title_en': 'Receptionist', 'department_code': 'ADM'},
            
            # الخدمات المساندة
            {'code': 'CRP-401', 'title_ar': 'عامل نظافة', 'title_en': 'Cleaner', 'department_code': 'SRV'},
            {'code': 'CRP-402', 'title_ar': 'حارس أمن', 'title_en': 'Security Guard', 'department_code': 'SRV'},
            {'code': 'CRP-403', 'title_ar': 'فني صيانة', 'title_en': 'Maintenance Technician', 'department_code': 'SRV'},
            {'code': 'CRP-404', 'title_ar': 'عامل خدمات', 'title_en': 'Services Worker', 'department_code': 'SRV'},
        ]
        
        try:
            with transaction.atomic():
                for job_data in default_job_titles:
                    department = Department.objects.get(code=job_data['department_code'])
                    
                    cls.objects.get_or_create(
                        code=job_data['code'],
                        defaults={
                            'title_ar': job_data['title_ar'],
                            'title_en': job_data['title_en'],
                            'department': department,
                            'is_active': True
                        }
                    )
                
                return True
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"فشل في إنشاء المسميات الوظيفية للشركة: {e}")
            return False
