from .base import BaseDownloader
from typing import Dict


class InstagramDownloader(BaseDownloader):

    def __init__(self, temp_dir: str, cookiefile: str = ''):
        super().__init__(temp_dir, cookiefile)

    def detect_url(self, url: str) -> bool:
        u = url.lower()
        found = 'instagram.com' in u or 'instagr.am' in u
        print(f"[IG] detect_url({url[:60]}): {found}")
        return found

    async def get_info(self, url: str) -> Dict:
        print(f"[IG] get_info: {url[:60]}, cookiefile={self.cookiefile}")
        try:
            info = await self.ytdlp_get_info(url, cookiefile=self.cookiefile)
            if not info:
                print(f"[IG] get_info: yt-dlp вернул None")
                return {'error': 'Не удалось получить информацию', 'formats': []}

            title = info.get('title') or info.get('display_id') or 'Instagram'
            print(f"[IG] get_info: title={str(title)[:50]}, duration={info.get('duration', 0)}s")
            return {
                'platform': 'instagram',
                'title': str(title)[:50],
                'duration': info.get('duration', 0),
                'is_short': True,
                'formats': [{'format_id': 'best', 'quality': 'Auto'}],
            }
        except Exception as e:
            err = str(e).lower()
            print(f"[IG] get_info error: {e}")
            if 'login' in err or 'private' in err or 'cookie' in err:
                return {
                    'error': 'Нужны cookies Instagram (cookies/instagram.txt)',
                    'formats': [],
                }
            return {'error': str(e)[:150], 'formats': []}

    async def download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        print(f"[IG] download: format={format_id}, url={url[:60]}")
        result = await self.ytdlp_download(
            url, format_id, progress_queue, cookiefile=self.cookiefile
        )
        print(f"[IG] download result: path={'OK' if result[0] else 'FAIL'}, title={result[1][:50] if result[1] else 'None'}")
        return result
