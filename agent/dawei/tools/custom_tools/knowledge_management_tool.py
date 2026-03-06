# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Knowledge base management tools for document operations"""

import logging
from pathlib import Path
from typing import List, Dict, Any

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool

logger = logging.getLogger(__name__)


class UploadDocumentInput(BaseModel):
    """Upload document input schema"""

    file_path: str = Field(
        ...,
        description="Path to the document file to upload",
    )


class UploadDocumentTool(CustomBaseTool):
    """Upload document to knowledge base

    This tool uploads a document to the knowledge base, parses it,
    chunks it, generates embeddings, and indexes it for retrieval.
    """

    def __init__(self, knowledge_service=None):
        """Initialize upload document tool

        Args:
            knowledge_service: KnowledgeService instance
        """
        super().__init__()
        self.name = "upload_document"
        self.description = (
            "Upload a document to the knowledge base. "
            "Supports PDF, DOCX, TXT, and Markdown files. "
            "The document will be parsed, chunked, and indexed automatically."
        )
        self.args_schema = UploadDocumentInput
        self.knowledge_service = knowledge_service

    @safe_tool_operation(
        "upload_document",
        fallback_value="Error: Document upload failed",
    )
    async def _run(self, file_path: str) -> str:
        """Upload document to knowledge base

        Args:
            file_path: Path to document file

        Returns:
            Upload result message
        """
        try:
            # Validate file path
            path = Path(file_path)
            if not path.exists():
                return f"Error: File not found: {file_path}"

            if not path.is_file():
                return f"Error: Path is not a file: {file_path}"

            # Check file size (max 100MB)
            file_size = path.stat().st_size
            max_size = 100 * 1024 * 1024  # 100MB
            if file_size > max_size:
                return f"Error: File too large ({file_size / 1024 / 1024:.1f}MB). Maximum size: 100MB"

            # Check if knowledge service is available
            if self.knowledge_service is None:
                return "Error: Knowledge service is not initialized."

            # Upload document
            result = await self.knowledge_service.add_document(str(path))

            # Format result
            return self._format_upload_result(result)

        except Exception as e:
            logger.error(f"Document upload failed: {e}", exc_info=True)
            return f"Error: Failed to upload document - {str(e)}"

    def _format_upload_result(self, result: Any) -> str:
        """Format upload result

        Args:
            result: Upload result

        Returns:
            Formatted message
        """
        lines = [
            "## Document Upload Successful",
            "",
        ]

        if hasattr(result, 'id'):
            lines.append(f"**Document ID:** {result.id}")
        if hasattr(result, 'metadata'):
            metadata = result.metadata
            if hasattr(metadata, 'file_name'):
                lines.append(f"**File Name:** {metadata.file_name}")
            if hasattr(metadata, 'file_type'):
                lines.append(f"**File Type:** {metadata.file_type}")
            if hasattr(metadata, 'file_size'):
                size_mb = metadata.file_size / 1024 / 1024
                lines.append(f"**File Size:** {size_mb:.2f} MB")

        lines.append("")
        lines.append("The document has been:")
        lines.append("- ✓ Parsed")
        lines.append("- ✓ Chunked")
        lines.append("- ✓ Embedded")
        lines.append("- ✓ Indexed")
        lines.append("")
        lines.append("You can now search this document using the search_knowledge tool.")

        return "\n".join(lines)


class DeleteDocumentInput(BaseModel):
    """Delete document input schema"""

    document_id: str = Field(
        ...,
        description="ID of the document to delete",
    )


class DeleteDocumentTool(CustomBaseTool):
    """Delete document from knowledge base

    Removes a document and all its chunks from the knowledge base.
    """

    def __init__(self, knowledge_service=None):
        """Initialize delete document tool

        Args:
            knowledge_service: KnowledgeService instance
        """
        super().__init__()
        self.name = "delete_document"
        self.description = (
            "Delete a document from the knowledge base. "
            "This will remove the document and all its chunks. "
            "Use the document_id from list_documents or search results."
        )
        self.args_schema = DeleteDocumentInput
        self.knowledge_service = knowledge_service

    @safe_tool_operation(
        "delete_document",
        fallback_value="Error: Document deletion failed",
    )
    async def _run(self, document_id: str) -> str:
        """Delete document from knowledge base

        Args:
            document_id: Document ID

        Returns:
            Deletion result message
        """
        try:
            if self.knowledge_service is None:
                return "Error: Knowledge service is not initialized."

            # Delete document
            success = await self.knowledge_service.delete_document(document_id)

            if success:
                return f"## Document Deleted Successfully\n\nDocument ID: {document_id}\n\nThe document and all its chunks have been removed from the knowledge base."
            else:
                return f"Error: Failed to delete document {document_id}. Document may not exist."

        except Exception as e:
            logger.error(f"Document deletion failed: {e}", exc_info=True)
            return f"Error: Failed to delete document - {str(e)}"


class ListDocumentsInput(BaseModel):
    """List documents input schema"""

    limit: int = Field(
        default=20,
        description="Maximum number of documents to return",
    )
    offset: int = Field(
        default=0,
        description="Number of documents to skip",
    )


class ListDocumentsTool(CustomBaseTool):
    """List documents in knowledge base

    Lists all documents with metadata, useful for browsing
    and finding document IDs for deletion.
    """

    def __init__(self, knowledge_service=None):
        """Initialize list documents tool

        Args:
            knowledge_service: KnowledgeService instance
        """
        super().__init__()
        self.name = "list_documents"
        self.description = (
            "List all documents in the knowledge base. "
            "Shows document IDs, names, types, and sizes. "
            "Use this to find documents before deleting them."
        )
        self.args_schema = ListDocumentsInput
        self.knowledge_service = knowledge_service

    @safe_tool_operation(
        "list_documents",
        fallback_value="Error: Failed to list documents",
    )
    async def _run(self, limit: int = 20, offset: int = 0) -> str:
        """List documents in knowledge base

        Args:
            limit: Maximum documents to return
            offset: Number of documents to skip

        Returns:
            Formatted document list
        """
        try:
            if self.knowledge_service is None:
                return "Error: Knowledge service is not initialized."

            # List documents
            documents = await self.knowledge_service.list_documents(
                limit=limit,
                skip=offset,
            )

            # Format results
            return self._format_document_list(documents)

        except Exception as e:
            logger.error(f"Failed to list documents: {e}", exc_info=True)
            return f"Error: Failed to list documents - {str(e)}"

    def _format_document_list(self, documents: List[Any]) -> str:
        """Format document list

        Args:
            documents: List of documents

        Returns:
            Formatted document list
        """
        if not documents:
            return "## Knowledge Base Documents\n\nNo documents found in the knowledge base."

        lines = [
            f"## Knowledge Base Documents",
            f"**Total:** {len(documents)} documents",
            "",
            "---",
            "",
        ]

        for i, doc in enumerate(documents, 1):
            lines.append(f"### Document {i}")

            if hasattr(doc, 'id'):
                lines.append(f"**ID:** `{doc.id}`")
            if hasattr(doc, 'metadata'):
                metadata = doc.metadata
                if hasattr(metadata, 'file_name'):
                    lines.append(f"**Name:** {metadata.file_name}")
                if hasattr(metadata, 'file_type'):
                    lines.append(f"**Type:** {metadata.file_type}")
                if hasattr(metadata, 'file_size'):
                    size_kb = metadata.file_size / 1024
                    lines.append(f"**Size:** {size_kb:.1f} KB")
                if hasattr(metadata, 'indexed_at') and metadata.indexed_at:
                    lines.append(f"**Indexed:** {metadata.indexed_at}")

            lines.append("")

        return "\n".join(lines)


class ReindexDocumentInput(BaseModel):
    """Reindex document input schema"""

    document_id: str = Field(
        ...,
        description="ID of the document to reindex",
    )


class ReindexDocumentTool(CustomBaseTool):
    """Reindex document in knowledge base

    Re-parses, re-chunks, and re-embeds a document.
    Useful after updating chunking or embedding settings.
    """

    def __init__(self, knowledge_service=None):
        """Initialize reindex document tool

        Args:
            knowledge_service: KnowledgeService instance
        """
        super().__init__()
        self.name = "reindex_document"
        self.description = (
            "Reindex a document in the knowledge base. "
            "Re-parses, re-chunks, and re-embeds the document. "
            "Use this after changing chunking or embedding settings."
        )
        self.args_schema = ReindexDocumentInput
        self.knowledge_service = knowledge_service

    @safe_tool_operation(
        "reindex_document",
        fallback_value="Error: Document reindex failed",
    )
    async def _run(self, document_id: str) -> str:
        """Reindex document

        Args:
            document_id: Document ID

        Returns:
            Reindex result message
        """
        try:
            if self.knowledge_service is None:
                return "Error: Knowledge service is not initialized."

            # Reindex document
            success = await self.knowledge_service.reindex_document(document_id)

            if success:
                return f"## Document Reindexed Successfully\n\nDocument ID: {document_id}\n\nThe document has been re-parsed, re-chunked, and re-indexed."
            else:
                return f"Error: Failed to reindex document {document_id}."

        except Exception as e:
            logger.error(f"Document reindex failed: {e}", exc_info=True)
            return f"Error: Failed to reindex document - {str(e)}"
