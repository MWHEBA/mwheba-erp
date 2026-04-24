"""
إشارات الأذونات
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import PermissionRequest
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


@receiver(post_save, sender=PermissionRequest)
def recalculate_attendance_summary_on_extra_permission(sender, instance, created, **kwargs):
    """
    إعادة حساب ملخص الحضور تلقائياً عند تغيير أي إذن إضافي (is_extra=True)
    يضمن أن is_deduction_exempt يُطبَّق فوراً على الملخص
    """
    if not instance.is_extra:
        return  # الأذونات العادية لا تؤثر على extra_permissions_hours

    try:
        from datetime import date
        from .attendance_summary import AttendanceSummary
        from hr.utils.payroll_helpers import get_payroll_period

        perm_date = instance.date
        month = date(perm_date.year, perm_date.month, 1)
        start_date, end_date, _ = get_payroll_period(month)

        # جلب الملخص إن وُجد وغير معتمد
        summary = AttendanceSummary.objects.filter(
            employee=instance.employee,
            month=month,
            is_approved=False  # لا نعيد حساب الملخصات المعتمدة
        ).first()

        if summary and summary.is_calculated:
            logger.info(
                f"إعادة حساب ملخص الحضور للموظف {instance.employee.get_full_name_ar()} "
                f"شهر {month} بسبب تغيير إذن إضافي ID={instance.id} "
                f"(is_deduction_exempt={instance.is_deduction_exempt})"
            )
            summary.calculate()

    except Exception as e:
        logger.error(f"خطأ في إعادة حساب ملخص الحضور بعد تغيير الإذن: {e}")


@receiver(post_save, sender=PermissionRequest)
def send_permission_notifications(sender, instance, created, **kwargs):
    """
    إرسال إشعارات الأذونات - نفس نمط leave notifications
    للإدارة فقط (لا يتم إرسال إشعارات للموظفين)
    """
    try:
        from core.models import Notification
        
        if created and instance.status == 'pending':
            # إشعار للمدير المباشر
            if hasattr(instance.employee, 'direct_manager') and instance.employee.direct_manager:
                if hasattr(instance.employee.direct_manager, 'user') and instance.employee.direct_manager.user:
                    Notification.objects.create(
                        user=instance.employee.direct_manager.user,
                        title='طلب إذن جديد يحتاج موافقة',
                        message=f'إذن للموظف {instance.employee.get_full_name_ar()} - {instance.permission_type.name_ar}',
                        notification_type='permission_pending',
                        link=f'/hr/permissions/{instance.pk}/'
                    )
            
            # إشعار لمجموعة HR
            hr_users = User.objects.filter(groups__name__in=['HR', 'HR Manager'])
            for hr_user in hr_users:
                Notification.objects.create(
                    user=hr_user,
                    title='طلب إذن جديد',
                    message=f'تم تسجيل إذن للموظف {instance.employee.get_full_name_ar()}',
                    notification_type='permission_created',
                    link=f'/hr/permissions/{instance.pk}/'
                )
        
        elif instance.status == 'approved':
            # إشعار للـ HR بالاعتماد
            hr_users = User.objects.filter(groups__name__in=['HR', 'HR Manager'])
            for hr_user in hr_users:
                Notification.objects.create(
                    user=hr_user,
                    title='تم اعتماد إذن',
                    message=f'تم اعتماد إذن {instance.permission_type.name_ar} للموظف {instance.employee.get_full_name_ar()}',
                    notification_type='permission_approved',
                    link=f'/hr/permissions/{instance.pk}/'
                )
        
        elif instance.status == 'rejected':
            # إشعار للـ HR بالرفض
            hr_users = User.objects.filter(groups__name__in=['HR', 'HR Manager'])
            for hr_user in hr_users:
                Notification.objects.create(
                    user=hr_user,
                    title='تم رفض إذن',
                    message=f'تم رفض إذن {instance.permission_type.name_ar} للموظف {instance.employee.get_full_name_ar()}',
                    notification_type='permission_rejected',
                    link=f'/hr/permissions/{instance.pk}/'
                )
    
    except Exception:
        # تجاهل الأخطاء في الإشعارات - لا نريد أن تؤثر على العملية الأساسية
        pass
