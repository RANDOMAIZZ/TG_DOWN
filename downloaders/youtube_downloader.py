from .base import BaseDownloader
from typing import Dict
import os
import asyncio
import yt_dlp

QUALITY_MAP = {
    '144p': 144, '240p': 240, '360p': 360, '480p': 480,
    '720p': 720, '1080p': 1080, '1440p': 1440, '2160p': 2160,
}


class YouTubeDownloader(BaseDownloader):

    def __init__(self, temp_dir: str, cookiefile: str = '', cookies_browser: str = ''):
        super().__init__(temp_dir, cookiefile)
        self.cookies_browser = cookies_browser

    def _yt_extra(self) -> dict:
        if self.cookiefile and self.resolve_cookiefile(self.cookiefile):
            return {}
        if self.cookies_browser:
            print(f"[YT] cookies file not found, trying --cookies-from-browser {self.cookies_browser}")
            return {'cookiesfrombrowser': (self.cookies_browser, None, None, None)}
        prof = os.path.expanduser('~\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles')
        if os.path.isdir(prof):
            for entry in os.listdir(prof):
                if entry.endswith('.default-release') or entry.endswith('.default'):
                    p = os.path.join(prof, entry, 'cookies.sqlite')
                    if os.path.isfile(p):
                        try:
                            with open(p, 'rb') as _f:
                                _f.read(1)
                            print('[YT] cookies file not found, using Firefox cookies')
                            return {'cookiesfrombrowser': ('firefox', None, None, None)}
                        except Exception:
                            continue
        print('[YT] куки не найдены, использую Android client (без авторизации)')
        return {'extractor_args': {'youtube': {'player_client': ['android']}}}

    def detect_url(self, url: str) -> bool:
        u = url.lower()
        found = 'youtube.com' in u or 'youtu.be' in u
        print(f"[YT] detect_url({url[:60]}): {found}")
        return found

    def _build_fallback_formats(self):
        return [
            {'format_id': '2160p', 'quality': '2160p', 'height': 2160},
            {'format_id': '1080p', 'quality': '1080p', 'height': 1080},
            {'format_id': '720p', 'quality': '720p', 'height': 720},
            {'format_id': '480p', 'quality': '480p', 'height': 480},
            {'format_id': '360p', 'quality': '360p', 'height': 360},
        ]

    async def get_info(self, url: str) -> Dict:
        is_short = '/shorts/' in url.lower()
        print(f"[YT] get_info: {url[:60]} (shorts={is_short})")

        try:
            info = await self.ytdlp_get_info(url, cookiefile=self.cookiefile, extra=self._yt_extra())
            if not info:
                return {'platform': 'youtube', 'title': 'YouTube Video', 'duration': 0,
                        'is_short': is_short, 'formats': self._build_fallback_formats()}

            title = info.get('title', 'video')
            duration = info.get('duration', 0)

            if is_short:
                return {
                    'platform': 'youtube_shorts',
                    'title': title, 'duration': duration, 'is_short': True,
                    'formats': [{'format_id': 'best', 'quality': 'Auto'}],
                    'artist': info.get('artist') or info.get('channel', '') or info.get('uploader', ''),
                    'track': info.get('track') or title,
                }

            formats = self.parse_video_formats(info)
            if not formats:
                formats = self._build_fallback_formats()
            return {
                'platform': 'youtube', 'title': title, 'duration': duration,
                'is_short': False, 'formats': formats,
            }
        except Exception as e:
            print(f"[YT] get_info error: {e}")
            return {'platform': 'youtube', 'title': 'YouTube Video', 'duration': 0,
                    'is_short': is_short, 'formats': self._build_fallback_formats()}

    async def download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        print(f"[YT] download: format={format_id}, url={url[:60]}")

        extra = self._yt_extra()
        loop = asyncio.get_event_loop()

        # Мапим запрошенное качество в форматную строку yt-dlp
        if format_id == 'best':
            fmt_str = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best'
        elif format_id in QUALITY_MAP:
            h = QUALITY_MAP[format_id]
            fmt_str = f'bestvideo[height<={h}]+bestaudio/best[ext=mp4]/best'
        else:
            fmt_str = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best'

        print(f"[YT] download: fmt_str={fmt_str}")

        def _sync(fmt):
            outtmpl, tag = self.unique_outtmpl()
            opts = {
                'quiet': True, 'no_warnings': True,
                'outtmpl': outtmpl,
                'format': fmt,
                'merge_output_format': 'mp4',
                'http_headers': {'User-Agent': self.user_agent},
                'retries': 3, 'fragment_retries': 3, 'socket_timeout': 30,
            }
            cf = self.resolve_cookiefile(self.cookiefile)
            if cf:
                opts['cookiefile'] = cf
            if extra:
                opts.update(extra)
            if progress_queue:
                opts['progress_hooks'] = [self.make_progress_hook(progress_queue)]

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return None, 'Не удалось скачать'
                if info.get('_type') == 'playlist' and info.get('entries'):
                    info = info['entries'][0] or info
                title = (info.get('title') or info.get('track') or 'media')[:80]
                path = self.resolve_downloaded_file(info, ydl, tag)
                if path:
                    return path, title
                return None, 'Файл не найден после загрузки'

        result = await loop.run_in_executor(None, lambda: _sync(fmt_str))

        # Если не сработало — пробуем best
        if result[0] is None and fmt_str != 'best[ext=mp4]/best':
            print(f"[YT] download: fallback to best")
            result = await loop.run_in_executor(None, lambda: _sync('best[ext=mp4]/best'))

        print(f"[YT] download result: path={'OK' if result[0] else 'FAIL'}, title={result[1][:50] if result[1] else 'None'}")
        return result
