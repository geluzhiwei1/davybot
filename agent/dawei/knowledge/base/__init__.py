# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Base classes and interfaces for knowledge system"""

from dawei.knowledge.base.vector_store import VectorStore
from dawei.knowledge.base.graph_store import GraphStore
from dawei.knowledge.base.fulltext_store import FullTextStore

__all__ = [
    "VectorStore",
    "GraphStore",
    "FullTextStore",
]
