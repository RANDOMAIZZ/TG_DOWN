#!/bin/bash
set -e

# Папка для скачиваний
mkdir -p downloads downloaders/cookies

# Восстанавливаем куки из переменной окружения (base64)
if [ -n "$YOUTUBE_COOKIES" ]; then
    echo "$YOUTUBE_COOKIES" | base64 -d > downloaders/cookies/youtube.txt 2>/dev/null && echo "[OK] YouTube cookies restored from env"
fi
if [ -n "$VK_COOKIES" ]; then
    echo "$VK_COOKIES" | base64 -d > vk.com_cookies.txt 2>/dev/null && echo "[OK] VK cookies restored from env"
fi

# Persistent disk at /data — пробрасываем сессию и куки
if [ -d /data ]; then
    for f in video_bot.session video_bot.session-journal vk_auth.json vk_cookies.txt vk.com_cookies.txt; do
        if [ -f "/data/$f" ] && [ ! -f "/app/$f" ]; then
            ln -s "/data/$f" "/app/$f"
        fi
    done
    mkdir -p /data/downloads
fi

exec python bot.py
