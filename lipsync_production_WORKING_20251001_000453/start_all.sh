#!/bin/bash

# LipSync Production System - Quick Start Script
# Created: 2025-10-01 00:04:32
# Status: ✅ PRODUCTION READY

set -euo pipefail

echo "🚀 Starting LipSync Production System..."

# 1. Start ComfyUI servers
echo "📡 Starting ComfyUI servers (8 GPU)..."
cd /home/epycmax/ComfyUI-Production

# Activate conda environment
source /home/epycmax/miniconda3/etc/profile.d/conda.sh
conda activate latentsync

# Create logs directory
mkdir -p logs

# Start 8 ComfyUI servers on different GPUs
for i in {0..7}; do
  port=$((8188 + i))
  echo "  Starting ComfyUI on port $port with GPU $i"
  CUDA_VISIBLE_DEVICES=$i nohup python main.py --listen 0.0.0.0 --port $port --enable-cors-header > logs/comfyui_${port}.log 2>&1 &
  sleep 2
done

# Wait for ComfyUI servers to start
echo "⏳ Waiting for ComfyUI servers to initialize (30 seconds)..."
sleep 30

# 2. Start Backend API
echo "🖥️ Starting Backend API..."
cd /home/epycmax/lipsync_production_WORKING_20251001_000453
nohup python backend_with_timing.py > backend.log 2>&1 &

# Wait for backend to start
echo "⏳ Waiting for Backend to initialize (10 seconds)..."
sleep 10

# 3. Check system status
echo "🔍 Checking system status..."

# Check ComfyUI servers
echo "📊 ComfyUI Servers Status:"
active_servers=$(ps aux | grep "port 81[89][0-9]" | grep -v grep | wc -l)
echo "  Active servers: $active_servers/8"

# Check backend
echo "🖥️ Backend Status:"
if pgrep -f "backend_with_timing.py" > /dev/null; then
    echo "  Backend: ✅ Running"
else
    echo "  Backend: ❌ Not running"
fi

# Check frontend
echo "🌐 Frontend Status:"
if pgrep -f "http.server 3001" > /dev/null; then
    echo "  Frontend: ✅ Running on port 3001"
else
    echo "  Frontend: ⚠️ Not running, starting..."
    cd /home/epycmax/lipsync_production_WORKING_20251001_000453
    nohup python -m http.server 3001 --bind 0.0.0.0 > frontend.log 2>&1 &
    echo "  Frontend: ✅ Started on port 3001"
fi

# Final status
echo ""
echo "🎉 LipSync Production System Status:"
echo "  Frontend: http://89.208.11.177:3001/"
echo "  Backend API: http://89.208.11.177:8000/"
echo "  ComfyUI Servers: http://89.208.11.177:8188-8195/"
echo ""
echo "📋 Monitor commands:"
echo "  Queue: curl -s http://localhost:8000/queue | jq '.queue[] | {id: .task_id[0:8], status, server: .server_url, progress}'"
echo "  GPU Load: nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader,nounits"
echo "  Backend logs: tail -f backend.log"
echo ""
echo "✅ System is ready for production use!"
