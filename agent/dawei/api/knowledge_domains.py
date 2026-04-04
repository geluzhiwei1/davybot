# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Domain API routes for knowledge graph domains"""

from fastapi import APIRouter, HTTPException, status

from dawei.knowledge.domains import DomainRegistry

logger = __import__("logging").getLogger(__name__)

router = APIRouter(prefix="/api/knowledge/domains", tags=["knowledge-domains"])


@router.get("")
async def list_domains():
    """List all available domain profiles"""
    try:
        domains = DomainRegistry.list_domains()
        return {"domains": domains, "total": len(domains)}
    except Exception as e:
        logger.error(f"Failed to list domains: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{domain}/schema")
async def get_domain_schema(domain: str):
    """Get domain schema (entity_types and relation_types)"""
    schema = DomainRegistry.get_schema(domain)
    if not schema.get("entity_types") and not schema.get("relation_types"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Domain not found: {domain}",
        )
    return schema
