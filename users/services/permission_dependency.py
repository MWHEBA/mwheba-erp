# -*- coding: utf-8 -*-
"""
Permission Dependency Engine
خدمة إدارة شجرة الاعتماديات المسبقة الصريحة وحلها للأدوار والمستخدمين.
"""
from typing import List, Set, Dict
import logging
from django.contrib.auth.models import Permission

logger = logging.getLogger(__name__)

class PermissionDependencyService:
    """
    خدمة حساب وحل التبعيات المسبقة للصلاحيات المركبة
    """
    # خريطة التبعيات المسبقة الصريحة المعيارية: الصلاحية المركبة -> الصلاحيات التمهيدية المطلوبة (app_label.codename)
    DEPENDENCY_MAP: Dict[str, List[str]] = {
        # مبيعات وعروض أسعار
        'sale.add_sale': [
            'customer.view_customer', 'product.view_product', 'financial.view_currency',
            'product.view_unit', 'product.view_warehouse', 'sale.view_sale'
        ],
        'sale.change_sale': [
            'customer.view_customer', 'product.view_product', 'financial.view_currency',
            'product.view_unit', 'product.view_warehouse', 'sale.view_sale'
        ],
        'sale.view_sale': [
            'financial.view_currency', 'product.view_warehouse', 'product.view_unit',
            'product.view_category', 'customer.view_customer', 'product.view_product',
            'financial.view_taxrate'
        ],
        'sale.add_quotation': [
            'customer.view_customer', 'product.view_product', 'financial.view_currency',
            'product.view_unit', 'sale.view_quotation'
        ],
        'sale.change_quotation': [
            'customer.view_customer', 'product.view_product', 'financial.view_currency',
            'product.view_unit', 'sale.view_quotation'
        ],
        'sale.add_salesorder': [
            'customer.view_customer', 'product.view_product', 'financial.view_currency',
            'product.view_unit', 'product.view_warehouse', 'sale.view_salesorder'
        ],
        'sale.change_salesorder': [
            'customer.view_customer', 'product.view_product', 'financial.view_currency',
            'product.view_unit', 'product.view_warehouse', 'sale.view_salesorder'
        ],
        'sale.convert_quotation': [
            'sale.view_quotation', 'sale.add_sale', 'product.view_product', 'customer.view_customer'
        ],
        'sale.convert_to_order': [
            'sale.view_quotation', 'sale.add_salesorder', 'product.view_product', 'customer.view_customer'
        ],
        'sale.approve_sales_order': [
            'sale.view_salesorder'
        ],
        'sale.add_deliverynote': [
            'customer.view_customer', 'product.view_product', 'product.view_warehouse',
            'product.view_unit', 'sale.view_deliverynote', 'sale.view_salesorder'
        ],
        'sale.add_salereturn': [
            'customer.view_customer', 'product.view_product', 'product.view_warehouse',
            'product.view_unit', 'sale.view_salereturn'
        ],
        'sale.view_creditnote': [
            'customer.view_customer', 'financial.view_currency'
        ],
        'sale.add_creditnote': [
            'customer.view_customer', 'sale.view_creditnote', 'financial.view_currency', 'sale.view_sale'
        ],

        
        # مشتريات وموردين
        'purchase.add_purchase': [
            'supplier.view_supplier', 'product.view_product', 'financial.view_currency',
            'product.view_unit', 'product.view_warehouse', 'purchase.view_purchase'
        ],
        'purchase.change_purchase': [
            'supplier.view_supplier', 'product.view_product', 'financial.view_currency',
            'product.view_unit', 'product.view_warehouse', 'purchase.view_purchase'
        ],
        'purchase.view_purchase': [
            'financial.view_currency', 'product.view_warehouse', 'product.view_unit',
            'product.view_category', 'supplier.view_supplier', 'product.view_product',
            'financial.view_taxrate'
        ],
        'purchase.add_purchaseorder': [
            'supplier.view_supplier', 'product.view_product', 'financial.view_currency',
            'product.view_unit', 'purchase.view_purchaseorder'
        ],
        'purchase.change_purchaseorder': [
            'supplier.view_supplier', 'product.view_product', 'financial.view_currency',
            'product.view_unit', 'purchase.view_purchaseorder'
        ],
        'purchase.add_goodsreceivednote': [
            'supplier.view_supplier', 'product.view_product', 'product.view_warehouse',
            'product.view_unit', 'purchase.view_goodsreceivednote'
        ],
        'purchase.add_purchasereturn': [
            'supplier.view_supplier', 'product.view_product', 'product.view_warehouse',
            'product.view_unit', 'purchase.view_purchasereturn'
        ],
        
        # عملاء وموردين
        'customer.add_customer': ['customer.view_customer'],
        'customer.change_customer': ['customer.view_customer'],
        'customer.delete_customer': ['customer.view_customer'],
        'supplier.add_supplier': ['supplier.view_supplier'],
        'supplier.change_supplier': ['supplier.view_supplier'],
        'supplier.delete_supplier': ['supplier.view_supplier'],
        
        # منتجات ومخازن
        'product.add_product': ['product.view_product', 'product.view_unit'],
        'product.change_product': ['product.view_product'],
        'product.delete_product': ['product.view_product'],
        'product.add_stockmovement': ['product.view_warehouse', 'product.view_product', 'product.view_unit', 'product.view_stock'],
        'product.add_stocktransfer': ['product.view_warehouse', 'product.view_product', 'product.view_unit', 'product.view_stock'],
        'product.add_inventoryadjustment': ['product.view_warehouse', 'product.view_product', 'product.view_stock', 'product.view_inventoryadjustment'],
        'product.add_batchvoucher': ['product.view_warehouse', 'product.view_product', 'product.view_batchvoucher'],
        'product.add_warehouse': ['product.view_warehouse'],
        'product.change_warehouse': ['product.view_warehouse'],
        
        # مالية وحسابات
        'financial.add_journalentry': [
            'financial.view_chartofaccounts', 'financial.view_currency',
            'financial.view_accountingperiod', 'financial.view_journalentry'
        ],
        'financial.change_journalentry': [
            'financial.view_chartofaccounts', 'financial.view_currency',
            'financial.view_accountingperiod', 'financial.view_journalentry'
        ],
        'financial.add_paymentvoucher': [
            'financial.view_chartofaccounts', 'financial.view_currency', 'financial.view_paymentvoucher'
        ],
        'financial.add_receiptvoucher': [
            'financial.view_chartofaccounts', 'financial.view_currency', 'financial.view_receiptvoucher'
        ],
        'financial.add_chartofaccounts': ['financial.view_chartofaccounts'],
        'financial.change_chartofaccounts': ['financial.view_chartofaccounts'],
        'financial.add_currency': ['financial.view_currency'],
        'financial.change_currency': ['financial.view_currency'],
        
        # أوامر شغل وتسعير مطبوعات
        'printing_pricing.add_pricingorder': ['product.view_product', 'product.view_unit', 'customer.view_customer'],
        'printing_pricing.add_printingorder': [
            'product.view_product', 'product.view_unit', 'customer.view_customer',
            'printing_pricing.view_printingorder'
        ],
        'printing_pricing.change_printingorder': ['printing_pricing.view_printingorder'],
        'work_order.add_workorder': ['work_order.view_workorder', 'product.view_product', 'customer.view_customer'],
        'work_order.change_workorder': ['work_order.view_workorder'],

        # خريطة التوافق العكسي بالأسماء المجردة (Bare codenames)
        'add_sale': ['view_customer', 'view_product', 'view_currency', 'view_unit', 'view_warehouse', 'view_sale'],
        'change_sale': ['view_customer', 'view_product', 'view_currency', 'view_unit', 'view_warehouse', 'view_sale'],
        'add_quotation': ['view_customer', 'view_product', 'view_currency', 'view_unit', 'view_quotation'],
        'change_quotation': ['view_customer', 'view_product', 'view_currency', 'view_unit', 'view_quotation'],
        'add_salesorder': ['view_customer', 'view_product', 'view_currency', 'view_unit', 'view_warehouse', 'view_salesorder'],
        'add_purchase': ['view_supplier', 'view_product', 'view_currency', 'view_unit', 'view_warehouse', 'view_purchase'],
        'change_purchase': ['view_supplier', 'view_product', 'view_currency', 'view_unit', 'view_warehouse', 'view_purchase'],
        'add_purchaseorder': ['view_supplier', 'view_product', 'view_currency', 'view_unit', 'view_purchaseorder'],
        'add_customer': ['view_customer'],
        'change_customer': ['view_customer'],
        'delete_customer': ['view_customer'],
        'add_supplier': ['view_supplier'],
        'change_supplier': ['view_supplier'],
        'delete_supplier': ['view_supplier'],
        'add_product': ['view_product', 'view_unit'],
        'change_product': ['view_product'],
        'delete_product': ['view_product'],
        'add_stockmovement': ['view_warehouse', 'view_product', 'view_unit', 'view_stock'],
        'add_stocktransfer': ['view_warehouse', 'view_product', 'view_unit', 'view_stock'],
        'add_journalentry': ['view_chartofaccounts', 'view_currency', 'view_accountingperiod', 'view_journalentry'],
        'add_paymentvoucher': ['view_chartofaccounts', 'view_currency', 'view_paymentvoucher'],
        'add_receiptvoucher': ['view_chartofaccounts', 'view_currency', 'view_receiptvoucher'],
    }

    # خريطة التوافق العكسي بالأسماء المجردة
    BARE_DEPENDENCY_MAP: Dict[str, List[str]] = {
        k: v for k, v in DEPENDENCY_MAP.items() if '.' not in k
    }

    @classmethod
    def get_unified_dependency_map(cls) -> Dict[str, List[str]]:
        """دمج الخريطتين لضمان إرجاع التبعيات بصيغة app_label وبصيغة codename مجردة"""
        merged = dict(cls.DEPENDENCY_MAP)
        merged.update(cls.BARE_DEPENDENCY_MAP)
        return merged

    @classmethod
    def get_required_dependencies(cls, permissions_list: List[str]) -> Set[str]:
        """
        حساب كافة الاعتماديات التمهيدية المطلوبة لقائمة من الصلاحيات.
        ترجع كلاً من الصيغة المؤهلة والصيغة المجردة لضمان التوافق العكسي التام 100%.
        """
        required: Set[str] = set()
        for perm in permissions_list:
            clean_name = perm.split('.')[-1] if '.' in perm else perm
            # 1. مطابقة من الخريطة المعيارية
            for parent_key, deps in cls.DEPENDENCY_MAP.items():
                if parent_key == perm or parent_key.split('.')[-1] == clean_name:
                    for dep in deps:
                        required.add(dep)
                        # إضافة النسخة المجردة أيضاً لدعم الاختبارات القديمة
                        required.add(dep.split('.')[-1])
            # 2. مطابقة من خريطة الأسماء المجردة
            if clean_name in cls.BARE_DEPENDENCY_MAP:
                for dep in cls.BARE_DEPENDENCY_MAP[clean_name]:
                    required.add(dep)
        return required

    @classmethod
    def auto_resolve_dependencies_for_role(cls, role) -> int:
        """
        فحص وحل تبعيات الدور وإضافة الصلاحيات التمهيدية الناقصة صراحة للدور في قاعدة البيانات.
        تستخدم مطابقة ثنائية آمنة (content_type__app_label, codename).
        """
        from django.db.models import Q
        current_perms = list(role.permissions.select_related('content_type').all())
        current_formatted = {f"{p.content_type.app_label}.{p.codename}" for p in current_perms}
        
        required_dep_formatted = cls.get_required_dependencies(list(current_formatted))
        missing_formatted = required_dep_formatted - current_formatted
        
        if not missing_formatted:
            return 0
            
        # بناء استعلام ثنائي صارم لمنع الـ codename collisions
        query = Q()
        for item in missing_formatted:
            if '.' in item:
                app_label, codename = item.split('.', 1)
                query |= Q(content_type__app_label=app_label, codename=codename)
            else:
                query |= Q(codename=item)
                
        missing_perms = Permission.objects.filter(query)
        if missing_perms.exists():
            role.permissions.add(*missing_perms)
            logger.info(f"Auto-resolved {missing_perms.count()} prerequisite permissions for role '{role.name}'")
            return missing_perms.count()
            
        return 0

    @classmethod
    def auto_resolve_dependencies_for_user(cls, user) -> int:
        """
        فحص وحل تبعيات الصلاحيات المخصصة للمستخدم وإضافة الصلاحيات التمهيدية الناقصة صراحة.
        """
        from django.db.models import Q
        current_perms = list(user.custom_permissions.select_related('content_type').all())
        current_formatted = {f"{p.content_type.app_label}.{p.codename}" for p in current_perms}
        
        required_dep_formatted = cls.get_required_dependencies(list(current_formatted))
        missing_formatted = required_dep_formatted - current_formatted
        
        if not missing_formatted:
            return 0
            
        query = Q()
        for item in missing_formatted:
            if '.' in item:
                app_label, codename = item.split('.', 1)
                query |= Q(content_type__app_label=app_label, codename=codename)
            else:
                query |= Q(codename=item)
                
        missing_perms = Permission.objects.filter(query)
        if missing_perms.exists():
            user.custom_permissions.add(*missing_perms)
            if hasattr(user, 'user_permissions'):
                user.user_permissions.add(*missing_perms)
            logger.info(f"Auto-resolved {missing_perms.count()} prerequisite permissions for user '{user.username}'")
            return missing_perms.count()
            
        return 0

