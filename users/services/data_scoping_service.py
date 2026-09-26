# -*- coding: utf-8 -*-
"""
Data Scoping Service
Centralized service for data filtering, salesmen scoping, and role-based queryset scoping.
"""
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


class DataScopingService:
    """
    خدمة عزل وتحديد نطاق البيانات (Data Scoping Service)
    تضمن عدم تسريب بيانات غير مخصصة للأدوار الوظيفية
    """

    NON_SALES_ROLES = [
        'accountant',
        'financial_manager',
        'procurement_officer',
        'inventory_manager',
        'production_supervisor',
        'hr_officer',
        'viewer',
        'driver',
    ]

    @staticmethod
    def get_scoped_salesmen(include_user_id=None):
        """
        الحصول على المستخدمين المخولين بالمبيعات (مندوبي ومديري المبيعات)
        مع استبعاد الأدوار المتخصصة غير المبيعات (المحاسبة، المشتريات، المخازن، الموارد البشرية)
        مع إمكانية شمول مستخدم محدد (في حال تعديل سجل قديم)
        """
        # استبعاد الأدوار غير المبيعات صراحة ما لم يكن للمستخدم دور أو صلاحية مبيعات إضافية
        excluded_filter = (
            Q(role__name__in=DataScopingService.NON_SALES_ROLES) &
            ~Q(secondary_roles__name__in=['sales_rep', 'sales_manager']) &
            ~Q(user_permissions__codename__in=['add_sale', 'view_sale', 'add_salesorder', 'add_quotation']) &
            ~Q(custom_permissions__codename__in=['add_sale', 'view_sale', 'add_salesorder', 'add_quotation'])
        )

        base_filter = Q(is_active=True) & ~excluded_filter & ~User.get_hidden_filter()
        if include_user_id:
            base_filter = base_filter | Q(pk=include_user_id)

        return User.objects.filter(base_filter).distinct().order_by('first_name', 'username')

    @staticmethod
    def get_scoped_sales(user, queryset=None):
        """
        عزل وتحديد نطاق فواتير المبيعات بناء على صلاحيات المستخدم:
        - المدير / صاحب صلاحية عرض كل المبيعات: يرى الجميع
        - المحاسب / المدير المالي / مراجع القيود: يرى الجميع (Accountant Blindness Prevention)
        - الأدوار التشغيلية (المحصل / أمين تسليم البضاعة / مشرف الإنتاج): يرى الجميع
        - المندوب الميداني: يرى مبيعاته وما أنشأه فقط
        """
        if queryset is None:
            from sale.models import Sale
            queryset = Sale.objects.all()

        if not user or not user.is_authenticated:
            return queryset.none()

        has_supervisor = (
            user.is_superuser or 
            getattr(user, 'is_admin', False) or 
            user.has_perm('sale.view_all_sales')
        )
        has_financial = (
            getattr(user, 'is_accountant', False) or 
            getattr(user, 'is_financial_manager', False) or 
            user.has_perm('financial.view_journalentry')
        )
        has_operations = (
            user.has_perm('sale.add_salepayment') or 
            user.has_perm('sale.add_deliverynote') or 
            user.has_perm('work_order.view_workorder')
        )

        if has_supervisor or has_financial or has_operations:
            return queryset

        return queryset.filter(Q(salesman=user) | Q(created_by=user))

    @staticmethod
    def get_scoped_quotations(user, queryset=None):
        """
        عزل وتحديد نطاق عروض الأسعار:
        - المدير / مشرف المبيعات / المحاسب: يرى الجميع
        - المندوب: يرى عروضه وما أنشأه فقط
        """
        if queryset is None:
            from sale.models import Quotation
            queryset = Quotation.objects.all()

        if not user or not user.is_authenticated:
            return queryset.none()

        has_supervisor = (
            user.is_superuser or 
            getattr(user, 'is_admin', False) or 
            user.has_perm('sale.view_all_quotations')
        )
        has_financial = (
            getattr(user, 'is_accountant', False) or 
            getattr(user, 'is_financial_manager', False) or 
            user.has_perm('financial.view_journalentry')
        )

        if has_supervisor or has_financial:
            return queryset

        return queryset.filter(Q(salesman=user) | Q(created_by=user))

    @staticmethod
    def get_scoped_sales_orders(user, queryset=None):
        """
        عزل وتحديد نطاق أوامر البيع:
        - المدير / مشرف المبيعات / المحاسب / التشغيل: يرى الجميع
        - المندوب: يرى أوامره وما أنشأه فقط
        """
        if queryset is None:
            from sale.models.sales_models import SalesOrder
            queryset = SalesOrder.objects.all()

        if not user or not user.is_authenticated:
            return queryset.none()

        has_supervisor = (
            user.is_superuser or 
            getattr(user, 'is_admin', False) or 
            user.has_perm('sale.view_all_salesorders')
        )
        has_financial = (
            getattr(user, 'is_accountant', False) or 
            getattr(user, 'is_financial_manager', False) or 
            user.has_perm('financial.view_journalentry')
        )
        has_operations = (
            user.has_perm('sale.add_salepayment') or 
            user.has_perm('sale.add_deliverynote') or 
            user.has_perm('work_order.view_workorder')
        )

        if has_supervisor or has_financial or has_operations:
            return queryset

        return queryset.filter(Q(salesman=user) | Q(created_by=user))

    @staticmethod
    def get_scoped_delivery_notes(user, queryset=None):
        """
        عزل وتحديد نطاق إذون تسليم البضاعة (صرف المخزن):
        - المدير / المشرف / المحاسب: يرى الجميع
        - أمين المخزن: يرى أذون المخازن التي يديرها
        - المندوب: يرى أذون أوامره أو ما أنشأه
        """
        if queryset is None:
            from sale.models.sales_models import DeliveryNote
            queryset = DeliveryNote.objects.all()

        if not user or not user.is_authenticated:
            return queryset.none()

        has_supervisor = (
            user.is_superuser or 
            getattr(user, 'is_admin', False) or 
            user.has_perm('sale.view_all_salesorders') or 
            user.has_perm('sale.view_all_sales')
        )
        has_financial = (
            getattr(user, 'is_accountant', False) or 
            getattr(user, 'is_financial_manager', False) or 
            user.has_perm('financial.view_journalentry')
        )

        if has_supervisor or has_financial:
            return queryset

        return queryset.filter(
            Q(warehouse__manager=user) | 
            Q(sales_order__salesman=user) | 
            Q(created_by=user)
        ).distinct()

    @staticmethod
    def get_scoped_purchases(user, queryset=None):
        """
        عزل وتحديد نطاق فواتير المشتريات:
        - المشتريات والمالية والمخازن بحسب الصلاحية
        """
        if queryset is None:
            from purchase.models.purchase import Purchase
            queryset = Purchase.objects.all()

        if not user or not user.is_authenticated:
            return queryset.none()

        return queryset

    @staticmethod
    def get_scoped_credit_notes(user, queryset=None):
        """
        عزل وتحديد نطاق الإشعارات الدائنة:
        - الإدارة / المالية / مشرف المبيعات: يرى الكل
        - المندوب: يرى إشعارات الفواتير التابعة له أو التي أنشأها بنفسه
        """
        if queryset is None:
            from sale.models import CreditNote
            queryset = CreditNote.objects.all()

        if not user or not user.is_authenticated:
            return queryset.none()

        has_supervisor = (
            user.is_superuser or 
            getattr(user, 'is_admin', False) or 
            user.has_perm('sale.view_all_sales')
        )
        has_financial = (
            getattr(user, 'is_accountant', False) or 
            getattr(user, 'is_financial_manager', False) or 
            user.has_perm('financial.view_journalentry')
        )

        if has_supervisor or has_financial:
            return queryset

        return queryset.filter(
            Q(sale__salesman=user) | 
            Q(sale__created_by=user) | 
            Q(created_by=user)
        ).distinct()

    @staticmethod
    def get_transaction_warehouses(user=None):
        """
        الحصول على المخازن المتاحة لحركات البيع والشراء وإصدار الفواتير
        - المشرف / من يملك view_all_warehouses: يرى كافة المخازن
        - أمين المخزن أو المستخدم المسند له مخازن: يرى المخازن المسندة له
        - المستخدم العام: يرى المخازن النشطة المتاحة
        """
        from product.models.stock_management import Warehouse
        if not user or not user.is_authenticated:
            return Warehouse.objects.filter(is_active=True).order_by('name')

        if user.is_superuser or getattr(user, 'is_admin', False) or user.has_perm('product.view_all_warehouses'):
            return Warehouse.objects.filter(is_active=True).order_by('name')

        managed = Warehouse.objects.filter(is_active=True, manager=user)
        if managed.exists():
            return managed.order_by('name')

        return Warehouse.objects.filter(is_active=True).order_by('name')

    @staticmethod
    def get_managed_warehouses(user):
        """
        الحصول على المخازن المسندة لإدارة المستخدم فعلياً (للجرد والتحويلات المخزنية ومحاضر الاستلام GRN)
        - المدير العام / أصحاب الاطلاع الشامل: يرى كافة المخازن
        - أمين المخزن: يرى فقط المخازن التي يديرها
        """
        from product.models.stock_management import Warehouse
        if not user or not user.is_authenticated:
            return Warehouse.objects.none()

        if user.is_superuser or getattr(user, 'is_admin', False) or user.has_perm('product.view_all_warehouses'):
            return Warehouse.objects.filter(is_active=True).order_by('name')

        return Warehouse.objects.filter(is_active=True, manager=user).order_by('name')

