#!/usr/bin/env python3
"""
Простейший прокси для ComfyUI с автораспределением задач
"""
import http.server
import socketserver
import requests
import json
import time
from urllib.parse import urlparse

class SimpleComfyUIProxy(http.server.SimpleHTTPRequestHandler):
    INSTANCES = [
        'http://localhost:8188',
        'http://localhost:8189'
    ]
    
    def get_instance_loads(self):
        loads = []
        for url in self.INSTANCES:
            try:
                resp = requests.get(f"{url}/queue", timeout=1)
                data = resp.json()
                running = len(data.get('queue_running', []))
                pending = len(data.get('queue_pending', []))
                total = running + pending
                loads.append((url, total, running, pending))
            except:
                loads.append((url, 999, 999, 0))
        return loads
    
    def select_instance(self):
        loads = self.get_instance_loads()
        # Выбираем наименее загруженный
        best = min(loads, key=lambda x: x[1])
        return best[0]
    
    def proxy_to_instance(self, target_url):
        try:
            # Готовим заголовки
            headers = dict(self.headers)
            if 'host' in headers:
                del headers['host']
            
            # Читаем тело
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else None
            
            # Отправляем запрос
            if self.command == 'GET':
                resp = requests.get(target_url + self.path, headers=headers, stream=True)
            elif self.command == 'POST':
                resp = requests.post(target_url + self.path, headers=headers, data=body, stream=True)
            else:
                self.send_error(405)
                return
            
            # Возвращаем ответ
            self.send_response(resp.status_code)
            for key, value in resp.headers.items():
                if key.lower() not in ['connection', 'transfer-encoding']:
                    self.send_header(key, value)
            self.end_headers()
            
            # Стримим контент
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    self.wfile.write(chunk)
                    
        except Exception as e:
            print(f"Proxy error: {e}")
            self.send_error(500)
    
    def do_GET(self):
        if self.path == '/status':
            # Статус всех экземпляров
            loads = self.get_instance_loads()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            status = {
                'instances': [
                    {'url': url, 'total_tasks': total, 'running': running, 'pending': pending}
                    for url, total, running, pending in loads
                ]
            }
            self.wfile.write(json.dumps(status, indent=2).encode())
            return
        
        # Для задач выбираем наименее загруженный
        if '/prompt' in self.path:
            target = self.select_instance()
            print(f"[TASK] Направляем на {target}")
        else:
            # Для остального используем первый
            target = self.INSTANCES[0]
        
        self.proxy_to_instance(target)
    
    def do_POST(self):
        # Для задач всегда выбираем наименее загруженный
        if '/prompt' in self.path:
            target = self.select_instance()
            loads = self.get_instance_loads()
            gpu_id = 0 if target.endswith('8188') else 1
            load = next((x for x in loads if x[0] == target), (target, 0, 0, 0))
            print(f"[TASK] POST {self.path} -> GPU {gpu_id} (нагрузка: {load[1]})")
        else:
            target = self.INSTANCES[0]
        
        self.proxy_to_instance(target)

if __name__ == '__main__':
    PORT = 8191
    with socketserver.TCPServer(("", PORT), SimpleComfyUIProxy) as httpd:
        print(f"🚀 Simple ComfyUI Proxy запущен на порту {PORT}")
        print(f"🌐 http://89.208.11.177:{PORT}")
        print("📊 Автораспределение задач между GPU")
        print("📋 Статус: http://89.208.11.177:8190/status")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Остановка...")
