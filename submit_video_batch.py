#!/usr/bin/env python3
"""
Helper для массовой отправки видео в очередь обработки
"""
import json
import requests
import sys
import argparse
from pathlib import Path
import glob

def load_workflow_template(workflow_file):
    """Загрузить шаблон workflow"""
    try:
        with open(workflow_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка загрузки workflow: {e}")
        return None

def submit_video_task(api_url, input_video, output_video, workflow, priority=0):
    """Отправить задачу на обработку видео"""
    payload = {
        "input_video": str(input_video),
        "output_video": str(output_video),
        "workflow": workflow,
        "priority": priority
    }
    
    try:
        response = requests.post(f"{api_url}/api/tasks", 
                               json=payload, 
                               timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if result['success']:
                return result['data']['task_id']
            else:
                print(f"Ошибка API: {result.get('error', 'Unknown error')}")
                return None
        else:
            print(f"HTTP ошибка: {response.status_code} - {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Ошибка сети: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Отправка видео в очередь обработки ComfyUI")
    parser.add_argument("--api-url", default="http://localhost:5000", 
                       help="URL API очереди")
    parser.add_argument("--workflow", required=True, 
                       help="Путь к файлу workflow JSON")
    parser.add_argument("--input-pattern", required=True,
                       help="Паттерн входных файлов (например: '/path/to/videos/*.mp4')")
    parser.add_argument("--output-dir", required=True,
                       help="Директория для выходных файлов")
    parser.add_argument("--output-suffix", default="_processed", 
                       help="Суффикс для выходных файлов")
    parser.add_argument("--priority", type=int, default=0,
                       help="Приоритет задач (больше = выше приоритет)")
    
    args = parser.parse_args()
    
    # Загружаем workflow
    workflow = load_workflow_template(args.workflow)
    if not workflow:
        sys.exit(1)
    
    # Находим входные файлы
    input_files = glob.glob(args.input_pattern)
    if not input_files:
        print(f"Не найдено файлов по паттерну: {args.input_pattern}")
        sys.exit(1)
    
    # Создаем выходную директорию
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Найдено {len(input_files)} файлов для обработки")
    print(f"Workflow: {args.workflow}")
    print(f"API URL: {args.api_url}")
    print(f"Выходная директория: {output_dir}")
    print()
    
    submitted_tasks = []
    
    for input_file in input_files:
        input_path = Path(input_file)
        output_filename = input_path.stem + args.output_suffix + input_path.suffix
        output_path = output_dir / output_filename
        
        print(f"Отправляем: {input_path.name} -> {output_filename}")
        
        task_id = submit_video_task(
            args.api_url, 
            str(input_path), 
            str(output_path), 
            workflow, 
            args.priority
        )
        
        if task_id:
            submitted_tasks.append({
                'task_id': task_id,
                'input': str(input_path),
                'output': str(output_path)
            })
            print(f"  ✓ Task ID: {task_id}")
        else:
            print(f"  ✗ Ошибка отправки")
    
    print(f"\nВсего отправлено задач: {len(submitted_tasks)}")
    
    if submitted_tasks:
        print("\nСтатус можно проверить по адресу:")
        print(f"{args.api_url}")
        print("\nИли через API:")
        for task in submitted_tasks:
            print(f"curl {args.api_url}/api/tasks/{task['task_id']}")

if __name__ == '__main__':
    main()
