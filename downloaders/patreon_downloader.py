import os, re, json, asyncio
from downloaders.base import BaseDownloader, resolve_path

PATREON_COOKIES_DEFAULT = 'patreon_cookies.txt'

class PatreonDownloader(BaseDownloader):
    def __init__(self, temp_dir: str, cookiefile: str = ''):
        super().__init__(temp_dir, cookiefile)

    def detect_url(self, url: str) -> bool:
        u = url.lower().strip()
        return 'patreon.com' in u or 'patreon.com/posts/' in u or re.search(r'patreon\.com/(?:posts/[\w-]+-)?\d+', u) is not None

    def _get_cookiefile(self) -> str:
        cf = self.resolve_cookiefile(self.cookiefile)
        return cf if cf else ''

    def _base_cmd(self) -> list:
        cmd = ['yt-dlp', '--no-warnings']
        cf = self._get_cookiefile()
        if cf:
            cmd.extend(['--cookies', cf])
        return cmd

    async def get_info(self, url: str) -> dict:
        cmd = self._base_cmd() + ['--dump-json', url]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            raise Exception(stderr.decode(errors='replace').strip())
        try:
            return json.loads(stdout.decode(errors='replace'))
        except json.JSONDecodeError:
            raise Exception('Failed to parse yt-dlp output')

    async def download(self, url: str, fmt_id: str, progress_queue=None) -> tuple:
        outtmpl, tag = self.unique_outtmpl()
        cmd = self._base_cmd() + ['-f', fmt_id, '-o', outtmpl, url]
        if progress_queue:
            cmd.extend(['--progress-template', 'default:%(progress._percent_str)s|%(progress._speed_str)s'])

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
        if proc.returncode != 0:
            raise Exception(stderr.decode(errors='replace').strip())

        files = [f for f in os.listdir(self.temp_dir) if tag in f]
        if not files:
            raise Exception('Downloaded file not found')

        filepath = os.path.join(self.temp_dir, files[0])
        ext = os.path.splitext(filepath)[1].lstrip('.')
        return filepath, ext

    @staticmethod
    def parse_video_formats(info: dict, limit: int = 12) -> list:
        formats = []
        seen = set()
        for f in info.get('formats', []):
            fmt_id = f.get('format_id', '')
            ext = f.get('ext', '')
            height = f.get('height')
            tbr = f.get('tbr', 0)
            filesize = f.get('filesize') or f.get('filesize_approx') or 0

            key = f"{ext}_{height or 'audio'}_{tbr}"
            if key in seen:
                continue
            seen.add(key)

            label = f"{ext} | {height}p" if height else f"{ext} | audio"
            label += f" | {tbr:.0f}k" if tbr else ''
            label += f" | {filesize / 1024 / 1024:.1f}MB" if filesize else ''

            formats.append({
                'format_id': fmt_id,
                'ext': ext,
                'quality': label,
                'height': height,
                'filesize': filesize,
                'tbr': tbr,
            })
            if len(formats) >= limit:
                break
        return formats
