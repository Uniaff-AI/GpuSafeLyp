#!/bin/bash
"""
Скрипт запуска системы очередей ComfyUI
"""

set -e

COMFYUI_DIR="/home/administrator/ComfyUI"
CONDA_ENV="comfyui-latentsync"
PYTHON_PATH="/home/administrator/miniconda3/envs/$CONDA_ENV/bin/python"

cd "$COMFYUI_DIR"

echo "=== Запуск системы очередей ComfyUI ==="

# Проверяем что ComfyUI запущен
if ! pgrep -f "main.py --listen 0.0.0.0 --port 8188" > /dev/null; then
    echo "ComfyUI не запущен! Запускаем..."
    nohup $PYTHON_PATH main.py --listen 0.0.0.0 --port 8188 > comfyui_with_queue.log 2>&1 &
    echo "ComfyUI запущен в фоне"
    sleep 10
else
    echo "ComfyUI уже запущен"
fi

# Проверяем что API очереди не запущен
if pgrep -f "queue_api.py" > /dev/null; then
    echo "API очереди уже запущен"
else
    echo "Запускаем API очереди..."
    nohup $PYTHON_PATH queue_api.py > queue_api.log 2>&1 &
    echo "API очереди запущен на порту 5000"
fi

echo ""
echo "=== Система запущена ==="
echo "ComfyUI: http://localhost:8188"
echo "Queue API: http://localhost:5000"
echo "Queue Monitor: http://localhost:5000"
echo ""

# Показываем статус
sleep 3
echo "=== Текущий статус ==="
$PYTHON_PATH -c "
import requests
import json
try:
    response = requests.get('http://localhost:5000/api/status', timeout=5)
    if response.status_code == 200:
        data = response.json()
        print('Queue Status:', json.dumps(data['data'], indent=2))
    else:
        print('Ошибка получения статуса:', response.status_code)
except Exception as e:
    print('API еще не готов:', e)
"

echo ""
echo "Для добавления задачи в очередь используйте POST запрос:"
echo 'curl -X POST http://localhost:5000/api/tasks -H "Content-Type: application/json" -d '\''{
  "input_video": "/path/to/input.mp4",
  "output_video": "/path/to/output.mp4", 
  "workflow": {...}, 
  "priority": 0
}'\'''
