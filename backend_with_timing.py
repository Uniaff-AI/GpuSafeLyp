#!/usr/bin/env python3
import asyncio
import json
import logging
import shutil
import uuid
import time
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
from media_utils import prepare_media_files

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="LipSync API with Smart Balancer (8 Servers)", version="1.0.0")

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
# File mapping storage - maps UUID filenames to original names
file_mappings: Dict[str, str] = {}

class GenerateRequest(BaseModel):
    audio_file: str
    video_file: str
    lips_expression: float = 1.5
    seed: int = 1331
    trim_to_audio: bool = True
    save_output: bool = True

def log_with_time(message: str):
    timestamp = datetime.now().strftime("[%H:%M:%S]")
    print(f"{timestamp} {message}")
    logger.info(message)

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

def copy_file_to_all_comfyui_dirs(file_path: Path, original_name: str):
    """Копируем файл во все возможные ComfyUI input директории"""
    copied_count = 0
    for input_dir in COMFYUI_INPUT_DIRS:
        if input_dir.exists():
            try:
                target_path = input_dir / original_name
                shutil.copy2(file_path, target_path)
                log_with_time(f"📂 Copied to: {target_path}")
                copied_count += 1
            except Exception as e:
                log_with_time(f"⚠️  Failed to copy to {input_dir}: {e}")
    
    if copied_count == 0:
        log_with_time(f"⚠️  No ComfyUI input directories found!")
    else:
        log_with_time(f"✅ File copied to {copied_count} ComfyUI directories")

async def get_server_stats(server_url: str) -> Optional[dict]:
    """Получаем статистику сервера (очередь, система)"""
    try:
        async with aiohttp.ClientSession() as session:
            # Проверяем очередь
            async with session.get(f"http://{server_url}/queue", timeout=aiohttp.ClientTimeout(total=2)) as response:
                if response.status == 200:
                    queue_data = await response.json()
                    queue_size = len(queue_data.get('queue_running', [])) + len(queue_data.get('queue_pending', []))
                else:
                    queue_size = -1
            
            # Проверяем системные ресурсы
            async with session.get(f"http://{server_url}/system_stats", timeout=aiohttp.ClientTimeout(total=2)) as response:
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
        return None
    
    # Выбираем сервер с наименьшей нагрузкой
    best_server = min(online_servers.items(), key=lambda x: x[1]["load_score"])
    
    log_with_time(f"🎯 Selected server {best_server[0]} (load: {best_server[1]['load_score']:.1f}, queue: {best_server[1]['queue_size']})")
    
    return best_server[0]

def get_workflow_json(audio_filename: str, video_filename: str, lips_expression: float = 1.5, seed: int = 1331, trim_to_audio: bool = True, save_output: bool = True) -> dict:
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
                "seed": seed,
                "lips_expression": lips_expression,
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
                "trim_to_audio": trim_to_audio,
                "pingpong": False,
                "save_output": save_output
            },
            "class_type": "VHS_VideoCombine",
            "_meta": {"title": "Save Video"}
        }
    }

async def submit_workflow_to_comfyui(server_url: str, workflow: dict, client_id: str) -> Optional[str]:
    try:
        prompt_data = {"prompt": workflow, "client_id": client_id}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"http://{server_url}/prompt", json=prompt_data) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("prompt_id")
                else:
                    error_text = await response.text()
                    log_with_time(f"❌ ComfyUI error {response.status}: {error_text}")
                    return None
    except Exception as e:
        log_with_time(f"❌ Submit error: {e}")
        return None

async def check_comfyui_result(server_url: str, prompt_id: str) -> Optional[dict]:
    """Проверяем результат в истории ComfyUI с обработкой ошибок"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://{server_url}/history/{prompt_id}") as response:
                if response.status == 200:
                    history = await response.json()
                    if prompt_id in history:
                        task_data = history[prompt_id]
                        status_data = task_data.get("status", {})
                        
                        # Проверяем на ошибки
                        if status_data.get("status_str") == "error":
                            messages = status_data.get("messages", [])
                            error_message = "Unknown error"
                            for msg in messages:
                                if msg[0] == "execution_error":
                                    error_info = msg[1]
                                    error_message = error_info.get("exception_message", "Execution error")
                                    break
                            
                            return {
                                "completed": False,
                                "error": True,
                                "error_message": error_message,
                                "server_url": server_url
                            }
                        
                        # Проверяем на успешное завершение
                        if status_data.get("completed"):
                            outputs = task_data.get("outputs", {})
                            if "41" in outputs and "gifs" in outputs["41"]:
                                video_info = outputs["41"]["gifs"][0]
                                return {
                                    "completed": True,
                                    "error": False,
                                    "filename": video_info["filename"],
                                    "server_url": server_url
                                }
                        
                return {"completed": False, "error": False}
    except Exception as e:
        log_with_time(f"❌ Check result error: {e}")
        return None

async def monitor_task(task_id: str, server_url: str, prompt_id: str):
    """Мониторим выполнение задачи"""
    max_wait_time = 3600  # 1 час  # 10 минут
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
            
        # ============ НОВАЯ ЛОГИКА ОБРАБОТКИ ОШИБОК ============
        if result.get("error", False):
            # Задача завершена с ошибкой!
            end_time = datetime.now()
            start_time = tasks[task_id]["started_at"]
            total_duration = format_duration(start_time, end_time)
            
            tasks[task_id].update({
                "status": "failed",
                "progress": 0,
                "message": f"❌ Error: {result["error_message"]}",
                "result_url": None,
                "completed_at": end_time,
                "duration": total_duration,
                "error": result["error_message"]
            })
            log_with_time(f"❌ Task {task_id} failed: {result["error_message"]}")
            break
        # ====================================================
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

@app.get("/")
async def root():
    return {"message": "🎬 LipSync API with Smart Balancer (8 Servers) is running"}

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
            "current_load": server_data["queue_size"],
            "max_load": 10,
            "memory_usage": round((server_data["vram_used"] / max(server_data["vram_total"], 1)) * 100, 1) if server_data["vram_total"] > 0 else 0,
            "last_health_check": None,
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
        log_with_time(f"🎬 Starting LipSync task {task_id} at {start_time.strftime('%H:%M:%S')}")
        
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
            raise HTTPException(status_code=404, detail=f"Audio file not found: {request.audio_file}")
        if not video_path:
            raise HTTPException(status_code=404, detail=f"Video file not found: {request.video_file}")
        
        # 🎬 АВТОМАТИЧЕСКАЯ ОБРЕЗКА ВИДЕО ПО ДЛИНЕ АУДИО
        log_with_time(f"🎬 Preparing media files: checking video/audio durations...")
        try:
            prepared_video_path, prepared_audio_path = prepare_media_files(str(video_path), str(audio_path))
            
            # Если видео было обрезано, обновляем путь и копируем в ComfyUI директории
            if prepared_video_path != str(video_path):
                log_with_time(f"✂️ Video trimmed to match audio duration")
                # Создаем новое имя для обрезанного видео
                trimmed_name = f"trimmed_{video_original}"
                # Копируем обрезанное видео в ComfyUI директории
                copy_file_to_all_comfyui_dirs(Path(prepared_video_path), trimmed_name)
                video_original = trimmed_name
                log_with_time(f"📁 Using trimmed video: {video_original}")
            else:
                log_with_time(f"✅ Video duration OK, no trimming needed")
        except Exception as e:
            log_with_time(f"⚠️ Media preparation failed, using original files: {e}")
        
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
        
        # Create workflow
        workflow = get_workflow_json(audio_original, video_original, request.lips_expression, request.seed, request.trim_to_audio, request.save_output)
        log_with_time(f"📝 Created workflow with files: {audio_original}, {video_original}")
        
        # Submit to ComfyUI
        prompt_id = await submit_workflow_to_comfyui(server_url, workflow, task_id)
        
        if not prompt_id:
            raise HTTPException(status_code=500, detail="Failed to submit workflow")
        
        log_with_time(f"✅ Workflow submitted successfully, prompt_id: {prompt_id}")
        
        # Store task info with timing
        tasks[task_id] = {
            "task_id": task_id,
            "status": "started",
            "progress": 0,
            "message": f"🚀 Started at {start_time.strftime('%H:%M:%S')}",
            "result_url": None,
            "created_at": start_time,
            "started_at": start_time,
            "prompt_id": prompt_id,
            "server_url": server_url,
            "duration": "0s",
            "audio_file": audio_original,
            "video_file": video_original
        }
        
        # Start monitoring in background
        asyncio.create_task(monitor_task(task_id, server_url, prompt_id))
        
        return {"task_id": task_id, "status": "started"}
        
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
    log_with_time("🚀 Starting LipSync API with Smart Balancer, Timing & Multi-Directory Support...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
