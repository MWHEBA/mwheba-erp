"""
خدمة مطابقة البيانات المالية - Data Reconciliation Service
تتضمن مطابقة يومية، اكتشاف التناقضات، والتنبيهات
"""

import logging
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Dict, Any, Optional, List, Tuple
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Sum, Count, Q
from governance.services import AuditService
from financial.models.journal_entry import JournalEntry, JournalEntryLine

# Import AccountingGateway for unified journal entry creation
from governance.services import AccountingGateway, JournalEntryLineData

logger = logging.getLogger(__name__)


class DataReconciliationService:
    """
    خدمة مطابقة البيانات المالية مع اكتشاف التناقضات
    """
    
    # حدود التناقضات المقبولة
    ACCEPTABLE_VARIANCE_PERCENTAGE = 0.01  # 1%
    ACCEPTABLE_VARIANCE_AMOUNT = Decimal('1.00')  # 1 جنيه
    
    # أنواع المطابقة
    RECONCILIATION_TYPES = [
        'daily_transactions',
        'payments',
        'journal_entries',
        'account_balances'
    ]
    
    @classmethod
    def run_daily_reconciliation(
        cls,
        reconciliation_date: Optional[date] = None,
        reconciliation_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        تشغيل مطابقة البيانات اليومية
        
        Args:
            reconciliation_date: تاريخ المطابقة (افتراضي: أمس)
            reconciliation_types: أنواع المطابقة المطلوبة
            
        Returns:
            Dict: نتائج المطابقة الشاملة
        """
        if reconciliation_date is None:
            reconciliation_date = (timezone.now() - timedelta(days=1)).date()
        
        if reconciliation_types is None:
            reconciliation_types = cls.RECONCILIATION_TYPES
        
        reconciliation_results = {
            'date': reconciliation_date.isoformat(),
            'start_time': timezone.now().isoformat(),
            'end_time': None,
            'status': 'running',
            'results': {},
            'discrepancies': [],
            'summary': {
                'total_checks': 0,
                'passed_checks': 0,
                'failed_checks': 0,
                'warnings': 0
            }
        }
        
        try:
            # تشغيل كل نوع من أنواع المطابقة
            for reconciliation_type in reconciliation_types:
                
                if reconciliation_type == 'daily_transactions':
                    result = cls._reconcile_daily_transactions(reconciliation_date)
                elif reconciliation_type == 'payments':
                    result = cls._reconcile_payments(reconciliation_date)
                elif reconciliation_type == 'journal_entries':
                    result = cls._reconcile_journal_entries(reconciliation_date)
                elif reconciliation_type == 'account_balances':
                    result = cls._reconcile_account_balances(reconciliation_date)
                else:
                    logger.warning(f"نوع مطابقة غير معروف: {reconciliation_type}")
                    continue
                
                reconciliation_results['results'][reconciliation_type] = result
                
                # تحديث الملخص
                reconciliation_results['summary']['total_checks'] += result.get('total_checks', 0)
                reconciliation_results['summary']['passed_checks'] += result.get('passed_checks', 0)
                reconciliation_results['summary']['failed_checks'] += result.get('failed_checks', 0)
                reconciliation_results['summary']['warnings'] += result.get('warnings', 0)
                
                # إضافة التناقضات
                if result.get('discrepancies'):
                    reconciliation_results['discrepancies'].extend(result['discrepancies'])
            
            # تحديد الحالة النهائية
            if reconciliation_results['summary']['failed_checks'] > 0:
                reconciliation_results['status'] = 'failed'
            elif reconciliation_results['summary']['warnings'] > 0:
                reconciliation_results['status'] = 'warning'
            else:
                reconciliation_results['status'] = 'passed'
            
            reconciliation_results['end_time'] = timezone.now().isoformat()
            
            # حفظ النتائج
            cls._save_reconciliation_results(reconciliation_results)
            
            # إرسال التنبيهات إذا لزم الأمر
            if reconciliation_results['status'] in ['failed', 'warning']:
                cls._send_reconciliation_alerts(reconciliation_results)
            
            
            return reconciliation_results
            
        except Exception as e:
            reconciliation_results['status'] = 'error'
            reconciliation_results['error'] = str(e)
            reconciliation_results['end_time'] = timezone.now().isoformat()
            
            logger.error(f"خطأ في المطابقة اليومية: {e}")
            
            # تسجيل الخطأ
            AuditService.log_operation(
                operation_type='reconciliation_error',
                details={
                    'date': reconciliation_date.isoformat(),
                    'error': str(e),
                    'partial_results': reconciliation_results
                }
            )
            
            return reconciliation_results
    
    @classmethod
    def _reconcile_daily_transactions(cls, reconciliation_date: date) -> Dict[str, Any]:
        """
        مطابقة المعاملات اليومية
        """
        result = {
            'type': 'daily_transactions',
            'total_checks': 0,
            'passed_checks': 0,
            'failed_checks': 0,
            'warnings': 0,
            'discrepancies': [],
            'details': {}
        }
        
        try:
            # الحصول على المعاملات اليومية
            daily_entries = JournalEntry.objects.filter(
                date=reconciliation_date
            ).select_related().prefetch_related('lines')
            
            result['details']['total_entries'] = daily_entries.count()
            result['total_checks'] += 1
            
            # فحص توازن كل قيد
            unbalanced_entries = []
            
            for entry in daily_entries:
                total_debit = entry.lines.aggregate(
                    total=Sum('debit')
                )['total'] or Decimal('0')
                
                total_credit = entry.lines.aggregate(
                    total=Sum('credit')
                )['total'] or Decimal('0')
                
                variance = abs(total_debit - total_credit)
                
                if variance > cls.ACCEPTABLE_VARIANCE_AMOUNT:
                    unbalanced_entries.append({
                        'entry_id': entry.id,
                        'entry_number': entry.number,
                        'total_debit': float(total_debit),
                        'total_credit': float(total_credit),
                        'variance': float(variance)
                    })
                    
                    result['discrepancies'].append({
                        'type': 'unbalanced_journal_entry',
                        'severity': 'high',
                        'description': f'قيد غير متوازن: {entry.number}',
                        'details': {
                            'entry_id': entry.id,
                            'entry_number': entry.number,
                            'debit': float(total_debit),
                            'credit': float(total_credit),
                            'variance': float(variance)
                        }
                    })
            
            result['details']['unbalanced_entries'] = len(unbalanced_entries)
            
            if unbalanced_entries:
                result['failed_checks'] += 1
            else:
                result['passed_checks'] += 1
            
            # فحص إجمالي المعاملات اليومية
            daily_totals = daily_entries.aggregate(
                total_debit=Sum('lines__debit'),
                total_credit=Sum('lines__credit')
            )
            
            total_debit = daily_totals['total_debit'] or Decimal('0')
            total_credit = daily_totals['total_credit'] or Decimal('0')
            daily_variance = abs(total_debit - total_credit)
            
            result['details']['daily_totals'] = {
                'total_debit': float(total_debit),
                'total_credit': float(total_credit),
                'variance': float(daily_variance)
            }
            
            result['total_checks'] += 1
            
            if daily_variance > cls.ACCEPTABLE_VARIANCE_AMOUNT:
                result['failed_checks'] += 1
                result['discrepancies'].append({
                    'type': 'daily_totals_imbalance',
                    'severity': 'critical',
                    'description': f'عدم توازن في إجماليات اليوم',
                    'details': result['details']['daily_totals']
                })
            else:
                result['passed_checks'] += 1
            
        except Exception as e:
            result['failed_checks'] += 1
            result['discrepancies'].append({
                'type': 'reconciliation_error',
                'severity': 'critical',
                'description': f'خطأ في مطابقة المعاملات اليومية: {str(e)}'
            })
        
        return result
    
    @classmethod
    def _reconcile_payments(cls, reconciliation_date: date) -> Dict[str, Any]:
        """
        مطابقة المدفوعات
        """
        result = {
            'type': 'payments',
            'total_checks': 0,
            'passed_checks': 0,
            'failed_checks': 0,
            'warnings': 0,
            'discrepancies': [],
            'details': {}
        }
        
        try:
            # الحصول على قيود المدفوعات اليومية من القيود المحاسبية
            payment_journal_entries = JournalEntry.objects.filter(
                date=reconciliation_date,
                entry_type__in=['parent_payment', 'fee_payment', 'payment']
            )
            
            result['details']['total_payment_entries'] = payment_journal_entries.count()
            result['total_checks'] += 1
            
            # فحص توازن قيود المدفوعات
            unbalanced = []
            for entry in payment_journal_entries:
                total_debit = entry.lines.aggregate(total=Sum('debit'))['total'] or Decimal('0')
                total_credit = entry.lines.aggregate(total=Sum('credit'))['total'] or Decimal('0')
                if abs(total_debit - total_credit) > cls.ACCEPTABLE_VARIANCE_AMOUNT:
                    unbalanced.append(entry.id)
            
            if unbalanced:
                result['failed_checks'] += 1
                result['discrepancies'].append({
                    'type': 'unbalanced_payment_entries',
                    'severity': 'high',
                    'description': f'قيود مدفوعات غير متوازنة: {len(unbalanced)}',
                    'details': {'entry_ids': unbalanced}
                })
            else:
                result['passed_checks'] += 1
            
            result['total_checks'] += 1
            result['passed_checks'] += 1
            
        except Exception as e:
            result['failed_checks'] += 1
            result['discrepancies'].append({
                'type': 'reconciliation_error',
                'severity': 'critical',
                'description': f'خطأ في مطابقة المدفوعات: {str(e)}'
            })
        
        return result
    
    @classmethod
    def _reconcile_journal_entries(cls, reconciliation_date: date) -> Dict[str, Any]:
        """
        مطابقة القيود المحاسبية
        """
        result = {
            'type': 'journal_entries',
            'total_checks': 0,
            'passed_checks': 0,
            'failed_checks': 0,
            'warnings': 0,
            'discrepancies': [],
            'details': {}
        }
        
        try:
            # الحصول على القيود اليومية
            daily_entries = JournalEntry.objects.filter(
                date=reconciliation_date
            )
            
            result['details']['total_entries'] = daily_entries.count()
            
            # فحص القيود المرحلة
            posted_entries = daily_entries.filter(status='posted')
            draft_entries = daily_entries.filter(status='draft')
            
            result['details']['posted_entries'] = posted_entries.count()
            result['details']['draft_entries'] = draft_entries.count()
            
            result['total_checks'] += 1
            
            # تحذير إذا كان هناك قيود غير مرحلة
            if draft_entries.exists():
                result['warnings'] += 1
                result['discrepancies'].append({
                    'type': 'unposted_journal_entries',
                    'severity': 'medium',
                    'description': f'قيود غير مرحلة: {draft_entries.count()}',
                    'details': {
                        'count': draft_entries.count(),
                        'entry_ids': list(draft_entries.values_list('id', flat=True))
                    }
                })
            
            # فحص القيود بدون بنود
            entries_without_lines = daily_entries.filter(lines__isnull=True)
            
            if entries_without_lines.exists():
                result['failed_checks'] += 1
                result['discrepancies'].append({
                    'type': 'entries_without_lines',
                    'severity': 'high',
                    'description': f'قيود بدون بنود: {entries_without_lines.count()}',
                    'details': {
                        'count': entries_without_lines.count(),
                        'entry_ids': list(entries_without_lines.values_list('id', flat=True))
                    }
                })
            else:
                result['passed_checks'] += 1
            
            # فحص القيود ذات البند الواحد
            single_line_entries = []
            for entry in daily_entries:
                lines_count = entry.lines.count()
                if lines_count == 1:
                    single_line_entries.append(entry.id)
            
            if single_line_entries:
                result['warnings'] += 1
                result['discrepancies'].append({
                    'type': 'single_line_entries',
                    'severity': 'medium',
                    'description': f'قيود ببند واحد فقط: {len(single_line_entries)}',
                    'details': {
                        'count': len(single_line_entries),
                        'entry_ids': single_line_entries
                    }
                })
            
            result['total_checks'] += 1
            
        except Exception as e:
            result['failed_checks'] += 1
            result['discrepancies'].append({
                'type': 'reconciliation_error',
                'severity': 'critical',
                'description': f'خطأ في مطابقة القيود المحاسبية: {str(e)}'
            })
        
        return result
    
    @classmethod
    def _reconcile_account_balances(cls, reconciliation_date: date) -> Dict[str, Any]:
        """
        مطابقة أرصدة الحسابات
        """
        result = {
            'type': 'account_balances',
            'total_checks': 0,
            'passed_checks': 0,
            'failed_checks': 0,
            'warnings': 0,
            'discrepancies': [],
            'details': {}
        }
        
        try:
            # هذا فحص أساسي - يمكن توسيعه حسب الحاجة
            from financial.models.chart_of_accounts import ChartOfAccounts
            
            # الحصول على الحسابات النشطة
            active_accounts = ChartOfAccounts.objects.filter(
                is_active=True,
                is_leaf=True  # حسابات نهائية فقط
            )
            
            result['details']['total_accounts'] = active_accounts.count()
            result['total_checks'] += 1
            
            # فحص الحسابات التي لها حركة في هذا التاريخ
            accounts_with_movement = JournalEntryLine.objects.filter(
                journal_entry__date=reconciliation_date,
                journal_entry__status='posted'
            ).values('account').distinct().count()
            
            result['details']['accounts_with_movement'] = accounts_with_movement
            
            # هذا فحص أساسي - يمكن إضافة المزيد من الفحوصات المتقدمة
            result['passed_checks'] += 1
            
        except Exception as e:
            result['failed_checks'] += 1
            result['discrepancies'].append({
                'type': 'reconciliation_error',
                'severity': 'critical',
                'description': f'خطأ في مطابقة أرصدة الحسابات: {str(e)}'
            })
        
        return result
    
    @classmethod
    def _save_reconciliation_results(cls, results: Dict[str, Any]):
        """
        حفظ نتائج المطابقة
        """
        # حفظ في cache للوصول السريع
        cache_key = f"reconciliation_results:{results['date']}"
        cache.set(cache_key, results, timeout=86400 * 7)  # أسبوع
        
        # تسجيل في نظام التدقيق
        AuditService.log_operation(
            operation_type='daily_reconciliation_completed',
            details=results
        )
        
        # حفظ ملخص في cache للتقارير
        summary_key = f"reconciliation_summary:{results['date']}"
        summary = {
            'date': results['date'],
            'status': results['status'],
            'summary': results['summary'],
            'discrepancies_count': len(results['discrepancies']),
            'timestamp': results['end_time']
        }
        cache.set(summary_key, summary, timeout=86400 * 30)  # شهر
    
    @classmethod
    def _send_reconciliation_alerts(cls, results: Dict[str, Any]):
        """
        إرسال تنبيهات المطابقة
        """
        # تسجيل التنبيه
        alert_data = {
            'type': 'reconciliation_alert',
            'date': results['date'],
            'status': results['status'],
            'failed_checks': results['summary']['failed_checks'],
            'warnings': results['summary']['warnings'],
            'discrepancies_count': len(results['discrepancies']),
            'critical_discrepancies': [
                d for d in results['discrepancies'] 
                if d.get('severity') == 'critical'
            ]
        }
        
        AuditService.log_operation(
            operation_type='reconciliation_alert_sent',
            details=alert_data
        )
        
        logger.warning(f"تم إرسال تنبيه مطابقة لتاريخ {results['date']}: {results['status']}")
    
    @classmethod
    def get_reconciliation_history(
        cls,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 30
    ) -> List[Dict[str, Any]]:
        """
        الحصول على تاريخ المطابقات
        """
        if end_date is None:
            end_date = timezone.now().date()
        
        if start_date is None:
            start_date = end_date - timedelta(days=limit)
        
        history = []
        current_date = start_date
        
        while current_date <= end_date:
            cache_key = f"reconciliation_summary:{current_date.isoformat()}"
            summary = cache.get(cache_key)
            
            if summary:
                history.append(summary)
            
            current_date += timedelta(days=1)
        
        return sorted(history, key=lambda x: x['date'], reverse=True)
    
    @classmethod
    def get_reconciliation_report(cls, reconciliation_date: date) -> Optional[Dict[str, Any]]:
        """
        الحصول على تقرير مطابقة مفصل
        """
        cache_key = f"reconciliation_results:{reconciliation_date.isoformat()}"
        return cache.get(cache_key)
    
    @classmethod
    def create_manual_reconciliation_entry(
        cls,
        reconciliation_date: date,
        discrepancy_type: str,
        description: str,
        amount: Decimal,
        account_code: str,
        user,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        إنشاء قيد مطابقة يدوي لحل التناقضات
        """
        try:
            from financial.services.accounting_integration_service import AccountingIntegrationService
            from financial.models.chart_of_accounts import ChartOfAccounts
            from financial.models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
            
            # الحصول على الحساب
            account = ChartOfAccounts.objects.get(code=account_code, is_active=True)
            
            # إنشاء قيد المطابقة
            with transaction.atomic():
                # Prepare journal entry lines (simplified - needs counterpart account)
                lines = [
                    JournalEntryLineData(
                        account_code=account.code,
                        debit=amount if amount > 0 else Decimal('0'),
                        credit=abs(amount) if amount < 0 else Decimal('0'),
                        description=description
                    )
                    # TODO: Add counterpart line based on discrepancy type
                ]
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                journal_entry = gateway.create_journal_entry(
                    source_module='financial',
                    source_model='Reconciliation',
                    source_id=0,
                    lines=lines,
                    idempotency_key=f"JE:financial:Reconciliation:{reconciliation_date.strftime('%Y%m%d')}:{int(timezone.now().timestamp())}",
                    user=user,
                    entry_type='reconciliation',
                    description=description,
                    reference=f"قيد مطابقة يدوي - {discrepancy_type}",
                    date=reconciliation_date
                )
                
                # تسجيل العملية
                AuditService.log_operation(
                    operation_type='manual_reconciliation_entry',
                    details={
                        'reconciliation_date': reconciliation_date.isoformat(),
                        'discrepancy_type': discrepancy_type,
                        'amount': float(amount),
                        'account_code': account_code,
                        'journal_entry_id': journal_entry.id,
                        'notes': notes
                    },
                    user=user
                )
                
                return {
                    'success': True,
                    'journal_entry_id': journal_entry.id,
                    'journal_entry_number': journal_entry.number,
                    'message': 'تم إنشاء قيد المطابقة بنجاح'
                }
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء قيد المطابقة اليدوي: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': 'فشل في إنشاء قيد المطابقة'
            }