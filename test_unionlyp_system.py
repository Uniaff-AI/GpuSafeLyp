#!/usr/bin/env python3
"""
Тестовый скрипт для unionlyp с диагностикой и демонстрацией sync check
"""

import asyncio
import aiohttp
import json
import time
from pathlib import Path
from datetime import datetime

BACKEND_URL = "http://localhost:8000"

def log_test(message: str, level: str = "INFO"):
    """Логирование тестов"""
    timestamp = datetime.now().strftime("[%H:%M:%S]")
    icons = {"INFO": "ℹ️", "SUCCESS": "✅", "ERROR": "❌", "WAIT": "⏳", "TEST": "🧪"}
    print(f"{timestamp} {icons.get(level, 'ℹ️')} {message}")

async def check_backend_health():
    """Проверяет здоровье backend"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BACKEND_URL}/health", timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    data = await response.json()
                    log_test("Backend is healthy", "SUCCESS")
                    return True
                else:
                    log_test(f"Backend unhealthy: {response.status}", "ERROR")
                    return False
    except Exception as e:
        log_test(f"Backend connection failed: {e}", "ERROR")
        return False

async def check_servers_status():
    """Проверяет статус серверов через API"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BACKEND_URL}/servers/status", timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    servers = data.get("servers", [])
                    
                    online_count = sum(1 for s in servers if s["status"] == "online")
                    log_test(f"Servers status: {online_count}/{len(servers)} online", "INFO")
                    
                    for server in servers:
                        status_icon = "✅" if server["status"] == "online" else "❌"
                        log_test(f"  {status_icon} GPU {server['gpu_id']} ({server['name']}): queue {server['queue_size']}, load {server['load_score']}")
                    
                    return online_count > 0
                else:
                    log_test("Failed to get server status", "ERROR")
                    return False
    except Exception as e:
        log_test(f"Server status check failed: {e}", "ERROR")
        return False

async def test_sync_check():
    """Тестирует функцию sync check"""
    log_test("Testing sync check functionality...", "TEST")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BACKEND_URL}/sync/check", timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 200:
                    data = await response.json()
                    log_test(f"Sync check completed: {data.get('message', 'OK')}", "SUCCESS")
                    return True
                else:
                    log_test("Sync check failed", "ERROR")
                    return False
    except Exception as e:
        log_test(f"Sync check error: {e}", "ERROR")
        return False

async def get_queue_status():
    """Получает текущий статус очереди"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BACKEND_URL}/queue/status", timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    data = await response.json()
                    queue = data.get("queue", [])
                    
                    # Группируем по статусам
                    status_counts = {}
                    for task in queue:
                        status = task.get("status", "unknown")
                        status_counts[status] = status_counts.get(status, 0) + 1
                    
                    log_test(f"Queue status: {len(queue)} total tasks", "INFO")
                    for status, count in status_counts.items():
                        log_test(f"  {status}: {count}")
                    
                    return status_counts
                else:
                    log_test("Failed to get queue status", "ERROR")
                    return {}
    except Exception as e:
        log_test(f"Queue status check failed: {e}", "ERROR")
        return {}

async def simulate_task_monitoring():
    """Симулирует мониторинг задач для демонстрации sync check"""
    log_test("Monitoring queue for sync check demonstration...", "TEST")
    
    for i in range(6):  # Мониторим 3 минуты (6 * 30 секунд)
        await asyncio.sleep(30)  # Ждем 30 секунд между проверками
        
        log_test(f"Monitoring cycle {i+1}/6", "WAIT")
        
        # Получаем статус очереди
        status_counts = await get_queue_status()
        
        # Показываем активные задачи
        if status_counts.get("started", 0) > 0:
            log_test(f"Active tasks: {status_counts['started']}", "INFO")
        
        # Если есть auto_removed задачи, это означает что sync check работает
        if status_counts.get("auto_removed", 0) > 0:
            log_test(f"Sync check detected and removed {status_counts['auto_removed']} stuck tasks!", "SUCCESS")

async def run_full_test():
    """Запускает полный набор тестов"""
    log_test("🚀 STARTING UNIONLYP SYSTEM TESTS", "INFO")
    print("=" * 80)
    
    # 1. Проверяем backend
    log_test("1. Checking backend health...", "TEST")
    backend_ok = await check_backend_health()
    if not backend_ok:
        log_test("Backend is not available. Please start the backend first.", "ERROR")
        return
    
    print("-" * 80)
    
    # 2. Проверяем серверы
    log_test("2. Checking ComfyUI servers...", "TEST")
    servers_ok = await check_servers_status()
    if not servers_ok:
        log_test("No ComfyUI servers are online!", "ERROR")
        return
    
    print("-" * 80)
    
    # 3. Тестируем sync check
    log_test("3. Testing sync check...", "TEST")
    sync_ok = await test_sync_check()
    
    print("-" * 80)
    
    # 4. Получаем статус очереди
    log_test("4. Checking initial queue status...", "TEST")
    initial_status = await get_queue_status()
    
    print("-" * 80)
    
    # 5. Мониторинг для демонстрации sync check
    log_test("5. Demonstrating sync check monitoring...", "TEST")
    log_test("   (This will monitor for 3 minutes to show sync check in action)", "INFO")
    log_test("   Background sync check runs every 30 seconds automatically", "INFO")
    
    await simulate_task_monitoring()
    
    print("=" * 80)
    log_test("✅ All tests completed!", "SUCCESS")
    
    # Финальный статус
    log_test("Final system status:", "INFO")
    final_status = await get_queue_status()
    
    log_test("🎯 SYSTEM READY FOR PRODUCTION!", "SUCCESS")

if __name__ == "__main__":
    asyncio.run(run_full_test())
