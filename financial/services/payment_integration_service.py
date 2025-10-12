"""
خدمة التكامل المالي الموحدة للمدفوعات
ربط شامل ومحترف بين المدفوعات والنظام المالي مع معالجة جميع السيناريوهات
"""
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any, Union
import logging
import traceback
from datetime import date, datetime

from ..models.chart_of_accounts import ChartOfAccounts
from ..models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
from ..services.journal_service import JournalEntryService
from ..services.payment_sync_service import payment_sync_service

logger = logging.getLogger(__name__)
User = get_user_model()


class PaymentIntegrationError(Exception):
    """استثناء خاص بأخطاء التكامل المالي"""
    pass


class PaymentIntegrationService:
    """
    خدمة التكامل المالي الموحدة والشاملة للمدفوعات
    
    الميزات:
    - ربط كامل بين المدفوعات والنظام المالي
    - إنشاء حركات خزن وقيود محاسبية تلقائية
    - معالجة جميع السيناريوهات والحالات الاستثنائية
    - نظام rollback متقدم
    - تتبع شامل للأخطاء والعمليات
    """
    
    # أكواد الحسابات المحاسبية الافتراضية (حسب دليل الحسابات المعتمد)
    DEFAULT_ACCOUNTS = {
        'cash': '11011',                   # الصندوق الرئيسي
        'bank': '11021',                   # البنك الأهلي
        'accounts_receivable': '11030',    # العملاء
        'accounts_payable': '21010',       # الموردون
        'sales_revenue': '41010',          # إيرادات المبيعات
        'purchase_expense': '51010',       # تكلفة البضاعة المباعة
    }
    
    # ملاحظة: تم إزالة نظام CashMovement - الخدمة تعمل مع القيود المحاسبية فقط
    
    @classmethod
    def process_payment(
        cls,
        payment,
        payment_type: str,
        user: Optional[User] = None,
        force_sync: bool = False
    ) -> Dict[str, Any]:
        """
        معالجة شاملة للدفعة وربطها بالنظام المالي
        
        Args:
            payment: كائن الدفعة (SalePayment أو PurchasePayment)
            payment_type: نوع الدفعة ('sale' أو 'purchase')
            user: المستخدم المنفذ للعملية
            force_sync: إجبار التزامن حتى لو كانت الدفعة مربوطة مسبقاً
            
        Returns:
            Dict يحتوي على نتائج العملية
        """
        operation_id = f"{payment_type}_{payment.id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            logger.info(f"بدء معالجة الدفعة - العملية: {operation_id}")
            
            # التحقق من صحة البيانات
            cls._validate_payment_data(payment, payment_type)
            
            # التحقق من إمكانية الربط
            if not force_sync and payment.is_financially_synced:
                return {
                    'success': True,
                    'message': 'الدفعة مربوطة مالياً مسبقاً',
                    'operation_id': operation_id,
                    'already_synced': True
                }
            
            # بدء المعاملة الذرية
            with transaction.atomic():
                result = cls._execute_payment_integration(
                    payment, payment_type, user, operation_id
                )
                
                # تسجيل نجاح العملية
                logger.info(f"تم ربط الدفعة بنجاح - العملية: {operation_id}")
                
                return result
                
        except Exception as e:
            # معالجة الأخطاء وتسجيلها
            error_message = str(e)
            logger.error(f"فشل في معالجة الدفعة - العملية: {operation_id} - الخطأ: {error_message}")
            logger.error(f"تفاصيل الخطأ: {traceback.format_exc()}")
            
            # تحديث حالة الدفعة
            payment.mark_financial_sync_failed(error_message)
            
            return {
                'success': False,
                'message': f'فشل في ربط الدفعة: {error_message}',
                'operation_id': operation_id,
                'error': error_message,
                'error_type': type(e).__name__
            }
    
    @classmethod
    def _validate_payment_data(cls, payment, payment_type: str):
        """التحقق من صحة بيانات الدفعة"""
        
        # التحقق من نوع الدفعة
        if payment_type not in ['sale', 'purchase']:
            raise PaymentIntegrationError(f"نوع دفعة غير صحيح: {payment_type}")
        
        # التحقق من وجود الحساب المالي
        if not payment.financial_account:
            raise PaymentIntegrationError("يجب تحديد الحساب المالي للدفعة")
        
        # التحقق من أن الحساب نقدي أو بنكي
        if not (payment.financial_account.is_cash_account or payment.financial_account.is_bank_account):
            raise PaymentIntegrationError("الحساب المحدد ليس حساباً نقدياً أو بنكياً")
        
        # التحقق من المبلغ
        if not payment.amount or payment.amount <= 0:
            raise PaymentIntegrationError("مبلغ الدفعة يجب أن يكون أكبر من صفر")
        
        # التحقق من تاريخ الدفع
        if not payment.payment_date:
            raise PaymentIntegrationError("يجب تحديد تاريخ الدفع")
        
        # التحقق من وجود الفاتورة المرتبطة
        if payment_type == 'sale' and not hasattr(payment, 'sale'):
            raise PaymentIntegrationError("دفعة المبيعات يجب أن ترتبط بفاتورة مبيعات")
        
        if payment_type == 'purchase' and not hasattr(payment, 'purchase'):
            raise PaymentIntegrationError("دفعة المشتريات يجب أن ترتبط بفاتورة مشتريات")
    
    @classmethod
    def _execute_payment_integration(
        cls,
        payment,
        payment_type: str,
        user: Optional[User],
        operation_id: str
    ) -> Dict[str, Any]:
        """تنفيذ عملية الربط المالي"""
        
        # إنشاء القيد المحاسبي
        journal_entry = cls._create_journal_entry(payment, payment_type, user)
        
        # ربط القيد بالدفعة
        payment.mark_financial_sync_success(journal_entry, None)
        
        # تزامن مع الخدمات الأخرى
        cls._sync_with_other_services(payment, payment_type, user)
        
        return {
            'success': True,
            'message': 'تم ربط الدفعة بالنظام المالي بنجاح',
            'operation_id': operation_id,
            'journal_entry_id': journal_entry.id,
            'journal_entry_number': journal_entry.number
        }
    
    
    @classmethod
    def _ensure_accounting_period(cls, payment_date: date) -> AccountingPeriod:
        """التأكد من وجود فترة محاسبية أو إنشاء واحدة"""
        
        # البحث عن فترة محاسبية موجودة
        period = AccountingPeriod.get_period_for_date(payment_date)
        
        if not period:
            # إنشاء فترة محاسبية تلقائية للسنة
            year = payment_date.year
            period, created = AccountingPeriod.objects.get_or_create(
                start_date=date(year, 1, 1),
                end_date=date(year, 12, 31),
                defaults={
                    'name': f'السنة المالية {year}',
                    'status': 'open'
                }
            )
            if created:
                logger.info(f"تم إنشاء فترة محاسبية تلقائية: {period.name}")
        
        return period
    
    @classmethod
    def _create_journal_entry(
        cls,
        payment,
        payment_type: str,
        user: Optional[User]
    ) -> JournalEntry:
        """إنشاء قيد محاسبي للدفعة"""
        
        # التأكد من وجود فترة محاسبية
        cls._ensure_accounting_period(payment.payment_date)
        
        # تحديد أرقام الحسابات
        cash_account_code = payment.financial_account.code
        
        if payment_type == 'sale':
            # دفعة مبيعات: مدين الخزينة/البنك، دائن حساب العميل المحدد
            
            # استخدام الحساب المالي للعميل المحدد بدلاً من الحساب العام
            customer = payment.sale.customer
            if customer.financial_account:
                customer_account = customer.financial_account
                logger.info(f"استخدام حساب العميل المحدد: {customer_account.code} - {customer_account.name}")
            else:
                # إذا لم يكن للعميل حساب محدد، استخدم الحساب العام
                customer_account_code = cls.DEFAULT_ACCOUNTS['accounts_receivable']
                try:
                    customer_account = ChartOfAccounts.objects.get(code=customer_account_code, is_active=True)
                except ChartOfAccounts.DoesNotExist:
                    logger.warning(f"حساب العملاء {customer_account_code} غير موجود - سيتم استخدام حساب بديل")
                    # محاولة إيجاد أي حساب عملاء
                    customer_account = ChartOfAccounts.objects.filter(
                        name__icontains='عميل',
                        is_active=True,
                        is_leaf=True  # التأكد من أنه حساب نهائي
                    ).first()
                    if not customer_account:
                        raise PaymentIntegrationError(f"لا يوجد حساب عملاء نشط ونهائي في النظام")
            
            # التحقق من أن الحساب يمكن إدراج قيود عليه
            if not customer_account.can_post_entries():
                raise PaymentIntegrationError(f"لا يمكن إدراج قيود على حساب العميل {customer_account.code} - {customer_account.name}")
            
            # إنشاء القيد
            journal_entry = JournalEntryService.create_simple_entry(
                debit_account=cash_account_code,
                credit_account=customer_account.code,
                amount=payment.amount,
                description=f"دفعة من العميل {payment.sale.customer.name} - فاتورة {payment.sale.number}",
                date=payment.payment_date,
                reference=f"SALE-PAY-{payment.id}",
                user=user or payment.created_by
            )
            
        else:  # purchase
            # دفعة مشتريات: مدين حساب المورد المحدد، دائن الخزينة/البنك
            
            # استخدام الحساب المالي للمورد المحدد بدلاً من الحساب العام
            supplier = payment.purchase.supplier
            if supplier.financial_account:
                supplier_account = supplier.financial_account
                logger.info(f"استخدام حساب المورد المحدد: {supplier_account.code} - {supplier_account.name}")
            else:
                # إذا لم يكن للمورد حساب محدد، استخدم الحساب العام
                supplier_account_code = cls.DEFAULT_ACCOUNTS['accounts_payable']
                try:
                    supplier_account = ChartOfAccounts.objects.get(code=supplier_account_code, is_active=True)
                except ChartOfAccounts.DoesNotExist:
                    logger.warning(f"حساب الموردين {supplier_account_code} غير موجود - سيتم استخدام حساب بديل")
                    # محاولة إيجاد أي حساب موردين
                    supplier_account = ChartOfAccounts.objects.filter(
                        name__icontains='مورد',
                        is_active=True,
                        is_leaf=True  # التأكد من أنه حساب نهائي
                    ).first()
                    if not supplier_account:
                        raise PaymentIntegrationError(f"لا يوجد حساب موردين نشط ونهائي في النظام")
            
            # التحقق من أن الحساب يمكن إدراج قيود عليه
            if not supplier_account.can_post_entries():
                raise PaymentIntegrationError(f"لا يمكن إدراج قيود على حساب المورد {supplier_account.code} - {supplier_account.name}")
            
            # إنشاء القيد
            journal_entry = JournalEntryService.create_simple_entry(
                debit_account=supplier_account.code,
                credit_account=cash_account_code,
                amount=payment.amount,
                description=f"دفعة للمورد {payment.purchase.supplier.name} - فاتورة {payment.purchase.number}",
                date=payment.payment_date,
                reference=f"PURCH-PAY-{payment.id}",
                user=user or payment.created_by
            )
        
        return journal_entry
    
    
    @classmethod
    def _sync_with_other_services(cls, payment, payment_type: str, user: Optional[User]):
        """تزامن مع الخدمات الأخرى في النظام"""
        
        # ملاحظة: تم تعطيل استدعاء payment_sync_service لتجنب إنشاء قيود مكررة
        # الخدمة الحالية (PaymentIntegrationService) تقوم بكل العمليات المطلوبة
        
        logger.info(f"تم تخطي التزامن مع الخدمات القديمة - الخدمة الجديدة تتولى كل شيء")
        
        # يمكن إضافة تزامن مع خدمات أخرى هنا إذا لزم الأمر
        # مثل: تحديث الإحصائيات، إرسال إشعارات، إلخ
        pass
    
    
    
    @classmethod
    def get_integration_status(cls, payment) -> Dict[str, Any]:
        """الحصول على حالة الربط المالي للدفعة"""
        
        return {
            'is_synced': payment.is_financially_synced,
            'can_be_synced': payment.can_be_synced,
            'financial_status': payment.financial_status,
            'financial_error': payment.financial_error,
            'has_journal_entry': bool(payment.financial_transaction),
            'journal_entry_number': payment.financial_transaction.number if payment.financial_transaction else None,
        }
    
    @classmethod
    def bulk_sync_payments(
        cls,
        payments: List,
        payment_type: str,
        user: Optional[User] = None
    ) -> Dict[str, Any]:
        """مزامنة مجموعة من الدفعات دفعة واحدة"""
        
        results = {
            'total': len(payments),
            'success': 0,
            'failed': 0,
            'already_synced': 0,
            'errors': []
        }
        
        for payment in payments:
            try:
                result = cls.process_payment(payment, payment_type, user)
                
                if result['success']:
                    if result.get('already_synced'):
                        results['already_synced'] += 1
                    else:
                        results['success'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append({
                        'payment_id': payment.id,
                        'error': result.get('error', 'خطأ غير معروف')
                    })
                    
            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'payment_id': payment.id,
                    'error': str(e)
                })
        
        return results


# إنشاء instance عام للخدمة
payment_integration_service = PaymentIntegrationService()
