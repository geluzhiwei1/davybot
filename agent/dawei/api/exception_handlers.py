# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Unified Exception Handlers for FastAPI

Provides centralized exception handling for all API endpoints following fast fail principles.
"""

from typing import Any
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from dawei.logg.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# Custom HTTP Exceptions
# ============================================================================


class APIException(HTTPException):
    """Base exception for API errors with proper logging."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        log_level: str = "error",
        log_exception: bool = True,
    ):
        super().__init__(status_code=status_code, detail=detail)
        if log_exception:
            log_func = getattr(logger, log_level, logger.error)
            log_func(f"API error [{status_code}]: {detail}")


class BadRequestException(APIException):
    """400 Bad Request"""

    def __init__(self, detail: str, log: bool = True):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            log_level="warning",
            log_exception=log,
        )


class UnauthorizedException(APIException):
    """401 Unauthorized"""

    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            log_level="warning",
        )


class ForbiddenException(APIException):
    """403 Forbidden"""

    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            log_level="warning",
        )


class NotFoundException(APIException):
    """404 Not Found"""

    def __init__(self, detail: str, log: bool = True):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            log_level="info",
            log_exception=log,
        )


class ConflictException(APIException):
    """409 Conflict"""

    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            log_level="warning",
        )


class UnprocessableEntityException(APIException):
    """422 Unprocessable Entity"""

    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )


class InternalServerException(APIException):
    """500 Internal Server Error"""

    def __init__(self, detail: str, original_error: Exception | None = None):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        )
        # Log full exception with traceback for 500 errors
        if original_error:
            logger.exception(
                f"Internal server error: {detail}",
                exc_info=original_error if original_error is not Exception else None,
            )


class ServiceUnavailableException(APIException):
    """503 Service Unavailable"""

    def __init__(self, detail: str, original_error: Exception | None = None):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        )
        if original_error:
            logger.warning(f"Service unavailable: {detail}: {original_error}")


# ============================================================================
# Global Exception Handlers
# ============================================================================


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTPException instances (including our custom exceptions).

    This handler is automatically called by FastAPI for any HTTPException raised.
    """
    # Build error response - detail can be str or dict
    error_content = exc.detail if isinstance(exc.detail, dict) else {"message": exc.detail}

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail,
            "errorType": "HTTPException",
            "statusCode": exc.status_code,
            **error_content,
        },
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle Pydantic validation errors.

    Called when request body validation fails.
    """
    errors = exc.errors()
    detail = "; ".join([f"{err['loc'][0]} - {err['msg']}" for err in errors])

    logger.warning(f"Request validation failed: {detail}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": f"Validation error: {detail}",
            "statusCode": status.HTTP_422_UNPROCESSABLE_ENTITY,
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all unexpected exceptions.

    This is the last resort handler for any exception not caught by specific handlers.
    Follows fast fail principle: always log and return 500, never silence errors.
    """
    # Log the full exception with traceback
    logger.exception(f"Unhandled exception in {request.url.path}: {exc}")

    # Fast fail: include error details in response for debugging
    error_detail = str(exc)
    error_type = type(exc).__name__

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": error_detail,
            "errorType": error_type,
            "statusCode": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "path": str(request.url.path),
        },
    )


# ============================================================================
# Registration Function
# ============================================================================


def register_exception_handlers(app) -> None:
    """Register all exception handlers with FastAPI application.

    Args:
        app: FastAPI application instance

    Usage:
        from dawei.api.exception_handlers import register_exception_handlers
        from dawei.server import create_app

        app = create_app(...)
        register_exception_handlers(app)
    """
    # HTTPException (and all subclasses) - custom exceptions
    app.add_exception_handler(HTTPException, http_exception_handler)

    # Pydantic validation errors
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    # Generic exception catch-all (must be last - follows fast fail)
    app.add_exception_handler(Exception, generic_exception_handler)

    logger.info("Unified exception handlers registered with FastAPI application")
