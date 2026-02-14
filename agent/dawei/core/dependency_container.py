# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dependency Container for service management
Provides centralized dependency injection throughout the application
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class ServiceConfig:
    """Configuration for service registration"""

    singleton: bool = True
    factory: Callable | None = None
    instance: Any | None = None


class DependencyContainer:
    """Centralized dependency injection container
    Supports singleton and factory-based service registration
    """

    def __init__(self):
        self._services: dict[str, ServiceConfig] = {}
        self._singletons: dict[str, Any] = {}
        self._lock = RLock()

    def register(self, service_type: type[T], instance: T, **_kwargs) -> None:
        """Register a service instance"""
        with self._lock:
            service_name = service_type.__name__
            self._services[service_name] = ServiceConfig(singleton=True, instance=instance)
            self._singletons[service_name] = instance
            logger.debug(f"Registered singleton service: {service_name}")

    def register_factory(self, service_type: type[T], factory: Callable[[], T], **_kwargs) -> None:
        """Register a service factory function"""
        with self._lock:
            service_name = service_type.__name__
            self._services[service_name] = ServiceConfig(singleton=True, factory=factory)
            logger.debug(f"Registered factory service: {service_name}")

    def register_transient(self, service_type: type[T], factory: Callable[[], T], **_kwargs) -> None:
        """Register a transient service (new instance each time)"""
        with self._lock:
            service_name = service_type.__name__
            self._services[service_name] = ServiceConfig(singleton=False, factory=factory)
            logger.debug(f"Registered transient service: {service_name}")

    def get(self, service_type: type[T]) -> T:
        """Get a service instance"""
        service_name = service_type.__name__

        with self._lock:
            if service_name not in self._services:
                raise ValueError(f"Service '{service_name}' not registered")

            service_config = self._services[service_name]

            # Return singleton instance if available
            if service_config.singleton:
                if service_name in self._singletons:
                    return self._singletons[service_name]

                # Create singleton instance
                if service_config.factory:
                    instance = service_config.factory()
                    self._singletons[service_name] = instance
                    return instance
                if service_config.instance:
                    self._singletons[service_name] = service_config.instance
                    return service_config.instance

            # Create transient instance
            if service_config.factory:
                return service_config.factory()

            raise ValueError(f"Service '{service_name}' has no factory or instance")

    def is_registered(self, service_type: type[T]) -> bool:
        """Check if a service is registered"""
        service_name = service_type.__name__
        return service_name in self._services

    def unregister(self, service_type: type[T]) -> None:
        """Unregister a service"""
        service_name = service_type.__name__

        with self._lock:
            if service_name in self._services:
                del self._services[service_name]
                if service_name in self._singletons:
                    del self._singletons[service_name]
                logger.debug(f"Unregistered service: {service_name}")

    def clear(self) -> None:
        """Clear all services"""
        with self._lock:
            self._services.clear()
            self._singletons.clear()
            logger.debug("Cleared all services")

    def get_registered_services(self) -> dict[str, ServiceConfig]:
        """Get all registered service configurations"""
        return self._services.copy()


# Global container instance
_global_container: DependencyContainer | None = None


def get_global_container() -> DependencyContainer:
    """Get the global dependency container"""
    global _global_container
    if _global_container is None:
        _global_container = DependencyContainer()
    return _global_container


def reset_global_container() -> None:
    """Reset the global container (mainly for testing)"""
    global _global_container
    if _global_container is not None:
        _global_container.clear()
    _global_container = None


def inject[T](service_type: type[T]) -> Callable[[Any], T]:
    """Decorator to inject a service into a class
    Usage:
        @inject(MyService)
        class MyClass:
            def __init__(self, my_service: MyService):
                self.my_service = my_service
    """

    def decorator(cls):
        original_init = cls.__init__

        def new_init(self, *args, **kwargs):
            # Get service from container
            container = get_global_container()
            service_instance = container.get(service_type)

            # Add service to kwargs before calling original __init__
            kwargs[service_type.__name__.lower()] = service_instance

            # Call original __init__
            original_init(self, *args, **kwargs)

        cls.__init__ = new_init
        return cls

    return decorator


def service_factory[T](service_type: type[T]) -> Callable[[], T]:
    """Decorator to mark a function as a service factory
    Usage:
        @service_factory(MyService)
        def create_my_service():
            return MyService()
    """

    def decorator(factory_func: Callable[[], T]) -> Callable[[], T]:
        container = get_global_container()
        container.register_factory(service_type, factory_func)
        return factory_func

    return decorator


def singleton_service[T](service_type: type[T]) -> Callable[[], T]:
    """Decorator to mark a function as a singleton service factory
    Usage:
        @singleton_service(MyService)
        def create_my_service():
            return MyService()
    """

    def decorator(factory_func: Callable[[], T]) -> Callable[[], T]:
        container = get_global_container()
        container.register_factory(service_type, factory_func)
        return factory_func

    return decorator


def transient_service[T](service_type: type[T]) -> Callable[[], T]:
    """Decorator to mark a function as a transient service factory
    Usage:
        @transient_service(MyService)
        def create_my_service():
            return MyService()
    """

    def decorator(factory_func: Callable[[], T]) -> Callable[[], T]:
        container = get_global_container()
        container.register_transient(service_type, factory_func)
        return factory_func

    return decorator
