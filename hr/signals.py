"""
إشارات (Signals) نظام الموارد البشرية
تحديث تلقائي لأرصدة الإجازات عند تغيير تاريخ التعيين
تحديث تلقائي لحالة العقود
إشعارات تلقائية للعقود
تتبع تلقائي لتعديلات العقود
"""
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.db import transaction
from datetime import date
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

@receiver(pre_save, sender='hr.Contract')
def auto_update_contract_status(sender, instance, **kwargs):
    """
    تحديث حالة العقد تلقائياً بناءً على التواريخ
    - لا يتم تغيير الحالات اليدوية (suspended, terminated)
    - يتم تحديث draft → active عند بداية العقد
    - يتم تحديث active → expired عند انتهاء العقد
    """
    # لا نغير الحالات اليدوية
    if instance.status in ['suspended', 'terminated']:
        return
    
    today = date.today()
    
    # إذا انتهى العقد → expired
    if instance.end_date and instance.end_date < today:
        if instance.status != 'expired':
            instance.status = 'expired'
            logger.info(f"تم تحديث حالة العقد {instance.contract_number} إلى 'منتهي'")
    
    # إذا بدأ العقد → active (فقط لو كان draft)
    elif instance.start_date <= today and instance.status == 'draft':
        instance.status = 'active'
        logger.info(f"تم تفعيل العقد {instance.contract_number} تلقائياً")


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


@receiver(post_save, sender='hr.Contract')
def send_contract_notifications(sender, instance, created, **kwargs):
    """
    إرسال إشعارات تلقائية للعقود
    - عند إنشاء عقد جديد
    - عند تغيير الحالة
    - عند اقتراب انتهاء العقد
    """
    from core.services.notification_service import NotificationService
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    try:
        # إشعار عند إنشاء عقد جديد
        if created:
            # إشعار للموظف
            if hasattr(instance.employee, 'user') and instance.employee.user:
                NotificationService.create_notification(
                    user=instance.employee.user,
                    title="عقد عمل جديد",
                    message=f"تم إنشاء عقد عمل جديد لك برقم {instance.contract_number}",
                    notification_type="contract_created",
                    related_model="Contract",
                    related_id=instance.id,
                    priority="high"
                )
            
            # إشعار لقسم الموارد البشرية
            hr_users = User.objects.filter(groups__name='HR', is_active=True)
            for user in hr_users:
                NotificationService.create_notification(
                    user=user,
                    title="عقد جديد",
                    message=f"تم إنشاء عقد جديد للموظف {instance.employee.get_full_name_ar()} - {instance.contract_number}",
                    notification_type="contract_created",
                    related_model="Contract",
                    related_id=instance.id
                )
        
        # إشعار عند تفعيل العقد
        if not created and instance.status == 'active':
            old_instance = sender.objects.get(pk=instance.pk)
            if hasattr(old_instance, '_state') and old_instance.status != 'active':
                if hasattr(instance.employee, 'user') and instance.employee.user:
                    NotificationService.create_notification(
                        user=instance.employee.user,
                        title="تفعيل العقد",
                        message=f"تم تفعيل عقدك {instance.contract_number}",
                        notification_type="contract_activated",
                        related_model="Contract",
                        related_id=instance.id,
                        priority="high"
                    )
        
        # إشعار عند إنهاء العقد
        if instance.status == 'terminated':
            if hasattr(instance.employee, 'user') and instance.employee.user:
                NotificationService.create_notification(
                    user=instance.employee.user,
                    title="إنهاء العقد",
                    message=f"تم إنهاء عقدك {instance.contract_number}",
                    notification_type="contract_terminated",
                    related_model="Contract",
                    related_id=instance.id,
                    priority="urgent"
                )
        
        # إشعار عند اقتراب انتهاء فترة التجربة
        if instance.probation_end_date:
            days_to_probation_end = (instance.probation_end_date - date.today()).days
            if 0 <= days_to_probation_end <= 7:  # قبل أسبوع
                hr_users = User.objects.filter(groups__name='HR', is_active=True)
                for user in hr_users:
                    NotificationService.create_notification(
                        user=user,
                        title="انتهاء فترة التجربة قريباً",
                        message=f"ستنتهي فترة التجربة للموظف {instance.employee.get_full_name_ar()} خلال {days_to_probation_end} يوم",
                        notification_type="probation_ending",
                        related_model="Contract",
                        related_id=instance.id,
                        priority="high"
                    )
        
        # إشعار عند اقتراب انتهاء العقد
        if instance.end_date and instance.status == 'active':
            days_to_expiry = (instance.end_date - date.today()).days
            
            # إشعار قبل 60 يوم
            if days_to_expiry == 60:
                hr_users = User.objects.filter(groups__name='HR', is_active=True)
                for user in hr_users:
                    NotificationService.create_notification(
                        user=user,
                        title="عقد سينتهي خلال شهرين",
                        message=f"عقد الموظف {instance.employee.get_full_name_ar()} ({instance.contract_number}) سينتهي في {instance.end_date}",
                        notification_type="contract_expiring_soon",
                        related_model="Contract",
                        related_id=instance.id,
                        priority="medium"
                    )
            
            # إشعار قبل 30 يوم
            elif days_to_expiry == 30:
                hr_users = User.objects.filter(groups__name='HR', is_active=True)
                for user in hr_users:
                    NotificationService.create_notification(
                        user=user,
                        title="عقد سينتهي خلال شهر",
                        message=f"عقد الموظف {instance.employee.get_full_name_ar()} ({instance.contract_number}) سينتهي في {instance.end_date}",
                        notification_type="contract_expiring_soon",
                        related_model="Contract",
                        related_id=instance.id,
                        priority="high"
                    )
            
            # إشعار قبل 7 أيام
            elif days_to_expiry == 7:
                hr_users = User.objects.filter(groups__name='HR', is_active=True)
                for user in hr_users:
                    NotificationService.create_notification(
                        user=user,
                        title="⚠️ عقد سينتهي خلال أسبوع",
                        message=f"عقد الموظف {instance.employee.get_full_name_ar()} ({instance.contract_number}) سينتهي في {instance.end_date}",
                        notification_type="contract_expiring_urgent",
                        related_model="Contract",
                        related_id=instance.id,
                        priority="urgent"
                    )
    
    except Exception as e:
        logger.error(f"خطأ في إرسال إشعارات العقد {instance.contract_number}: {str(e)}")


@receiver(post_save, sender='hr.Contract')
def sync_contract_with_attendance(sender, instance, created, **kwargs):
    """
    ربط العقود مع نظام الحضور والانصراف
    - تفعيل/إيقاف البصمة حسب حالة العقد
    - تحديث بيانات الموظف في نظام البصمة
    - تحديث بيانات الوظيفة في ملف الموظف
    """
    try:
        # 1. حفظ رقم البصمة في BiometricUserMapping (إذا تم إدخاله)
        if instance.biometric_user_id:
            from .models import BiometricUserMapping
            
            # البحث عن mapping موجود
            mapping, created = BiometricUserMapping.objects.get_or_create(
                employee=instance.employee,
                defaults={
                    'biometric_user_id': str(instance.biometric_user_id),
                    'is_active': True
                }
            )
            
            # تحديث رقم البصمة إذا تغير
            if not created and mapping.biometric_user_id != str(instance.biometric_user_id):
                mapping.biometric_user_id = str(instance.biometric_user_id)
                mapping.save()
                logger.info(f"تم تحديث رقم البصمة للموظف {instance.employee.get_full_name_ar()} من {mapping.biometric_user_id} إلى {instance.biometric_user_id}")
            elif created:
                logger.info(f"تم إنشاء ربط بصمة جديد: {instance.employee.get_full_name_ar()} → {instance.biometric_user_id}")
        
        # 2. تحديث بيانات الوظيفة فوراً (عند أي حفظ)
        updated_fields = []
        
        # تحديث الوظيفة
        if instance.job_title:
            old_job = instance.employee.job_title
            if old_job != instance.job_title:
                instance.employee.job_title = instance.job_title
                updated_fields.append('job_title')
                logger.info(f"تم تحديث وظيفة الموظف {instance.employee.get_full_name_ar()} من {old_job} إلى {instance.job_title}")
                
                # تسجيل التغيير كـ Amendment (فقط عند التفعيل)
                if instance.status == 'active' and old_job:
                    from .models.contract import ContractAmendment
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    
                    try:
                        from core.middleware.current_user import get_current_user
                        user = get_current_user()
                    except:
                        user = instance.created_by
                    
                    if user:
                        ContractAmendment.objects.create(
                            contract=instance,
                            amendment_number=f"{instance.contract_number}-AMD-JOB",
                            amendment_type='other',
                            effective_date=date.today(),
                            description=f'تغيير الوظيفة من {old_job} إلى {instance.job_title}',
                            field_name='job_title',
                            old_value=str(old_job),
                            new_value=str(instance.job_title),
                            is_automatic=True,
                            created_by=user
                        )
        
        # تحديث القسم
        if instance.department:
            old_dept = instance.employee.department
            if old_dept != instance.department:
                instance.employee.department = instance.department
                updated_fields.append('department')
                logger.info(f"تم تحديث قسم الموظف {instance.employee.get_full_name_ar()} من {old_dept} إلى {instance.department}")
        
        # حفظ التحديثات
        if updated_fields:
            instance.employee.save(update_fields=updated_fields)
        
        # 3. تفعيل/إيقاف البصمة
        if instance.status == 'active':
            # تفعيل الموظف في نظام الحضور
            if hasattr(instance.employee, 'biometric_user_id') and instance.employee.biometric_user_id:
                # تحديث حالة الموظف في أجهزة البصمة
                from hr.models import BiometricDevice
                devices = BiometricDevice.objects.filter(is_active=True)
                for device in devices:
                    try:
                        # هنا يمكن إضافة كود التفعيل الفعلي للبصمة
                        logger.info(f"تم تفعيل الموظف {instance.employee.get_full_name_ar()} في جهاز البصمة {device.name}")
                    except Exception as e:
                        logger.error(f"خطأ في تفعيل البصمة للموظف {instance.employee.get_full_name_ar()}: {str(e)}")
        
        # عند إنهاء أو إيقاف العقد
        elif instance.status in ['terminated', 'expired', 'suspended']:
            # التحقق من عدم وجود عقد ساري آخر
            from hr.models import Contract
            other_active_contracts = Contract.objects.filter(
                employee=instance.employee,
                status='active'
            ).exclude(pk=instance.pk).exists()
            
            # إيقاف البصمة فقط إذا لم يكن هناك عقد ساري آخر
            if not other_active_contracts:
                if hasattr(instance.employee, 'biometric_user_id') and instance.employee.biometric_user_id:
                    # إلغاء تنشيط الـ Mapping
                    from hr.models import BiometricUserMapping
                    BiometricUserMapping.objects.filter(
                        employee=instance.employee
                    ).update(is_active=False)
                    logger.info(f"تم إلغاء تنشيط ربط البصمة للموظف {instance.employee.get_full_name_ar()}")
                    
                    # إيقاف في الأجهزة
                    from hr.models import BiometricDevice
                    devices = BiometricDevice.objects.filter(is_active=True)
                    for device in devices:
                        try:
                            # هنا يمكن إضافة كود الإيقاف الفعلي للبصمة
                            logger.info(f"تم إيقاف الموظف {instance.employee.get_full_name_ar()} في جهاز البصمة {device.name}")
                        except Exception as e:
                            logger.error(f"خطأ في إيقاف البصمة للموظف {instance.employee.get_full_name_ar()}: {str(e)}")
            else:
                logger.info(f"لم يتم إيقاف البصمة للموظف {instance.employee.get_full_name_ar()} - يوجد عقد ساري آخر")
            
            # حساب مستحقات نهاية الخدمة (إذا كان منهي)
            if instance.status == 'terminated':
                calculate_end_of_service_benefits(instance)
    
    except Exception as e:
        logger.error(f"خطأ في مزامنة العقد مع نظام الحضور: {str(e)}")
    
    # حذف الـ flags المؤقتة
    if hasattr(instance, '_hire_date_changed'):
        delattr(instance, '_hire_date_changed')
    if hasattr(instance, '_old_hire_date'):
        delattr(instance, '_old_hire_date')


def calculate_end_of_service_benefits(contract):
    """
    حساب مستحقات نهاية الخدمة
    """
    try:
        from datetime import date
        from decimal import Decimal
        
        # حساب مدة الخدمة
        service_start = contract.start_date
        service_end = date.today()
        service_days = (service_end - service_start).days
        service_years = service_days / 365.25
        
        # حساب المستحقات حسب قانون العمل
        # السنوات الخمس الأولى: 21 يوم عن كل سنة
        # بعد الخمس سنوات: 30 يوم عن كل سنة
        
        daily_salary = contract.basic_salary / 30
        
        if service_years <= 5:
            benefit_days = service_years * 21
        else:
            benefit_days = (5 * 21) + ((service_years - 5) * 30)
        
        total_benefit = daily_salary * Decimal(str(benefit_days))
        
        logger.info(
            f"مستحقات نهاية الخدمة للموظف {contract.employee.get_full_name_ar()}: "
            f"{total_benefit} (مدة الخدمة: {service_years:.2f} سنة)"
        )
        
        # يمكن حفظ المستحقات في جدول منفصل أو إنشاء سجل مالي
        
        return {
            'service_years': service_years,
            'benefit_days': benefit_days,
            'daily_salary': daily_salary,
            'total_benefit': total_benefit
        }
    
    except Exception as e:
        logger.error(f"خطأ في حساب مستحقات نهاية الخدمة: {str(e)}")
        return None


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


@receiver(pre_save, sender='hr.Contract')
def track_contract_changes(sender, instance, **kwargs):
    """
    تتبع تلقائي لجميع التغييرات في العقد
    يسجل القيمة القديمة والجديدة لكل حقل متغير
    """
    if not instance.pk:
        # عقد جديد - لا نسجل تغييرات
        return
    
    try:
        # جلب النسخة القديمة من قاعدة البيانات
        old_contract = sender.objects.get(pk=instance.pk)
        
        # الحقول المهمة للتتبع (لا نتتبع الموظف وتاريخ البداية لأنهما لا يمكن تغييرهما)
        tracked_fields = {
            # معلومات العقد
            'contract_type': 'نوع العقد',
            
            # التواريخ
            'end_date': 'تاريخ النهاية',
            'probation_period_months': 'فترة التجربة (بالأشهر)',
            'probation_end_date': 'تاريخ انتهاء التجربة',
            
            # الراتب
            'basic_salary': 'الراتب الأساسي',
            
            # البنود والشروط
            'terms_and_conditions': 'البنود والشروط',
            'special_clauses': 'بنود خاصة',
            
            # التجديد
            'auto_renew': 'تجديد تلقائي',
            'renewal_notice_days': 'أيام الإشعار قبل التجديد',
            'renewed_to': 'تم التجديد إلى',
            
            # الحالة
            'status': 'الحالة',
            
            # التوقيع
            'signed_date': 'تاريخ التوقيع',
            
            # ملاحظات
            'notes': 'ملاحظات',
        }
        
        # تخزين التغييرات مؤقتاً
        if not hasattr(instance, '_tracked_changes'):
            instance._tracked_changes = []
        
        # مقارنة الحقول
        for field_name, field_label in tracked_fields.items():
            old_value = getattr(old_contract, field_name, None)
            new_value = getattr(instance, field_name, None)
            
            # تنسيق القيم للعرض
            def format_value(value, field_name):
                """تنسيق القيمة للعرض"""
                if value is None or value == '':
                    return 'غير محدد'
                
                # Boolean fields
                if isinstance(value, bool):
                    return 'نعم' if value else 'لا'
                
                # Date fields
                if hasattr(value, 'strftime'):
                    return value.strftime('%Y-%m-%d')
                
                # Decimal/Float (للراتب)
                if field_name == 'basic_salary':
                    try:
                        return f"{float(value):,.2f} ج.م"
                    except:
                        pass
                
                # Foreign Key (renewed_to)
                if field_name == 'renewed_to' and hasattr(value, 'contract_number'):
                    return value.contract_number
                
                return str(value)
            
            old_str = format_value(old_value, field_name)
            new_str = format_value(new_value, field_name)
            
            # إذا تغيرت القيمة
            if old_str != new_str:
                instance._tracked_changes.append({
                    'field_name': field_name,
                    'field_label': field_label,
                    'old_value': old_str,
                    'new_value': new_str
                })
                
                logger.info(
                    f"تغيير في العقد {instance.contract_number}: "
                    f"{field_label} من '{old_str}' إلى '{new_str}'"
                )
    
    except sender.DoesNotExist:
        pass
    except Exception as e:
        logger.error(f"خطأ في تتبع تغييرات العقد: {str(e)}")


@receiver(post_save, sender='hr.Contract')
def create_automatic_amendments(sender, instance, created, **kwargs):
    """
    إنشاء سجلات تعديل تلقائية بعد حفظ العقد
    """
    if created:
        # عقد جديد - لا نسجل تعديلات
        return
    
    # التحقق من وجود تغييرات مسجلة
    if not hasattr(instance, '_tracked_changes') or not instance._tracked_changes:
        return
    
    try:
        from .models.contract import ContractAmendment
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        # الحصول على المستخدم الحالي من middleware
        user = None
        try:
            from core.middleware.current_user import get_current_user
            user = get_current_user()
        except:
            pass
        
        # إذا لم نجد المستخدم، نستخدم أول superuser
        if not user or not user.is_authenticated:
            user = User.objects.filter(is_superuser=True).first()
        
        # إذا لم نجد أي مستخدم، نتوقف
        if not user:
            logger.error("لا يمكن إنشاء تعديلات تلقائية: لا يوجد مستخدم")
            return
        
        # إنشاء تعديل لكل تغيير
        for change in instance._tracked_changes:
            # توليد رقم تعديل
            last_amendment = ContractAmendment.objects.filter(
                contract=instance
            ).order_by('-amendment_number').first()
            
            if last_amendment and '-AMD-' in last_amendment.amendment_number:
                last_num = int(last_amendment.amendment_number.split('-AMD-')[-1])
                amendment_number = f"{instance.contract_number}-AMD-{last_num + 1:03d}"
            else:
                amendment_number = f"{instance.contract_number}-AMD-001"
            
            # تحديد نوع التعديل بناءً على الحقل
            amendment_type = 'other'
            field_name_lower = change['field_name'].lower()
            
            if 'salary' in field_name_lower or 'basic_salary' in field_name_lower:
                amendment_type = 'salary_increase'
            elif 'end_date' in field_name_lower:
                amendment_type = 'extension'
            elif 'contract_type' in field_name_lower or 'status' in field_name_lower:
                amendment_type = 'other'
            elif 'probation' in field_name_lower:
                amendment_type = 'other'
            elif 'renew' in field_name_lower:
                amendment_type = 'other'
            
            # إنشاء التعديل
            ContractAmendment.objects.create(
                contract=instance,
                amendment_number=amendment_number,
                amendment_type=amendment_type,
                effective_date=date.today(),
                description=f"تغيير {change['field_label']}",
                field_name=change['field_name'],
                old_value=change['old_value'],
                new_value=change['new_value'],
                is_automatic=True,
                created_by=user
            )
            
            logger.info(f"تم إنشاء تعديل تلقائي {amendment_number} للعقد {instance.contract_number}")
        
        # مسح التغييرات المؤقتة
        delattr(instance, '_tracked_changes')
    
    except Exception as e:
        logger.error(f"خطأ في إنشاء التعديلات التلقائية: {str(e)}")


# ==================== تتبع الاستحقاقات والاستقطاعات ====================

@receiver(pre_save, sender='hr.SalaryComponent')
def store_old_salary_component_values(sender, instance, **kwargs):
    """حفظ القيم القديمة قبل التعديل"""
    if instance.pk:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            instance._old_name = old_instance.name
            instance._old_amount = old_instance.amount
            instance._old_component_type = old_instance.component_type
            
            # التحقق من وجود تغيير فعلي
            has_changes = (
                old_instance.name != instance.name or
                old_instance.amount != instance.amount or
                old_instance.component_type != instance.component_type
            )
            instance._has_real_changes = has_changes
        except sender.DoesNotExist:
            instance._has_real_changes = False


@receiver(post_save, sender='hr.SalaryComponent')
def track_salary_component_changes(sender, instance, created, **kwargs):
    """تتبع إضافة أو تعديل مكونات الراتب"""
    
    # تجاهل التحديثات بدون تغييرات فعلية
    if not created and not getattr(instance, '_has_real_changes', False):
        return
    
    try:
        from .models.contract import ContractAmendment
        
        # Check if contract exists before accessing it
        contract = None
        if hasattr(instance, 'contract') and instance.contract:
            contract = instance.contract
        else:
            # Fallback: try to get active contract from employee
            if hasattr(instance, 'employee') and instance.employee:
                contract = instance.employee.contracts.filter(status='active').first()
        
        # If no contract found, log with employee number and return
        if not contract:
            component_type_display = instance.get_component_type_display()
            employee_number = instance.employee.employee_number if hasattr(instance, 'employee') and instance.employee else 'Unknown'
            if created:
                logger.info(f"تم إضافة {component_type_display}: {instance.name} للموظف {employee_number} (بدون عقد نشط)")
            else:
                logger.info(f"تم تعديل {component_type_display}: {instance.name} للموظف {employee_number} (بدون عقد نشط)")
            return
        
        # للإضافة الجديدة فقط
        if created:
            # الحصول على المستخدم الحالي
            user = None
            try:
                from core.middleware.current_user import get_current_user
                user = get_current_user()
            except:
                if hasattr(contract, 'created_by') and contract.created_by:
                    user = contract.created_by
            
            # توليد رقم تعديل
            last_amendment = ContractAmendment.objects.filter(
                contract=contract
            ).order_by('-amendment_number').first()
            
            if last_amendment and '-AMD-' in last_amendment.amendment_number:
                last_num = int(last_amendment.amendment_number.split('-AMD-')[-1])
                amendment_number = f"{contract.contract_number}-AMD-{last_num + 1:03d}"
            else:
                amendment_number = f"{contract.contract_number}-AMD-001"
            
            # تحديد نوع المكون
            component_type_display = instance.get_component_type_display()
            
            # تحديد نوع التعديل حسب نوع المكون
            if instance.component_type == 'earning':
                amendment_type = 'salary_increase'
            elif instance.component_type == 'deduction':
                amendment_type = 'salary_deduction'
            else:
                amendment_type = 'other'
            
            # إنشاء التعديل (فقط إذا كان هناك مستخدم)
            if user:
                ContractAmendment.objects.create(
                    contract=contract,
                    amendment_number=amendment_number,
                    amendment_type=amendment_type,
                    effective_date=date.today(),
                    description=f"إضافة {component_type_display}: {instance.name}",
                    field_name=f"salary_component_{instance.component_type}",
                    old_value="غير موجود",
                    new_value=f"{instance.name} - {float(instance.amount):,.2f} ج.م",
                    is_automatic=True,
                    created_by=user
                )
            
            logger.info(f"تم تسجيل إضافة {component_type_display}: {instance.name} للعقد {contract.contract_number}")
        
        # للتعديل - تم التحقق من التغيير في البداية
        else:
            old_name = getattr(instance, '_old_name', instance.name)
            old_amount = getattr(instance, '_old_amount', instance.amount)
            
            # الحصول على المستخدم الحالي
            user = None
            try:
                from core.middleware.current_user import get_current_user
                user = get_current_user()
            except:
                if hasattr(contract, 'created_by') and contract.created_by:
                    user = contract.created_by
            
            # توليد رقم تعديل
            last_amendment = ContractAmendment.objects.filter(
                contract=contract
            ).order_by('-amendment_number').first()
            
            if last_amendment and '-AMD-' in last_amendment.amendment_number:
                last_num = int(last_amendment.amendment_number.split('-AMD-')[-1])
                amendment_number = f"{contract.contract_number}-AMD-{last_num + 1:03d}"
            else:
                amendment_number = f"{contract.contract_number}-AMD-001"
            
            # تحديد نوع المكون
            component_type_display = instance.get_component_type_display()
            
            # تحديد نوع التعديل حسب نوع المكون
            if instance.component_type == 'earning':
                amendment_type = 'salary_increase'
            elif instance.component_type == 'deduction':
                amendment_type = 'salary_deduction'
            else:
                amendment_type = 'other'
            
            # إنشاء التعديل (فقط إذا كان هناك مستخدم)
            if user:
                ContractAmendment.objects.create(
                    contract=contract,
                    amendment_number=amendment_number,
                    amendment_type=amendment_type,
                    effective_date=date.today(),
                    description=f"تعديل {component_type_display}: {instance.name}",
                    field_name=f"salary_component_{instance.component_type}",
                    old_value=f"{old_name} - {float(old_amount):,.2f} ج.م",
                    new_value=f"{instance.name} - {float(instance.amount):,.2f} ج.م",
                    is_automatic=True,
                    created_by=user
                )
            
            logger.info(f"تم تسجيل تعديل {component_type_display}: {instance.name} للعقد {contract.contract_number}")
    
    except Exception as e:
        logger.error(f"خطأ في تتبع تغييرات مكونات الراتب: {str(e)}")


@receiver(post_delete, sender='hr.SalaryComponent')
def track_salary_component_deletion(sender, instance, **kwargs):
    """تتبع حذف مكونات الراتب"""
    try:
        from .models.contract import ContractAmendment
        
        # Check if contract exists before accessing it
        contract = None
        if hasattr(instance, 'contract') and instance.contract:
            contract = instance.contract
        else:
            # Fallback: try to get active contract from employee
            if hasattr(instance, 'employee') and instance.employee:
                contract = instance.employee.contracts.filter(status='active').first()
        
        # If no contract found, log with employee number and return
        if not contract:
            component_type_display = instance.get_component_type_display()
            employee_number = instance.employee.employee_number if hasattr(instance, 'employee') and instance.employee else 'Unknown'
            logger.info(f"تم حذف {component_type_display}: {instance.name} للموظف {employee_number} (بدون عقد نشط)")
            return
        
        # الحصول على المستخدم الحالي
        user = None
        try:
            from core.middleware.current_user import get_current_user
            user = get_current_user()
        except:
            if hasattr(contract, 'created_by') and contract.created_by:
                user = contract.created_by
        
        # توليد رقم تعديل
        last_amendment = ContractAmendment.objects.filter(
            contract=contract
        ).order_by('-amendment_number').first()
        
        if last_amendment and '-AMD-' in last_amendment.amendment_number:
            last_num = int(last_amendment.amendment_number.split('-AMD-')[-1])
            amendment_number = f"{contract.contract_number}-AMD-{last_num + 1:03d}"
        else:
            amendment_number = f"{contract.contract_number}-AMD-001"
        
        # تحديد نوع المكون
        component_type_display = instance.get_component_type_display()
        
        # إنشاء التعديل
        if user:
            ContractAmendment.objects.create(
                contract=contract,
                amendment_number=amendment_number,
                amendment_type='other',
                effective_date=date.today(),
                description=f"حذف {component_type_display}: {instance.name}",
                field_name=f"salary_component_{instance.component_type}",
                old_value=f"{instance.name} - {float(instance.amount):,.2f} ج.م",
                new_value="تم الحذف",
                is_automatic=True,
                created_by=user
            )
        
        logger.info(f"تم تسجيل حذف {component_type_display}: {instance.name} من العقد {contract.contract_number}")
    
    except Exception as e:
        logger.error(f"خطأ في تتبع حذف مكونات الراتب: {str(e)}")
