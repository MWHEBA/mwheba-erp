"""
خدمة تقارير الربحية حسب التصنيفات المالية
"""
from django.db.models import Sum, Q, F, DecimalField, Value
from django.db.models.functions import Coalesce
from decimal import Decimal
from datetime import date
from typing import Dict, List, Optional, Tuple

from financial.models import JournalEntry, JournalEntryLine, FinancialCategory


class CategoryProfitabilityService:
    """
    خدمة تحليل الربحية حسب التصنيفات المالية
    """
    
    @staticmethod
    def get_category_report(
        category_code: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> Dict:
        """
        تقرير تفصيلي لتصنيف واحد
        
        Args:
            category_code: رمز التصنيف
            date_from: تاريخ البداية (اختياري)
            date_to: تاريخ النهاية (اختياري)
        
        Returns:
            dict: تقرير يحتوي على الإيرادات والمصروفات والربح
        """
        from financial.models import FinancialCategory, FinancialSubcategory
        
        # محاولة البحث في التصنيفات الرئيسية أولاً
        category = FinancialCategory.objects.filter(code=category_code, is_active=True).first()
        
        if category:
            is_subcategory = False
            parent_name = ''
        else:
            # محاولة البحث في التصنيفات الفرعية
            subcategories = FinancialSubcategory.objects.select_related('parent_category').filter(
                code=category_code, 
                is_active=True
            )
            
            # تحذير إذا وجدنا أكثر من تصنيف فرعي بنفس الكود
            if subcategories.count() > 1:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Found {subcategories.count()} subcategories with code '{category_code}'. "
                    f"Using the first one. Consider making subcategory codes globally unique."
                )
            
            subcategory = subcategories.first()
            
            if subcategory:
                category = subcategory
                is_subcategory = True
                parent_name = subcategory.parent_category.name
            else:
                return {
                    'success': False,
                    'error': f'التصنيف {category_code} غير موجود أو غير نشط'
                }
        
        # بناء الاستعلام الأساسي
        if is_subcategory:
            entries_query = JournalEntry.objects.filter(
                financial_subcategory=category,
                status='posted'
            )
        else:
            entries_query = JournalEntry.objects.filter(
                status='posted'
            ).filter(
                Q(financial_category=category) | Q(financial_subcategory__parent_category=category)
            )
        
        # تطبيق فلتر التاريخ
        if date_from:
            entries_query = entries_query.filter(date__gte=date_from)
        if date_to:
            entries_query = entries_query.filter(date__lte=date_to)
        
        # حساب الإيرادات على أساس نقدي (Cash Basis)
        # نحسب المبالغ المحصلة فعلياً من الخزينة/البنك
        cash_receipts = JournalEntryLine.objects.filter(
            journal_entry__in=entries_query,
            account__code__in=['10100', '10200'],  # الخزينة والبنك
            debit__gt=0  # المبالغ المدينة (المستلمة)
        ).aggregate(
            total=Coalesce(Sum('debit'), Value(Decimal('0')), output_field=DecimalField())
        )
        
        # حساب الاستردادات (المبالغ الدائنة من الخزينة/البنك - أي قيد فيه خروج نقدية)
        cash_refunds = JournalEntryLine.objects.filter(
            journal_entry__in=entries_query,
            account__code__in=['10100', '10200'],  # الخزينة والبنك
            credit__gt=0  # المبالغ الدائنة (المدفوعة)
        ).aggregate(
            total=Coalesce(Sum('credit'), Value(Decimal('0')), output_field=DecimalField())
        )
        
        # حساب المصروفات (حسابات تبدأ بـ 5)
        expense_lines = JournalEntryLine.objects.filter(
            journal_entry__in=entries_query,
            account__code__startswith='5'
        ).aggregate(
            total=Coalesce(Sum('debit'), Value(Decimal('0')), output_field=DecimalField())
        )
        
        gross_revenues = cash_receipts['total'] or Decimal('0')
        refunds = cash_refunds['total'] or Decimal('0')
        revenues = gross_revenues - refunds  # صافي الإيرادات بعد الاستردادات
        expenses = expense_lines['total'] or Decimal('0')
        profit = revenues - expenses
        margin = (profit / revenues * 100) if revenues > 0 else Decimal('0')
        
        # جلب قائمة الإيرادات (المبالغ المحصلة - القيود اللي فيها دخول نقدية)
        revenue_entries = []
        for entry in entries_query.prefetch_related('lines__account'):
            cash_amount = sum(
                line.debit for line in entry.lines.all()
                if line.account.code in ['10100', '10200']
            )
            if cash_amount > 0:
                revenue_entries.append({
                    'id': entry.id,
                    'date': entry.date,
                    'number': entry.number,
                    'description': entry.description,
                    'amount': cash_amount,
                    'reference': entry.reference or '-'
                })
        
        # جلب قائمة الاستردادات (القيود اللي فيها خروج نقدية)
        refund_entries = []
        for entry in entries_query.prefetch_related('lines__account'):
            refund_amount = sum(
                line.credit for line in entry.lines.all()
                if line.account.code in ['10100', '10200']
            )
            if refund_amount > 0:
                refund_entries.append({
                    'id': entry.id,
                    'date': entry.date,
                    'number': entry.number,
                    'description': entry.description,
                    'amount': refund_amount,
                    'reference': entry.reference or '-'
                })
        
        # جلب قائمة المصروفات
        expense_entries = []
        for entry in entries_query.prefetch_related('lines__account'):
            expense_amount = sum(
                line.debit for line in entry.lines.all()
                if line.account.code.startswith('5')
            )
            if expense_amount > 0:
                expense_entries.append({
                    'id': entry.id,
                    'date': entry.date,
                    'number': entry.number,
                    'description': entry.description,
                    'amount': expense_amount,
                    'reference': entry.reference or '-'
                })
        
        return {
            'success': True,
            'category': {
                'code': category.code,
                'name': category.name,
                'parent_name': parent_name
            },
            'period': {
                'from': date_from,
                'to': date_to
            },
            'summary': {
                'gross_revenues': gross_revenues,
                'refunds': refunds,
                'revenues': revenues,
                'expenses': expenses,
                'profit': profit,
                'margin': margin
            },
            'revenue_entries': revenue_entries,
            'refund_entries': refund_entries,
            'expense_entries': expense_entries
        }
    
    @staticmethod
    def get_all_summary(
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> Dict:
        """
        ملخص كل التصنيفات المالية في شكل شجرة
        
        Args:
            date_from: تاريخ البداية (اختياري)
            date_to: تاريخ النهاية (اختياري)
        
        Returns:
            dict: ملخص يحتوي على جميع التصنيفات في شكل hierarchical
        """
        from financial.models import FinancialCategory, FinancialSubcategory
        
        # جلب التصنيفات الرئيسية النشطة
        parent_categories = FinancialCategory.objects.filter(
            is_active=True
        ).prefetch_related('subcategories').order_by('display_order', 'name')
        
        results = []
        total_revenues = Decimal('0')
        total_expenses = Decimal('0')
        
        for parent_category in parent_categories:
            # حساب حركات التصنيف الرئيسي المباشرة
            parent_entries = JournalEntry.objects.filter(
                status='posted',
                financial_category=parent_category,
                financial_subcategory__isnull=True  # حركات مباشرة على الأب فقط
            )
            
            # تطبيق فلتر التاريخ
            if date_from:
                parent_entries = parent_entries.filter(date__gte=date_from)
            if date_to:
                parent_entries = parent_entries.filter(date__lte=date_to)
            
            # حساب إيرادات ومصروفات الأب المباشرة
            parent_cash_receipts = JournalEntryLine.objects.filter(
                journal_entry__in=parent_entries,
                account__code__in=['10100', '10200'],
                debit__gt=0
            ).aggregate(
                total=Coalesce(Sum('debit'), Value(Decimal('0')), output_field=DecimalField())
            )
            
            parent_cash_refunds = JournalEntryLine.objects.filter(
                journal_entry__in=parent_entries,
                account__code__in=['10100', '10200'],
                credit__gt=0
            ).aggregate(
                total=Coalesce(Sum('credit'), Value(Decimal('0')), output_field=DecimalField())
            )
            
            parent_expenses = JournalEntryLine.objects.filter(
                journal_entry__in=parent_entries,
                account__code__startswith='5'
            ).aggregate(
                total=Coalesce(Sum('debit'), Value(Decimal('0')), output_field=DecimalField())
            )
            
            parent_gross_revenues = parent_cash_receipts['total'] or Decimal('0')
            parent_refunds = parent_cash_refunds['total'] or Decimal('0')
            parent_revenues = parent_gross_revenues - parent_refunds
            parent_expenses_total = parent_expenses['total'] or Decimal('0')
            
            # معالجة التصنيفات الفرعية
            subcategories_data = []
            subcategories_gross_revenues = Decimal('0')
            subcategories_refunds = Decimal('0')
            subcategories_revenues = Decimal('0')
            subcategories_expenses = Decimal('0')
            
            for subcategory in parent_category.subcategories.filter(is_active=True).order_by('display_order', 'name'):
                sub_entries = JournalEntry.objects.filter(
                    status='posted',
                    financial_subcategory=subcategory
                )
                
                # تطبيق فلتر التاريخ
                if date_from:
                    sub_entries = sub_entries.filter(date__gte=date_from)
                if date_to:
                    sub_entries = sub_entries.filter(date__lte=date_to)
                
                # حساب إيرادات ومصروفات الفرعي
                sub_cash_receipts = JournalEntryLine.objects.filter(
                    journal_entry__in=sub_entries,
                    account__code__in=['10100', '10200'],
                    debit__gt=0
                ).aggregate(
                    total=Coalesce(Sum('debit'), Value(Decimal('0')), output_field=DecimalField())
                )
                
                sub_cash_refunds = JournalEntryLine.objects.filter(
                    journal_entry__in=sub_entries,
                    account__code__in=['10100', '10200'],
                    credit__gt=0
                ).aggregate(
                    total=Coalesce(Sum('credit'), Value(Decimal('0')), output_field=DecimalField())
                )
                
                sub_expenses = JournalEntryLine.objects.filter(
                    journal_entry__in=sub_entries,
                    account__code__startswith='5'
                ).aggregate(
                    total=Coalesce(Sum('debit'), Value(Decimal('0')), output_field=DecimalField())
                )
                
                sub_gross_revenues = sub_cash_receipts['total'] or Decimal('0')
                sub_refunds = sub_cash_refunds['total'] or Decimal('0')
                sub_revenues = sub_gross_revenues - sub_refunds
                sub_expenses_total = sub_expenses['total'] or Decimal('0')
                
                # إضافة للإجماليات الفرعية
                subcategories_gross_revenues += sub_gross_revenues
                subcategories_refunds += sub_refunds
                subcategories_revenues += sub_revenues
                subcategories_expenses += sub_expenses_total
                
                # إضافة التصنيف الفرعي إذا كان له حركة
                if sub_gross_revenues > 0 or sub_expenses_total > 0:
                    sub_profit = sub_revenues - sub_expenses_total
                    sub_margin = (sub_profit / sub_revenues * 100) if sub_revenues > 0 else Decimal('0')
                    
                    subcategories_data.append({
                        'code': subcategory.code,
                        'name': subcategory.name,
                        'gross_revenues': sub_gross_revenues,
                        'refunds': sub_refunds,
                        'revenues': sub_revenues,
                        'expenses': sub_expenses_total,
                        'profit': sub_profit,
                        'margin': sub_margin,
                        'status': 'profit' if sub_profit > 0 else 'loss' if sub_profit < 0 else 'break_even',
                        'is_subcategory': True
                    })
            
            # إجمالي التصنيف الرئيسي = حركاته المباشرة + حركات أبنائه
            category_total_gross_revenues = parent_gross_revenues + subcategories_gross_revenues
            category_total_refunds = parent_refunds + subcategories_refunds
            category_total_revenues = parent_revenues + subcategories_revenues
            category_total_expenses = parent_expenses_total + subcategories_expenses
            
            # إضافة للإجماليات الكلية
            total_revenues += category_total_revenues
            total_expenses += category_total_expenses
            
            # إضافة التصنيف الرئيسي إذا كان له حركة (مباشرة أو من الأبناء)
            if category_total_gross_revenues > 0 or category_total_expenses > 0:
                category_profit = category_total_revenues - category_total_expenses
                category_margin = (category_profit / category_total_revenues * 100) if category_total_revenues > 0 else Decimal('0')
                
                results.append({
                    'code': parent_category.code,
                    'name': parent_category.name,
                    'gross_revenues': category_total_gross_revenues,
                    'refunds': category_total_refunds,
                    'revenues': category_total_revenues,
                    'expenses': category_total_expenses,
                    'profit': category_profit,
                    'margin': category_margin,
                    'status': 'profit' if category_profit > 0 else 'loss' if category_profit < 0 else 'break_even',
                    'is_subcategory': False,
                    'has_subcategories': len(subcategories_data) > 0,
                    'subcategories': subcategories_data,
                    'direct_gross_revenues': parent_gross_revenues,
                    'direct_refunds': parent_refunds,
                    'direct_revenues': parent_revenues,
                    'direct_expenses': parent_expenses_total
                })
        
        total_profit = total_revenues - total_expenses
        total_margin = (total_profit / total_revenues * 100) if total_revenues > 0 else Decimal('0')
        
        return {
            'success': True,
            'period': {
                'from': date_from,
                'to': date_to
            },
            'categories': results,
            'totals': {
                'revenues': total_revenues,
                'expenses': total_expenses,
                'profit': total_profit,
                'margin': total_margin
            }
        }
    
    @staticmethod
    def get_top_profitable_categories(
        limit: int = 5,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> List[Dict]:
        """
        أفضل التصنيفات الفرعية ربحاً
        
        Args:
            limit: عدد التصنيفات المطلوبة
            date_from: تاريخ البداية (اختياري)
            date_to: تاريخ النهاية (اختياري)
        
        Returns:
            list: قائمة بأفضل التصنيفات الفرعية
        """
        summary = CategoryProfitabilityService.get_all_summary(date_from, date_to)
        
        if not summary['success']:
            return []
        
        # جمع كل التصنيفات الفرعية من جميع التصنيفات الرئيسية
        all_subcategories = []
        for category in summary['categories']:
            if category.get('has_subcategories') and category.get('subcategories'):
                for subcategory in category['subcategories']:
                    # إضافة اسم التصنيف الرئيسي للسياق
                    subcategory['parent_name'] = category['name']
                    all_subcategories.append(subcategory)
        
        # ترتيب حسب الربح
        sorted_subcategories = sorted(
            all_subcategories,
            key=lambda x: x['profit'],
            reverse=True
        )
        
        return sorted_subcategories[:limit]
    
    @staticmethod
    def get_loss_making_categories(
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> List[Dict]:
        """
        التصنيفات الفرعية الخاسرة
        
        Args:
            date_from: تاريخ البداية (اختياري)
            date_to: تاريخ النهاية (اختياري)
        
        Returns:
            list: قائمة بالتصنيفات الفرعية الخاسرة
        """
        summary = CategoryProfitabilityService.get_all_summary(date_from, date_to)
        
        if not summary['success']:
            return []
        
        # جمع كل التصنيفات الفرعية من جميع التصنيفات الرئيسية
        all_subcategories = []
        for category in summary['categories']:
            if category.get('has_subcategories') and category.get('subcategories'):
                for subcategory in category['subcategories']:
                    # إضافة اسم التصنيف الرئيسي للسياق
                    subcategory['parent_name'] = category['name']
                    all_subcategories.append(subcategory)
        
        # فلترة التصنيفات الفرعية الخاسرة
        loss_subcategories = [
            cat for cat in all_subcategories
            if cat['profit'] < 0
        ]
        
        # ترتيب حسب الخسارة (الأكبر خسارة أولاً)
        sorted_subcategories = sorted(
            loss_subcategories,
            key=lambda x: x['profit']
        )
        
        return sorted_subcategories
