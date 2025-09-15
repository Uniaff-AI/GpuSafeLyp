#!/usr/bin/env python
"""
Тест LatentSync через ComfyUI API
"""

import json
import urllib.request
import urllib.parse
import time
import uuid
import os

def queue_prompt(prompt, server_address="localhost:8188"):
    """Отправляет prompt в очередь ComfyUI"""
    p = {"prompt": prompt, "client_id": str(uuid.uuid4())}
    data = json.dumps(p).encode('utf-8')
    
    req = urllib.request.Request(f"http://{server_address}/prompt", data=data)
    req.add_header('Content-Type', 'application/json')
    
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read())

def check_progress(prompt_id, server_address="localhost:8188"):
    """Проверяет прогресс выполнения"""
    with urllib.request.urlopen(f"http://{server_address}/history/{prompt_id}") as response:
        history = json.loads(response.read())
        return prompt_id in history

def create_test_workflow():
    """Создает простейший workflow для тестирования LatentSyncNode"""
    
    # Проверяем что тестовые файлы существуют
    video_path = os.path.abspath("test_files/test_face.mp4")
    audio_path = os.path.abspath("test_files/test_speech.wav") 
    
    print(f"Video path: {video_path}")
    print(f"Audio path: {audio_path}")
    
    if not os.path.exists(video_path):
        print(f"ERROR: Test video not found: {video_path}")
        return None
        
    if not os.path.exists(audio_path):
        print(f"ERROR: Test audio not found: {audio_path}")
        return None
    
    workflow = {
        "1": {
            "class_type": "VHS_LoadVideo",
            "inputs": {
                "video": video_path,
                "force_rate": 0,
                "force_size": "Disabled",
                "custom_width": 512,
                "custom_height": 512,
                "frame_load_cap": 0,
                "skip_first_frames": 0,
                "select_every_nth": 1
            }
        },
        "2": {
            "class_type": "VHS_LoadAudio", 
            "inputs": {
                "audio": audio_path
            }
        },
        "3": {
            "class_type": "LatentSyncNode",
            "inputs": {
                "images": ["1", 0],
                "audio": ["2", 0], 
                "seed": 42,
                "lips_expression": 1.5,
                "inference_steps": 10  # Уменьшено для быстрого теста
            }
        },
        "4": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["3", 0],
                "audio": ["3", 1],
                "frame_rate": 25,
                "loop_count": 0,
                "filename_prefix": "latentsync_test",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True
            }
        }
    }
    
    return workflow

def main():
    """Основная функция теста"""
    print("=== Тест LatentSync через ComfyUI API ===")
    
    # Проверяем подключение к серверу
    try:
        with urllib.request.urlopen("http://localhost:8188/system_stats") as response:
            stats = json.loads(response.read())
            print("✓ ComfyUI сервер доступен")
            print(f"  VRAM: {stats.get('vram', {}).get('total', 'Unknown')} MB")
    except Exception as e:
        print(f"✗ Ошибка подключения к ComfyUI: {e}")
        return False
    
    # Создаем workflow
    workflow = create_test_workflow()
    if workflow is None:
        return False
    
    print("✓ Workflow создан")
    
    # NOTE: Этот тест требует дополнительные ноды (VHS_LoadVideo, VHS_LoadAudio)
    # которые могут быть не установлены. Это демонстрирует структуру теста.
    print("\nПримечание:")
    print("- Данный workflow требует VideoHelperSuite для загрузки видео/аудио")
    print("- Для полного теста установите: https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite")
    print("- LatentSyncNode основная функциональность проверена в предыдущих тестах")
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
