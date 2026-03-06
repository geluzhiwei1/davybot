# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Embedding model manager for text/vector conversion"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Any

import numpy as np
from sentence_transformers import SentenceTransformer

from dawei.knowledge.models import (
    EmbeddingModel,
    EmbeddingModelType,
    EmbeddingRequest,
    EmbeddingResponse,
)

logger = logging.getLogger(__name__)


# Model configurations
MODEL_CONFIGS: Dict[EmbeddingModelType, Dict[str, Any]] = {
    # Text models
    EmbeddingModelType.MINILM: {
        "dimension": 384,
        "max_sequence_length": 512,
        "supports_multilingual": False,
        "modalities": ["text"],
        "model_name": "sentence-transformers/all-MiniLM-L6-v2",
    },
    EmbeddingModelType.BGE_M3: {
        "dimension": 1024,
        "max_sequence_length": 8192,
        "supports_multilingual": True,
        "modalities": ["text"],
        "model_name": "BAAI/bge-m3",
    },
    EmbeddingModelType.BGE_LARGE: {
        "dimension": 1024,
        "max_sequence_length": 512,
        "supports_multilingual": True,
        "modalities": ["text"],
        "model_name": "BAAI/bge-large-zh-v1.5",
    },
    EmbeddingModelType.JINA_V4: {
        "dimension": 768,
        "max_sequence_length": 8192,
        "supports_multilingual": True,
        "modalities": ["text"],
        "model_name": "jinaai/jina-embeddings-v4",
    },
}


class EmbeddingManager:
    """Manager for embedding model loading and inference

    Features:
    - Automatic model caching
    - Batch processing for efficiency
    - Multi-language support
    - Model version management
    """

    def __init__(
        self,
        model_type: EmbeddingModelType = EmbeddingModelType.MINILM,
        cache_dir: str | Path | None = None,
        device: str = "cpu",
    ):
        """Initialize embedding manager

        Args:
            model_type: Embedding model to use
            cache_dir: Directory to cache downloaded models
            device: Device to run model on ("cpu", "cuda", "mps")
        """
        self.model_type = model_type
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.device = device

        # Model configuration
        if model_type not in MODEL_CONFIGS:
            raise ValueError(f"Unsupported model type: {model_type}")

        self.config = MODEL_CONFIGS[model_type]
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        """Lazy-load model on first access"""
        if self._model is None:
            self._load_model()
        return self._model

    @property
    def dimension(self) -> int:
        """Get embedding dimension"""
        return self.config["dimension"]

    def _load_model(self) -> None:
        """Load embedding model"""
        try:
            model_name = self.config["model_name"]
            logger.info(f"Loading embedding model: {model_name}")

            # Ensure cache directory exists
            if self.cache_dir:
                self.cache_dir.mkdir(parents=True, exist_ok=True)

            # Set HF endpoint to mirror if in China (for faster downloads)
            import os

            if "HF_ENDPOINT" not in os.environ:
                # Auto-detect and use mirror for better connectivity
                os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
                logger.info(f"Using HF mirror: {os.environ['HF_ENDPOINT']}")

            # Load model with retry logic
            import time

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self._model = SentenceTransformer(
                        model_name_or_path=model_name,
                        cache_folder=str(self.cache_dir) if self.cache_dir else None,
                        device=self.device,
                    )
                    break
                except RuntimeError as e:
                    if "client has been closed" in str(e) and attempt < max_retries - 1:
                        logger.warning(f"HTTP client closed on attempt {attempt + 1}, retrying...")
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    else:
                        raise

            logger.info(f"Model loaded successfully. Dimension: {self.dimension}")

        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise

    async def embed(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Generate embeddings for texts

        Args:
            texts: List of text strings
            batch_size: Batch size for processing

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        try:
            # Generate embeddings in batches
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )

            # Convert to list of lists
            return embeddings.tolist()

        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise

    async def embed_single(self, text: str) -> List[float]:
        """Generate embedding for single text

        Args:
            text: Text string

        Returns:
            Embedding vector
        """
        embeddings = await self.embed([text])
        return embeddings[0]

    def get_model_info(self) -> EmbeddingModel:
        """Get model information

        Returns:
            Model configuration
        """
        return EmbeddingModel(
            name=self.config["model_name"],
            type=self.model_type,
            dimension=self.config["dimension"],
            max_sequence_length=self.config["max_sequence_length"],
            supports_multilingual=self.config["supports_multilingual"],
        )

    @staticmethod
    @lru_cache(maxsize=1)
    def cosine_similarity(vec1: tuple[float, ...], vec2: tuple[float, ...]) -> float:
        """Calculate cosine similarity between two vectors

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Similarity score between 0 and 1
        """
        arr1 = np.array(vec1)
        arr2 = np.array(vec2)

        dot_product = np.dot(arr1, arr2)
        norm1 = np.linalg.norm(arr1)
        norm2 = np.linalg.norm(arr2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))

    @staticmethod
    def dot_product(vec1: List[float], vec2: List[float]) -> float:
        """Calculate dot product of two vectors

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Dot product value
        """
        return float(np.dot(vec1, vec2))

    @staticmethod
    def euclidean_distance(vec1: List[float], vec2: List[float]) -> float:
        """Calculate Euclidean distance between two vectors

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Euclidean distance
        """
        return float(np.linalg.norm(np.array(vec1) - np.array(vec2)))


class EmbeddingService:
    """High-level service for embedding operations"""

    def __init__(self, manager: EmbeddingManager):
        """Initialize embedding service

        Args:
            manager: Embedding manager instance
        """
        self.manager = manager

    async def process_request(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Process embedding request

        Args:
            request: Embedding request

        Returns:
            Embedding response
        """
        import time

        start_time = time.time()

        # Validate model type
        if request.model != self.manager.model_type:
            logger.warning(f"Requested model {request.model} differs from loaded {self.manager.model_type}")

        # Generate embeddings
        embeddings = await self.manager.embed(
            texts=request.texts,
            batch_size=request.batch_size,
        )

        # Calculate metrics
        latency_ms = (time.time() - start_time) * 1000
        total_tokens = sum(len(text.split()) for text in request.texts)

        return EmbeddingResponse(
            embeddings=embeddings,
            model=request.model.value,
            dimension=self.manager.dimension,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )

    async def embed_documents(self, documents: List[str]) -> List[List[float]]:
        """Embed multiple documents

        Args:
            documents: List of document texts

        Returns:
            List of embeddings
        """
        return await self.manager.embed(documents)

    async def embed_query(self, query: str) -> List[float]:
        """Embed search query

        Args:
            query: Search query text

        Returns:
            Query embedding
        """
        return await self.manager.embed_single(query)
