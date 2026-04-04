# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Knowledge graph builder - extract from full document, not per-chunk"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dawei.knowledge.extraction.base import ExtractionStrategy

logger = logging.getLogger(__name__)


async def build_document_graph(
    graph_store,
    document,  # Document object
    chunks: list,  # List[DocumentChunk]
    extractor,  # ExtractionStrategy
    base_id: str,
    extraction_strategy: str,
    file_name: str,
) -> tuple[int, int]:
    """Build knowledge graph from FULL document content.

    Flow:
    1. Create document entity in graph
    2. Extract knowledge from full document text (NOT per-chunk)
    3. Create chunk entities + doc→chunk relations (for navigation only)
    4. Add extracted entities with doc→entity "mentions" relations
    5. Add extracted relations between entities

    Returns:
        (total_entities, total_relations) count
    """
    from dawei.knowledge.models import GraphEntity, GraphRelation

    total_entities = 0
    total_relations = 0

    # 1. Document entity
    doc_entity = GraphEntity(
        id=f"doc_{document.id}",
        type="document",
        name=file_name,
        description=f"Document: {file_name}",
        properties={
            "file_size": document.metadata.file_size,
            "file_type": document.metadata.file_type,
        },
        base_id=base_id,
    )
    await graph_store.add_entity(doc_entity)
    total_entities += 1

    # 2. Extract knowledge from FULL document content
    extraction_result = None
    try:
        extraction_result = await extractor.extract(
            document.content,
            document_id=document.id,
        )
        logger.info(
            f"Full-document extraction: {len(extraction_result.entities)} entities, "
            f"{len(extraction_result.relations)} relations"
        )
    except Exception as e:
        logger.warning(f"Failed to extract knowledge from document: {e}")

    # 3. Chunk entities + doc→chunk relations (for navigation)
    for i, chunk in enumerate(chunks):
        page_number = chunk.metadata.get("page_number") if chunk.metadata else None
        chunk_entity = GraphEntity(
            id=chunk.id,
            type="chunk",
            name=f"Chunk {i}",
            description=(chunk.content[:100] + "...") if len(chunk.content) > 100 else chunk.content,
            properties={
                "chunk_index": i,
                "document_id": chunk.document_id,
                "page_number": page_number,
                "content": chunk.content,
            },
            base_id=base_id,
        )
        await graph_store.add_entity(chunk_entity)
        total_entities += 1

        doc_chunk_relation = GraphRelation(
            id=f"rel_{doc_entity.id}_{chunk.id}",
            from_entity=doc_entity.id,
            to_entity=chunk.id,
            relation_type="contains",
            properties={"order": i},
            base_id=base_id,
        )
        await graph_store.add_relation(doc_chunk_relation)
        total_relations += 1

    # 4. Add extracted entities + doc→entity relations
    if extraction_result:
        entity_id_map: dict[str, str] = {}

        for entity in extraction_result.entities:
            entity_id = f"entity_{hash(entity.name)}_{base_id}"

            if entity.name not in entity_id_map:
                entity_id_map[entity.name] = entity_id

                graph_entity = GraphEntity(
                    id=entity_id,
                    type=entity.type,
                    name=entity.name,
                    description=entity.properties.get("description", ""),
                    properties={
                        **entity.properties,
                        "confidence": entity.confidence,
                        "source": "extraction",
                        "source_documents": [entity.source_document_id] if entity.source_document_id else [],
                        "source_chunks": [entity.source_chunk_id] if entity.source_chunk_id else [],
                        "source_pages": [entity.source_page_number] if entity.source_page_number is not None else [],
                    },
                    base_id=base_id,
                )
                await graph_store.add_entity(graph_entity)
                total_entities += 1

            # Document mentions entity
            mentions_relation = GraphRelation(
                id=f"rel_{doc_entity.id}_{entity_id_map[entity.name]}",
                from_entity=doc_entity.id,
                to_entity=entity_id_map[entity.name],
                relation_type="mentions",
                properties={
                    "confidence": entity.confidence,
                    "strategy": extraction_strategy,
                },
                base_id=base_id,
            )
            await graph_store.add_relation(mentions_relation)
            total_relations += 1

        # 5. Add extracted relations between entities
        for relation in extraction_result.relations:
            from_id = entity_id_map.get(relation.from_entity)
            to_id = entity_id_map.get(relation.to_entity)

            if from_id and to_id:
                graph_relation = GraphRelation(
                    id=f"rel_{from_id}_{to_id}_{relation.relation_type}",
                    from_entity=from_id,
                    to_entity=to_id,
                    relation_type=relation.relation_type,
                    properties={
                        **relation.properties,
                        "confidence": relation.confidence,
                        "strategy": extraction_strategy,
                    },
                    base_id=base_id,
                )
                await graph_store.add_relation(graph_relation)
                total_relations += 1

    logger.info(
        f"Graph built for {file_name}: {total_entities} entities, {total_relations} relations "
        f"(strategy: {extraction_strategy})"
    )
    return total_entities, total_relations
