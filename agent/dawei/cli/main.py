# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei CLI Entry Point

Provides the 'dawei-agent' command line tool.
"""

from dawei.cli.agent_cli import CLIMain


def cli():
    """Entry point for 'dawei-agent' CLI command."""
    import fire

    fire.Fire(CLIMain)


if __name__ == "__main__":
    cli()
