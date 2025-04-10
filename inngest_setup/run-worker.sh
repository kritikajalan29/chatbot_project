#!/bin/bash

# Startup script for the Inngest worker in production

# Get the directory this script is in
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load environment variables if .env exists
if [ -f ../.env ]; then
    echo "Loading environment variables from .env file"
    set -a
    source ../.env
    set +a
fi

# Check if PORT is set, otherwise use default
if [ -z "$PORT" ]; then
    PORT=8000
    echo "PORT not set, using default: $PORT"
fi

# Print information about the environment
echo "Starting Inngest worker..."
echo "Working directory: $(pwd)"
echo "Python executable: $(which python)"
echo "Python version: $(python --version)"

# Create log directory if it doesn't exist
mkdir -p ../logs

# Start the FastAPI app with uvicorn
echo "Starting uvicorn server on port $PORT"
exec uvicorn inngest_app:app --host 0.0.0.0 --port $PORT --log-level info 