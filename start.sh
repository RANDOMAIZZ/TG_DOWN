#!/bin/bash
set -e

# Persistent disk at /data — пробрасываем сессию и куки
if [ -d /data ]; then
    for f in video_bot.session video_bot.session-journal vk_auth.json vk_cookies.txt vk.com_cookies.txt; do
        if [ -f "/data/$f" ] && [ ! -f "/app/$f" ]; then
            ln -s "/data/$f" "/app/$f"
        fi
    done
    # Папка для скачиваний
    mkdir -p /data/downloads
fi

exec python bot.py
