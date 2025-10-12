"""
خدمة التحقق من صحة الأرصدة والتسويات المتقدمة
"""
from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple, Any
from datetime import date, datetime, timedelta
import logging

from ..models.chart_of_accounts import ChartOfAccounts
from ..models.journal_entry import JournalEntry, JournalEntryLine
from ..models.enhanced_balance import BalanceReconciliation, BalanceAuditLog
from .enhanced_balance_service import EnhancedBalanceService

logger = logging.getLogger(__name__)


class AdvancedBalanceValidationService:
    """
    خدمة التحقق المتقدم من صحة الأرصدة
    """
    
    # حد الفرق المقبول (قرش واحد)
    TOLERANCE = Decimal('0.01')
    
    @classmethod
    def validate_all_balances(
        cls,
        date_to: Optional[date] = None,
        fix_discrepancies: bool = False
    ) -> Dict:
        """
        التحقق من صحة جميع الأرصدة
        """
        if not date_to:
            date_to = timezone.now().date()
        
        logger.info(f"بدء التحقق من صحة الأرصدة حتى تاريخ {date_to}")
        
        results = {
            'validation_date': date_to,
            'total_accounts': 0,
            'valid_accounts': 0,
            'invalid_accounts': 0,
            'discrepancies': [],
            'total_discrepancy_amount': Decimal('0'),
            'fixed_discrepancies': 0,
            'errors': []
        }
        
        # الحصول على جميع الحسابات النهائية النشطة
        accounts = ChartOfAccounts.objects.filter(
            is_leaf=True,
            is_active=True
        ).order_by('code')
        
        results['total_accounts'] = accounts.count()
        
        for account in accounts:
            try:
                validation_result = cls._validate_single_account(account, date_to)
                
                if validation_result['is_valid']:
                    results['valid_accounts'] += 1
                else:
                    results['invalid_accounts'] += 1
                    results['discrepancies'].append(validation_result)
                    results['total_discrepancy_amount'] += abs(validation_result['difference'])
                    
                    # محاولة إصلاح الفرق إذا طُلب
                    if fix_discrepancies:
                        fixed = cls._fix_balance_discrepancy(account, validation_result, date_to)
                        if fixed:
                            results['fixed_discrepancies'] += 1
                
            except Exception as e:
                error_msg = f"خطأ في التحقق من الحساب {account.code}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
        
        # حفظ نتائج التحقق
        cls._save_validation_results(results, date_to)
        
        logger.info(f"انتهى التحقق: {results['valid_accounts']} صحيح، {results['invalid_accounts']} خطأ")
        return results
    
    @classmethod
    def _validate_single_account(cls, account: ChartOfAccounts, date_to: date) -> Dict:
        """
        التحقق من صحة رصيد حساب واحد
        """
        # حساب الرصيد من القيود المحاسبية
        calculated_balance = EnhancedBalanceService.get_account_balance_optimized(
            account, date_to=date_to, use_cache=False
        )
        
        # الحصول على الرصيد من الكاش المحلي
        try:
            from ..models.enhanced_balance import AccountBalanceCache
            cache_obj = AccountBalanceCache.objects.get(account=account)
            cached_balance = cache_obj.current_balance
        except AccountBalanceCache.DoesNotExist:
            cached_balance = Decimal('0')
        
        # حساب الفرق
        difference = calculated_balance - cached_balance
        is_valid = abs(difference) <= cls.TOLERANCE
        
        result = {
            'account_id': account.id,
            'account_code': account.code,
            'account_name': account.name,
            'calculated_balance': calculated_balance,
            'cached_balance': cached_balance,
            'difference': difference,
            'is_valid': is_valid,
            'validation_date': date_to
        }
        
        # تسجيل النتيجة في سجل المراجعة
        BalanceAuditLog.log_balance_change(
            account=account,
            action='calculate',
            old_balance=cached_balance,
            new_balance=calculated_balance,
            notes=f"التحقق من الصحة - فرق: {difference}"
        )
        
        return result
    
    @classmethod
    def _fix_balance_discrepancy(
        cls,
        account: ChartOfAccounts,
        validation_result: Dict,
        date_to: date
    ) -> bool:
        """
        إصلاح فرق الرصيد
        """
        try:
            difference = validation_result['difference']
            
            if abs(difference) <= cls.TOLERANCE:
                return True  # لا يحتاج إصلاح
            
            # تحديث الكاش المحلي
            from ..models.enhanced_balance import AccountBalanceCache
            cache_obj, created = AccountBalanceCache.objects.get_or_create(
                account=account,
                defaults={'current_balance': validation_result['calculated_balance']}
            )
            
            if not created:
                cache_obj.current_balance = validation_result['calculated_balance']
                cache_obj.needs_refresh = False
                cache_obj.is_valid = True
                cache_obj.save()
            
            # تسجيل الإصلاح
            BalanceAuditLog.log_balance_change(
                account=account,
                action='update',
                old_balance=validation_result['cached_balance'],
                new_balance=validation_result['calculated_balance'],
                notes=f"إصلاح فرق الرصيد: {difference}"
            )
            
            logger.info(f"تم إصلاح رصيد الحساب {account.code}")
            return True
            
        except Exception as e:
            logger.error(f"خطأ في إصلاح رصيد الحساب {account.code}: {str(e)}")
            return False
    
    @classmethod
    def validate_trial_balance_integrity(cls, date_to: Optional[date] = None) -> Dict:
        """
        التحقق من سلامة ميزان المراجعة
        """
        if not date_to:
            date_to = timezone.now().date()
        
        logger.info(f"التحقق من سلامة ميزان المراجعة حتى {date_to}")
        
        # الحصول على ميزان المراجعة
        trial_balance = EnhancedBalanceService.get_trial_balance_optimized(date_to=date_to)
        
        # حساب الإجماليات
        total_debit = Decimal('0')
        total_credit = Decimal('0')
        
        for item in trial_balance:
            if item.get('account_code'):  # تجاهل صف الإجمالي
                debit_balance = item.get('debit_balance', 0)
                credit_balance = item.get('credit_balance', 0)
                
                # تحويل إلى Decimal إذا لم يكن كذلك
                if not isinstance(debit_balance, Decimal):
                    debit_balance = Decimal(str(debit_balance))
                if not isinstance(credit_balance, Decimal):
                    credit_balance = Decimal(str(credit_balance))
                
                total_debit += debit_balance
                total_credit += credit_balance
        
        difference = total_debit - total_credit
        is_balanced = abs(difference) <= cls.TOLERANCE
        
        # التحقق من القيود غير المتوازنة
        unbalanced_entries = cls._find_unbalanced_entries(date_to)
        
        # التحقق من الحسابات بدون حركة
        dormant_accounts = cls._find_dormant_accounts(date_to)
        
        result = {
            'validation_date': date_to,
            'is_balanced': is_balanced,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'difference': difference,
            'accounts_count': len([item for item in trial_balance if item.get('account_code')]),
            'unbalanced_entries': unbalanced_entries,
            'dormant_accounts_count': len(dormant_accounts),
            'status': 'متوازن' if is_balanced else f'غير متوازن - الفرق: {difference}'
        }
        
        logger.info(f"نتيجة التحقق: {result['status']}")
        return result
    
    @classmethod
    def _find_unbalanced_entries(cls, date_to: date) -> List[Dict]:
        """
        البحث عن القيود غير المتوازنة
        """
        unbalanced = []
        
        entries = JournalEntry.objects.filter(
            status='posted',
            date__lte=date_to
        ).prefetch_related('lines')
        
        for entry in entries:
            total_debit = sum(line.debit for line in entry.lines.all())
            total_credit = sum(line.credit for line in entry.lines.all())
            difference = total_debit - total_credit
            
            if abs(difference) > cls.TOLERANCE:
                unbalanced.append({
                    'entry_id': entry.id,
                    'entry_number': entry.number,
                    'date': entry.date,
                    'description': entry.description,
                    'total_debit': total_debit,
                    'total_credit': total_credit,
                    'difference': difference
                })
        
        return unbalanced
    
    @classmethod
    def _find_dormant_accounts(cls, date_to: date, days_back: int = 90) -> List[Dict]:
        """
        البحث عن الحسابات الخاملة
        """
        cutoff_date = date_to - timedelta(days=days_back)
        
        # الحسابات التي لم تتحرك خلال الفترة المحددة
        active_accounts = JournalEntryLine.objects.filter(
            journal_entry__status='posted',
            journal_entry__date__gte=cutoff_date,
            journal_entry__date__lte=date_to
        ).values_list('account_id', flat=True).distinct()
        
        dormant_accounts = ChartOfAccounts.objects.filter(
            is_leaf=True,
            is_active=True
        ).exclude(id__in=active_accounts)
        
        return [
            {
                'account_id': acc.id,
                'account_code': acc.code,
                'account_name': acc.name,
                'last_activity': cls._get_last_activity_date(acc, date_to)
            }
            for acc in dormant_accounts
        ]
    
    @classmethod
    def _get_last_activity_date(cls, account: ChartOfAccounts, date_to: date) -> Optional[date]:
        """
        الحصول على تاريخ آخر نشاط للحساب
        """
        last_line = JournalEntryLine.objects.filter(
            account=account,
            journal_entry__status='posted',
            journal_entry__date__lte=date_to
        ).order_by('-journal_entry__date', '-journal_entry__id').first()
        
        return last_line.journal_entry.date if last_line else None
    
    @classmethod
    def reconcile_account_balance(
        cls,
        account: ChartOfAccounts,
        external_balance: Decimal,
        reconciliation_date: date,
        user=None
    ) -> Dict:
        """
        تسوية رصيد الحساب مع رصيد خارجي
        """
        logger.info(f"بدء تسوية الحساب {account.code} بتاريخ {reconciliation_date}")
        
        # حساب الرصيد من النظام
        system_balance = EnhancedBalanceService.get_account_balance_optimized(
            account, date_to=reconciliation_date, use_cache=False
        )
        
        # الحصول على الرصيد المحسوب
        calculated_balance = cls._recalculate_account_balance(account, reconciliation_date)
        
        # إنشاء سجل التسوية
        reconciliation = BalanceReconciliation.objects.create(
            account=account,
            reconciliation_date=reconciliation_date,
            system_balance=system_balance,
            calculated_balance=calculated_balance,
            external_balance=external_balance
        )
        
        # حساب الفروقات
        reconciliation.calculate_differences()
        
        result = {
            'reconciliation_id': reconciliation.id,
            'account_code': account.code,
            'account_name': account.name,
            'reconciliation_date': reconciliation_date,
            'system_balance': system_balance,
            'calculated_balance': calculated_balance,
            'external_balance': external_balance,
            'system_difference': reconciliation.system_difference,
            'external_difference': reconciliation.external_difference,
            'status': reconciliation.status,
            'needs_attention': reconciliation.status == 'discrepancy'
        }
        
        # تسجيل في سجل المراجعة
        BalanceAuditLog.log_balance_change(
            account=account,
            action='reconcile',
            old_balance=system_balance,
            new_balance=calculated_balance,
            user=user,
            notes=f"تسوية مع رصيد خارجي {external_balance}"
        )
        
        logger.info(f"انتهت تسوية الحساب {account.code} - الحالة: {reconciliation.status}")
        return result
    
    @classmethod
    def _recalculate_account_balance(cls, account: ChartOfAccounts, date_to: date) -> Decimal:
        """
        إعادة حساب رصيد الحساب من الصفر
        """
        lines = JournalEntryLine.objects.filter(
            account=account,
            journal_entry__status='posted',
            journal_entry__date__lte=date_to
        ).aggregate(
            total_debit=models.Sum('debit'),
            total_credit=models.Sum('credit')
        )
        
        total_debit = lines['total_debit'] or Decimal('0')
        total_credit = lines['total_credit'] or Decimal('0')
        
        if account.nature == 'debit':
            return total_debit - total_credit
        else:
            return total_credit - total_debit
    
    @classmethod
    def _save_validation_results(cls, results: Dict, validation_date: date):
        """
        حفظ نتائج التحقق في قاعدة البيانات
        """
        try:
            # يمكن إنشاء نموذج منفصل لحفظ نتائج التحقق
            # أو حفظها في ملف log
            logger.info(f"نتائج التحقق من الأرصدة بتاريخ {validation_date}:")
            logger.info(f"إجمالي الحسابات: {results['total_accounts']}")
            logger.info(f"الحسابات الصحيحة: {results['valid_accounts']}")
            logger.info(f"الحسابات الخاطئة: {results['invalid_accounts']}")
            logger.info(f"إجمالي الفروقات: {results['total_discrepancy_amount']}")
            
        except Exception as e:
            logger.error(f"خطأ في حفظ نتائج التحقق: {str(e)}")
    
    @classmethod
    def generate_balance_health_report(cls, date_to: Optional[date] = None) -> Dict:
        """
        تقرير صحة الأرصدة الشامل
        """
        if not date_to:
            date_to = timezone.now().date()
        
        logger.info(f"إنشاء تقرير صحة الأرصدة لتاريخ {date_to}")
        
        # التحقق من جميع الأرصدة
        balance_validation = cls.validate_all_balances(date_to)
        
        # التحقق من ميزان المراجعة
        trial_balance_validation = cls.validate_trial_balance_integrity(date_to)
        
        # إحصائيات إضافية
        total_assets = cls._calculate_total_by_type('asset', date_to)
        total_liabilities = cls._calculate_total_by_type('liability', date_to)
        total_equity = cls._calculate_total_by_type('equity', date_to)
        
        # معادلة الميزانية: الأصول = الخصوم + حقوق الملكية
        balance_sheet_equation = total_assets - (total_liabilities + total_equity)
        
        report = {
            'report_date': date_to,
            'generated_at': timezone.now(),
            'balance_validation': balance_validation,
            'trial_balance_validation': trial_balance_validation,
            'balance_sheet_totals': {
                'total_assets': total_assets,
                'total_liabilities': total_liabilities,
                'total_equity': total_equity,
                'balance_sheet_equation': balance_sheet_equation,
                'equation_balanced': abs(balance_sheet_equation) <= cls.TOLERANCE
            },
            'health_score': cls._calculate_health_score(
                balance_validation, trial_balance_validation, balance_sheet_equation
            ),
            'recommendations': cls._generate_recommendations(
                balance_validation, trial_balance_validation
            )
        }
        
        logger.info(f"تم إنشاء تقرير صحة الأرصدة - النتيجة: {report['health_score']}/100")
        return report
    
    @classmethod
    def _calculate_total_by_type(cls, account_type: str, date_to: date) -> Decimal:
        """
        حساب إجمالي نوع حسابات معين
        """
        accounts = ChartOfAccounts.objects.filter(
            account_type__category=account_type,
            is_leaf=True,
            is_active=True
        )
        
        total = Decimal('0')
        for account in accounts:
            balance = EnhancedBalanceService.get_account_balance_optimized(
                account, date_to=date_to
            )
            total += balance
        
        return total
    
    @classmethod
    def _calculate_health_score(
        cls,
        balance_validation: Dict,
        trial_balance_validation: Dict,
        balance_sheet_equation: Decimal
    ) -> int:
        """
        حساب نقاط صحة النظام المالي (من 100)
        """
        score = 100
        
        # خصم نقاط للحسابات الخاطئة
        if balance_validation['total_accounts'] > 0:
            error_rate = balance_validation['invalid_accounts'] / balance_validation['total_accounts']
            score -= int(error_rate * 50)  # حتى 50 نقطة
        
        # خصم نقاط لعدم توازن ميزان المراجعة
        if not trial_balance_validation['is_balanced']:
            score -= 30
        
        # خصم نقاط لعدم توازن معادلة الميزانية
        if abs(balance_sheet_equation) > cls.TOLERANCE:
            score -= 20
        
        return max(0, score)
    
    @classmethod
    def _generate_recommendations(
        cls,
        balance_validation: Dict,
        trial_balance_validation: Dict
    ) -> List[str]:
        """
        توليد توصيات لتحسين صحة النظام المالي
        """
        recommendations = []
        
        if balance_validation['invalid_accounts'] > 0:
            recommendations.append(
                f"يوجد {balance_validation['invalid_accounts']} حساب بأرصدة خاطئة - "
                "يُنصح بتشغيل عملية الإصلاح التلقائي"
            )
        
        if not trial_balance_validation['is_balanced']:
            recommendations.append(
                f"ميزان المراجعة غير متوازن بفرق {trial_balance_validation['difference']} - "
                "يجب مراجعة القيود المحاسبية"
            )
        
        if trial_balance_validation['unbalanced_entries']:
            recommendations.append(
                f"يوجد {len(trial_balance_validation['unbalanced_entries'])} قيد غير متوازن - "
                "يجب مراجعة وتصحيح هذه القيود"
            )
        
        if balance_validation['total_discrepancy_amount'] > Decimal('100'):
            recommendations.append(
                "إجمالي الفروقات كبير - يُنصح بإجراء مراجعة شاملة للنظام المالي"
            )
        
        if not recommendations:
            recommendations.append("النظام المالي في حالة جيدة - لا توجد مشاكل مكتشفة")
        
        return recommendations
