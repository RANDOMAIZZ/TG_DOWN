from .base import BaseDownloader
from typing import Dict, Optional
import os
import re
import requests as req


def _extract_gdrive_id(url: str) -> Optional[str]:
    m = re.search(r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)', url)
    if m:
        return m.group(1)
    m = re.search(r'id=([a-zA-Z0-9_-]{25,})', url)
    if m:
        return m.group(1)
    return None


def _is_video_ext(path: str) -> bool:
    ext = os.path.splitext(path.lower())[1]
    return ext in ('.mp4', '.webm', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.m4v', '.3gp')


class GoogleDriveDownloader(BaseDownloader):

    def detect_url(self, url: str) -> bool:
        u = url.lower()
        found = 'drive.google.com' in u or 'docs.google.com' in u
        print('[GD] detect_url(%s): %s' % (url[:60], found))
        return found

    async def get_info(self, url: str) -> Dict:
        print('[GD] get_info: %s' % url[:60])
        file_id = _extract_gdrive_id(url)
        if not file_id:
            return {'error': 'Google Drive: bad link', 'formats': []}
        try:
            info = await self.ytdlp_get_info(url)
            if info:
                formats = self.parse_video_formats(info)
                title = (info.get('title') or 'Google Drive')[:50]
                return {
                    'platform': 'gdrive',
                    'title': title,
                    'duration': info.get('duration', 0),
                    'is_short': False,
                    'formats': formats or [{'format_id': 'best', 'quality': 'Video'}],
                }
        except Exception as e:
            print('[GD] yt-dlp failed: %s' % str(e)[:100])
        fname = _gdrive_get_filename(file_id)
        if _is_video_ext(fname):
            return {
                'platform': 'gdrive',
                'title': os.path.splitext(fname)[0][:50],
                'duration': 0, 'is_short': False,
                'formats': [{'format_id': 'best', 'quality': 'Video'}],
            }
        else:
            return {
                'platform': 'gdrive_file',
                'title': fname[:50],
                'duration': 0, 'is_short': True,
                'formats': [{'format_id': 'direct', 'quality': 'Download'}],
            }

    async def download(self, url: str, fmt: str, progress_queue=None) -> tuple:
        print('[GD] download: format=%s, url=%s' % (fmt, url[:60]))
        try:
            result = await self.ytdlp_download(url, 'best', progress_queue)
            if result[0]:
                return result
        except Exception as e:
            print('[GD] yt-dlp dl failed: %s' % str(e)[:100])
        file_id = _extract_gdrive_id(url)
        if not file_id:
            return None, 'Google Drive: bad link'
        import asyncio, uuid
        tag = uuid.uuid4().hex[:10]
        fname = _gdrive_get_filename(file_id)
        outpath = os.path.join(self.temp_dir, '%s_%s' % (tag, fname))
        loop = asyncio.get_event_loop()

        def _dl():
            dl_url = 'https://drive.google.com/uc?export=download' + '&id=' + file_id
            s = req.Session()
            r = s.get(dl_url, stream=True, timeout=300, allow_redirects=True)
            if 'confirm' in r.text[:2000]:
                cm = re.search(r'name="confirm"[^>]+value="([^"]+)"', r.text)
                if cm:
                    dl_url = dl_url + '&confirm=' + cm.group(1)
                    r = s.get(dl_url, stream=True, timeout=300, allow_redirects=True)
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
            print('[GD] direct OK: %s' % path)
            return path, os.path.splitext(fname)[0][:50]
        except Exception as e:
            print('[GD] direct error: %s' % e)
            return None, str(e)[:200]


def _gdrive_get_filename(file_id: str) -> str:
    try:
        url = 'https://drive.google.com/uc?export=download' + '&id=' + file_id
        r = req.head(url, allow_redirects=True, timeout=10)
        cd = r.headers.get('Content-Disposition', '')
        m = re.search(r'filename[^;]*?=([^;]+)', cd, re.I)
        if m:
            import urllib.parse
            return urllib.parse.unquote(m.group(1).strip().strip('"').strip("'"))
    except Exception as e:
        print('[GD] filename error: %s' % e)
    return 'gdrive_file'

