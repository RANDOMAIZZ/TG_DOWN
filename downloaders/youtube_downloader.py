from .base import BaseDownloader
from typing import Dict, Optional
import os
import base64
import requests
import yt_dlp
import asyncio
import uuid


YT_COOKIES_PATH = '/tmp/yt_cookies.txt'
COBALT_API = os.environ.get('COBALT_API', 'https://api.cobalt.tools')


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

    def _build_opts(self, download: bool = False):
        opts = {
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'format': 'worst[ext=mp4]/worst',
            'ignore_no_formats_error': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'android_creator', 'tv_embedded', 'web_creator'],
                    'skip': ['webpage', 'configs'],
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36',
            },
        }
        cf = self._get_cookiefile()
        if cf:
            opts['cookiefile'] = cf
        return opts

    def detect_url(self, url: str) -> bool:
        u = url.lower()
        found = 'youtube.com' in u or 'youtu.be' in u
        print(f'[YT] detect_url({url[:60]}): {found}')
        return found

    async def get_info(self, url: str) -> Dict:
        is_short = '/shorts/' in url.lower()
        print(f'[YT] get_info: {url[:60]} (shorts={is_short})')

        # try cobalt first
        cobalt_info = await self._cobalt_get_info(url)
        if cobalt_info:
            cobalt_info['is_short'] = is_short
            return cobalt_info

        # try yt-dlp with multiple approaches
        for approach in range(3):
            try:
                opts = self._build_opts()
                if approach == 1:
                    opts['extractor_args']['youtube']['player_client'] = ['android', 'android_creator']
                    opts['extractor_args']['youtube']['skip'] = ['webpage', 'configs', 'js']
                elif approach == 2:
                    opts['extractor_args']['youtube']['player_client'] = ['tv_embedded', 'web_creator']
                    opts['format'] = 'worst/worst[ext=mp4]'

                def _sync():
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(url, download=False)

                loop = asyncio.get_event_loop()
                info = await loop.run_in_executor(None, _sync)

                if info:
                    title = info.get('title', 'video')
                    duration = info.get('duration', 0)
                    print(f'[YT] get_info success: title={title[:50]}, duration={duration}s')

                    if is_short:
                        return {
                            'platform': 'youtube_shorts', 'title': title,
                            'duration': duration, 'is_short': True,
                            'formats': [{'format_id': 'best', 'quality': 'Auto'}],
                            'artist': info.get('artist') or info.get('channel', '') or info.get('uploader', ''),
                            'track': info.get('track') or title,
                        }

                    formats = self.parse_video_formats(info)
                    print(f'[YT] get_info: {len(formats)} formats')
                    return {
                        'platform': 'youtube', 'title': title,
                        'duration': duration, 'is_short': False,
                        'formats': formats or [{'format_id': 'best', 'quality': 'Auto'}],
                    }
            except Exception as e:
                print(f'[YT] approach {approach} failed: {e}')
                continue

        return {'error': 'All approaches failed', 'formats': []}

    async def download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        print(f'[YT] download: format={format_id}, url={url[:60]}')

        # try cobalt first
        result = await self._cobalt_download(url, format_id, progress_queue)
        if result[0]:
            return result

        print('[YT] download: cobalt failed, trying yt-dlp')

        for approach in range(3):
            try:
                opts = self._build_opts(download=True)
                if approach == 1:
                    opts['extractor_args']['youtube']['player_client'] = ['android', 'android_creator']
                    opts['extractor_args']['youtube']['skip'] = ['webpage', 'configs', 'js']
                elif approach == 2:
                    opts['extractor_args']['youtube']['player_client'] = ['tv_embedded', 'web_creator']
                    opts['format'] = 'worst/worst[ext=mp4]'

                outtmpl, tag = self.unique_outtmpl()
                opts['outtmpl'] = outtmpl
                if progress_queue:
                    opts['progress_hooks'] = [self.make_progress_hook(progress_queue)]

                def _sync():
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        if not info:
                            return None, 'Empty info'
                        if info.get('_type') == 'playlist' and info.get('entries'):
                            info = info['entries'][0] or info
                        title = (info.get('title') or info.get('track') or 'media')[:80]
                        path = self.resolve_downloaded_file(info, ydl, tag)
                        if path:
                            return path, title
                        return None, 'File not found'

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, _sync)
                if result[0]:
                    print(f'[YT] download success: {result[1][:40]}')
                    return result
                print(f'[YT] approach {approach} failed: {result[1]}')
            except Exception as e:
                print(f'[YT] download approach {approach} error: {e}')
                continue

        return None, 'All approaches failed'

    # -- Cobalt API --

    async def _cobalt_get_info(self, url: str) -> Dict:
        print(f'[YT] cobalt: get_info {url[:60]}')
        try:
            resp = requests.post(
                f'{COBALT_API}/',
                json={'url': url, 'downloadMode': 'auto'},
                headers={
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'User-Agent': self.user_agent,
                    'Origin': 'https://cobalt.tools',
                    'Referer': 'https://cobalt.tools/',
                },
                timeout=15,
            )
            if resp.status_code != 200:
                print(f'[YT] cobalt: status {resp.status_code}')
                return None
            data = resp.json()
            status = data.get('status')
            print(f'[YT] cobalt: status={status}')
            if status == 'error':
                return None
            if status in ('tunnel', 'redirect'):
                filename = data.get('filename', 'video.mp4')
                title = os.path.splitext(filename)[0]
                return {
                    'platform': 'youtube',
                    'title': title,
                    'duration': 0,
                    'is_short': False,
                    'formats': [{'format_id': 'best', 'quality': 'Auto'}],
                    '_cobalt_url': data.get('url'),
                    '_cobalt_filename': filename,
                }
            if status == 'picker':
                items = data.get('picker', [])
                if items and items[0].get('type') == 'video':
                    return {
                        'platform': 'youtube',
                        'title': 'YouTube Video',
                        'duration': 0,
                        'is_short': False,
                        'formats': [{'format_id': 'best', 'quality': 'Auto'}],
                        '_cobalt_url': items[0].get('url'),
                        '_cobalt_filename': 'video.mp4',
                    }
            return None
        except Exception as e:
            print(f'[YT] cobalt get_info error: {e}')
            return None

    async def _cobalt_download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        print(f'[YT] cobalt: download {url[:60]}')
        try:
            body = {'url': url, 'downloadMode': 'audio' if format_id == 'audio_only' else 'auto'}
            if format_id == 'audio_only':
                body['audioFormat'] = 'mp3'
            resp = requests.post(
                f'{COBALT_API}/',
                json=body,
                headers={
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'User-Agent': self.user_agent,
                    'Origin': 'https://cobalt.tools',
                    'Referer': 'https://cobalt.tools/',
                },
                timeout=30,
            )
            if resp.status_code != 200:
                print(f'[YT] cobalt download: status {resp.status_code}')
                return None, f'Cobalt status {resp.status_code}'
            data = resp.json()
            status = data.get('status')
            print(f'[YT] cobalt download: status={status}')
            if status == 'error':
                return None, f"Cobalt error: {data.get('error', 'unknown')}"
            if status == 'tunnel':
                return await self._cobalt_fetch(data.get('url'), data.get('filename', 'video.mp4'), progress_queue)
            if status == 'redirect':
                return await self._cobalt_fetch(data.get('url'), data.get('filename', 'video.mp4'), progress_queue)
            if status == 'picker':
                for item in data.get('picker', []):
                    if item.get('type') == 'video':
                        return await self._cobalt_fetch(item['url'], 'video.mp4', progress_queue)
                return None, 'No video in picker'
            return None, f'Unknown cobalt status: {status}'
        except Exception as e:
            print(f'[YT] cobalt download error: {e}')
            return None, str(e)

    async def _cobalt_fetch(self, url: str, filename: str, progress_queue=None) -> tuple:
        loop = asyncio.get_event_loop()
        def _sync():
            tag = uuid.uuid4().hex[:10]
            ext = os.path.splitext(filename)[1] or '.mp4'
            out = os.path.join(self.temp_dir, f'{tag}{ext}')
            r = requests.get(url, stream=True, timeout=120, headers={'User-Agent': self.user_agent})
            r.raise_for_status()
            total = int(r.headers.get('content-length', 0))
            downloaded = 0
            with open(out, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_queue and total > 0:
                            try:
                                loop.call_soon_threadsafe(
                                    progress_queue.put_nowait, {
                                        'stage': 'download', 'current': downloaded, 'total': total,
                                        'fragment': 1, 'fragments': 1, 'speed': '',
                                    }
                                )
                            except Exception:
                                pass
            if os.path.getsize(out) < 1024:
                os.remove(out)
                return None, 'File too small'
            title = os.path.splitext(filename)[0]
            return out, title
        result = await loop.run_in_executor(None, _sync)
        print(f'[YT] cobalt fetch: path={"OK" if result[0] else "FAIL"}')
        return result
