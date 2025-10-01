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
import queue
import threading

import aiofiles
import aiohttp
import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from media_utils import prepare_media_files

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="LipSync API with Smart Balancer & Queue (8 Servers)", version="1.1.0")

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
    {"name": "GPU Server 4", "url": "localhost:8191", "gpu_id": 3},
    {"name": "GPU Server 5", "url": "localhost:8192", "gpu_id": 4},
    {"name": "GPU Server 6", "url": "localhost:8193", "gpu_id": 5},
    {"name": "GPU Server 7", "url": "localhost:8194", "gpu_id": 6},
    {"name": "GPU Server 8", "url": "localhost:8195", "gpu_id": 7}
]

UPLOAD_DIR = Path("uploads")
# Multiple ComfyUI input directories
COMFYUI_INPUT_DIRS = [
    Path("/home/epycmax/ComfyUI-Production/input"),
    Path("/home/epycmax/ComfyUI/input"),
    Path("/home/epycmax/ComfyUI/ComfyUI_main/input"),
    Path("/home/epycmax/ComfyUI_deployment/ComfyUI/input")
]

UPLOAD_DIR.mkdir(exist_ok=True)

# Task storage and server tracking with improved queue system
tasks: Dict[str, dict] = {}
server_loads: Dict[str, dict] = {}
server_queues: Dict[str, queue.Queue] = {}
active_tasks_per_server: Dict[str, int] = {}
# File mapping storage - maps UUID filenames to original names
file_mappings: Dict[str, str] = {}

# Initialize queues and counters for each server
for server in COMFYUI_SERVERS:
    server_url = server["url"]
    server_queues[server_url] = queue.Queue()
    active_tasks_per_server[server_url] = 0

class GenerateRequest(BaseModel):
    audio_file: str
    video_file: str
    lips_expression: float = 1.5
    seed: int = 1331
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
    
    if total_seconds < 60:
        return f"{total_seconds}s"
    else:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}m {seconds}s"

def copy_file_to_all_comfyui_dirs(source_path: Path, original_filename: str):
    """Копирует файл во все директории ComfyUI input"""
    for comfyui_dir in COMFYUI_INPUT_DIRS:
        if comfyui_dir.exists():
            target_path = comfyui_dir / original_filename
            try:
                shutil.copy2(source_path, target_path)
                log_with_time(f"📂 Copied {original_filename} to {comfyui_dir}")
            except Exception as e:
                log_with_time(f"⚠️  Failed to copy to {comfyui_dir}: {e}")

async def get_server_stats(server_url: str) -> dict:
    """Получает статистику сервера"""
    try:
        async with aiohttp.ClientSession() as session:
            # Get queue info
            queue_url = f"http://{server_url}/queue"
            async with session.get(queue_url, timeout=aiohttp.ClientTimeout(total=3)) as response:
                if response.status == 200:
                    queue_data = await response.json()
                    queue_size = len(queue_data.get("queue_running", [])) + len(queue_data.get("queue_pending", []))
                else:
                    queue_size = -1
                    
            # Get system stats
            system_url = f"http://{server_url}/system_stats"
            vram_used = 0
            vram_total = 25 * 1024 * 1024 * 1024  # Default 25GB for RTX 3090
            
            try:
                async with session.get(system_url, timeout=aiohttp.ClientTimeout(total=2)) as response:
                    if response.status == 200:
                        system_data = await response.json()
                        if "devices" in system_data:
                            for device in system_data["devices"]:
                                if device.get("type") == "cuda":
                                    vram_used = device.get("vram_total", vram_total) - device.get("vram_free", device.get("vram_total", vram_total))
                                    vram_total = device.get("vram_total", vram_total)
                                    break
            except:
                pass  # Use defaults if system stats unavailable
            
            # Add server's internal queue size
            internal_queue_size = server_queues[server_url].qsize()
            active_tasks = active_tasks_per_server[server_url]
            total_load = queue_size + internal_queue_size + active_tasks
            
            return {
                "online": True,
                "queue_size": total_load,
                "vram_used": vram_used,
                "vram_total": vram_total,
                "load_score": total_load * 10 + (vram_used / max(vram_total, 1)) * 5
            }
    except Exception as e:
        log_with_time(f"⚠️  Server {server_url} stats error: {e}")
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

async def queue_task_to_server(server_url: str, task_data: dict):
    """Добавляет задачу в очередь сервера"""
    try:
        server_queues[server_url].put(task_data, timeout=1)
        log_with_time(f"📋 Task {task_data['task_id'][:8]} queued to server {server_url}")
    except queue.Full:
        log_with_time(f"❌ Server {server_url} queue is full!")
        raise HTTPException(status_code=503, detail=f"Server {server_url} queue is full")

def get_workflow_json(audio_filename: str, video_filename: str, lips_expression: float = 1.5, seed: int = 1331, save_output: bool = True) -> dict:
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
            async with session.post(f"http://{server_url}/prompt", 
                                  json=prompt_data,
                                  timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("prompt_id")
                else:
                    log_with_time(f"❌ ComfyUI submission failed: {response.status}")
                    return None
    except Exception as e:
        log_with_time(f"❌ ComfyUI submission error: {e}")
        return None

async def monitor_task_progress(server_url: str, task_id: str, prompt_id: str):
    """Мониторит прогресс задачи на сервере ComfyUI"""
    log_with_time(f"👀 Monitoring task {task_id[:8]} on server {server_url}")
    
    start_time = time.time()
    
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                # Check queue status
                async with session.get(f"http://{server_url}/queue") as response:
                    if response.status == 200:
                        queue_data = await response.json()
                        
                        # Check if our task is still in queue or being processed
                        running = queue_data.get("queue_running", [])
                        pending = queue_data.get("queue_pending", [])
                        
                        task_found = False
                        for item in running + pending:
                            if item[1] == prompt_id:
                                task_found = True
                                # Update task status to processing
                                if task_id in tasks:
                                    tasks[task_id]["status"] = "processing"
                                    elapsed = time.time() - start_time
                                    # Estimate 15-20 seconds per video second, assume ~30s video = ~7 minutes
                                    estimated_total = 540  # 9 minutes average
                                    tasks[task_id]["progress"] = min(10 + (elapsed / estimated_total) * 80, 95)
                                break
                        
                        if not task_found:
                            # Task completed - check for results
                            result = await check_task_completion(server_url, task_id, prompt_id)
                            return result
                
        except Exception as e:
            log_with_time(f"❌ Monitor error for task {task_id[:8]}: {e}")
        
        await asyncio.sleep(5)  # Check every 5 seconds
    

async def check_task_completion(server_url: str, task_id: str, prompt_id: str):
    """Проверяет завершение задачи используя ComfyUI History API"""
    try:
        async with aiohttp.ClientSession() as session:
            # Get task history from ComfyUI
            async with session.get(f"http://{server_url}/history/{prompt_id}",
                                 timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    history_data = await response.json()
                    
                    if prompt_id in history_data:
                        task_data = history_data[prompt_id]
                        status = task_data.get("status", {})
                        
                        # Check if task completed successfully
                        if status.get("status_str") == "success" and status.get("completed"):
                            outputs = task_data.get("outputs", {})
                            
                            # Find the output video file
                            result_file = None
                            for node_id, node_outputs in outputs.items():
                                if "gifs" in node_outputs:
                                    for gif_info in node_outputs["gifs"]:
                                        if gif_info.get("format") == "video/h264-mp4":
                                            result_file = Path(gif_info["fullpath"])
                                            break
                                if result_file:
                                    break
                            
                            if result_file and result_file.exists():
                                log_with_time(f"✅ Task {task_id[:8]} completed successfully: {result_file}")
                                
                                # Update task status
                                if task_id in tasks:
                                    tasks[task_id]["status"] = "completed"
                                    tasks[task_id]["progress"] = 100
                                    tasks[task_id]["result_url"] = f"http://89.208.11.177:8000/download/{result_file.name}"
                                    tasks[task_id]["message"] = f"✅ Completed successfully!"
                                    
                                    end_time = datetime.now()
                                    start_time = datetime.fromisoformat(tasks[task_id]["started_at"].replace('Z', '+00:00'))
                                    duration = format_duration(start_time, end_time)
                                    tasks[task_id]["completed_at"] = end_time.isoformat() + "Z"
                                    tasks[task_id]["duration"] = duration
                                
                                return {"success": True, "result_file": str(result_file)}
                            else:
                                log_with_time(f"❌ Task {task_id[:8]} completed but no result file found")
                                
                        elif status.get("status_str") == "error":
                            log_with_time(f"❌ Task {task_id[:8]} failed with error in ComfyUI")
                            if task_id in tasks:
                                tasks[task_id]["status"] = "failed"
                                tasks[task_id]["message"] = "❌ ComfyUI processing error"
                            return {"success": False, "error": "ComfyUI processing error"}
                    
                    # Task not found in history - still running or lost
                    return {"success": False, "error": "Task not found in history"}
                else:
                    log_with_time(f"❌ Failed to get history from {server_url}: {response.status}")
                    return {"success": False, "error": f"History API error: {response.status}"}
                    
    except Exception as e:
        log_with_time(f"❌ Error checking task completion: {e}")
        return {"success": False, "error": str(e)}
    
    # Fallback to old file search method if API fails
    log_with_time(f"📁 Falling back to file search for task {task_id[:8]}")
    try:
        output_dirs = [
            Path("/home/epycmax/ComfyUI-Production/output"),
            Path("/home/epycmax/ComfyUI/output"), 
            Path("/home/epycmax/ComfyUI/ComfyUI_main/output")
        ]
        
        result_file = None
        for output_dir in output_dirs:
            if output_dir.exists():
                pattern = "lipsync_result_*.mp4"
                files = list(output_dir.glob(pattern))
                
                if files:
                    # Get files created after task started
                    task_start_time = datetime.fromisoformat(tasks[task_id]["started_at"].replace("Z", "+00:00")).timestamp() if task_id in tasks else 0
                    recent_files = [f for f in files if f.stat().st_mtime > task_start_time - 5]
                    if recent_files:
                        result_file = max(recent_files, key=lambda x: x.stat().st_mtime)
                        break
        
        if result_file:
            log_with_time(f"✅ Task {task_id[:8]} found result via file search: {result_file}")
            
            if task_id in tasks:
                tasks[task_id]["status"] = "completed"
                tasks[task_id]["progress"] = 100
                tasks[task_id]["result_url"] = f"http://89.208.11.177:8000/download/{result_file.name}"
                tasks[task_id]["message"] = f"✅ Completed successfully!"
                
                end_time = datetime.now()
                start_time = datetime.fromisoformat(tasks[task_id]["started_at"].replace('Z', '+00:00'))
                duration = format_duration(start_time, end_time)
                tasks[task_id]["completed_at"] = end_time.isoformat() + "Z"
                tasks[task_id]["duration"] = duration
            
            return {"success": True, "result_file": str(result_file)}
        else:
            log_with_time(f"❌ Task {task_id[:8]} failed - no result file found")
            
            if task_id in tasks:
                tasks[task_id]["status"] = "failed"
                tasks[task_id]["message"] = "❌ No result file generated"
            
            return {"success": False, "error": "No result file found"}
            
    except Exception as e:
        log_with_time(f"❌ Fallback file search failed: {e}")
        if task_id in tasks:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["message"] = "❌ Error during result checking"
        return {"success": False, "error": str(e)}
async def process_task_on_server(server_url: str, task_data: dict):
    """Обрабатывает задачу на конкретном сервере"""
    task_id = task_data["task_id"]
    
    try:
        log_with_time(f"🎬 Processing task {task_id[:8]} on server {server_url}")
        
        # Submit workflow to ComfyUI
        prompt_id = await submit_workflow_to_comfyui(server_url, task_data["workflow"], task_id)
        
        if not prompt_id:
            if task_id in tasks:
                tasks[task_id]["status"] = "failed"
                tasks[task_id]["message"] = "❌ Failed to submit to ComfyUI"
            return
        
        # Monitor progress
        result = await monitor_task_progress(server_url, task_id, prompt_id)
        
        log_with_time(f"📊 Task {task_id[:8]} result: {result.get('success', False)}")
        
    except Exception as e:
        log_with_time(f"❌ Task processing error {task_id[:8]}: {e}")
        if task_id in tasks:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["message"] = f"❌ Processing error: {str(e)}"

# Start worker threads for all servers

def server_worker(server_url: str):
    """Worker thread для обработки задач на конкретном сервере"""
    log_with_time(f"🚀 Started worker for server {server_url}")
    
    while True:
        try:
            # Get task from queue (blocking)
            task_data = server_queues[server_url].get(timeout=10)
            
            if task_data is None:  # Shutdown signal
                break
            
            # Increment active tasks counter
            active_tasks_per_server[server_url] += 1
            
            # Process the task
            asyncio.run(process_task_on_server(server_url, task_data))
            
        except queue.Empty:
            continue  # No tasks, keep waiting
        except Exception as e:
            log_with_time(f"❌ Worker error on server {server_url}: {e}")
        finally:
            # Decrement active tasks counter
            if active_tasks_per_server[server_url] > 0:
                active_tasks_per_server[server_url] -= 1

def start_server_workers():
    for server in COMFYUI_SERVERS:
        server_url = server["url"]
        worker_thread = threading.Thread(
            target=server_worker, 
            args=(server_url,), 
            daemon=True,
            name=f"worker-{server_url}"
        )
        worker_thread.start()
        log_with_time(f"🔄 Started worker thread for {server_url}")

# Routes
@app.on_event("startup")
async def startup_event():
    log_with_time("🚀 Starting LipSync API with Smart Balancer, Queue & Multi-Directory Support...")
    start_server_workers()

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
    
    queue_stats = {}
    for server_url, q in server_queues.items():
        queue_stats[server_url] = {
            "queued": q.qsize(),
            "active": active_tasks_per_server[server_url]
        }
    
    return {
        "server_loads": server_loads, 
        "active_tasks": len(tasks),
        "queue_stats": queue_stats
    }

@app.get("/queue")
async def get_queue():
    return {"queue": list(tasks.values())}

@app.get("/queue/status")
async def get_queue_status():
    return {"queue": list(tasks.values())}

@app.get("/history")
async def get_history():
    return {"history": [task for task in tasks.values() if task["status"] in ["completed", "failed"]]}

@app.post("/queue/clear")
async def clear_queue():
    global tasks
    old_count = len(tasks)
    tasks.clear()
    return {"message": f"Cleared {old_count} tasks from queue"}

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
        log_with_time(f"🎬 Starting LipSync task {task_id[:8]} at {start_time.strftime('%H:%M:%S')}")
        
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
        
        # Get original filenames
        audio_original = file_mappings.get(request.audio_file, request.audio_file)
        video_original = file_mappings.get(request.video_file, request.video_file)
        
        # Prepare media files
        log_with_time(f"🎬 Preparing media files: checking video/audio durations...")
        try:
            prepared_video_path, prepared_audio_path = prepare_media_files(str(video_path), str(audio_path))
            
            # If video was trimmed, update path and copy to ComfyUI directories
            if prepared_video_path != str(video_path):
                log_with_time(f"✂️ Video trimmed to match audio duration")
                trimmed_video_name = f"trimmed_{video_original}"
                copy_file_to_all_comfyui_dirs(Path(prepared_video_path), trimmed_video_name)
                video_original = trimmed_video_name
            
            if prepared_audio_path != str(audio_path):
                log_with_time(f"🔧 Audio processed")
                processed_audio_name = f"processed_{audio_original}"
                copy_file_to_all_comfyui_dirs(Path(prepared_audio_path), processed_audio_name)
                audio_original = processed_audio_name
                
        except Exception as e:
            log_with_time(f"⚠️  Media preparation failed: {e}, using original files")
        
        # Ensure files exist in ALL ComfyUI input directories
        copy_file_to_all_comfyui_dirs(audio_path, audio_original)
        copy_file_to_all_comfyui_dirs(video_path, video_original)
        
        # Find best available server using smart balancer
        server_url = await find_best_server()
        
        if not server_url:
            raise HTTPException(status_code=503, detail="No ComfyUI servers available")
        
        log_with_time(f"🎯 Using best server: {server_url} (smart balancer)")
        
        # Create workflow
        workflow = get_workflow_json(audio_original, video_original, request.lips_expression, request.seed, request.save_output)
        log_with_time(f"📝 Created workflow with files: {audio_original}, {video_original}")
        
        # Store task info
        tasks[task_id] = {
            "task_id": task_id,
            "status": "started",
            "progress": 0,
            "message": f"🚀 Queued on server {server_url}",
            "result_url": None,
            "started_at": start_time.isoformat() + "Z",
            "completed_at": None,
            "duration": None,
            "timing": f"Started at {start_time.strftime('%H:%M:%S')}",
            "server_url": server_url,
            "audio_file": request.audio_file,
            "video_file": request.video_file,
            "lips_expression": request.lips_expression,
            "seed": request.seed
        }
        
        # Queue task to best server
        task_data = {
            "task_id": task_id,
            "workflow": workflow,
            "server_url": server_url,
            "audio_original": audio_original,
            "video_original": video_original
        }
        
        await queue_task_to_server(server_url, task_data)
        
        log_with_time(f"✅ Task {task_id[:8]} queued successfully to {server_url}")
        
        return {
            "task_id": task_id,
            "status": "queued",
            "message": f"Task queued on server {server_url}",
            "server_url": server_url,
            "estimated_time": "Processing will start shortly..."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Failed to queue task: {e}"
        log_with_time(f"❌ {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/task/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return tasks[task_id]

@app.get("/download/{filename}")
async def download_result(filename: str):
    """Download result file"""
    output_dirs = [
        Path("/home/epycmax/ComfyUI-Production/output"),
        Path("/home/epycmax/ComfyUI/output"),
        Path("/home/epycmax/ComfyUI/ComfyUI_main/output")
    ]
    
    for output_dir in output_dirs:
        file_path = output_dir / filename
        if file_path.exists():
            return FileResponse(
                path=str(file_path),
                filename=filename,
                media_type="video/mp4"
            )
    
    raise HTTPException(status_code=404, detail="File not found")

@app.delete("/task/{task_id}")
async def cancel_task(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks[task_id]
    if task["status"] in ["completed", "failed"]:
        raise HTTPException(status_code=400, detail="Cannot cancel completed task")
    
    # Mark as cancelled
    task["status"] = "cancelled"
    task["message"] = "❌ Task cancelled by user"
    
    log_with_time(f"🚫 Task {task_id[:8]} cancelled")
    
    return {"message": "Task cancelled", "task_id": task_id}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
