# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

import logging
from abc import ABC, abstractmethod

from pydantic import BaseModel, ValidationError


class CustomBaseTool(ABC):
    """Simplified BaseTool class for our custom tools."""

    def __init__(self):
        # Don't override class attributes if they exist
        if not hasattr(self, "name"):
            self.name = ""
        if not hasattr(self, "description"):
            self.description = ""
        if not hasattr(self, "args_schema"):
            self.args_schema = None
        # Add a logger
        self.logger = logging.getLogger(self.__class__.__name__)
        # Initialize context as None
        self.context = None
        # Initialize user_workspace as None
        self.user_workspace = None

    def set_context(self, context):
        """Set the context for the tool"""
        self.context = context

    @abstractmethod
    def _run(self, **kwargs) -> str:
        """The actual implementation of the tool.
        This method should be implemented by subclasses.
        It will receive validated arguments.
        """

    def run(self, context=None, **kwargs) -> str:
        """Public interface for running the tool with Pydantic validation.
        This method should not be overridden by subclasses.
        """
        # Set the context if provided
        if context is not None:
            self.set_context(context)

        result = None
        if self.args_schema and issubclass(self.args_schema, BaseModel):
            try:
                # Preprocess kwargs to handle JSON strings for object parameters
                # Some LLMs (like GLM) serialize object parameters as JSON strings
                processed_kwargs = self._preprocess_json_strings(kwargs)

                # Validate and parse the arguments using the Pydantic schema
                validated_args = self.args_schema(**processed_kwargs)
                # Call the actual implementation with validated arguments
                result = self._run(**validated_args.dict())
            except ValidationError:
                # Re-raise the validation error so it can be caught by the ToolExecutor
                # and sent back to the LLM for self-correction.
                raise
        else:
            # If no schema is defined, run the tool directly.
            # This provides backward compatibility for simpler tools.
            result = self._run(**kwargs)

        return result

    def _preprocess_json_strings(self, kwargs: dict) -> dict:
        """Preprocess kwargs to parse JSON strings for object parameters.

        Some LLMs (like GLM) serialize object parameters as JSON strings
        instead of proper objects. This method detects and parses such strings.

        Args:
            kwargs: The raw keyword arguments from the LLM

        Returns:
            Preprocessed kwargs with JSON strings parsed to objects

        """
        import json

        processed = {}
        for key, value in kwargs.items():
            # Check if this field exists in the schema and is an object type
            if key in self.args_schema.model_fields:
                field_info = self.args_schema.model_fields[key]

                # Check if the field annotation indicates a dict or nested model type
                # Common patterns: Dict[str, Any], dict, BaseModel subclass
                field_annotation = str(field_info.annotation)

                # If the value is a string that looks like JSON and the field expects an object
                if (
                    isinstance(value, str)
                    and value.strip().startswith("{")
                    and any(
                        pattern in field_annotation
                        for pattern in [
                            "Dict",
                            "dict",
                            "BaseModel",
                            "TimerSetInput",
                            "object",
                        ]
                    )
                ):
                    try:
                        parsed = json.loads(value)
                        processed[key] = parsed
                        continue
                    except (json.JSONDecodeError, ValueError):
                        # If parsing fails, use the original value
                        pass

            processed[key] = value

        return processed
