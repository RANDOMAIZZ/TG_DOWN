#!/bin/bash
set -e

# Add deno to PATH for yt-dlp EJS challenge solver
export PATH="/root/.deno/bin:$PATH"

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
tor --RunAsDaemon 1 --DataDirectory /tmp/tor --User root 2>/dev/null || true

# Wait for Tor to be ready (up to 30s)
echo "[start.sh] Waiting for Tor bootstrap..."
for i in 0 1 2 3 4 5 6 7 8 9; do
    sleep 3
    if curl --socks5 127.0.0.1:9050 --max-time 3 https://check.torproject.org/api/ip 2>/dev/null | grep -q IsTor; then
        echo "[start.sh] Tor ready"
        break
    fi
    echo "[start.sh] Tor not ready yet ($((i+1))*3s)"
done

# Pre-cache EJS challenge solver for YouTube
YTDLP=""
for cand in "$(dirname "$0")/venv/bin/yt-dlp" "$(dirname "$0")/.venv/bin/yt-dlp" "$(command -v yt-dlp 2>/dev/null)"; do
    if [ -n "$cand" ] && [ -f "$cand" ]; then YTDLP="$cand"; break; fi
done
if [ -z "$YTDLP" ] && command -v yt-dlp &>/dev/null; then
    YTDLP=$(command -v yt-dlp)
fi
if [ -n "$YTDLP" ]; then
    echo "[start.sh] Caching EJS challenge solver ($YTDLP)..."
    $YTDLP --remote-components ejs:github --no-warnings --ignore-errors --dump-json "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 2>/dev/null || true
    echo "[start.sh] EJS cache done"
else
    echo "[start.sh] yt-dlp not found, skipping EJS cache"
fi

PYTHONUNBUFFERED=1 exec python bot.py
