"""
✅ FIXED: Daily caching + No circular dependencies
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from django.core.cache import cache
from django.db.models import Count, Sum, Q
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


class PermissionQuotaService:
    CACHE_TIMEOUT = 300  # 5 minutes
    
    @staticmethod
    def get_limits_for_date(target_date: date) -> dict:
        """
        ✅ FIXED: Cache per day (not per month)
        """
        cache_key = f'permission_limits_{target_date.isoformat()}'
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        from hr.models.attendance import RamadanSettings
        from core.models import SystemSetting
        
        ramadan = RamadanSettings.objects.filter(
            start_date__lte=target_date,
            end_date__gte=target_date
        ).first()
        
        if ramadan:
            limits = {
                'max_count': ramadan.permission_max_count,
                'max_hours': Decimal(str(ramadan.permission_max_hours)),
                'is_ramadan': True,
                'source': 'ramadan'
            }
        else:
            limits = {
                'max_count': int(SystemSetting.get_setting('hr_permission_max_count_monthly', 2)),
                'max_hours': Decimal(str(SystemSetting.get_setting('hr_permission_max_hours_monthly', '2'))),
                'is_ramadan': False,
                'source': 'system'
            }
        
        cache.set(cache_key, limits, PermissionQuotaService.CACHE_TIMEOUT)
        return limits
    
    @staticmethod
    def get_monthly_quota_info(employee, target_date: date) -> dict:
        """
        الحصول على معلومات حصة الموظف الشهرية مع الأخذ في الاعتبار إعدادات رمضان.
        """
        from core.models import SystemSetting
        from hr.models.attendance import RamadanSettings
        
        # Check if the date is in Ramadan
        ramadan = RamadanSettings.objects.filter(
            start_date__lte=target_date,
            end_date__gte=target_date
        ).first()
        
        usage = PermissionQuotaService.get_monthly_usage(employee, target_date)
        
        if ramadan:
            max_count = ramadan.permission_max_count
            max_hours = float(ramadan.permission_max_hours)
            is_ramadan = True
        else:
            max_count = int(SystemSetting.get_setting('hr_permission_max_count_monthly', 2))
            max_hours = float(SystemSetting.get_setting('hr_permission_max_hours_monthly', 2))
            is_ramadan = False
            
        used_count = usage['total_count']
        used_hours = float(usage['total_hours'])
        
        return {
            'used_count': used_count,
            'max_count': max_count,
            'remaining_count': max(0, max_count - used_count),
            'used_hours': used_hours,
            'max_hours': max_hours,
            'remaining_hours': max(0, max_hours - used_hours),
            'is_ramadan': is_ramadan
        }
    @staticmethod
    def get_monthly_usage(employee, target_date: date, exclude_permission_id=None) -> dict:
        """
        ✅ FIXED: استخدام apps.get_model لتجنب circular import
        الفلترة بالفترة الفعلية للدورة بدل الشهر الميلادي.
        """
        from django.apps import apps
        from hr.utils.payroll_helpers import get_payroll_period, get_payroll_month_for_date
        PermissionRequest = apps.get_model('hr', 'PermissionRequest')

        # تحديد الشهر الأساسي للدورة ثم حساب الفترة
        payroll_month = get_payroll_month_for_date(target_date)
        period_start, period_end, _ = get_payroll_period(payroll_month)

        base_query = Q(
            employee=employee,
            date__gte=period_start,
            date__lte=period_end,
            status='approved'
        )
        
        if exclude_permission_id:
            base_query &= ~Q(id=exclude_permission_id)
        
        normal_result = PermissionRequest.objects.filter(
            base_query, is_extra=False
        ).aggregate(
            total_count=Count('id'),
            total_hours=Sum('duration_hours')
        )
        
        extra_result = PermissionRequest.objects.filter(
            base_query, is_extra=True
        ).aggregate(
            extra_count=Count('id'),
            extra_hours=Sum('duration_hours')
        )
        
        return {
            'total_count': normal_result['total_count'] or 0,
            'total_hours': normal_result['total_hours'] or Decimal('0'),
            'extra_count': extra_result['extra_count'] or 0,
            'extra_hours': extra_result['extra_hours'] or Decimal('0')
        }
    
    @staticmethod
    def check_can_request(employee, target_date: date, duration_hours: Decimal, 
                         is_extra: bool = False, exclude_permission_id=None) -> tuple:
        """
        التحقق من إمكانية طلب إذن
        Returns: (can_request: bool, error_message: str or None, details: dict)
        """
        if is_extra:
            return True, None, {'type': 'extra', 'unlimited': True}
        
        limits = PermissionQuotaService.get_limits_for_date(target_date)
        usage = PermissionQuotaService.get_monthly_usage(employee, target_date, exclude_permission_id)
        
        if usage['total_count'] >= limits['max_count']:
            return False, f"تجاوزت الحد الأقصى ({limits['max_count']} أذونات)", {}
        
        total_hours = float(usage['total_hours']) + float(duration_hours)
        if total_hours > float(limits['max_hours']):
            remaining = float(limits['max_hours']) - float(usage['total_hours'])
            return False, f"تجاوزت الحد الأقصى ({limits['max_hours']} ساعة). المتبقي: {remaining}", {}
        
        return True, None, {
            'remaining_count': limits['max_count'] - usage['total_count'] - 1,
            'remaining_hours': float(limits['max_hours']) - total_hours
        }
    
    @staticmethod
    @transaction.atomic
    def create_permission_request(employee_id: int, permission_data: dict) -> tuple:
        """
        ✅ NEW: إنشاء إذن بشكل آمن مع row-level locking
        Returns: (success: bool, permission or error_message)
        """
        from django.apps import apps
        from django.core.exceptions import ValidationError
        
        Employee = apps.get_model('hr', 'Employee')
        PermissionRequest = apps.get_model('hr', 'PermissionRequest')
        
        try:
            # ✅ CRITICAL: Lock employee row
            employee = Employee.objects.select_for_update().get(pk=employee_id)
            
            # Re-check quota inside transaction
            can_request, error_msg, _ = PermissionQuotaService.check_can_request(
                employee=employee,
                target_date=permission_data['date'],
                duration_hours=permission_data['duration_hours'],
                is_extra=permission_data.get('is_extra', False)
            )
            
            if not can_request:
                return False, error_msg
            
            permission = PermissionRequest.objects.create(employee=employee, **permission_data)
            logger.info(f"✅ Permission created: {employee.get_full_name_ar()} - {permission.date}")
            
            return True, permission
            
        except Employee.DoesNotExist:
            return False, "الموظف غير موجود"
        except Exception as e:
            logger.error(f"❌ Error creating permission: {e}", exc_info=True)
            return False, str(e)
    
    @staticmethod
    def calculate_extra_permission_deduction(employee, month: date, 
                                            basic_salary: Decimal, 
                                            worked_days: int) -> dict:
        """
        حساب خصم الأذونات الإضافية بنفس معادلة ملخص الحضور:
        hourly_rate = (basic_salary / 30) / shift_hours  — مع دعم رمضان لكل إذن
        """
        from django.apps import apps
        from hr.utils.payroll_helpers import get_payroll_period
        
        PermissionRequest = apps.get_model('hr', 'PermissionRequest')
        RamadanSettings = apps.get_model('hr', 'RamadanSettings')

        period_start, period_end, _ = get_payroll_period(month)

        extra_permissions = PermissionRequest.objects.filter(
            employee=employee,
            date__gte=period_start,
            date__lte=period_end,
            is_extra=True,
            status='approved',
            is_deduction_exempt=False
        ).select_related('employee__shift')
        
        if not extra_permissions.exists():
            return {'total_deduction': Decimal('0'), 'permissions': []}

        # الراتب اليومي الثابت (÷30) — نفس معادلة ملخص الحضور
        daily_salary = (basic_salary / Decimal('30')).quantize(Decimal('0.01'), ROUND_HALF_UP)

        total_deduction = Decimal('0')
        permissions_details = []
        last_hourly_rate = Decimal('0')

        for perm in extra_permissions:
            if not (perm.deduction_hours and perm.deduction_hours > 0):
                continue

            # تحديد ساعات الوردية مع دعم رمضان
            shift = employee.shift if hasattr(employee, 'shift') else None
            is_ramadan_day = RamadanSettings.objects.filter(
                start_date__lte=perm.date,
                end_date__gte=perm.date
            ).exists()

            if shift:
                if is_ramadan_day and shift.ramadan_start_time and shift.ramadan_end_time:
                    shift_hours = Decimal(str(shift.calculate_ramadan_work_hours()))
                else:
                    shift_hours = Decimal(str(shift.calculate_work_hours()))
                if shift_hours <= Decimal('0'):
                    shift_hours = Decimal('8')
            else:
                shift_hours = Decimal('8')

            hourly_rate = (daily_salary / shift_hours).quantize(Decimal('0.01'), ROUND_HALF_UP)
            last_hourly_rate = hourly_rate

            deduction = (hourly_rate * Decimal(str(perm.deduction_hours))).quantize(
                Decimal('0.01'), ROUND_HALF_UP
            )
            total_deduction += deduction
            permissions_details.append({
                'id': perm.id,
                'date': perm.date,
                'hours': perm.deduction_hours,
                'amount': deduction
            })
        
        return {
            'total_deduction': total_deduction.quantize(Decimal('0.01'), ROUND_HALF_UP),
            'permissions': permissions_details,
            'hourly_rate': last_hourly_rate,
            'worked_days': worked_days
        }
