#!/bin/bash

# LipSync Production System - Stop Script
# Created: 2025-10-01 00:04:32

echo "🛑 Stopping LipSync Production System..."

# Stop ComfyUI servers
echo "📡 Stopping ComfyUI servers..."
pkill -f "main.py --listen.*port 81[89][0-9]" || echo "  No ComfyUI servers running"

# Stop Backend API
echo "🖥️ Stopping Backend API..."
pkill -f "backend_with_timing.py" || echo "  No Backend running"

# Stop Frontend (optional)
echo "🌐 Stopping Frontend..."
pkill -f "http.server 3001" || echo "  No Frontend on port 3001 running"

# Wait a moment
sleep 2

# Check what's still running
echo "🔍 Checking remaining processes..."
remaining_comfyui=$(ps aux | grep "port 81[89][0-9]" | grep -v grep | wc -l)
remaining_backend=$(pgrep -f "backend_with_timing.py" | wc -l)
remaining_frontend=$(pgrep -f "http.server 3001" | wc -l)

echo "  ComfyUI servers still running: $remaining_comfyui"
echo "  Backend processes still running: $remaining_backend"
echo "  Frontend processes still running: $remaining_frontend"

if [ $((remaining_comfyui + remaining_backend + remaining_frontend)) -eq 0 ]; then
    echo "✅ All processes stopped successfully!"
else
    echo "⚠️ Some processes may still be running. Use 'ps aux | grep -E \"(comfyui|backend|http.server)\"' to check."
fi

echo "✅ Stop completed!"
