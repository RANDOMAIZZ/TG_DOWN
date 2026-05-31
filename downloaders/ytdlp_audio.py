from .base import BaseDownloader, resolve_path
from typing import Dict
import os
import asyncio
import uuid


class YtdlpAudioDownloader(BaseDownloader):
    """Универсальный загрузчик музыки через yt-dlp (SoundCloud, Spotify и др.)."""

    platform_id = 'music'
    platform_title = 'Music'
    requires_auth = False
    auth_hint = ''

    def __init__(self, temp_dir: str, cookiefile: str = '', extra_ydl: dict = None):
        super().__init__(temp_dir, cookiefile)
        self.extra_ydl = extra_ydl or {}

    def detect_url(self, url: str) -> bool:
        return False

    def _check_auth(self) -> bool:
        if not self.requires_auth:
            return True
        ok = bool(self.resolve_cookiefile())
        print(f"[{self.platform_id}] _check_auth: {'OK' if ok else 'нет cookies'}")
        return ok

    async def get_info(self, url: str) -> Dict:
        print(f"[{self.platform_id}] get_info: {url[:60]}")
        if not self._check_auth():
            return {
                'error': self.auth_hint or 'Нужен файл cookies',
                'formats': [],
                'needs_auth': True,
            }

        try:
            info = await self.ytdlp_get_info(
                url, extra=self.extra_ydl, cookiefile=self.cookiefile
            )
            if not info:
                print(f"[{self.platform_id}] get_info: yt-dlp вернул None")
                return {'error': 'Не удалось получить информацию', 'formats': []}

            if info.get('_type') == 'playlist':
                entries = [e for e in (info.get('entries') or []) if e]
                if entries:
                    info = entries[0]
                    print(f"[{self.platform_id}] get_info: это плейлист, берём первый трек")

            title = (info.get('title') or info.get('track') or self.platform_title)[:50]
            duration = info.get('duration', 0)
            print(f"[{self.platform_id}] get_info: title={title}, duration={duration}s")
            return {
                'platform': self.platform_id,
                'title': title,
                'duration': duration,
                'is_short': True,
                'formats': [{'format_id': 'best', 'quality': 'MP3', 'filesize': 0}],
            }
        except Exception as e:
            print(f"[{self.platform_id}] get_info error: {e}")
            return {'error': str(e)[:200], 'formats': []}

    async def download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        print(f"[{self.platform_id}] download: format={format_id}, url={url[:60]}")
        if not self._check_auth():
            return None, self.auth_hint or 'Нет авторизации'
        result = await self.ytdlp_download(
            url, format_id, progress_queue,
            audio_only=True, extra=self.extra_ydl, cookiefile=self.cookiefile,
        )
        print(f"[{self.platform_id}] download result: path={'OK' if result[0] else 'FAIL'}, title={result[1][:50] if result[1] else 'None'}")
        return result


class SoundCloudDownloader(YtdlpAudioDownloader):
    platform_id = 'soundcloud'
    platform_title = 'SoundCloud'

    def detect_url(self, url: str) -> bool:
        u = url.lower()
        found = 'soundcloud.com' in u or 'on.soundcloud.com' in u
        print(f"[SC] detect_url({url[:60]}): {found}")
        return found


class YandexMusicDownloader(YtdlpAudioDownloader):
    platform_id = 'yandex_music'
    platform_title = 'Yandex Music'
    requires_auth = True
    auth_hint = (
        'Для Яндекс.Музыки положите cookies в cookies/yandex.txt '
        '(экспорт из браузера, будучи залогиненным на music.yandex.ru)'
    )

    def detect_url(self, url: str) -> bool:
        u = url.lower()
        found = (
            'music.yandex' in u
            or 'music.yandex.ru' in u
            or ('yandex.ru' in u and ('/album/' in u or '/track/' in u or '/artist/' in u))
        )
        print(f"[YM] detect_url({url[:60]}): {found}")
        return found


class SpotifyDownloader(BaseDownloader):
    platform_id = 'spotify'
    platform_title = 'Spotify'

    def detect_url(self, url: str) -> bool:
        u = url.lower()
        found = 'open.spotify.com' in u or 'spotify.com/track' in u
        print(f"[SP] detect_url({url[:60]}): {found}")
        return found

    def _scrape_spotify_meta(self, url: str) -> dict:
        import requests as req, re, json
        meta = {'title': '', 'artist': '', 'album': '', 'year': '', 'track': '', 'cover': ''}
        r = req.get(url, headers={'User-Agent': self.user_agent}, timeout=20)
        html = r.text

        mt = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html)
        if mt:
            meta['title'] = mt.group(1)
        mi = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
        if mi:
            meta['cover'] = mi.group(1)
        ma = re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', html)
        if ma:
            parts = [p.strip() for p in ma.group(1).split('\u00b7')]
            if len(parts) >= 2:
                meta['artist'] = parts[0]
                if not meta['title']:
                    meta['title'] = parts[1]

        my = re.search(r'<meta[^>]+property="music:release_date"[^>]+content="([^"]+)"', html)
        if my:
            meta['year'] = my.group(1)[:4]
        mt2 = re.search(r'<meta[^>]+property="music:album:track"[^>]+content="(\d+)"', html)
        if mt2:
            meta['track'] = mt2.group(1)

        jld = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
        if jld:
            try:
                data = json.loads(jld.group(1))
                if isinstance(data, dict):
                    if data.get('name') and not meta['title']:
                        meta['title'] = data['name']
                    if data.get('byArtist'):
                        a = data['byArtist']
                        if isinstance(a, dict) and a.get('name'):
                            meta['artist'] = a['name']
                        elif isinstance(a, list) and a and a[0].get('name'):
                            meta['artist'] = a[0]['name']
                    if data.get('album'):
                        alb = data['album']
                        if isinstance(alb, dict):
                            meta['album'] = alb.get('name', '')
                    if data.get('datePublished'):
                        meta['year'] = data['datePublished'][:4]
                    if data.get('trackNumber'):
                        meta['track'] = str(data['trackNumber'])
            except json.JSONDecodeError:
                pass

        print(f"[SP] scraped: {meta['artist']} - {meta['title']} / {meta['album']} ({meta['year']})")
        return meta

    def _fetch_lyrics(self, artist: str, title: str) -> str:
        if not artist or not title:
            return ''
        import requests as req, urllib.parse
        try:
            r = req.get(
                f'https://lrclib.net/api/get?artist_name={urllib.parse.quote(artist)}&track_name={urllib.parse.quote(title)}',
                timeout=15,
            )
            if r.status_code != 200:
                return ''
            data = r.json()
            lyrics = data.get('plainLyrics') or data.get('syncedLyrics') or ''
            if lyrics:
                print(f"[SP] lyrics fetched ({len(lyrics)} chars)")
            return lyrics
        except Exception as e:
            print(f"[SP] lyrics fetch skip: {e}")
            return ''

    def _enrich_metadata(self, filepath: str, meta: dict, lyrics: str = ''):
        try:
            from mutagen.flac import FLAC, Picture
            import requests as req
            audio = FLAC(filepath)

            changed = False
            mapping = {'TITLE': 'title', 'ARTIST': 'artist', 'ALBUM': 'album', 'DATE': 'year', 'TRACKNUMBER': 'track'}
            for tag, key in mapping.items():
                val = meta.get(key)
                if not val:
                    continue
                if tag not in audio or not audio[tag][0]:
                    audio[tag] = val
                    changed = True

            if lyrics:
                audio['LYRICS'] = lyrics
                changed = True

            if meta.get('cover') and not audio.pictures:
                img_data = req.get(meta['cover'], timeout=15).content
                pic = Picture()
                pic.type = 3
                pic.mime = 'image/jpeg'
                pic.desc = 'Cover'
                pic.data = img_data
                audio.add_picture(pic)
                changed = True
                print(f"[SP] cover embedded: {len(img_data)} bytes")

            if changed:
                audio.save()
                print(f"[SP] metadata written")
        except Exception as e:
            print(f"[SP] metadata enrich skip: {e}")

    def _download_via_spotiflac(self, url: str, output_dir: str, progress_queue=None) -> tuple:
        from SpotiFLAC import SpotiFLAC as _spotiflac
        from working_sites_manager import patch_tidal_apis, install_success_hook, flush_good_urls, patch_spotify_metadata
        patch_tidal_apis()
        patch_spotify_metadata()
        install_success_hook()
        import time, os, re, sys

        class _Capture:
            _buf = ''
            _prog_re = re.compile(r'(\d+(?:\.\d+)?)\s*%\s*(?:\s+(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*(KB|MB|GB))?')
            _svc_re = re.compile(r'(?:📡|service|using)\s*[:\-]?\s*(\S+)', re.I)
            _last_send = 0
            _service = ''
            encoding = sys.__stderr__.encoding or 'utf-8'
            def write(self, text, q=progress_queue):
                sys.__stderr__.write(text)
                if q is None:
                    return
                self._buf += text
                if '\r' in self._buf or '\n' in self._buf:
                    lines = re.split(r'[\r\n]+', self._buf)
                    self._buf = lines[-1]
                    for line in lines[:-1]:
                        self._check_line(line, q)
            def _check_line(self, line, q):
                clean = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', line).strip()
                if not clean:
                    return
                sm = self._svc_re.search(clean)
                if sm:
                    self._service = sm.group(1)
                m = self._prog_re.search(clean)
                if m:
                    pct = float(m.group(1))
                    cur_b = float(m.group(2)) if m.group(2) else 0
                    total_b = float(m.group(3)) if m.group(3) else 0
                    unit = m.group(4) or ''
                    mult = {'KB': 1024, 'MB': 1024**2, 'GB': 1024**3}.get(unit, 1)
                    now = time.time()
                    if now - self._last_send >= 1.0 or pct >= 100:
                        self._last_send = now
                        q.put({
                            'stage': 'download',
                            'current': int(cur_b * mult) if cur_b else int(pct),
                            'total': int(total_b * mult) if total_b else 100,
                            'speed': f'{m.group(2) or ""}/{m.group(3) or ""} {unit}'.strip('/ ') if m.group(2) else f'{pct:.0f}%',
                            'service': self._service,
                        })
            def flush(self):
                sys.__stderr__.flush()
            def isatty(self):
                return True

        before = set(os.listdir(output_dir))
        print(f"[SP] SpotiFLAC: запуск...")
        cap = _Capture()
        sys.stderr = cap
        try:
            _spotiflac(
                url=url,
                output_dir=output_dir,
                services=["tidal", "qobuz", "deezer", "amazon"],
                quality="LOSSLESS",
                log_level=30,
                embed_lyrics=False,
                enrich_metadata=False,
                use_artist_subfolders=False,
                use_album_subfolders=False,
                filename_format="{artist} - {title}",
            )
        finally:
            sys.stderr = sys.__stderr__

        after = set(os.listdir(output_dir))
        new_files = after - before
        flac_files = [f for f in new_files if f.endswith('.flac')]
        if not flac_files:
            mp3_files = [f for f in new_files if f.endswith(('.mp3', '.m4a', '.opus', '.ogg'))]
            if mp3_files:
                flac_files = mp3_files
        if not flac_files:
            flush_good_urls()
            return None, 'Файл не найден после SpotiFLAC'

        best = max((os.path.join(output_dir, f) for f in flac_files), key=os.path.getmtime)
        title_part = os.path.splitext(os.path.basename(best))[0]
        print(f"[SP] SpotiFLAC OK: {best}")
        flush_good_urls()
        return best, title_part[:80]

    async def get_info(self, url: str) -> Dict:
        print(f"[SP] get_info: {url[:60]}")
        try:
            meta = self._scrape_spotify_meta(url)
            display = f"{meta['artist']} - {meta['title']}" if meta['artist'] and meta['title'] else (meta['title'] or 'Spotify Track')
            return {
                'platform': 'spotify',
                'title': display[:80],
                'duration': 0,
                'is_short': True,
                'formats': [{'format_id': 'best', 'quality': 'FLAC'}],
                'artist': meta['artist'],
                'track': meta['title'],
            }
        except Exception as e:
            print(f"[SP] get_info error: {e}")
            return {'error': str(e)[:200], 'formats': []}

    async def download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        print(f"[SP] download: format={format_id}, url={url[:60]}")
        loop = asyncio.get_event_loop()
        tag = uuid.uuid4().hex[:10]
        out_dir = os.path.join(self.temp_dir, f'spoti_{tag}')
        os.makedirs(out_dir, exist_ok=True)
        path = title = None
        try:
            meta = self._scrape_spotify_meta(url)
            result = await loop.run_in_executor(
                None, lambda: self._download_via_spotiflac(url, out_dir, progress_queue)
            )
            path, title = result
            if path and os.path.isfile(path):
                import shutil
                lyrics = self._fetch_lyrics(meta.get('artist', ''), meta.get('title', ''))
                self._enrich_metadata(path, meta, lyrics)
                fname = os.path.basename(path)
                dest = os.path.join(self.temp_dir, fname)
                dest = self._resolve_unique(dest)
                shutil.move(path, dest)
                print(f"[SP] download OK: {dest}")
                return dest, title, lyrics
            return None, title or 'Ошибка SpotiFLAC', ''
        except Exception as e:
            print(f"[SP] download error: {e}")
            return None, str(e)[:200], ''
        finally:
            try:
                import shutil
                shutil.rmtree(out_dir, ignore_errors=True)
            except Exception:
                pass

    def _resolve_unique(self, path: str) -> str:
        if not os.path.exists(path):
            return path
        base, ext = os.path.splitext(path)
        n = 1
        while True:
            p = f"{base} ({n}){ext}"
            if not os.path.exists(p):
                return p
            n += 1
