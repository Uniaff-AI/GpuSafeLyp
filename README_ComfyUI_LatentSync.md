# ComfyUI с LatentSync 1.6

## Запуск ComfyUI с публичным доступом

ComfyUI с интегрированным LatentSyncWrapper запущен и доступен по адресу:

**http://89.208.11.177:8188**

### Управление сервисом

Для запуска:
```bash
cd ~/ComfyUI/ComfyUI_main
./run_comfyui_public.sh
```

Для остановки:
```bash
pkill -f "python main.py"
```

Для проверки статуса:
```bash
ps aux | grep main.py
tail -f ~/ComfyUI/ComfyUI_main/comfyui_public.log
```

### Использование LatentSync

1. Откройте ComfyUI в браузере по адресу http://89.208.11.177:8188
2. Загрузите пример воркфлоу: `input/latentsync1.5_comfyui_basic.json`
3. В интерфейсе найдите ноды LatentSync:
   - **LatentSync Model Loader** - загружает модель LatentSync 1.6
   - **LatentSync Generate** - выполняет синхронизацию губ
   - **LatentSync Preview** - предварительный просмотр

### Доступные модели

Модели LatentSync находятся в:
```
~/ComfyUI/ComfyUI_main/custom_nodes/ComfyUI-LatentSyncWrapper/checkpoints/
├── latentsync_unet.pt (5GB) - основная модель LatentSync 1.6
├── stable_syncnet.pt (1.6GB) - SyncNet для детекции
├── vae/ - VAE энкодер/декодер
├── whisper/ - модели Whisper для аудио
└── auxiliary/ - вспомогательные файлы
```

### Технические характеристики

- **GPU**: NVIDIA GeForce RTX 3090 (24GB VRAM)
- **Разрешение**: до 512x512 (LatentSync 1.6)
- **Форматы видео**: MP4, AVI, MOV
- **Форматы аудио**: WAV, MP3, AAC
- **Python**: 3.10.18 с Conda окружением `latentsync`

### Примеры использования

1. **Базовая синхронизация**:
   - Загрузите видео в Load Video
   - Загрузите аудио в Load Audio  
   - Подключите к LatentSync Generate
   - Запустите обработку

2. **Расширенные настройки**:
   - Настройка силы синхронизации
   - Выбор области лица
   - Настройка качества обработки

### Мониторинг ресурсов

Для мониторинга GPU:
```bash
watch -n 1 nvidia-smi
```

Для просмотра логов:
```bash
tail -f ~/ComfyUI/ComfyUI_main/comfyui_public.log
```

### Поддержка

- LatentSync версия: 1.6
- ComfyUI версия: 0.3.57
- PyTorch версия: 2.5.1+cu124
- CUDA версия: 12.4

Сервис готов к использованию для качественной синхронизации губ на видео!
