#!/bin/bash
# Backend stop script for Tauri desktop application

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PID_FILE="$SCRIPT_DIR/backend.pid"

if [[ -f "$PID_FILE" ]]; then
    PID=$(cat "$PID_FILE")
    echo "[Dawei Backend] Stopping server (PID: $PID)..."

    # Kill the process
    kill "$PID" 2>/dev/null || true

    # Wait for process to terminate
    for i in {1..10}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            echo "[Dawei Backend] Server stopped"
            rm -f "$PID_FILE"
            exit 0
        fi
        sleep 1
    done

    # Force kill if still running
    echo "[Dawei Backend] Force killing server..."
    kill -9 "$PID" 2>/dev/null || true
    rm -f "$PID_FILE"
else
    echo "[Dawei Backend] No PID file found, backend may not be running"
fi
