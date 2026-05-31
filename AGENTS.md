# Telegram Video Bot - Current State

## Goal
Multipurpose Telegram-бот, скачивающий видео/аудио с 13+ платформ (YouTube, TikTok, VK, OK, Twitter/X, Instagram и др.).

## Hosting
- **Hetzner VPS** (CX22, Ubuntu 22.04, public IP) — основной сервер
- Render больше не используется
- Контейнеризация: Dockerfile (python:3.11-slim + ffmpeg + tor + deno)

## YouTube Status (критический компонент)
- **`yt-dlp --remote-components ejs:github` в CLI работает** — показывает форматы видео (1080p)
- **Python API yt-dlp НЕ работает** — `extract_info()` не проксирует `remote_components`
- EJS challenge solver (Deno) кешируется через start.sh → `$(dirname "$0")/venv/bin/yt-dlp`
- Tor socks5 (`127.0.0.1:9050`) добавлен как fallback
- Куки YouTube загружены в `www.youtube.com_cookies.txt`

## Security (Чисто)
- **config.py**: больше НЕ содержит секретов (читает из .env / env vars)
- **.gitignore**: добавлены config.py, session-файлы, куки, venv/ и т.д.
- **.env.example**: шаблон для .env (сам .env в gitignore)
- **requirements.txt**: добавлен python-dotenv
- ALLOWED_USERS: настроен (4 пользователя)
- Impersonate отключён: `curl_cffi` не поддерживается сервером

## EJS Cache Solution
- `start.sh` (строка 31-37): $VENV_YT="/app/venv/bin/yt-dlp"
- Кеширует Deno-скрипты до старта бота

## Open Issues
1. 🚨 **YouTube не работает через Python API** — `n challenge solving failed`. После деплоя проверить
2. 🚨 **GitHub PAT токен засвечен** — отозвать в GitHub Settings
3. ⚠️ **Репозиторий публичный** — сделать приватным после отзыва токенов
4. ⚠️ **Старые токены (API_ID/API_HASH/BOT_TOKEN) засвечены в git history на сервере** — отозвать и создать новые

## Deploy Instructions (после пуша)
На сервере (Hetzner):
```bash
cd /root/video_bot
git pull
# Создать/обновить .env с новыми токенами
nano .env
# Удалить config.py из git-трекинга (если был закоммичен)
git rm --cached config.py 2>/dev/null; true
# Убить старый контейнер, собрать и запустить новый
docker stop video-bot 2>/dev/null; docker rm video-bot 2>/dev/null
docker build -t video-bot .
docker run -d \
  --name video-bot \
  --restart unless-stopped \
  --env-file .env \
  -v video-bot-data:/data \
  video-bot
# Проверить логи
docker logs -f video-bot
```

## Workflow
1. Редактировать код локально (Windows)
2. Пуш в GitHub (любым способом)
3. На Hetzner: `git pull && docker build -t video-bot . && docker rm -f video-bot && docker run -d ...`
4. Проверка: `docker logs -f video-bot` — искать `[start.sh] Caching EJS challenge solver...`
