#!/bin/bash

# Запуск ComfyUI с публичным доступом
echo "Запуск ComfyUI на всех интерфейсах 0.0.0.0:8188..."

# Активируем conda окружение
source ~/miniconda3/etc/profile.d/conda.sh
conda activate latentsync

# Запускаем ComfyUI с публичным доступом
python main.py \
    --listen 0.0.0.0 \
    --port 8188 \
    --enable-cors-header \
    --cuda-device 0
