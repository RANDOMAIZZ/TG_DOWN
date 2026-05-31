from abc import ABC, abstractmethod
import yt_dlp
import os
import re
import asyncio
import queue
import uuid
import glob
from pathlib import Path
from typing import Dict, List, Optional, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resolve_path(path: str) -> str:
    if not path:
        return ''
    p = Path(path)
    if p.is_absolute():
        return str(p.resolve())
    return str((PROJECT_ROOT / p).resolve())


class BaseDownloader(ABC):

    def __init__(self, temp_dir: str, cookiefile: str = ''):
        self.temp_dir = temp_dir
        self.cookiefile = cookiefile
        os.makedirs(temp_dir, exist_ok=True)
        self.user_agent = (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        )

    def resolve_cookiefile(self, path: str = None) -> Optional[str]:
        path = path if path is not None else self.cookiefile
        resolved = resolve_path(path) if path else ''
        if resolved and os.path.isfile(resolved):
            return resolved
        return None

    def unique_outtmpl(self) -> tuple:
        tag = uuid.uuid4().hex[:10]
        outtmpl = os.path.join(self.temp_dir, f'{tag}_%(id)s.%(ext)s')
        return outtmpl, tag

    @staticmethod
    def parse_video_formats(info: dict, limit: int = 12) -> List[dict]:
        seen = set()
        formats = []
        for f in info.get('formats', []):
            height = f.get('height')
            if not height or f.get('vcodec') in (None, 'none'):
                continue
            quality = f'{height}p'
            if quality in seen:
                continue
            seen.add(quality)
            formats.append({
                'format_id': f['format_id'],
                'quality': quality,
                'filesize': f.get('filesize') or f.get('filesize_approx') or 0,
            })
        formats.sort(
            key=lambda x: int(x['quality'][:-1]) if x['quality'][:-1].isdigit() else 0
        )
        return formats[:limit]

    @staticmethod
    def make_progress_hook(progress_queue):
        def hook(d):
            if d.get('status') == 'finished':
                if progress_queue:
                    try:
                        progress_queue.put_nowait({
                            'stage': 'download', 'current': 1, 'total': 1,
                            'fragment': 1, 'fragments': 1,
                        })
                    except Exception:
                        pass
                return
            if d.get('status') != 'downloading':
                return
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            fragment = d.get('fragment_index', 0) or 0
            fragments = d.get('fragment_count', 0) or 0
            speed = d.get('speed', 0) or 0
            try:
                progress_queue.put_nowait({
                    'stage': 'download',
                    'current': downloaded,
                    'total': total,
                    'fragment': fragment,
                    'fragments': fragments,
                    'speed': f'{(speed / 1024 / 1024):.1f} MB/s' if speed else '',
                    'eta': d.get('eta', 0),
                })
            except Exception:
                pass
        return hook

    def resolve_downloaded_file(self, info: dict, ydl: yt_dlp.YoutubeDL, tag: str) -> Optional[str]:
        candidates = []
        if info:
            try:
                fn = ydl.prepare_filename(info)
                candidates.append(fn)
                base, _ = os.path.splitext(fn)
                for ext in (
                    '.mp4', '.webm', '.mkv', '.m4a', '.mp3', '.opus',
                    '.ogg', '.flac', '.jpg', '.png', '.webp',
                ):
                    candidates.append(base + ext)
            except Exception as e:
                print(f"[Base] resolve_downloaded_file: prepare_filename error: {e}")

        for path in candidates:
            if path and os.path.isfile(path) and os.path.getsize(path) > 0:
                if not path.endswith(('.part', '.ytdl', '.temp')):
                    print(f"[Base] resolve_downloaded_file: найден по prepare_filename: {path}")
                    return path

        pattern = os.path.join(self.temp_dir, f'{tag}_*')
        files = [
            f for f in glob.glob(pattern)
            if os.path.isfile(f) and not f.endswith(('.part', '.ytdl', '.temp'))
        ]
        if not files:
            print(f"[Base] resolve_downloaded_file: файл не найден (tag={tag})")
            return None
        found = max(files, key=os.path.getmtime)
        print(f"[Base] resolve_downloaded_file: найден по glob: {found}")
        return found

    def build_ydl_opts(
        self,
        format_id: str = 'best',
        progress_queue: queue.Queue = None,
        audio_only: bool = False,
        extra: dict = None,
        cookiefile: str = None,
        referer: str = None,
    ) -> tuple:
        outtmpl, tag = self.unique_outtmpl()
        opts = {
            'quiet': True,
            'no_warnings': True,
            'outtmpl': outtmpl,
            'http_headers': {'User-Agent': self.user_agent},
            'retries': 3,
            'fragment_retries': 3,
            'socket_timeout': 30,
        }

        cf = self.resolve_cookiefile(cookiefile)
        if cf:
            opts['cookiefile'] = cf

        if referer:
            opts['http_headers']['Referer'] = referer

        if audio_only:
            opts['format'] = 'bestaudio/best'
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }]
            print(f"[Base] build_ydl_opts: audio_only, format={opts['format']}")
        elif format_id == 'best':
            opts['format'] = (
                'bestvideo[ext=mp4]+bestaudio[ext=m4a]/'
                'bestvideo+bestaudio/best[ext=mp4]/best'
            )
            opts['merge_output_format'] = 'mp4'
            print(f"[Base] build_ydl_opts: best, format={opts['format']}")
        else:
            opts['format'] = f'{format_id}+bestaudio/{format_id}/bestvideo+bestaudio/best[ext=mp4]/best'
            opts['merge_output_format'] = 'mp4'
            print(f"[Base] build_ydl_opts: custom format_id={format_id}, format={opts['format']}")

        if progress_queue:
            opts['progress_hooks'] = [self.make_progress_hook(progress_queue)]

        if extra:
            opts.update(extra)

        return opts, tag

    def ytdlp_download_sync(
        self,
        url: str,
        format_id: str = 'best',
        progress_queue: queue.Queue = None,
        audio_only: bool = False,
        extra: dict = None,
        cookiefile: str = None,
        referer: str = None,
        normalize_url: Callable[[str], str] = None,
        ssl_retry: bool = False,
    ) -> tuple:
        if normalize_url:
            url = normalize_url(url)
        if referer is None:
            referer = url

        extras = [extra]
        if ssl_retry:
            from .vk_session import vk_ssl_retry_extras
            extras = vk_ssl_retry_extras(extra or {})

        last_err = None
        for idx, attempt_extra in enumerate(extras):
            print(f"[Base] ytdlp_download_sync попытка {idx + 1}/{len(extras)}: format_id={format_id}, audio_only={audio_only}")
            opts, tag = self.build_ydl_opts(
                format_id, progress_queue, audio_only, attempt_extra, cookiefile, referer
            )
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    print(f"[Base] ytdlp_download_sync: запуск extract_info (download=True)...")
                    info = ydl.extract_info(url, download=True)
                    if not info:
                        print(f"[Base] ytdlp_download_sync: extract_info вернул None")
                        return None, 'Не удалось скачать'
                    if info.get('_type') == 'playlist' and info.get('entries'):
                        info = info['entries'][0] or info
                    title = (info.get('title') or info.get('track') or 'media')[:80]
                    print(f"[Base] ytdlp_download_sync: title={title}")
                    path = self.resolve_downloaded_file(info, ydl, tag)
                    if path:
                        print(f"[Base] ytdlp_download_sync: файл найден: {path}")
                        return path, title
                    print(f"[Base] ytdlp_download_sync: файл не найден после загрузки")
                    return None, title or 'Файл не найден после загрузки'
            except Exception as e:
                last_err = e
                err_s = str(e).lower()
                if ssl_retry and ('ssl' in err_s or 'eof' in err_s or 'generic' in err_s):
                    print(f'[Base] ytdlp_download_sync SSL retry после: {e}')
                    continue
                print(f'[Base] ytdlp_download_sync {url[:60]} error: {e}')
                return None, str(e)
        print(f"[Base] ytdlp_download_sync: все попытки исчерпаны")
        return None, str(last_err) if last_err else 'Не удалось скачать'

    async def ytdlp_download(self, url: str, format_id: str = 'best', progress_queue=None, **kwargs) -> tuple:
        loop = asyncio.get_event_loop()
        kw = dict(kwargs)
        return await loop.run_in_executor(
            None,
            lambda: self.ytdlp_download_sync(url, format_id, progress_queue, **kw),
        )

    def ytdlp_get_info_sync(
        self,
        url: str,
        extra: dict = None,
        cookiefile: str = None,
        referer: str = None,
        normalize_url: Callable[[str], str] = None,
        ssl_retry: bool = False,
    ) -> Optional[dict]:
        if normalize_url:
            url = normalize_url(url)

        extras = [extra]
        if ssl_retry:
            from .vk_session import vk_ssl_retry_extras
            extras = vk_ssl_retry_extras(extra or {})

        last_err = None
        for idx, attempt_extra in enumerate(extras):
            print(f"[Base] ytdlp_get_info_sync попытка {idx + 1}/{len(extras)}: {url[:60]}")
            opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'http_headers': {'User-Agent': self.user_agent},
            }
            cf = self.resolve_cookiefile(cookiefile)
            if cf:
                opts['cookiefile'] = cf
            if referer:
                opts['http_headers']['Referer'] = referer
            if attempt_extra:
                attempt = dict(attempt_extra)
                headers = attempt.pop('http_headers', None)
                if headers:
                    opts['http_headers'].update(headers)
                opts.update(attempt)

            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    print(f"[Base] ytdlp_get_info_sync: запуск extract_info (download=False)...")
                    info = ydl.extract_info(url, download=False)
                    if info:
                        formats_cnt = len(info.get('formats', []))
                        print(f"[Base] ytdlp_get_info_sync: OK, {formats_cnt} форматов")
                    else:
                        print(f"[Base] ytdlp_get_info_sync: вернул None")
                    return info
            except Exception as e:
                last_err = e
                err_s = str(e).lower()
                if ssl_retry and ('ssl' in err_s or 'eof' in err_s or 'generic' in err_s):
                    print(f'[Base] ytdlp_get_info_sync retry: {e}')
                    continue
                print(f'[Base] ytdlp_get_info_sync error: {e}')
                raise last_err
        if last_err:
            raise last_err
        return None

    async def ytdlp_get_info(self, url: str, **kwargs) -> Optional[dict]:
        loop = asyncio.get_event_loop()
        kw = dict(kwargs)
        return await loop.run_in_executor(
            None, lambda: self.ytdlp_get_info_sync(url, **kw)
        )

    @abstractmethod
    def detect_url(self, url: str) -> bool:
        pass

    @abstractmethod
    async def get_info(self, url: str) -> Dict:
        pass

    @abstractmethod
    async def download(self, url: str, format_id: str, progress_queue: queue.Queue = None) -> tuple:
        pass

    @staticmethod
    def find_thumbnail(media_path: str) -> Optional[str]:
        base = os.path.splitext(media_path)[0]
        for ext in ('.jpg', '.jpeg', '.png', '.webp'):
            thumb = base + ext
            if os.path.exists(thumb):
                return thumb
        return None

    @staticmethod
    def parse_artist_title(info: dict, filename: str = '') -> tuple:
        """(artist, title) из info или filename."""
        artist = info.get('artist', '') or ''
        title = info.get('title', '') or ''
        if artist and title:
            return artist.strip(), title.strip()
        raw = title or filename or ''
        m = re.match(r'^(.+?)\s*[-–—]\s*(.+)$', raw.strip())
        if m:
            return m.group(1).strip(), m.group(2).strip()
        return '', raw.strip()

    @staticmethod
    def fetch_lyrics_sync(artist: str, title: str, timeout: int = 10) -> str:
        """Поиск текста песни через lrclib.net и lyrics.ovh."""
        if not title:
            return ''
        import urllib.parse, requests as req
        text = ''

        # 1. lrclib.net — точный поиск
        if artist:
            try:
                url = f'https://lrclib.net/api/get?artist_name={urllib.parse.quote(artist)}&track_name={urllib.parse.quote(title)}'
                r = req.get(url, timeout=timeout)
                if r.status_code == 200:
                    data = r.json()
                    text = data.get('plainLyrics') or data.get('syncedLyrics') or ''
                    if text:
                        print(f"[Lyrics] lrclib: {len(text)} chars")
                        return text
            except Exception as e:
                print(f"[Lyrics] lrclib error: {e}")

        # 2. lrclib.net — поиск по запросу
        try:
            q = urllib.parse.quote(f'{artist} {title}' if artist else title)
            r = req.get(f'https://lrclib.net/api/search?q={q}', timeout=timeout)
            if r.status_code == 200:
                results = r.json()
                if results:
                    text = results[0].get('plainLyrics') or results[0].get('syncedLyrics') or ''
                    if text:
                        print(f"[Lyrics] lrclib search: {len(text)} chars")
                        return text
        except Exception as e:
            print(f"[Lyrics] lrclib search error: {e}")

        # 3. lyrics.ovh
        if artist:
            try:
                url = f'https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}'
                r = req.get(url, timeout=timeout)
                if r.status_code == 200:
                    text = r.json().get('lyrics', '')
                    if text:
                        print(f"[Lyrics] lyrics.ovh: {len(text)} chars")
                        return text
            except Exception as e:
                print(f"[Lyrics] lyrics.ovh error: {e}")

        return text
