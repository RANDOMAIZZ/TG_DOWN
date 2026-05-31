from .base import BaseDownloader
from typing import Dict


class XVideosDownloader(BaseDownloader):

    def detect_url(self, url: str) -> bool:
        u = url.lower()
        found = 'xvideos.com' in u or 'xvideos.net' in u or 'xv-ru.com' in u
        print(f"[XV] detect_url({url[:60]}): {found}")
        return found

    async def get_info(self, url: str) -> Dict:
        print(f"[XV] get_info: {url[:60]}")
        try:
            info = await self.ytdlp_get_info(url, referer=url)
            if not info:
                print(f"[XV] get_info: yt-dlp вернул None")
                return {'error': 'Сайт недоступен', 'formats': []}
            title = (info.get('title') or 'video')[:50]
            print(f"[XV] get_info: title={title}, duration={info.get('duration', 0)}s")
            return {
                'platform': 'xvideos',
                'title': title,
                'duration': info.get('duration', 0),
                'is_short': True,
                'formats': [{'format_id': 'best', 'quality': 'Auto'}],
            }
        except Exception as e:
            print(f"[XV] get_info error: {e}")
            return {'error': str(e), 'formats': []}

    async def download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        print(f"[XV] download: format={format_id}, url={url[:60]}")
        result = await self.ytdlp_download(url, format_id, progress_queue, referer=url)
        print(f"[XV] download result: path={'OK' if result[0] else 'FAIL'}, title={result[1][:50] if result[1] else 'None'}")
        return result
