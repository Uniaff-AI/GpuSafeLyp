# 🚀 ИНСТРУКЦИИ ПО ВОССТАНОВЛЕНИЮ LIPSYNC СИСТЕМЫ

## 📦 Содержимое бэкапа:
- `backend_with_timing.py` - Основной рабочий бэкенд
- `frontend_clean.html` - Рабочий веб-интерфейс  
- `react_frontend/` - React компоненты (если есть)
- `start_all_comfyui.sh` - Скрипт запуска ComfyUI серверов
- `system_state.txt` - Снимок активных процессов
- `server_config.txt` - Конфигурация портов и серверов
- `optimal_settings.md` - Рекомендованные настройки

## 🔧 Восстановление системы:

### 1. Запуск ComfyUI серверов:
```bash
chmod +x start_all_comfyui.sh
./start_all_comfyui.sh
```

### 2. Запуск бэкенда:
```bash
python backend_with_timing.py > backend.log 2>&1 &
```

### 3. Запуск фронтенда:
```bash
python3 -m http.server 3001 --directory . > /dev/null 2>&1 &
```

### 4. Проверка работоспособности:
- Frontend: http://localhost:3001/frontend_clean.html
- Backend API: http://localhost:5000/health
- ComfyUI: http://localhost:8188/

## ⚙️ Конфигурация серверов (из бэкапа):
См. `server_config.txt` для точных портов и CUDA устройств.

## 🎯 Рекомендованные настройки:
См. `optimal_settings.md` для оптимальных параметров качества.

## 🔥 Дата создания бэкапа:
Mon Sep 29 23:05:42 UTC 2025
