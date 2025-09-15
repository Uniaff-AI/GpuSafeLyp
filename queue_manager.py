#!/usr/bin/env python3
"""
Queue Manager для ComfyUI - управляет очередью задач обработки видео
"""
import asyncio
import json
import time
import uuid
import threading
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import logging
from pathlib import Path
import requests
import websocket
import queue
from gpu_monitor import GPUMonitor

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class VideoTask:
    task_id: str
    input_video_path: str
    output_video_path: str
    workflow_data: dict
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_message: Optional[str] = None
    comfyui_prompt_id: Optional[str] = None
    priority: int = 0  # Чем больше число, тем выше приоритет

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()

class ComfyUIQueueManager:
    def __init__(self, comfyui_url: str = "http://127.0.0.1:8188", 
                 max_concurrent_tasks: Optional[int] = None,
                 memory_per_video_gb: float = 6.0):
        self.comfyui_url = comfyui_url
        self.gpu_monitor = GPUMonitor(memory_per_video_gb=memory_per_video_gb)
        self.max_concurrent_tasks = max_concurrent_tasks
        
        # Хранилище задач
        self.tasks: Dict[str, VideoTask] = {}
        self.pending_queue = queue.PriorityQueue()
        self.running_tasks: Dict[str, VideoTask] = {}
        
        # Синхронизация
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        
        # Логирование
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Коллбэки
        self.task_callbacks: Dict[str, List[Callable]] = {}
        
        # Запуск фонового процесса
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        
        self.logger.info("ComfyUIQueueManager инициализирован")
    
    def add_task(self, input_video: str, output_video: str, 
                 workflow_data: dict, priority: int = 0) -> str:
        """Добавить новую задачу в очередь"""
        task_id = str(uuid.uuid4())
        
        task = VideoTask(
            task_id=task_id,
            input_video_path=input_video,
            output_video_path=output_video,
            workflow_data=workflow_data,
            priority=priority
        )
        
        with self.lock:
            self.tasks[task_id] = task
            # Приоритетная очередь: (-priority, created_at, task_id)
            self.pending_queue.put((-priority, task.created_at, task_id))
        
        self.logger.info(f"Добавлена задача {task_id}: {input_video} -> {output_video}")
        return task_id
    
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Получить статус задачи"""
        with self.lock:
            task = self.tasks.get(task_id)
            if task:
                return asdict(task)
        return None
    
    def get_queue_status(self) -> Dict:
        """Получить общий статус очереди"""
        with self.lock:
            pending_count = self.pending_queue.qsize()
            running_count = len(self.running_tasks)
            
            completed_count = sum(1 for t in self.tasks.values() 
                                if t.status == TaskStatus.COMPLETED)
            failed_count = sum(1 for t in self.tasks.values() 
                             if t.status == TaskStatus.FAILED)
        
        slots_info = self.gpu_monitor.calculate_available_slots()
        
        return {
            'pending': pending_count,
            'running': running_count,
            'completed': completed_count,
            'failed': failed_count,
            'total_tasks': len(self.tasks),
            'available_slots': slots_info['available_slots'],
            'max_concurrent': self.max_concurrent_tasks or slots_info['available_slots'],
            'gpu_info': slots_info
        }
    
    def cancel_task(self, task_id: str) -> bool:
        """Отменить задачу"""
        with self.lock:
            task = self.tasks.get(task_id)
            if task and task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                self.logger.info(f"Задача {task_id} отменена")
                return True
        return False
    
    def _get_max_concurrent(self) -> int:
        """Определить максимальное количество одновременных задач"""
        if self.max_concurrent_tasks:
            return self.max_concurrent_tasks
        
        slots_info = self.gpu_monitor.calculate_available_slots()
        return max(1, slots_info['available_slots'])
    
    def _scheduler_loop(self):
        """Основной цикл планировщика задач"""
        self.logger.info("Запущен планировщик задач")
        
        while not self.stop_event.wait(5.0):  # Проверка каждые 5 секунд
            try:
                self._process_queue()
                self._check_running_tasks()
            except Exception as e:
                self.logger.error(f"Ошибка в планировщике: {e}")
    
    def _process_queue(self):
        """Обработать очередь и запустить новые задачи"""
        max_concurrent = self._get_max_concurrent()
        
        with self.lock:
            current_running = len(self.running_tasks)
            
            while (current_running < max_concurrent and 
                   not self.pending_queue.empty()):
                
                try:
                    _, _, task_id = self.pending_queue.get_nowait()
                    task = self.tasks.get(task_id)
                    
                    if not task or task.status != TaskStatus.PENDING:
                        continue
                    
                    # Запускаем задачу
                    if self._start_task(task):
                        self.running_tasks[task_id] = task
                        current_running += 1
                        self.logger.info(f"Запущена задача {task_id} ({current_running}/{max_concurrent})")
                    
                except queue.Empty:
                    break
    
    def _start_task(self, task: VideoTask) -> bool:
        """Запустить задачу в ComfyUI"""
        try:
            # Обновляем workflow данными задачи
            workflow = task.workflow_data.copy()
            
            # Отправляем в ComfyUI API
            response = requests.post(
                f"{self.comfyui_url}/prompt",
                json={"prompt": workflow, "client_id": task.task_id},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                task.comfyui_prompt_id = result.get('prompt_id')
                task.status = TaskStatus.RUNNING
                task.started_at = time.time()
                return True
            else:
                self.logger.error(f"Ошибка запуска задачи {task.task_id}: {response.text}")
                task.status = TaskStatus.FAILED
                task.error_message = f"HTTP {response.status_code}: {response.text}"
                return False
                
        except Exception as e:
            self.logger.error(f"Исключение при запуске задачи {task.task_id}: {e}")
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            return False
    
    def _check_running_tasks(self):
        """Проверить статус выполняющихся задач"""
        completed_tasks = []
        
        with self.lock:
            for task_id, task in self.running_tasks.items():
                try:
                    # Проверяем статус через ComfyUI API
                    if self._is_task_completed(task):
                        task.status = TaskStatus.COMPLETED
                        task.completed_at = time.time()
                        completed_tasks.append(task_id)
                        self.logger.info(f"Задача {task_id} завершена")
                        
                except Exception as e:
                    self.logger.error(f"Ошибка проверки задачи {task_id}: {e}")
            
            # Удаляем завершенные задачи из running
            for task_id in completed_tasks:
                self.running_tasks.pop(task_id, None)
    
    def _is_task_completed(self, task: VideoTask) -> bool:
        """Проверить, завершена ли задача"""
        if not task.comfyui_prompt_id:
            return False
        
        try:
            response = requests.get(
                f"{self.comfyui_url}/history/{task.comfyui_prompt_id}",
                timeout=10
            )
            
            if response.status_code == 200:
                history = response.json()
                if task.comfyui_prompt_id in history:
                    # Если задача есть в истории, значит она завершена
                    return True
        except:
            pass
        
        return False
    
    def stop(self):
        """Остановить менеджер очереди"""
        self.logger.info("Остановка менеджера очереди...")
        self.stop_event.set()
        self.scheduler_thread.join(timeout=10)

if __name__ == '__main__':
    # Тест системы
    manager = ComfyUIQueueManager()
    
    print("=== Тест Queue Manager ===")
    
    # Добавляем тестовые задачи
    for i in range(3):
        workflow = {
            "3": {
                "inputs": {
                    "seed": 42 + i,
                    "steps": 20,
                    "cfg": 8.0,
                },
                "class_type": "KSampler"
            }
        }
        
        task_id = manager.add_task(
            input_video=f"test_input_{i}.mp4",
            output_video=f"test_output_{i}.mp4", 
            workflow_data=workflow,
            priority=i
        )
        print(f"Добавлена задача {i}: {task_id}")
    
    # Показываем статус
    import time
    for _ in range(5):
        status = manager.get_queue_status()
        print(f"\nСтатус очереди: {json.dumps(status, indent=2)}")
        time.sleep(2)
    
    manager.stop()
