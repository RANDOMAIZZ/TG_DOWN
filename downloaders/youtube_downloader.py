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
                print(f'[YT] Cookies loaded -> {YT_COOKIES_PATH} ({len(data)} bytes)')
            except Exception as e:
                print(f'[YT] Cookies error: {e}')

    def _get_cookiefile(self):
        if self._loaded_cookies and os.path.isfile(YT_COOKIES_PATH):
            return YT_COOKIES_PATH
        cf = self.resolve_cookiefile(self.cookiefile)
        return cf if cf else None

    def detect_url(self, url: str) -> bool:
        u = url.lower()
        return 'youtube.com' in u or 'youtu.be' in u

    async def get_info(self, url: str) -> Dict:
        is_short = '/shorts/' in url.lower()
        print(f'[YT] get_info: {url[:60]}')

        configs = [
            # 0: android client, worst format, no webpage
            {
                'quiet': True, 'no_warnings': True, 'socket_timeout': 30,
                'format': 'worst',
                'extractor_args': {'youtube': {'player_client': ['android'], 'skip': ['webpage', 'configs', 'js']}},
            },
            # 1: tv_embedded client
            {
                'quiet': True, 'no_warnings': True, 'socket_timeout': 30,
                'format': 'worst',
                'extractor_args': {'youtube': {'player_client': ['tv_embedded'], 'skip': ['webpage', 'configs']}},
            },
            # 2: web_creator client
            {
                'quiet': True, 'no_warnings': True, 'socket_timeout': 30,
                'format': 'worst',
                'extractor_args': {'youtube': {'player_client': ['web_creator'], 'skip': ['webpage', 'configs']}},
            },
            # 3: all clients, no skip
            {
                'quiet': True, 'no_warnings': True, 'socket_timeout': 30,
                'format': 'worst',
                'extractor_args': {'youtube': {'player_client': ['android', 'android_creator', 'tv_embedded', 'web_creator']}},
            },
            # 4: default yt-dlp with cookies only
            {
                'quiet': True, 'no_warnings': True, 'socket_timeout': 30,
                'format': 'worst',
            },
            # 5: default yt-dlp, no format specified (yt-dlp default)
            {
                'quiet': True, 'no_warnings': True, 'socket_timeout': 30,
            },
        ]

        cf = self._get_cookiefile()
        if cf:
            for c in configs:
                c['cookiefile'] = cf

        for i, opts in enumerate(configs):
            try:
                pc = opts.get('extractor_args', {}).get('youtube', {}).get('player_client', ['default'])
                print(f'[YT] cfg{i}: player={pc}, format={opts.get("format","best")}')
                info = await self.ytdlp_get_info(url, extra=opts)
                if info:
                    title = info.get('title', 'video')
                    duration = info.get('duration', 0)
                    print(f'[YT] cfg{i} OK: {title[:40]}')
                    if is_short:
                        return {
                            'platform': 'youtube_shorts', 'title': title,
                            'duration': duration, 'is_short': True,
                            'formats': [{'format_id': 'best', 'quality': 'Auto'}],
                            'artist': info.get('artist') or info.get('channel', '') or info.get('uploader', ''),
                            'track': info.get('track') or title,
                        }
                    formats = self.parse_video_formats(info)
                    return {
                        'platform': 'youtube', 'title': title,
                        'duration': duration, 'is_short': False,
                        'formats': formats or [{'format_id': 'best', 'quality': 'Auto'}],
                    }
            except Exception as e:
                print(f'[YT] cfg{i} fail: {e}')
                continue

        return {'error': 'All configs failed', 'formats': []}

    async def download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        print(f'[YT] download: format={format_id}, url={url[:60]}')

        configs = [
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30,
             'format': 'worst',
             'extractor_args': {'youtube': {'player_client': ['android'], 'skip': ['webpage', 'configs', 'js']}}},
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30,
             'format': 'worst',
             'extractor_args': {'youtube': {'player_client': ['tv_embedded'], 'skip': ['webpage', 'configs']}}},
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30,
             'format': 'worst',
             'extractor_args': {'youtube': {'player_client': ['web_creator'], 'skip': ['webpage', 'configs']}}},
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30,
             'format': 'worst',
             'extractor_args': {'youtube': {'player_client': ['android', 'android_creator', 'tv_embedded', 'web_creator']}}},
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30,
             'format': 'worst'},
        ]

        cf = self._get_cookiefile()
        if cf:
            for c in configs:
                c['cookiefile'] = cf

        for i, opts in enumerate(configs):
            try:
                print(f'[YT] dl cfg{i}: player={opts.get("extractor_args",{}).get("youtube",{}).get("player_client",["default"])}')
                result = await self.ytdlp_download(url, format_id, progress_queue, extra=opts)
                if result[0]:
                    print(f'[YT] dl cfg{i} OK')
                    return result
                print(f'[YT] dl cfg{i} fail: {result[1]}')
            except Exception as e:
                print(f'[YT] dl cfg{i} error: {e}')
                continue

        return None, 'All configs failed'
