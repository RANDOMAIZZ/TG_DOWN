from .base import BaseDownloader, resolve_path
from .vk_session import (
    VK_REFERER,
    is_vk_music_url,
    normalize_vk_music_url,
    vk_api_get_audio_info,
    format_vk_error,
)
from typing import Dict, Optional, Callable
import requests
import os
import asyncio
import uuid
import yt_dlp

MIN_AUDIO_SIZE = 1024
COOKIE_FILES = ['vk_cookies.txt', 'vk.com_cookies.txt']


class VKMusicDownloader(BaseDownloader):

    def __init__(self, temp_dir: str, vk_token: str = ''):
        super().__init__(temp_dir)
        self.vk_token = vk_token
        self._cached_info = None
        print(f"[VK_M] __init__: token={'есть' if vk_token else 'нет'}")

    def detect_url(self, url: str) -> bool:
        found = is_vk_music_url(url)
        print(f"[VK_M] detect_url({url[:60]}): {found}")
        return found

    def _check_auth(self) -> bool:
        ok = bool(self.vk_token)
        print(f"[VK_M] _check_auth: {'есть токен' if ok else 'нет токена'}")
        return ok

    def _find_cookie_file(self) -> str:
        for name in COOKIE_FILES:
            path = resolve_path(name)
            if path and os.path.isfile(path):
                print(f"[VK_M] найден cookie файл: {path}")
                return path
        print(f"[VK_M] cookie файл не найден")
        return ''

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

    def _ytdlp_get_info(self, url: str) -> Optional[Dict]:
        try:
            with yt_dlp.YoutubeDL(self._ytdlp_opts()) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = []
                for f in info.get('formats', []):
                    audio_url = f.get('url', '')
                    if audio_url:
                        formats.append({
                            'format_id': f.get('format_id', 'best'),
                            'quality': f.get('format_note', '') or f.get('abr', '') or 'MP3',
                            'url': audio_url,
                            'ext': f.get('ext', 'mp3'),
                            'filesize': f.get('filesize') or f.get('filesize_approx', 0),
                        })
                print(f"[VK_M] yt-dlp info: {len(formats)} форматов, title={info.get('title', '?')[:50]}")
                return {
                    'title': info.get('title', 'VK Audio')[:50],
                    'duration': info.get('duration', 0),
                    'formats': formats,
                    'platform': 'vk_music',
                    'is_short': True,
                }
        except Exception as e:
            print(f"[VK_M] yt-dlp audio info error: {e}")
            return None

    def _ytdlp_download(self, url: str, progress_cb: Callable = None) -> tuple:
        tag = uuid.uuid4().hex[:8]
        temp_name = f'vktmp_{tag}_%(id)s.%(ext)s'
        outtmpl = os.path.join(self.temp_dir, temp_name)
        print(f"[VK_M] yt-dlp download: tag={tag}")
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
            format='bestaudio/best',
            outtmpl=outtmpl,
            progress_hooks=hooks,
        )
        with yt_dlp.YoutubeDL(opts) as ydl:
            print(f"[VK_M] yt-dlp: запуск extract_info(download=True)...")
            info = ydl.extract_info(url, download=True)
            video_id = info.get('id', '')
            for f in os.listdir(self.temp_dir):
                if video_id in f and tag in f:
                    full = os.path.join(self.temp_dir, f)
                    print(f"[VK_M] yt-dlp: найден: {full}")
                    return full, info.get('title', 'VK Audio')
            expected = ydl.prepare_filename(info)
            print(f"[VK_M] yt-dlp: возвращаем expected: {expected}")
            return expected, info.get('title', 'VK Audio')

    async def get_info(self, url: str) -> Dict:
        url = normalize_vk_music_url(url)
        result = None
        print(f"[VK_M] get_info: {url[:80]}")

        # Level 1: VK API
        if self._check_auth():
            def _sync():
                return vk_api_get_audio_info(url, self.vk_token)
            loop = asyncio.get_event_loop()
            print(f"[VK_M] get_info: пробуем VK API...")
            result = await loop.run_in_executor(None, _sync)
            if result and result.get('formats'):
                print(f"[VK_M] API: {len(result['formats'])} форматов")
                self._cached_info = result
                return result
            print(f"[VK_M] API не сработал, пробуем yt-dlp...")

        # Level 2: yt-dlp
        print(f"[VK_M] get_info: пробуем yt-dlp...")
        def _sync_yt():
            return self._ytdlp_get_info(url)
        loop = asyncio.get_event_loop()
        yt_result = await loop.run_in_executor(None, _sync_yt)
        if yt_result:
            print(f"[VK_M] yt-dlp: {len(yt_result['formats'])} форматов")
            self._cached_info = yt_result
            return yt_result

        error_text = result.get('error', '') if result else 'Не удалось загрузить аудио'
        print(f"[VK_M] get_info: все методы не сработали: {error_text}")
        return {
            'error': format_vk_error(error_text) or error_text,
            'formats': [],
            'needs_auth': True,
        }

    async def download(
        self, url: str, format_id: str, progress_queue=None
    ) -> tuple:
        url = normalize_vk_music_url(url)
        info = self._cached_info
        if not info:
            info = await self.get_info(url)
        if not info.get('formats'):
            return None, info.get('error', 'Нет форматов')
        print(f"[VK_M] download: format={format_id}, info_platform={info.get('platform')}")

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

        # Level 1: VK API direct
        if info.get('platform') == 'vk_music' and 'url' in info['formats'][0]:
            audio_url = info['formats'][0].get('url', '')
            if audio_url:
                print(f"[VK_M] download: прямой URL, скачиваем напрямую...")
                def _sync():
                    return self._download_direct(audio_url, info.get('title', 'VK Audio'), progress)
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, _sync)
                if result[0]:
                    print(f"[VK_M] download: прямой download OK: {result[0]}")
                    return result
                print(f"[VK_M] download: прямой download не сработал, пробуем yt-dlp")

        # Level 2: yt-dlp
        try:
            def _sync():
                return self._ytdlp_download(url, progress)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _sync)
            print(f"[VK_M] download result: path={'OK' if result[0] else 'FAIL'}, title={result[1][:50] if result[1] else 'None'}")
            return result
        except Exception as e:
            print(f"[VK_M] download error: {e}")
            return None, f'Ошибка: {e}'

    def _download_direct(self, audio_url: str, title: str, progress_cb: Callable = None) -> tuple:
        tag = uuid.uuid4().hex[:10]
        out = os.path.join(self.temp_dir, f'{tag}_vk_audio.mp3')
        print(f"[VK_M] _download_direct: {audio_url[:100]} -> {out}")
        r = requests.get(
            audio_url,
            headers={'User-Agent': self.user_agent, 'Referer': VK_REFERER},
            timeout=120, stream=True, allow_redirects=True,
        )
        r.raise_for_status()
        print(f"[VK_M] _download_direct: status={r.status_code}")
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
        print(f"[VK_M] _download_direct: сохранено {file_size} байт")
        if file_size < MIN_AUDIO_SIZE:
            os.remove(out)
            print(f"[VK_M] _download_direct: файл слишком мал ({file_size} байт), удалён")
            return None, f'Аудио повреждено ({file_size} байт)'
        return out, title
