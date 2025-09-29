# ComfyUI-LatentSyncWrapper 1.6 Analysis

Это unofficial implementation LatentSync 1.6 для ComfyUI с улучшениями:

## Ключевые особенности LatentSync 1.6:
1. **Enhanced Resolution Training**: 512×512 разрешение (vs 1.5)
2. **Improved Visual Quality**: Убрана размытость зубов и губ
3. **Reduced VRAM**: 20GB VRAM (RTX 3090 compatible)
4. **FlashAttention-2**: Нативная PyTorch реализация

## Архитектура системы:
- **ComfyUI Node**: Обертка для LatentSync
- **Модели**: VAE + UNet + SyncNet + Whisper
- **Процесс**: Video + Audio → Lip-sync Video

## Требования:
1. ComfyUI
2. FFmpeg
3. Модели (manual download из private HF repo):
   - vae/diffusion_pytorch_model.safetensors
   - latentsync_unet.pt (~5GB)  
   - stable_syncnet.pt (~1.6GB)
   - whisper/tiny.pt

## Зависимости:
diffusers, transformers, mediapipe, face-alignment, 
decord, ffmpeg-python, safetensors, soundfile, etc.

## Параметры узла:
- video_path: Входное видео
- audio: Аудио вход
- seed: Для воспроизводимости
- lips_expression: 1.0-3.0 (интенсивность движения губ)
- inference_steps: 10-50 (качество vs скорость)

## Ограничения:
- Фронтальное видео с лицом
- 25 FPS (автоконверсия)
- Не поддерживает аниме/мультфильмы
- Требует manual model downloads
