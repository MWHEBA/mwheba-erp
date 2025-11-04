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
