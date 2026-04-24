from financial.models import ChartOfAccounts

class ExpenseClassifier:
    """
    خدمة تصنيف المصروفات (Direct Costs vs G&A)
    """
    
    DIRECT_COST_KEYWORDS = [
        'باص', 'نقل', 'كتب', 'زي', 'نشاط', 'رحلات', 'حفلات', 'تعليم'
    ]
    
    GA_KEYWORDS = [
        'كهرباء', 'مياه', 'إيجار', 'نت', 'صيانة', 'نظافة', 'إداري', 'عمومي'
    ]
    
    @classmethod
    def classify_account(cls, account):
        """
        تصنيف حساب المصروفات
        """
        if account.account_type.category != 'expense':
            return 'other'
            
        name = account.name.lower()
        
        for keyword in cls.DIRECT_COST_KEYWORDS:
            if keyword in name:
                return 'direct_cost'
                
        for keyword in cls.GA_KEYWORDS:
            if keyword in name:
                return 'general_administrative'
                
        return 'general_administrative'  # الافتراضي
    
    @classmethod
    def get_direct_costs(cls, period=None):
        """
        الحصول على إجمالي التكاليف المباشرة
        """
        # هذا يتطلب منطقاً أكثر تعقيداً لجلب الأرصدة
        # سنقوم هنا فقط بتحديد الحسابات
        accounts = ChartOfAccounts.objects.filter(account_type__category='expense')
        direct_accounts = []
        for acc in accounts:
            if cls.classify_account(acc) == 'direct_cost':
                direct_accounts.append(acc)
        return direct_accounts
