# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Abstract base class for knowledge graph storage"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any

from dawei.knowledge.models import GraphEntity, GraphPath, GraphRelation


class GraphStore(ABC):
    """Abstract base class for knowledge graph storage

    Implementations:
    - SQLiteGraphStore: Personal/team edition (SQLite)
    - Neo4jGraphStore: Enterprise edition (Neo4j)
    """

    def __init__(self, **kwargs):
        """Initialize graph store

        Args:
            **kwargs: Implementation-specific parameters
        """
        self.config = kwargs

    @abstractmethod
    async def add_entity(self, entity: GraphEntity) -> None:
        """Add an entity/node to the graph

        Args:
            entity: Entity to add
        """
        pass

    @abstractmethod
    async def add_relation(self, relation: GraphRelation) -> None:
        """Add a relation/edge to the graph

        Args:
            relation: Relation to add
        """
        pass

    @abstractmethod
    async def get_entity(self, entity_id: str) -> GraphEntity | None:
        """Get entity by ID

        Args:
            entity_id: Entity ID

        Returns:
            Entity if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_relations(
        self,
        entity_id: str,
        relation_type: str | None = None,
        direction: str = "outgoing",
    ) -> List[GraphRelation]:
        """Get relations for an entity

        Args:
            entity_id: Entity ID
            relation_type: Optional filter by relation type
            direction: "incoming", "outgoing", or "both"

        Returns:
            List of relations
        """
        pass

    @abstractmethod
    async def find_path(
        self,
        from_entity: str,
        to_entity: str,
        max_depth: int = 3,
        relation_types: List[str] | None = None,
    ) -> List[GraphPath]:
        """Find paths between two entities

        Args:
            from_entity: Start entity ID
            to_entity: End entity ID
            max_depth: Maximum path length
            relation_types: Optional relation type filters

        Returns:
            List of paths ranked by relevance
        """
        pass

    @abstractmethod
    async def find_neighbors(
        self,
        entity_id: str,
        hops: int = 1,
        relation_types: List[str] | None = None,
    ) -> List[GraphEntity]:
        """Find neighboring entities

        Args:
            entity_id: Center entity ID
            hops: Number of hops to explore
            relation_types: Optional relation type filters

        Returns:
            List of neighboring entities
        """
        pass

    @abstractmethod
    async def search_entities(
        self,
        query: str,
        entity_type: str | None = None,
        limit: int = 10,
    ) -> List[tuple[str, float]]:
        """Search entities by name/description

        Args:
            query: Search query text
            entity_type: Optional entity type filter
            limit: Maximum results

        Returns:
            List of (entity_id, score) tuples
        """
        pass

    @abstractmethod
    async def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity and its relations

        Args:
            entity_id: Entity ID to delete

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def delete_relation(self, relation_id: str) -> bool:
        """Delete a relation

        Args:
            relation_id: Relation ID to delete

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def query(self, query: str, **params) -> List[Any]:
        """Execute graph query

        Args:
            query: Query language string (Cypher, SQL, etc.)
            **params: Query parameters

        Returns:
            Query results
        """
        pass

    async def health_check(self) -> bool:
        """Check if graph store is healthy

        Returns:
            True if healthy, False otherwise
        """
        try:
            await self.query("RETURN 1")
            return True
        except Exception:
            return False
