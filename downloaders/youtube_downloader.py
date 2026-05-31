from .base import BaseDownloader
from typing import Dict
import os
import base64
import yt_dlp
import asyncio
import socket


def _tor_available() -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(('127.0.0.1', 9050))
        s.close()
        return True
    except:
        return False

TOR_PROXY = 'socks5h://127.0.0.1:9050'


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

        # try impersonation first (uses curl_cffi to look like real browser)
        configs = [
            # 0: impersonate chrome + android client
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30, 'impersonate': 'chrome',
             'format': 'worst',
             'extractor_args': {'youtube': {'player_client': ['android'], 'skip': ['webpage', 'configs', 'js']}}},
            # 1: impersonate safari + android
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30, 'impersonate': 'safari',
             'format': 'worst',
             'extractor_args': {'youtube': {'player_client': ['android'], 'skip': ['webpage', 'configs', 'js']}}},
            # 2: impersonate chrome, no extractor_args
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30, 'impersonate': 'chrome',
             'format': 'worst'},
            # 3: impersonate safari, no extractor_args
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30, 'impersonate': 'safari',
             'format': 'worst'},
            # 4: impersonate edge
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30, 'impersonate': 'edge',
             'format': 'worst'},
            # 5: android client (no impersonation)
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30,
             'format': 'worst',
             'extractor_args': {'youtube': {'player_client': ['android']}}},
            # 6: tv_embedded client (no impersonation)
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30,
             'format': 'worst',
             'extractor_args': {'youtube': {'player_client': ['tv_embedded']}}},
            # 7: default yt-dlp (last resort)
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30,
             'format': 'worst'},
        ]

        # Add Tor proxy configs if Tor is running
        if _tor_available():
            print('[YT] Tor available, adding proxy configs')
            for pi, pc in enumerate(['chrome', 'safari', 'edge']):
                configs.append({'quiet': True, 'no_warnings': True, 'socket_timeout': 60,
                                'proxy': TOR_PROXY, 'impersonate': pc, 'format': 'worst'})
            configs.append({'quiet': True, 'no_warnings': True, 'socket_timeout': 60,
                            'proxy': TOR_PROXY, 'format': 'worst'})
        else:
            print('[YT] Tor not available')

        cf = self._get_cookiefile()
        if cf:
            for c in configs:
                c['cookiefile'] = cf

        for i, opts in enumerate(configs):
            try:
                imp = opts.get('impersonate', 'none')
                pc = opts.get('extractor_args', {}).get('youtube', {}).get('player_client', ['default'])
                print(f'[YT] cfg{i}: imp={imp}, pc={pc}')
                loop = asyncio.get_event_loop()

                def _sync(o):
                    with yt_dlp.YoutubeDL(o) as ydl:
                        return ydl.extract_info(url, download=False)

                info = await loop.run_in_executor(None, _sync, opts)
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
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30, 'impersonate': 'chrome',
             'format': 'worst',
             'extractor_args': {'youtube': {'player_client': ['android'], 'skip': ['webpage', 'configs', 'js']}}},
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30, 'impersonate': 'safari',
             'format': 'worst',
             'extractor_args': {'youtube': {'player_client': ['android'], 'skip': ['webpage', 'configs', 'js']}}},
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30, 'impersonate': 'chrome',
             'format': 'worst'},
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30, 'impersonate': 'safari',
             'format': 'worst'},
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30, 'impersonate': 'edge',
             'format': 'worst'},
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30,
             'format': 'worst',
             'extractor_args': {'youtube': {'player_client': ['android']}}},
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30,
             'format': 'worst',
             'extractor_args': {'youtube': {'player_client': ['tv_embedded']}}},
            {'quiet': True, 'no_warnings': True, 'socket_timeout': 30,
             'format': 'worst'},
        ]

        if _tor_available():
            for pi, pc in enumerate(['chrome', 'safari', 'edge']):
                configs.append({'quiet': True, 'no_warnings': True, 'socket_timeout': 60,
                                'proxy': TOR_PROXY, 'impersonate': pc, 'format': 'worst'})
            configs.append({'quiet': True, 'no_warnings': True, 'socket_timeout': 60,
                            'proxy': TOR_PROXY, 'format': 'worst'})

        cf = self._get_cookiefile()
        if cf:
            for c in configs:
                c['cookiefile'] = cf

        for i, opts in enumerate(configs):
            try:
                imp = opts.get('impersonate', 'none')
                pc = opts.get('extractor_args', {}).get('youtube', {}).get('player_client', ['default'])
                print(f'[YT] dl cfg{i}: imp={imp}, pc={pc}')
                outtmpl, tag = self.unique_outtmpl()
                opts['outtmpl'] = outtmpl
                if progress_queue:
                    opts['progress_hooks'] = [self.make_progress_hook(progress_queue)]

                def _sync(o):
                    with yt_dlp.YoutubeDL(o) as ydl:
                        info = ydl.extract_info(url, download=True)
                        if not info:
                            return None, 'Empty info'
                        if info.get('_type') == 'playlist' and info.get('entries'):
                            info = info['entries'][0] or info
                        title = (info.get('title') or info.get('track') or 'media')[:80]
                        path = self.resolve_downloaded_file(info, ydl, tag)
                        return (path, title) if path else (None, 'File not found')

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, _sync, opts)
                if result[0]:
                    print(f'[YT] dl cfg{i} OK')
                    return result
                print(f'[YT] dl cfg{i} fail: {result[1]}')
            except Exception as e:
                print(f'[YT] dl cfg{i} error: {e}')
                continue

        return None, 'All configs failed'
