from .base import BaseDownloader, resolve_path
from .vk_session import (
    VK_REFERER,
    VK_CHROME_UA,
    is_vk_music_url,
    vk_api_get_video_info,
    format_vk_error,
)
from typing import Dict, Optional, Callable
import requests
import re
import os
import asyncio
import uuid
import yt_dlp

MIN_VIDEO_SIZE = 100 * 1024
COOKIE_FILES = ['vk_cookies.txt', 'vk.com_cookies.txt']


class VKDownloader(BaseDownloader):

    def __init__(self, temp_dir: str, vk_token: str = ''):
        super().__init__(temp_dir)
        self.vk_token = vk_token
        self._cached_info = None
        print(f"[VK] __init__: token={'есть' if vk_token else 'нет'}")

    def detect_url(self, url: str) -> bool:
        from .vk_session import is_vk_url
        found = is_vk_url(url) and not is_vk_music_url(url)
        print(f"[VK] detect_url({url[:60]}): {found}")
        return found

    @staticmethod
    def _normalize_url(url: str) -> str:
        url = (
            url.replace('vk.ru/', 'vk.com/')
            .replace('vkvideo.ru/', 'vk.com/')
            .replace('m.vk.ru/', 'vk.com/')
            .replace('m.vk.com/', 'vk.com/')
        )
        if url.startswith('http://'):
            url = 'https://' + url[7:]
        return url

    def _check_auth(self) -> bool:
        ok = bool(self.vk_token)
        print(f"[VK] _check_auth: {'есть токен' if ok else 'нет токена'}")
        return ok

    def _find_cookie_file(self) -> str:
        for name in COOKIE_FILES:
            path = resolve_path(name)
            if path and os.path.isfile(path):
                print(f"[VK] найден cookie файл: {path}")
                return path
        print(f"[VK] cookie файл не найден")
        return ''

    # ── yt-dlp helpers ──

    def _ytdlp_opts(self, **extra) -> dict:
        opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        cookie_file = self._find_cookie_file()
        if cookie_file:
            opts['cookiefile'] = cookie_file
        opts.update(extra)
        return opts

    @staticmethod
    def _closest_tier(h: int, tiers: list) -> int:
        if not h:
            return 0
        return min(tiers, key=lambda t: abs(t - h))

    def _ytdlp_get_info(self, url: str) -> Optional[Dict]:
        try:
            with yt_dlp.YoutubeDL(self._ytdlp_opts()) as ydl:
                info = ydl.extract_info(url, download=False)
                raw = info.get('formats', [])
                print(f"[VK] yt-dlp get_info: {len(raw)} raw форматов")

                tiers = [2160, 1440, 1080, 720, 540, 480, 360, 240, 144]
                tier_best = {}
                best_audio = None

                for f in raw:
                    vcodec = f.get('vcodec', 'none')
                    acodec = f.get('acodec', 'none')
                    height = f.get('height') or 0

                    if height and vcodec != 'none':
                        tier = self._closest_tier(height, tiers)
                        fsize = f.get('filesize') or 0
                        cur = tier_best.get(tier)
                        if not cur or fsize > (cur.get('filesize') or 0):
                            tier_best[tier] = f

                    elif vcodec == 'none' and acodec != 'none':
                        fabr = f.get('abr') or 0
                        babr = best_audio.get('abr') or 0 if best_audio else 0
                        if not best_audio or fabr > babr:
                            best_audio = f

                formats = []
                for tier in sorted(tiers, reverse=True):
                    f = tier_best.get(tier)
                    if f:
                        video_only = f.get('acodec', 'none') == 'none'
                        formats.append({
                            'format_id': f'{tier}p',
                            'quality': f'{tier}p',
                            'height': tier,
                            '_fmt_id': f['format_id'],
                            '_video_only': video_only,
                        })
                        print(f"[VK]   tier {tier}p: fmt_id={f['format_id']}, video_only={video_only}")

                if best_audio:
                    formats.append({
                        'format_id': 'Audio',
                        'quality': 'Audio',
                        'height': 0,
                        '_fmt_id': best_audio['format_id'],
                        '_video_only': False,
                    })
                    print(f"[VK]   audio: fmt_id={best_audio['format_id']}")

                print(f"[VK] yt-dlp get_info: {len(formats)} форматов")
                return {
                    'title': info.get('title', 'VK Video')[:50],
                    'duration': info.get('duration', 0),
                    'formats': formats,
                    'platform': 'vk',
                    'is_short': not formats,
                }
        except Exception as e:
            print(f"[VK] yt-dlp get_info error: {e}")
            return None

    def _ytdlp_download(self, url: str, target: dict = None, progress_cb: Callable = None) -> tuple:
        tag = uuid.uuid4().hex[:8]
        temp_name = f'vktmp_{tag}_%(id)s.%(ext)s'
        outtmpl = os.path.join(self.temp_dir, temp_name)

        fmt_id = (target or {}).get('_fmt_id', '')
        video_only = (target or {}).get('_video_only', False)
        is_audio = (target or {}).get('quality') == 'Audio'

        if is_audio:
            fmt = 'bestaudio/best'
        elif video_only or fmt_id:
            fmt = f'{fmt_id}+bestaudio/best[ext=mp4]/best' if fmt_id else 'best'
        else:
            fmt = 'best'

        print(f"[VK] yt-dlp download: fmt='{fmt}', video_only={video_only}, is_audio={is_audio}")

        hooks = []
        if progress_cb:
            def hook(d):
                if d['status'] == 'downloading':
                    total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                    downloaded = d.get('downloaded_bytes', 0)
                    fragment = d.get('fragment_index', 0) or 0
                    fragments = d.get('fragment_count', 0) or 0
                    speed = d.get('speed', 0) or 0
                    progress_cb('download', downloaded, total, fragment, fragments, speed)
                elif d['status'] == 'finished':
                    progress_cb('download', 1, 1, 1, 1, '')
            hooks.append(hook)

        opts = self._ytdlp_opts(
            format=fmt,
            outtmpl=outtmpl,
            progress_hooks=hooks,
        )
        if not is_audio:
            opts['merge_output_format'] = 'mp4'

        with yt_dlp.YoutubeDL(opts) as ydl:
            print(f"[VK] yt-dlp: запуск extract_info(download=True)...")
            info = ydl.extract_info(url, download=True)
            expected = ydl.prepare_filename(info)
            print(f"[VK] yt-dlp: expected={expected}")
            if os.path.isfile(expected):
                print(f"[VK] yt-dlp: найден по prepare_filename")
                return expected, info.get('title', 'VK Video')
            video_id = info.get('id', '')
            for f in os.listdir(self.temp_dir):
                if video_id in f and tag in f:
                    full = os.path.join(self.temp_dir, f)
                    print(f"[VK] yt-dlp: найден по video_id+tag: {full}")
                    return full, info.get('title', 'VK Video')
            candidates = [os.path.join(self.temp_dir, f) for f in os.listdir(self.temp_dir) if tag in f]
            if candidates:
                best = max(candidates, key=os.path.getmtime)
                print(f"[VK] yt-dlp: найден по tag: {best}")
                return best, info.get('title', 'VK Video')
            print(f"[VK] yt-dlp: файл не найден, возвращаем expected")
            return expected, info.get('title', 'VK Video')

    # ── Main API ──

    async def get_info(self, url: str) -> Dict:
        url = self._normalize_url(url)
        result = None
        print(f"[VK] get_info: {url[:80]}")

        # Level 1: VK API token
        if self._check_auth():
            def _sync():
                return vk_api_get_video_info(url, self.vk_token)
            loop = asyncio.get_event_loop()
            print(f"[VK] get_info: пробуем VK API...")
            result = await loop.run_in_executor(None, _sync)
            if result and result.get('formats'):
                has_direct = any(
                    f.get('url', '').lower().endswith(('.mp4', '.m3u8'))
                    for f in result['formats']
                )
                if has_direct:
                    print(f"[VK] API: {len(result['formats'])} форматов с прямыми ссылками")
                    self._cached_info = result
                    return result
                print(f"[VK] API дал только страницы, пробуем yt-dlp...")
            else:
                print(f"[VK] API не дал форматов, пробуем yt-dlp...")

        # Level 2: yt-dlp
        print(f"[VK] get_info: пробуем yt-dlp...")
        def _sync_yt():
            return self._ytdlp_get_info(url)
        loop = asyncio.get_event_loop()
        yt_result = await loop.run_in_executor(None, _sync_yt)
        if yt_result:
            print(f"[VK] yt-dlp: {len(yt_result['formats'])} форматов")
            self._cached_info = yt_result
            return yt_result

        # Всё сломалось
        error_text = result.get('error', '') if result else 'Не удалось загрузить видео'
        print(f"[VK] get_info: все методы не сработали: {error_text}")
        return {
            'error': format_vk_error(error_text) or error_text,
            'formats': [],
            'needs_auth': True,
        }

    async def download(
        self, url: str, format_id: str, progress_queue=None
    ) -> tuple:
        url = self._normalize_url(url)
        info = self._cached_info
        if not info:
            info = await self.get_info(url)

        if not info.get('formats'):
            return None, info.get('error', 'Нет форматов')

        # Найти целевой формат
        target = next((f for f in info['formats'] if f.get('format_id') == format_id), None)
        if not target:
            target = info['formats'][0]
            print(f"[VK] download: формат {format_id} не найден, берём первый: {target.get('format_id')}")
        else:
            print(f"[VK] download: целевой формат: {target.get('format_id')}")

        # Если есть прямой URL (.mp4/.m3u8) — качаем напрямую
        video_url = target.get('url', '')
        is_direct = video_url.lower().endswith(('.mp4', '.m3u8'))
        print(f"[VK] download: is_direct={is_direct}, url_=%s" % video_url[:100] if video_url else "нет URL")

        q = progress_queue
        main_loop = asyncio.get_event_loop()
        def progress(stage, current, total, fragment=0, fragments=0, speed=''):
            if q:
                try:
                    main_loop.call_soon_threadsafe(
                        q.put_nowait, {
                            'stage': stage, 'current': int(current), 'total': int(total),
                            'fragment': int(fragment), 'fragments': int(fragments),
                            'speed': str(speed),
                        }
                    )
                except Exception:
                    pass

        if is_direct:
            print(f"[VK] download: прямое скачивание...")
            def _sync():
                return self._download_direct(video_url, info.get('title', 'VK Video'), progress)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _sync)
            if result[0]:
                print(f"[VK] download: прямой download OK: {result[0]}")
                return result
            print(f"[VK] download: прямой download не сработал, пробуем yt-dlp")

        # yt-dlp
        try:
            def _sync():
                return self._ytdlp_download(url, target, progress)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _sync)
            print(f"[VK] download result: path={'OK' if result[0] else 'FAIL'}, title={result[1][:50] if result[1] else 'None'}")
            return result
        except Exception as e:
            print(f"[VK] download error: {e}")
            return None, f'Ошибка: {e}'

    # ── Прямое скачивание ──

    def _download_direct(self, video_url: str, title: str, progress_cb: Callable = None) -> tuple:
        tag = uuid.uuid4().hex[:10]
        ext = '.m3u8' if '.m3u8' in video_url.lower() else '.mp4'
        out = os.path.join(self.temp_dir, f'{tag}_vk_direct{ext}')
        print(f"[VK] _download_direct: {video_url[:100]} -> {out}")
        r = requests.get(
            video_url,
            headers={'User-Agent': self.user_agent, 'Referer': VK_REFERER},
            timeout=120, stream=True, allow_redirects=True,
        )
        r.raise_for_status()

        content_type = r.headers.get('Content-Type', r.headers.get('content-type', ''))
        print(f"[VK] _download_direct: status={r.status_code}, Content-Type={content_type[:50]}")
        if 'text' in content_type.lower() or 'html' in content_type.lower():
            print(f"[VK] _download_direct: HTML вместо видео")
            return None, 'HTML вместо видео'

        total = int(r.headers.get('content-length', 0))
        downloaded = 0
        with open(out, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb('download', downloaded, total)

        file_size = os.path.getsize(out)
        print(f"[VK] _download_direct: сохранено {file_size} байт в {out}")
        if file_size < MIN_VIDEO_SIZE:
            os.remove(out)
            print(f"[VK] _download_direct: файл слишком мал ({file_size} байт), удалён")
            return None, f'Видео повреждено ({file_size} байт)'
        return out, title

    # ── Извлечение из HTML (запасной вариант) ──

    def _extract_video_url_from_player(self, player_url: str) -> str:
        try:
            r = requests.get(
                player_url,
                headers={'User-Agent': VK_CHROME_UA, 'Referer': VK_REFERER},
                timeout=30, allow_redirects=True,
            )
            html = r.text
            patterns = [
                r'(?:https?:)?//[^"\']+?\.(?:mp4|m3u8)[^"\'\s]*',
                r'"url"\s*:\s*"((?:https?:)?//[^"]+\.(?:mp4|m3u8)[^"]*)"',
                r'"mp4"\s*:\s*"((?:https?:)?//[^"]+)"',
                r'"hls"\s*:\s*"((?:https?:)?//[^"]+)"',
                r'player\.videoFile\s*=\s*"([^"]+)"',
            ]
            for pat in patterns:
                m = re.search(pat, html, re.I)
                if m:
                    video_url = m.group(1)
                    if video_url.startswith('//'):
                        video_url = 'https:' + video_url
                    video_url = video_url.replace('\\/', '/').replace('&amp;', '&')
                    print(f"[VK] HTML парсинг: найден URL: {video_url[:100]}")
                    return video_url
            print(f"[VK] HTML парсинг: URL не найден")
            return ''
        except Exception as e:
            print(f"[VK] HTML парсинг error: {e}")
            return ''
