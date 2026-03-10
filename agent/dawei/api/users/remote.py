# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""
Remote Services API
Remote Services API - Control interfaces for NAT tunnel services
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from dawei.remote.nat_service import (
    NATService,
    NATTunnelInfo,
    get_nat_service,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/remote", tags=["Remote Services"])


# ============================================================================
# Pydantic Models
# ============================================================================


class ServiceConfig(BaseModel):
    """Service configuration"""

    name: str = Field(..., description="Service name")
    type: str = Field(..., description="Service type (http, https, ssh, tcp, udp)")
    local_port: int = Field(..., ge=1, le=65535, description="Local port")
    domain: Optional[str] = Field(None, description="Custom domain (optional)")


class StartNATServiceRequest(BaseModel):
    """Start NAT service request"""

    nat_server_addr: str = Field(default="localhost:8888", description="NAT server address")
    services: List[ServiceConfig] = Field(default_factory=list, description="Services to expose")


class TunnelInfoResponse(BaseModel):
    """Tunnel information response"""

    name: str = Field(..., description="Tunnel name")
    service_type: str = Field(..., description="Service type")
    local_port: int = Field(..., description="Local port")
    public_url: str = Field(..., description="Public access URL")
    tunnel_id: str = Field(..., description="Tunnel ID")
    created_at: str = Field(..., description="Creation time (ISO format)")


class NATServiceStatusResponse(BaseModel):
    """NAT service status response"""

    running: bool = Field(..., description="Is running")
    client_id: Optional[str] = Field(None, description="Client ID")
    client_name: Optional[str] = Field(None, description="Client name")
    tunnels: List[TunnelInfoResponse] = Field(default_factory=list, description="Active tunnel list")
    tunnel_count: int = Field(..., description="Tunnel count")


class NATServiceResponse(BaseModel):
    """NAT service operation response"""

    success: bool = Field(..., description="Operation success")
    message: str = Field(..., description="Response message")
    service_status: Optional[NATServiceStatusResponse] = Field(None, description="Service status")
    tunnels: List[TunnelInfoResponse] = Field(default_factory=list, description="Tunnel list")


class AddServiceRequest(BaseModel):
    """Add service request"""

    name: str = Field(..., description="Service name")
    service_type: str = Field(..., description="Service type")
    local_port: int = Field(..., ge=1, le=65535, description="Local port")
    domain: Optional[str] = Field(None, description="Custom domain")


class NATConfigResponse(BaseModel):
    """NAT configuration response"""

    support_system_url: str = Field(..., description="Support system URL")
    oauth_client_id: str = Field(..., description="OAuth client ID")
    default_nat_server_addr: str = Field(..., description="Default NAT server address")
    supported_service_types: List[str] = Field(..., description="Supported service types")
    user_client_name: str = Field(..., description="User's NAT client name")


# ============================================================================
# Helper Functions
# ============================================================================


def _convert_tunnel_to_response(tunnel: NATTunnelInfo) -> TunnelInfoResponse:
    """
    Convert NATTunnelInfo to API response format

    Args:
        tunnel: NATTunnelInfo instance

    Returns:
        TunnelInfoResponse: API response
    """
    return TunnelInfoResponse(name=tunnel.name, service_type=tunnel.service_type, local_port=tunnel.local_port, public_url=tunnel.public_url, tunnel_id=tunnel.tunnel_id, created_at=tunnel.created_at.isoformat())


def _convert_tunnels_to_response(tunnels: List[NATTunnelInfo]) -> List[TunnelInfoResponse]:
    """
    Batch convert tunnel information

    Args:
        tunnels: NATTunnelInfo list

    Returns:
        List[TunnelInfoResponse]: API response list
    """
    return [_convert_tunnel_to_response(t) for t in tunnels]


async def get_current_user_id() -> str:
    """
    Get current user ID (simplified implementation)

    Should be obtained from JWT token or session in production

    Returns:
        str: User ID
    """
    # TODO: Implement real user authentication
    return "default_user"


def get_user_nat_service(user_id: str) -> NATService:
    """
    Get NAT service instance for user

    Args:
        user_id: User ID

    Returns:
        NATService: NAT service instance
    """
    # Create independent service instance for each user
    # Use user ID as part of client name
    return NATService(client_name=f"davybot-user-{user_id}")


# ============================================================================
# API Endpoints
# ============================================================================


@router.post("/nat/start", response_model=NATServiceResponse)
async def start_nat_service(request: StartNATServiceRequest, current_user: str = Depends(get_current_user_id)) -> NATServiceResponse:
    """
    Start NAT service

    Create NAT tunnels to expose local services to public network.

    Args:
        request: Start request
        current_user: Current user ID

    Returns:
        NATServiceResponse: Operation result

    Raises:
        HTTPException: On operation failure
    """
    try:
        # Get user's NAT service instance
        service = get_user_nat_service(current_user)

        # Check if already running
        if service.is_running:
            return NATServiceResponse(
                success=False, message="NAT service is already running", service_status=NATServiceStatusResponse(running=True, client_id=service.client_identifier, client_name=service.client_name, tunnels=_convert_tunnels_to_response(service.get_tunnels()), tunnel_count=len(service.get_tunnels()))
            )

        # Convert service configurations
        services_data = [{"name": svc.name, "type": svc.type, "local_port": svc.local_port, "domain": svc.domain} for svc in request.services]

        # Start service (run in new thread to avoid blocking)
        loop = asyncio.get_event_loop()
        tunnels = await loop.run_in_executor(None, lambda: asyncio.run(service.start(nat_server_addr=request.nat_server_addr, services=services_data)))

        # Convert tunnel information
        tunnel_responses = _convert_tunnels_to_response(tunnels)

        logger.info(f"NAT service started for user {current_user}: {len(tunnels)} tunnel(s) created")

        return NATServiceResponse(
            success=True, message=f"NAT service started successfully with {len(tunnels)} tunnel(s)", service_status=NATServiceStatusResponse(running=True, client_id=service.client_identifier, client_name=service.client_name, tunnels=tunnel_responses, tunnel_count=len(tunnel_responses)), tunnels=tunnel_responses
        )

    except RuntimeError as e:
        logger.error(f"Failed to start NAT service: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error starting NAT service: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unexpected error: {str(e)}")


@router.post("/nat/stop", response_model=NATServiceResponse)
async def stop_nat_service(current_user: str = Depends(get_current_user_id)) -> NATServiceResponse:
    """
    Stop NAT service

    Close all NAT tunnels.

    Args:
        current_user: Current user ID

    Returns:
        NATServiceResponse: Operation result

    Raises:
        HTTPException: On operation failure
    """
    try:
        # Get user's NAT service instance
        service = get_user_nat_service(current_user)

        # Check if running
        if not service.is_running:
            return NATServiceResponse(success=False, message="NAT service is not running", service_status=NATServiceStatusResponse(running=False, client_id=service.client_identifier, client_name=service.client_name, tunnels=[], tunnel_count=0))

        # Stop service
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: asyncio.run(service.stop()))

        logger.info(f"NAT service stopped for user {current_user}")

        return NATServiceResponse(success=True, message="NAT service stopped successfully", service_status=NATServiceStatusResponse(running=False, client_id=service.client_identifier, client_name=service.client_name, tunnels=[], tunnel_count=0))

    except Exception as e:
        logger.error(f"Failed to stop NAT service: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/nat/status", response_model=NATServiceStatusResponse)
async def get_nat_service_status(current_user: str = Depends(get_current_user_id)) -> NATServiceStatusResponse:
    """
    Get NAT service status

    Query current NAT service running status and active tunnels.

    Args:
        current_user: Current user ID

    Returns:
        NATServiceStatusResponse: Service status

    Raises:
        HTTPException: On query failure
    """
    try:
        # Get user's NAT service instance
        service = get_user_nat_service(current_user)

        # Get tunnel information
        tunnels = service.get_tunnels()
        tunnel_responses = _convert_tunnels_to_response(tunnels)

        return NATServiceStatusResponse(running=service.is_running, client_id=service.client_identifier, client_name=service.client_name, tunnels=tunnel_responses, tunnel_count=len(tunnel_responses))

    except Exception as e:
        logger.error(f"Failed to get NAT service status: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/nat/tunnels", response_model=List[TunnelInfoResponse])
async def get_nat_tunnels(current_user: str = Depends(get_current_user_id)) -> List[TunnelInfoResponse]:
    """
    Get active tunnel list

    Return all active NAT tunnel information.

    Args:
        current_user: Current user ID

    Returns:
        List[TunnelInfoResponse]: Tunnel list

    Raises:
        HTTPException: On query failure
    """
    try:
        # Get user's NAT service instance
        service = get_user_nat_service(current_user)

        # Get tunnel information
        tunnels = service.get_tunnels()
        return _convert_tunnels_to_response(tunnels)

    except Exception as e:
        logger.error(f"Failed to get NAT tunnels: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/nat/services/add", response_model=NATServiceResponse)
async def add_nat_service(request: AddServiceRequest, current_user: str = Depends(get_current_user_id)) -> NATServiceResponse:
    """
    Add service to NAT client

    Dynamically add new service to running NAT client.

    Args:
        request: Add service request
        current_user: Current user ID

    Returns:
        NATServiceResponse: Operation result

    Raises:
        HTTPException: On operation failure
    """
    try:
        # Get user's NAT service instance
        service = get_user_nat_service(current_user)

        # Check if running
        if not service.is_running:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="NAT service is not running. Start it first.")

        # Add service
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: asyncio.run(service.add_service(name=request.name, service_type=request.service_type, local_port=request.local_port, domain=request.domain)))

        # Get updated tunnel list
        tunnels = service.get_tunnels()
        tunnel_responses = _convert_tunnels_to_response(tunnels)

        logger.info(f"Service added for user {current_user}: {request.name} ({request.service_type}) -> {request.local_port}")

        return NATServiceResponse(success=True, message=f"Service '{request.name}' added successfully", service_status=NATServiceStatusResponse(running=True, client_id=service.client_identifier, client_name=service.client_name, tunnels=tunnel_responses, tunnel_count=len(tunnel_responses)), tunnels=tunnel_responses)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add service: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/nat/config")
async def get_nat_config(current_user: str = Depends(get_current_user_id)) -> Dict[str, Any]:
    """
    Get NAT configuration

    Return configured NAT service information (no sensitive data).

    Args:
        current_user: Current user ID

    Returns:
        Dict: Configuration information with standard response format

    Raises:
        HTTPException: On query failure
    """
    try:
        from dawei.config.settings import get_settings

        settings = get_settings()
        support_config = settings.support_system

        config = NATConfigResponse(support_system_url=support_config.url, oauth_client_id=support_config.oauth_client_id, default_nat_server_addr="localhost:8888", supported_service_types=["http", "https", "ssh", "tcp", "udp"], user_client_name=f"davybot-user-{current_user}")

        return {"success": True, "data": config.model_dump(), "message": "NAT configuration retrieved successfully"}

    except Exception as e:
        logger.error(f"Failed to get NAT config: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ============================================================================
# Health Check Endpoints
# ============================================================================


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint

    Returns:
        Dict: Health status
    """
    return {"status": "healthy", "service": "Remote Services API", "version": "1.0.0", "features": {"nat_service": True, "tunnel_management": True, "service_management": True}}
