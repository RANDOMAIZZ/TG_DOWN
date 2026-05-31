from .base import BaseDownloader
from typing import Dict
import re
import requests
import os
import json
import asyncio


class PinterestDownloader(BaseDownloader):

    def detect_url(self, url: str) -> bool:
        u = url.lower()
        found = 'pinterest.com' in u or 'pin.it' in u
        print(f"[Pin] detect_url({url[:60]}): {found}")
        return found

    def _resolve_short_url(self, url: str) -> str:
        if 'pin.it' in url.lower():
            try:
                resp = requests.head(url, allow_redirects=True, timeout=10)
                if resp.url:
                    print(f"[Pin] _resolve_short_url: {url} -> {resp.url[:80]}")
                    return resp.url
            except Exception as e:
                print(f"[Pin] _resolve_short_url error: {e}")
        return url

    def _extract_pin_id(self, url: str) -> str:
        m = re.search(r'/pin/(?:[\w-]+--)?(\d+)', url)
        pid = m.group(1) if m else None
        print(f"[Pin] _extract_pin_id: {pid or 'not found'}")
        return pid

    async def get_info(self, url: str) -> Dict:
        print(f"[Pin] get_info: {url[:60]}")

        # Try yt-dlp for video pins first
        try:
            info = await self.ytdlp_get_info(url)
            if info and info.get('formats'):
                title = (info.get('title') or 'Pinterest')[:50]
                print(f"[Pin] get_info: yt-dlp нашёл видео: {title}")
                return {
                    'platform': 'pinterest',
                    'title': title,
                    'duration': info.get('duration', 0),
                    'is_short': True,
                    'formats': [{'format_id': 'best', 'quality': 'Auto'}],
                }
            print(f"[Pin] get_info: yt-dlp не дал форматов, пробуем как картинку")
        except Exception as e:
            print(f"[Pin] get_info: yt-dlp не сработал ({e}), пробуем как картинку")

        # Image pin fallback
        try:
            loop = asyncio.get_event_loop()
            image_url, title = await loop.run_in_executor(
                None, lambda: self._fetch_image_data(url)
            )
            if not image_url:
                print(f"[Pin] get_info: не удалось найти изображение: {title}")
                return {'error': title or 'Не удалось найти изображение', 'formats': []}
            print(f"[Pin] get_info: найдено изображение: {title}")
            return {
                'platform': 'pinterest',
                'title': title,
                'duration': 0,
                'is_short': True,
                'formats': [{'format_id': 'image', 'quality': 'Image'}],
            }
        except Exception as e:
            print(f"[Pin] get_info error: {e}")
            return {'error': str(e)[:150], 'formats': []}

    def _fetch_image_data(self, url: str) -> tuple:
        """(image_url, title) or (None, error_msg)"""
        resolved = self._resolve_short_url(url)
        pin_id = self._extract_pin_id(resolved)
        if not pin_id:
            return None, 'Не удалось определить ID пина'

        api_data = json.dumps({
            'options': {
                'field_set_key': 'unauth_react_main_pin',
                'id': pin_id,
            },
        })
        resp = requests.get(
            'https://www.pinterest.com/resource/PinResource/get/',
            params={'data': api_data},
            headers={
                'User-Agent': self.user_agent,
                'X-Pinterest-PWS-Handler': 'www/[username].js',
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()['resource_response']['data']

        images = data.get('images', {})
        image_url = None
        for key in ('orig', '736x', '564x', '236x'):
            img = images.get(key)
            if isinstance(img, dict) and img.get('url'):
                image_url = img['url']
                break
        if not image_url:
            for img in images.values():
                if isinstance(img, dict) and img.get('url'):
                    image_url = img['url']
                    break

        title = data.get('title') or data.get('grid_title') or 'Pinterest'
        print(f"[Pin] _fetch_image_data: url={'found' if image_url else 'None'}, title={title[:50]}")
        return image_url, str(title)[:50]

    async def download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        print(f"[Pin] download: format={format_id}, url={url[:60]}")
        if format_id == 'image':
            loop = asyncio.get_event_loop()
            image_url, title = await loop.run_in_executor(
                None, lambda: self._fetch_image_data(url)
            )
            if not image_url:
                print(f"[Pin] download: не удалось скачать изображение")
                return None, title or 'Не удалось скачать изображение'

            import uuid
            tag = uuid.uuid4().hex[:10]
            ext = os.path.splitext(image_url.split('?')[0])[1] or '.jpg'
            out = os.path.join(self.temp_dir, f'{tag}_pin{ext}')

            r = requests.get(
                image_url,
                headers={'User-Agent': self.user_agent},
                timeout=30,
                stream=True,
            )
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
                                progress_queue.put_nowait({
                                    'stage': 'download', 'current': downloaded, 'total': total,
                                    'fragment': 1, 'fragments': 1, 'speed': '',
                                })
                            except Exception:
                                pass
            if progress_queue:
                try:
                    progress_queue.put_nowait({
                        'stage': 'download', 'current': 1, 'total': 1,
                        'fragment': 1, 'fragments': 1, 'speed': '',
                    })
                except Exception:
                    pass
            print(f"[Pin] download: изображение сохранено: {out}")
            return out, title

        result = await self.ytdlp_download(url, format_id, progress_queue)
        print(f"[Pin] download result: path={'OK' if result[0] else 'FAIL'}, title={result[1][:50] if result[1] else 'None'}")
        return result
