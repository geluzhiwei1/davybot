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
        relation_types: list[str] | None = None,
    ) -> list[GraphPath]:
        """Find shortest paths between two entities using bidirectional BFS

        Args:
            from_entity: Start entity ID
            to_entity: Target entity ID
            max_depth: Maximum path length
            relation_types: Optional relation type filters

        Returns:
            List of paths (at most 1 for BFS shortest path)
        """
        from collections import deque

        if from_entity == to_entity:
            entity = await self.get_entity(from_entity)
            if entity:
                return [GraphPath(entities=[entity], relations=[], score=1.0)]
            return []

        # BFS: (current_id, [(edge_entity_id, relation), ...])
        queue: deque[tuple[str, list[tuple[str, GraphRelation]]]] = deque(
            [(from_entity, [])]
        )
        visited = {from_entity}

        while queue:
            current_id, path_rels = queue.popleft()

            if len(path_rels) >= max_depth:
                continue

            if current_id == to_entity:
                # Reconstruct path with entity and relation objects
                entity_ids = [from_entity] + [rid for rid, _ in path_rels]
                entities = []
                for eid in entity_ids:
                    e = await self.get_entity(eid)
                    if e:
                        entities.append(e)
                relations = [r for _, r in path_rels]
                score = 1.0 / (len(path_rels) + 1)  # shorter = higher score
                return [GraphPath(entities=entities, relations=relations, score=score)]

            # Traverse both directions
            out_rels = await self.get_entity_relations(current_id, direction="out")
            in_rels = await self.get_entity_relations(current_id, direction="in")

            for rel in out_rels:
                if relation_types and rel.relation_type not in relation_types:
                    continue
                if rel.to_entity not in visited:
                    visited.add(rel.to_entity)
                    queue.append((rel.to_entity, path_rels + [(rel.to_entity, rel)]))

            for rel in in_rels:
                if relation_types and rel.relation_type not in relation_types:
                    continue
                if rel.from_entity not in visited:
                    visited.add(rel.from_entity)
                    queue.append((rel.from_entity, path_rels + [(rel.from_entity, rel)]))

        return []

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
        """Find neighboring entities within N hops (bidirectional)

        Args:
            entity_id: Center entity ID
            hops: Number of hops to explore (default: 1)
            relation_types: Optional relation type filters

        Returns:
            List of neighboring entities sorted by proximity (closer first)
        """
        if hops < 1:
            return []

        from collections import deque

        # BFS: (entity_id, depth)
        queue: deque[tuple[str, int]] = deque([(entity_id, 0)])
        visited = {entity_id}
        ordered: list[GraphEntity] = []

        while queue:
            current_id, depth = queue.popleft()

            if depth >= hops:
                continue

            # Traverse both outgoing and incoming relations
            out_rels = await self.get_entity_relations(current_id, direction="out")
            in_rels = await self.get_entity_relations(current_id, direction="in")

            for rel in out_rels + in_rels:
                if relation_types and rel.relation_type not in relation_types:
                    continue

                # Determine neighbor ID based on direction
                neighbor_id = rel.to_entity if rel.from_entity == current_id else rel.from_entity

                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    neighbor = await self.get_entity(neighbor_id)
                    if neighbor:
                        ordered.append(neighbor)
                        queue.append((neighbor_id, depth + 1))

        return ordered

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
