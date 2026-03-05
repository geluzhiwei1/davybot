# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Debug entry point for Dawei Server.

This module is used to run the server in debug mode via:
    fastapi dev agent/dawei/debug_main.py

Or via VS Code debugger.
"""

from dawei.server_app import create_app

# Create the FastAPI application instance for fastapi dev
app = create_app(host="0.0.0.0", port=8465)
