# 📋 Инструкции для загрузки на GitHub

Проект подготовлен к загрузке! Выполните следующие шаги:

## 🔐 1. Авторизация в GitHub CLI

```bash
cd /home/epycmax/ComfyUI-Production
gh auth login
```

Выберите:
- GitHub.com
- HTTPS
- Yes (for Git operations)
- Login with a web browser

## 🏗️ 2. Создание репозитория

После авторизации выполните:

```bash
# Создать репозиторий в организации Uniaff-AI
gh repo create Uniaff-AI/ComfyUI-Production-Deployment \
    --public \
    --description "Production-ready ComfyUI deployment with dual GPU support, auto-restart watchdog, and SystemD integration" \
    --source .

# Или создать и сразу загрузить
gh repo create Uniaff-AI/ComfyUI-Production-Deployment \
    --public \
    --description "Production-ready ComfyUI deployment with dual GPU support, auto-restart watchdog, and SystemD integration" \
    --source . \
    --push
```

## 📤 3. Альтернативный способ - ручная загрузка

Если предпочитаете создать репозиторий вручную:

1. Создайте репозиторий на GitHub.com в организации Uniaff-AI
2. Выполните команды:

```bash
git remote add origin https://github.com/Uniaff-AI/ComfyUI-Production-Deployment.git
git branch -M main
git push -u origin main
```

## 📊 4. Проверка загрузки

После успешной загрузки проверьте:

```bash
gh repo view Uniaff-AI/ComfyUI-Production-Deployment --web
```

## 📁 Состояние проекта

✅ Git репозиторий инициализирован
✅ Все файлы добавлены и закоммичены
✅ .gitignore настроен
✅ README_DEPLOYMENT.md создан
✅ SystemD сервисы включены
✅ Watchdog скрипт настроен

Готов к загрузке на GitHub!
