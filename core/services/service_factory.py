# -*- coding: utf-8 -*-
"""
Service Factory

Factory pattern for creating and managing services following unified patterns.
"""

from typing import Type, Dict, Any
from .base_service import BaseService


class ServiceFactory:
    """
    Factory for creating services with unified patterns.
    
    Features:
    - Service registration
    - Service creation with parameters
    - Service discovery
    """
    
    _services: Dict[str, Type[BaseService]] = {}
    
    @classmethod
    def register_service(cls, name: str, service_class: Type[BaseService]) -> None:
        """
        Register a service class.
        
        Args:
            name: Service name identifier
            service_class: Service class to register
        """
        cls._services[name] = service_class
    
    @classmethod
    def create_service(cls, name: str, *args, **kwargs) -> BaseService:
        """
        Create service instance.
        
        Args:
            name: Service name
            *args: Service constructor arguments
            **kwargs: Service constructor keyword arguments
            
        Returns:
            BaseService: Service instance
            
        Raises:
            ValueError: If service not registered
        """
        if name not in cls._services:
            raise ValueError(f"خدمة غير مسجلة: {name}")
        
        service_class = cls._services[name]
        return service_class(*args, **kwargs)
    
    @classmethod
    def get_available_services(cls) -> list:
        """
        Get list of available services.
        
        Returns:
            list: List of registered service names
        """
        return list(cls._services.keys())
    
    @classmethod
    def is_service_registered(cls, name: str) -> bool:
        """
        Check if service is registered.
        
        Args:
            name: Service name
            
        Returns:
            bool: True if service is registered
        """
        return name in cls._services