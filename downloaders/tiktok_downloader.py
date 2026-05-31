from .base import BaseDownloader
from typing import Dict, Optional
import re
import json
import requests
import os
import asyncio
import uuid
import subprocess


class TikTokDownloader(BaseDownloader):

    def detect_url(self, url: str) -> bool:
        u = url.lower()
        found = 'tiktok.com' in u or 'vm.tiktok.com' in u or 'vt.tiktok.com' in u
        print(f"[TT] detect_url({url[:60]}): {found}")
        return found

    def _is_photo_url(self, url: str) -> bool:
        return '/photo/' in url.lower()

    def _resolve_short_url(self, url: str) -> str:
        short_domains = ('vm.tiktok.com', 'vt.tiktok.com')
        if any(d in url.lower() for d in short_domains):
            try:
                resp = requests.head(url, allow_redirects=True, timeout=10)
                if resp.url:
                    print(f"[TT] resolve: {url} -> {resp.url[:80]}")
                    return resp.url
            except Exception as e:
                print(f"[TT] resolve error: {e}")
        return url

    def _extract_page_data(self, url: str):
        """Scrape TikTok photo post data: image URLs + music info."""
        ua = self.user_agent
        resp = requests.get(url, headers={'User-Agent': ua}, timeout=20)
        resp.raise_for_status()
        html = resp.text

        pattern = r'<script[^>]*id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>'
        m = re.search(pattern, html, re.DOTALL)
        if not m:
            print(f"[TT] _extract_page: не найден скрипт с данными")
            return None, None

        data = json.loads(m.group(1))
        scope = data.get('__DEFAULT_SCOPE__', {})

        # Try video-detail path (some photo posts have video-detail with imagePost)
        item = scope.get('webapp.video-detail', {}).get('itemInfo', {}).get('itemStruct', {})
        if not item:
            item = scope.get('webapp.image-detail', {})

        # Images
        images = item.get('imagePost', {}).get('images', [])
        if not images:
            images = item.get('images', [])
        if not images:
            images = item.get('imageList', [])

        photo_urls = []
        for img in images:
            display = (
                img.get('displayURL')
                or img.get('imageURL', {}).get('url_list', [None])[0]
                or img.get('url_list', [None])[0]
                or img.get('downloadURL')
            )
            if display:
                if display.startswith('//'):
                    display = 'https:' + display
                elif display.startswith('/'):
                    display = 'https://www.tiktok.com' + display
                photo_urls.append(display)

        if not photo_urls:
            og = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
            if og:
                photo_urls.append(og.group(1))

        # Music
        music = item.get('music') or {}
        music_url = music.get('playUrl') or music.get('play_url', {}).get('uri', '')
        music_title = music.get('title', '')
        if music_url and music_url.startswith('//'):
            music_url = 'https:' + music_url

        print(f"[TT] _extract_page: {len(photo_urls)} фото, music={'есть' if music_url else 'нет'}")
        return (photo_urls if photo_urls else None, music_url or None)

    async def get_info(self, url: str) -> Dict:
        print(f"[TT] get_info: {url[:60]}")

        # Allways resolve short URLs first to detect photo posts
        loop = asyncio.get_event_loop()
        resolved = await loop.run_in_executor(None, lambda: self._resolve_short_url(url))

        if self._is_photo_url(resolved):
            print(f"[TT] get_info: это фото-пост (resolved={resolved[:80]})")
            try:
                photo_urls, music_url = await loop.run_in_executor(
                    None, lambda: self._extract_page_data(resolved)
                )
                if photo_urls:
                    title = f"TikTok Photo ({len(photo_urls)} фото)"
                    return {
                        'platform': 'tiktok_photo',
                        'title': title,
                        'duration': 0,
                        'is_short': True,
                        'formats': [{'format_id': 'image', 'quality': 'Video'}],
                        'photo_urls': photo_urls,
                        'music_url': music_url,
                    }
                print(f"[TT] get_info: не удалось извлечь фото из HTML")
            except Exception as e:
                print(f"[TT] get_info photo error: {e}")

        try:
            info = await self.ytdlp_get_info(resolved)
            if not info:
                print(f"[TT] get_info: yt-dlp вернул None")
                return {'error': 'Не удалось получить информацию', 'formats': []}
            title = (info.get('title') or 'TikTok')[:50]
            print(f"[TT] get_info: title={title}, duration={info.get('duration', 0)}s")
            return {
                'platform': 'tiktok',
                'title': title,
                'duration': info.get('duration', 0),
                'is_short': True,
                'formats': [{'format_id': 'best', 'quality': 'Auto'}],
            }
        except Exception as e:
            err = str(e)
            print(f"[TT] get_info error: {err[:150]}")
            if 'Unsupported URL' in err:
                return {
                    'error': 'TikTok фото не поддерживаются yt-dlp.',
                    'formats': [],
                }
            return {'error': err, 'formats': []}

    def _download_file(self, url: str, path: str):
        r = requests.get(url, headers={'User-Agent': self.user_agent}, timeout=60, stream=True)
        r.raise_for_status()
        with open(path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    def _get_audio_duration(self, path: str) -> float:
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', path],
                capture_output=True, text=True, timeout=30,
            )
            return float(result.stdout.strip()) if result.stdout.strip() else 0
        except Exception:
            return 0

    def _make_slideshow(self, image_paths: list, audio_path: str, output: str, tag: str) -> str:
        """Create video slideshow from images with audio using FFmpeg."""
        num = len(image_paths)
        if num == 0:
            return None

        # Get audio duration or default 10s per image
        total_dur = self._get_audio_duration(audio_path) if audio_path else 0
        if total_dur <= 0:
            total_dur = num * 10  # fallback: 10s per image

        per_img = total_dur / num

        # Build concat file list
        list_path = os.path.join(self.temp_dir, f'{tag}_concat.txt')
        with open(list_path, 'w', encoding='utf-8') as f:
            for img in image_paths:
                abs_img = os.path.abspath(img)
                f.write(f"file '{abs_img}'\n")
                f.write(f"duration {per_img}\n")
            last = os.path.abspath(image_paths[-1])
            f.write(f"file '{last}'\n")

        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', list_path,
            '-c:v', 'libx264',
            '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p',
            '-pix_fmt', 'yuv420p',
        ]

        if audio_path and os.path.isfile(audio_path):
            cmd += ['-i', audio_path, '-c:a', 'aac', '-shortest']
        else:
            cmd += ['-an']

        cmd += ['-movflags', '+faststart', output]

        print(f"[TT] _make_slideshow: {num} фото, per_img={per_img:.1f}s, total={total_dur:.1f}s")
        subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        os.remove(list_path)

        if os.path.isfile(output) and os.path.getsize(output) > 0:
            return output
        return None

    async def download(self, url: str, format_id: str, progress_queue=None) -> tuple:
        print(f"[TT] download: format={format_id}, url={url[:60]}")

        loop = asyncio.get_event_loop()
        resolved = await loop.run_in_executor(None, lambda: self._resolve_short_url(url))

        if format_id == 'image':
            try:
                photo_urls, music_url = await loop.run_in_executor(
                    None, lambda: self._extract_page_data(resolved)
                )
                if not photo_urls:
                    return None, 'Не удалось найти фото'

                tag = uuid.uuid4().hex[:10]
                img_dir = os.path.join(self.temp_dir, f'{tag}_imgs')
                os.makedirs(img_dir, exist_ok=True)

                total_photos = len(photo_urls)
                has_music = bool(music_url)
                total_steps = total_photos + (1 if has_music else 0) + 1
                step = 0

                if progress_queue:
                    try:
                        progress_queue.put_nowait({
                            'stage': 'download', 'current': 0, 'total': total_steps,
                            'fragment': 0, 'fragments': total_steps, 'speed': '',
                        })
                    except Exception:
                        pass

                # Download all photos
                img_paths = []
                for i, img_url in enumerate(photo_urls):
                    ext = os.path.splitext(img_url.split('?')[0])[1] or '.jpg'
                    path = os.path.join(img_dir, f'img_{i:03d}{ext}')
                    print(f"[TT] download: фото {i + 1}/{total_photos}")
                    await loop.run_in_executor(None, lambda u=img_url, p=path: self._download_file(u, p))
                    img_paths.append(path)
                    step += 1
                    if progress_queue:
                        try:
                            progress_queue.put_nowait({
                                'stage': 'download', 'current': step, 'total': total_steps,
                                'fragment': step, 'fragments': total_steps,
                                'speed': f'Фото {i+1}/{total_photos}',
                            })
                        except Exception:
                            pass

                # Download music if available
                audio_path = None
                if music_url:
                    audio_path = os.path.join(self.temp_dir, f'{tag}_audio.mp3')
                    print(f"[TT] download: скачиваю музыку...")
                    if progress_queue:
                        try:
                            progress_queue.put_nowait({
                                'stage': 'download', 'current': step, 'total': total_steps,
                                'fragment': step, 'fragments': total_steps, 'speed': 'Музыка',
                            })
                        except Exception:
                            pass
                    try:
                        await loop.run_in_executor(None, lambda: self._download_file(music_url, audio_path))
                        if not os.path.isfile(audio_path) or os.path.getsize(audio_path) < 1024:
                            audio_path = None
                    except Exception as e:
                        print(f"[TT] download: music download error: {e}")
                        audio_path = None
                    step += 1

                # Create slideshow video
                output = os.path.join(self.temp_dir, f'{tag}_slideshow.mp4')
                if progress_queue:
                    try:
                        progress_queue.put_nowait({
                            'stage': 'download', 'current': step, 'total': total_steps,
                            'fragment': step, 'fragments': total_steps, 'speed': 'Создание видео',
                        })
                    except Exception:
                        pass
                result = await loop.run_in_executor(
                    None, lambda: self._make_slideshow(img_paths, audio_path, output, tag)
                )

                # Cleanup images
                for p in img_paths:
                    try:
                        os.remove(p)
                    except Exception:
                        pass
                try:
                    os.rmdir(img_dir)
                except Exception:
                    pass
                if audio_path:
                    try:
                        os.remove(audio_path)
                    except Exception:
                        pass

                if result:
                    print(f"[TT] download: видео готово: {output}")
                    return output, 'TikTok Video'
                return None, 'Не удалось создать видео'

            except Exception as e:
                print(f"[TT] download photo error: {e}")
                return None, str(e)[:150]

        result = await self.ytdlp_download(resolved, format_id, progress_queue)
        print(f"[TT] download result: path={'OK' if result[0] else 'FAIL'}, title={result[1][:50] if result[1] else 'None'}")
        return result
