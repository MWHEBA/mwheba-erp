"""
أدوات التكامل مع النظام المالي الحالي لمعاملات الشريك
"""

from django.db import models
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta

from ..models.partner_transactions import PartnerTransaction, PartnerBalance
from ..models.chart_of_accounts import ChartOfAccounts
from core.models import SystemSetting
try:
    from ..models.partner_transactions import PartnerSettings, PartnerAuditLog
except ImportError:
    # في حالة عدم توفر هذه النماذج بعد
    PartnerSettings = None
    PartnerAuditLog = None


class PartnerFinancialIntegration:
    """
    فئة للتكامل مع النظام المالي الحالي
    """
    
    @staticmethod
    def find_or_create_partner_account(partner_name="محمد يوسف"):
        """
        البحث عن أو إنشاء حساب الشريك
        """
        try:
            # البحث عن الحساب الموجود
            partner_account = ChartOfAccounts.objects.get(
                name__icontains="جاري الشريك",
                is_active=True
            )
            return partner_account
        except ChartOfAccounts.DoesNotExist:
            # إنشاء حساب جديد إذا لم يكن موجوداً
            # البحث عن نوع الحساب المناسب
            try:
                from ..models import AccountType
                account_type = AccountType.objects.filter(
                    name__icontains="جاري"
                ).first()
                
                if not account_type:
                    account_type = AccountType.objects.filter(
                        name__icontains="حسابات"
                    ).first()
                
                partner_account = ChartOfAccounts.objects.create(
                    name=f"جاري الشريك - {partner_name}",
                    code="2100001",  # رمز حساب جاري الشريك
                    account_type=account_type,
                    is_active=True,
                    is_leaf=True,
                    description=f"حساب جاري الشريك {partner_name}"
                )
                
                return partner_account
                
            except Exception as e:
                raise Exception(f"فشل في إنشاء حساب الشريك: {str(e)}")
    
    @staticmethod
    def get_available_cash_accounts():
        """
        جلب الحسابات النقدية المتاحة
        """
        return ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True
        ).filter(
            models.Q(name__icontains="صندوق") |
            models.Q(name__icontains="بنك") |
            models.Q(name__icontains="نقدية") |
            models.Q(account_type__name__icontains="صندوق") |
            models.Q(account_type__name__icontains="بنك")
        ).order_by('name')
    
    @staticmethod
    def validate_transaction_limits(transaction_type, amount, partner_account):
        """
        التحقق من حدود المعاملات - مبسط (بدون قيود)
        """
        # لا توجد قيود أو حدود - السماح بجميع المعاملات
        return True
    
    @staticmethod
    def check_approval_requirements(transaction_type, amount):
        """
        التحقق من متطلبات الموافقة - مبسط (موافقة تلقائية)
        """
        # موافقة تلقائية على جميع المعاملات
        return True
    
    @staticmethod
    def create_partner_transaction(
        transaction_type, 
        partner_account, 
        cash_account, 
        amount, 
        description, 
        created_by,
        contribution_type=None,
        withdrawal_type=None,
        transaction_date=None
    ):
        """
        إنشاء معاملة شريك جديدة مع جميع التحققات
        """
        if not transaction_date:
            transaction_date = timezone.now().date()
        
        # التحقق من حدود المعاملات
        PartnerFinancialIntegration.validate_transaction_limits(
            transaction_type, amount, partner_account
        )
        
        # تحديد حالة الموافقة
        auto_approve = PartnerFinancialIntegration.check_approval_requirements(
            transaction_type, amount
        )
        
        status = 'approved' if auto_approve else 'pending'
        
        # إنشاء المعاملة
        transaction_obj = PartnerTransaction.objects.create(
            transaction_type=transaction_type,
            partner_account=partner_account,
            cash_account=cash_account,
            amount=amount,
            description=description,
            contribution_type=contribution_type,
            withdrawal_type=withdrawal_type,
            transaction_date=transaction_date,
            created_by=created_by,
            status=status
        )
        
        # إكمال المعاملة إذا كانت معتمدة تلقائياً
        if auto_approve:
            success = transaction_obj.complete()
            if success:
                # تحديث رصيد الشريك
                partner_balance, created = PartnerBalance.objects.get_or_create(
                    partner_account=partner_account
                )
                partner_balance.update_balance()
        
        # تسجيل في سجل التدقيق (إذا كان متاحاً)
        if PartnerAuditLog:
            try:
                PartnerAuditLog.log_action(
                    user=created_by,
                    action=f'create_{transaction_type}',
                    description=f'تم إنشاء {transaction_obj.get_transaction_type_display()} بمبلغ {amount} {SystemSetting.get_currency_symbol()}',
                    extra_data={
                        'transaction_id': transaction_obj.id,
                        'amount': float(amount),
                        'status': status
                    }
                )
            except Exception:
                # تجاهل أخطاء سجل التدقيق
                pass
        
        return transaction_obj
    
    @staticmethod
    def get_partner_financial_summary(partner_account, days=30):
        """
        الحصول على ملخص مالي للشريك
        """
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        # المعاملات في الفترة المحددة
        transactions = PartnerTransaction.objects.filter(
            partner_account=partner_account,
            transaction_date__gte=start_date,
            status='completed'
        )
        
        # الإحصائيات
        contributions = transactions.filter(transaction_type='contribution')
        withdrawals = transactions.filter(transaction_type='withdrawal')
        
        summary = {
            'period_days': days,
            'start_date': start_date,
            'end_date': end_date,
            'total_contributions': contributions.aggregate(
                total=models.Sum('amount')
            )['total'] or Decimal('0'),
            'total_withdrawals': withdrawals.aggregate(
                total=models.Sum('amount')
            )['total'] or Decimal('0'),
            'contributions_count': contributions.count(),
            'withdrawals_count': withdrawals.count(),
            'net_flow': Decimal('0'),
        }
        
        summary['net_flow'] = summary['total_contributions'] - summary['total_withdrawals']
        
        # الرصيد الحالي
        partner_balance, created = PartnerBalance.objects.get_or_create(
            partner_account=partner_account
        )
        if created:
            partner_balance.update_balance()
        
        summary['current_balance'] = partner_balance.current_balance
        summary['total_contributions_all_time'] = partner_balance.total_contributions
        summary['total_withdrawals_all_time'] = partner_balance.total_withdrawals
        
        return summary
    
    @staticmethod
    def sync_existing_transactions():
        """
        مزامنة المعاملات الموجودة مع النظام الجديد
        """
        # البحث عن معاملات الشريك في القيود المحاسبية الموجودة
        partner_accounts = ChartOfAccounts.objects.filter(
            name__icontains="جاري الشريك",
            is_active=True
        )
        
        synced_count = 0
        
        for partner_account in partner_accounts:
            # تحديث رصيد الشريك
            partner_balance, created = PartnerBalance.objects.get_or_create(
                partner_account=partner_account
            )
            partner_balance.update_balance()
            synced_count += 1
        
        return synced_count
