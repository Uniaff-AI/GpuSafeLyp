#!/bin/bash

# Функция для мониторинга
monitor_session() {
    while true; do
        clear
        echo "=== LIVE МОНИТОРИНГ COMFYUI ==="
        echo "$(date)"
        echo ""
        
        # GPU Status
        echo "🎮 GPU STATUS:"
        nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader,nounits | \
        while IFS=',' read used total util temp; do
            usage_pct=$(echo "scale=1; $used*100/$total" | bc)
            echo "   Память: $used/$total MB ($usage_pct%)"
            echo "   Утилизация: $util%"
            echo "   Температура: $temp°C"
        done
        echo ""
        
        # ComfyUI Process
        echo "⚙️  ПРОЦЕССЫ:"
        ps aux | grep "main.py.*8188" | grep -v grep | \
        while read user pid cpu mem vsz rss tty stat start time command; do
            echo "   ComfyUI PID $pid: CPU $cpu%, RAM $mem%"
        done
        echo ""
        
        # Last log entries
        echo "📋 ПОСЛЕДНИЕ ЛОГИ (5 строк):"
        if [ -f "comfyui_patched.log" ]; then
            tail -5 comfyui_patched.log | sed 's/^/   /'
        else
            echo "   Нет логов"
        fi
        echo ""
        
        # Live log stream (если есть новые записи)
        echo "🔄 НОВЫЕ СОБЫТИЯ:"
        if [ -f "comfyui_patched.log" ]; then
            # Показываем последние 3 строки с живым обновлением
            tail -3 comfyui_patched.log | grep -E "(MEMORY-SAFE|got prompt|Exception|Error|CONSERVATIVE|batch_size)" | tail -3 | sed 's/^/   → /'
        fi
        
        echo ""
        echo "Обновление каждые 2 сек. Ctrl+C для остановки"
        sleep 2
    done
}

# Запуск мониторинга
monitor_session
