from .base import BaseDownloader
from typing import Dict


class RutubeDownloader(BaseDownloader):

    def detect_url(self, url: str) -> bool:
        found = 'rutube.ru' in url.lower()
        print(f"[RT] detect_url({url[:60]}): {found}")
        return found

    async def get_info(self, url: str) -> Dict:
        print(f"[RT] get_info: {url[:60]}")
        try:
            info = await self.ytdlp_get_info(url, extra={
                'extractor_args': {'rutube': {'skip': ['webpage']}},
            })
            if not info:
                print(f"[RT] get_info: yt-dlp вернул None")
                return {'error': 'Не удалось получить информацию', 'formats': []}

            formats = self.parse_video_formats(info)
            title = (info.get('title') or 'Rutube')[:50]
            print(f"[RT] get_info: title={title}, duration={info.get('duration', 0)}s, formats={len(formats)}")
            return {
                'platform': 'rutube',
                'title': title,
                'duration': info.get('duration', 0),
                'is_short': False,
                'formats': formats or [{'format_id': 'best', 'quality': 'Auto'}],
            }
        except Exception as e:
            err = str(e)
            print(f"[RT] get_info error: {err[:200]}")
            if '404' in err:
                return {'error': 'Видео недоступно или удалено', 'formats': []}
            if 'DRM' in err:
                return {'error': 'Видео защищено DRM', 'formats': []}
            return {'error': err[:200], 'formats': []}

    async def download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        print(f"[RT] download: format={format_id}, url={url[:60]}")
        result = await self.ytdlp_download(url, format_id, progress_queue, extra={
            'extractor_args': {'rutube': {'skip': ['webpage']}},
        })
        print(f"[RT] download result: path={'OK' if result[0] else 'FAIL'}, title={result[1][:50] if result[1] else 'None'}")
        return result
