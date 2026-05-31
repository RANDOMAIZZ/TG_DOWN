from .base import BaseDownloader
from typing import Dict, Optional
import os
import sys
import json
import glob
import asyncio
import socket
import base64


def _tor_available() -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(('127.0.0.1', 9050))
        s.close()
        return True
    except:
        return False


TOR_PROXY = 'socks5h://127.0.0.1:9050'
YT_COOKIES_PATH = '/tmp/yt_cookies.txt'


def _find_yt() -> str:
    venv_yt = os.path.join(os.path.dirname(sys.executable), 'yt-dlp')
    if os.path.isfile(venv_yt):
        return venv_yt
    import shutil
    return shutil.which('yt-dlp') or 'yt-dlp'


class YouTubeDownloader(BaseDownloader):

    def __init__(self, temp_dir: str, cookiefile: str = '', cookies_browser: str = ''):
        super().__init__(temp_dir, cookiefile)
        self.cookies_browser = cookies_browser
        self._loaded_cookies = False
        raw = os.environ.get('YOUTUBE_COOKIES')
        if raw:
            try:
                data = base64.b64decode(raw)
                with open(YT_COOKIES_PATH, 'wb') as f:
                    f.write(data)
                self.cookiefile = YT_COOKIES_PATH
                self._loaded_cookies = True
                print(f'[YT] Cookies loaded -> {YT_COOKIES_PATH} ({len(data)} bytes)')
            except Exception as e:
                print(f'[YT] Cookies error: {e}')

    def _get_cookiefile(self):
        if self._loaded_cookies and os.path.isfile(YT_COOKIES_PATH):
            return YT_COOKIES_PATH
        cf = self.resolve_cookiefile(self.cookiefile)
        return cf if cf else None

    def detect_url(self, url: str) -> bool:
        u = url.lower()
        return 'youtube.com' in u or 'youtu.be' in u

    def _base_cmd(self) -> list:
        cmd = [_find_yt(), '--remote-components', 'ejs:github', '--no-warnings']
        cf = self._get_cookiefile()
        if cf:
            cmd.extend(['--cookies', cf])
        return cmd

    async def _run_yt(self, args: list, timeout: int = 60) -> str:
        loop = asyncio.get_event_loop()
        cmd = self._base_cmd() + args
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise Exception(f'yt-dlp timeout ({timeout}s)')
        if proc.returncode != 0:
            err = stderr.decode('utf-8', errors='replace').strip()
            raise Exception(err or f'exit code {proc.returncode}')
        return stdout.decode('utf-8', errors='replace')

    def parse_video_formats(self, info: dict, limit: int = 12) -> list:
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
                'height': height,
                'width': f.get('width', 0),
                'filesize': f.get('filesize') or f.get('filesize_approx', 0),
            })
            if len(formats) >= limit:
                break
        return formats

    async def get_info(self, url: str) -> Dict:
        is_short = '/shorts/' in url.lower()
        print(f'[YT] get_info: {url[:60]}')

        configs = [
            {'args': ['--dump-json', url], 'label': 'primary'},
        ]
        if _tor_available():
            print('[YT] Tor available')
            configs.append({
                'args': ['--proxy', TOR_PROXY, '--dump-json', url],
                'label': 'tor',
            })

        last_error = ''
        for cfg in configs:
            try:
                stdout = await self._run_yt(cfg['args'])
                info = json.loads(stdout)
                title = info.get('title', 'video')
                duration = info.get('duration', 0)
                print(f'[YT] {cfg["label"]} OK: {title[:40]}')

                if is_short:
                    return {
                        'platform': 'youtube_shorts', 'title': title,
                        'duration': duration, 'is_short': True,
                        'formats': [{'format_id': 'best', 'quality': 'Auto'}],
                        'artist': info.get('artist') or info.get('channel', '') or info.get('uploader', ''),
                        'track': info.get('track') or title,
                    }

                formats = self.parse_video_formats(info)
                return {
                    'platform': 'youtube', 'title': title,
                    'duration': duration, 'is_short': False,
                    'formats': formats or [{'format_id': 'best', 'quality': 'Auto'}],
                }
            except Exception as e:
                print(f'[YT] {cfg["label"]} fail: {e}')
                last_error = str(e)

        return {'error': last_error or 'All configs failed', 'formats': []}

    async def _download_progress(self, args: list, progress_queue, timeout: int = 120) -> None:
        pt = 'json:{"s":"%(progress.status)s","d":"%(progress.downloaded_bytes)s","t":"%(progress.total_bytes)s","sp":"%(progress.speed)s","e":"%(progress.eta)s"}'
        cmd = self._base_cmd() + ['--progress-template', pt, '-q'] + args
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
        )
        loop = asyncio.get_event_loop()
        try:
            while True:
                line = await asyncio.wait_for(proc.stderr.readline(), timeout=timeout)
                if not line:
                    break
                raw = line.decode('utf-8', errors='replace').strip()
                if raw.startswith('{"s"'):
                    try:
                        data = json.loads(raw)
                        d = data.get('d', '0')
                        t = data.get('t', '0')
                        sp = data.get('sp', '0')
                        downloaded = int(d) if d not in ('None', '') else 0
                        total = int(t) if t not in ('None', '') else 0
                        speed = int(sp) if sp not in ('None', '') else 0
                        if progress_queue and total > 0:
                            progress_queue.put_nowait({
                                'stage': 'download',
                                'current': downloaded,
                                'total': total,
                                'fragment': 0,
                                'fragments': 1,
                                'speed': f'{(speed / 1024 / 1024):.1f} MB/s' if speed else '',
                            })
                    except Exception:
                        pass
            ret = await proc.wait()
        except asyncio.TimeoutError:
            proc.kill()
            raise Exception(f'yt-dlp timeout ({timeout}s)')
        if ret != 0:
            raise Exception(f'exit code {ret}')

    async def download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        print(f'[YT] download: format={format_id}, url={url[:60]}')
        outtmpl, tag = self.unique_outtmpl()

        configs = [
            {'args': ['-f', format_id, '-o', outtmpl, url], 'label': 'primary'},
        ]
        if _tor_available():
            configs.append({
                'args': ['--proxy', TOR_PROXY, '-f', format_id, '-o', outtmpl, url],
                'label': 'tor',
            })

        last_error = ''
        for cfg in configs:
            try:
                await self._download_progress(cfg['args'], progress_queue, timeout=120)
                filepath = self._find_file(tag)
                if filepath:
                    try:
                        info_stdout = await self._run_yt(['--dump-json', url])
                        info = json.loads(info_stdout)
                        title = (info.get('title') or info.get('track') or 'media')[:80]
                    except Exception:
                        title = 'video'
                    print(f'[YT] dl {cfg["label"]} OK: {filepath}')
                    return filepath, title
                last_error = 'File not found after download'
                print(f'[YT] dl {cfg["label"]} fail: file not found (tag={tag})')
            except Exception as e:
                print(f'[YT] dl {cfg["label"]} error: {e}')
                last_error = str(e)

        return None, last_error or 'All configs failed'

    def _find_file(self, tag: str) -> Optional[str]:
        pattern = os.path.join(self.temp_dir, f'{tag}_*')
        files = [f for f in glob.glob(pattern)
                 if os.path.isfile(f) and not f.endswith(('.part', '.ytdl', '.temp'))]
        if not files:
            return None
        return max(files, key=os.path.getmtime)
