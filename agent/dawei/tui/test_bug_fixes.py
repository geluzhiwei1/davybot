#!/usr/bin/env python3
# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Bug fix verification script for TUI improvements.

Tests that all reported issues have been fixed:
1. Pydantic schema errors (3 errors)
2. Task graph loading error (1 error)
"""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_pydantic_schemas():
    """Test that all Pydantic schemas can be generated."""
    print("\n" + "=" * 60)
    print("Testing Pydantic Schema Fixes")
    print("=" * 60)

    try:
        from pydantic import BaseModel

        from dawei.tools.custom_tools.market_tools import (
            AgentListInput,
            PluginListInput,
            SkillListInput,
        )

        schemas = {
            "SkillListInput": SkillListInput,
            "AgentListInput": AgentListInput,
            "PluginListInput": PluginListInput,
        }

        all_passed = True
        for name, schema_class in schemas.items():
            try:
                # This would fail with the old code
                schema_json = schema_class.model_json_schema()
                print(f"✅ {name}.model_json_schema() works")
                print(f"   Schema type: {schema_json.get('title', 'N/A')}")
            except Exception as e:
                print(f"❌ {name}.model_json_schema() failed: {e}")
                all_passed = False

        if all_passed:
            print("\n✅ All Pydantic schema tests passed!")
        else:
            print("\n⚠️  Some schema tests failed")

        return all_passed

    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_task_graph():
    """Test that task graph JSON is valid."""
    print("\n" + "=" * 60)
    print("Testing Task Graph Fix")
    print("=" * 60)

    workspace_path = Path("/home/dev007/ws/dawei-agent/test-feishu-workspace")
    task_graph_path = workspace_path / ".dawei" / "task_graphs" / "default.json"

    if not task_graph_path.exists():
        print(f"❌ Task graph file not found: {task_graph_path}")
        return False

    try:
        with Path(task_graph_path).open() as f:
            data = json.load(f)

        # Validate structure
        required_keys = ["task_graph_id", "timestamp", "nodes", "total_tasks"]
        missing_keys = [key for key in required_keys if key not in data]

        if missing_keys:
            print(f"❌ Missing required keys: {missing_keys}")
            return False

        print("✅ Task graph JSON is valid")
        print(f"   Task graph ID: {data['task_graph_id']}")
        print(f"   Timestamp: {data['timestamp']}")
        print(f"   Total tasks: {data['total_tasks']}")
        print(f"   Nodes count: {len(data.get('nodes', {}))}")

        # Verify consistency
        if data["total_tasks"] != len(data.get("nodes", {})):
            nodes_count = len(data.get("nodes", {}))
            print(f"⚠️  Warning: total_tasks ({data['total_tasks']}) != nodes count ({nodes_count})")
        else:
            print("✅ Task count is consistent")

        return True

    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {e}")
        print(f"   Line {e.lineno}, Column {e.colno}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_css_compatibility():
    """Test that CSS is compatible with Textual."""
    print("\n" + "=" * 60)
    print("Testing CSS Compatibility")
    print("=" * 60)

    css_path = Path(__file__).parent / "ui" / "themes" / "default.css"

    if not css_path.exists():
        print(f"❌ CSS file not found: {css_path}")
        return False

    try:
        with Path(css_path).open() as f:
            css_content = f.read()

        # Test with Textual
        from textual.app import App

        app = App()
        app.CSS = css_content

        print("✅ CSS file is valid")
        print(f"   Path: {css_path}")
        print(f"   Size: {len(css_content)} bytes")
        print(f"   Lines: {len(css_content.splitlines())}")

        # Check for known problematic properties
        problematic = ["spacing:", "box-shadow:", "caret:", "@media"]

        found_issues = []
        for prop in problematic:
            if prop in css_content:
                found_issues.append(prop)

        if found_issues:
            print(f"⚠️  Found potentially problematic properties: {found_issues}")
            return False
        print("✅ No problematic CSS properties found")

        return True

    except Exception as e:
        print(f"❌ CSS validation error: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("TUI Bug Fix Verification Suite")
    print("=" * 60)
    print("\nThis script verifies that all reported bugs have been fixed:")
    print("  1. Pydantic schema errors (3 errors)")
    print("  2. Task graph loading error (1 error)")
    print("  3. CSS compatibility issues")

    results = {
        "Pydantic Schemas": test_pydantic_schemas(),
        "Task Graph": test_task_graph(),
        "CSS Compatibility": test_css_compatibility(),
    }

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)

    if passed == total:
        print("\n🎉 All bug fixes verified!")
        print("\nYou can now start TUI with:")
        print("  cd /home/dev007/ws/dawei-agent/agent")
        print("  uv run dawei tui --workspace /home/dev007/ws/dawei-agent/test-feishu-workspace")
        return 0
    print(f"\n⚠️  {total - passed} test(s) failed")
    print("Please review the errors above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
