#!/bin/bash

echo "🚀 Starting all ComfyUI servers on 8 GPUs..."

# Activate the correct conda environment
source /home/epycmax/miniconda3/bin/activate latentsync

# Change to ComfyUI directory
cd /home/epycmax/ComfyUI-Production

# Function to start ComfyUI on specific GPU and port
start_comfyui() {
    local gpu=$1
    local port=$2
    
    echo "🔥 Starting ComfyUI on GPU $gpu, port $port"
    CUDA_VISIBLE_DEVICES=$gpu nohup python main.py \
        --listen 0.0.0.0 \
        --port $port \
        --enable-cors-header \
        --cuda-device 0 \
        > /home/epycmax/comfyui_gpu${gpu}_port${port}.log 2>&1 &
    
    sleep 2
}

# Start servers for all 8 GPUs (ports 8188-8195)
for gpu in {0..7}; do
    port=$((8188+gpu))
    
    # Check if server is already running
    if curl -s --connect-timeout 1 http://localhost:$port/system_stats >/dev/null 2>&1; then
        echo "✅ GPU $gpu already running on port $port"
    else
        start_comfyui $gpu $port
    fi
done

echo "✅ All ComfyUI servers starting. Wait 30 seconds for initialization..."
sleep 30

# Check status
echo "📊 Checking server status..."
for gpu in {0..7}; do
    port=$((8188+gpu))
    if curl -s --connect-timeout 2 http://localhost:$port/system_stats >/dev/null 2>&1; then
        echo "✅ GPU $gpu (port $port): Online"
    else
        echo "❌ GPU $gpu (port $port): Offline"
    fi
done
