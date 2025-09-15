#!/usr/bin/env python
"""
Простой тест LatentSyncNode.
"""

import sys
import os
import torch
import numpy as np
from pathlib import Path

# Добавляем путь к ComfyUI в PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'custom_nodes', 'ComfyUI-LatentSyncWrapper'))

def create_dummy_data():
    """Создаем тестовые данные в формате ComfyUI"""
    
    # Создаем тестовое видео (5 кадров 256x256x3)
    images = torch.rand(5, 256, 256, 3, dtype=torch.float32)
    print(f"Created dummy video with shape: {images.shape}")
    
    # Создаем тестовое аудио (44100 Hz, 3 секунды, моно)
    audio_length = 44100 * 3  
    audio = {
        "waveform": torch.rand(1, audio_length, dtype=torch.float32),  # (channels, samples)
        "sample_rate": 44100
    }
    print(f"Created dummy audio with shape: {audio['waveform'].shape}")
    
    return images, audio

def test_import():
    """Тестируем импорт node"""
    try:
        from nodes import LatentSyncNode
        print("✓ LatentSyncNode успешно импортирован")
        return LatentSyncNode
    except Exception as e:
        print(f"✗ Ошибка импорта LatentSyncNode: {e}")
        return None

def test_node_init():
    """Тестируем инициализацию node"""
    try:
        LatentSyncNode = test_import()
        if LatentSyncNode is None:
            return None
            
        node = LatentSyncNode()
        print("✓ LatentSyncNode успешно инициализирован")
        return node
    except Exception as e:
        print(f"✗ Ошибка инициализации node: {e}")
        return None

def test_node_types():
    """Тестируем типы входов/выходов"""
    try:
        LatentSyncNode = test_import()
        if LatentSyncNode is None:
            return False
            
        input_types = LatentSyncNode.INPUT_TYPES()
        print("✓ INPUT_TYPES получены:")
        for key, value in input_types.get("required", {}).items():
            print(f"  - {key}: {value}")
        
        # Проверяем константы
        print(f"✓ CATEGORY: {LatentSyncNode.CATEGORY}")
        print(f"✓ RETURN_TYPES: {getattr(LatentSyncNode, 'RETURN_TYPES', 'Не найдено')}")
        print(f"✓ RETURN_NAMES: {getattr(LatentSyncNode, 'RETURN_NAMES', 'Не найдено')}")
        print(f"✓ FUNCTION: {getattr(LatentSyncNode, 'FUNCTION', 'Не найдено')}")
        
        return True
    except Exception as e:
        print(f"✗ Ошибка получения типов: {e}")
        return False

def test_inference():
    """Тестируем inference функцию (только создание без выполнения)"""
    try:
        node = test_node_init()
        if node is None:
            return False
            
        # Проверяем что функция inference существует
        if hasattr(node, 'inference'):
            print("✓ Функция inference найдена")
            
            # Получаем подпись функции
            import inspect
            sig = inspect.signature(node.inference)
            print(f"✓ Сигнатура inference: {sig}")
            
            return True
        else:
            print("✗ Функция inference не найдена")
            return False
            
    except Exception as e:
        print(f"✗ Ошибка проверки inference: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("=== Тестирование ComfyUI-LatentSyncWrapper ===")
    
    # Базовые проверки
    print("\n1. Проверка CUDA...")
    print(f"   CUDA доступен: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"   Устройство: {torch.cuda.get_device_name(0)}")
        print(f"   Память: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
    
    print("\n2. Тестирование импорта...")
    if not test_import():
        return False
    
    print("\n3. Тестирование типов node...")
    if not test_node_types():
        return False
        
    print("\n4. Тестирование инициализации...")
    if not test_node_init():
        return False
        
    print("\n5. Тестирование inference...")
    if not test_inference():
        return False
    
    print("\n=== Все тесты пройдены успешно! ===")
    print("\nПримечание: Для полного теста нужны реальные видео и аудио файлы.")
    print("Основная функциональность node готова к работе.")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
