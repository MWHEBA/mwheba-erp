# -*- coding: utf-8 -*-
"""
Core Services Module

Unified service infrastructure following the patterns defined in the unified services guide.
"""

from .base_service import BaseService, TransactionalService, BulkOperationService, CacheService, IntegrationService
from .service_factory import ServiceFactory

# Register core services
from users.services.user_management_service import UserManagementService, BulkUserManagementService
from users.services.permission_service import PermissionService

# Register services with factory
ServiceFactory.register_service('user_management', UserManagementService)
ServiceFactory.register_service('bulk_user_management', BulkUserManagementService)

__all__ = [
    'BaseService', 
    'TransactionalService', 
    'BulkOperationService', 
    'CacheService', 
    'IntegrationService',
    'ServiceFactory'
]