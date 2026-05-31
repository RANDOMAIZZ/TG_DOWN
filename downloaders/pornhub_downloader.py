from .base import BaseDownloader
from typing import Dict
import re
import json
import os
import asyncio
import uuid
import queue


class PornhubDownloader(BaseDownloader):

    def detect_url(self, url: str) -> bool:
        u = url.lower()
        found = 'pornhub.com' in u or 'pornhub.org' in u
        return found

    def _fetch_page_sync(self, url: str) -> str:
        from curl_cffi import requests
        r = requests.get(url, impersonate='chrome131', timeout=30)
        r.raise_for_status()
        return r.text

    def _parse_flashvars(self, html: str) -> dict:
        m = re.search(r'var flashvars_\d+\s*=\s*({.*?});', html, re.DOTALL)
        if m:
            return json.loads(m.group(1))
        return {}

    def _parse_title(self, html: str) -> str:
        m = re.search(r'<title>(.*?)</title>', html, re.DOTALL)
        if m:
            title = m.group(1).strip()
            title = re.sub(r'\s*-\s*Pornhub.*$', '', title, flags=re.IGNORECASE).strip()
            return title[:80] if title else 'PornHub Video'
        return 'PornHub Video'

    async def get_info(self, url: str) -> Dict:
        print(f"[PH] get_info: {url[:60]}")

        try:
            loop = asyncio.get_event_loop()
            html = await loop.run_in_executor(None, self._fetch_page_sync, url)

            flashvars = await loop.run_in_executor(None, self._parse_flashvars, html)

            if flashvars.get('video_unavailable') == '1' or '410' in html[:1000]:
                return {'error': 'Видео недоступно (удалено или заблокировано)', 'formats': []}

            medias = flashvars.get('mediaDefinitions', [])

            if not medias:
                return {'error': 'Не удалось получить информацию о видео', 'formats': []}

            title = flashvars.get('video_title', '') or self._parse_title(html)
            duration = flashvars.get('video_duration', 0) or 0

            formats = []
            for media in medias:
                quality = media.get('quality', '')
                video_url = media.get('videoUrl', '')
                if not video_url or not quality:
                    continue
                if isinstance(quality, list):
                    continue
                label = f'{quality}p' if str(quality).isdigit() else str(quality)
                formats.append({
                    'format_id': f'ph_{quality}p' if str(quality).isdigit() else f'ph_{quality}',
                    'quality': label,
                    'url': video_url,
                    'height': int(quality) if str(quality).isdigit() else 0,
                })

            if not formats:
                return {'error': 'Нет доступных форматов', 'formats': []}

            formats.sort(key=lambda x: x.get('height', 0), reverse=True)

            return {
                'platform': 'pornhub',
                'title': str(title)[:80],
                'duration': int(duration),
                'is_short': len(formats) <= 1,
                'formats': formats,
            }

        except Exception as e:
            print(f"[PH] get_info error: {e}")
            return {'error': str(e)[:200], 'formats': []}

    async def download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        print(f"[PH] download: format={format_id}, url={url[:60]}")

        try:
            loop = asyncio.get_event_loop()
            html = await loop.run_in_executor(None, self._fetch_page_sync, url)
            flashvars = await loop.run_in_executor(None, self._parse_flashvars, html)
            medias = flashvars.get('mediaDefinitions', [])

            target_url = ''
            target_quality = ''
            for media in medias:
                vid = f'ph_{media.get("quality", "")}p'
                if vid == format_id:
                    target_url = media.get('videoUrl', '')
                    target_quality = media.get('quality', '')
                    break

            if not target_url:
                for media in medias:
                    q = media.get('quality', '')
                    if isinstance(q, list):
                        continue
                    target_url = media.get('videoUrl', '')
                    target_quality = q
                    break

            if not target_url:
                return None, 'Не удалось получить URL видео'

            title = flashvars.get('video_title', 'PornHub Video')[:80]

            # Download via yt-dlp with the direct HLS URL
            result = await self.ytdlp_download(
                target_url, 'best', progress_queue,
                referer='https://www.pornhub.com/',
            )

            if result[0] and os.path.isfile(result[0]):
                return result

            # Fallback: try direct download via requests
            ext = '.mp4'
            if '.m3u8' in target_url.lower():
                return await self._download_hls(target_url, title, progress_queue)
            out_path = os.path.join(self.temp_dir, f'ph_{uuid.uuid4().hex[:10]}{ext}')

            def _dl():
                from curl_cffi import requests
                r = requests.get(target_url, impersonate='chrome131', timeout=120, stream=True)
                r.raise_for_status()
                total = int(r.headers.get('content-length', 0))
                downloaded = 0
                with open(out_path, 'wb') as f:
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
                return out_path

            result_path = await loop.run_in_executor(None, _dl)
            if os.path.isfile(result_path) and os.path.getsize(result_path) > 0:
                return result_path, title
            return None, 'Не удалось скачать видео'

        except Exception as e:
            print(f"[PH] download error: {e}")
            return None, str(e)[:200]

    async def _download_hls(self, url: str, title: str, progress_queue) -> tuple:
        print(f"[PH] _download_hls: {url[:80]}")
        try:
            result = await self.ytdlp_download(url, 'best', progress_queue)
            return result
        except Exception as e:
            return None, f'HLS error: {e}'
