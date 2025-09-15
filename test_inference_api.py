import json
import urllib.request
import urllib.parse
import time
import os

# Простой тест workflow через API
workflow = {
    "1": {
        "class_type": "LatentSyncNode",
        "inputs": {
            "images": [
                [[1, 1, 1], [1, 1, 1]],  # Dummy 2x3 image tensor
                [[1, 1, 1], [1, 1, 1]]
            ],
            "audio": {
                "waveform": [[0.1, 0.2, 0.1, 0.2] * 1000],  # Dummy audio
                "sample_rate": 44100
            },
            "seed": 42,
            "lips_expression": 1.5,
            "inference_steps": 2  # Минимум для быстрого теста
        }
    }
}

try:
    # Отправляем запрос
    data = json.dumps({"prompt": workflow}).encode('utf-8')
    req = urllib.request.Request("http://localhost:8188/prompt", data=data)
    req.add_header('Content-Type', 'application/json')
    
    print("Отправляю тестовый workflow...")
    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read())
        print(f"✅ Запрос отправлен: {result}")

except Exception as e:
    print(f"❌ Ошибка API: {e}")
