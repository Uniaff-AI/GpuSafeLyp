#!/usr/bin/env python3
"""
Простой балансировщик нагрузки для ComfyUI
Перенаправляет запросы между двумя экземплярами ComfyUI на портах 8188 и 8189
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import json
import random
import urllib.parse
import threading
import time

class ComfyUILoadBalancer(BaseHTTPRequestHandler):
    # Список экземпляров ComfyUI
    COMFYUI_INSTANCES = [
        'http://localhost:8188',
        'http://localhost:8189'
    ]
    
    def __init__(self, *args, **kwargs):
        self.current_instance = 0
        super().__init__(*args, **kwargs)
    
    def get_next_instance(self):
        """Простое round-robin распределение"""
        instance = self.COMFYUI_INSTANCES[self.current_instance]
        self.current_instance = (self.current_instance + 1) % len(self.COMFYUI_INSTANCES)
        return instance
    
    def get_best_instance(self):
        """Выбор наименее загруженного экземпляра"""
        best_instance = None
        min_queue = float('inf')
        
        for instance in self.COMFYUI_INSTANCES:
            try:
                response = requests.get(f"{instance}/queue", timeout=2)
                queue_data = response.json()
                
                running_count = len(queue_data.get('queue_running', []))
                pending_count = len(queue_data.get('queue_pending', []))
                total_queue = running_count + pending_count
                
                if total_queue < min_queue:
                    min_queue = total_queue
                    best_instance = instance
                    
            except:
                continue
                
        return best_instance or self.COMFYUI_INSTANCES[0]
    
    def proxy_request(self, target_url):
        """Проксирует запрос к целевому экземпляру"""
        try:
            # Подготавливаем заголовки
            headers = {}
            for key, value in self.headers.items():
                if key.lower() not in ['host', 'connection']:
                    headers[key] = value
            
            # Читаем тело запроса
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else None
            
            # Отправляем запрос
            if self.command == 'GET':
                response = requests.get(target_url + self.path, headers=headers, timeout=300)
            elif self.command == 'POST':
                response = requests.post(target_url + self.path, headers=headers, data=body, timeout=300)
            else:
                self.send_error(405, 'Method Not Allowed')
                return
            
            # Возвращаем ответ
            self.send_response(response.status_code)
            
            # Копируем заголовки ответа
            for key, value in response.headers.items():
                if key.lower() not in ['connection', 'transfer-encoding']:
                    self.send_header(key, value)
            self.end_headers()
            
            # Копируем тело ответа
            self.wfile.write(response.content)
            
        except Exception as e:
            self.send_error(500, f'Proxy error: {str(e)}')
    
    def do_GET(self):
        if self.path.startswith('/queue'):
            # Для просмотра очереди используем наименее загруженный экземпляр
            target = self.get_best_instance()
        else:
            # Для остальных запросов используем round-robin
            target = self.get_next_instance()
            
        print(f"GET {self.path} -> {target}")
        self.proxy_request(target)
    
    def do_POST(self):
        if self.path.startswith('/prompt'):
            # Для отправки промптов выбираем наименее загруженный экземпляр
            target = self.get_best_instance()
            print(f"POST {self.path} -> {target} (best instance)")
        else:
            # Для остальных POST запросов используем round-robin
            target = self.get_next_instance()
            print(f"POST {self.path} -> {target}")
            
        self.proxy_request(target)

def run_load_balancer(port=8190):
    """Запускает балансировщик нагрузки"""
    server = HTTPServer(('0.0.0.0', port), ComfyUILoadBalancer)
    print(f"ComfyUI Load Balancer запущен на порту {port}")
    print("Балансирует между:")
    for instance in ComfyUILoadBalancer.COMFYUI_INSTANCES:
        print(f"  - {instance}")
    print(f"Доступ: http://89.208.11.177:{port}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановка балансировщика...")
        server.shutdown()

if __name__ == '__main__':
    run_load_balancer()
