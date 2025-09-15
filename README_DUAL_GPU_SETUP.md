# ComfyUI с LatentSync 1.6 - Параллельная обработка на 2 GPU

## 🚀 Настройка завершена!

Теперь у вас работает **параллельная обработка LatentSync** на двух GPU:

### Доступные сервисы:

1. **Балансировщик нагрузки** (рекомендуется):
   - **URL**: http://89.208.11.177:8190
   - Автоматически распределяет задачи между GPU
   - Выбирает наименее загруженный экземпляр

2. **ComfyUI GPU 0** (прямой доступ):
   - **URL**: http://89.208.11.177:8188
   - Использует NVIDIA RTX 3090 #0

3. **ComfyUI GPU 1** (прямой доступ):
   - **URL**: http://89.208.11.177:8189
   - Использует NVIDIA RTX 3090 #1

## 📋 Управление сервисами

### Запуск всего комплекса:
```bash
cd ~/ComfyUI/ComfyUI_main

# Запуск двух экземпляров ComfyUI
./run_comfyui_dual_gpu.sh

# Запуск балансировщика (в отдельном терминале)
conda activate latentsync
python comfyui_load_balancer.py
```

### Или быстрый запуск:
```bash
cd ~/ComfyUI/ComfyUI_main && ./run_comfyui_dual_gpu.sh
cd ~/ComfyUI/ComfyUI_main && conda activate latentsync && nohup python comfyui_load_balancer.py > load_balancer.log 2>&1 &
```

### Остановка всех сервисов:
```bash
pkill -f "python main.py"
pkill -f "comfyui_load_balancer.py"
```

## 📊 Мониторинг

### Проверка статуса GPU:
```bash
nvidia-smi
```

### Проверка работающих процессов:
```bash
ps aux | grep "python main.py"
ps aux | grep balancer
```

### Просмотр логов:
```bash
tail -f ~/ComfyUI/ComfyUI_main/comfyui_gpu0.log    # GPU 0
tail -f ~/ComfyUI/ComfyUI_main/comfyui_gpu1.log    # GPU 1
tail -f ~/ComfyUI/ComfyUI_main/load_balancer.log   # Балансировщик
```

### Проверка очередей:
```bash
curl -s http://localhost:8188/queue | jq '.queue_running | length'  # GPU 0
curl -s http://localhost:8189/queue | jq '.queue_running | length'  # GPU 1
curl -s http://localhost:8190/queue | jq '.'                         # Балансировщик
```

## 🎯 Использование

1. **Откройте балансировщик**: http://89.208.11.177:8190
2. **Загрузите воркфлоу**: используйте пример `latentsync1.5_comfyui_basic.json`
3. **Отправьте несколько задач**: они будут автоматически распределены между GPU
4. **Мониторьте прогресс**: в интерфейсе или через nvidia-smi

## ⚡ Производительность

- **Параллельная обработка**: до 2 задач одновременно
- **GPU память**: по 24GB на каждый GPU
- **Автобалансировка**: задачи направляются к наименее загруженному GPU
- **Разрешение**: до 512x512 (LatentSync 1.6)

## 🔧 Устранение неполадок

### Проблема с GLIBCXX (исправлена):
```bash
conda activate latentsync
conda update -c conda-forge libstdcxx-ng --yes
```

### Если GPU не используется:
```bash
# Проверить доступность CUDA
nvidia-smi
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())"
```

### Если порты заняты:
```bash
# Найти процессы на портах
netstat -tulpn | grep :8188
netstat -tulpn | grep :8189
netstat -tulpn | grep :8190
```

---

**Готово!** Теперь вы можете обрабатывать LatentSync задачи параллельно на двух RTX 3090! 🎉
