#!/bin/bash

# ComfyUI Auto-Restart Watchdog Script
COMFY_DIR="/home/epycmax/ComfyUI/ComfyUI_main"
CONDA_ENV="latentsync"
LOG_DIR="/home/epycmax/comfy_logs"
LOCKFILE="/tmp/comfy_watchdog.lock"

# Создание директории для логов
mkdir -p "$LOG_DIR"

# Проверка что скрипт не запущен дважды
exec 200>"$LOCKFILE"
flock -n 200 || { echo "Watchdog уже запущен"; exit 1; }

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_DIR/watchdog.log"
}

check_and_restart() {
    local gpu=$1
    local port=$2
    local pid_file="/tmp/comfy_gpu${gpu}.pid"
    
    # Проверка процесса по PID файлу
    if [[ -f "$pid_file" ]]; then
        local saved_pid=$(cat "$pid_file")
        if kill -0 "$saved_pid" 2>/dev/null; then
            # Проверка что процесс действительно ComfyUI
            if ps -p "$saved_pid" -o cmd= | grep -q "main.py.*--port $port.*--cuda-device $gpu"; then
                # Проверка что порт отвечает
                if curl -s "http://localhost:$port" >/dev/null 2>&1; then
                    return 0  # Все в порядке
                else
                    log "WARN: GPU$gpu процесс жив но порт $port не отвечает"
                fi
            else
                log "WARN: PID $saved_pid не соответствует ComfyUI GPU$gpu"
            fi
        fi
        # Убираем неактуальный PID файл
        rm -f "$pid_file"
    fi
    
    # Убиваем зомби процессы
    pkill -f "main.py.*--port $port.*--cuda-device $gpu" 2>/dev/null || true
    sleep 2
    
    # Перезапуск
    log "Перезапуск ComfyUI GPU$gpu на порту $port"
    cd "$COMFY_DIR"
    source ~/miniconda3/etc/profile.d/conda.sh
    conda activate "$CONDA_ENV"
    
    nohup python main.py \
        --listen 0.0.0.0 \
        --port "$port" \
        --enable-cors-header \
        --cuda-device "$gpu" \
        > "$LOG_DIR/comfy_gpu${gpu}.log" 2>&1 &
    
    local new_pid=$!
    echo "$new_pid" > "$pid_file"
    log "Запущен ComfyUI GPU$gpu (PID: $new_pid, порт: $port)"
    
    # Ждем запуска
    sleep 10
    if curl -s "http://localhost:$port" >/dev/null 2>&1; then
        log "SUCCESS: ComfyUI GPU$gpu успешно запущен"
    else
        log "ERROR: ComfyUI GPU$gpu не смог запуститься"
    fi
}

log "=== Запуск ComfyUI Watchdog ==="

while true; do
    check_and_restart 0 8188
    check_and_restart 1 8189
    sleep 30  # Проверка каждые 30 секунд
done
