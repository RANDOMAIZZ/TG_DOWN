from .base import BaseDownloader
from typing import Dict


class TwitterDownloader(BaseDownloader):

    def detect_url(self, url: str) -> bool:
        u = url.lower()
        found = ('twitter.com' in u or 'x.com' in u) and '/status/' in u
        print(f'[TWIT] detect_url({url[:60]}): {found}')
        return found

    async def get_info(self, url: str) -> Dict:
        print(f'[TWIT] get_info: {url[:60]}')
        try:
            info = await self.ytdlp_get_info(url)
            if not info:
                return {'error': 'Twitter: не удалось получить информацию', 'formats': []}
            formats = self.parse_video_formats(info)
            title = (info.get('title') or info.get('description') or 'Twitter video')[:50]
            return {
                'platform': 'twitter',
                'title': title,
                'duration': info.get('duration', 0),
                'is_short': True,
                'formats': formats or [{'format_id': 'best', 'quality': 'Auto'}],
            }
        except Exception as e:
            err = str(e)
            print(f'[TWIT] get_info error: {err[:200]}')
            return {'error': err[:200], 'formats': []}

    async def download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        print(f'[TWIT] download: format={format_id}, url={url[:60]}')
        result = await self.ytdlp_download(url, format_id, progress_queue)
        return result
