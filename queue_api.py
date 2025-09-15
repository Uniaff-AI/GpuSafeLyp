#!/usr/bin/env python3
"""
REST API для управления очередью обработки видео ComfyUI
"""
from flask import Flask, request, jsonify, send_from_directory
import logging
import json
from pathlib import Path
import uuid
from queue_manager import ComfyUIQueueManager, TaskStatus

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация Flask приложения
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 * 1024  # 16GB max file

# Глобальный менеджер очереди
queue_manager = None

def init_queue_manager():
    """Инициализировать менеджер очереди"""
    global queue_manager
    if not queue_manager:
        queue_manager = ComfyUIQueueManager(
            comfyui_url="http://127.0.0.1:8188",
            memory_per_video_gb=6.0  # Настройте под ваши нужды
        )
        logger.info("Менеджер очереди инициализирован")

@app.route('/api/status', methods=['GET'])
def get_queue_status():
    """Получить общий статус очереди"""
    try:
        status = queue_manager.get_queue_status()
        return jsonify({
            'success': True,
            'data': status
        })
    except Exception as e:
        logger.error(f"Ошибка получения статуса: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/tasks', methods=['POST'])
def add_task():
    """Добавить новую задачу в очередь"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Требуется JSON данные'
            }), 400
        
        # Проверяем обязательные поля
        required_fields = ['input_video', 'output_video', 'workflow']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Отсутствует обязательное поле: {field}'
                }), 400
        
        # Добавляем задачу
        task_id = queue_manager.add_task(
            input_video=data['input_video'],
            output_video=data['output_video'],
            workflow_data=data['workflow'],
            priority=data.get('priority', 0)
        )
        
        return jsonify({
            'success': True,
            'data': {
                'task_id': task_id,
                'status': 'pending'
            }
        })
        
    except Exception as e:
        logger.error(f"Ошибка добавления задачи: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/tasks/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Получить статус конкретной задачи"""
    try:
        task_status = queue_manager.get_task_status(task_id)
        
        if not task_status:
            return jsonify({
                'success': False,
                'error': 'Задача не найдена'
            }), 404
        
        # Преобразуем TaskStatus enum в строку
        if 'status' in task_status:
            task_status['status'] = task_status['status'].value
        
        return jsonify({
            'success': True,
            'data': task_status
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения статуса задачи: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/tasks/<task_id>', methods=['DELETE'])
def cancel_task(task_id):
    """Отменить задачу"""
    try:
        result = queue_manager.cancel_task(task_id)
        
        if result:
            return jsonify({
                'success': True,
                'message': f'Задача {task_id} отменена'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Невозможно отменить задачу (возможно, уже выполняется или завершена)'
            }), 400
            
    except Exception as e:
        logger.error(f"Ошибка отмены задачи: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/tasks', methods=['GET'])
def get_all_tasks():
    """Получить список всех задач"""
    try:
        with queue_manager.lock:
            tasks = []
            for task in queue_manager.tasks.values():
                task_dict = task.__dict__.copy()
                task_dict['status'] = task.status.value
                tasks.append(task_dict)
        
        return jsonify({
            'success': True,
            'data': {
                'tasks': tasks,
                'count': len(tasks)
            }
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения списка задач: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/gpu', methods=['GET'])
def get_gpu_info():
    """Получить информацию о GPU"""
    try:
        gpu_info = queue_manager.gpu_monitor.get_gpu_info()
        slots_info = queue_manager.gpu_monitor.calculate_available_slots()
        
        return jsonify({
            'success': True,
            'data': {
                'gpu_info': gpu_info,
                'slots_info': slots_info
            }
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения GPU информации: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Веб-интерфейс
@app.route('/', methods=['GET'])
def index():
    """Главная страница с мониторингом"""
    html = """
<!DOCTYPE html>
<html>
<head>
    <title>ComfyUI Queue Manager</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .status-card { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .running { background-color: #e3f2fd; }
        .pending { background-color: #fff3e0; }
        .completed { background-color: #e8f5e8; }
        .failed { background-color: #ffebee; }
        .refresh-btn { padding: 10px 20px; background-color: #2196F3; color: white; border: none; border-radius: 5px; cursor: pointer; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <div class="container">
        <h1>ComfyUI Queue Manager</h1>
        
        <button class="refresh-btn" onclick="loadData()">Обновить</button>
        
        <div id="queue-status" class="status-card">
            <h2>Статус очереди</h2>
            <div id="status-content">Загрузка...</div>
        </div>
        
        <div id="gpu-info" class="status-card">
            <h2>GPU информация</h2>
            <div id="gpu-content">Загрузка...</div>
        </div>
        
        <div id="tasks-list">
            <h2>Список задач</h2>
            <div id="tasks-content">Загрузка...</div>
        </div>
    </div>
    
    <script>
        function loadData() {
            loadQueueStatus();
            loadGPUInfo();
            loadTasks();
        }
        
        function loadQueueStatus() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const status = data.data;
                        document.getElementById('status-content').innerHTML = `
                            <p><strong>В очереди:</strong> ${status.pending}</p>
                            <p><strong>Выполняется:</strong> ${status.running}</p>
                            <p><strong>Завершено:</strong> ${status.completed}</p>
                            <p><strong>Ошибки:</strong> ${status.failed}</p>
                            <p><strong>Доступно слотов:</strong> ${status.available_slots}</p>
                            <p><strong>Макс. одновременно:</strong> ${status.max_concurrent}</p>
                        `;
                    }
                })
                .catch(error => {
                    document.getElementById('status-content').innerHTML = 'Ошибка загрузки: ' + error;
                });
        }
        
        function loadGPUInfo() {
            fetch('/api/gpu')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const gpu = data.data.gpu_info.gpus[0];
                        document.getElementById('gpu-content').innerHTML = `
                            <p><strong>Всего памяти:</strong> ${gpu.total_mb} MB</p>
                            <p><strong>Используется:</strong> ${gpu.used_mb} MB (${gpu.utilization_percent.toFixed(1)}%)</p>
                            <p><strong>Свободно:</strong> ${gpu.free_mb} MB</p>
                        `;
                    }
                })
                .catch(error => {
                    document.getElementById('gpu-content').innerHTML = 'Ошибка загрузки: ' + error;
                });
        }
        
        function loadTasks() {
            fetch('/api/tasks')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const tasks = data.data.tasks;
                        let html = '<table><tr><th>ID</th><th>Статус</th><th>Вход</th><th>Выход</th><th>Создана</th></tr>';
                        
                        tasks.forEach(task => {
                            const created = new Date(task.created_at * 1000).toLocaleString();
                            html += `<tr class="${task.status}">
                                <td>${task.task_id.substr(0, 8)}...</td>
                                <td>${task.status}</td>
                                <td>${task.input_video_path}</td>
                                <td>${task.output_video_path}</td>
                                <td>${created}</td>
                            </tr>`;
                        });
                        
                        html += '</table>';
                        document.getElementById('tasks-content').innerHTML = html;
                    }
                })
                .catch(error => {
                    document.getElementById('tasks-content').innerHTML = 'Ошибка загрузки: ' + error;
                });
        }
        
        // Автообновление каждые 5 секунд
        setInterval(loadData, 5000);
        
        // Загрузка при старте
        loadData();
    </script>
</body>
</html>
    """
    return html

if __name__ == '__main__':
    init_queue_manager()
    
    # Запуск Flask приложения
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        threaded=True
    )
