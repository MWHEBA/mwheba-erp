"""
نموذج سجل تدقيق وتتبع التعديلات اليدوية على الحضور والانصراف
"""
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class AttendanceAuditLog(models.Model):
    """سجل تدقيق التعديلات اليدوية وبصمة المشرف (Attendance Audit Trail)"""

    attendance = models.ForeignKey(
        'Attendance',
        on_delete=models.CASCADE,
        related_name='audit_logs',
        verbose_name='سجل الحضور'
    )
    field_name = models.CharField(max_length=100, verbose_name='الحقل المعدل')
    old_value = models.TextField(blank=True, null=True, verbose_name='القيمة السابقة')
    new_value = models.TextField(blank=True, null=True, verbose_name='القيمة الجديدة')

    changed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='attendance_audit_edits',
        verbose_name='المستخدم المنفذ'
    )
    reason = models.TextField(verbose_name='سبب التعديل / الملاحظة')

    supervisor_witness = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supervised_audit_punches',
        verbose_name='المشرف الشاهد والمسؤول'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ وتوقيت التعديل')

    class Meta:
        verbose_name = 'سجل تدقيق حضور'
        verbose_name_plural = 'سجلات تدقيق الحضور'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.attendance.employee} - {self.field_name} ({self.created_at})"
