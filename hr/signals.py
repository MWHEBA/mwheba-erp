"""
إشارات (Signals) نظام الموارد البشرية
تحديث تلقائي لأرصدة الإجازات عند تغيير تاريخ التعيين
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.db import transaction
from datetime import date
import logging

logger = logging.getLogger(__name__)


@receiver(pre_save, sender='hr.Employee')
def track_hire_date_change(sender, instance, **kwargs):
    """
    تتبع تغيير تاريخ التعيين قبل الحفظ
    يحفظ التاريخ القديم للمقارنة بعد الحفظ
    """
    if instance.pk:  # موظف موجود (تعديل)
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            if old_instance.hire_date != instance.hire_date:
                # حفظ التاريخ القديم للمقارنة
                instance._old_hire_date = old_instance.hire_date
                instance._hire_date_changed = True
                
                logger.info(
                    f"تم اكتشاف تغيير في تاريخ التعيين للموظف {instance.get_full_name_ar()}: "
                    f"{old_instance.hire_date} → {instance.hire_date}"
                )
        except sender.DoesNotExist:
            pass


@receiver(post_save, sender='hr.Employee')
def update_leave_accrual_on_hire_date_change(sender, instance, created, **kwargs):
    """
    تحديث أرصدة الإجازات تلقائياً عند:
    1. تغيير تاريخ التعيين (يدوياً)
    2. إضافة موظف جديد بتاريخ قديم
    
    يحدث الأرصدة بناءً على مدة الخدمة الجديدة
    """
    from .services.leave_accrual_service import LeaveAccrualService
    from .models import LeaveBalance
    
    # التحقق من الحالات التي تحتاج تحديث
    needs_update = False
    reason = ""
    
    if created:
        # موظف جديد - التحقق من مدة الخدمة
        from core.models import SystemSetting
        probation_months = SystemSetting.get_setting('leave_accrual_probation_months', 3)
        
        months_worked = LeaveAccrualService.calculate_months_worked(instance.hire_date)
        if months_worked >= probation_months:  # لديه أرصدة مستحقة
            needs_update = True
            reason = f"موظف جديد بتاريخ تعيين قديم ({months_worked} شهر)"
    
    elif getattr(instance, '_hire_date_changed', False):
        # تم تغيير تاريخ التعيين
        needs_update = True
        old_date = getattr(instance, '_old_hire_date', None)
        reason = f"تغيير تاريخ التعيين من {old_date} إلى {instance.hire_date}"
    
    if needs_update and instance.status == 'active':
        try:
            with transaction.atomic():
                current_year = date.today().year
                
                # التحقق من وجود أرصدة، وإنشائها إذا لم تكن موجودة
                existing_balances = LeaveBalance.objects.filter(
                    employee=instance,
                    year=current_year
                ).count()
                
                if existing_balances == 0:
                    # التحقق من إعداد الإنشاء التلقائي
                    from core.models import SystemSetting
                    auto_create = SystemSetting.get_setting('leave_auto_create_balances', True)
                    
                    if not auto_create:
                        logger.info(
                            f"تم تخطي إنشاء أرصدة الإجازات للموظف {instance.get_full_name_ar()} - "
                            f"الإنشاء التلقائي معطل في الإعدادات"
                        )
                        return
                    
                    # إنشاء أرصدة جديدة
                    from .models import LeaveType
                    leave_types = LeaveType.objects.filter(is_active=True)
                    
                    if leave_types.exists():
                        months_worked = LeaveAccrualService.calculate_months_worked(instance.hire_date)
                        accrual_percentage = LeaveAccrualService.get_accrual_percentage(months_worked)
                        
                        created_count = 0
                        for leave_type in leave_types:
                            total_days = leave_type.max_days_per_year
                            accrued_days = int(total_days * accrual_percentage)
                            
                            LeaveBalance.objects.create(
                                employee=instance,
                                leave_type=leave_type,
                                year=current_year,
                                total_days=total_days,
                                accrued_days=accrued_days,
                                used_days=0,
                                remaining_days=accrued_days,
                                accrual_start_date=instance.hire_date,
                                last_accrual_date=date.today()
                            )
                            created_count += 1
                        
                        logger.info(
                            f"تم إنشاء {created_count} رصيد إجازة للموظف {instance.get_full_name_ar()} - "
                            f"السبب: {reason} - "
                            f"نسبة الاستحقاق: {int(accrual_percentage*100)}%"
                        )
                else:
                    # تحديث الأرصدة الموجودة
                    result = LeaveAccrualService.update_employee_accrual(instance, current_year)
                    
                    # تحديث accrual_start_date في جميع الأرصدة
                    LeaveBalance.objects.filter(
                        employee=instance,
                        year=current_year
                    ).update(accrual_start_date=instance.hire_date)
                    
                    logger.info(
                        f"تم تحديث أرصدة الإجازات للموظف {instance.get_full_name_ar()} - "
                        f"السبب: {reason} - "
                        f"عدد الأرصدة المحدثة: {result['updated_count']}"
                    )
                
        except Exception as e:
            logger.error(
                f"خطأ في تحديث أرصدة الإجازات للموظف {instance.get_full_name_ar()}: {str(e)}"
            )
    
    # حذف الـ flags المؤقتة
    if hasattr(instance, '_hire_date_changed'):
        delattr(instance, '_hire_date_changed')
    if hasattr(instance, '_old_hire_date'):
        delattr(instance, '_old_hire_date')


@receiver(post_save, sender='hr.LeaveBalance')
def auto_update_remaining_days(sender, instance, created, **kwargs):
    """
    تحديث تلقائي للأيام المتبقية عند تغيير الأيام المستحقة أو المستخدمة
    """
    # حساب الأيام المتبقية
    new_remaining = instance.accrued_days - instance.used_days
    
    # تحديث فقط إذا كان هناك فرق (لتجنب infinite loop)
    if instance.remaining_days != new_remaining:
        sender.objects.filter(pk=instance.pk).update(remaining_days=new_remaining)
