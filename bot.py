"""Telegram Video Bot — универсальный загрузчик видео/аудио."""
import os
import re
import sys
import uuid
import queue
import time
import asyncio
import threading
import http.server

# Python 3.14+ fix: pyrogram async_to_sync needs an event loop at import time
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
)
from pyrogram.errors import FloodWait
from config import (
    API_ID, API_HASH, BOT_TOKEN, TEMP_DIR, MAX_FILE_SIZE, ALLOWED_QUALITIES,
    DEEZER_ARL, VK_COOKIES_FILE, INSTAGRAM_COOKIES_FILE,
    SOUNDCLOUD_COOKIES_FILE, YANDEX_COOKIES_FILE,
    SPOTIFY_COOKIES_FILE, YOUTUBE_COOKIES_FILE, YOUTUBE_COOKIES_FROM_BROWSER,
    VK_LOGIN, VK_PASSWORD, VK_COOKIES_FROM_BROWSER,
    ALLOWED_USERS,
)
from downloaders import (
    YouTubeDownloader, TikTokDownloader, PornhubDownloader,
    XVideosDownloader, VKDownloader, PinterestDownloader,
    RutubeDownloader, OdklDownloader, InstagramDownloader, DeezerDownloader,
    VKMusicDownloader, SoundCloudDownloader, YandexMusicDownloader,
    SpotifyDownloader, BaseDownloader, resolve_path,
)
from downloaders.vk_session import is_vk_music_url, is_vk_url

EMOJIS = {
    'success': '\u2705', 'error': '\u274c', 'info': '\u2139\ufe0f',
    'download': '\u2b07\ufe0f', 'music': '\ud83c\udfb5', 'video': '\ud83c\udfac',
    'settings': '\u2699\ufe0f', 'quality': '\ud83d\udcf1', 'stop': '\u26d4',
    'queue': '\ud83d\udce4', 'loading': '\u23f3',
}
VK_AUTH_FILE = 'vk_auth.json'
app = Client("video_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


# ── Helpers ──

def _url_lower(url: str) -> str:
    return url.strip().lower().split('?')[0].split('#')[0]

def sanitize_filename(name: str, max_len: int = 100) -> str:
    name = re.sub(r'[\\/*?:"<>|]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    if len(name) > max_len:
        name = name[:max_len].rstrip()
    return name or 'audio'


def detect_platform(url: str) -> str:
    u = _url_lower(url)
    if 'youtube.com' in u or 'youtu.be' in u:
        return 'youtube_shorts' if '/shorts/' in u else 'youtube'
    if 'tiktok.com' in u or 'vm.tiktok.com' in u or 'vt.tiktok.com' in u:
        return 'tiktok_photo' if '/photo/' in u else 'tiktok'
    if 'soundcloud.com' in u or 'on.soundcloud.com' in u:
        return 'soundcloud'
    if 'music.yandex' in u or ('yandex.ru' in u and ('/album/' in u or '/track/' in u)):
        return 'yandex_music'
    if 'open.spotify.com' in u or 'spotify.com/track' in u:
        return 'spotify'
    if 'deezer.com' in u:
        return 'deezer'
    if is_vk_music_url(url):
        return 'vk_music'
    if is_vk_url(url):
        return 'vk'
    if 'pornhub.com' in u or 'pornhub.org' in u:
        return 'pornhub'
    if 'xvideos.com' in u or 'xv-ru.com' in u:
        return 'xvideos'
    if 'pinterest.com' in u or 'pin.it' in u:
        return 'pinterest'
    if 'rutube.ru' in u:
        return 'rutube'
    if 'ok.ru' in u or 'odnoklassniki.ru' in u:
        return 'odkl'
    if 'instagram.com' in u or 'instagr.am' in u:
        return 'instagram'
    return 'unknown'


def is_vk_video(url: str) -> bool:
    u = _url_lower(url)
    return is_vk_url(url) and not is_vk_music_url(url)


def make_progress_bar(pct: float, width: int = 16) -> str:
    filled = int(pct / 100 * width)
    return '█' * filled + '░' * (width - filled)


# ── VK Auth ──

def load_vk_auth() -> dict:
    try:
        if os.path.isfile(VK_AUTH_FILE):
            import json
            with open(VK_AUTH_FILE, encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"[Bot] Failed to load {VK_AUTH_FILE}: {e}")
    return {}


def save_vk_token(token: str = ''):
    import json
    data = {'vk_token': token} if token else {}
    with open(VK_AUTH_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def get_vk_token() -> str:
    stored = load_vk_auth()
    token = stored.get('vk_token', '') or ''
    if token:
        return token
    return VK_PASSWORD if VK_PASSWORD and VK_LOGIN else ''


# ── Platform → Downloader ──

def get_downloader(url: str):
    platform = detect_platform(url)
    if platform == 'vk_music':
        return VKMusicDownloader(TEMP_DIR, get_vk_token())
    if platform == 'vk':
        return VKDownloader(TEMP_DIR, get_vk_token())
    if platform == 'youtube' or platform == 'youtube_shorts':
        return YouTubeDownloader(TEMP_DIR, cookiefile=resolve_path(YOUTUBE_COOKIES_FILE), cookies_browser=YOUTUBE_COOKIES_FROM_BROWSER)
    if platform == 'tiktok' or platform == 'tiktok_photo':
        return TikTokDownloader(TEMP_DIR)
    if platform == 'soundcloud':
        return SoundCloudDownloader(TEMP_DIR, cookiefile=resolve_path(SOUNDCLOUD_COOKIES_FILE))
    if platform == 'yandex_music':
        return YandexMusicDownloader(TEMP_DIR, cookiefile=resolve_path(YANDEX_COOKIES_FILE))
    if platform == 'spotify':
        return SpotifyDownloader(TEMP_DIR, cookiefile=resolve_path(SPOTIFY_COOKIES_FILE))
    if platform == 'deezer':
        return DeezerDownloader(TEMP_DIR, DEEZER_ARL)
    if platform == 'instagram':
        return InstagramDownloader(TEMP_DIR, cookiefile=resolve_path(INSTAGRAM_COOKIES_FILE))
    if platform == 'pornhub':
        return PornhubDownloader(TEMP_DIR)
    if platform == 'xvideos':
        return XVideosDownloader(TEMP_DIR)
    if platform == 'pinterest':
        return PinterestDownloader(TEMP_DIR)
    if platform == 'rutube':
        return RutubeDownloader(TEMP_DIR)
    if platform == 'odkl':
        return OdklDownloader(TEMP_DIR)
    return None


# ── VK token extraction ──

VK_TOKEN_URL_RE = re.compile(
    r'(?:access_token=)(vk1\.[a-zA-Z0-9._\-]+)',
    re.I,
)


def extract_vk_token_from_url(text: str) -> str:
    """Извлекает токен VK из URL вида https://api.vk.com/blank.html#access_token=vk1.a..."""
    m = VK_TOKEN_URL_RE.search(text)
    if m:
        return m.group(1)
    return ''


# ── Commands ──

@app.on_message(filters.command("start"))
async def start_cmd(client, msg):
    await msg.reply_text(
        f"{EMOJIS['success']} *Video Bot запущен!*\n\n"
        "Отправьте ссылку.\n"
        "\U0001f511 VK: пришлите URL с токеном из браузера после авторизации\n"
        "\u0418\u043b\u0438 `/login vk_token <\u0442\u043e\u043a\u0435\u043d>`\n"
        "Для Яндекс/Instagram нужны cookies — см. папку `cookies/`",
        parse_mode=enums.ParseMode.MARKDOWN,
    )


@app.on_message(filters.command("help"))
async def help_cmd(client, msg):
    await msg.reply_text(
        f"{EMOJIS['info']} *Команды:*\n\n"
        "/start — запуск\n"
        "/help — справка\n"
        f"/login vk_token <\u0442\u043e\u043a\u0435\u043d> — VK токен\n"
        "/logout vk — удалить VK токен\n\n"
        "*Поддерживаемые платформы:*\n"
        "\U0001f3ac YouTube, YouTube Shorts\n"
        "\U0001f4f1 TikTok\n"
        "VK (\u0432\u0438\u0434\u0435\u043e \u0438 \u043c\u0443\u0437\u044b\u043a\u0430)\n"
        "\U0001f3b5 SoundCloud, Deezer, Spotify, Яндекс.Музыка\n"
        "\U0001f4f7 Instagram, Pinterest\n"
        "\U0001f4fa Pornhub, XVideos, Rutube\n\n"
        "*VK:*\n"
        "\U0001f511 `/login vk_token <\u0442\u043e\u043a\u0435\u043d>` — авторизация\n"
        "\u0414\u043e\u043c\u0435\u043d vkvideo.ru \u0442\u043e\u0436\u0435 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u0442\u0441\u044f\n\n"
        "Лимит: 2 GB (MTProto).",
        parse_mode=enums.ParseMode.MARKDOWN,
    )


@app.on_message(filters.command("login"))
async def login_cmd(client, msg):
    parts = msg.text.split(maxsplit=2)
    if len(parts) < 2 or parts[1].lower() not in ('vk', 'vk_token', 'vktoken'):
        await msg.reply_text(
            f"{EMOJIS['error']} *Использование:*\n\n"
            "`/login vk_token <\u0442\u043e\u043a\u0435\u043d>`\n"
            "\u0418\u043b\u0438 \u043f\u0440\u043e\u0441\u0442\u043e \u043f\u0440\u0438\u0448\u043b\u0438\u0442\u0435 URL \u0441 \u0442\u043e\u043a\u0435\u043d\u043e\u043c\n"
            "\u0438\u0437 \u0430\u0434\u0440\u0435\u0441\u043d\u043e\u0439 \u0441\u0442\u0440\u043e\u043a\u0438 \u043f\u043e\u0441\u043b\u0435 \u0430\u0432\u0442\u043e\u0440\u0438\u0437\u0430\u0446\u0438\u0438.\n\n"
            "\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0442\u043e\u043a\u0435\u043d: https://vkhost.github.io/\n\n"
            "\u0422\u043e\u043a\u0435\u043d \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u0435\u0442\u0441\u044f \u0438 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u043f\u043e\u0441\u043b\u0435 \u043f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0441\u043a\u0430.",
            parse_mode=enums.ParseMode.MARKDOWN,
        )
        return

    token_arg = parts[2].strip() if len(parts) > 2 else ''
    token = extract_vk_token_from_url(token_arg) or token_arg
    if not token:
        await msg.reply_text(f"{EMOJIS['error']} \u0422\u043e\u043a\u0435\u043d \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d")
        return
    save_vk_token(token)
    await msg.reply_text(
        f"{EMOJIS['success']} *VK \u0442\u043e\u043a\u0435\u043d \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d!*\n\n"
        "\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0441\u0441\u044b\u043b\u043a\u0443 \u043d\u0430 VK \u0432\u0438\u0434\u0435\u043e \u0438\u043b\u0438 \u043c\u0443\u0437\u044b\u043a\u0443.\n"
        "\u041f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u044e\u0442\u0441\u044f: vk.com, vk.ru, vkvideo.ru",
        parse_mode=enums.ParseMode.MARKDOWN,
    )


@app.on_message(filters.command("logout"))
async def logout_cmd(client, msg):
    parts = msg.text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].lower() in ('vk',):
        save_vk_token()
        remaining = get_vk_token()
        if remaining:
            await msg.reply_text(
                f"{EMOJIS['info']} \u0422\u043e\u043a\u0435\u043d \u0438\u0437 \u0431\u043e\u0442\u0430 \u0443\u0434\u0430\u043b\u0451\u043d, \u043d\u043e \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0435\u0442\u0441\u044f VK_PASSWORD \u0438\u0437 config.py",
                parse_mode=enums.ParseMode.MARKDOWN,
            )
        else:
            await msg.reply_text(
                f"{EMOJIS['success']} VK \u0442\u043e\u043a\u0435\u043d \u0443\u0434\u0430\u043b\u0451\u043d.",
                parse_mode=enums.ParseMode.MARKDOWN,
            )


# ── Message Handler (URL processing) ──

def build_quality_keyboard(formats: list) -> InlineKeyboardMarkup:
    """Формирует клавиатуру выбора качества из реально доступных форматов."""
    rows = []
    row = []
    for i, fmt in enumerate(formats):
        label = fmt.get('quality', fmt.get('format_id', f'fmt_{i}'))
        cb = fmt['format_id']
        row.append(InlineKeyboardButton(label, callback_data=f'fmt:{cb}'))
        if len(row) >= 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows) if rows else None


async def _download_audio_ytdlp(url: str, progress_queue, cookiefile: str = '') -> tuple:
    """Скачать только аудио через yt-dlp (для audio_only формата)."""
    import yt_dlp
    from downloaders.base import resolve_path
    tag = uuid.uuid4().hex[:8]
    outtmpl = os.path.join(TEMP_DIR, f'audio_{tag}_%(id)s.%(ext)s')

    q = progress_queue
    def hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            fragment = d.get('fragment_index', 0) or 0
            fragments = d.get('fragment_count', 0) or 0
            speed = d.get('speed', 0) or 0
            if q:
                try:
                    q.put_nowait({
                        'stage': 'download', 'current': int(downloaded), 'total': int(total),
                        'fragment': int(fragment), 'fragments': int(fragments),
                        'speed': f'{(speed / 1024 / 1024):.1f} MB/s' if speed else '',
                    })
                except Exception:
                    pass
        elif d['status'] == 'finished':
            if q:
                try:
                    q.put_nowait({
                        'stage': 'download', 'current': 1, 'total': 1,
                        'fragment': 1, 'fragments': 1, 'speed': '',
                    })
                except Exception:
                    pass

    opts = {
        'quiet': True, 'no_warnings': True,
        'format': 'worst[ext=mp4]/worst',
        'outtmpl': outtmpl,
        'progress_hooks': [hook],
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }],
    }
    cf = resolve_path(cookiefile) if cookiefile else None
    if cf:
        opts['cookiefile'] = cf

    def _sync():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            expected = ydl.prepare_filename(info)
            base, _ = os.path.splitext(expected)
            for ext in ('.mp3', '.m4a', '.opus', '.webm'):
                path = base + ext
                if os.path.isfile(path):
                    return path, info.get('title', 'Audio')[:50]
            return expected, info.get('title', 'Audio')[:50]

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)


async def _start_download_with_progress(
    msg: Message, status_msg, downloader, url: str, fmt_id: str, info: dict,
):
    q = queue.Queue()
    is_audio_only = fmt_id == 'audio_only'
    if is_audio_only:
        cf = getattr(downloader, 'cookiefile', '')
        dl_task = asyncio.create_task(_download_audio_ytdlp(url, q, cookiefile=cf))
    else:
        dl_task = asyncio.create_task(downloader.download(url, fmt_id, progress_queue=q))
    last_update = 0
    waiting_start = 0
    d_service = ''

    # Немедленное обновление — убираем info/выбор качества, показываем старт
    try:
        await status_msg.edit_text(f"\u2b07\ufe0f *\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430...*")
    except Exception:
        pass

    while True:
        d_stage, d_current, d_total, d_frag, d_frags, d_speed = 'download', 0, 0, 0, 0, ''
        found = False
        while not q.empty():
            try:
                item = q.get_nowait()
                if isinstance(item, dict):
                    d_stage = item.get('stage', 'download')
                    d_current = item.get('current', 0)
                    d_total = item.get('total', 0)
                    d_frag = item.get('fragment', 0)
                    d_frags = item.get('fragments', 0)
                    d_speed = item.get('speed', '')
                    svc = item.get('service', '')
                    if svc:
                        d_service = svc
                    found = True
                elif isinstance(item, tuple) and len(item) >= 2:
                    d_stage = item[0]
                    d_current = int(item[1]) if len(item) > 1 else 0
                    d_total = int(item[2]) if len(item) > 2 else 0
                    found = True
            except queue.Empty:
                break

        now = asyncio.get_event_loop().time()

        if found and d_stage == 'download' and d_total > 0:
            if now - last_update >= 1.5 or d_current >= d_total:
                pct = d_current / d_total * 100
                bar = make_progress_bar(pct)
                frag_info = f' \u2022 \u0424\u0440\u0430\u0433\u043c\u0435\u043d\u0442 {d_frag}/{d_frags}' if d_frags > 1 else ''
                speed_info = f' \u2022 {d_speed}' if d_speed else ''
                service_info = f'\U0001f4e1 {d_service}  \u00b7  ' if d_service else ''
                text = (
                    f"\U0001f4e5 *Download*\n"
                    f"{service_info}`{bar}` {pct:.0f}%  ({d_current/1024/1024:.1f}MB / {d_total/1024/1024:.1f}MB)"
                    f"{frag_info}{speed_info}"
                )
                try:
                    await status_msg.edit_text(text)
                except Exception:
                    pass
                last_update = now
        elif found and d_stage == 'download' and d_total == 0 and now - last_update >= 3.0:
            label = d_service if d_service else '\u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435...'
            dots = '.' * (int(now * 2) % 4)
            try:
                await status_msg.edit_text(f"\u2b07\ufe0f *{label}*{dots}")
            except Exception:
                pass
            last_update = now
        elif not found and now - last_update >= 3.0:
            if waiting_start == 0:
                waiting_start = now
            elapsed = int(now - waiting_start)
            dots = '.' * (elapsed % 4)
            try:
                await status_msg.edit_text(f"\u23f3 \u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u043c\u043e\u0436\u0435\u0442 \u0437\u0430\u043d\u044f\u0442\u044c \u043d\u0435\u043a\u043e\u0442\u043e\u0440\u043e\u0435 \u0432\u0440\u0435\u043c\u044f{dots}")
            except Exception:
                pass
            last_update = now

        if dl_task.done():
            break
        await asyncio.sleep(0.5)

    try:
        result = await dl_task
    except Exception as e:
        await status_msg.edit_text(f"{EMOJIS['error']} \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438: {e}")
        return
    if len(result) >= 3:
        filepath, filename, lyrics = result
    else:
        filepath, filename = result
        lyrics = ''
    if filepath is None:
        await status_msg.edit_text(f"{EMOJIS['error']} {filename}")
        return

    # Переименовываем аудио в название видео
    if filename and filepath.lower().endswith(('.flac', '.mp3', '.m4a', '.opus')):
        title_safe = sanitize_filename(filename)
        ext = os.path.splitext(filepath)[1]
        new_path = os.path.join(os.path.dirname(filepath), f'{title_safe}{ext}')
        if new_path != filepath and not os.path.isfile(new_path):
            try:
                os.rename(filepath, new_path)
                filepath = new_path
            except Exception:
                pass

    title_display = filename or info.get('title', '')
    caption = f"{EMOJIS['success']} *{title_display}*"

    # Парсим артиста/название один раз, используем и для текста, и для кнопки
    artist_lr, song_lr = BaseDownloader.parse_artist_title(info, filename)
    if not lyrics and song_lr:
        try:
            loop = asyncio.get_event_loop()
            lyrics = await loop.run_in_executor(
                None, lambda: BaseDownloader.fetch_lyrics_sync(artist_lr, song_lr)
            )
        except Exception as e:
            print(f"[Lyrics] error: {e}")
    file_size = os.path.getsize(filepath)
    tmb = file_size / 1024 / 1024

    last_up = 0
    async def upload_progress(current, total):
        nonlocal last_up
        if total <= 0:
            return
        now = asyncio.get_event_loop().time()
        if now - last_up < 0.5 and current < total:
            return
        last_up = now
        pct = current / total * 100
        bar = make_progress_bar(pct)
        text = f"\U0001f4e4 *Upload*\n`{bar}` {pct:.0f}%  ({current/1024/1024:.1f}MB / {total/1024/1024:.1f}MB)"
        try:
            await status_msg.edit_text(text)
        except Exception:
            pass

    is_audio_fmt = fmt_id == 'audio_only' or filepath.lower().endswith(('.flac', '.mp3', '.m4a'))
    is_zip = filepath.lower().endswith('.zip')
    is_image = filepath.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))

    # Встраиваем текст в сам файл
    if lyrics:
        try:
            from mutagen import File as MFile
            mf = MFile(filepath)
            if mf is not None:
                try:
                    mf['LYRICS'] = [lyrics]
                    mf.save()
                except Exception:
                    from mutagen.id3 import ID3, USLT
                    try:
                        id3 = ID3(filepath)
                        id3.add(USLT(encoding=3, lang='eng', desc='', text=lyrics))
                        id3.save()
                    except Exception:
                        pass
        except Exception as e:
            print(f'[Meta] embed lyrics error: {e}')

    # Кнопки для показа/скрытия текста
    user_data[msg.from_user.id] = {
        'lyrics_artist': artist_lr,
        'lyrics_title': song_lr,
        'lyrics_text': lyrics or '',
        'lyrics_msg_id': None,
    }
    show_hide_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton('\U0001f4dd \u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c \u0442\u0435\u043a\u0441\u0442', callback_data='show_lyrics'),
    ]]) if (lyrics or (artist_lr and song_lr)) else None

    try:
        if is_zip:
            sent = await msg.reply_document(
                document=filepath, caption=caption,
                parse_mode=enums.ParseMode.MARKDOWN,
                progress=upload_progress,
                reply_markup=show_hide_kb,
            )
        elif is_image:
            sent = await msg.reply_photo(
                photo=filepath, caption=caption,
                parse_mode=enums.ParseMode.MARKDOWN,
                progress=upload_progress,
                reply_markup=show_hide_kb,
            )
        elif info.get('platform') == 'vk_music' or is_audio_fmt:
            sent = await msg.reply_audio(
                audio=filepath, caption=caption,
                parse_mode=enums.ParseMode.MARKDOWN,
                progress=upload_progress,
                reply_markup=show_hide_kb,
            )
        else:
            sent = await msg.reply_video(
                video=filepath, caption=caption,
                parse_mode=enums.ParseMode.MARKDOWN,
                supports_streaming=True,
                progress=upload_progress,
                reply_markup=show_hide_kb,
            )
        user_data[msg.from_user.id]['audio_msg_id'] = sent.id
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"{EMOJIS['error']} \u041e\u0448\u0438\u0431\u043a\u0430: {e}")
    finally:
        try:
            if filepath and os.path.isfile(filepath):
                os.remove(filepath)
        except Exception:
            pass


@app.on_message(filters.text & ~filters.command(["start", "help", "login", "logout"]))
async def handle_url(client, msg):
    if ALLOWED_USERS and msg.from_user.id not in ALLOWED_USERS:
        await msg.reply_text(f"{EMOJIS['error']} \u0423 \u0432\u0430\u0441 \u043d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u0430 \u043a \u0431\u043e\u0442\u0443.")
        return
    text = msg.text.strip()

    # VK OAuth token URL — автоопределение
    token_from_url = extract_vk_token_from_url(text)
    if token_from_url and 'blank.html' in text.lower():
        save_vk_token(token_from_url)
        await msg.reply_text(
            f"{EMOJIS['success']} *VK \u0442\u043e\u043a\u0435\u043d \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d!*\n\n"
            "\u0422\u0435\u043f\u0435\u0440\u044c \u043c\u043e\u0436\u0435\u0442\u0435 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u0442\u044c VK \u0441\u0441\u044b\u043b\u043a\u0438.",
            parse_mode=enums.ParseMode.MARKDOWN,
        )
        return

    url = text

    # Нормализация VK: vk.com/video-* -> vkvideo.ru/video-*
    m_vk = re.match(r'https?://vk\.com/video([-\d_]+)', url)
    if m_vk:
        url = f'https://vkvideo.ru/video{m_vk.group(1)}'

    platform = detect_platform(url)
    if platform == 'unknown':
        await msg.reply_text(f"{EMOJIS['error']} \u041d\u0435\u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u043d\u043d\u0430\u044f \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0430.")
        return

    downloader = get_downloader(url)
    if downloader is None:
        await msg.reply_text(f"{EMOJIS['error']} \u041d\u0435\u0442 \u043f\u043e\u0434\u0445\u043e\u0434\u044f\u0449\u0435\u0433\u043e \u0437\u0430\u0433\u0440\u0443\u0437\u0447\u0438\u043a\u0430.")
        return

    load_frames = ['\u25d0\u25d1', '\u25d1\u25d0', '\u25d0\u25d1', '\u25d1\u25d0']
    async def _animate_loading(m):
        i = 0
        while True:
            d = '.' * ((i // 2) % 4)
            try:
                await m.edit_text(
                    f"{load_frames[i % len(load_frames)]} \u041f\u043e\u043b\u0443\u0447\u0430\u044e \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u044e{d}"
                )
            except Exception:
                pass
            i += 1
            await asyncio.sleep(1.0)

    status_msg = await msg.reply_text(f"\u25d0\u25d1 \u041f\u043e\u043b\u0443\u0447\u0430\u044e \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u044e...")
    anim_task = asyncio.create_task(_animate_loading(status_msg))
    try:
        info = await downloader.get_info(url)
    except Exception as e:
        anim_task.cancel()
        await status_msg.edit_text(f"{EMOJIS['error']} \u041e\u0448\u0438\u0431\u043a\u0430: {e}")
        return
    finally:
        anim_task.cancel()

    if info.get('error'):
        await status_msg.edit_text(f"{EMOJIS['error']} {info['error']}")
        return

    # Добавляем выбор "Audio" к любому видео
    if info.get('platform') != 'vk_music':
        has_video = any(
            str(f.get('quality', '')).rstrip('p').isdigit() or f.get('height', 0) > 0
            for f in info.get('formats', [])
        )
        if has_video and not any(f.get('quality') == 'Audio' for f in info.get('formats', [])):
            info['formats'].append({
                'format_id': 'audio_only',
                'quality': 'Audio',
                'height': 0,
            })

    title = info.get('title', '\u0411\u0435\u0437 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u044f')
    duration = info.get('duration', 0)
    mins, secs = divmod(int(duration), 60) if duration else (0, 0)
    duration_str = f"{mins}:{secs:02d}" if duration else "?"

    text = (
        f"{EMOJIS['video'] if info.get('platform') != 'vk_music' else EMOJIS['music']} *{title}*\n"
        f"\u23f1 {duration_str}\n\n"
        f"\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043a\u0430\u0447\u0435\u0441\u0442\u0432\u043e:"
    )

    formats = info.get('formats', [])
    keyboard = build_quality_keyboard(formats) if len(formats) > 1 else None
    if info.get('is_short') or not keyboard:
        fmt = formats[0] if formats else None
        if not fmt:
            await status_msg.edit_text(f"{EMOJIS['error']} \u041d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0445 \u0444\u043e\u0440\u043c\u0430\u0442\u043e\u0432.")
            return
        await _start_download_with_progress(msg, status_msg, downloader, url, fmt['format_id'], info)
        return

    await status_msg.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
    user_data[msg.from_user.id] = {'downloader': downloader, 'url': url, 'info': info, 'msg': msg}


user_data = {}


@app.on_callback_query()
async def handle_callback(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await callback.answer('\u0423 \u0432\u0430\u0441 \u043d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u0430', show_alert=True)
        return
    raw = callback.data
    user = user_data.get(user_id, {})

    # ── Кнопка показать/скрыть текст ──
    if raw == 'show_lyrics':
        await callback.answer()
        artist = user.get('lyrics_artist', '')
        title = user.get('lyrics_title', '')
        existing = user.get('lyrics_text', '')

        if not existing and artist and title:
            try:
                await callback.message.edit_reply_markup(None)
            except Exception:
                pass
            wait_msg = await callback.message.reply('\u23f3 \u0418\u0449\u0443 \u0442\u0435\u043a\u0441\u0442...')
            loop = asyncio.get_event_loop()
            existing = await loop.run_in_executor(
                None, lambda: BaseDownloader.fetch_lyrics_sync(artist, title)
            )
            user['lyrics_text'] = existing
            await wait_msg.delete()

        if existing:
            MAX_LYRICS = 3500
            display = existing[:MAX_LYRICS]
            if len(existing) > MAX_LYRICS:
                display += '\n\n...'
            sent_lyrics = await callback.message.reply(
                f'\U0001f3b5 *{title}*\n```\n{display}\n```',
                parse_mode=enums.ParseMode.MARKDOWN,
            )
            user['lyrics_msg_id'] = sent_lyrics.id
            hide_kb = InlineKeyboardMarkup([[
                InlineKeyboardButton('\U0001f648 \u0421\u043a\u0440\u044b\u0442\u044c \u0442\u0435\u043a\u0441\u0442', callback_data='hide_lyrics'),
            ]])
            try:
                await callback.message.edit_reply_markup(hide_kb)
            except Exception:
                pass
        else:
            await callback.answer('\u274c \u0422\u0435\u043a\u0441\u0442 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d', show_alert=True)
        return

    if raw == 'hide_lyrics':
        await callback.answer()
        lyrics_msg_id = user.get('lyrics_msg_id')
        if lyrics_msg_id:
            try:
                await client.delete_messages(callback.message.chat.id, lyrics_msg_id)
            except Exception:
                pass
            user['lyrics_msg_id'] = None
        show_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton('\U0001f4dd \u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c \u0442\u0435\u043a\u0441\u0442', callback_data='show_lyrics'),
        ]])
        try:
            await callback.message.edit_reply_markup(show_kb)
        except Exception:
            pass
        return

    # ── Выбор качества ──
    if not user:
        await callback.answer('\u0421\u0435\u0441\u0441\u0438\u044f \u0438\u0441\u0442\u0435\u043a\u043b\u0430', show_alert=True)
        return
    if 'downloader' not in user:
        await callback.answer('\u0421\u0435\u0441\u0441\u0438\u044f \u0438\u0441\u0442\u0435\u043a\u043b\u0430', show_alert=True)
        return

    fmt_id = raw[4:] if raw.startswith('fmt:') else raw
    downloader = user['downloader']
    url = user['url']
    info = user['info']
    msg = user['msg']

    fmt = next((f for f in info.get('formats', []) if f['format_id'] == fmt_id), None)
    if not fmt:
        await callback.answer('\u0424\u043e\u0440\u043c\u0430\u0442 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d', show_alert=True)
        return

    await callback.answer()
    m = callback.message
    await m.edit_text(f"\u2b07\ufe0f *\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430...*", reply_markup=None)
    await _start_download_with_progress(msg, m, downloader, url, fmt_id, info)


def _cleanup_temp_dir():
    resolved = resolve_path(TEMP_DIR)
    cutoff = time.time() - 3600
    count = 0
    for fname in os.listdir(resolved):
        fpath = os.path.join(resolved, fname)
        try:
            st = os.stat(fpath)
            if st.st_mtime < cutoff:
                os.remove(fpath)
                count += 1
        except Exception:
            pass
    if count:
        print(f"[VideoBot] \u043e\u0447\u0438\u0449\u0435\u043d\u043e {count} \u0444\u0430\u0439\u043b\u043e\u0432 \u0438\u0437 {resolved}")

# ── Main ──

if __name__ == '__main__':
    stored_token = get_vk_token()
    if stored_token:
        print(f"[VideoBot] VK: \u0430\u0432\u0442\u043e\u0440\u0438\u0437\u0430\u0446\u0438\u044f \u043f\u043e \u0442\u043e\u043a\u0435\u043d\u0443 ({VK_AUTH_FILE})")
    else:
        print("[VideoBot] VK: \u0442\u043e\u043a\u0435\u043d \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d. \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439\u0442\u0435 /login vk_token <\u0442\u043e\u043a\u0435\u043d>")

    # ── Загрузка базы рабочих сайтов ──
    try:
        from working_sites_manager import load_good_tidal_urls, patch_tidal_apis, patch_spotify_metadata
        good = load_good_tidal_urls()
        if good:
            print(f"[WS] \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043d\u043e {len(good)} \u0440\u0430\u0431\u043e\u0447\u0438\u0445 Tidal API")
        else:
            print("[WS] \u0431\u0430\u0437\u0430 \u0440\u0430\u0431\u043e\u0447\u0438\u0445 \u0441\u0430\u0439\u0442\u043e\u0432 \u043f\u0443\u0441\u0442\u0430")
        patch_tidal_apis()
        patch_spotify_metadata()
    except Exception as e:
        print(f"[WS] \u043e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438: {e}")
    _cleanup_temp_dir()
    print("[VideoBot] Bot started! MTProto (2 GB limit)")

    # Health check для Render Web Service
    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b'OK')
        def log_message(self, *a): pass
    threading.Thread(target=http.server.HTTPServer(('0.0.0.0', 10000), _H).serve_forever, daemon=True).start()

    app.run()
