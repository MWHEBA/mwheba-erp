"""
خدمة إدارة التصنيفات المالية والميزانيات
"""
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Sum, Count
from decimal import Decimal
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from ..models.categories import FinancialCategory, CategoryBudget
from ..models.transactions import FinancialTransaction

logger = logging.getLogger(__name__)


class CategoryService:
    """
    خدمة شاملة لإدارة التصنيفات المالية والميزانيات
    """
    
    @staticmethod
    def create_category(
        name: str,
        category_type: str,
        code: str = "",
        parent_id: Optional[int] = None,
        priority: str = 'medium',
        budget_limit: Optional[Decimal] = None,
        requires_approval: bool = False,
        user=None
    ) -> FinancialCategory:
        """
        إنشاء فئة مالية جديدة
        """
        try:
            with transaction.atomic():
                # التحقق من التصنيف الأب إذا تم تحديدها
                parent = None
                if parent_id:
                    parent = FinancialCategory.objects.get(id=parent_id, is_active=True)
                    
                    # التحقق من توافق النوع
                    if parent.type not in [category_type, 'both']:
                        raise ValidationError("نوع التصنيف الفرعية يجب أن يتوافق مع التصنيف الأب")
                
                # إنشاء التصنيف
                category = FinancialCategory.objects.create(
                    name=name,
                    code=code,
                    type=category_type,
                    parent=parent,
                    priority=priority,
                    budget_limit=budget_limit,
                    requires_approval=requires_approval,
                    created_by=user
                )
                
                logger.info(f"تم إنشاء فئة مالية: {category.name}")
                return category
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء التصنيف المالية: {str(e)}")
            raise ValidationError(f"فشل في إنشاء التصنيف المالية: {str(e)}")
    
    @staticmethod
    def create_budget(
        category_id: int,
        budget_amount: Decimal,
        period_type: str,
        start_date: datetime,
        end_date: datetime,
        notes: str = "",
        user=None
    ) -> CategoryBudget:
        """
        إنشاء ميزانية لفئة مالية
        """
        try:
            with transaction.atomic():
                category = FinancialCategory.objects.get(id=category_id, is_active=True)
                
                # التحقق من عدم تداخل الفترات
                existing_budget = CategoryBudget.objects.filter(
                    category=category,
                    is_active=True,
                    start_date__lte=end_date,
                    end_date__gte=start_date
                ).first()
                
                if existing_budget:
                    raise ValidationError("يوجد ميزانية أخرى لهذا التصنيف في نفس الفترة")
                
                # إنشاء الميزانية
                budget = CategoryBudget.objects.create(
                    category=category,
                    period_type=period_type,
                    start_date=start_date,
                    end_date=end_date,
                    budget_amount=budget_amount,
                    notes=notes,
                    created_by=user
                )
                
                logger.info(f"تم إنشاء ميزانية للفئة {category.name}: {budget_amount}")
                return budget
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء الميزانية: {str(e)}")
            raise ValidationError(f"فشل في إنشاء الميزانية: {str(e)}")
    
    @staticmethod
    def get_category_usage(
        category_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """
        الحصول على استخدام الميزانية للفئة
        """
        try:
            category = FinancialCategory.objects.get(id=category_id)
            
            if not start_date:
                start_date = timezone.now().date().replace(day=1)  # بداية الشهر الحالي
            if not end_date:
                end_date = timezone.now().date()
            
            # حساب إجمالي المعاملات في هذا التصنيف
            transactions = FinancialTransaction.objects.filter(
                category=category,
                date__gte=start_date,
                date__lte=end_date,
                status='processed'
            )
            
            total_spent = transactions.aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')
            
            transaction_count = transactions.count()
            
            # الحصول على الميزانية النشطة
            active_budget = CategoryBudget.objects.filter(
                category=category,
                is_active=True,
                start_date__lte=end_date,
                end_date__gte=start_date
            ).first()
            
            budget_limit = active_budget.budget_amount if active_budget else category.budget_limit
            
            usage_data = {
                'category': category.name,
                'total_spent': total_spent,
                'transaction_count': transaction_count,
                'budget_limit': budget_limit,
                'remaining': None,
                'usage_percentage': 0,
                'is_over_budget': False,
                'is_warning': False,
                'period_from': start_date,
                'period_to': end_date
            }
            
            if budget_limit:
                usage_data['remaining'] = budget_limit - total_spent
                usage_data['usage_percentage'] = (total_spent / budget_limit) * 100 if budget_limit > 0 else 0
                usage_data['is_over_budget'] = total_spent > budget_limit
                usage_data['is_warning'] = usage_data['usage_percentage'] >= category.warning_threshold
            
            return usage_data
            
        except Exception as e:
            logger.error(f"خطأ في حساب استخدام التصنيف: {str(e)}")
            return {}
    
    @staticmethod
    def get_budget_alerts() -> List[Dict]:
        """
        الحصول على تنبيهات الميزانيات
        """
        alerts = []
        
        try:
            # الحصول على التصنيفات التي لها حدود ميزانية
            categories_with_budget = FinancialCategory.objects.filter(
                is_active=True,
                budget_limit__isnull=False
            )
            
            current_date = timezone.now().date()
            start_of_month = current_date.replace(day=1)
            
            for category in categories_with_budget:
                usage_data = CategoryService.get_category_usage(
                    category.id, 
                    start_of_month, 
                    current_date
                )
                
                if usage_data.get('is_over_budget'):
                    alerts.append({
                        'type': 'over_budget',
                        'category': category.name,
                        'message': f'تم تجاوز ميزانية فئة {category.name}',
                        'spent': usage_data['total_spent'],
                        'budget': usage_data['budget_limit'],
                        'excess': usage_data['total_spent'] - usage_data['budget_limit'],
                        'priority': 'high'
                    })
                elif usage_data.get('is_warning'):
                    alerts.append({
                        'type': 'budget_warning',
                        'category': category.name,
                        'message': f'اقتراب من حد ميزانية فئة {category.name}',
                        'spent': usage_data['total_spent'],
                        'budget': usage_data['budget_limit'],
                        'usage_percentage': usage_data['usage_percentage'],
                        'priority': 'medium'
                    })
            
            # فحص الميزانيات النشطة
            active_budgets = CategoryBudget.objects.filter(
                is_active=True,
                start_date__lte=current_date,
                end_date__gte=current_date
            )
            
            for budget in active_budgets:
                usage_data = CategoryService.get_category_usage(
                    budget.category.id,
                    budget.start_date,
                    min(budget.end_date, current_date)
                )
                
                if usage_data['total_spent'] > budget.budget_amount:
                    alerts.append({
                        'type': 'budget_exceeded',
                        'category': budget.category.name,
                        'message': f'تم تجاوز ميزانية {budget.category.name} للفترة {budget.start_date} - {budget.end_date}',
                        'spent': usage_data['total_spent'],
                        'budget': budget.budget_amount,
                        'excess': usage_data['total_spent'] - budget.budget_amount,
                        'priority': 'high'
                    })
            
            return alerts
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على تنبيهات الميزانية: {str(e)}")
            return []
    
    @staticmethod
    def get_category_hierarchy(category_type: Optional[str] = None) -> List[Dict]:
        """
        الحصول على التسلسل الهرمي للتصنيفات
        """
        try:
            # الحصول على التصنيفات الجذر
            root_categories = FinancialCategory.objects.filter(
                parent__isnull=True,
                is_active=True
            )
            
            if category_type:
                root_categories = root_categories.filter(type__in=[category_type, 'both'])
            
            def build_tree(category):
                children = category.children.filter(is_active=True)
                if category_type:
                    children = children.filter(type__in=[category_type, 'both'])
                
                return {
                    'id': category.id,
                    'name': category.name,
                    'code': category.code,
                    'type': category.type,
                    'level': category.level,
                    'budget_limit': category.budget_limit,
                    'children': [build_tree(child) for child in children]
                }
            
            return [build_tree(category) for category in root_categories]
            
        except Exception as e:
            logger.error(f"خطأ في بناء التسلسل الهرمي: {str(e)}")
            return []
    
    @staticmethod
    def get_category_report(
        start_date: datetime,
        end_date: datetime,
        category_type: Optional[str] = None
    ) -> Dict:
        """
        تقرير شامل للتصنيفات المالية
        """
        try:
            categories = FinancialCategory.objects.filter(is_active=True)
            
            if category_type:
                categories = categories.filter(type__in=[category_type, 'both'])
            
            report_data = {
                'period_from': start_date,
                'period_to': end_date,
                'categories': [],
                'summary': {
                    'total_categories': categories.count(),
                    'total_spent': Decimal('0'),
                    'total_budget': Decimal('0'),
                    'categories_over_budget': 0,
                    'categories_with_warnings': 0
                }
            }
            
            for category in categories:
                usage_data = CategoryService.get_category_usage(
                    category.id, start_date, end_date
                )
                
                category_data = {
                    'id': category.id,
                    'name': category.name,
                    'code': category.code,
                    'type': category.type,
                    'priority': category.priority,
                    'usage': usage_data
                }
                
                report_data['categories'].append(category_data)
                
                # تحديث الملخص
                report_data['summary']['total_spent'] += usage_data['total_spent']
                
                if usage_data['budget_limit']:
                    report_data['summary']['total_budget'] += usage_data['budget_limit']
                
                if usage_data.get('is_over_budget'):
                    report_data['summary']['categories_over_budget'] += 1
                
                if usage_data.get('is_warning'):
                    report_data['summary']['categories_with_warnings'] += 1
            
            return report_data
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء تقرير التصنيفات: {str(e)}")
            return {}
    
    @staticmethod
    def update_budget_spent_amounts():
        """
        تحديث المبالغ المنفقة في الميزانيات
        """
        try:
            updated_count = 0
            
            active_budgets = CategoryBudget.objects.filter(is_active=True)
            
            for budget in active_budgets:
                # حساب المبلغ المنفق في فترة الميزانية
                spent_amount = FinancialTransaction.objects.filter(
                    category=budget.category,
                    date__gte=budget.start_date,
                    date__lte=budget.end_date,
                    status='processed'
                ).aggregate(
                    total=Sum('amount')
                )['total'] or Decimal('0')
                
                if budget.spent_amount != spent_amount:
                    budget.spent_amount = spent_amount
                    budget.save(update_fields=['spent_amount'])
                    updated_count += 1
            
            logger.info(f"تم تحديث {updated_count} ميزانية")
            return updated_count
            
        except Exception as e:
            logger.error(f"خطأ في تحديث الميزانيات: {str(e)}")
            return 0
