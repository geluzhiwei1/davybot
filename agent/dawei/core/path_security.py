# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Path security utilities to prevent path traversal attacks.

This module provides functions to safely handle file paths and prevent
directory traversal vulnerabilities like ../../etc/passwd attacks.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class PathTraversalError(Exception):
    """Raised when a path traversal attempt is detected."""


def safe_path_join(
    base_dir: str,
    user_path: str,
    allow_absolute: bool = False,
    allowed_extensions: set[str] | None = None,
) -> str:
    """Safely join a base directory with a user-provided path.

    This function prevents path traversal attacks by:
    1. Normalizing the user path
    2. Resolving the absolute path
    3. Validating that the result is within the base directory
    4. Optionally checking file extensions

    Args:
        base_dir: The base directory (e.g., workspace root)
        user_path: User-provided path (can be relative or contain ..)
        allow_absolute: Whether to allow absolute paths (default: False)
        allowed_extensions: Optional set of allowed file extensions (e.g., {'.py', '.txt'})

    Returns:
        str: The safe, absolute path within base_dir

    Raises:
        PathTraversalError: If the path attempts to escape base_dir
        ValueError: If the path is invalid or extension not allowed

    Examples:
        >>> safe_path_join("/workspace", "file.txt")
        '/workspace/file.txt'

        >>> safe_path_join("/workspace", "../etc/passwd")
        PathTraversalError: Path traversal detected

        >>> safe_path_join("/workspace", "script.py", allowed_extensions={'.py', '.txt'})
        '/workspace/script.py'

        >>> safe_path_join("/workspace", "malicious.exe", allowed_extensions={'.py', '.txt'})
        ValueError: Extension .exe not allowed

    """
    # SUPER MODE: Bypass all path security checks
    try:
        # Import here to avoid circular dependency
        from dawei.core.super_mode import is_super_mode_enabled, log_security_bypass

        if is_super_mode_enabled():
            log_security_bypass(
                "safe_path_join",
                f"user_path={user_path}, allow_absolute={allow_absolute}",
            )
            # In super mode, just return the resolved path without checks
            user_path_obj = Path(user_path)
            if user_path_obj.is_absolute():
                return str(user_path_obj.resolve())
            return str(Path(base_dir) / user_path_obj).resolve()
    except ImportError:
        # If super_mode module not available, continue with normal checks
        pass

    # Normalize base directory to Path object
    base_path = Path(base_dir).resolve()
    base_dir_str = str(base_path)

    # Check if user provided absolute path
    user_path_obj = Path(user_path)
    if user_path_obj.is_absolute():
        if not allow_absolute:
            logger.warning(f"Absolute path not allowed: {user_path}")
            raise ValueError(f"Absolute paths are not allowed: {user_path}")
        # For absolute paths, use it directly after normalization
        full_path = user_path_obj.resolve()
    else:
        # Join and resolve to get absolute path
        full_path = (base_path / user_path_obj).resolve()

        # Verify the path is within base_dir (only for relative paths)
        if not _is_path_within_directory(str(full_path), base_dir_str):
            logger.error(
                f"Path traversal attempt detected: base_dir={base_dir_str}, user_path={user_path}, resolved={full_path}",
            )
            raise PathTraversalError(
                f"Path traversal detected: {user_path} resolves outside base directory",
            )

    # Check file extension if whitelist provided
    if allowed_extensions:
        # Only check extensions if the file has an extension
        if "." in full_path.name:
            file_ext = full_path.suffix.lower()
            if file_ext and file_ext not in allowed_extensions:
                logger.warning(f"File extension not allowed: {file_ext} in {full_path}")
                raise ValueError(
                    f"File extension '{file_ext}' not allowed. Allowed: {', '.join(sorted(allowed_extensions))}",
                )

    return str(full_path)


def _is_path_within_directory(path: str, directory: str) -> bool:
    """Check if a path is within a directory.

    Args:
        path: The path to check
        directory: The directory to check against

    Returns:
        bool: True if path is within directory, False otherwise

    """
    # Resolve both paths to absolute form
    path_obj = Path(path).resolve()
    dir_obj = Path(directory).resolve()

    # Convert to strings for comparison
    path_str = str(path_obj)
    dir_str = str(dir_obj)

    # Exact match counts as within directory
    if path_str == dir_str:
        return True

    # Ensure directory ends with separator for proper prefix match
    if not dir_str.endswith(os.sep):
        dir_str += os.sep

    # Check if path starts with directory
    return path_str.startswith(dir_str)


def validate_path_components(path: str, forbidden_components: set[str] | None = None) -> bool:
    """Validate that path doesn't contain suspicious components.

    Args:
        path: The path to validate
        forbidden_components: Optional set of forbidden path components
            (defaults to common system directories)

    Returns:
        bool: True if path is safe, False otherwise

    Examples:
        >>> validate_path_components("safe/file.txt")
        True

        >>> validate_path_components("../../../etc/passwd")
        False

    """
    if forbidden_components is None:
        # Default forbidden components (case-insensitive)
        forbidden_components = {
            "etc",
            "sys",
            "proc",
            "dev",
            "root",
            "windows",
            "system32",
            "program files",
        }

    # Normalize path for checking
    path_obj = Path(path)
    str(path_obj)

    # Check for obvious traversal patterns
    if ".." in path_obj.parts:
        logger.warning(f"Path contains parent directory references: {path}")
        return False

    # Check each component
    for component in path_obj.parts:
        component_lower = component.lower()
        if component_lower in forbidden_components:
            logger.warning(f"Path contains forbidden component: {component}")
            return False

    return True


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """Sanitize a filename to prevent directory traversal and other attacks.

    Args:
        filename: The filename to sanitize
        max_length: Maximum filename length

    Returns:
        str: Sanitized filename safe to use

    Examples:
        >>> sanitize_filename("safe_file.txt")
        'safe_file.txt'

        >>> sanitize_filename("../../../etc/passwd")
        'passwd'

        >>> sanitize_filename("file with spaces.txt")
        'file with spaces.txt'

    """
    # Remove any path separators - only keep basename
    filename = Path(filename).name

    # Replace dangerous characters with underscore
    dangerous_chars = [
        "..",
        "/",
        "\\",
        "\x00",
        "\n",
        "\r",
        ":",
        "|",
        "?",
        "*",
        "<",
        ">",
        '"',
    ]
    for char in dangerous_chars:
        filename = filename.replace(char, "_")

    # Remove control characters
    filename = "".join(char for char in filename if ord(char) >= 32)

    # Limit length
    if len(filename) > max_length:
        # Keep extension if present
        filename_path = Path(filename)
        name = filename_path.stem
        ext = filename_path.suffix
        max_name_length = max_length - len(ext)
        filename = name[:max_name_length] + ext

    # Ensure filename is not empty
    if not filename:
        filename = "unnamed"

    return filename


def validate_file_size(file_path: str, max_size_mb: int = 100) -> bool:
    """Validate that a file is within size limits.

    Args:
        file_path: Path to the file
        max_size_mb: Maximum size in megabytes

    Returns:
        bool: True if file size is acceptable, False otherwise

    """
    try:
        size_bytes = Path(file_path).stat().st_size
        max_bytes = max_size_mb * 1024 * 1024

        if size_bytes > max_bytes:
            logger.warning(f"File too large: {file_path} ({size_bytes} bytes > {max_bytes} bytes)")
            return False

        return True
    except OSError as e:
        logger.exception(f"Error checking file size for {file_path}: {e}")
        raise  # Re-raise to fail fast - file access errors should not be silent


def is_safe_file_type(file_path: str, allowed_mime_types: set[str] | None = None) -> bool:
    """Check if a file is of an allowed type based on its extension.

    Args:
        file_path: Path to the file
        allowed_mime_types: Optional set of allowed MIME types

    Returns:
        bool: True if file type is allowed, False otherwise

    """
    if allowed_mime_types is None:
        # Default: allow common text and data files
        allowed_mime_types = {
            "text/plain",
            "text/html",
            "text/css",
            "text/javascript",
            "application/json",
            "application/xml",
            "application/pdf",
        }

    # Get file extension
    file_path_obj = Path(file_path)
    ext = file_path_obj.suffix.lower()

    # Map extensions to MIME types
    mime_map = {
        ".txt": "text/plain",
        ".html": "text/html",
        ".css": "text/css",
        ".js": "text/javascript",
        ".json": "application/json",
        ".xml": "application/xml",
        ".pdf": "application/pdf",
        ".py": "text/plain",
        ".md": "text/plain",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
    }

    mime_type = mime_map.get(ext, "application/octet-stream")

    return mime_type in allowed_mime_types


# ============================================================================
# API Response Path Sanitization
# ============================================================================


def sanitize_api_path(absolute_path: str, workspace_name: str | None = None) -> str:
    """Sanitize absolute file system path for API responses.

    Converts absolute paths to relative or virtual paths to prevent
    leaking server filesystem information.

    Args:
        absolute_path: Absolute file system path (e.g., "/home/user/workspaces/project")
        workspace_name: Optional workspace name to use as relative base

    Returns:
        str: Sanitized path safe for API responses

    Examples:
        >>> sanitize_api_path("/home/dev007/ws/project", "project")
        'project'

        >>> sanitize_api_path("/home/dev007/ws/project/file.txt", "project")
        'file.txt'

    """
    if not absolute_path:
        return ""

    path_obj = Path(absolute_path)

    # If workspace_name is provided, return path relative to it
    if workspace_name:
        # Return just the filename if it's direct child
        if workspace_name in (path_obj.parent.name, path_obj.name):
            return path_obj.name
        # Return relative path if deeper
        try:
            # Try to get relative path from workspace root
            workspace_root = Path(absolute_path).parent
            if workspace_root.name == workspace_name:
                return path_obj.name
            return str(path_obj.relative_to(workspace_root))
        except (ValueError, RuntimeError):
            # Fallback to basename if relative path fails
            return path_obj.name

    # Fallback: return only the basename (last component)
    return path_obj.name


def sanitize_workspace_response(data: dict, remove_path: bool = True) -> dict:
    """Sanitize workspace API response to remove absolute filesystem paths.

    This function recursively processes a dictionary and removes or sanitizes
    any 'path' fields that contain absolute filesystem paths.

    Args:
        data: Response dictionary potentially containing path fields
        remove_path: If True, remove 'path' fields; if False, sanitize them

    Returns:
        dict: Sanitized response dictionary

    Examples:
        >>> data = {"id": "123", "path": "/home/dev007/ws/project", "name": "project"}
        >>> sanitize_workspace_response(data)
        {'id': '123', 'name': 'project'}

        >>> sanitize_workspace_response(data, remove_path=False)
        {'id': '123', 'path': 'project', 'name': 'project'}

    """
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            if key == "path" and isinstance(value, str):
                # Check if it's an absolute path
                if Path(value).is_absolute():
                    if remove_path:
                        # Skip this field entirely
                        continue
                    # Sanitize to basename only
                    sanitized[key] = sanitize_api_path(value)
                else:
                    # Keep relative paths as-is
                    sanitized[key] = value
            else:
                # Recursively sanitize nested values
                sanitized[key] = sanitize_workspace_response(value, remove_path)
        return sanitized

    if isinstance(data, list):
        # Recursively sanitize list items
        return [sanitize_workspace_response(item, remove_path) for item in data]

    # Return primitive types as-is
    return data
