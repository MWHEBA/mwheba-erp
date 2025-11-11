"""
خدمة إدارة قوالب مكونات الراتب
"""
from django.db import transaction
from hr.models import SalaryComponentTemplate, SalaryComponent, Employee
import logging


class TemplateService:
    """خدمة إدارة قوالب مكونات الراتب"""
    
    @staticmethod
    def get_available_templates(component_type=None):
        """
        الحصول على القوالب المتاحة
        
        Args:
            component_type: نوع المكون ('earning' أو 'deduction') أو None للكل
            
        Returns:
            QuerySet: قائمة القوالب المتاحة
        """
        templates = SalaryComponentTemplate.objects.filter(is_active=True)
        
        if component_type:
            templates = templates.filter(component_type=component_type)
            
        return templates.order_by('component_type', 'order', 'name')
    
    @staticmethod
    def apply_template_to_employee(template_code, employee_id, custom_amount=None):
        """
        تطبيق قالب على موظف معين
        
        Args:
            template_code: كود القالب
            employee_id: معرف الموظف
            custom_amount: مبلغ مخصص (اختياري)
            
        Returns:
            tuple: (SalaryComponent, created)
        """
        logger = logging.getLogger(__name__)
        
        try:
            template = SalaryComponentTemplate.objects.get(
                code=template_code,
                is_active=True
            )
            employee = Employee.objects.get(id=employee_id)
            
            # تطبيق القالب
            component = template.apply_to_employee(employee)
            
            # تطبيق المبلغ المخصص إذا تم تحديده
            if custom_amount is not None:
                component.amount = custom_amount
                component.save()
            
            logger.info(f"تم تطبيق قالب {template.name} على الموظف {employee.get_full_name_ar()}")
            
            return component, True
            
        except SalaryComponentTemplate.DoesNotExist:
            logger.error(f"القالب {template_code} غير موجود")
            return None, False
        except Employee.DoesNotExist:
            logger.error(f"الموظف {employee_id} غير موجود")
            return None, False
        except Exception as e:
            logger.error(f"خطأ في تطبيق القالب: {str(e)}")
            return None, False
    
    @staticmethod
    @transaction.atomic
    def apply_multiple_templates(template_codes, employee_id):
        """
        تطبيق عدة قوالب على موظف واحد
        
        Args:
            template_codes: قائمة أكواد القوالب
            employee_id: معرف الموظف
            
        Returns:
            dict: نتائج التطبيق
        """
        results = {
            'success': [],
            'failed': [],
            'total': len(template_codes)
        }
        
        for template_code in template_codes:
            component, created = TemplateService.apply_template_to_employee(
                template_code, employee_id
            )
            
            if component:
                results['success'].append({
                    'template_code': template_code,
                    'component_name': component.name,
                    'created': created
                })
            else:
                results['failed'].append(template_code)
        
        return results
    
    @staticmethod
    @transaction.atomic
    def apply_template_to_multiple_employees(template_code, employee_ids):
        """
        تطبيق قالب واحد على عدة موظفين
        
        Args:
            template_code: كود القالب
            employee_ids: قائمة معرفات الموظفين
            
        Returns:
            dict: نتائج التطبيق
        """
        results = {
            'success': [],
            'failed': [],
            'total': len(employee_ids)
        }
        
        for employee_id in employee_ids:
            component, created = TemplateService.apply_template_to_employee(
                template_code, employee_id
            )
            
            if component:
                results['success'].append({
                    'employee_id': employee_id,
                    'employee_name': component.employee.get_full_name_ar(),
                    'created': created
                })
            else:
                results['failed'].append(employee_id)
        
        return results
    
    @staticmethod
    def get_employee_applied_templates(employee_id):
        """
        الحصول على القوالب المطبقة على موظف معين
        
        Args:
            employee_id: معرف الموظف
            
        Returns:
            QuerySet: مكونات الراتب المرتبطة بقوالب
        """
        return SalaryComponent.objects.filter(
            employee_id=employee_id,
            template__isnull=False
        ).select_related('template')
    
    @staticmethod
    def remove_template_from_employee(template_code, employee_id):
        """
        إزالة قالب من موظف معين
        
        Args:
            template_code: كود القالب
            employee_id: معرف الموظف
            
        Returns:
            bool: نجح الحذف أم لا
        """
        logger = logging.getLogger(__name__)
        
        try:
            component = SalaryComponent.objects.get(
                employee_id=employee_id,
                code=template_code,
                template__isnull=False
            )
            
            component_name = component.name
            employee_name = component.employee.get_full_name_ar()
            
            component.delete()
            
            logger.info(f"تم حذف {component_name} من الموظف {employee_name}")
            return True
            
        except SalaryComponent.DoesNotExist:
            logger.warning(f"المكون {template_code} غير موجود للموظف {employee_id}")
            return False
        except Exception as e:
            logger.error(f"خطأ في حذف المكون: {str(e)}")
            return False
    
    @staticmethod
    def get_template_usage_stats(template_code):
        """
        إحصائيات استخدام القالب
        
        Args:
            template_code: كود القالب
            
        Returns:
            dict: إحصائيات الاستخدام
        """
        try:
            template = SalaryComponentTemplate.objects.get(code=template_code)
            
            usage_count = SalaryComponent.objects.filter(
                template=template
            ).count()
            
            active_usage = SalaryComponent.objects.filter(
                template=template,
                is_active=True
            ).count()
            
            return {
                'template_name': template.name,
                'total_usage': usage_count,
                'active_usage': active_usage,
                'template_active': template.is_active
            }
            
        except SalaryComponentTemplate.DoesNotExist:
            return None
