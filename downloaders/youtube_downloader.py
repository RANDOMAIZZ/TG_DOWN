from .base import BaseDownloader
from typing import Dict
import os
import base64


YT_COOKIES_PATH = '/tmp/yt_cookies.txt'


class YouTubeDownloader(BaseDownloader):

    def __init__(self, temp_dir: str, cookiefile: str = '', cookies_browser: str = ''):
        super().__init__(temp_dir, cookiefile)
        self.cookies_browser = cookies_browser
        self._loaded_cookies = False

        # Пытаемся загрузить куки из переменной окружения (Render)
        raw = os.environ.get('YOUTUBE_COOKIES')
        if raw:
            try:
                data = base64.b64decode(raw)
                with open(YT_COOKIES_PATH, 'wb') as f:
                    f.write(data)
                self.cookiefile = YT_COOKIES_PATH
                self._loaded_cookies = True
                print(f"[YT] Cookies loaded from env -> {YT_COOKIES_PATH} ({len(data)} bytes)")
            except Exception as e:
                print(f"[YT] Failed to load cookies from env: {e}")

    def _yt_extra(self) -> dict:
        # Если куки загружены — ничего не делаем, yt-dlp использует default web client
        if self._loaded_cookies:
            return {}
        if self.cookiefile and self.resolve_cookiefile(self.cookiefile):
            return {}
        if self.cookies_browser:
            print(f"[YT] cookies file not found, trying --cookies-from-browser {self.cookies_browser}")
            return {'cookiesfrombrowser': (self.cookies_browser, None, None, None)}
        # Firefox на локальном ПК
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

    async def get_info(self, url: str) -> Dict:
        is_short = '/shorts/' in url.lower()
        print(f"[YT] get_info: {url[:60]} (shorts={is_short})")

        try:
            info = await self.ytdlp_get_info(url, cookiefile=self.cookiefile, extra=self._yt_extra())
            if not info:
                print(f"[YT] get_info: yt-dlp вернул None")
                return {'error': 'Не удалось получить информацию', 'formats': []}

            title = info.get('title', 'video')
            duration = info.get('duration', 0)
            print(f"[YT] get_info: title={title[:50]}, duration={duration}s")

            if is_short:
                print(f"[YT] get_info: это Shorts, отдаём Auto")
                return {
                    'platform': 'youtube_shorts',
                    'title': title,
                    'duration': duration,
                    'is_short': True,
                    'formats': [{'format_id': 'best', 'quality': 'Auto'}],
                    'artist': info.get('artist') or info.get('channel', '') or info.get('uploader', ''),
                    'track': info.get('track') or title,
                }

            formats = self.parse_video_formats(info)
            print(f"[YT] get_info: {len(formats)} форматов")
            return {
                'platform': 'youtube',
                'title': title,
                'duration': duration,
                'is_short': False,
                'formats': formats,
            }
        except Exception as e:
            print(f"[YT] get_info error: {e}")
            return {'error': str(e), 'formats': []}

    async def download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        print(f"[YT] download: format={format_id}, url={url[:60]}")
        # Всегда используем best — format_id от parse_video_formats ненадёжен
        result = await self.ytdlp_download(url, 'best', progress_queue, cookiefile=self.cookiefile, extra=self._yt_extra())
        print(f"[YT] download result: path={'OK' if result[0] else 'FAIL'}, title={result[1][:50] if result[1] else 'None'}")
        return result
