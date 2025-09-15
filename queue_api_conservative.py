#!/usr/bin/env python3
"""
REST API для управления очередью обработки видео ComfyUI (консервативная версия)
"""
from flask import Flask, request, jsonify
import logging
import json
import time
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
    """Инициализировать менеджер очереди с консервативными настройками"""
    global queue_manager
    if not queue_manager:
        queue_manager = ComfyUIQueueManager(
            comfyui_url="http://127.0.0.1:8188",
            memory_per_video_gb=15.0,  # Более консервативная оценка
            max_concurrent_tasks=2     # Принудительно ограничиваем до 2 задач
        )
        logger.info("Менеджер очереди инициализирован (консервативный режим)")

# Добавляем динамическую настройку
@app.route('/api/config', methods=['POST'])
def update_config():
    """Обновить конфигурацию системы"""
    try:
        data = request.get_json()
        
        if 'memory_per_video_gb' in data:
            queue_manager.gpu_monitor.memory_per_video = data['memory_per_video_gb'] * 1024
            logger.info(f"Обновлен memory_per_video_gb: {data['memory_per_video_gb']}")
        
        if 'safety_margin' in data:
            queue_manager.gpu_monitor.safety_margin = data['safety_margin']
            logger.info(f"Обновлен safety_margin: {data['safety_margin']}")
        
        if 'max_concurrent_tasks' in data:
            queue_manager.max_concurrent_tasks = data['max_concurrent_tasks']
            logger.info(f"Обновлен max_concurrent_tasks: {data['max_concurrent_tasks']}")
        
        return jsonify({
            'success': True,
            'message': 'Конфигурация обновлена',
            'current_config': {
                'memory_per_video_gb': queue_manager.gpu_monitor.memory_per_video / 1024,
                'safety_margin': queue_manager.gpu_monitor.safety_margin,
                'max_concurrent_tasks': queue_manager.max_concurrent_tasks
            }
        })
        
    except Exception as e:
        logger.error(f"Ошибка обновления конфигурации: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

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
        
        required_fields = ['input_video', 'output_video', 'workflow']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Отсутствует обязательное поле: {field}'
                }), 400
        
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
                'error': 'Невозможно отменить задачу'
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

@app.route('/api/emergency-stop', methods=['POST'])
def emergency_stop():
    """Экстренная остановка всех задач"""
    try:
        with queue_manager.lock:
            # Отменяем все pending задачи
            cancelled_count = 0
            for task in queue_manager.tasks.values():
                if task.status == TaskStatus.PENDING:
                    task.status = TaskStatus.CANCELLED
                    cancelled_count += 1
            
            # Очищаем очередь
            while not queue_manager.pending_queue.empty():
                try:
                    queue_manager.pending_queue.get_nowait()
                except:
                    break
        
        logger.info(f"Экстренная остановка: отменено {cancelled_count} задач")
        
        return jsonify({
            'success': True,
            'message': f'Отменено {cancelled_count} задач в очереди',
            'running_tasks_count': len(queue_manager.running_tasks)
        })
        
    except Exception as e:
        logger.error(f"Ошибка экстренной остановки: {e}")
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

# Обновленный веб-интерфейс с кнопкой экстренной остановки
@app.route('/', methods=['GET'])
def index():
    """Главная страница с мониторингом"""
    html = """
<!DOCTYPE html>
<html>
<head>
    <title>ComfyUI Queue Manager (Conservative)</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .status-card { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .running { background-color: #e3f2fd; }
        .pending { background-color: #fff3e0; }
        .completed { background-color: #e8f5e8; }
        .failed { background-color: #ffebee; }
        .btn { padding: 10px 20px; color: white; border: none; border-radius: 5px; cursor: pointer; margin: 5px; }
        .btn-primary { background-color: #2196F3; }
        .btn-danger { background-color: #f44336; }
        .btn-warning { background-color: #ff9800; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        .config-section { background-color: #f9f9f9; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .config-input { margin: 5px; padding: 5px; width: 100px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>ComfyUI Queue Manager (Conservative Mode)</h1>
        
        <div class="config-section">
            <h3>Настройки</h3>
            <label>Memory per Video (GB): <input type="number" id="memory-per-video" class="config-input" value="15" step="0.5"></label>
            <label>Max Concurrent: <input type="number" id="max-concurrent" class="config-input" value="2" step="1"></label>
            <label>Safety Margin: <input type="number" id="safety-margin" class="config-input" value="0.7" step="0.1" min="0.1" max="1.0"></label>
            <button class="btn btn-primary" onclick="updateConfig()">Обновить настройки</button>
        </div>
        
        <div>
            <button class="btn btn-primary" onclick="loadData()">Обновить</button>
            <button class="btn btn-danger" onclick="emergencyStop()">🚨 Экстренная остановка</button>
        </div>
        
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
        function updateConfig() {
            const config = {
                memory_per_video_gb: parseFloat(document.getElementById('memory-per-video').value),
                max_concurrent_tasks: parseInt(document.getElementById('max-concurrent').value),
                safety_margin: parseFloat(document.getElementById('safety-margin').value)
            };
            
            fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(config)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Настройки обновлены успешно!');
                    loadData();
                } else {
                    alert('Ошибка: ' + data.error);
                }
            })
            .catch(error => {
                alert('Ошибка сети: ' + error);
            });
        }
        
        function emergencyStop() {
            if (confirm('Вы уверены, что хотите отменить все задачи в очереди?')) {
                fetch('/api/emergency-stop', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert(data.message);
                        loadData();
                    } else {
                        alert('Ошибка: ' + data.error);
                    }
                })
                .catch(error => {
                    alert('Ошибка сети: ' + error);
                });
            }
        }
        
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
                            <p style="color: red;"><strong>Режим:</strong> Консервативный (ограничено для предотвращения ошибок памяти)</p>
                        `;
                    }
                });
        }
        
        function loadGPUInfo() {
            fetch('/api/gpu')
                .then(response => response.json())
                .then(data => {
                    if (data.success && data.data.gpu_info.gpus.length > 0) {
                        const gpu = data.data.gpu_info.gpus[0];
                        document.getElementById('gpu-content').innerHTML = `
                            <p><strong>Всего памяти:</strong> ${gpu.total_mb} MB</p>
                            <p><strong>Используется:</strong> ${gpu.used_mb} MB (${gpu.utilization_percent.toFixed(1)}%)</p>
                            <p><strong>Свободно:</strong> ${gpu.free_mb} MB</p>
                        `;
                    }
                });
        }
        
        function loadTasks() {
            fetch('/api/tasks')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const tasks = data.data.tasks;
                        let html = '<table><tr><th>ID</th><th>Статус</th><th>Вход</th><th>Выход</th><th>Создана</th><th>Действия</th></tr>';
                        
                        tasks.forEach(task => {
                            const created = new Date(task.created_at * 1000).toLocaleString();
                            const cancelBtn = task.status === 'pending' ? 
                                `<button class="btn btn-warning" onclick="cancelTask('${task.task_id}')">Отменить</button>` : '';
                            
                            html += `<tr class="${task.status}">
                                <td>${task.task_id.substr(0, 8)}...</td>
                                <td>${task.status}</td>
                                <td>${task.input_video_path}</td>
                                <td>${task.output_video_path}</td>
                                <td>${created}</td>
                                <td>${cancelBtn}</td>
                            </tr>`;
                        });
                        
                        html += '</table>';
                        document.getElementById('tasks-content').innerHTML = html;
                    }
                });
        }
        
        function cancelTask(taskId) {
            fetch('/api/tasks/' + taskId, {method: 'DELETE'})
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Задача отменена');
                    loadData();
                } else {
                    alert('Ошибка: ' + data.error);
                }
            });
        }
        
        // Автообновление каждые 3 секунды (чаще для отслеживания проблем)
        setInterval(loadData, 3000);
        
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
