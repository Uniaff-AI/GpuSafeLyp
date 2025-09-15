#!/bin/bash
"""
Автоматическая очистка служебных файлов в папке input
"""

cd /home/administrator/ComfyUI/input

echo "=== ОЧИСТКА СЛУЖЕБНЫХ ФАЙЛОВ ==="

# Удаляем файлы ._* (метаданные macOS)
if ls ._* 1> /dev/null 2>&1; then
    echo "Найдены служебные файлы macOS:"
    ls -la ._*
    rm -f ._*
    echo "✅ Удалены файлы ._*"
else
    echo "✅ Нет служебных файлов ._*"
fi

# Удаляем файлы .DS_Store (метаданные macOS)
if ls .DS_Store 1> /dev/null 2>&1; then
    rm -f .DS_Store
    echo "✅ Удален .DS_Store"
fi

# Удаляем файлы Thumbs.db (метаданные Windows)  
if ls Thumbs.db 1> /dev/null 2>&1; then
    rm -f Thumbs.db
    echo "✅ Удален Thumbs.db"
fi

echo ""
echo "=== СПИСОК КОРРЕКТНЫХ ФАЙЛОВ ==="
ls -la *.mp3 *.mp4 2>/dev/null | head -10

echo ""
echo "=== ОЧИСТКА ЗАВЕРШЕНА ==="
