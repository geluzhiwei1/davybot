"""Session Manager

Handle chat history persistence and restoration.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dawei.core.local_context import set_session_id

logger = logging.getLogger(__name__)


class SessionManagerError(Exception):
    """Raised when session operations fail"""


@dataclass
class ChatMessage:
    """Chat message data structure"""

    role: str
    content: str
    timestamp: str
    metadata: dict[str, Any] | None = None


@dataclass
class ChatSession:
    """Chat session data structure"""

    session_id: str
    workspace: str
    created_at: str
    updated_at: str
    messages: list[ChatMessage]
    settings: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class SessionManager:
    """Manage chat session persistence"""

    def __init__(self, workspace_path: str):
        """Initialize session manager

        Args:
            workspace_path: Path to workspace directory

        """
        self.workspace_path = Path(workspace_path).resolve()
        # Use conversations directory instead of sessions for compatibility with Agent system
        self.sessions_dir = self.workspace_path / ".dawei" / "conversations"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.current_session: ChatSession | None = None

        logger.info(f"SessionManager initialized for workspace: {self.workspace_path}")

    def create_session(self, session_id: str | None = None) -> ChatSession:
        """Create a new chat session

        Args:
            session_id: Optional session ID (auto-generated if not provided)

        Returns:
            New ChatSession

        """
        if session_id is None:
            session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        now = datetime.now(timezone.utc).isoformat()

        session = ChatSession(
            session_id=session_id,
            workspace=str(self.workspace_path),
            created_at=now,
            updated_at=now,
            messages=[],
            settings={},
            metadata={},
        )

        self.current_session = session

        # Set session context for logging
        set_session_id(session_id)

        logger.info(f"Created new session: {session_id}")

        return session

    def add_message(self, role: str, content: str, metadata: dict | None = None) -> None:
        """Add message to current session

        Args:
            role: Message role (user/assistant/system/error)
            content: Message content
            metadata: Optional metadata

        """
        if self.current_session is None:
            self.create_session()

        message = ChatMessage(
            role=role,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )

        self.current_session.messages.append(message)
        self.current_session.updated_at = datetime.now(timezone.utc).isoformat()

        logger.debug(f"Added {role} message to session")

    def save_session(self, session: ChatSession | None = None) -> bool:
        """Save session to disk

        Args:
            session: Session to save (uses current if not provided)

        Returns:
            True if successful

        Raises:
            SessionManagerError: If session is invalid or save operation fails

        """
        session = session or self.current_session

        if session is None:
            raise SessionManagerError("No session to save")

        if not session.session_id:
            raise SessionManagerError("Session ID is required")

        if not session.workspace:
            raise SessionManagerError("Session workspace is required")

        try:
            session_file = self.sessions_dir / f"{session.session_id}.json"

            # Convert to dict with fast fail validation
            session_dict = {
                "session_id": session.session_id,
                "workspace": session.workspace,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
                "messages": [
                    {
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp,
                        "metadata": msg.metadata,
                    }
                    for msg in session.messages
                ],
                "settings": session.settings or {},
                "metadata": session.metadata or {},
            }

            # Write to file
            with session_file.open("w", encoding="utf-8") as f:
                json.dump(session_dict, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved session to: {session_file}")
            return True

        except OSError as e:
            raise SessionManagerError(f"File system error while saving session: {e}")
        except (TypeError, ValueError) as e:
            raise SessionManagerError(f"Data serialization error: {e}")
        except Exception as e:
            raise SessionManagerError(f"Unexpected error while saving session: {e}")

    def load_session(self, session_id: str) -> ChatSession | None:
        """Load session from disk

        Args:
            session_id: Session ID to load

        Returns:
            Loaded ChatSession or None if session doesn't exist

        Raises:
            SessionManagerError: If session file exists but is corrupted or invalid

        """
        if not session_id:
            raise SessionManagerError("Session ID is required")

        # Try to find the session file
        # First, try direct match: {session_id}.json
        session_file = self.sessions_dir / f"{session_id}.json"

        # If not found, search for files with timestamp prefix: {timestamp}_{session_id}.json
        if not session_file.exists():
            # Search for files matching the pattern *_{{session_id}}.json
            matching_files = list(self.sessions_dir.glob(f"*_{session_id}.json"))

            if matching_files:
                session_file = matching_files[0]
                logger.info(f"Found session file with timestamp prefix: {session_file.name}")
            else:
                logger.warning(f"Session file not found: {session_file}")
                logger.warning(f"Searched for: {session_id}.json and *_ {session_id}.json")
                return None

        try:
            with Path(session_file).open(encoding="utf-8") as f:
                session_dict = json.load(f)

            # Support both 'id' and 'session_id' fields for compatibility
            file_session_id = session_dict.get("session_id") or session_dict.get("id")

            if not file_session_id:
                raise SessionManagerError(
                    f"Session file missing both 'session_id' and 'id' fields: {session_file}",
                )

            # Fast fail validation for other required fields
            # workspace is optional - use current workspace if not present
            required_fields = ["created_at", "updated_at"]
            for field in required_fields:
                if field not in session_dict:
                    raise SessionManagerError(
                        f"Missing required field '{field}' in session file: {session_file}",
                    )

            # Reconstruct messages with validation
            messages = []
            for i, msg in enumerate(session_dict.get("messages", [])):
                if not isinstance(msg, dict):
                    raise SessionManagerError(f"Invalid message format at index {i}: expected dict")
                if "role" not in msg or "content" not in msg or "timestamp" not in msg:
                    raise SessionManagerError(
                        f"Message at index {i} missing required fields: role, content, timestamp",
                    )

                messages.append(
                    ChatMessage(
                        role=msg["role"],
                        content=msg["content"],
                        timestamp=msg["timestamp"],
                        metadata=msg.get("metadata", {}),
                    ),
                )

            session = ChatSession(
                session_id=file_session_id,
                workspace=session_dict.get("workspace", str(self.workspace_path)),
                created_at=session_dict["created_at"],
                updated_at=session_dict["updated_at"],
                messages=messages,
                settings=session_dict.get("settings", {}),
                metadata=session_dict.get("metadata", {}),
            )

            self.current_session = session

            # Set session context for logging
            set_session_id(file_session_id)

            logger.info(f"Loaded session: {file_session_id}")

            return session

        except json.JSONDecodeError as e:
            raise SessionManagerError(f"Invalid JSON in session file {session_file}: {e}")
        except OSError as e:
            raise SessionManagerError(
                f"File system error while reading session file {session_file}: {e}",
            )
        except Exception as e:
            raise SessionManagerError(f"Unexpected error while loading session {session_id}: {e}")

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all available sessions

        Returns:
            List of session summaries (empty list if no sessions or invalid sessions)

        """
        sessions = []

        if not self.sessions_dir.exists():
            logger.warning(f"Sessions directory does not exist: {self.sessions_dir}")
            return sessions

        try:
            session_files = list(self.sessions_dir.glob("*.json"))

            for session_file in session_files:
                try:
                    with Path(session_file).open(encoding="utf-8") as f:
                        session_dict = json.load(f)

                    # Support both 'id' and 'session_id' fields for compatibility
                    session_id = session_dict.get("session_id") or session_dict.get("id")

                    # Fast fail validation for required fields
                    if not session_id:
                        logger.warning(f"Session file missing session_id/id: {session_file}")
                        continue

                    if "created_at" not in session_dict or "updated_at" not in session_dict:
                        logger.warning(f"Session file missing timestamp fields: {session_file}")
                        continue

                    sessions.append(
                        {
                            "session_id": session_id,  # Use the found ID
                            "created_at": session_dict["created_at"],
                            "updated_at": session_dict["updated_at"],
                            "message_count": session_dict.get("message_count", len(session_dict.get("messages", []))),
                            "file": str(session_file),
                        },
                    )

                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON in session file {session_file}: {e}")
                except OSError as e:
                    logger.warning(f"File system error reading session file {session_file}: {e}")
                except Exception as e:
                    logger.warning(f"Unexpected error reading session file {session_file}: {e}")

            # Sort by updated_at (newest first)
            sessions.sort(key=lambda x: x["updated_at"], reverse=True)

        except Exception as e:
            # For list operations, we want to fail fast but return partial results
            logger.error(f"Critical error while listing sessions: {e}", exc_info=True)
            # Return what we've collected so far, don't raise exception for this method

        return sessions

    def delete_session(self, session_id: str) -> bool:
        """Delete a session

        Args:
            session_id: Session ID to delete

        Returns:
            True if successful

        Raises:
            SessionManagerError: If session ID is invalid or deletion fails

        """
        if not session_id:
            raise SessionManagerError("Session ID is required")

        session_file = self.sessions_dir / f"{session_id}.json"

        if not session_file.exists():
            logger.warning(f"Session file not found: {session_file}")
            return False

        try:
            session_file.unlink()
            logger.info(f"Deleted session: {session_id}")
            return True

        except OSError as e:
            raise SessionManagerError(f"File system error while deleting session {session_id}: {e}")
        except Exception as e:
            raise SessionManagerError(f"Unexpected error while deleting session {session_id}: {e}")

    def export_session_as_markdown(self, session_id: str | None = None) -> str | None:
        """Export session as markdown

        Args:
            session_id: Session ID to export (uses current if not provided)

        Returns:
            Markdown string or None if no session found

        Raises:
            SessionManagerError: If session ID is invalid or session data is corrupted

        """
        session_id = session_id or (self.current_session.session_id if self.current_session else None)

        if not session_id:
            raise SessionManagerError("No session to export")

        session = self.load_session(session_id)
        if not session:
            raise SessionManagerError(f"Session not found: {session_id}")

        lines = []
        lines.append(f"# Chat Session: {session_id}\n")
        lines.append(f"Created: {session.created_at}\n")
        lines.append(f"Updated: {session.updated_at}\n")
        lines.append(f"Workspace: {session.workspace}\n")
        lines.append("---\n\n")

        for msg in session.messages:
            # Fast fail validation for message data
            if not msg.role or not msg.content or not msg.timestamp:
                raise SessionManagerError(
                    f"Invalid message data in session {session_id}: missing required fields",
                )

            role = msg.role.capitalize()
            try:
                timestamp = datetime.fromisoformat(msg.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError as e:
                raise SessionManagerError(
                    f"Invalid timestamp format in message from session {session_id}: {e}",
                )

            lines.append(f"## [{timestamp}] {role}\n\n")
            lines.append(f"{msg.content}\n\n")
            lines.append("---\n\n")

        return "".join(lines)

    def save_exported_markdown(
        self,
        session_id: str | None = None,
        output_path: str | None = None,
    ) -> str | None:
        """Save exported session as markdown file

        Args:
            session_id: Session ID to export
            output_path: Output file path (auto-generated if not provided)

        Returns:
            Path to saved file or None if export fails

        Raises:
            SessionManagerError: If session ID is invalid or file operations fail

        """
        markdown = self.export_session_as_markdown(session_id)

        if not markdown:
            return None

        if output_path is None:
            session_id = session_id or (self.current_session.session_id if self.current_session else "export")
            output_path = str(self.workspace_path / f"{session_id}_chat_export.md")

        # Validate output path
        output_file = Path(output_path)
        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise SessionManagerError(f"Cannot create output directory {output_file.parent}: {e}")

        try:
            with output_file.open("w", encoding="utf-8") as f:
                f.write(markdown)

            logger.info(f"Exported session to: {output_path}")
            return output_path

        except OSError as e:
            raise SessionManagerError(
                f"File system error while saving export to {output_path}: {e}",
            )
        except Exception as e:
            raise SessionManagerError(f"Unexpected error while saving export: {e}")

    def get_current_session(self) -> ChatSession | None:
        """Get current session

        Returns:
            Current ChatSession or None

        """
        return self.current_session

    def clear_current_session(self) -> None:
        """Clear current session"""
        self.current_session = None
        logger.info("Cleared current session")
