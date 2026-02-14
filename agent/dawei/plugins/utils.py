# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Utility functions for plugin system"""

import asyncio
import logging
from pathlib import Path
from typing import Any, TypeVar

import yaml

logger = logging.getLogger(__name__)


T = TypeVar("T")


def load_yaml_file(file_path: Path) -> dict[str, Any]:
    """Load YAML file safely"""
    if not file_path.exists():
        raise FileNotFoundError(f"YAML file not found: {file_path}")

    try:
        with Path(file_path).open(encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError:
        logger.exception("Invalid YAML in {file_path}: ")
        raise


def save_yaml_file(file_path: Path, data: dict[str, Any]) -> None:
    """Save data to YAML file safely"""
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)


def validate_python_class_name(name: str) -> bool:
    """Validate Python class name"""
    if not name:
        return False

    if not (name[0].isupper() or name[0] == "_"):
        return False

    return all(c.isalnum() or c == "_" for c in name)


def parse_entry_point(entry_point: str) -> tuple[str, str]:
    """Parse plugin entry point string"""
    if ":" not in entry_point:
        raise ValueError(f"Invalid entry point format: {entry_point}. Expected 'module:ClassName'")

    module_name, class_name = entry_point.split(":", 1)

    if not module_name or not class_name:
        raise ValueError(
            f"Invalid entry point: {entry_point}. Module and class name must not be empty",
        )

    if not validate_python_class_name(class_name):
        raise ValueError(f"Invalid class name in entry point: {class_name}")

    return module_name, class_name


def import_class(module_name: str, class_name: str) -> type[T]:
    """Dynamically import a class from a module"""
    try:
        import importlib

        module = importlib.import_module(module_name)
        return getattr(module, class_name)
    except ImportError as e:
        raise ImportError(f"Failed to import module '{module_name}': {e}")
    except AttributeError as e:
        raise ImportError(f"Class '{class_name}' not found in module '{module_name}': {e}")


def import_class_from_file(file_path: str | Path, class_name: str) -> type[T]:
    """Dynamically import a class from a specific file path (avoid sys.path conflicts).

    Args:
        file_path: Path to the Python file containing the class
        class_name: Name of the class to import

    Returns:
        The imported class

    Raises:
        ImportError: If file or class not found
    """
    import importlib.util
    import sys
    from pathlib import Path

    file_path = Path(file_path)
    if not file_path.exists():
        raise ImportError(f"Plugin file not found: {file_path}")

    # Create a unique module name based on file path
    # This prevents conflicts when multiple plugins use "plugin.py"
    module_name = f"plugin_{file_path.parent.name}_{file_path.stem}"

    # Load module from file
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load module spec from {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
    except Exception as e:
        raise ImportError(f"Failed to execute module {module_name} from {file_path}: {e}")

    # Get the class from the module
    try:
        return getattr(module, class_name)
    except AttributeError:
        raise ImportError(
            f"Class '{class_name}' not found in module '{module_name}' (file: {file_path})"
        )


def merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dictionaries"""
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


async def run_with_timeout(coro, timeout: float, default: Any = None) -> Any:
    """Run coroutine with timeout"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except TimeoutError:
        logger.warning(f"Coroutine timed out after {timeout}s")
        return default


def create_plugin_id(name: str, version: str) -> str:
    """Create unique plugin ID from name and version"""
    return f"{name}@{version}"
