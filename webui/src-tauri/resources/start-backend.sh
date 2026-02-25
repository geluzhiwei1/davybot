#!/bin/bash
# Backend startup script for Tauri desktop application
# This script will be bundled with the Tauri app and used to start the Python backend

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check for bundled Python environment first (production)
if [[ -f "$SCRIPT_DIR/resources/python-env/bin/python" ]]; then
    PYTHON="$SCRIPT_DIR/resources/python-env/bin/python"
    WORK_DIR="$SCRIPT_DIR/resources/python-env"
    echo "[Dawei Backend] Using bundled Python environment"
# Fall back to development mode
elif [[ -f "$SCRIPT_DIR/../../services/agent-api/.venv/bin/python" ]]; then
    BACKEND_DIR="$SCRIPT_DIR/../../services/agent-api"
    PYTHON="$BACKEND_DIR/.venv/bin/python"
    WORK_DIR="$BACKEND_DIR"
    echo "[Dawei Backend] Development mode detected"
# Last resort: system Python
else
    PYTHON="python3"
    WORK_DIR="$SCRIPT_DIR"
    echo "[Dawei Backend] Using system Python (not recommended)"
fi

# Start the backend server
echo "[Dawei Backend] Starting server..."
echo "[Dawei Backend] Python: $PYTHON"
echo "[Dawei Backend] Working directory: $WORK_DIR"
echo "[Dawei Backend] Log file: $SCRIPT_DIR/backend.log"

cd "$WORK_DIR"

# Start server in background, redirect output to log file
"$PYTHON" -m dawei.server --host 127.0.0.1 --port 8465 > "$SCRIPT_DIR/backend.log" 2>&1 &

# Save the PID
echo $! > "$SCRIPT_DIR/backend.pid"

echo "[Dawei Backend] Server started with PID: $(cat $SCRIPT_DIR/backend.pid)"
echo "[Dawei Backend] Waiting for server to be ready..."

# Wait for server to be ready (max 30 seconds)
for i in {1..30}; do
    if curl -s http://127.0.0.1:8465/health > /dev/null 2>&1; then
        echo "[Dawei Backend] Server is ready!"
        exit 0
    fi
    sleep 1
done

echo "[Dawei Backend] WARNING: Server may not be ready. Check log file: $SCRIPT_DIR/backend.log"
exit 0
