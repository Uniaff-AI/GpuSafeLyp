#!/bin/bash
"""
Продвинутая очистка папки input от всех типов служебных файлов
"""

cd /home/administrator/ComfyUI/input

echo "=== ПРОДВИНУТАЯ ОЧИСТКА ФАЙЛОВ ==="

# Счетчик удаленных файлов
deleted=0

# Удаляем все файлы ._* (метаданные macOS)
for f in ._* 2>/dev/null; do
    if [[ -f "$f" ]]; then
        echo "🗑️  Удаляю служебный файл: $f"
        rm -f "$f"
        ((deleted++))
    fi
done

# Находим и удаляем AppleDouble файлы (проверяем содержимое)
echo "🔍 Проверяю файлы на AppleDouble..."
for f in *.mp3 *.mp4 2>/dev/null; do
    if [[ -f "$f" ]]; then
        filetype=$(file "$f")
        if [[ "$filetype" == *"AppleDouble"* ]] || [[ "$filetype" == *"Macintosh"* ]]; then
            size=$(stat -c%s "$f")
            echo "🗑️  Удаляю AppleDouble файл: $f (размер: $size байт)"
            rm -f "$f"
            ((deleted++))
        elif [[ $(stat -c%s "$f") -lt 1000 ]]; then
            echo "⚠️  Подозрительно маленький файл: $f (размер: $(stat -c%s "$f") байт)"
            filetype=$(file "$f")
            echo "    Тип: $filetype"
            if [[ "$filetype" != *"Audio file with ID3"* ]] && [[ "$filetype" != *"MPEG"* ]] && [[ "$filetype" != *"ISO Media"* ]]; then
                echo "🗑️  Удаляю поврежденный файл: $f"
                rm -f "$f"
                ((deleted++))
            fi
        fi
    fi
done

# Удаляем другие служебные файлы
for f in .DS_Store Thumbs.db desktop.ini; do
    if [[ -f "$f" ]]; then
        echo "🗑️  Удаляю системный файл: $f"
        rm -f "$f"
        ((deleted++))
    fi
done

echo ""
echo "=== РЕЗУЛЬТАТ ОЧИСТКИ ==="
echo "Удалено файлов: $deleted"
echo ""

echo "=== КОРРЕКТНЫЕ АУДИО/ВИДЕО ФАЙЛЫ ==="
for f in *.mp3 *.mp4 2>/dev/null; do
    if [[ -f "$f" ]]; then
        size=$(stat -c%s "$f")
        size_mb=$(echo "scale=2; $size/1024/1024" | bc)
        filetype=$(file "$f" | cut -d: -f2 | sed 's/^[ \t]*//')
        echo "✅ $f (${size_mb}MB) - $filetype"
    fi
done | head -15

echo ""
echo "=== ОЧИСТКА ЗАВЕРШЕНА ==="
