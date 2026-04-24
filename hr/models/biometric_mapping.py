"""
نموذج ربط معرفات البصمة بالموظفين
"""
from django.db import models


class BiometricUserMapping(models.Model):
    """
    ربط معرف البصمة برقم الموظف
    
    يستخدم عندما يكون معرف المستخدم في البصمة مختلف عن رقم الموظف
    """
    
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='biometric_mappings',
        verbose_name='الموظف'
    )
    
    biometric_user_id = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='معرف المستخدم في البصمة'
    )
    
    device = models.ForeignKey(
        'BiometricDevice',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='user_mappings',
        verbose_name='الماكينة'
    )
    
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'ربط معرف البصمة'
        verbose_name_plural = 'ربط معرفات البصمة'
        unique_together = ['employee', 'biometric_user_id']
    
    def __str__(self):
        return f"{self.employee.employee_number} → {self.biometric_user_id}"
