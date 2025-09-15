#!/bin/bash
"""
Мониторинг памяти GPU в реальном времени
"""

echo "=== GPU Memory Monitor ==="
echo "Мониторинг использования памяти GPU каждые 2 секунды"
echo "Нажмите Ctrl+C для остановки"
echo ""

while true; do
    clear
    echo "=== $(date) ==="
    nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu --format=csv,noheader,nounits | \
    while IFS=', ' read -r name total used free util; do
        echo "GPU: $name"
        echo "  Всего:        ${total} MB"
        echo "  Используется: ${used} MB ($(echo "scale=1; $used*100/$total" | bc)%)"
        echo "  Свободно:     ${free} MB"
        echo "  Утилизация:   ${util}%"
        
        # Расчет доступных слотов
        available_safe=$(echo "scale=0; ($free * 0.7) / 15360" | bc)
        echo "  Доступно слотов (консервативно): $available_safe"
        echo ""
    done
    
    # Показываем процессы ComfyUI
    echo "=== ComfyUI Процессы ==="
    ps aux | grep -E "(main.py|queue_api)" | grep -v grep | \
    while read user pid cpu mem vsz rss tty stat start time command; do
        echo "  PID: $pid, Память: ${mem}%, Команда: $command"
    done
    
    echo ""
    echo "=== Статус очереди ==="
    curl -s http://localhost:5000/api/status 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if data['success']:
        s = data['data']
        print(f'  Очередь: {s[\"pending\"]} | Выполняется: {s[\"running\"]} | Завершено: {s[\"completed\"]} | Ошибки: {s[\"failed\"]}')
    else:
        print('  API недоступен')
except:
    print('  API недоступен')
" || echo "  API недоступен"
    
    sleep 2
done
