from .base import BaseDownloader
from typing import Dict

class TwitchDownloader(BaseDownloader):

    def detect_url(self, url: str) -> bool:
        u = url.lower()
        found = 'twitch.tv' in u
        print('[TW] detect_url(%s): %s' % (url[:60], found))
        return found

    async def get_info(self, url: str) -> Dict:
        print('[TW] get_info: %s' % url[:60])
        try:
            info = await self.ytdlp_get_info(url)
            if not info:
                return {'error': 'Twitch: no info', 'formats': []}
            formats = self.parse_video_formats(info)
            title = (info.get('title') or 'Twitch')[:50]
            return {
                'platform': 'twitch',
                'title': title,
                'duration': info.get('duration', 0),
                'is_short': False,
                'formats': formats or [{'format_id': 'best', 'quality': 'Auto'}],
            }
        except Exception as e:
            return {'error': str(e)[:200], 'formats': []}

    async def download(self, url: str, fmt: str, progress_queue=None) -> tuple:
        print('[TW] download: format=%s, url=%s' % (fmt, url[:60]))
        return await self.ytdlp_download(url, fmt, progress_queue)
