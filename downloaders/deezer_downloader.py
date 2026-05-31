from .base import BaseDownloader
import os
import re
import uuid
import asyncio
import zipfile
from typing import Dict, Optional

from deezer import Deezer, TrackFormats
from deemix import generateDownloadObject
from deemix.downloader import Downloader
from deemix.itemgen import GenerationError
from deemix.settings import load as loadSettings
from deemix.utils import formatListener
import deemix.utils.localpaths as localpaths


class DeezerDownloader(BaseDownloader):

    def __init__(self, temp_dir: str, arl: str = ''):
        super().__init__(temp_dir)
        self.arl = arl
        self._cached_info = None
        self._dz = None

    def detect_url(self, url: str) -> bool:
        found = 'deezer.com' in url.lower()
        print(f"[DZ] detect_url({url[:60]}): {found}")
        return found

    def _normalize_url(self, url: str) -> str:
        url = url.replace('http://', 'https://')
        return url

    def _get_dz(self) -> Optional[Deezer]:
        if self._dz and self._dz.logged_in:
            print(f"[DZ] _get_dz: уже залогинен")
            return self._dz
        if not self.arl:
            print(f"[DZ] _get_dz: ARL не задан")
            return None
        print(f"[DZ] _get_dz: логинимся через ARL...")
        dz = Deezer()
        if dz.login_via_arl(self.arl.strip()):
            print(f"[DZ] _get_dz: успешно")
            self._dz = dz
            return dz
        print(f"[DZ] _get_dz: не удалось залогиниться по ARL")
        return None

    def _deemix_settings(self) -> dict:
        settings = loadSettings(localpaths.getConfigFolder())
        settings['downloadLocation'] = self.temp_dir
        settings['overwriteFile'] = 'skip'
        settings['createAlbumFolder'] = False
        settings['createArtistFolder'] = False
        settings['createCDFolder'] = False
        settings['createSingleFolder'] = True
        settings['createPlaylistFolder'] = False
        return settings

    async def get_info(self, url: str) -> Dict:
        url = self._normalize_url(url)
        is_album = bool(re.search(r'/album/(\d+)', url))
        print(f"[DZ] get_info: {url[:60]}, album={is_album}")

        if not re.search(r'/(track|album)/(\d+)', url):
            return {'error': 'Неверная ссылка Deezer (нужна ссылка на трек или альбом)', 'formats': []}

        if not self.arl or not self._get_dz():
            print(f"[DZ] get_info: ARL нет, пробуем preview")
            # Preview only
            track_id = self._extract_id(url, r'/track/(\d+)')
            if track_id:
                import requests
                try:
                    r = requests.get(f'https://api.deezer.com/track/{track_id}', timeout=15)
                    if r.status_code == 200:
                        data = r.json()
                        title = f"{data.get('artist', {}).get('name', 'Unknown')} - {data.get('title', 'Unknown')}"
                        print(f"[DZ] get_info preview: {title}")
                        return {
                            'platform': 'deezer',
                            'title': title[:50],
                            'duration': data.get('duration', 0),
                            'is_short': True,
                            'formats': [{'format_id': 'preview', 'quality': '30s preview (MP3)'}],
                        }
                except Exception as e:
                    print(f"[DZ] get_info preview error: {e}")
            return {'error': 'Укажите DEEZER_ARL в config.py для Deezer', 'formats': []}

        dz = self._get_dz()
        settings = self._deemix_settings()
        bitrate = TrackFormats.FLAC
        class Silent:
            @staticmethod
            def send(key, value=None): pass

        def fetch():
            try:
                objs = generateDownloadObject(dz, url, bitrate, {}, Silent)
                if not isinstance(objs, list):
                    objs = [objs]
                if not objs:
                    print(f"[DZ] get_info: generateDownloadObject вернул пустой список")
                    return None
                first = objs[0]
                title = getattr(first, 'title', getattr(first, 'id', 'Deezer'))[:50]
                print(f"[DZ] get_info: title={title}, album={'nb_tracks' in dir(first)}")
                if hasattr(first, 'nb_tracks'):
                    print(f"[DZ] get_info: альбом, {first.nb_tracks} треков")
                    return {
                        'platform': 'deezer',
                        'title': title,
                        'is_short': True,
                        'formats': [{'format_id': 'best', 'quality': f'FLAC (Album, {first.nb_tracks} треков)'}],
                    }
                print(f"[DZ] get_info: трек")
                return {
                    'platform': 'deezer',
                    'title': title,
                    'duration': getattr(first, 'duration', 0),
                    'is_short': True,
                    'formats': [{'format_id': 'best', 'quality': 'FLAC'}],
                }
            except GenerationError as e:
                print(f"[DZ] get_info GenerationError: {e}")
                return {'error': str(e), 'formats': []}
            except Exception as e:
                print(f"[DZ] get_info error: {e}")
                return {'error': str(e), 'formats': []}

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, fetch)
        if result:
            self._cached_info = result
        return result or {'error': 'Не удалось получить информацию', 'formats': []}

    @staticmethod
    def _extract_id(url: str, pattern: str) -> Optional[str]:
        m = re.search(pattern, url)
        return m.group(1) if m else None

    async def download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        url = self._normalize_url(url)
        print(f"[DZ] download: format={format_id}, url={url[:60]}")

        if format_id == 'preview':
            return await self._download_preview(url)

        dz = self._get_dz()
        if not dz:
            return None, 'Укажите DEEZER_ARL в config.py для скачивания'

        tag = uuid.uuid4().hex[:8]
        settings = self._deemix_settings()
        settings['downloadLocation'] = self.temp_dir
        settings['createSingleFolder'] = False

        class ProgressListener:
            def __init__(self, q):
                self.q = q
                self.current = 0
                self.total = 0
            def send(self, key, value=None):
                if key == 'download_start':
                    if value:
                        self.total = getattr(value, 'size', 0) or 0
                        self.current = 0
                        if self.q:
                            print(f"[DZ] download_start: total={self.total}")
                elif key == 'download_progress':
                    self.current = value or 0
                    if self.q and self.total > 0:
                        try:
                            self.q.put_nowait({
                                'stage': 'download', 'current': int(self.current), 'total': int(self.total),
                                'fragment': 1, 'fragments': 1, 'speed': '',
                            })
                        except Exception:
                            pass
                elif key == 'download_finish_success':
                    print(f"[DZ] download_finish_success")
                    if self.q:
                        try:
                            self.q.put_nowait({
                                'stage': 'download', 'current': 1, 'total': 1,
                                'fragment': 1, 'fragments': 1, 'speed': '',
                            })
                        except Exception:
                            pass

        listener = ProgressListener(progress_queue)

        def _sync():
            try:
                objs = generateDownloadObject(dz, url, TrackFormats.FLAC, {}, listener)
                if not isinstance(objs, list):
                    objs = [objs]
                if not objs:
                    print(f"[DZ] download: generateDownloadObject вернул пустой список")
                    return None, 'Не удалось создать объект загрузки'
                is_album = len(objs) > 1 or (hasattr(objs[0], 'nb_tracks') and objs[0].nb_tracks > 1)
                print(f"[DZ] download: {'альбом' if is_album else 'трек'}, {len(objs)} объектов")

                for obj in objs:
                    print(f"[DZ] download: запускаем Downloader для {getattr(obj, 'id', '?')}")
                    Downloader(dz, obj, settings, listener).start()

                # Collect downloaded files
                downloaded = []
                for f in os.listdir(self.temp_dir):
                    fp = os.path.join(self.temp_dir, f)
                    if os.path.isfile(fp) and not f.endswith(('.part', '.ytdl', '.temp')):
                        downloaded.append(fp)

                print(f"[DZ] download: {len(downloaded)} файлов во временной папке")

                if not downloaded:
                    return None, 'Файл не найден после скачивания'

                title = (getattr(objs[0], 'title', None) or
                         getattr(objs[0], 'artist', '') + ' - ' + getattr(objs[0], 'title', '') or
                         'Deezer')[:50]

                if is_album and len(downloaded) > 1:
                    zip_name = os.path.join(self.temp_dir, f'deezer_{tag}_album.zip')
                    print(f"[DZ] download: архивируем альбом в {zip_name}")
                    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
                        for fp in downloaded:
                            if fp.endswith('.flac'):
                                zf.write(fp, os.path.basename(fp))
                                os.remove(fp)
                    return zip_name, title

                for fp in downloaded:
                    if fp.endswith('.flac'):
                        print(f"[DZ] download: FLAC файл: {fp}")
                        return fp, title
                print(f"[DZ] download: возвращаем первый файл: {downloaded[0]}")
                return downloaded[0], title

            except GenerationError as e:
                print(f"[DZ] download GenerationError: {e}")
                return None, str(e)
            except Exception as e:
                print(f"[DZ] download error: {e}")
                return None, str(e)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync)

    async def _download_preview(self, url: str) -> tuple:
        import requests
        track_id = self._extract_id(url, r'/track/(\d+)')
        if not track_id:
            return None, 'Неверная ссылка'
        print(f"[DZ] _download_preview: track_id={track_id}")
        r = requests.get(f'https://api.deezer.com/track/{track_id}', timeout=15)
        if r.status_code != 200:
            return None, 'Трек не найден'
        info = r.json()
        title = f"{info.get('artist', {}).get('name', 'Unknown')} - {info.get('title', 'Unknown')}"
        safe = re.sub(r'[\\/*?:"<>|]', '', title)[:100]
        filename = os.path.join(self.temp_dir, f"{safe}.mp3")
        preview_url = info.get('preview', '')
        if not preview_url:
            return None, 'Превью недоступно'
        print(f"[DZ] _download_preview: скачиваем preview...")
        r2 = requests.get(preview_url, timeout=30)
        with open(filename, 'wb') as f:
            f.write(r2.content)
        if os.path.getsize(filename) > 0:
            print(f"[DZ] _download_preview: OK, {os.path.getsize(filename)} байт")
            return filename, title
        return None, 'Превью недоступно'
