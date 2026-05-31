from .base import BaseDownloader
from typing import Dict
import os
import base64
import yt_dlp
import asyncio


YT_COOKIES_PATH = '/tmp/yt_cookies.txt'


class YouTubeDownloader(BaseDownloader):

    def __init__(self, temp_dir: str, cookiefile: str = '', cookies_browser: str = ''):
        super().__init__(temp_dir, cookiefile)
        self.cookies_browser = cookies_browser
        self._loaded_cookies = False

        raw = os.environ.get('YOUTUBE_COOKIES')
        if raw:
            try:
                data = base64.b64decode(raw)
                with open(YT_COOKIES_PATH, 'wb') as f:
                    f.write(data)
                self.cookiefile = YT_COOKIES_PATH
                self._loaded_cookies = True
                print(f"[YT] Cookies loaded -> {YT_COOKIES_PATH} ({len(data)} bytes)")
            except Exception as e:
                print(f"[YT] Cookies error: {e}")

    def _get_cookiefile(self):
        if self._loaded_cookies and os.path.isfile(YT_COOKIES_PATH):
            return YT_COOKIES_PATH
        cf = self.resolve_cookiefile(self.cookiefile)
        return cf if cf else None

    def _base_opts(self):
        return {
            'quiet': True,
            'no_warnings': True,
            'http_headers': {'User-Agent': self.user_agent},
            'socket_timeout': 30,
        }

    def detect_url(self, url: str) -> bool:
        u = url.lower()
        found = 'youtube.com' in u or 'youtu.be' in u
        print(f"[YT] detect_url({url[:60]}): {found}")
        return found

    async def get_info(self, url: str) -> Dict:
        is_short = '/shorts/' in url.lower()
        print(f"[YT] get_info: {url[:60]} (shorts={is_short})")

        opts = self._base_opts()
        cf = self._get_cookiefile()
        if cf:
            opts['cookiefile'] = cf
            print(f"[YT] get_info: using cookies")
        else:
            opts['extractor_args'] = {'youtube': {'player_client': ['android']}}
            print(f"[YT] get_info: using android client (no cookies)")

        def _sync():
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, _sync)
        except Exception as e:
            print(f"[YT] get_info error: {e}")
            return {'error': str(e), 'formats': []}

        if not info:
            return {'error': 'yt-dlp вернул None', 'formats': []}

        title = info.get('title', 'video')
        duration = info.get('duration', 0)
        print(f"[YT] get_info: title={title[:50]}, duration={duration}s")

        if is_short:
            return {
                'platform': 'youtube_shorts', 'title': title,
                'duration': duration, 'is_short': True,
                'formats': [{'format_id': 'best', 'quality': 'Auto'}],
                'artist': info.get('artist') or info.get('channel', '') or info.get('uploader', ''),
                'track': info.get('track') or title,
            }

        formats = self.parse_video_formats(info)
        print(f"[YT] get_info: {len(formats)} форматов")
        return {
            'platform': 'youtube', 'title': title,
            'duration': duration, 'is_short': False,
            'formats': formats or [{'format_id': 'best', 'quality': 'Auto'}],
        }

    async def download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        print(f"[YT] download: format={format_id}, url={url[:60]}")

        opts = self._base_opts()
        cf = self._get_cookiefile()
        if cf:
            opts['cookiefile'] = cf
        else:
            opts['extractor_args'] = {'youtube': {'player_client': ['android']}}

        outtmpl, tag = self.unique_outtmpl()
        opts['outtmpl'] = outtmpl
        if progress_queue:
            opts['progress_hooks'] = [self.make_progress_hook(progress_queue)]

        def _sync():
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
                return None, 'Файл не найден'

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _sync)
        print(f"[YT] download result: path={'OK' if result[0] else 'FAIL'}")
        return result
