#!/bin/bash

# Запуск двух экземпляров ComfyUI на разных GPU
echo "Запуск ComfyUI на двух GPU для параллельной обработки..."

# Активируем conda окружение
source ~/miniconda3/etc/profile.d/conda.sh
conda activate latentsync

# Останавливаем старые процессы
pkill -f "python main.py" || true
sleep 2

# Создаем папки для каждого экземпляра
mkdir -p ~/ComfyUI/ComfyUI_gpu0/output
mkdir -p ~/ComfyUI/ComfyUI_gpu1/output

# Копируем конфиги (если нужно)
cp -r custom_nodes ~/ComfyUI/ComfyUI_gpu0/ 2>/dev/null || true
cp -r custom_nodes ~/ComfyUI/ComfyUI_gpu1/ 2>/dev/null || true
cp -r models ~/ComfyUI/ComfyUI_gpu0/ 2>/dev/null || true
cp -r models ~/ComfyUI/ComfyUI_gpu1/ 2>/dev/null || true

# Запускаем первый экземпляр на GPU 0, порт 8188
echo "Запуск ComfyUI GPU 0 на порту 8188..."
nohup python main.py \
    --listen 0.0.0.0 \
    --port 8188 \
    --enable-cors-header \
    --cuda-device 0 \
    --output-directory ~/ComfyUI/ComfyUI_gpu0/output \
    > ~/ComfyUI/ComfyUI_main/comfyui_gpu0.log 2>&1 &

sleep 5

# Запускаем второй экземпляр на GPU 1, порт 8189  
echo "Запуск ComfyUI GPU 1 на порту 8189..."
nohup python main.py \
    --listen 0.0.0.0 \
    --port 8189 \
    --enable-cors-header \
    --cuda-device 1 \
    --output-directory ~/ComfyUI/ComfyUI_gpu1/output \
    > ~/ComfyUI/ComfyUI_main/comfyui_gpu1.log 2>&1 &

sleep 3

echo "Экземпляры ComfyUI запущены:"
echo "- GPU 0: http://89.208.11.177:8188"
echo "- GPU 1: http://89.208.11.177:8189"
echo ""
echo "Проверка статуса:"
ps aux | grep "python main.py"
