"""
Financial Category Service
خدمة التصنيفات المالية - محدثة ومبسطة
"""
from django.db.models import QuerySet, Sum, Q, DecimalField
from django.db.models.functions import Coalesce
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date
from typing import Optional, Dict, List
import logging

from ..models.categories import FinancialCategory
from ..models.journal_entry import JournalEntry, JournalEntryLine

logger = logging.getLogger(__name__)


class FinancialCategoryService:
    """
    خدمة إدارة التصنيفات المالية - نسخة محدثة ومبسطة
    """
    
    # ==================== Basic Operations ====================
    
    @staticmethod
    def get_all_active() -> QuerySet:
        """
        جلب جميع التصنيفات النشطة مرتبة حسب display_order
        
        Returns:
            QuerySet: التصنيفات النشطة
        """
        return FinancialCategory.objects.filter(
            is_active=True
        ).select_related(
            'default_revenue_account',
            'default_expense_account'
        ).order_by('display_order', 'name')
    
    @staticmethod
    def get_by_code(code: str) -> Optional[FinancialCategory]:
        """
        جلب تصنيف بالكود
        
        Args:
            code: كود التصنيف
            
        Returns:
            FinancialCategory أو None
        """
        try:
            return FinancialCategory.objects.select_related(
                'default_revenue_account',
                'default_expense_account'
            ).get(code=code, is_active=True)
        except FinancialCategory.DoesNotExist:
            logger.warning(f"التصنيف المالي بالكود {code} غير موجود")
            return None
    
    @staticmethod
    def get_last_for_vendor(vendor_id: int) -> Optional[FinancialCategory]:
        """
        جلب آخر تصنيف مستخدم لمورد معين
        (للاقتراح التلقائي في واجهة المصروفات)
        
        Args:
            vendor_id: معرف المورد
            
        Returns:
            FinancialCategory أو None
        """
        try:
            # البحث عن آخر قيد للمورد له تصنيف
            last_entry = JournalEntry.objects.filter(
                source_module='purchase',
                source_model='PurchaseInvoice',
                financial_category__isnull=False
            ).select_related('financial_category').order_by('-date').first()
            
            if last_entry and last_entry.financial_category:
                return last_entry.financial_category
            
            return None
            
        except Exception as e:
            logger.error(f"خطأ في جلب آخر تصنيف للمورد {vendor_id}: {str(e)}")
            return None
    
    @staticmethod
    def validate_accounts(category: FinancialCategory) -> dict:
        """
        التحقق من صحة الحسابات المحاسبية للتصنيف
        
        Args:
            category: التصنيف المالي
            
        Returns:
            dict: نتيجة التحقق
        """
        issues = []
        
        # التحقق من وجود حساب واحد على الأقل
        if not category.default_revenue_account and not category.default_expense_account:
            issues.append("لا يوجد حساب إيرادات أو مصروفات محدد")
        
        # التحقق من نشاط الحسابات
        if category.default_revenue_account and not category.default_revenue_account.is_active:
            issues.append(f"حساب الإيرادات {category.default_revenue_account.code} غير نشط")
        
        if category.default_expense_account and not category.default_expense_account.is_active:
            issues.append(f"حساب المصروفات {category.default_expense_account.code} غير نشط")
        
        return {
            'is_valid': len(issues) == 0,
            'issues': issues
        }
    
    @staticmethod
    def get_for_dropdown() -> list:
        """
        جلب التصنيفات بصيغة مناسبة للـ dropdown
        
        Returns:
            list: قائمة التصنيفات بصيغة (id, name)
        """
        categories = FinancialCategoryService.get_all_active()
        return [
            {
                'id': cat.id,
                'code': cat.code,
                'name': cat.name,
            }
            for cat in categories
        ]
    
    # ==================== Profitability Analysis ====================
    
    @staticmethod
    def get_category_report(
        code: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> Dict:
        """
        تقرير ربحية تصنيف واحد
        
        Args:
            code: كود التصنيف
            date_from: تاريخ البداية (اختياري)
            date_to: تاريخ النهاية (اختياري)
            
        Returns:
            dict: تقرير الربحية
        """
        try:
            # جلب التصنيف
            category = FinancialCategory.objects.get(code=code, is_active=True)
            
            # بناء الاستعلام الأساسي
            entries_query = JournalEntry.objects.filter(
                financial_category=category,
                status='posted'
            )
            
            # تطبيق فلتر التاريخ
            if date_from:
                entries_query = entries_query.filter(date__gte=date_from)
            if date_to:
                entries_query = entries_query.filter(date__lte=date_to)
            
            # حساب الإيرادات (من حساب الإيرادات الافتراضي)
            revenue = Decimal('0')
            if category.default_revenue_account:
                revenue_lines = JournalEntryLine.objects.filter(
                    journal_entry__in=entries_query,
                    account=category.default_revenue_account
                ).aggregate(
                    total=Coalesce(Sum('credit'), Decimal('0'), output_field=DecimalField())
                )
                revenue = revenue_lines['total'] or Decimal('0')
            
            # حساب المصروفات (من حساب المصروفات الافتراضي)
            expenses = Decimal('0')
            if category.default_expense_account:
                expense_lines = JournalEntryLine.objects.filter(
                    journal_entry__in=entries_query,
                    account=category.default_expense_account
                ).aggregate(
                    total=Coalesce(Sum('debit'), Decimal('0'), output_field=DecimalField())
                )
                expenses = expense_lines['total'] or Decimal('0')
            
            # حساب الربح/الخسارة
            profit = revenue - expenses
            margin = (profit / revenue * 100) if revenue > 0 else Decimal('0')
            
            return {
                'category': {
                    'code': category.code,
                    'name': category.name,
                },
                'period': {
                    'from': date_from,
                    'to': date_to,
                },
                'revenue': revenue,
                'expenses': expenses,
                'profit': profit,
                'margin': margin,
                'is_profitable': profit > 0,
                'entries_count': entries_query.count(),
            }
            
        except FinancialCategory.DoesNotExist:
            logger.error(f"التصنيف {code} غير موجود")
            return {}
        except Exception as e:
            logger.error(f"خطأ في حساب ربحية التصنيف {code}: {str(e)}")
            return {}
    
    @staticmethod
    def get_all_summary(
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> Dict:
        """
        ملخص ربحية جميع التصنيفات
        
        Args:
            date_from: تاريخ البداية (اختياري)
            date_to: تاريخ النهاية (اختياري)
            
        Returns:
            dict: ملخص شامل
        """
        try:
            categories = FinancialCategory.objects.filter(is_active=True)
            
            summary_data = {
                'period': {
                    'from': date_from,
                    'to': date_to,
                },
                'categories': [],
                'totals': {
                    'revenue': Decimal('0'),
                    'expenses': Decimal('0'),
                    'profit': Decimal('0'),
                    'margin': Decimal('0'),
                },
                'profitable_count': 0,
                'loss_count': 0,
            }
            
            for category in categories:
                report = FinancialCategoryService.get_category_report(
                    category.code,
                    date_from,
                    date_to
                )
                
                if report:
                    summary_data['categories'].append(report)
                    
                    # تحديث الإجماليات
                    summary_data['totals']['revenue'] += report['revenue']
                    summary_data['totals']['expenses'] += report['expenses']
                    summary_data['totals']['profit'] += report['profit']
                    
                    # عد الربحية
                    if report['is_profitable']:
                        summary_data['profitable_count'] += 1
                    elif report['profit'] < 0:
                        summary_data['loss_count'] += 1
            
            # حساب الهامش الإجمالي
            if summary_data['totals']['revenue'] > 0:
                summary_data['totals']['margin'] = (
                    summary_data['totals']['profit'] / 
                    summary_data['totals']['revenue'] * 100
                )
            
            # ترتيب حسب الربح (الأعلى أولاً)
            summary_data['categories'].sort(
                key=lambda x: x['profit'],
                reverse=True
            )
            
            return summary_data
            
        except Exception as e:
            logger.error(f"خطأ في حساب ملخص الربحية: {str(e)}")
            return {}
    
    @staticmethod
    def get_top_profitable(
        limit: int = 5,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> List[Dict]:
        """
        أفضل التصنيفات ربحاً
        
        Args:
            limit: عدد التصنيفات المطلوبة
            date_from: تاريخ البداية
            date_to: تاريخ النهاية
            
        Returns:
            list: قائمة أفضل التصنيفات
        """
        summary = FinancialCategoryService.get_all_summary(date_from, date_to)
        
        if not summary or not summary.get('categories'):
            return []
        
        # فلترة التصنيفات الربحية فقط
        profitable = [
            cat for cat in summary['categories']
            if cat['is_profitable']
        ]
        
        return profitable[:limit]
    
    @staticmethod
    def get_loss_making(
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> List[Dict]:
        """
        التصنيفات الخاسرة
        
        Args:
            date_from: تاريخ البداية
            date_to: تاريخ النهاية
            
        Returns:
            list: قائمة التصنيفات الخاسرة
        """
        summary = FinancialCategoryService.get_all_summary(date_from, date_to)
        
        if not summary or not summary.get('categories'):
            return []
        
        # فلترة التصنيفات الخاسرة فقط
        loss_making = [
            cat for cat in summary['categories']
            if cat['profit'] < 0
        ]
        
        # ترتيب حسب الخسارة (الأكبر أولاً)
        loss_making.sort(key=lambda x: x['profit'])
        
        return loss_making


# Alias for backward compatibility
CategoryService = FinancialCategoryService
CategoryProfitabilityService = FinancialCategoryService
