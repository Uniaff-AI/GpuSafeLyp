#!/usr/bin/env python3
"""
Диагностические утилиты для unionlyp - анализ проблем с многопользовательскими задачами
"""

import asyncio
import json
import os
import subprocess
import aiohttp
from pathlib import Path
from datetime import datetime
from typing import List, Dict

# ComfyUI серверы
COMFYUI_SERVERS = [
    {"name": "GPU Server 1", "url": "localhost:8188", "gpu_id": 0},
    {"name": "GPU Server 2", "url": "localhost:8189", "gpu_id": 1},
    {"name": "GPU Server 3", "url": "localhost:8190", "gpu_id": 2},
    {"name": "GPU Server 4", "url": "localhost:8196", "gpu_id": 3},
    {"name": "GPU Server 5", "url": "localhost:8192", "gpu_id": 4},
    {"name": "GPU Server 6", "url": "localhost:8193", "gpu_id": 5},
    {"name": "GPU Server 7", "url": "localhost:8194", "gpu_id": 6},
    {"name": "GPU Server 8", "url": "localhost:8195", "gpu_id": 7}
]

# Директории для проверки файлов
UPLOAD_DIR = Path("uploads")
COMFYUI_INPUT_DIRS = [
    Path("ComfyUI-Production/input"),
    Path("ComfyUI/input"),
    Path("ComfyUI/ComfyUI_main/input"),
    Path("ComfyUI_deployment/ComfyUI/input")
]

def log_diagnostic(message: str, level: str = "INFO"):
    """Логирование с временной меткой"""
    timestamp = datetime.now().strftime("[%H:%M:%S]")
    icon = {"INFO": "ℹ️", "WARN": "⚠️", "ERROR": "❌", "OK": "✅", "SEARCH": "🔍"}[level]
    print(f"{timestamp} {icon} {message}")

def check_file_permissions(file_path: Path) -> Dict:
    """Проверяет права доступа к файлу"""
    if not file_path.exists():
        return {"exists": False, "error": f"File {file_path} does not exist"}
    
    try:
        stat = file_path.stat()
        permissions = oct(stat.st_mode)[-3:]
        owner_uid = stat.st_uid
        owner_gid = stat.st_gid
        
        # Получаем имя пользователя и группы
        import pwd, grp
        try:
            owner_name = pwd.getpwuid(owner_uid).pw_name
        except KeyError:
            owner_name = f"uid:{owner_uid}"
        
        try:
            group_name = grp.getgrgid(owner_gid).gr_name
        except KeyError:
            group_name = f"gid:{owner_gid}"
        
        # Проверяем читаемость
        readable = file_path.is_file() and os.access(file_path, os.R_OK)
        
        return {
            "exists": True,
            "permissions": permissions,
            "owner": owner_name,
            "group": group_name,
            "readable": readable,
            "size": stat.st_size
        }
    except Exception as e:
        return {"exists": True, "error": f"Permission check failed: {e}"}

async def check_comfyui_server_status(server_url: str) -> Dict:
    """Проверяет статус ComfyUI сервера"""
    try:
        async with aiohttp.ClientSession() as session:
            # Проверка базового API
            async with session.get(f"http://{server_url}/", timeout=aiohttp.ClientTimeout(total=5)) as response:
                api_status = response.status == 200
            
            # Проверка очереди
            queue_status = False
            queue_info = {}
            try:
                async with session.get(f"http://{server_url}/queue", timeout=aiohttp.ClientTimeout(total=3)) as response:
                    if response.status == 200:
                        queue_data = await response.json()
                        queue_status = True
                        queue_info = {
                            "running": len(queue_data.get('queue_running', [])),
                            "pending": len(queue_data.get('queue_pending', []))
                        }
            except:
                pass
            
            # Проверка системной информации
            system_status = False
            system_info = {}
            try:
                async with session.get(f"http://{server_url}/system_stats", timeout=aiohttp.ClientTimeout(total=3)) as response:
                    if response.status == 200:
                        system_data = await response.json()
                        system_status = True
                        if system_data.get('devices'):
                            device = system_data['devices'][0]
                            system_info = {
                                "vram_total": device.get('vram_total', 0),
                                "vram_free": device.get('vram_free', 0),
                                "vram_used": device.get('vram_total', 0) - device.get('vram_free', 0)
                            }
            except:
                pass
            
            return {
                "online": api_status,
                "api_responsive": api_status,
                "queue_accessible": queue_status,
                "queue_info": queue_info,
                "system_accessible": system_status,
                "system_info": system_info
            }
    except Exception as e:
        return {
            "online": False,
            "api_responsive": False,
            "error": str(e)
        }

def get_process_info() -> List[Dict]:
    """Получает информацию о запущенных ComfyUI процессах"""
    try:
        # Ищем процессы ComfyUI
        result = subprocess.run([
            'ps', 'aux'
        ], capture_output=True, text=True)
        
        processes = []
        for line in result.stdout.split('\n'):
            if 'main.py' in line and any(f'port {server["url"].split(":")[1]}' in line for server in COMFYUI_SERVERS):
                parts = line.split()
                if len(parts) >= 11:
                    processes.append({
                        "user": parts[0],
                        "pid": parts[1],
                        "cpu": parts[2],
                        "mem": parts[3],
                        "command": ' '.join(parts[10:])
                    })
        
        return processes
    except Exception as e:
        log_diagnostic(f"Failed to get process info: {e}", "ERROR")
        return []

async def diagnose_file_accessibility():
    """Диагностирует доступность файлов в разных ComfyUI директориях"""
    log_diagnostic("🔍 ДИАГНОСТИКА ДОСТУПНОСТИ ФАЙЛОВ", "SEARCH")
    
    # Проверяем uploads директорию
    if UPLOAD_DIR.exists():
        log_diagnostic(f"📁 Uploads directory: {UPLOAD_DIR.absolute()}")
        upload_files = list(UPLOAD_DIR.glob("*"))
        log_diagnostic(f"   Found {len(upload_files)} files in uploads")
        
        # Показываем несколько примеров файлов
        for file_path in upload_files[:3]:
            perm_info = check_file_permissions(file_path)
            if perm_info.get("exists"):
                log_diagnostic(f"   📄 {file_path.name}: {perm_info.get('permissions', 'unknown')} {perm_info.get('owner', 'unknown')}:{perm_info.get('group', 'unknown')} ({perm_info.get('size', 0)} bytes)")
            else:
                log_diagnostic(f"   ❌ {file_path.name}: {perm_info.get('error', 'Unknown error')}", "ERROR")
    else:
        log_diagnostic("📁 Uploads directory does not exist!", "ERROR")
    
    # Проверяем ComfyUI input директории
    for input_dir in COMFYUI_INPUT_DIRS:
        log_diagnostic(f"📂 Checking ComfyUI input dir: {input_dir.absolute()}")
        
        if input_dir.exists():
            try:
                files = list(input_dir.glob("*"))
                log_diagnostic(f"   Found {len(files)} files")
                
                # Проверяем директорию на права записи
                dir_stat = input_dir.stat()
                dir_perms = oct(dir_stat.st_mode)[-3:]
                log_diagnostic(f"   Directory permissions: {dir_perms}")
                
                # Проверяем несколько файлов
                for file_path in files[:3]:
                    perm_info = check_file_permissions(file_path)
                    if perm_info.get("exists") and not perm_info.get("error"):
                        readable_status = "✅ readable" if perm_info.get("readable") else "❌ not readable"
                        log_diagnostic(f"   📄 {file_path.name}: {perm_info.get('permissions')} {readable_status}")
                    else:
                        log_diagnostic(f"   ❌ {file_path.name}: {perm_info.get('error', 'Permission error')}", "ERROR")
                        
            except PermissionError:
                log_diagnostic(f"   ❌ Permission denied to access {input_dir}", "ERROR")
            except Exception as e:
                log_diagnostic(f"   ❌ Error accessing {input_dir}: {e}", "ERROR")
        else:
            log_diagnostic(f"   ⚠️  Directory does not exist", "WARN")

async def diagnose_comfyui_servers():
    """Диагностирует состояние ComfyUI серверов"""
    log_diagnostic("🔍 ДИАГНОСТИКА COMFYUI СЕРВЕРОВ", "SEARCH")
    
    for server in COMFYUI_SERVERS:
        server_url = server["url"]
        gpu_id = server["gpu_id"]
        
        log_diagnostic(f"🖥️  Checking {server['name']} (GPU {gpu_id}) - {server_url}")
        
        # Проверяем статус сервера
        status = await check_comfyui_server_status(server_url)
        
        if status["online"]:
            log_diagnostic(f"   ✅ Server is online and responsive", "OK")
            
            if status["queue_accessible"]:
                queue_info = status["queue_info"]
                log_diagnostic(f"   📊 Queue: {queue_info.get('running', 0)} running, {queue_info.get('pending', 0)} pending")
            else:
                log_diagnostic(f"   ⚠️  Queue API not accessible", "WARN")
            
            if status["system_accessible"]:
                sys_info = status["system_info"]
                vram_used_pct = (sys_info.get('vram_used', 0) / max(sys_info.get('vram_total', 1), 1)) * 100
                log_diagnostic(f"   💾 VRAM: {sys_info.get('vram_used', 0)}MB / {sys_info.get('vram_total', 0)}MB ({vram_used_pct:.1f}%)")
            else:
                log_diagnostic(f"   ⚠️  System stats not accessible", "WARN")
        else:
            log_diagnostic(f"   ❌ Server is offline or not responding", "ERROR")
            if status.get("error"):
                log_diagnostic(f"   Error: {status['error']}")

def diagnose_processes():
    """Диагностирует запущенные процессы ComfyUI"""
    log_diagnostic("🔍 ДИАГНОСТИКА ПРОЦЕССОВ COMFYUI", "SEARCH")
    
    processes = get_process_info()
    
    if not processes:
        log_diagnostic("❌ No ComfyUI processes found running!", "ERROR")
        return
    
    log_diagnostic(f"Found {len(processes)} ComfyUI processes:")
    
    for proc in processes:
        cpu_usage = f"{proc['cpu']}%" if proc['cpu'] else "0%"
        mem_usage = f"{proc['mem']}%" if proc['mem'] else "0%"
        log_diagnostic(f"   🔧 PID {proc['pid']} (User: {proc['user']}) CPU: {cpu_usage} MEM: {mem_usage}")
        
        # Извлекаем порт и GPU из команды
        command = proc['command']
        port = None
        gpu = None
        
        if '--port' in command:
            parts = command.split('--port')
            if len(parts) > 1:
                port_part = parts[1].strip().split()[0]
                port = port_part
        
        if '--cuda-device' in command:
            parts = command.split('--cuda-device')
            if len(parts) > 1:
                gpu_part = parts[1].strip().split()[0]
                gpu = gpu_part
        
        log_diagnostic(f"      Port: {port or 'unknown'}, GPU: {gpu or 'unknown'}")

def check_backend_status():
    """Проверяет состояние backend процесса"""
    log_diagnostic("🔍 ДИАГНОСТИКА BACKEND", "SEARCH")
    
    try:
        # Проверяем процессы backend
        result = subprocess.run([
            'ps', 'aux'
        ], capture_output=True, text=True)
        
        backend_processes = []
        for line in result.stdout.split('\n'):
            if 'backend' in line and 'python' in line:
                parts = line.split()
                if len(parts) >= 11:
                    backend_processes.append({
                        "user": parts[0],
                        "pid": parts[1],
                        "cpu": parts[2],
                        "mem": parts[3],
                        "command": ' '.join(parts[10:])
                    })
        
        if backend_processes:
            for proc in backend_processes:
                log_diagnostic(f"✅ Backend PID {proc['pid']} (User: {proc['user']}) CPU: {proc['cpu']}% MEM: {proc['mem']}%", "OK")
        else:
            log_diagnostic("⚠️  No backend processes found", "WARN")
        
        # Проверяем доступность backend API
        try:
            result = subprocess.run([
                'curl', '-s', '--max-time', '3', 'http://localhost:8000/health'
            ], capture_output=True, text=True)
            
            if result.returncode == 0 and 'healthy' in result.stdout:
                log_diagnostic("✅ Backend API is responding", "OK")
            else:
                log_diagnostic("❌ Backend API is not responding", "ERROR")
        except:
            log_diagnostic("❌ Failed to check backend API", "ERROR")
            
    except Exception as e:
        log_diagnostic(f"Error checking backend: {e}", "ERROR")

async def full_diagnostic():
    """Запускает полную диагностику системы"""
    log_diagnostic("🚀 ЗАПУСК ПОЛНОЙ ДИАГНОСТИКИ UNIONLYP", "INFO")
    print("=" * 60)
    
    # 1. Проверяем процессы
    diagnose_processes()
    print("-" * 60)
    
    # 2. Проверяем backend
    check_backend_status()
    print("-" * 60)
    
    # 3. Проверяем файлы
    await diagnose_file_accessibility()
    print("-" * 60)
    
    # 4. Проверяем ComfyUI серверы
    await diagnose_comfyui_servers()
    print("=" * 60)
    
    log_diagnostic("✅ Диагностика завершена", "OK")

if __name__ == "__main__":
    asyncio.run(full_diagnostic())
