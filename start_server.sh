#!/bin/bash

PORT=5001

echo "🔍 Checking for existing server running on port $PORT..."
PID=$(lsof -t -i:$PORT)

if [ ! -z "$PID" ]; then
    echo "🛑 Killing existing server (PID: $PID)..."
    kill -9 $PID
    sleep 1
else
    echo "✅ No existing server found."
fi

echo "🚀 Starting server.py..."
./venv/bin/python server.py
