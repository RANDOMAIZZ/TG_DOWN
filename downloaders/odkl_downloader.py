from .base import BaseDownloader
from typing import Dict, Optional
import os
import asyncio
import uuid


QUALITY_LABELS = {
    'mobile': 'Mobile',
    'lowest': '144p',
    'low': '240p',
    'sd': '360p',
    'hd': '720p',
    'full': '1080p',
}


class OdklDownloader(BaseDownloader):

    def __init__(self, temp_dir: str, cookiefile: str = ''):
        super().__init__(temp_dir, cookiefile)
        self._cached_info: Optional[dict] = None
        self._cached_formats: list = []

    def detect_url(self, url: str) -> bool:
        found = 'ok.ru' in url.lower() or 'odnoklassniki.ru' in url.lower()
        print(f"[OK] detect_url({url[:60]}): {found}")
        return found

    def _extract_direct_formats(self, info: dict) -> list:
        direct_ids = {'mobile', 'lowest', 'low', 'sd', 'hd', 'full'}
        formats = []
        for f in info.get('formats', []):
            fmt_id = f.get('format_id', '')
            if fmt_id not in direct_ids:
                continue
            video_url = f.get('url', '')
            if not video_url:
                continue
            label = QUALITY_LABELS.get(fmt_id, fmt_id)
            formats.append({
                'format_id': fmt_id,
                'quality': label,
                'url': video_url,
                'height': {'full': 1080, 'hd': 720, 'sd': 480, 'low': 240, 'lowest': 144}.get(fmt_id, 0),
            })
        formats.sort(key=lambda x: x.get('height', 0), reverse=True)
        return formats

    async def get_info(self, url: str) -> Dict:
        print(f"[OK] get_info: {url[:60]}")
        try:
            info = await self.ytdlp_get_info(url)
            if not info:
                return {'error': 'Не удалось получить информацию', 'formats': []}

            self._cached_info = info
            formats = self._extract_direct_formats(info)
            self._cached_formats = formats

            title = (info.get('title') or 'OK Video')[:50]
            print(f"[OK] get_info: title={title}, duration={info.get('duration', 0)}s, formats={len(formats)}")
            return {
                'platform': 'odkl',
                'title': title,
                'duration': info.get('duration', 0),
                'is_short': False,
                'formats': formats or [{'format_id': 'best', 'quality': 'Auto'}],
            }
        except Exception as e:
            err = str(e)
            print(f"[OK] get_info error: {err[:200]}")
            return {'error': err[:200], 'formats': []}

    async def download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        print(f"[OK] download: format={format_id}, url={url[:60]}")

        if not self._cached_formats:
            info = await self.ytdlp_get_info(url)
            if not info:
                return None, 'Не удалось получить информацию'
            self._cached_formats = self._extract_direct_formats(info)

        target = next((f for f in self._cached_formats if f['format_id'] == format_id), None)
        if not target:
            target = self._cached_formats[0] if self._cached_formats else None
        if not target:
            return None, 'Нет доступных форматов'

        direct_url = target.get('url', '')
        if not direct_url:
            return None, 'Нет URL для скачивания'

        title = (self._cached_info.get('title') if self._cached_info else 'OK Video')[:80]

        q = progress_queue
        loop = asyncio.get_event_loop()

        def _sync():
            import requests
            tag = uuid.uuid4().hex[:10]
            ext = '.mp4'
            out = os.path.join(self.temp_dir, f'ok_{tag}{ext}')

            r = requests.get(
                direct_url,
                headers={'User-Agent': self.user_agent, 'Referer': 'https://ok.ru/'},
                timeout=120, stream=True, allow_redirects=True,
            )
            r.raise_for_status()

            content_type = r.headers.get('Content-Type', '')
            if 'text' in content_type.lower() or 'html' in content_type.lower():
                return None, 'HTML вместо видео'

            total = int(r.headers.get('content-length', 0))
            downloaded = 0
            with open(out, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if q and total > 0:
                            try:
                                loop.call_soon_threadsafe(
                                    q.put_nowait, {
                                        'stage': 'download', 'current': downloaded, 'total': total,
                                        'fragment': 1, 'fragments': 1, 'speed': '',
                                    }
                                )
                            except Exception:
                                pass

            if os.path.getsize(out) < 1024:
                os.remove(out)
                return None, 'Файл слишком мал'
            return out, title

        result = await loop.run_in_executor(None, _sync)
        print(f"[OK] download result: path={'OK' if result[0] else 'FAIL'}, title={result[1][:50] if result[1] else 'None'}")
        return result
