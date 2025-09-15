#!/usr/bin/env python3
"""
Улучшенный балансировщик нагрузки для ComfyUI с поддержкой WebSocket
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import json
import threading
import time
import hashlib
import socket
import select
from urllib.parse import urlparse, parse_qs

class WebSocketComfyUIBalancer(BaseHTTPRequestHandler):
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
            total_load = running * 2 + pending
            
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
        loads = [self.get_instance_load(inst) for inst in self.COMFYUI_INSTANCES]
        
        # Для отправки задач выбираем наименее загруженный
        if self.command == 'POST' and '/prompt' in self.path:
            available_instances = [l for l in loads if l['available']]
            if not available_instances:
                return loads[0]['instance']
                
            best = min(available_instances, key=lambda x: x['total_load'])
            print(f"[TASK] Отправляем задачу на GPU {best['instance']['gpu_id']} (нагрузка: {best['total_load']})")
            return best['instance']
        
        # Для WebSocket и логов - используем сессионный экземпляр
        if self.path.startswith('/ws') or 'log' in self.path.lower():
            if client_session:
                with self.session_lock:
                    session_data = self.user_sessions.get(client_session, {})
                    preferred = session_data.get('preferred_instance')
                    if preferred:
                        return preferred
        
        # Выбираем наименее загруженный для новой сессии
        available_instances = [l for l in loads if l['available']]
        if available_instances:
            best = min(available_instances, key=lambda x: x['total_load'])
            
            if client_session:
                with self.session_lock:
                    self.user_sessions[client_session]['preferred_instance'] = best['instance']
            
            return best['instance']
        
        return self.COMFYUI_INSTANCES[0]
    
    def handle_websocket_upgrade(self, target_instance):
        """Обработка WebSocket upgrade запросов"""
        try:
            # Парсим URL цели
            target_url = target_instance['url'].replace('http://', '')
            host, port = target_url.split(':')
            port = int(port)
            
            # Создаем соединение с целевым сервером
            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.connect((host, port))
            
            # Подготавливаем заголовки для upgrade
            upgrade_headers = []
            for key, value in self.headers.items():
                if key.lower() == 'host':
                    upgrade_headers.append(f"{key}: {target_url}")
                else:
                    upgrade_headers.append(f"{key}: {value}")
            
            # Отправляем запрос на upgrade
            upgrade_request = f"GET {self.path} HTTP/1.1\r\n"
            upgrade_request += "\r\n".join(upgrade_headers) + "\r\n\r\n"
            
            target_sock.send(upgrade_request.encode())
            
            # Получаем ответ на upgrade
            response = target_sock.recv(4096)
            
            # Отправляем ответ клиенту
            self.wfile.write(response)
            
            # Начинаем проксирование WebSocket трафика
            client_sock = self.connection
            
            while True:
                ready = select.select([client_sock, target_sock], [], [], 30)
                if not ready[0]:
                    break
                    
                for sock in ready[0]:
                    try:
                        data = sock.recv(4096)
                        if not data:
                            break
                            
                        if sock == client_sock:
                            target_sock.send(data)
                        else:
                            client_sock.send(data)
                    except:
                        break
                        
            target_sock.close()
            
        except Exception as e:
            print(f"[ERROR] WebSocket proxy error: {e}")
            self.send_error(500, f'WebSocket proxy error: {str(e)}')
    
    def proxy_request(self, target_instance):
        """Проксирует обычный HTTP запрос"""
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
        
        # Проверяем WebSocket upgrade
        if (self.headers.get('Connection', '').lower() == 'upgrade' and 
            self.headers.get('Upgrade', '').lower() == 'websocket'):
            target = self.select_best_instance(client_session)
            print(f"[WebSocket] {self.path} -> GPU {target['gpu_id']}")
            self.handle_websocket_upgrade(target)
            return
        
        # Обычные GET запросы
        if (self.path.startswith('/queue') or self.path.startswith('/history') or 
            'log' in self.path.lower()):
            target = self.select_best_instance(client_session)
        else:
            target = self.select_best_instance(client_session)
            
        print(f"[GET] {self.path} -> GPU {target['gpu_id']}")
        self.proxy_request(target)
    
    def do_POST(self):
        client_session = self.get_client_session()
        
        if self.path.startswith('/prompt'):
            target = self.select_best_instance(force_new=True)
        else:
            target = self.select_best_instance(client_session)
            
        print(f"[POST] {self.path} -> GPU {target['gpu_id']}")
        self.proxy_request(target)

def cleanup_sessions():
    """Очистка старых сессий"""
    while True:
        time.sleep(300)
        current_time = time.time()
        
        with WebSocketComfyUIBalancer.session_lock:
            expired_sessions = []
            for session_id, session_data in WebSocketComfyUIBalancer.user_sessions.items():
                if current_time - session_data['last_activity'] > 1800:
                    expired_sessions.append(session_id)
            
            for session_id in expired_sessions:
                del WebSocketComfyUIBalancer.user_sessions[session_id]
                
            if expired_sessions:
                print(f"[CLEANUP] Удалено {len(expired_sessions)} старых сессий")

def run_websocket_balancer(port=8190):
    """Запускает балансировщик с поддержкой WebSocket"""
    
    cleanup_thread = threading.Thread(target=cleanup_sessions, daemon=True)
    cleanup_thread.start()
    
    server = HTTPServer(('0.0.0.0', port), WebSocketComfyUIBalancer)
    print(f"🚀 WebSocket ComfyUI Load Balancer запущен на порту {port}")
    print("📊 Поддержка WebSocket для логов в реальном времени:")
    for i, instance in enumerate(WebSocketComfyUIBalancer.COMFYUI_INSTANCES):
        print(f"   GPU {instance['gpu_id']}: {instance['url']}")
    print(f"🌐 Единый интерфейс с логами: http://89.208.11.177:{port}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Остановка балансировщика...")
        server.shutdown()

if __name__ == '__main__':
    run_websocket_balancer()
