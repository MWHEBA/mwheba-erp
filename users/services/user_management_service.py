# -*- coding: utf-8 -*-
"""
User Management Service

Enhanced user management service following unified service patterns with
optimized queries and bulk operations support.
"""

from django.db import transaction, DatabaseError
from django.db.models import Count, Q, Prefetch
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.models import Permission
from typing import List, Dict, Any, Optional
import logging

from core.services.base_service import TransactionalService, BulkOperationService
from governance.thread_safety import monitor_operation
from governance.services.audit_service import AuditService
from ..models import User, Role
from .permission_service import PermissionService
from .permission_cache import PermissionCacheService

logger = logging.getLogger('users.user_management_service')


class UserManagementService(TransactionalService):
    """
    Enhanced User Management Service following unified patterns.
    
    Features:
    - Optimized database queries with select_related/prefetch_related
    - Bulk operations support
    - Caching integration
    - User statistics with custom permissions only
    - Permission summaries for users
    - Integration with PermissionService for filtering
    """
    
    def perform_operation(self, action: str, *args, **kwargs) -> Any:
        """
        Perform user management operations.
        
        Args:
            action: Operation to perform
            *args: Operation arguments
            **kwargs: Operation keyword arguments
            
        Returns:
            Any: Operation result
        """
        if action == 'get_users_with_stats':
            return self._get_users_with_permission_stats()
        elif action == 'get_user_summary':
            return self._get_permission_summary_for_user(kwargs['user'])
        elif action == 'get_system_stats':
            return self._get_system_permission_statistics()
        elif action == 'update_user_permissions':
            return self._update_user_custom_permissions(
                kwargs['user'], kwargs['permission_ids'], kwargs['updated_by']
            )
        elif action == 'search_users':
            return self._search_users(
                kwargs.get('query', ''),
                kwargs.get('role_id'),
                kwargs.get('has_permissions')
            )
        else:
            raise ValueError(f"عملية غير مدعومة: {action}")
    
    def _get_users_with_permission_stats(self) -> List[Dict[str, Any]]:
        """
        Get all users with their custom permission statistics using optimized queries.
        Only counts the custom business-relevant permissions.
        
        Returns:
            list: Users with permission statistics
        """
        with monitor_operation("get_users_with_permission_stats"):
            try:
                # Get custom permission IDs once to avoid repeated queries
                custom_perm_ids = list(PermissionService.get_custom_permissions_only().values_list('id', flat=True))
                
                # Optimized query with all necessary relations (including inactive users)
                users = User.objects.all().select_related('role').prefetch_related(
                    'secondary_roles',
                    Prefetch(
                        'custom_permissions',
                        queryset=Permission.objects.filter(id__in=custom_perm_ids),
                        to_attr='cached_user_custom_permissions'
                    ),
                    Prefetch(
                        'user_permissions',
                        queryset=Permission.objects.filter(id__in=custom_perm_ids),
                        to_attr='cached_custom_permissions'
                    ),
                    Prefetch(
                        'role__permissions',
                        queryset=Permission.objects.filter(id__in=custom_perm_ids),
                        to_attr='cached_role_custom_permissions'
                    )
                )
                
                result = []
                for user in users:
                    # Count custom permissions efficiently using cached attributes
                    direct_perm_ids = {p.id for p in getattr(user, 'cached_custom_permissions', [])} | {p.id for p in getattr(user, 'cached_user_custom_permissions', [])}
                    direct_custom_count = len(direct_perm_ids)
                    role_custom_count = 0
                    
                    if user.role and hasattr(user.role, 'cached_role_custom_permissions'):
                        role_custom_count = len(user.role.cached_role_custom_permissions)
                    
                    # Total unique custom permissions (avoid double counting)
                    role_perm_ids = set()
                    if user.role and hasattr(user.role, 'cached_role_custom_permissions'):
                        role_perm_ids = {p.id for p in user.role.cached_role_custom_permissions}
                    
                    total_custom_count = len(direct_perm_ids | role_perm_ids)
                    
                    user_data = {
                        'user': user,
                        'user_id': user.id,
                        'username': user.username,
                        'full_name': user.get_full_name(),
                        'email': user.email,
                        'is_active': user.is_active,
                        'is_superuser': user.is_superuser,
                        'last_login': user.last_login,
                        'date_joined': user.date_joined,
                        'custom_permissions_count': total_custom_count,
                        'role_name': user.role.display_name if user.role else 'بدون دور',
                        'role_id': user.role.id if user.role else None,
                        'role_permissions_count': role_custom_count,
                        'direct_permissions_count': direct_custom_count,
                        'total_custom_permissions': len(custom_perm_ids)
                    }
                    
                    result.append(user_data)
                
                # Sort by custom permissions count (descending)
                result.sort(key=lambda x: x['custom_permissions_count'], reverse=True)
                
                logger.info(f"Retrieved permission statistics for {len(result)} users")
                return result
                
            except ValidationError as e:
                logger.error(f"Validation error getting users with permission stats: {e}")
                return []
            except DatabaseError as e:
                logger.error(f"Database error getting users with permission stats: {e}")
                return []
            except Exception as e:
                logger.error(f"Unexpected error getting users with permission stats: {e}")
                return []
    
    def _get_permission_summary_for_user(self, user: User) -> Dict[str, Any]:
        """
        Get detailed permission summary for a specific user with optimized queries.
        Shows breakdown by categories and includes only custom permissions.
        
        Args:
            user: User to get summary for
            
        Returns:
            dict: Detailed permission summary
        """
        with monitor_operation("get_permission_summary_for_user"):
            try:
                # Try cache first
                cached_summary = PermissionCacheService.get_user_summary(user.id)
                if cached_summary:
                    return cached_summary
                
                # Get custom permission IDs
                custom_perm_ids = list(PermissionService.get_custom_permissions_only().values_list('id', flat=True))
                
                # Optimized query for user with custom permissions only
                user = User.objects.select_related('role').prefetch_related(
                    Prefetch(
                        'user_permissions',
                        queryset=Permission.objects.filter(id__in=custom_perm_ids).select_related('content_type'),
                        to_attr='cached_custom_permissions'
                    ),
                    Prefetch(
                        'role__permissions',
                        queryset=Permission.objects.filter(id__in=custom_perm_ids).select_related('content_type'),
                        to_attr='cached_role_custom_permissions'
                    )
                ).get(id=user.id)
                
                # Get user's custom permissions efficiently
                direct_perms = getattr(user, 'cached_custom_permissions', [])
                role_perms = []
                if user.role and hasattr(user.role, 'cached_role_custom_permissions'):
                    role_perms = user.role.cached_role_custom_permissions
                
                # Combine permissions (avoid duplicates)
                all_user_perms = {}
                for perm in direct_perms:
                    all_user_perms[perm.id] = perm
                for perm in role_perms:
                    all_user_perms[perm.id] = perm
                
                user_custom_perms = list(all_user_perms.values())
                
                # Get categorized custom permissions
                categorized_permissions = PermissionService.get_categorized_custom_permissions()
                
                # Build summary by category
                category_summary = {}
                total_assigned = 0
                total_available = 0
                
                for category_key, category_data in categorized_permissions.items():
                    category_perms = category_data['permissions']
                    total_available += len(category_perms)
                    
                    # Find which permissions in this category the user has
                    user_perm_ids = {p.id for p in user_custom_perms}
                    user_has_perms = [
                        perm for perm in category_perms 
                        if perm.id in user_perm_ids
                    ]
                    
                    assigned_count = len(user_has_perms)
                    total_assigned += assigned_count
                    
                    category_summary[category_key] = {
                        'name': category_data['name'],
                        'name_en': category_data['name_en'],
                        'icon': category_data['icon'],
                        'description': category_data['description'],
                        'total_permissions': len(category_perms),
                        'assigned_permissions': assigned_count,
                        'percentage': round((assigned_count / len(category_perms)) * 100, 1) if category_perms else 0,
                        'permissions': [
                            {
                                'id': perm.id,
                                'codename': perm.codename,
                                'name': perm.name,
                                'assigned': perm in user_has_perms
                            }
                            for perm in category_perms
                        ]
                    }
                
                # Overall summary
                overall_percentage = round((total_assigned / total_available) * 100, 1) if total_available > 0 else 0
                
                summary = {
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'full_name': user.get_full_name(),
                        'email': user.email,
                        'is_active': user.is_active,
                        'is_superuser': user.is_superuser
                    },
                    'role': {
                        'id': user.role.id if user.role else None,
                        'name': user.role.display_name if user.role else 'بدون دور',
                        'description': user.role.description if user.role else None
                    },
                    'permissions_overview': {
                        'total_available_custom': total_available,
                        'total_assigned_custom': total_assigned,
                        'overall_percentage': overall_percentage,
                        'categories_count': len(categorized_permissions)
                    },
                    'categories': category_summary,
                    'generated_at': timezone.now().isoformat()
                }
                
                # Cache the summary
                PermissionCacheService.set_user_summary(user.id, summary)
                
                return summary
                
            except ValidationError as e:
                logger.error(f"Validation error getting permission summary for user {user.id}: {e}")
                return {}
            except DatabaseError as e:
                logger.error(f"Database error getting permission summary for user {user.id}: {e}")
                return {}
            except Exception as e:
                logger.error(f"Unexpected error getting permission summary for user {user.id}: {e}")
                return {}
    
    def _get_system_permission_statistics(self) -> Dict[str, Any]:
        """
        Get system-wide permission statistics with optimized queries.
        
        Returns:
            dict: System permission statistics
        """
        with monitor_operation("get_system_permission_statistics"):
            try:
                # Basic counts with optimized queries
                total_users = User.objects.filter(is_active=True).count()
                total_roles = Role.objects.filter(is_active=True).count()
                total_custom_permissions = PermissionService.get_custom_permissions_only().count()
                
                # Users with roles
                users_with_roles = User.objects.filter(role__isnull=False, is_active=True).count()
                
                # Users with direct custom permissions - optimized query
                custom_perm_ids = PermissionService.get_custom_permissions_only().values_list('id', flat=True)
                users_with_direct_custom_perms = User.objects.filter(
                    user_permissions__in=custom_perm_ids,
                    is_active=True
                ).distinct().count()
                
                # Role usage statistics with optimized queries
                roles_with_counts = Role.objects.filter(is_active=True).annotate(
                    active_users_count=Count('users', filter=Q(users__is_active=True))
                ).prefetch_related(
                    Prefetch(
                        'permissions',
                        queryset=Permission.objects.filter(id__in=custom_perm_ids)
                    )
                )
                
                role_usage = {}
                for role in roles_with_counts:
                    custom_perms_count = len(role.permissions.all())
                    
                    role_usage[role.display_name] = {
                        'users_count': role.active_users_count,
                        'custom_permissions_count': custom_perms_count,
                        'percentage_of_custom': round((custom_perms_count / total_custom_permissions) * 100, 1) if total_custom_permissions > 0 else 0
                    }
                
                # Category statistics
                categorized_permissions = PermissionService.get_categorized_custom_permissions()
                category_stats = {}
                for category_key, category_data in categorized_permissions.items():
                    category_stats[category_key] = {
                        'name': category_data['name'],
                        'permissions_count': len(category_data['permissions']),
                        'percentage_of_total': round((len(category_data['permissions']) / total_custom_permissions) * 100, 1) if total_custom_permissions > 0 else 0
                    }
                
                return {
                    'overview': {
                        'total_active_users': total_users,
                        'total_active_roles': total_roles,
                        'total_custom_permissions': total_custom_permissions,
                        'users_with_roles': users_with_roles,
                        'users_without_roles': total_users - users_with_roles,
                        'users_with_direct_custom_permissions': users_with_direct_custom_perms,
                        'role_assignment_rate': round((users_with_roles / total_users) * 100, 1) if total_users > 0 else 0
                    },
                    'role_usage': role_usage,
                    'category_distribution': category_stats,
                    'generated_at': timezone.now().isoformat()
                }
                
            except Exception as e:
                logger.error(f"Error getting system permission statistics: {e}")
                return {}
    
    @transaction.atomic
    def _update_user_custom_permissions(self, user: User, permission_ids: List[int], updated_by: User) -> bool:
        """
        Update user's direct custom permissions with optimized operations.
        Only allows assignment of custom business-relevant permissions.
        
        Args:
            user: User to update permissions for
            permission_ids: List of permission IDs to assign
            updated_by: User performing the update
            
        Returns:
            bool: True if successful
        """
        with monitor_operation("update_user_custom_permissions"):
            try:
                # Validate permissions
                if not updated_by.has_perm('users.change_user') and not updated_by.is_superuser:
                    raise ValidationError("Insufficient permissions to update user permissions")
                
                # Get custom permissions only with optimized query
                custom_permissions = PermissionService.get_custom_permissions_only()
                valid_permission_ids = set(custom_permissions.values_list('id', flat=True))
                
                # Filter to only allow custom permissions
                filtered_permission_ids = [
                    pid for pid in permission_ids 
                    if pid in valid_permission_ids
                ]
                
                # Store old permissions for audit
                old_custom_perms = list(user.user_permissions.filter(
                    id__in=valid_permission_ids
                ).values_list('codename', flat=True))
                
                # Update user's direct permissions (only custom ones)
                user.user_permissions.clear()
                user.custom_permissions.clear()
                if filtered_permission_ids:
                    new_permissions = custom_permissions.filter(id__in=filtered_permission_ids)
                    user.user_permissions.set(new_permissions)
                    user.custom_permissions.set(new_permissions)
                
                # Invalidate cache
                if hasattr(user, '_cached_permissions'):
                    delattr(user, '_cached_permissions')
                PermissionCacheService.invalidate_user_cache(user.id)
                
                # New permissions for audit
                new_custom_perms = list(user.user_permissions.filter(
                    id__in=valid_permission_ids
                ).values_list('codename', flat=True))
                
                # Log the update
                AuditService.log_operation(
                    model_name='User',
                    object_id=user.id,
                    operation='UPDATE_CUSTOM_PERMISSIONS',
                    source_service='UserManagementService',
                    user=updated_by,
                    before_data={'custom_permissions': old_custom_perms},
                    after_data={'custom_permissions': new_custom_perms},
                    target_user_id=user.id
                )
                
                logger.info(f"Custom permissions updated for user '{user.username}' by '{updated_by.username}'")
                return True
                
            except Exception as e:
                logger.error(f"Error updating user custom permissions: {e}")
                raise
    
    def _search_users(self, query: str = '', role_id: int = None, has_permissions: bool = None) -> List[Dict[str, Any]]:
        """
        Search users with filtering options using optimized queries.
        
        Args:
            query: Search query for username, email, or full name
            role_id: Filter by specific role ID
            has_permissions: Filter by whether user has custom permissions
            
        Returns:
            list: Filtered users with stats
        """
        with monitor_operation("search_users"):
            try:
                # Start with all users (including inactive)
                users_query = User.objects.all()
                
                # Apply search query
                if query:
                    users_query = users_query.filter(
                        Q(username__icontains=query) |
                        Q(first_name__icontains=query) |
                        Q(last_name__icontains=query) |
                        Q(email__icontains=query)
                    )
                
                # Filter by role
                if role_id:
                    users_query = users_query.filter(role_id=role_id)
                
                # Filter by permissions
                if has_permissions is not None:
                    custom_perm_ids = PermissionService.get_custom_permissions_only().values_list('id', flat=True)
                    if has_permissions:
                        users_query = users_query.filter(
                            Q(user_permissions__in=custom_perm_ids) |
                            Q(role__permissions__in=custom_perm_ids)
                        ).distinct()
                    else:
                        users_query = users_query.exclude(
                            Q(user_permissions__in=custom_perm_ids) |
                            Q(role__permissions__in=custom_perm_ids)
                        ).distinct()
                
                # Optimize query with necessary relations
                users = users_query.select_related('role').prefetch_related(
                    Prefetch(
                        'user_permissions',
                        queryset=Permission.objects.filter(id__in=PermissionService.get_custom_permissions_only().values_list('id', flat=True))
                    ),
                    Prefetch(
                        'role__permissions',
                        queryset=Permission.objects.filter(id__in=PermissionService.get_custom_permissions_only().values_list('id', flat=True))
                    )
                )
                
                result = []
                for user in users:
                    # Count custom permissions efficiently
                    direct_perms = set(user.user_permissions.all())
                    role_perms = set(user.role.permissions.all() if user.role else [])
                    total_custom_perms = len(direct_perms | role_perms)
                    
                    result.append({
                        'user': user,
                        'user_id': user.id,
                        'username': user.username,
                        'full_name': user.get_full_name(),
                        'email': user.email,
                        'role_name': user.role.display_name if user.role else 'بدون دور',
                        'custom_permissions_count': total_custom_perms,
                        'last_login': user.last_login
                    })
                
                logger.info(f"User search returned {len(result)} results")
                return result
                
            except Exception as e:
                logger.error(f"Error searching users: {e}")
                return []

    @staticmethod
    def invalidate_user_sessions(user_id: int):
        """
        إنهاء وحذف كافة الجلسات النشطة للمستخدم فوراً من قاعدة البيانات
        """
        try:
            from django.contrib.sessions.models import Session
            now = timezone.now()
            for session in Session.objects.filter(expire_date__gte=now):
                try:
                    data = session.get_decoded()
                    if str(data.get('_auth_user_id')) == str(user_id):
                        session.delete()
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Could not invalidate user sessions for user {user_id}: {e}")

    @staticmethod
    def can_delete_user(user: User, current_user=None) -> tuple[bool, list[dict], str]:
        """
        فحص استباقي شامل لشروط حذف المستخدم:
        1. منع حذف الحساب الحالي.
        2. منع حذف مدير النظام الرئيسي (superuser).
        3. منع حذف المستخدم إذا كان نشطاً (يجب تعطيله وأرشفته أولاً).
        4. منع حذف المستخدم إذا كان مربوطاً بملف موظف HR.
        5. فحص شامل لكافة المعاملات والعمليات في كافة موديولات النظام.
        """
        if current_user and user.pk == current_user.pk:
            return False, [], "لا يمكنك حذف حسابك الخاص المسجل به حالياً!"

        if user.is_superuser:
            return False, [], "لا يمكن حذف مدير النظام الرئيسي لأسباب أمنية وتشغيلية!"

        if user.is_active:
            return False, [], "لا يمكن حذف المستخدم لأنه ما زال في حالة 'نشط'. يجب تعطيل الحساب أولاً ونقله إلى الأرشيف قبل محاولة الحذف."

        operations_summary = []

        # 1. فحص ملف الموظف في الموارد البشرية
        try:
            from hr.models import Employee
            if Employee.objects.filter(user=user).exists():
                operations_summary.append({
                    'label': 'ملف وظيفي وسجلات بالموارد البشرية',
                    'count': 1,
                    'icon': 'fas fa-id-card'
                })
        except Exception:
            pass

        # 2. فحص المبيعات والعملاء وعروض الأسعار
        try:
            from sale.models import Sale, SalesOrder, Quotation, CreditNote
            sales_count = Sale.objects.filter(Q(created_by=user) | Q(sales_person=user)).count()
            if sales_count > 0:
                operations_summary.append({'label': 'فواتير ومبيعات', 'count': sales_count, 'icon': 'fas fa-file-invoice-dollar'})

            orders_count = SalesOrder.objects.filter(created_by=user).count()
            if orders_count > 0:
                operations_summary.append({'label': 'أوامر بيع', 'count': orders_count, 'icon': 'fas fa-shopping-cart'})

            quotations_count = Quotation.objects.filter(created_by=user).count()
            if quotations_count > 0:
                operations_summary.append({'label': 'عروض أسعار', 'count': quotations_count, 'icon': 'fas fa-file-alt'})

            credit_notes_count = CreditNote.objects.filter(created_by=user).count()
            if credit_notes_count > 0:
                operations_summary.append({'label': 'إشعارات دائنة', 'count': credit_notes_count, 'icon': 'fas fa-undo'})
        except Exception:
            pass

        # فحص إسناد مندوب مبيعات للعملاء
        try:
            from customer.models import Customer
            assigned_customers = Customer.objects.filter(sales_rep=user).count()
            if assigned_customers > 0:
                operations_summary.append({'label': 'عملاء مسندين كمندوب مبيعات', 'count': assigned_customers, 'icon': 'fas fa-users'})
        except Exception:
            pass

        # 3. فحص المشتريات والموردين
        try:
            from purchase.models import Purchase, PurchaseOrder, SupplierBill, PurchaseReturn, PurchasePayment
            purchases_count = Purchase.objects.filter(created_by=user).count()
            if purchases_count > 0:
                operations_summary.append({'label': 'فواتير مشتريات', 'count': purchases_count, 'icon': 'fas fa-shopping-bag'})

            po_count = PurchaseOrder.objects.filter(Q(created_by=user) | Q(approved_by=user)).count()
            if po_count > 0:
                operations_summary.append({'label': 'أوامر شراء', 'count': po_count, 'icon': 'fas fa-truck-loading'})

            bills_count = SupplierBill.objects.filter(created_by=user).count()
            if bills_count > 0:
                operations_summary.append({'label': 'فواتير موردين', 'count': bills_count, 'icon': 'fas fa-receipt'})

            returns_count = PurchaseReturn.objects.filter(created_by=user).count()
            if returns_count > 0:
                operations_summary.append({'label': 'مرتجعات مشتريات', 'count': returns_count, 'icon': 'fas fa-reply'})

            payments_count = PurchasePayment.objects.filter(Q(created_by=user) | Q(posted_by=user)).count()
            if payments_count > 0:
                operations_summary.append({'label': 'مدفوعات موردين', 'count': payments_count, 'icon': 'fas fa-money-check-alt'})
        except Exception:
            pass

        # 4. فحص المحاسبة والمالية والموافقات
        try:
            from financial.models import JournalEntry, FinancialTransaction, OpeningBalanceBatch, FXRevaluationRun
            je_count = JournalEntry.objects.filter(Q(created_by=user) | Q(posted_by=user) | Q(locked_by=user)).count()
            if je_count > 0:
                operations_summary.append({'label': 'قيود يومية محاسبية', 'count': je_count, 'icon': 'fas fa-calculator'})

            ft_count = FinancialTransaction.objects.filter(Q(created_by=user) | Q(approved_by=user)).count()
            if ft_count > 0:
                operations_summary.append({'label': 'معاملات وسندات مالية', 'count': ft_count, 'icon': 'fas fa-money-bill-wave'})

            ob_count = OpeningBalanceBatch.objects.filter(Q(created_by=user) | Q(approved_by=user) | Q(posted_by=user)).count()
            if ob_count > 0:
                operations_summary.append({'label': 'دفعات أرصدة افتتاحية', 'count': ob_count, 'icon': 'fas fa-balance-scale'})

            fx_count = FXRevaluationRun.objects.filter(created_by=user).count()
            if fx_count > 0:
                operations_summary.append({'label': 'جلسات إعادة تقييم عملات', 'count': fx_count, 'icon': 'fas fa-coins'})
        except Exception:
            pass

        # فحص سلاسل الموافقات المؤسسية
        try:
            from financial.models.approval import EnterpriseApprovalStep, EnterpriseApprovalRequest
            steps_count = EnterpriseApprovalStep.objects.filter(action_by=user).count()
            if steps_count > 0:
                operations_summary.append({'label': 'خطوات وسجلات موافقات مالية', 'count': steps_count, 'icon': 'fas fa-check-double'})

            reqs_count = EnterpriseApprovalRequest.objects.filter(Q(requested_by=user) | Q(approved_by=user)).count()
            if reqs_count > 0:
                operations_summary.append({'label': 'طلبات موافقات مؤسسية', 'count': reqs_count, 'icon': 'fas fa-clipboard-check'})
        except Exception:
            pass

        # 5. فحص المخازن والإنتاج وتسعير الطباعة (Rule 4: مصطلحات المخازن الموحدة)
        try:
            from product.models import StockMovement, StockTransfer, InventoryAdjustment
            sm_count = StockMovement.objects.filter(created_by=user).count()
            if sm_count > 0:
                operations_summary.append({'label': 'حركات مخزنية', 'count': sm_count, 'icon': 'fas fa-boxes'})

            st_count = StockTransfer.objects.filter(created_by=user).count()
            if st_count > 0:
                operations_summary.append({'label': 'تحويلات مخزنية', 'count': st_count, 'icon': 'fas fa-dolly'})

            ia_count = InventoryAdjustment.objects.filter(created_by=user).count()
            if ia_count > 0:
                operations_summary.append({'label': 'تسويات مخزنية', 'count': ia_count, 'icon': 'fas fa-clipboard-list'})
        except Exception:
            pass

        try:
            from work_order.models import WorkOrder
            wo_count = WorkOrder.objects.filter(created_by=user).count()
            if wo_count > 0:
                operations_summary.append({'label': 'أوامر تشغيل وشغل', 'count': wo_count, 'icon': 'fas fa-industry'})
        except Exception:
            pass

        try:
            from printing_pricing.models import PrintingOrder
            ppo_count = PrintingOrder.objects.filter(Q(created_by=user) | Q(sales_rep=user)).count()
            if ppo_count > 0:
                operations_summary.append({'label': 'طلبات تسعير طباعة', 'count': ppo_count, 'icon': 'fas fa-print'})
        except Exception:
            pass

        # 6. فحص سجلات النشاطات المنفذة بواسطة هذا المستخدم
        try:
            from users.models import ActivityLog
            al_count = ActivityLog.objects.filter(user=user).count()
            if al_count > 0:
                operations_summary.append({'label': 'سجلات نشاطات وتدقيق في النظام', 'count': al_count, 'icon': 'fas fa-history'})
        except Exception:
            pass

        # 7. فحص ملف الموظف في HR
        try:
            if hasattr(user, 'employee_profile') and user.employee_profile:
                emp = user.employee_profile
                operations_summary.append({
                    'label': f'ملف موظف في الموارد البشرية ({emp.name} - {emp.employee_number})',
                    'count': 1,
                    'icon': 'fas fa-id-card'
                })
        except Exception:
            pass

        # 8. فحص تلقائي لأي جداول مرتبطة متبقية
        excluded_relations = {
            'users_with_custom_permissions', 'users_with_revoked_permissions',
            'secondary_roles', 'groups', 'user_permissions', 'logentry'
        }
        total_operations = sum(item['count'] for item in operations_summary)

        if total_operations == 0:
            for rel in user._meta.related_objects:
                accessor_name = rel.get_accessor_name()
                if accessor_name in excluded_relations:
                    continue
                try:
                    rel_manager = getattr(user, accessor_name, None)
                    if rel_manager is not None and hasattr(rel_manager, 'count'):
                        c = rel_manager.count()
                        if c > 0:
                            verbose_name = getattr(rel.related_model._meta, 'verbose_name_plural', rel.related_model.__name__)
                            operations_summary.append({
                                'label': f'سجلات {verbose_name}',
                                'count': c,
                                'icon': 'fas fa-database'
                            })
                            total_operations += c
                except Exception:
                    pass

        if total_operations > 0:
            ops_details = "، ".join([f"{item['label']} ({item['count']})" for item in operations_summary[:3]])
            if len(operations_summary) > 3:
                ops_details += f" وغيرها ({len(operations_summary) - 3} أنواع أخرى)"
            user_display = user.get_full_name() or user.username
            msg = f"لا يمكن حذف المستخدم '{user_display}' نهائياً لوجود {total_operations} عملية وسجل مرتبط به في النظام ({ops_details}). يمكنك الإبقاء عليه معطلاً في الأرشيف لحفظ سجلات التدقيق."
            return False, operations_summary, msg

        return True, [], ""

    @staticmethod
    @transaction.atomic
    def delete_user(user: User, current_user=None) -> dict:
        """
        حذف نهائي آمن للمستخدم بعد التحقق من شروط الحذف الصارمة
        """
        locked_user = User.objects.select_for_update().get(pk=user.pk)
        can_del, summary, error_msg = UserManagementService.can_delete_user(locked_user, current_user=current_user)
        if not can_del:
            return {
                'success': False,
                'message': error_msg,
                'operations_summary': summary
            }

        user_name = locked_user.get_full_name() or locked_user.username
        user_id = locked_user.id

        # تنظيف الجلسات وكاش الصلاحيات
        UserManagementService.invalidate_user_sessions(user_id)
        PermissionCacheService.invalidate_user_cache(user_id)

        # حذف نهائي عبر force=True لتخطي فحص النموذج بعد اجتياز فحص السيرفيس
        locked_user.delete(force=True)
        logger.info(f"✅ تم حذف المستخدم {user_name} (ID: {user_id}) نهائياً بنجاح لعدم وجود أي عمليات مرتبطة به")

        return {
            'success': True,
            'message': f"تم حذف المستخدم '{user_name}' نهائياً بنجاح لعدم وجود أي عمليات مرتبطة به."
        }

    @staticmethod
    @transaction.atomic
    def toggle_user_status(user: User, current_user=None, target_active: Optional[bool] = None) -> dict:
        """
        التبديل بين تفعيل الحساب أو تعطيله وأرشفته فورياً
        مع حماية آخر مدير نشط، وإنهاء الجلسات اللحظي، ومزامنة الحالات
        """
        locked_user = User.objects.select_for_update().get(pk=user.pk)

        if target_active is None:
            new_active = not locked_user.is_active
        else:
            new_active = bool(target_active)

        user_name = locked_user.get_full_name() or locked_user.username

        if not new_active:
            # 1. منع تعطيل الحساب الشخصي
            if current_user and locked_user.pk == current_user.pk:
                return {
                    'success': False,
                    'message': "لا يمكنك تعطيل حسابك الخاص المسجل به حالياً!"
                }

            # 2. قفل أمان آخر مدير نشط في النظام
            if locked_user.is_superuser:
                active_superusers = User.objects.filter(is_superuser=True, is_active=True).exclude(pk=locked_user.pk).count()
                if active_superusers == 0:
                    return {
                        'success': False,
                        'message': "لا يمكن تعطيل مدير النظام الرئيسي لأنه المدير النشط الوحيد المتبقي في النظام!"
                    }

            if locked_user.role and locked_user.role.name == 'admin':
                active_admins = User.objects.filter(role__name='admin', is_active=True).exclude(pk=locked_user.pk).count()
                active_superusers = User.objects.filter(is_superuser=True, is_active=True).exclude(pk=locked_user.pk).count()
                if active_admins == 0 and active_superusers == 0:
                    return {
                        'success': False,
                        'message': "لا يمكن تعطيل هذا المستخدم لأنه المشرف الإداري النشط الوحيد المتبقي في النظام!"
                    }

        # تحديث الحالة والمزامنة
        locked_user.is_active = new_active
        locked_user.status = "active" if new_active else "inactive"
        locked_user.save(update_fields=['is_active', 'status'])

        # مزامنة حالة ملف الموظف في HR إن وجد مع تفادي التكرار والـ ValidationError
        try:
            if hasattr(locked_user, 'employee_profile') and locked_user.employee_profile:
                emp = locked_user.employee_profile
                if not new_active and emp.status == 'active':
                    emp.status = 'suspended'
                    emp.save(update_fields=['status'])
                elif new_active and emp.status == 'suspended':
                    emp.status = 'active'
                    emp.save(update_fields=['status'])
        except Exception as emp_err:
            logger.warning(f"Could not sync employee status for user {locked_user.id}: {emp_err}")

        # مسح كاش الصلاحيات
        PermissionCacheService.invalidate_user_cache(locked_user.id)

        # إنهاء الجلسات اللحظي عند التعطيل
        if not new_active:
            UserManagementService.invalidate_user_sessions(locked_user.id)

        # تسجيل الحركة في ActivityLog
        try:
            from users.models import ActivityLog
            action_title = "تفعيل المستخدم" if new_active else "تعطيل وأرشفة المستخدم"
            ActivityLog.objects.create(
                user=current_user if current_user and current_user.is_authenticated else locked_user,
                action=action_title,
                model_name='User',
                object_id=locked_user.id,
                extra_data={
                    'user_name': user_name,
                    'is_active': new_active,
                    'status': locked_user.status,
                    'details': f"{action_title}: {user_name}"
                }
            )
        except Exception as e:
            logger.warning(f"Could not log user toggle action: {e}")

        action_text = "تفعيل" if new_active else "تعطيل"
        dest_text = "واستعادته من الأرشيف" if new_active else "ونقله إلى الأرشيف"

        return {
            'success': True,
            'is_active': new_active,
            'action': 'activated' if new_active else 'archived',
            'message': f"تم {action_text} المستخدم '{user_name}' {dest_text} بنجاح."
        }



class BulkUserManagementService(BulkOperationService):
    """
    Bulk operations service for user management with optimized queries.
    
    Features:
    - Bulk permission updates
    - Bulk role assignments
    - Bulk cache warming
    """
    
    def process_batch(self, batch: list, operation: str, **kwargs) -> list:
        """
        Process batch of users for bulk operations.
        
        Args:
            batch: Batch of users or user data
            operation: Operation to perform
            **kwargs: Operation parameters
            
        Returns:
            list: Successfully processed items
        """
        processed = []
        
        if operation == 'warm_cache':
            # Bulk cache warming
            user_ids = [user.id if hasattr(user, 'id') else user for user in batch]
            result = PermissionCacheService.bulk_cache_user_permissions(user_ids)
            processed.extend(result['success'])
            
        elif operation == 'assign_roles':
            # Bulk role assignment
            role = kwargs.get('role')
            assigned_by = kwargs.get('assigned_by')
            
            if not role or not assigned_by:
                raise ValueError("Role and assigned_by are required for bulk role assignment")
            
            with transaction.atomic():
                for user in batch:
                    try:
                        user.role = role
                        user.save(update_fields=['role'])
                        
                        # Invalidate cache
                        PermissionCacheService.invalidate_user_cache(user.id)
                        
                        processed.append(user)
                        
                    except Exception as e:
                        logger.error(f"Failed to assign role to user {user.id}: {e}")
                        continue
        
        return processed


# Export main classes
__all__ = ['UserManagementService', 'BulkUserManagementService']