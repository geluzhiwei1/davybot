# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""API 路由模块"""

# Import unified exception handlers for easy access across API modules
from .exception_handlers import (
    # Custom exception classes
    APIException,
    BadRequestException,
    ConflictException,
    ForbiddenException,
    InternalServerException,
    NotFoundException,
    ServiceUnavailableException,
    UnauthorizedException,
    UnprocessableEntityException,
    # Handler registration function
    register_exception_handlers,
)

__all__ = [
    "APIException",
    "BadRequestException",
    "UnauthorizedException",
    "ForbiddenException",
    "NotFoundException",
    "ConflictException",
    "UnprocessableEntityException",
    "InternalServerException",
    "ServiceUnavailableException",
    "register_exception_handlers",
]
