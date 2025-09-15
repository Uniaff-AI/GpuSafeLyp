#!/usr/bin/env python3
"""
GPU Memory Monitor для определения доступных слотов обработки
"""
import subprocess
import json
import psutil
import time
import logging
from typing import Dict, List, Tuple

class GPUMonitor:
    def __init__(self, memory_per_video_gb: float = 8.0, safety_margin: float = 0.8):
        """
        Args:
            memory_per_video_gb: Примерное потребление памяти на одно видео (в GB)
            safety_margin: Коэффициент безопасности (0.8 = использовать только 80% доступной памяти)
        """
        self.memory_per_video = memory_per_video_gb * 1024  # Convert to MB
        self.safety_margin = safety_margin
        self.logger = logging.getLogger(__name__)
    
    def get_gpu_info(self) -> Dict:
        """Получить информацию о GPU памяти"""
        try:
            result = subprocess.run([
                'nvidia-smi', '--query-gpu=memory.total,memory.used,memory.free',
                '--format=csv,noheader,nounits'
            ], capture_output=True, text=True, check=True)
            
            lines = result.stdout.strip().split('\n')
            gpus = []
            
            for i, line in enumerate(lines):
                total, used, free = map(int, line.split(', '))
                gpus.append({
                    'gpu_id': i,
                    'total_mb': total,
                    'used_mb': used,
                    'free_mb': free,
                    'utilization_percent': (used / total) * 100
                })
            
            return {
                'gpus': gpus,
                'timestamp': time.time()
            }
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Ошибка получения GPU info: {e}")
            return {'gpus': [], 'timestamp': time.time()}
    
    def calculate_available_slots(self) -> Dict:
        """Вычислить количество доступных слотов для новых видео"""
        gpu_info = self.get_gpu_info()
        
        if not gpu_info['gpus']:
            return {'available_slots': 0, 'details': 'GPU не найдены'}
        
        total_slots = 0
        gpu_details = []
        
        for gpu in gpu_info['gpus']:
            # Доступная память с учетом коэффициента безопасности
            available_memory = gpu['free_mb'] * self.safety_margin
            
            # Количество слотов для этой GPU
            slots_for_gpu = int(available_memory // self.memory_per_video)
            total_slots += slots_for_gpu
            
            gpu_details.append({
                'gpu_id': gpu['gpu_id'],
                'available_memory_mb': available_memory,
                'slots': slots_for_gpu,
                'used_percent': gpu['utilization_percent']
            })
        
        return {
            'available_slots': total_slots,
            'memory_per_video_mb': self.memory_per_video,
            'safety_margin': self.safety_margin,
            'gpu_details': gpu_details,
            'timestamp': gpu_info['timestamp']
        }
    
    def get_comfyui_processes(self) -> List[Dict]:
        """Получить информацию о процессах ComfyUI"""
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info']):
            try:
                if 'python' in proc.info['name'].lower() and proc.info['cmdline']:
                    cmdline = ' '.join(proc.info['cmdline'])
                    if 'main.py' in cmdline or 'comfyui' in cmdline.lower():
                        processes.append({
                            'pid': proc.info['pid'],
                            'cmdline': cmdline,
                            'memory_mb': proc.info['memory_info'].rss / 1024 / 1024
                        })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return processes

if __name__ == '__main__':
    # Тест скрипта
    monitor = GPUMonitor(memory_per_video_gb=6.0)  # Меньше для тестирования
    
    print("=== GPU Memory Status ===")
    gpu_info = monitor.get_gpu_info()
    print(json.dumps(gpu_info, indent=2))
    
    print("\n=== Available Slots ===")
    slots_info = monitor.calculate_available_slots()
    print(json.dumps(slots_info, indent=2))
    
    print("\n=== ComfyUI Processes ===")
    processes = monitor.get_comfyui_processes()
    print(json.dumps(processes, indent=2))
