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
from governance.signal_integration import governed_signal_handler
from datetime import date
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

@governed_signal_handler(
    signal_name="auto_update_contract_status",
    critical=True,
    description="تحديث حالة العقد تلقائياً"
)
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
    
    # إذا بدأ العقد → active (فقط لو كان draft)
    elif instance.start_date <= today and instance.status == 'draft':
        # لا نغير الحالة لو تم تعيين _keep_draft صراحةً (مثل الاستيراد الجماعي)
        if not getattr(instance, '_keep_draft', False):
            instance.status = 'active'


@governed_signal_handler(
    signal_name="track_contract_status_change",
    critical=True,
    description="تتبع تغيير حالة العقد قبل الحفظ"
)
@receiver(pre_save, sender='hr.Contract')
def track_contract_status_change(sender, instance, **kwargs):
    """
    حفظ الحالة القديمة للعقد قبل الحفظ
    يُستخدم لاكتشاف التحول إلى active في post_save
    """
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._old_status = old.status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@governed_signal_handler(
    signal_name="copy_salary_components_on_activation",
    critical=True,
    description="نسخ بنود الراتب من العقد للموظف عند التفعيل"
)
@receiver(post_save, sender='hr.Contract')
def copy_salary_components_on_activation(sender, instance, created, **kwargs):
    """
    نسخ بنود الراتب (ContractSalaryComponent) إلى بنود الموظف (SalaryComponent)
    عند تفعيل العقد - سواء يدوياً أو تلقائياً عبر pre_save signal
    """
    # نتحقق إن العقد أصبح active الآن
    if instance.status != 'active':
        return

    old_status = getattr(instance, '_old_status', None)

    # لو كان active قبل كده (مش تغيير جديد) ومش عقد جديد، نتجاهل
    # إلا لو العقد جديد وحالته active من الأول
    if not created and old_status == 'active':
        return

    # لو الـ view بيتعامل مع النسخ بنفسه (save_activate)، نتجنب التكرار
    # نتحقق من flag مؤقت يضعه الـ view
    if getattr(instance, '_components_copied_by_view', False):
        return

    try:
        with transaction.atomic():
            from .models.contract_salary_component import ContractSalaryComponent
            from .models.salary_component import SalaryComponent

            contract_components = ContractSalaryComponent.objects.filter(
                contract=instance
            ).order_by('order')

            if not contract_components.exists():
                return

            employee = instance.employee
            employee_components = SalaryComponent.objects.filter(
                employee=employee,
                is_active=True
            )

            copied_count = 0
            for contract_comp in contract_components:
                # البحث عن بند مطابق عند الموظف
                existing = employee_components.filter(
                    source_contract_component=contract_comp,
                    is_from_contract=True
                ).first()

                if not existing:
                    # البند مش موجود - انسخه
                    new_comp = contract_comp.copy_to_employee_component(employee)
                    if new_comp:
                        copied_count += 1

            if copied_count > 0:
                logger.info(
                    f"تم نسخ {copied_count} بند راتب للموظف "
                    f"{employee.get_full_name_ar()} من العقد {instance.contract_number}"
                )

    except Exception as e:
        logger.error(
            f"خطأ في نسخ بنود الراتب للعقد {instance.contract_number}: {str(e)}"
        )


@governed_signal_handler(
    signal_name="track_hire_date_change",
    critical=True,
    description="تتبع تغيير تاريخ التعيين"
)
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
                
        except sender.DoesNotExist:
            pass


from governance.signal_integration import governed_signal_handler

@governed_signal_handler(
    signal_name="hr_employee_leave_accrual_update",
    description="تحديث أرصدة الإجازات عند تغيير تاريخ التعيين أو إضافة موظف جديد",
    critical=True
)
@receiver(post_save, sender='hr.Employee')
def update_leave_accrual_on_hire_date_change(sender, instance, created, **kwargs):
    """
    تحديث أرصدة الإجازات تلقائياً عند:
    1. تغيير تاريخ التعيين (يدوياً)
    2. إضافة موظف جديد بتاريخ قديم
    
    FIX #18: Respect probation period before creating leave balances
    
    يحدث الأرصدة بناءً على مدة الخدمة الجديدة
    """
    from .services.leave_accrual_service import LeaveAccrualService
    from .models import LeaveBalance
    from django.utils import timezone
    
    # Check if employee is in probation period
    active_contract = instance.get_active_contract()
    if active_contract and active_contract.probation_end_date:
        today = timezone.now().date()
        if today < active_contract.probation_end_date:
            # TODO: Schedule task for probation end date
            return
    
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
                        return

                    # إنشاء أرصدة جديدة — single source of truth
                    from .models import LeaveType
                    leave_types = LeaveType.objects.filter(is_active=True, category__in=['annual', 'emergency'])

                    if leave_types.exists():
                        for leave_type in leave_types:
                            total_days = LeaveAccrualService.get_entitlement_for_employee(
                                instance, leave_type
                            )
                            LeaveBalance.objects.create(
                                employee=instance,
                                leave_type=leave_type,
                                year=current_year,
                                total_days=total_days,
                                accrued_days=total_days,
                                used_days=0,
                                remaining_days=total_days,
                                accrual_start_date=instance.hire_date,
                                last_accrual_date=date.today()
                            )

                else:
                    # تحديث الأرصدة الموجودة
                    LeaveAccrualService.update_employee_accrual(instance, current_year)

                    # تحديث accrual_start_date في جميع الأرصدة
                    LeaveBalance.objects.filter(
                        employee=instance,
                        year=current_year
                    ).update(accrual_start_date=instance.hire_date)
                    
                
        except Exception as e:
            logger.error(
                f"خطأ في تحديث أرصدة الإجازات للموظف {instance.get_full_name_ar()}: {str(e)}"
            )
    
    # حذف الـ flags المؤقتة
    if hasattr(instance, '_hire_date_changed'):
        delattr(instance, '_hire_date_changed')
    if hasattr(instance, '_old_hire_date'):
        delattr(instance, '_old_hire_date')


@governed_signal_handler(
    signal_name="hr_contract_notifications",
    critical=False,
    description="إرسال إشعارات تلقائية للعقود عند الإنشاء أو تغيير الحالة"
)
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


@governed_signal_handler(
    signal_name="hr_contract_attendance_sync",
    critical=True,
    description="ربط العقود مع نظام الحضور والانصراف"
)
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
            elif created:
                pass
        
        # 2. تحديث بيانات الوظيفة فوراً (عند أي حفظ)
        updated_fields = []
        
        # تحديث الوظيفة
        if instance.job_title:
            old_job = instance.employee.job_title
            if old_job != instance.job_title:
                instance.employee.job_title = instance.job_title
                updated_fields.append('job_title')
                
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
                        pass
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
                    
                    # إيقاف في الأجهزة
                    from hr.models import BiometricDevice
                    devices = BiometricDevice.objects.filter(is_active=True)
                    for device in devices:
                        try:
                            pass
                        except Exception as e:
                            logger.error(f"خطأ في إيقاف البصمة للموظف {instance.employee.get_full_name_ar()}: {str(e)}")
            else:
                pass
            
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


@governed_signal_handler(
    signal_name="hr_leave_balance_auto_update",
    critical=True,
    description="تحديث الأيام المتبقية تلقائياً عند تغيير رصيد الإجازات"
)
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


@governed_signal_handler(
    signal_name="track_contract_changes",
    critical=True,
    description="تتبع تغييرات العقد"
)
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
            'basic_salary': 'الأجر الأساسي',
            
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
                
    
    except sender.DoesNotExist:
        pass
    except Exception as e:
        logger.error(f"خطأ في تتبع تغييرات العقد: {str(e)}")


@governed_signal_handler(
    signal_name="hr_contract_automatic_amendments",
    critical=False,
    description="إنشاء تعديلات تلقائية للعقود عند الحاجة"
)
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
            
        
        # مسح التغييرات المؤقتة
        delattr(instance, '_tracked_changes')
    
    except Exception as e:
        logger.error(f"خطأ في إنشاء التعديلات التلقائية: {str(e)}")


# ==================== تتبع الاستحقاقات والاستقطاعات ====================

@governed_signal_handler(
    signal_name="store_old_salary_component_values",
    critical=False,
    description="حفظ القيم القديمة قبل التعديل"
)
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


@governed_signal_handler(
    signal_name="hr_salary_component_tracking",
    critical=False,
    description="تتبع إضافة أو تعديل مكونات الراتب"
)
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
                logger.warning(f"No active contract found for employee {employee_number} when creating {component_type_display}")
            else:
                logger.warning(f"No active contract found for employee {employee_number} when updating {component_type_display}")
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
            
    
    except Exception as e:
        logger.error(f"خطأ في تتبع تغييرات مكونات الراتب: {str(e)}")


@governed_signal_handler(
    signal_name="track_salary_component_deletion",
    critical=True,
    description="تتبع حذف مكونات الراتب"
)
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
        
    
    except Exception as e:
        logger.error(f"خطأ في تتبع حذف مكونات الراتب: {str(e)}")
