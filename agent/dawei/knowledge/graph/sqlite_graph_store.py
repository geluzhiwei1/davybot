# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""SQLite graph database implementation"""

import logging
import aiosqlite
from pathlib import Path
from typing import List, Dict, Any, Optional
import json

from dawei.knowledge.base.graph_store import GraphStore
from dawei.knowledge.models import GraphEntity, GraphRelation, GraphPath

logger = logging.getLogger(__name__)


class SQLiteGraphStore(GraphStore):
    """SQLite-based graph storage

    Stores entities and relations in SQLite tables.
    Implements simple graph traversal for knowledge search.
    """

    def __init__(self, db_path: str | Path):
        """Initialize SQLite graph store

        Args:
            db_path: Path to SQLite database file
        """
        super().__init__(db_path=str(db_path))
        self.db_path = Path(db_path)

    async def initialize(self) -> None:
        """Initialize graph database tables"""
        async with aiosqlite.connect(self.db_path) as db:
            # Create entities table
            await db.execute(
                """CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    name TEXT,
                    description TEXT,
                    properties TEXT,
                    base_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )"""
            )

            # Create relations table
            await db.execute(
                """CREATE TABLE IF NOT EXISTS relations (
                    id TEXT PRIMARY KEY,
                    from_entity TEXT NOT NULL,
                    to_entity TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    properties TEXT,
                    weight REAL DEFAULT 1.0,
                    base_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (from_entity) REFERENCES entities(id),
                    FOREIGN KEY (to_entity) REFERENCES entities(id)
                )"""
            )

            # Create indexes for efficient graph traversal
            await db.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_relations_from ON relations(from_entity)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_relations_to ON relations(to_entity)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type)")

            await db.commit()

    async def add_entity(self, entity: GraphEntity) -> None:
        """Add an entity/node to the graph

        Args:
            entity: Entity to add
        """
        async with aiosqlite.connect(self.db_path) as db:
            properties_json = json.dumps(entity.properties, default=str) if entity.properties else None

            await db.execute(
                """INSERT OR REPLACE INTO entities
                (id, type, name, description, properties, base_id)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (entity.id, entity.type, entity.name, entity.description, properties_json, entity.base_id),
            )
            await db.commit()

    async def add_relation(self, relation: GraphRelation) -> None:
        """Add a relation/edge to the graph

        Args:
            relation: Relation to add
        """
        async with aiosqlite.connect(self.db_path) as db:
            properties_json = json.dumps(relation.properties, default=str) if relation.properties else None

            await db.execute(
                """INSERT OR REPLACE INTO relations
                (id, from_entity, to_entity, relation_type, properties, weight, base_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (relation.id, relation.from_entity, relation.to_entity, relation.relation_type, properties_json, relation.weight, relation.base_id),
            )
            await db.commit()

    async def get_entity(self, entity_id: str) -> GraphEntity | None:
        """Get entity by ID

        Args:
            entity_id: Entity ID

        Returns:
            Entity if found, None otherwise
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT id, type, name, description, properties, base_id
                FROM entities WHERE id = ?""",
                (entity_id,),
            )
            row = await cursor.fetchone()

            if not row:
                return None

            entity_id, entity_type, name, description, properties_json, base_id = row
            properties = json.loads(properties_json) if properties_json else {}

            return GraphEntity(
                id=entity_id,
                type=entity_type,
                name=name,
                description=description,
                properties=properties,
                base_id=base_id,
            )

    async def get_relation(self, relation_id: str) -> GraphRelation | None:
        """Get relation by ID

        Args:
            relation_id: Relation ID

        Returns:
            Relation if found, None otherwise
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT id, from_entity, to_entity, relation_type, properties, weight, base_id
                FROM relations WHERE id = ?""",
                (relation_id,),
            )
            row = await cursor.fetchone()

            if not row:
                return None

            relation_id, from_entity, to_entity, relation_type, properties_json, weight, base_id = row
            properties = json.loads(properties_json) if properties_json else {}

            return GraphRelation(
                id=relation_id,
                from_entity=from_entity,
                to_entity=to_entity,
                relation_type=relation_type,
                properties=properties,
                weight=weight,
                base_id=base_id,
            )

    async def get_entity_relations(
        self,
        entity_id: str,
        relation_type: str | None = None,
        direction: str = "out",
    ) -> List[GraphRelation]:
        """Get all relations for an entity

        Args:
            entity_id: Entity ID
            relation_type: Optional relation type filter
            direction: 'out' (outgoing), 'in' (incoming), or 'both'

        Returns:
            List of relations
        """
        async with aiosqlite.connect(self.db_path) as db:
            if direction == "out":
                sql = """SELECT id, from_entity, to_entity, relation_type, properties, weight, base_id
                        FROM relations WHERE from_entity = ?"""
                params = [entity_id]
            elif direction == "in":
                sql = """SELECT id, from_entity, to_entity, relation_type, properties, weight, base_id
                        FROM relations WHERE to_entity = ?"""
                params = [entity_id]
            else:  # both
                sql = """SELECT id, from_entity, to_entity, relation_type, properties, weight, base_id
                        FROM relations WHERE from_entity = ? OR to_entity = ?"""
                params = [entity_id, entity_id]

            if relation_type:
                sql += " AND relation_type = ?"
                params.append(relation_type)

            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()

            relations = []
            for row in rows:
                relation_id, from_entity, to_entity, relation_type, properties_json, weight, base_id = row
                properties = json.loads(properties_json) if properties_json else {}

                relations.append(
                    GraphRelation(
                        id=relation_id,
                        from_entity=from_entity,
                        to_entity=to_entity,
                        relation_type=relation_type,
                        properties=properties,
                        weight=weight,
                        base_id=base_id,
                    )
                )

            return relations

    async def search_entities(
        self,
        query: str,
        entity_type: str | None = None,
        limit: int = 10,
    ) -> List[tuple[str, float]]:
        """Search entities by name/description

        Args:
            query: Search query
            entity_type: Optional entity type filter
            limit: Max results

        Returns:
            List of (entity_id, score) tuples
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Use FTS5-style search with LIKE
            query_pattern = f"%{query}%"

            sql = """SELECT id, name,
                           CASE WHEN name LIKE ? THEN 2 ELSE 1 END as name_match
                    FROM entities WHERE (name LIKE ? OR description LIKE ?)"""

            params = [query_pattern, query_pattern, query_pattern]

            if entity_type:
                sql += " AND type = ?"
                params.append(entity_type)

            sql += " ORDER BY name_match DESC, length(name) ASC LIMIT ?"
            params.append(limit)

            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()

            results = []
            for entity_id, name, name_match in rows:
                # Score based on match quality
                score = 0.9 if name_match == 2 else 0.7
                results.append((entity_id, score))

            return results

    async def find_path(
        self,
        from_entity: str,
        to_entity: str,
        max_depth: int = 3,
    ) -> GraphPath | None:
        """Find shortest path between two entities using BFS

        Args:
            from_entity: Start entity ID
            to_entity: Target entity ID
            max_depth: Maximum path length

        Returns:
            Path if found, None otherwise
        """
        from collections import deque

        # BFS queue: (current_entity, path_so_far)
        queue = deque([(from_entity, [])])
        visited = {from_entity}

        while queue:
            current, path = queue.popleft()

            if len(path) > max_depth:
                continue

            if current == to_entity:
                return GraphPath(
                    entities=[from_entity] + path + [to_entity],
                    relations=[],
                    length=len(path) + 1,
                )

            # Get neighbors
            relations = await self.get_entity_relations(current, direction="out")

            for relation in relations:
                if relation.to_entity not in visited:
                    visited.add(relation.to_entity)
                    new_path = path + [relation.to_entity]
                    queue.append((relation.to_entity, new_path))

        return None

    async def delete_entity(self, entity_id: str) -> int:
        """Delete an entity and all its relations

        Args:
            entity_id: Entity ID

        Returns:
            Number of relations deleted
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Delete relations first
            cursor = await db.execute("DELETE FROM relations WHERE from_entity = ? OR to_entity = ?", (entity_id, entity_id))
            relations_deleted = cursor.rowcount

            # Delete entity
            await db.execute("DELETE FROM entities WHERE id = ?", (entity_id,))

            await db.commit()
            return relations_deleted

    async def count_entities(self) -> int:
        """Count total entities

        Returns:
            Total entity count
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM entities")
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def count_relations(self) -> int:
        """Count total relations

        Returns:
            Total relation count
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM relations")
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def clear(self) -> None:
        """Clear all entities and relations"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM relations")
            await db.execute("DELETE FROM entities")
            await db.commit()

    async def get_relations(
        self,
        entity_id: str,
        relation_type: str | None = None,
        direction: str = "outgoing",
    ) -> List[GraphRelation]:
        """Get relations for an entity (alias for get_entity_relations)

        Args:
            entity_id: Entity ID
            relation_type: Optional filter by relation type
            direction: "incoming", "outgoing", or "both"

        Returns:
            List of relations
        """
        # Map direction names
        direction_map = {"incoming": "in", "outgoing": "out", "both": "both"}
        mapped_direction = direction_map.get(direction, direction)

        return await self.get_entity_relations(entity_id=entity_id, relation_type=relation_type, direction=mapped_direction)

    async def find_neighbors(
        self,
        entity_id: str,
        hops: int = 1,
        relation_types: List[str] | None = None,
    ) -> List[GraphEntity]:
        """Find neighboring entities within N hops

        Args:
            entity_id: Center entity ID
            hops: Number of hops to explore (default: 1)
            relation_types: Optional relation type filters

        Returns:
            List of neighboring entities sorted by proximity
        """
        if hops < 1:
            return []

        # Use BFS to find neighbors
        from collections import deque

        visited = set()
        queue = deque([(entity_id, 0)])  # (entity_id, current_depth)
        neighbors_map = {}  # entity_id -> GraphEntity
        entities_to_return = []

        while queue:
            current_id, depth = queue.popleft()

            if current_id in visited or depth > hops:
                continue

            visited.add(current_id)

            # Get outgoing relations
            relations = await self.get_entity_relations(current_id, direction="out")

            for relation in relations:
                # Filter by relation type if specified
                if relation_types and relation.relation_type not in relation_types:
                    continue

                neighbor_id = relation.to_entity

                if neighbor_id not in visited and neighbor_id != entity_id:
                    # Get neighbor entity
                    neighbor = await self.get_entity(neighbor_id)
                    if neighbor:
                        neighbors_map[neighbor_id] = neighbor
                        entities_to_return.append(neighbor)

                        # Continue BFS if within hop limit
                        if depth + 1 <= hops:
                            queue.append((neighbor_id, depth + 1))

        # Remove duplicates while preserving order (closer entities first)
        seen = set()
        unique_neighbors = []
        for entity in entities_to_return:
            if entity.id not in seen:
                seen.add(entity.id)
                unique_neighbors.append(entity)

        return unique_neighbors

    async def delete_relation(self, relation_id: str) -> bool:
        """Delete a relation by ID

        Args:
            relation_id: Relation ID to delete

        Returns:
            True if deleted, False if not found
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM relations WHERE id = ?", (relation_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def query(self, query: str, **params) -> List[Any]:
        """Execute SQL query on graph database

        Args:
            query: SQL query string
            **params: Query parameters

        Returns:
            Query results as list of rows

        Raises:
            Exception: If query execution fails
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, tuple(params.values()) if params else ())
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
