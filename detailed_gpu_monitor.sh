#!/bin/bash
"""
Детальный мониторинг GPU в реальном времени с обновлением каждую секунду
"""

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

echo -e "${WHITE}=== ПОДРОБНЫЙ МОНИТОРИНГ GPU ===${NC}"
echo -e "${CYAN}Обновление каждую секунду. Нажмите Ctrl+C для остановки${NC}"
echo ""

# Функция для красивого отображения размера памяти
format_memory() {
    local mem_mb=$1
    if [ $mem_mb -gt 1024 ]; then
        echo "$(echo "scale=2; $mem_mb/1024" | bc)GB"
    else
        echo "${mem_mb}MB"
    fi
}

# Функция для цветового кодирования использования памяти
color_memory() {
    local usage=$1
    if [ $(echo "$usage > 80" | bc) -eq 1 ]; then
        echo -e "${RED}${usage}%${NC}"
    elif [ $(echo "$usage > 60" | bc) -eq 1 ]; then
        echo -e "${YELLOW}${usage}%${NC}"
    elif [ $(echo "$usage > 40" | bc) -eq 1 ]; then
        echo -e "${BLUE}${usage}%${NC}"
    else
        echo -e "${GREEN}${usage}%${NC}"
    fi
}

# Функция для цветового кодирования температуры
color_temp() {
    local temp=$1
    if [ $temp -gt 80 ]; then
        echo -e "${RED}${temp}°C${NC}"
    elif [ $temp -gt 70 ]; then
        echo -e "${YELLOW}${temp}°C${NC}"
    elif [ $temp -gt 60 ]; then
        echo -e "${BLUE}${temp}°C${NC}"
    else
        echo -e "${GREEN}${temp}°C${NC}"
    fi
}

while true; do
    clear
    
    # Заголовок с временной меткой
    echo -e "${WHITE}╔══════════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${WHITE}║                          GPU МОНИТОРИНГ - $(date)                        ║${NC}"
    echo -e "${WHITE}╚══════════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    # Получаем данные GPU
    nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,utilization.memory,temperature.gpu,power.draw,power.limit,clocks.current.graphics,clocks.current.memory --format=csv,noheader,nounits | \
    while IFS=', ' read -r name total used free util_gpu util_mem temp power power_limit clock_gpu clock_mem; do
        
        # Вычисляем проценты
        usage_percent=$(echo "scale=1; $used*100/$total" | bc)
        free_percent=$(echo "scale=1; $free*100/$total" | bc)
        power_percent=$(echo "scale=1; $power*100/$power_limit" | bc)
        
        # Форматируем память
        total_fmt=$(format_memory $total)
        used_fmt=$(format_memory $used)
        free_fmt=$(format_memory $free)
        
        echo -e "${PURPLE}🎮 GPU:${NC} $name"
        echo ""
        
        # Блок памяти
        echo -e "${WHITE}┌─ ПАМЯТЬ ─────────────────────────────────────────────────┐${NC}"
        echo -e "${WHITE}│${NC} Всего:       ${WHITE}$total_fmt${NC}"
        echo -e "${WHITE}│${NC} Используется: $used_fmt ($(color_memory $usage_percent))"
        echo -e "${WHITE}│${NC} Свободно:     $free_fmt (${GREEN}${free_percent}%${NC})"
        echo -e "${WHITE}│${NC} Утилизация:   $(color_memory $util_mem) (память)"
        echo -e "${WHITE}└──────────────────────────────────────────────────────────┘${NC}"
        echo ""
        
        # Блок производительности
        echo -e "${WHITE}┌─ ПРОИЗВОДИТЕЛЬНОСТЬ ─────────────────────────────────────┐${NC}"
        echo -e "${WHITE}│${NC} GPU утилизация: $(color_memory $util_gpu)"
        echo -e "${WHITE}│${NC} Температура:    $(color_temp $temp)"
        echo -e "${WHITE}│${NC} Мощность:       ${CYAN}${power}W${NC}/${WHITE}${power_limit}W${NC} ($(color_memory $power_percent))"
        echo -e "${WHITE}│${NC} Частота GPU:    ${CYAN}${clock_gpu}MHz${NC}"
        echo -e "${WHITE}│${NC} Частота памяти: ${CYAN}${clock_mem}MHz${NC}"
        echo -e "${WHITE}└──────────────────────────────────────────────────────────┘${NC}"
        echo ""
        
        # Расчет доступных слотов для видео
        echo -e "${WHITE}┌─ АНАЛИЗ CAPACITY ────────────────────────────────────────┐${NC}"
        
        # Консервативный расчет (25GB на видео)
        slots_25gb=$(echo "scale=0; ($free * 0.5) / 25600" | bc)
        echo -e "${WHITE}│${NC} Слоты (25GB/видео):  ${GREEN}${slots_25gb}${NC} доступно"
        
        # Умеренный расчет (15GB на видео)
        slots_15gb=$(echo "scale=0; ($free * 0.7) / 15360" | bc)
        echo -e "${WHITE}│${NC} Слоты (15GB/видео):  ${YELLOW}${slots_15gb}${NC} доступно"
        
        # Агрессивный расчет (10GB на видео)
        slots_10gb=$(echo "scale=0; ($free * 0.8) / 10240" | bc)
        echo -e "${WHITE}│${NC} Слоты (10GB/видео):  ${BLUE}${slots_10gb}${NC} доступно"
        
        echo -e "${WHITE}└──────────────────────────────────────────────────────────┘${NC}"
        echo ""
    done
    
    # Процессы ComfyUI
    echo -e "${WHITE}┌─ ПРОЦЕССЫ COMFYUI ───────────────────────────────────────┐${NC}"
    ps aux | grep -E "(main.py|queue_api)" | grep -v grep | head -5 | \
    while read user pid cpu mem vsz rss tty stat start time command; do
        if [[ $command == *"main.py"* ]]; then
            echo -e "${WHITE}│${NC} ${GREEN}🔄 ComfyUI${NC}   PID: $pid, RAM: ${mem}%, CPU: ${cpu}%"
        elif [[ $command == *"queue_api"* ]]; then
            echo -e "${WHITE}│${NC} ${CYAN}📋 QueueAPI${NC}  PID: $pid, RAM: ${mem}%, CPU: ${cpu}%"
        fi
    done
    
    # Если нет процессов
    if ! ps aux | grep -E "(main.py|queue_api)" | grep -v grep > /dev/null; then
        echo -e "${WHITE}│${NC} ${RED}❌ Нет активных процессов ComfyUI${NC}"
    fi
    echo -e "${WHITE}└──────────────────────────────────────────────────────────┘${NC}"
    echo ""
    
    # Статус системы очередей
    echo -e "${WHITE}┌─ СИСТЕМА ОЧЕРЕДЕЙ ───────────────────────────────────────┐${NC}"
    queue_status=$(curl -s http://localhost:5000/api/status 2>/dev/null)
    if [ $? -eq 0 ]; then
        echo "$queue_status" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if data['success']:
        s = data['data']
        print(f'│ 📋 Очередь:     {s[\"pending\"]} задач')
        print(f'│ ⚡ Выполняется:  {s[\"running\"]} задач')  
        print(f'│ ✅ Завершено:    {s[\"completed\"]} задач')
        print(f'│ ❌ Ошибки:       {s[\"failed\"]} задач')
        print(f'│ 🎯 Макс слотов:  {s[\"max_concurrent\"]}')
    else:
        print('│ ❌ Ошибка получения статуса')
except:
    print('│ ⚠️  API недоступен')
" 2>/dev/null || echo -e "${WHITE}│${NC} ${RED}⚠️  API очередей недоступен${NC}"
    else
        echo -e "${WHITE}│${NC} ${RED}⚠️  API очередей недоступен${NC}"
    fi
    echo -e "${WHITE}└──────────────────────────────────────────────────────────┘${NC}"
    echo ""
    
    # Последние события ComfyUI
    echo -e "${WHITE}┌─ ПОСЛЕДНИЕ СОБЫТИЯ ──────────────────────────────────────┐${NC}"
    if [ -f "comfyui_conservative.log" ]; then
        tail -3 comfyui_conservative.log | sed 's/^/│ /' | head -3
    else
        echo -e "${WHITE}│${NC} ${YELLOW}Нет лог файла${NC}"
    fi
    echo -e "${WHITE}└──────────────────────────────────────────────────────────┘${NC}"
    
    echo -e "${CYAN}Следующее обновление через 1 секунду... ${NC}(Ctrl+C для остановки)"
    
    sleep 1
done
