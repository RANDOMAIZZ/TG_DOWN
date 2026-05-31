#!/bin/bash
set -e

# Папка для скачиваний
mkdir -p downloads

# Persistent disk at /data — пробрасываем сессию и куки
if [ -d /data ]; then
    for f in video_bot.session video_bot.session-journal vk_auth.json vk_cookies.txt vk.com_cookies.txt; do
        if [ -f "/data/$f" ] && [ ! -f "/app/$f" ]; then
            ln -s "/data/$f" "/app/$f"
        fi
    done
    mkdir -p /data/downloads
fi

# Start Tor for YouTube IP bypass
tor --RunAsDaemon 1 2>/dev/null || true
sleep 3

PYTHONUNBUFFERED=1 exec python bot.py
