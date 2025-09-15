#!/usr/bin/env python3
"""
Умный балансировщик нагрузки для ComfyUI с автоматическим распределением задач по GPU
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import json
import threading
import time
import hashlib
import uuid
from urllib.parse import urlparse, parse_qs

class SmartComfyUIBalancer(BaseHTTPRequestHandler):
    # Список экземпляров ComfyUI
    COMFYUI_INSTANCES = [
        {'url': 'http://localhost:8188', 'gpu_id': 0},
        {'url': 'http://localhost:8189', 'gpu_id': 1}
    ]
    
    # Кэш сессий пользователей
    user_sessions = {}
    session_lock = threading.Lock()
    
    def get_client_session(self):
        """Получить или создать сессию для клиента"""
        client_ip = self.client_address[0]
        user_agent = self.headers.get('User-Agent', '')
        
        # Создаем уникальный ID клиента
        client_key = hashlib.md5(f"{client_ip}:{user_agent}".encode()).hexdigest()
        
        with self.session_lock:
            if client_key not in self.user_sessions:
                self.user_sessions[client_key] = {
                    'preferred_instance': None,
                    'last_activity': time.time()
                }
            else:
                self.user_sessions[client_key]['last_activity'] = time.time()
                
        return client_key
    
    def get_instance_load(self, instance):
        """Получить текущую нагрузку экземпляра"""
        try:
            response = requests.get(f"{instance['url']}/queue", timeout=2)
            queue_data = response.json()
            
            running = len(queue_data.get('queue_running', []))
            pending = len(queue_data.get('queue_pending', []))
            total_load = running * 2 + pending  # Бегущие задачи весят больше
            
            return {
                'instance': instance,
                'running': running,
                'pending': pending,
                'total_load': total_load,
                'available': True
            }
        except Exception as e:
            return {
                'instance': instance,
                'running': 999,
                'pending': 999, 
                'total_load': 9999,
                'available': False
            }
    
    def select_best_instance(self, client_session=None, force_new=False):
        """Выбрать лучший экземпляр для обработки"""
        # Получаем нагрузку всех экземпляров
        loads = [self.get_instance_load(inst) for inst in self.COMFYUI_INSTANCES]
        
        print(f"[INFO] Нагрузка GPU: {[(l['instance']['gpu_id'], l['running'], l['pending']) for l in loads]}")
        
        # Для отправки задач выбираем наименее загруженный
        if self.command == 'POST' and '/prompt' in self.path:
            available_instances = [l for l in loads if l['available']]
            if not available_instances:
                return loads[0]['instance']  # Fallback
                
            best = min(available_instances, key=lambda x: x['total_load'])
            print(f"[TASK] Отправляем задачу на GPU {best['instance']['gpu_id']} (нагрузка: {best['total_load']})")
            return best['instance']
        
        # Для остальных запросов используем round-robin или сессии
        if client_session and not force_new:
            with self.session_lock:
                session_data = self.user_sessions.get(client_session, {})
                preferred = session_data.get('preferred_instance')
                if preferred and any(inst['url'] == preferred['url'] for inst in self.COMFYUI_INSTANCES):
                    return preferred
        
        # Выбираем наименее загруженный для новой сессии
        available_instances = [l for l in loads if l['available']]
        if available_instances:
            best = min(available_instances, key=lambda x: x['total_load'])
            
            if client_session:
                with self.session_lock:
                    self.user_sessions[client_session]['preferred_instance'] = best['instance']
            
            return best['instance']
        
        return self.COMFYUI_INSTANCES[0]  # Fallback
    
    def proxy_request(self, target_instance):
        """Проксирует запрос к целевому экземпляру"""
        try:
            target_url = target_instance['url']
            
            # Подготавливаем заголовки
            headers = {}
            for key, value in self.headers.items():
                if key.lower() not in ['host', 'connection', 'content-encoding']:
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
                if key.lower() not in ['connection', 'transfer-encoding', 'content-encoding']:
                    self.send_header(key, value)
            self.end_headers()
            
            # Копируем тело ответа
            self.wfile.write(response.content)
            
        except Exception as e:
            print(f"[ERROR] Proxy error: {e}")
            self.send_error(500, f'Proxy error: {str(e)}')
    
    def do_GET(self):
        client_session = self.get_client_session()
        
        if self.path.startswith('/queue') or self.path.startswith('/history'):
            # Для мониторинга используем наименее загруженный
            target = self.select_best_instance()
        else:
            # Для UI используем сессионный экземпляр
            target = self.select_best_instance(client_session)
            
        print(f"[GET] {self.path} -> GPU {target['gpu_id']}")
        self.proxy_request(target)
    
    def do_POST(self):
        client_session = self.get_client_session()
        
        if self.path.startswith('/prompt'):
            # Для задач ВСЕГДА выбираем наименее загруженный
            target = self.select_best_instance(force_new=True)
        else:
            # Для остальных POST запросов используем сессионный
            target = self.select_best_instance(client_session)
            
        print(f"[POST] {self.path} -> GPU {target['gpu_id']}")
        self.proxy_request(target)

def cleanup_sessions():
    """Очистка старых сессий"""
    while True:
        time.sleep(300)  # каждые 5 минут
        current_time = time.time()
        
        with SmartComfyUIBalancer.session_lock:
            expired_sessions = []
            for session_id, session_data in SmartComfyUIBalancer.user_sessions.items():
                if current_time - session_data['last_activity'] > 1800:  # 30 минут
                    expired_sessions.append(session_id)
            
            for session_id in expired_sessions:
                del SmartComfyUIBalancer.user_sessions[session_id]
                
            if expired_sessions:
                print(f"[CLEANUP] Удалено {len(expired_sessions)} старых сессий")

def run_smart_balancer(port=8190):
    """Запускает умный балансировщик нагрузки"""
    
    # Запускаем поток очистки сессий
    cleanup_thread = threading.Thread(target=cleanup_sessions, daemon=True)
    cleanup_thread.start()
    
    server = HTTPServer(('0.0.0.0', port), SmartComfyUIBalancer)
    print(f"🚀 Smart ComfyUI Load Balancer запущен на порту {port}")
    print("📊 Автоматическое распределение задач между GPU:")
    for i, instance in enumerate(SmartComfyUIBalancer.COMFYUI_INSTANCES):
        print(f"   GPU {instance['gpu_id']}: {instance['url']}")
    print(f"🌐 Единый интерфейс: http://89.208.11.177:{port}")
    print("💡 Все задачи автоматически распределяются по наименее загруженным GPU!")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Остановка балансировщика...")
        server.shutdown()

if __name__ == '__main__':
    run_smart_balancer()
