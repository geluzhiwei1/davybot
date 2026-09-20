# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei CLI - Refactored Main Entry Point

Modern, unified command-line interface for Dawei AI Assistant Platform.
Uses Click for command parsing and organization.

Usage:
    dawei <command> [options]

Commands:
    server       Server operations (start, stop, status)
    tui          Start the Terminal User Interface
    agent        Agent operations (run, modes, validate)

Examples:
    dawei server start --port 8465
    dawei server stop --port 8465
    dawei tui --workspace ./my-workspace
    dawei agent run ./my-workspace "Create hello world"

"""

from dawei.cli.core import cli


def main():
    """Main entry point for the dawei CLI."""
    cli()


if __name__ == "__main__":
    main()
