#!/usr/bin/env python3
import http.server
import socketserver
import webbrowser
import os

PORT = 8191
DIRECTORY = os.getcwd()

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()

if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
        print(f"🌐 ComfyUI Selector доступен по адресу:")
        print(f"   http://89.208.11.177:{PORT}/comfyui_selector.html")
        print(f"   http://localhost:{PORT}/comfyui_selector.html")
        print(f"\nНажмите Ctrl+C для остановки")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Сервер остановлен")
