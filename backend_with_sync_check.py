#!/usr/bin/env python3
import asyncio
import json
import logging
import shutil
import uuid
import time
import subprocess
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, List

import aiofiles
import aiohttp
import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="unionlyp API with Smart Balancer & Sync Check (8 Servers)", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration - ALL 8 GPU SERVERS
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

UPLOAD_DIR = Path("uploads")
# Multiple ComfyUI input directories
COMFYUI_INPUT_DIRS = [
    Path("ComfyUI-Production/input"),
    Path("ComfyUI/input"),
    Path("ComfyUI/ComfyUI_main/input"),
    Path("ComfyUI_deployment/ComfyUI/input")
]

UPLOAD_DIR.mkdir(exist_ok=True)

# Task storage and server tracking
tasks: Dict[str, dict] = {}
server_loads: Dict[str, dict] = {}
server_error_counts: Dict[str, int] = {}  # Трекинг ошибок серверов
last_oom_recovery: Dict[str, float] = {}  # Время последнего восстановления от OOM

# File mapping storage - maps UUID filenames to original names
file_mappings: Dict[str, str] = {}

class GenerateRequest(BaseModel):
    audio_file: str
    video_file: str

def log_with_time(message: str):
    timestamp = datetime.now().strftime("[%H:%M:%S]")
    print(f"{timestamp} {message}")
    logger.info(message)

def to_moscow_time(utc_dt: datetime = None) -> datetime:
    """Конвертирует UTC время в московское время (UTC+3)"""
    if utc_dt is None:
        utc_dt = datetime.now(timezone.utc)
    moscow_dt = utc_dt.replace(tzinfo=timezone.utc) + timezone.utc.utcoffset(utc_dt) + (timezone.utc.utcoffset(utc_dt) or 0) + (3 * 3600)
    return datetime.fromtimestamp(moscow_dt.timestamp())

def format_duration(start_time: datetime, end_time: datetime = None) -> str:
    """Форматирует продолжительность выполнения"""
    if end_time is None:
        end_time = datetime.now()
    
    duration = end_time - start_time
    total_seconds = int(duration.total_seconds())
    
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

def generate_random_seed() -> int:
    """Генерирует случайное seed значение от 1 до 999999"""
    seed = random.randint(1, 999999)
    log_with_time(f"🎲 Generated random seed: {seed}")
    return seed

def copy_file_to_all_comfyui_dirs(file_path: Path, original_name: str):
    """Копируем файл во все возможные ComfyUI input директории"""
    copied_count = 0
    for input_dir in COMFYUI_INPUT_DIRS:
        if input_dir.exists():
            try:
                target_path = input_dir / original_name
                shutil.copy2(file_path, target_path)
                # Устанавливаем права доступа 644 для всех
                target_path.chmod(0o644)
                log_with_time(f"📂 Copied to: {target_path} (permissions: 644)")
                copied_count += 1
            except Exception as e:
                log_with_time(f"⚠️  Failed to copy to {input_dir}: {e}")
    
    if copied_count == 0:
        log_with_time(f"⚠️  No ComfyUI input directories found!")
    else:
        log_with_time(f"✅ File copied to {copied_count} ComfyUI directories")

async def check_gpu_utilization(gpu_id: int) -> float:
    """Проверка загрузки GPU через nvidia-smi"""
    try:
        result = subprocess.run([
            'nvidia-smi', '--query-gpu=utilization.gpu', 
            '--format=csv,noheader,nounits', f'--id={gpu_id}'
        ], capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            util = float(result.stdout.strip())
            return util
        else:
            return 0.0
    except Exception as e:
        log_with_time(f"⚠️  Failed to check GPU {gpu_id} utilization: {e}")
        return 0.0

async def check_comfyui_queue(server_url: str) -> dict:
    """Проверка очереди ComfyUI сервера"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://{server_url}/queue", timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    queue_data = await response.json()
                    running = len(queue_data.get('queue_running', []))
                    pending = len(queue_data.get('queue_pending', []))
                    return {"running": running, "pending": pending, "total": running + pending}
                else:
                    return {"running": 0, "pending": 0, "total": 0}
    except Exception as e:
        log_with_time(f"⚠️  Failed to check ComfyUI queue {server_url}: {e}")
        return {"running": 0, "pending": 0, "total": 0}

async def sync_check_backend_comfyui():
    """🔍 ПЕРИОДИЧЕСКАЯ ПРОВЕРКА СООТВЕТСТВИЯ BACKEND ↔ COMFYUI"""
    log_with_time("🔍 Starting sync check: backend ↔ ComfyUI")
    
    # Получаем все активные задачи из backend
    backend_active_tasks = [t for t in tasks.values() if t['status'] == 'started']
    
    if not backend_active_tasks:
        log_with_time("✅ No active tasks in backend - sync check passed")
        return
    
    log_with_time(f"🔍 Checking {len(backend_active_tasks)} active tasks in backend")
    
    stuck_tasks = []
    
    for task in backend_active_tasks:
        task_id = task['task_id']
        server_url = task['server_url']
        
        # Определяем GPU ID
        port = server_url.split(':')[-1]
        gpu_map = {'8188': 0, '8189': 1, '8190': 2, '8196': 3, '8192': 4, '8193': 5, '8194': 6, '8195': 7}
        gpu_id = gpu_map.get(port, 0)
        
        # Время выполнения задачи
        started_at = datetime.fromisoformat(task['created_at'].replace('Z', '+00:00'))
        duration_mins = (datetime.now(started_at.tzinfo) - started_at).total_seconds() / 60
        
        # Проверяем если задача висит больше 8 минут
        if duration_mins > 8:
            # Проверяем загрузку GPU
            gpu_util = await check_gpu_utilization(gpu_id)
            
            # Проверяем очередь ComfyUI
            comfyui_queue = await check_comfyui_queue(server_url)
            
            log_with_time(f"🔍 Task {task_id[:8]}... (GPU {gpu_id}): {duration_mins:.1f}m, GPU: {gpu_util}%, ComfyUI queue: {comfyui_queue['total']}")
            
            # Если GPU не загружен и очереди нет - задача зависла
            if gpu_util < 10 and comfyui_queue['total'] == 0:
                stuck_tasks.append({
                    'task_id': task_id,
                    'duration_mins': duration_mins,
                    'gpu_id': gpu_id,
                    'gpu_util': gpu_util,
                    'server_url': server_url
                })
                log_with_time(f"⚠️  STUCK TASK DETECTED: {task_id[:8]}... on GPU {gpu_id} ({duration_mins:.1f}m, {gpu_util}% util)")
    
    # Удаляем зависшие задачи
    for stuck_task in stuck_tasks:
        task_id = stuck_task['task_id']
        log_with_time(f"🗑️  AUTO-REMOVING stuck task: {task_id[:8]}... (GPU {stuck_task['gpu_id']}, {stuck_task['duration_mins']:.1f}m)")
        
        if task_id in tasks:
            tasks[task_id].update({
                'status': 'auto_removed',
                'message': f'🤖 Auto-removed: stuck for {stuck_task["duration_mins"]:.1f}m with {stuck_task["gpu_util"]}% GPU util',
                'completed_at': datetime.now()
            })
    
    if stuck_tasks:
        log_with_time(f"🗑️  Removed {len(stuck_tasks)} stuck tasks")
    else:
        log_with_time("✅ All active tasks are processing correctly")

async def check_cuda_memory_and_recovery(server_url: str, gpu_id: int) -> bool:
    """Проверка и восстановление от CUDA Out of Memory"""
    try:
        # Проверяем память GPU через nvidia-smi
        result = subprocess.run([
            'nvidia-smi', '--query-gpu=memory.free,memory.used,memory.total', 
            '--format=csv,noheader,nounits', f'--id={gpu_id}'
        ], capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            memory_info = result.stdout.strip().split(',')
            free_mem = int(memory_info[0].strip())
            used_mem = int(memory_info[1].strip())
            total_mem = int(memory_info[2].strip())
            
            usage_percent = (used_mem / total_mem) * 100
            
            # Если память почти закончилась (>95%)
            if usage_percent > 95:
                log_with_time(f"🚨 GPU {gpu_id} memory critical: {usage_percent:.1f}% used ({used_mem}MB/{total_mem}MB)")
                
                # Пытаемся освободить память через API ComfyUI
                await clear_comfyui_memory(server_url)
                
                # Запоминаем время восстановления
                last_oom_recovery[server_url] = time.time()
                
                return False  # Сервер временно недоступен
            
        return True  # Память в порядке
        
    except Exception as e:
        log_with_time(f"⚠️  Failed to check GPU {gpu_id} memory: {e}")
        return True  # В случае ошибки проверки, считаем что все в порядке

async def clear_comfyui_memory(server_url: str):
    """Попытка освободить память ComfyUI через API"""
    try:
        async with aiohttp.ClientSession() as session:
            # Очищаем очередь
            async with session.post(f"http://{server_url}/queue", 
                                  json={"clear": True}, 
                                  timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    log_with_time(f"🧹 Cleared queue for {server_url}")
            
            # Запрос освобождения памяти
            async with session.post(f"http://{server_url}/free", 
                                  json={"unload_models": True, "free_memory": True},
                                  timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    log_with_time(f"🧹 Freed memory for {server_url}")
                    
            # Небольшая пауза для освобождения памяти
            await asyncio.sleep(2)
            
    except Exception as e:
        log_with_time(f"⚠️  Failed to clear memory for {server_url}: {e}")

async def restart_comfyui_server_if_needed(server_url: str, gpu_id: int) -> bool:
    """Перезапуск ComfyUI сервера в критических случаях"""
    try:
        port = server_url.split(':')[-1]
        
        log_with_time(f"🔄 Attempting to restart ComfyUI server on port {port} (GPU {gpu_id})")
        
        # Находим и убиваем процесс
        kill_cmd = f"pkill -f 'main.py.*port {port}.*cuda-device {gpu_id}'"
        subprocess.run(kill_cmd, shell=True, timeout=10)
        
        await asyncio.sleep(3)
        
        # Запускаем заново
        restart_cmd = f"""
        cd /home/epycmax/miniconda3/envs/latentsync && 
        source activate latentsync && 
        cd /home/epycmax/ComfyUI-Production && 
        python main.py --listen 0.0.0.0 --port {port} --enable-cors-header --cuda-device {gpu_id} > /home/epycmax/comfyui_gpu{gpu_id}_{port}.log 2>&1 &
        """
        
        subprocess.run(restart_cmd, shell=True)
        
        log_with_time(f"🔄 Restarted ComfyUI server on port {port} (GPU {gpu_id})")
        
        # Даем время на запуск
        await asyncio.sleep(10)
        
        return True
        
    except Exception as e:
        log_with_time(f"❌ Failed to restart server {server_url}: {e}")
        return False

async def get_server_stats(server_url: str) -> Optional[dict]:
    """Получаем статистику сервера с защитой от OOM"""
    gpu_id = None
    
    # Определяем GPU ID из конфигурации
    for server in COMFYUI_SERVERS:
        if server["url"] == server_url:
            gpu_id = server["gpu_id"]
            break
    
    if gpu_id is None:
        return {"online": False, "queue_size": 999, "vram_used": 0, "vram_total": 0, "load_score": 999}
    
    # Проверяем не было ли недавнего восстановления от OOM
    if server_url in last_oom_recovery and (time.time() - last_oom_recovery[server_url]) < 30:
        log_with_time(f"⏳ Server {server_url} recovering from OOM, skipping for 30s")
        return {"online": False, "queue_size": 999, "vram_used": 0, "vram_total": 0, "load_score": 999}
    
    # Проверяем память GPU перед запросом
    memory_ok = await check_cuda_memory_and_recovery(server_url, gpu_id)
    if not memory_ok:
        return {"online": False, "queue_size": 999, "vram_used": 0, "vram_total": 0, "load_score": 999}
    
    try:
        async with aiohttp.ClientSession() as session:
            # Проверяем очередь с таймаутом
            async with session.get(f"http://{server_url}/queue", timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    queue_data = await response.json()
                    queue_size = len(queue_data.get('queue_running', [])) + len(queue_data.get('queue_pending', []))
                    
                    # Сбрасываем счетчик ошибок при успешном ответе
                    server_error_counts[server_url] = 0
                else:
                    queue_size = -1
            
            # Проверяем системные ресурсы
            async with session.get(f"http://{server_url}/system_stats", timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    system_data = await response.json()
                    vram_used = 0
                    vram_total = 0
                    if system_data.get('devices'):
                        device = system_data['devices'][0]
                        vram_used = device.get('vram_total', 0) - device.get('vram_free', 0)
                        vram_total = device.get('vram_total', 0)
                else:
                    vram_used = 0
                    vram_total = 0
                    
            return {
                "online": True,
                "queue_size": queue_size if queue_size >= 0 else 999,
                "vram_used": vram_used,
                "vram_total": vram_total,
                "load_score": queue_size * 10 + (vram_used / max(vram_total, 1)) * 5
            }
    except Exception as e:
        # Увеличиваем счетчик ошибок
        server_error_counts[server_url] = server_error_counts.get(server_url, 0) + 1
        
        log_with_time(f"⚠️  Server {server_url} error #{server_error_counts[server_url]}: {e}")
        
        # Если много ошибок подряд, пытаемся перезапустить сервер
        if server_error_counts[server_url] >= 5:
            log_with_time(f"🔄 Too many errors for {server_url}, attempting restart...")
            await restart_comfyui_server_if_needed(server_url, gpu_id)
            server_error_counts[server_url] = 0  # Сбрасываем счетчик после попытки перезапуска
        
        return {"online": False, "queue_size": 999, "vram_used": 0, "vram_total": 0, "load_score": 999}

async def update_server_loads():
    """Обновляем информацию о нагрузке серверов"""
    for server in COMFYUI_SERVERS:
        server_url = server["url"]
        stats = await get_server_stats(server_url)
        server_loads[server_url] = {
            **server,
            **stats,
            "last_updated": time.time()
        }

async def find_best_server() -> Optional[str]:
    """Находим лучший сервер с наименьшей нагрузкой"""
    await update_server_loads()
    
    # Фильтруем только онлайн серверы
    online_servers = {url: data for url, data in server_loads.items() if data.get("online", False)}
    
    if not online_servers:
        log_with_time("⚠️  No online servers available!")
        return None
    
    # Выбираем сервер с наименьшей нагрузкой
    best_server = min(online_servers.items(), key=lambda x: x[1]["load_score"])
    
    log_with_time(f"🎯 Selected server {best_server[0]} (load: {best_server[1]['load_score']:.1f}, queue: {best_server[1]['queue_size']})")
    
    return best_server[0]

def get_workflow_json(audio_filename: str, video_filename: str) -> dict:
    # Генерируем случайный seed для каждого запуска
    random_seed = generate_random_seed()
    
    return {
        "40": {
            "inputs": {
                "video": video_filename,
                "force_rate": 25.0,
                "custom_width": 0,
                "custom_height": 768,
                "frame_load_cap": 0,
                "skip_first_frames": 0,
                "select_every_nth": 1,
                "format": "AnimateDiff",
                "choose video to upload": "image"
            },
            "class_type": "VHS_LoadVideo",
            "_meta": {"title": "Load Video"}
        },
        "37": {
            "inputs": {"audio": audio_filename},
            "class_type": "LoadAudio",
            "_meta": {"title": "Load Audio"}
        },
        "55": {
            "inputs": {
                "images": ["40", 0],
                "audio": ["37", 0],
                "mode": "pingpong",
                "fps": 25.0,
                "smooth_factor": 0.5,
                "silent_padding_sec": 0.5
            },
            "class_type": "VideoLengthAdjuster",
            "_meta": {"title": "Adjust Video Length"}
        },
        "54": {
            "inputs": {
                "images": ["55", 0],
                "audio": ["55", 1],
                "seed": random_seed,  # ✨ ТЕПЕРЬ РАНДОМНЫЙ!
                "lips_expression": 1.5,
                "inference_steps": 8
            },
            "class_type": "LatentSyncNode",
            "_meta": {"title": "LatentSync Generation"}
        },
        "41": {
            "inputs": {
                "images": ["54", 0],
                "audio": ["54", 1],
                "frame_rate": 25.0,
                "loop_count": 0,
                "filename_prefix": "lipsync_result",
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 19,
                "save_metadata": True,
                "trim_to_audio": False,
                "pingpong": False,
                "save_output": True
            },
            "class_type": "VHS_VideoCombine",
            "_meta": {"title": "Save Video"}
        }
    }

async def submit_workflow_to_comfyui(server_url: str, workflow: dict, client_id: str) -> Optional[str]:
    try:
        prompt_data = {"prompt": workflow, "client_id": client_id}
        
        log_with_time(f"📤 Submitting workflow to {server_url} with client_id: {client_id[:8]}...")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"http://{server_url}/prompt", 
                                  json=prompt_data, 
                                  timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    result = await response.json()
                    prompt_id = result.get("prompt_id")
                    log_with_time(f"✅ Workflow submitted to {server_url}, prompt_id: {prompt_id}")
                    return prompt_id
                else:
                    error_text = await response.text()
                    log_with_time(f"❌ ComfyUI error {response.status}: {error_text}")
                    
                    # Проверяем на CUDA Out of Memory в ошибке
                    if "out of memory" in error_text.lower() or "cuda" in error_text.lower():
                        gpu_id = None
                        for server in COMFYUI_SERVERS:
                            if server["url"] == server_url:
                                gpu_id = server["gpu_id"]
                                break
                        
                        if gpu_id is not None:
                            log_with_time(f"🚨 CUDA OOM detected on {server_url}, initiating recovery...")
                            await clear_comfyui_memory(server_url)
                    
                    return None
    except Exception as e:
        log_with_time(f"❌ Submit error to {server_url}: {e}")
        return None

async def check_comfyui_result(server_url: str, prompt_id: str) -> Optional[dict]:
    """Проверяем результат в истории ComfyUI"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://{server_url}/history/{prompt_id}",
                                 timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    history = await response.json()
                    if prompt_id in history:
                        task_data = history[prompt_id]
                        if task_data.get("status", {}).get("completed"):
                            # Задача завершена, извлекаем результат
                            outputs = task_data.get("outputs", {})
                            if "41" in outputs and "gifs" in outputs["41"]:
                                video_info = outputs["41"]["gifs"][0]
                                return {
                                    "completed": True,
                                    "filename": video_info["filename"],
                                    "server_url": server_url
                                }
                return {"completed": False}
    except Exception as e:
        log_with_time(f"❌ Check result error: {e}")
        return None

async def monitor_task(task_id: str, server_url: str, prompt_id: str):
    """Мониторим выполнение задачи с защитой от OOM"""
    max_wait_time = 1800  # 30 минут
    check_interval = 5   # Проверяем каждые 5 секунд
    elapsed_time = 0
    
    while elapsed_time < max_wait_time:
        await asyncio.sleep(check_interval)
        elapsed_time += check_interval
        
        if task_id not in tasks:
            break
            
        # Проверяем результат в ComfyUI
        result = await check_comfyui_result(server_url, prompt_id)
        if result is None:
            continue
            
        # Обновляем прогресс
        progress = min(90, int((elapsed_time / max_wait_time) * 100))
        
        # Рассчитываем продолжительность
        start_time = tasks[task_id]["started_at"]
        duration = format_duration(start_time)
        
        tasks[task_id].update({
            "progress": progress,
            "message": f"⏳ Processing... ({duration})",
            "duration": duration
        })
        
        if result["completed"]:
            # Задача завершена успешно!
            end_time = datetime.now()
            total_duration = format_duration(start_time, end_time)
            result_url = f"http://89.208.11.177:{result['server_url'].split(':')[1]}/view?filename={result['filename']}"
            
            tasks[task_id].update({
                "status": "completed",
                "progress": 100,
                "message": f"✅ Completed in {total_duration}",
                "result_url": result_url,
                "completed_at": end_time,
                "duration": total_duration
            })
            log_with_time(f"✅ Task {task_id} completed in {total_duration}: {result['filename']}")
            break
    
    # Если время истекло и задача не завершена
    if task_id in tasks and tasks[task_id]["status"] not in ["completed", "failed"]:
        # Проверим еще раз на случай завершения
        result = await check_comfyui_result(server_url, prompt_id)
        if result and result["completed"]:
            end_time = datetime.now()
            start_time = tasks[task_id]["started_at"]
            total_duration = format_duration(start_time, end_time)
            result_url = f"http://89.208.11.177:{result['server_url'].split(':')[1]}/view?filename={result['filename']}"
            
            tasks[task_id].update({
                "status": "completed", 
                "progress": 100,
                "message": f"✅ Completed in {total_duration}",
                "result_url": result_url,
                "completed_at": end_time,
                "duration": total_duration
            })
            log_with_time(f"✅ Task {task_id} completed after timeout check in {total_duration}: {result['filename']}")
        else:
            start_time = tasks[task_id]["started_at"]
            duration = format_duration(start_time)
            tasks[task_id].update({
                "status": "timeout",
                "progress": 89,
                "message": f"⏰ Timed out after {duration}",
                "duration": duration
            })
            log_with_time(f"⏰ Task {task_id} timed out after {duration}")

# Background task для периодической проверки
async def periodic_sync_check():
    """Background задача для периодической проверки соответствия backend ↔ ComfyUI"""
    while True:
        try:
            await asyncio.sleep(30)  # Проверяем каждые 30 секунд
            await sync_check_backend_comfyui()
        except Exception as e:
            log_with_time(f"❌ Error in periodic sync check: {e}")

@app.on_event("startup")
async def startup_event():
    """Запуск background задач при старте приложения"""
    log_with_time("🚀 Starting periodic sync check background task...")
    asyncio.create_task(periodic_sync_check())

@app.get("/")
async def root():
    return {"message": "unionlyp API with Smart Balancer, OOM Protection, Random Seeds & Sync Check (8 Servers) is running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now()}

@app.get("/servers/status")
async def get_servers_status():
    await update_server_loads()
    
    server_statuses = []
    for server_url, server_data in server_loads.items():
        server_statuses.append({
            "name": server_data["name"],
            "url": server_data["url"],
            "status": "online" if server_data["online"] else "offline",
            "gpu_id": server_data["gpu_id"],
            "queue_size": server_data["queue_size"],
            "load_score": round(server_data["load_score"], 1),
            "memory_used": server_data["vram_used"],
            "memory_total": server_data["vram_total"]
        })
    
    online_count = sum(1 for s in server_statuses if s["status"] == "online")
    log_with_time(f"📊 Smart Balancer: {online_count}/{len(COMFYUI_SERVERS)} servers online")
    
    return {"servers": server_statuses}

@app.get("/balancer/stats")
async def get_balancer_stats():
    await update_server_loads()
    return {"server_loads": server_loads, "active_tasks": len(tasks)}

@app.get("/queue/status")
async def get_queue_status():
    return {"queue": list(tasks.values())}

@app.get("/history")
async def get_history():
    return {"history": [task for task in tasks.values() if task["status"] in ["completed", "failed"]]}

@app.get("/sync/check")
async def manual_sync_check():
    """Ручной запуск проверки соответствия backend ↔ ComfyUI"""
    await sync_check_backend_comfyui()
    return {"message": "Sync check completed"}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        file_id = str(uuid.uuid4())
        file_extension = Path(file.filename).suffix
        new_filename = f"{file_id}{file_extension}"
        file_path = UPLOAD_DIR / new_filename
        
        content = await file.read()
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        
        # Store file mapping: UUID -> original name
        file_mappings[new_filename] = file.filename
        
        # Copy to ALL ComfyUI input directories
        copy_file_to_all_comfyui_dirs(file_path, file.filename)
        
        log_with_time(f"📁 Uploaded {file.filename} ({len(content)} bytes) -> {new_filename}")
        
        return {
            "filename": new_filename,
            "original_name": file.filename,
            "size": len(content),
            "path": str(file_path)
        }
    except Exception as e:
        log_with_time(f"❌ Upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

@app.post("/generate")
async def generate_lipsync(request: GenerateRequest):
    try:
        task_id = str(uuid.uuid4())
        start_time = datetime.now()
        log_with_time(f"🎬 Starting unionlyp task {task_id} at {start_time.strftime('%H:%M:%S')}")
        
        # Find uploaded files
        audio_path = None
        video_path = None
        
        # Check if files exist in uploads
        for file_path in UPLOAD_DIR.glob("*"):
            if file_path.name == request.audio_file:
                audio_path = file_path
            elif file_path.name == request.video_file:
                video_path = file_path
        
        if not audio_path:
            log_with_time(f"❌ Audio file not found: {request.audio_file}")
            raise HTTPException(status_code=404, detail=f"Audio file not found: {request.audio_file}")
        if not video_path:
            log_with_time(f"❌ Video file not found: {request.video_file}")
            raise HTTPException(status_code=404, detail=f"Video file not found: {request.video_file}")
        
        # Get original filenames from file mappings
        audio_original = file_mappings.get(request.audio_file, request.audio_file)
        video_original = file_mappings.get(request.video_file, request.video_file)
        
        log_with_time(f"📋 Files for ComfyUI: {audio_original} + {video_original}")
        log_with_time(f"🔗 Mapped from: {request.audio_file} -> {audio_original}")
        log_with_time(f"🔗 Mapped from: {request.video_file} -> {video_original}")
        
        # Ensure files exist in ALL ComfyUI input directories
        copy_file_to_all_comfyui_dirs(audio_path, audio_original)
        copy_file_to_all_comfyui_dirs(video_path, video_original)
        
        # Find best available server using smart balancer
        server_url = await find_best_server()
        
        if not server_url:
            raise HTTPException(status_code=503, detail="No ComfyUI servers available")
        
        log_with_time(f"🎯 Using best server: {server_url} (smart balancer)")
        
        # Create workflow with random seed!
        workflow = get_workflow_json(audio_original, video_original)
        workflow_seed = workflow["54"]["inputs"]["seed"]
        log_with_time(f"📝 Created workflow with files: {audio_original}, {video_original} (seed: {workflow_seed})")
        
        # Submit to ComfyUI
        prompt_id = await submit_workflow_to_comfyui(server_url, workflow, task_id)
        
        if not prompt_id:
            raise HTTPException(status_code=500, detail="Failed to submit workflow")
        
        log_with_time(f"✅ Workflow submitted successfully, prompt_id: {prompt_id}")
        
        # Store task info with timing (московское время) и seed
        tasks[task_id] = {
            "task_id": task_id,
            "status": "started",
            "progress": 0,
            "message": f"🚀 Started at {start_time.strftime('%H:%M:%S')} MSK",
            "result_url": None,
            "created_at": start_time,
            "started_at": start_time,
            "prompt_id": prompt_id,
            "server_url": server_url,
            "duration": "0s",
            "audio_file": audio_original,
            "video_file": video_original,
            "seed": workflow_seed  # ✨ Сохраняем использованный seed
        }
        
        # Start monitoring in background
        asyncio.create_task(monitor_task(task_id, server_url, prompt_id))
        
        return {"task_id": task_id, "status": "started", "seed": workflow_seed}
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Failed to submit workflow: {e}"
        log_with_time(f"❌ Task {task_id} failed: {error_msg}")
        if task_id in tasks:
            tasks[task_id].update({"status": "failed", "message": f"❌ Error: {error_msg}"})
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/task/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks[task_id].copy()
    # Format datetime fields for JSON serialization
    for field in ["created_at", "started_at", "completed_at"]:
        if field in task and isinstance(task[field], datetime):
            task[field] = task[field].isoformat()
    
    return task

@app.get("/logs")
async def get_logs():
    return {"message": "Check backend.log file"}

@app.delete("/task/{task_id}")
async def delete_task(task_id: str):
    if task_id in tasks:
        del tasks[task_id]
        return {"message": f"Task {task_id} deleted"}
    raise HTTPException(status_code=404, detail="Task not found")

if __name__ == "__main__":
    log_with_time("🚀 Starting unionlyp API with Smart Balancer, OOM Protection, Random Seeds, Sync Check & MSK Time...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
