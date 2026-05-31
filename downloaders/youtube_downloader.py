from .base import BaseDownloader
from typing import Dict
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

        # Пробуем через cobalt сначала
        cobalt_info = await self._cobalt_get_info(url)
        if cobalt_info:
            cobalt_info['is_short'] = is_short
            return cobalt_info

        # Fallback на yt-dlp
        opts = self._base_opts()
        cf = self._get_cookiefile()
        if cf:
            opts['cookiefile'] = cf
        else:
            opts['extractor_args'] = {'youtube': {'player_client': ['android']}}

        def _sync():
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, _sync)
        except Exception as e:
            print(f"[YT] yt-dlp get_info error: {e}")
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

        # Пробуем cobalt
        result = await self._cobalt_download(url, format_id, progress_queue)
        if result[0]:
            return result

        # Fallback на yt-dlp
        print(f"[YT] download: cobalt failed, trying yt-dlp")
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

    # ── Cobalt API ──

    async def _cobalt_get_info(self, url: str) -> Dict:
        """Получить инфо через cobalt API"""
        print(f"[YT] cobalt: get_info {url[:60]}")
        try:
            resp = requests.post(
                f'{COBALT_API}/',
                json={'url': url, 'downloadMode': 'auto'},
                headers={
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                },
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"[YT] cobalt: status {resp.status_code}")
                return None

            data = resp.json()
            status = data.get('status')
            print(f"[YT] cobalt: status={status}")

            if status == 'error':
                return None

            if status in ('tunnel', 'redirect'):
                # cobalt вернул прямую ссылку — значит видео доступно
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
            print(f"[YT] cobalt get_info error: {e}")
            return None

    async def _cobalt_download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        """Скачать через cobalt API"""
        print(f"[YT] cobalt: download {url[:60]}")
        try:
            resp = requests.post(
                f'{COBALT_API}/',
                json={
                    'url': url,
                    'downloadMode': 'audio' if format_id == 'audio_only' else 'auto',
                    'audioFormat': 'mp3',
                },
                headers={
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                },
                timeout=30,
            )
            if resp.status_code != 200:
                print(f"[YT] cobalt download: status {resp.status_code}")
                return None, f'Cobalt status {resp.status_code}'

            data = resp.json()
            status = data.get('status')
            print(f"[YT] cobalt download: status={status}")

            if status == 'error':
                return None, f"Cobalt error: {data.get('error', 'unknown')}"

            # Tunnel — скачиваем через cobalt proxy
            if status == 'tunnel':
                cobalt_url = data.get('url')
                filename = data.get('filename', 'video.mp4')
                return await self._cobalt_fetch(cobalt_url, filename, progress_queue)

            # Redirect — переходим по ссылке
            if status == 'redirect':
                cobalt_url = data.get('url')
                filename = data.get('filename', 'video.mp4')
                return await self._cobalt_fetch(cobalt_url, filename, progress_queue)

            # Picker — берём первый видео
            if status == 'picker':
                items = data.get('picker', [])
                for item in items:
                    if item.get('type') == 'video':
                        return await self._cobalt_fetch(item['url'], 'video.mp4', progress_queue)
                return None, 'Нет видео в picker'

            return None, f'Неизвестный cobalt статус: {status}'
        except Exception as e:
            print(f"[YT] cobalt download error: {e}")
            return None, str(e)

    async def _cobalt_fetch(self, url: str, filename: str, progress_queue=None) -> tuple:
        """Скачать файл по URL"""
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
                return None, 'Файл слишком мал'

            title = os.path.splitext(filename)[0]
            return out, title

        result = await loop.run_in_executor(None, _sync)
        print(f"[YT] cobalt fetch: path={'OK' if result[0] else 'FAIL'}")
        return result
