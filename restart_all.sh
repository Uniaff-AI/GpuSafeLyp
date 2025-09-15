#!/bin/bash

echo "🔄 Быстрый перезапуск ComfyUI системы..."

# Остановка всех процессов
echo "1. Остановка процессов..."
pkill -f "python main.py" 2>/dev/null || true
pkill -f "smart_load_balancer" 2>/dev/null || true
sleep 3

# Запуск ComfyUI
echo "2. Запуск ComfyUI на двух GPU..."
cd ~/ComfyUI/ComfyUI_main
./run_comfyui_dual_gpu.sh

# Ждем загрузки ComfyUI
echo "3. Ожидание загрузки ComfyUI..."
sleep 15

# Запуск балансировщика
echo "4. Запуск умного балансировщика..."
source ~/miniconda3/etc/profile.d/conda.sh
conda activate latentsync
nohup python smart_load_balancer.py > smart_balancer.log 2>&1 &

sleep 5

# Проверка статуса
echo "5. Проверка статуса:"
echo "   ComfyUI процессов: $(ps aux | grep 'python main.py' | grep -v grep | wc -l)/2"
echo "   Балансировщиков: $(ps aux | grep 'smart_load_balancer' | grep -v grep | wc -l)/1"

echo ""
echo "✅ Система перезапущена!"
echo "🌐 Главный интерфейс: http://89.208.11.177:8190"
