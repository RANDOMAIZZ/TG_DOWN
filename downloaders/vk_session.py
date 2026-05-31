"""VK API helpers — только access token."""
import os
import re
import time
import json
from typing import Dict, Optional

VK_REFERER = 'https://vk.com/'
VK_CHROME_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
)

# ── URL detection ──

_VK_DOMAINS = frozenset({'vk.com', 'vk.ru', 'vkvideo.ru'})


def is_vk_url(url: str) -> bool:
    u = url.lower()
    return any(d in u for d in _VK_DOMAINS)


def is_vk_music_url(url: str) -> bool:
    u = url.lower()
    if not any(d in u for d in _VK_DOMAINS):
        return False
    if 'badbrowser' in u:
        return False
    markers = (
        '/audio', '/music/', 'z=audio', 'act=audio',
        'audioplayer', 'audio_playlist', '/audios',
    )
    return any(m in u for m in markers)


def normalize_vk_music_url(url: str) -> str:
    url = (
        url.replace('vk.ru/', 'vk.com/')
        .replace('vkvideo.ru/', 'vk.com/')
        .replace('m.vk.ru/', 'vk.com/')
        .replace('m.vk.com/', 'vk.com/')
    )
    if url.startswith('http://'):
        url = 'https://' + url[7:]

    m = re.search(r'audio(-?\d+)_(\d+)', url, re.I)
    if m:
        return f'https://vk.com/audio{m.group(1)}_{m.group(2)}'

    m = re.search(r'[?&]z=audio(-?\d+)_(\d+)', url, re.I)
    if m:
        return f'https://vk.com/audio{m.group(1)}_{m.group(2)}'

    m = re.search(r'[?&]z=audio_playlist(-?\d+)_(\d+)', url, re.I)
    if m:
        return f'https://vk.com/audio{m.group(1)}_{m.group(2)}'

    return url


# ── VK API (vk_api library) ──

_VK_API_CACHE: Dict[str, object] = {}
_VK_API_LAST_CALL = 0.0


def _vk_api_get_session(token: str):
    """Get or create a cached vk_api.VkApi session from a token."""
    if not token:
        print("[VK DBG] _vk_api_get_session: token is empty")
        return None, 'Нет токена VK API'
    cache_key = f'token:{token[:16]}'
    if cache_key in _VK_API_CACHE:
        print(f"[VK DBG] _vk_api_get_session: using cached session for {cache_key}")
        return _VK_API_CACHE[cache_key], None
    print(f"[VK DBG] _vk_api_get_session: creating new session for {cache_key}")
    try:
        import vk_api
        print(f"[VK DBG] vk_api version: {getattr(vk_api, '__version__', 'unknown')}")
    except ImportError:
        print("[VK DBG] vk_api library not installed")
        return None, 'vk_api library not installed (pip install vk-api)'

    try:
        vk_session = vk_api.VkApi(token=token)
        print(f"[VK DBG] VkApi session created. type={type(vk_session)}")
        print(f"[VK DBG] has .method: {hasattr(vk_session, 'method')}")
        print(f"[VK DBG] has .get_api: {hasattr(vk_session, 'get_api')}")
        _VK_API_CACHE[cache_key] = vk_session
        return vk_session, None
    except Exception as e:
        print(f"[VK DBG] VkApi creation failed: {e}")
        return None, f'VK API token error: {e}'


def _vk_api_call(session, method: str, params: dict, retries: int = 2) -> dict:
    """Call VK API method with rate limiting and retries."""
    global _VK_API_LAST_CALL
    print(f"[VK API] calling '{method}' params={params}")
    for attempt in range(retries + 1):
        now = time.time()
        since_last = now - _VK_API_LAST_CALL
        if since_last < 1.0:
            wait = 1.0 - since_last
            print(f"[VK API] rate limit: sleeping {wait:.2f}s")
            time.sleep(wait)
        _VK_API_LAST_CALL = time.time()
        try:
            print(f"[VK API] session type={type(session).__name__}, has method={hasattr(session, 'method')}")
            result = session.method(method, params)
            print(f"[VK API] response type={type(result).__name__}, keys={list(result.keys()) if isinstance(result, dict) else 'N/A'}")
            import json
            print(f"[VK API] response preview={json.dumps(result, ensure_ascii=False, default=str)[:500]}")
            return result
        except Exception as e:
            err = str(e)
            print(f"[VK API] attempt {attempt+1}/{retries+1} failed: {e}")
            import traceback
            traceback.print_exc()
            if attempt < retries and ('flood' in err.lower() or 'too many' in err.lower()):
                wait = (attempt + 1) * 3
                print(f"[VK API] flood control, waiting {wait}s...")
                time.sleep(wait)
                continue
            raise
    return {}


# ── Video ──

def _parse_vk_video_id(url: str) -> tuple:
    patterns = [
        r'vk\.(?:com|ru|video\.ru)/video(-?\d+)_(\d+)',
        r'vkvideo\.ru/video(-?\d+)_(\d+)',
        r'vk\.(?:com|ru)/video_ext\.php\?.*\boid=(-?\d+).*\bid=(\d+)',
    ]
    for pat in patterns:
        m = re.search(pat, url, re.I)
        if m:
            return m.group(1), m.group(2)
    return None, None


def vk_api_get_video_info(url: str, token: str) -> dict:
    print(f"[VK DBG] vk_api_get_video_info called")
    print(f"[VK DBG]   url={url}")
    print(f"[VK DBG]   token={'SET' if token else 'EMPTY'}")
    owner_id, video_id = _parse_vk_video_id(url)
    print(f"[VK DBG]   parsed owner_id={owner_id}, video_id={video_id}")
    if not owner_id or not video_id:
        return {'error': 'Не удалось распознать ID видео', 'formats': []}

    session, err = _vk_api_get_session(token)
    print(f"[VK DBG] session={type(session).__name__ if session else 'None'}, err={err}")
    if err:
        return {'error': err, 'formats': []}

    try:
        method_params = {
            'videos': f'{owner_id}_{video_id}',
            'v': '5.131',
        }
        print(f"[VK DBG] calling video.get with: {method_params}")
        resp = _vk_api_call(session, 'video.get', method_params)
        print(f"[VK DBG] video.get keys={list(resp.keys())}")
        items = resp.get('items', [])
        print(f"[VK DBG] video.get items count={len(items)}")
        if not items:
            return {'error': 'Видео не найдено или недоступно', 'formats': []}
        item = items[0]
        files = item.get('files', {})
        print(f"[VK DBG] item keys={list(item.keys())}")
        print(f"[VK DBG] files keys={list(files.keys())}")
        for fk, fv in files.items():
            print(f"[VK DBG]   file[{fk}] = {str(fv)[:100]}")
        title = item.get('title', 'VK Video')
        duration = item.get('duration', 0)

        quality_map = {
            'quality_2160': '2160p', 'quality_1440': '1440p',
            'quality_1080': '1080p', 'quality_720': '720p',
            'quality_540': '540p', 'quality_480': '480p',
            'quality_360': '360p', 'quality_240': '240p',
            'quality_144': '144p',
        }
        formats = []
        for vk_key, label in quality_map.items():
            url_val = files.get(vk_key, '')
            if url_val:
                formats.append({'format_id': vk_key, 'quality': label, 'url': url_val})
                print(f"[VK DBG] quality {label}: url present")

        mp4_url = files.get('mp4', '')
        if mp4_url and not formats:
            formats.append({'format_id': 'mp4', 'quality': 'Auto', 'url': mp4_url})
            print(f"[VK DBG] mp4 fallback: url present")

        if not formats:
            player = item.get('player', '')
            direct_url = item.get('direct_url', '')
            if player:
                formats.append({'format_id': 'player', 'quality': 'HLS', 'url': player})
                print(f"[VK DBG] player page: {player[:100]}")
            if direct_url:
                formats.append({'format_id': 'direct_url', 'quality': 'Auto', 'url': direct_url})
                print(f"[VK DBG] direct_url: {direct_url[:100]}")
            if not formats:
                print(f"[VK DBG] NO formats found at all")

        result = {
            'title': str(title)[:50],
            'duration': duration,
            'formats': formats,
            'platform': 'vk',
            'is_short': not formats,
        }
        print(f"[VK DBG] result formats count={len(formats)}")
        return result
    except Exception as e:
        print(f"[VK DBG] EXCEPTION in video.get: {e}")
        import traceback
        traceback.print_exc()
        return {'error': f'VK API error: {e}', 'formats': []}


# ── Audio ──

def vk_api_get_audio_info(url: str, token: str) -> dict:
    print(f"[VK DBG] vk_api_get_audio_info called")
    print(f"[VK DBG]   url={url}")
    print(f"[VK DBG]   token={'SET' if token else 'EMPTY'}")
    m = re.search(r'audio(-?\d+)_(\d+)', url)
    if not m:
        print(f"[VK DBG]   no audio ID found in url")
        return {'error': 'Не удалось распознать ID аудио', 'formats': []}
    owner_id, audio_id = m.group(1), m.group(2)
    print(f"[VK DBG]   parsed owner_id={owner_id}, audio_id={audio_id}")

    session, err = _vk_api_get_session(token)
    print(f"[VK DBG] session={type(session).__name__ if session else 'None'}, err={err}")
    if err:
        return {'error': err, 'formats': []}

    try:
        method_params = {
            'audios': f'{owner_id}_{audio_id}',
            'v': '5.131',
        }
        print(f"[VK DBG] calling audio.getById with: {method_params}")
        resp = _vk_api_call(session, 'audio.getById', method_params)
        print(f"[VK DBG] audio.getById type={type(resp).__name__}")
        items = resp if isinstance(resp, list) else resp.get('items', [resp])
        print(f"[VK DBG] items count={len(items)}")
        if not items:
            return {'error': 'Аудио не найдено', 'formats': []}
        item = items[0]
        print(f"[VK DBG] item keys={list(item.keys()) if isinstance(item, dict) else 'N/A'}")
        audio_url = item.get('url', '') if isinstance(item, dict) else ''
        print(f"[VK DBG] audio url={'SET' if audio_url else 'EMPTY'}")
        if not audio_url:
            return {'error': 'URL аудио не получен (ограничение VK)', 'formats': []}
        title = item.get('title', 'VK Audio') if isinstance(item, dict) else 'VK Audio'
        artist = item.get('artist', '') if isinstance(item, dict) else ''
        full_title = f'{artist} - {title}' if artist else title
        duration = item.get('duration', 0) if isinstance(item, dict) else 0

        result = {
            'title': str(full_title)[:50],
            'duration': duration,
            'formats': [{'format_id': 'best', 'quality': 'MP3', 'url': audio_url}],
            'platform': 'vk_music',
            'is_short': True,
        }
        print(f"[VK DBG] result ok")
        return result
    except Exception as e:
        print(f"[VK DBG] EXCEPTION in audio.getById: {e}")
        import traceback
        traceback.print_exc()
        return {'error': f'VK API error: {e}', 'formats': []}


# ── Error formatting ──

def format_vk_error(err: str) -> str:
    text = err or ''
    low = text.lower()
    if 'token' in low or 'auth' in low:
        return 'Ошибка авторизации VK. Проверьте токен: `/login vk_token <токен>`'
    if 'flood' in low or 'too many' in low:
        return 'Слишком много запросов к VK API, подождите и попробуйте снова'
    if 'not found' in low or 'audio не найдено' in low or 'video не найдено' in low:
        return 'Видео/аудио не найдено. Проверьте ссылку.'
    return text[:300]
