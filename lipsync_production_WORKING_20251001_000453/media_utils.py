#!/usr/bin/env python3
"""
Утилиты для работы с медиа файлами - обрезка видео по длине аудио
"""

import subprocess
import json
import os
from pathlib import Path
import uuid
import logging

logger = logging.getLogger(__name__)

def get_media_duration(file_path: str) -> float:
    """Получает длительность медиа файла в секундах"""
    try:
        cmd = [
            'ffprobe', 
            '-v', 'quiet', 
            '-print_format', 'json', 
            '-show_format', 
            file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            duration = float(data['format']['duration'])
            logger.info(f"Duration of {file_path}: {duration:.2f} seconds")
            return duration
        else:
            logger.error(f"Failed to get duration of {file_path}: {result.stderr}")
            return 0.0
            
    except Exception as e:
        logger.error(f"Error getting duration of {file_path}: {e}")
        return 0.0

def trim_video_to_audio_length(video_path: str, audio_path: str, output_path: str = None) -> str:
    """Обрезает видео по длине аудио файла"""
    try:
        # Получаем длительности файлов
        video_duration = get_media_duration(video_path)
        audio_duration = get_media_duration(audio_path)
        
        logger.info(f"Video duration: {video_duration:.2f}s, Audio duration: {audio_duration:.2f}s")
        
        # Если видео короче или равно аудио - возвращаем исходное видео
        if video_duration <= audio_duration:
            logger.info("Video is shorter or equal to audio, no trimming needed")
            return video_path
        
        # Создаем имя для обрезанного видео если не задано
        if output_path is None:
            video_file = Path(video_path)
            output_path = str(video_file.parent / f"trimmed_{video_file.name}")
        
        # Обрезаем видео по длине аудио
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-t', str(audio_duration),  # Обрезаем до длины аудио
            '-c:v', 'libx264',  # Кодек видео
            '-c:a', 'aac',      # Кодек аудио
            '-preset', 'fast',   # Быстрое кодирование
            '-y',               # Перезаписывать если существует
            output_path
        ]
        
        logger.info(f"Trimming video to {audio_duration:.2f} seconds...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)  # 5 минут таймаут
        
        if result.returncode == 0:
            logger.info(f"✅ Video successfully trimmed: {output_path}")
            return output_path
        else:
            logger.error(f"❌ Failed to trim video: {result.stderr}")
            return video_path  # Возвращаем исходное видео в случае ошибки
            
    except Exception as e:
        logger.error(f"❌ Error trimming video: {e}")
        return video_path  # Возвращаем исходное видео в случае ошибки

def prepare_media_files(video_path: str, audio_path: str) -> tuple[str, str]:
    """Подготавливает медиа файлы - ВСЕГДА обрезает видео по длине аудио"""
    try:
        logger.info(f"🎬 Preparing media files: video={Path(video_path).name}, audio={Path(audio_path).name}")
        
        # Обрезаем видео по длине аудио
        prepared_video = trim_video_to_audio_length(video_path, audio_path)
        
        return prepared_video, audio_path
        
    except Exception as e:
        logger.error(f"❌ Error preparing media files: {e}")
        return video_path, audio_path  # Возвращаем исходные файлы в случае ошибки
