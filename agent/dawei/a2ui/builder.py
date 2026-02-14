# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""A2UI Builder - Helper class for easily constructing A2UI components.

This module provides a fluent API for building A2UI component trees,
making it easier for agents to generate UIs.

Example:
    builder = A2UIBuilder()

    form = builder.create_form("user_form", "User Registration")
    form.add_text_field("username", label="Username")
    form.add_text_field("email", label="Email", type="email")
    form.add_button("submit", label="Submit", action="submitForm")

    surface = builder.build()

"""

import uuid
from typing import Any


class A2UIComponent:
    """Base class for A2UI components."""

    def __init__(self, component_id: str, component_type: str, **properties):
        self.id = component_id
        self.type = component_type
        self.properties = properties
        self._children: list[A2UIComponent] = []
        self._data_context: str | None = None

    def add_child(self, child: "A2UIComponent") -> "A2UIComponent":
        """Add a child component."""
        self._children.append(child)
        return self

    def set_data_context(self, path: str) -> "A2UIComponent":
        """Set the data binding context for this component."""
        self._data_context = path
        return self

    def to_dict(self) -> dict[str, Any]:
        """Convert to A2UI component dictionary format."""
        component: dict[str, Any] = {
            "id": self.id,
            "component": {"type": self.type, **self.properties},
        }

        if self._children:
            if self.type in ["Row", "Column", "List"]:
                component["component"]["children"] = {
                    "explicitList": [child.id for child in self._children],
                }
            elif self.type == "Card":
                # Card can have child or children
                if len(self._children) == 1:
                    component["component"]["child"] = self._children[0].id
                else:
                    component["component"]["children"] = {
                        "explicitList": [child.id for child in self._children],
                    }
            elif self.type == "Button" and self._children:
                component["component"]["child"] = self._children[0].id

        if self._data_context:
            component["component"]["dataContextPath"] = self._data_context

        return component

    def collect_components(self, components: list[dict[str, Any]]) -> None:
        """Recursively collect all components into a flat list."""
        components.append(self.to_dict())
        for child in self._children:
            child.collect_components(components)


class A2UIBuilder:
    """Builder class for constructing A2UI surfaces.

    Provides convenient methods for creating common UI patterns.
    """

    def __init__(self):
        self._components: list[A2UIComponent] = []
        self._root_id: str | None = None
        self._data_model: dict[str, Any] = {}

    def create_row(
        self,
        row_id: str | None = None,
        distribution: str = "start",
        alignment: str = "center",
        spacing: int = 16,
    ) -> A2UIComponent:
        """Create a Row layout component."""
        component = A2UIComponent(
            component_id=row_id or f"row_{uuid.uuid4().hex[:8]}",
            component_type="Row",
            distribution=distribution,
            alignment=alignment,
            spacing=spacing,
        )
        self._register_root(component.id)
        self._components.append(component)
        return component

    def create_column(
        self,
        column_id: str | None = None,
        span: int = 24,
        offset: int = 0,
    ) -> A2UIComponent:
        """Create a Column layout component."""
        component = A2UIComponent(
            component_id=column_id or f"col_{uuid.uuid4().hex[:8]}",
            component_type="Column",
            span=span,
            offset=offset,
        )
        self._register_root(component.id)
        self._components.append(component)
        return component

    def create_card(
        self,
        card_id: str | None = None,
        elevation: str = "always",
    ) -> A2UIComponent:
        """Create a Card container component."""
        component = A2UIComponent(
            component_id=card_id or f"card_{uuid.uuid4().hex[:8]}",
            component_type="Card",
            elevation=elevation,
        )
        self._register_root(component.id)
        self._components.append(component)
        return component

    def create_text(
        self,
        text_id: str | None = None,
        text: str = "",
        usage_hint: str = "body",
    ) -> A2UIComponent:
        """Create a Text display component."""
        component = A2UIComponent(
            component_id=text_id or f"text_{uuid.uuid4().hex[:8]}",
            component_type="Text",
            text=text,
            usageHint=usage_hint,
        )
        self._components.append(component)
        return component

    def create_button(
        self,
        button_id: str | None = None,
        label: str = "Button",
        action: str = "click",
        variant: str = "default",
        context: list[dict[str, Any]] | None = None,
    ) -> A2UIComponent:
        """Create a Button interactive component."""
        # Create text label as child
        text_child = self.create_text(text_id=f"{button_id or 'btn'}_label", text=label)

        component = A2UIComponent(
            component_id=button_id or f"btn_{uuid.uuid4().hex[:8]}",
            component_type="Button",
            action={"name": action, "context": context or []},
            variant=variant,
        )
        component.add_child(text_child)
        self._components.append(component)
        return component

    def create_text_field(
        self,
        field_id: str | None = None,
        label: str = "",
        placeholder: str = "",
        field_type: str = "shortText",
        value: str | None = None,
    ) -> A2UIComponent:
        """Create a TextField input component."""
        component = A2UIComponent(
            component_id=field_id or f"field_{uuid.uuid4().hex[:8]}",
            component_type="TextField",
            label=label,
            placeholder=placeholder,
            type=field_type,
        )

        if value is not None:
            self._data_model[f"/{field_id}"] = value

        self._components.append(component)
        return component

    def create_checkbox(
        self,
        checkbox_id: str | None = None,
        label: str = "",
        value: bool = False,
    ) -> A2UIComponent:
        """Create a Checkbox input component."""
        component = A2UIComponent(
            component_id=checkbox_id or f"chk_{uuid.uuid4().hex[:8]}",
            component_type="CheckBox",
            label=label,
            value={"literalBoolean": value},
        )

        self._data_model[f"/{checkbox_id}"] = value
        self._components.append(component)
        return component

    def create_divider(
        self,
        divider_id: str | None = None,
        axis: str = "horizontal",
        thickness: int = 1,
    ) -> A2UIComponent:
        """Create a Divider component."""
        component = A2UIComponent(
            component_id=divider_id or f"div_{uuid.uuid4().hex[:8]}",
            component_type="Divider",
            axis=axis,
            thickness=thickness,
        )
        self._components.append(component)
        return component

    def _register_root(self, component_id: str) -> None:
        """Register the root component if not already set."""
        if self._root_id is None:
            self._root_id = component_id

    def build(
        self,
        title: str = "A2UI Surface",
        description: str | None = None,
        surface_type: str = "custom",
        layout: str = "vertical",
    ) -> dict[str, Any]:
        """Build the complete A2UI surface definition.

        Returns a dictionary ready to be passed to create_a2ui_surface tool.
        """
        # Collect all components into flat list
        components_list: list[dict[str, Any]] = []
        for component in self._components:
            component.collect_components(components_list)

        return {
            "title": title,
            "description": description,
            "surface_type": surface_type,
            "components": components_list,
            "data_model": self._data_model,
            "root_component_id": self._root_id,
            "layout": layout,
        }


# Convenience functions for common patterns


def create_form(
    form_id: str,
    title: str,
    fields: list[dict[str, Any]],
    submit_action: str = "submit",
) -> dict[str, Any]:
    """Create a form surface with text fields and a submit button.

    Args:
        form_id: Unique ID for the form
        title: Form title
        fields: List of field definitions, each with:
            - id: field ID
            - label: field label
            - type: field type ('shortText', 'number', 'email', etc.)
            - placeholder: optional placeholder
        submit_action: Action name for submit button

    Returns:
        Dictionary ready for create_a2ui_surface tool

    """
    builder = A2UIBuilder()

    # Create container
    column = builder.create_column(form_id)

    # Add title
    title_text = builder.create_text(text_id=f"{form_id}_title", text=title, usage_hint="h3")
    column.add_child(title_text)

    # Add fields
    for field in fields:
        field_comp = builder.create_text_field(
            field_id=field["id"],
            label=field["label"],
            placeholder=field.get("placeholder", ""),
            field_type=field.get("type", "shortText"),
        )
        column.add_child(field_comp)

    # Add submit button
    submit_btn = builder.create_button(
        button_id=f"{form_id}_submit",
        label="Submit",
        action=submit_action,
    )
    column.add_child(submit_btn)

    return builder.build(title=title, surface_type="form", layout="vertical")


def create_card_grid(grid_id: str, title: str, cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a grid of cards for data display.

    Args:
        grid_id: Unique ID for the grid
        title: Grid title
        cards: List of card definitions, each with:
            - title: card title
            - content: card content text
            - value: optional value to display

    Returns:
        Dictionary ready for create_a2ui_surface tool

    """
    builder = A2UIBuilder()

    # Create container row
    row = builder.create_row(grid_id, distribution="spaceAround")

    # Add cards
    for card_def in cards:
        card = builder.create_card()

        # Card title
        title_text = builder.create_text(
            text_id=f"{card_def['title']}_{uuid.uuid4().hex[:4]}",
            text=card_def["title"],
            usage_hint="h4",
        )
        card.add_child(title_text)

        # Card content
        content_text = builder.create_text(
            text_id=f"content_{uuid.uuid4().hex[:4]}",
            text=card_def.get("content", ""),
        )
        card.add_child(content_text)

        # Optional value
        if "value" in card_def:
            value_text = builder.create_text(
                text_id=f"value_{uuid.uuid4().hex[:4]}",
                text=str(card_def["value"]),
                usage_hint="caption",
            )
            card.add_child(value_text)

        row.add_child(card)

    return builder.build(title=title, surface_type="dashboard", layout="horizontal")
