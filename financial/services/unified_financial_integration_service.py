"""
خدمة التكامل المالي الموحدة
تتعامل مع التكامل بين النظام المالي والأنظمة الأخرى
"""

from django.db import transaction
from django.contrib.auth.models import User
from typing import Optional
import logging

from financial.models import ChartOfAccounts
from .unified_account_service import UnifiedAccountService

logger = logging.getLogger(__name__)


class UnifiedFinancialIntegrationService:
    """خدمة التكامل المالي الموحدة"""
    
    @classmethod
    def create_parent_account(cls, parent, user: Optional[User] = None) -> Optional[ChartOfAccounts]:
        """
        إنشاء حساب محاسبي لولي الأمر باستخدام الخدمة الموحدة
        
        Args:
            parent: نموذج ولي الأمر
            user: المستخدم الذي ينشئ الحساب
            
        Returns:
            ChartOfAccounts: الحساب المحاسبي الجديد أو None في حالة الفشل
        """
        try:
            return UnifiedAccountService.create_parent_account(parent, user)
        except Exception as e:
            logger.error(f"❌ فشل في إنشاء حساب ولي الأمر عبر الخدمة الموحدة: {e}")
            return None
    
    @classmethod
    def create_supplier_account(cls, supplier, user: Optional[User] = None) -> Optional[ChartOfAccounts]:
        """
        إنشاء حساب محاسبي للمورد باستخدام الخدمة الموحدة
        
        Args:
            supplier: نموذج المورد
            user: المستخدم الذي ينشئ الحساب
            
        Returns:
            ChartOfAccounts: الحساب المحاسبي الجديد أو None في حالة الفشل
        """
        try:
            return UnifiedAccountService.create_supplier_account(supplier, user)
        except Exception as e:
            logger.error(f"❌ فشل في إنشاء حساب المورد عبر الخدمة الموحدة: {e}")
            return None