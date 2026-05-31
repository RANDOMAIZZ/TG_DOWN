from .base import BaseDownloader
from typing import Dict, Optional
import os
import re
import requests as req


def _get_yadisk_direct_url(url: str) -> Optional[str]:
    try:
        api_url = 'https://cloud-api.yandex.net/v1/disk/public/resources/download'
        r = req.get(api_url, params={'public_key': url}, timeout=15)
        if r.status_code == 200:
            return r.json().get('href')
    except Exception as e:
        print('[YD] api error: %s' % e)
    return None


def _is_video_ext(path: str) -> bool:
    ext = os.path.splitext(path.lower())[1]
    return ext in ('.mp4', '.webm', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.m4v', '.3gp')


class YandexDiskDownloader(BaseDownloader):

    def detect_url(self, url: str) -> bool:
        u = url.lower()
        found = 'yadi.sk' in u or 'disk.yandex.ru' in u or 'disk.yandex.com' in u
        print('[YD] detect_url(%s): %s' % (url[:60], found))
        return found

    async def get_info(self, url: str) -> Dict:
        print('[YD] get_info: %s' % url[:60])
        try:
            info = await self.ytdlp_get_info(url)
            if info:
                formats = self.parse_video_formats(info)
                title = (info.get('title') or 'Yandex Disk')[:50]
                return {
                    'platform': 'yandex_disk',
                    'title': title,
                    'duration': info.get('duration', 0),
                    'is_short': False,
                    'formats': formats or [{'format_id': 'best', 'quality': 'Video'}],
                }
        except Exception as e:
            print('[YD] yt-dlp failed: %s' % str(e)[:100])
        direct = _get_yadisk_direct_url(url)
        if direct:
            resp = req.head(direct, allow_redirects=True, timeout=10)
            cd = resp.headers.get('Content-Disposition', '')
            m = re.search(r'filename[^;]*?=([^;]+)', cd, re.I)
            fname = ''
            if m:
                fname = m.group(1).strip().strip('"').strip("'")
            if not fname:
                fname = 'file'
            if _is_video_ext(fname):
                return {
                    'platform': 'yandex_disk',
                    'title': os.path.splitext(fname)[0][:50],
                    'duration': 0, 'is_short': False,
                    'formats': [{'format_id': 'best', 'quality': 'Video'}],
                }
            else:
                return {
                    'platform': 'yandex_disk_file',
                    'title': fname[:50],
                    'duration': 0, 'is_short': True,
                    'formats': [{'format_id': 'direct', 'quality': 'Download'}],
                }
        return {'error': 'Yandex Disk: no info', 'formats': []}

    async def download(self, url: str, fmt: str, progress_queue=None) -> tuple:
        print('[YD] download: format=%s, url=%s' % (fmt, url[:60]))
        try:
            result = await self.ytdlp_download(url, 'best', progress_queue)
            if result[0]:
                return result
        except Exception as e:
            print('[YD] yt-dlp dl failed: %s' % str(e)[:100])
        direct = _get_yadisk_direct_url(url)
        if not direct:
            return None, 'Yandex Disk: no download link'
        import asyncio, uuid
        tag = uuid.uuid4().hex[:10]
        resp = req.head(direct, allow_redirects=True, timeout=10)
        cd = resp.headers.get('Content-Disposition', '')
        m = re.search(r'filename[^;]*?=([^;]+)', cd, re.I)
        fname = 'yadisk_' + tag
        if m:
            fname = m.group(1).strip().strip('"').strip("'")
        outpath = os.path.join(self.temp_dir, '%s_%s' % (tag, fname))
        loop = asyncio.get_event_loop()

        def _dl():
            r = req.get(direct, stream=True, timeout=300)
            r.raise_for_status()
            total = int(r.headers.get('content-length', 0))
            dl = 0
            with open(outpath, 'wb') as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
                        dl += len(chunk)
                        if progress_queue and total > 0:
                            try:
                                progress_queue.put_nowait({
                                    'stage': 'download',
                                    'current': dl, 'total': total,
                                    'fragment': 0, 'fragments': 1,
                                })
                            except Exception:
                                pass
            return outpath
        try:
            path = await loop.run_in_executor(None, _dl)
            print('[YD] direct OK: %s' % path)
            return path, os.path.splitext(fname)[0][:50]
        except Exception as e:
            print('[YD] direct error: %s' % e)
            return None, str(e)[:200]

