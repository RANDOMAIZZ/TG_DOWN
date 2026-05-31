import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ── Load .env file (для локальной разработки / Docker) ──
_env = BASE_DIR / '.env'
if _env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        with open(_env, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k, v = k.strip(), v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                    v = v[1:-1]
                if not os.environ.get(k):
                    os.environ[k] = v

# ── Required secrets (должны быть в .env или переменных окружения) ──
API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
BOT_TOKEN = os.environ['BOT_TOKEN']

# ── Опциональные секреты ──
DEEZER_ARL = os.environ.get('DEEZER_ARL', '')
VK_LOGIN = os.environ.get('VK_LOGIN', '')
VK_PASSWORD = os.environ.get('VK_PASSWORD', '')
YOUTUBE_COOKIES_FROM_BROWSER = os.environ.get('YOUTUBE_COOKIES_FROM_BROWSER', '')
VK_COOKIES_FROM_BROWSER = os.environ.get('VK_COOKIES_FROM_BROWSER', '')

# ── Конфиги по умолчанию ──
TEMP_DIR = os.getenv('TEMP_DIR', 'downloads')
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024
ALLOWED_QUALITIES = ["144p", "240p", "360p", "480p", "720p", "1080p", "1440p", "2160p"]

VK_COOKIES_FILE = os.getenv('VK_COOKIES_FILE', 'vk.com_cookies.txt')
INSTAGRAM_COOKIES_FILE = os.getenv('INSTAGRAM_COOKIES_FILE', 'cookies/instagram.txt')
SOUNDCLOUD_COOKIES_FILE = os.getenv('SOUNDCLOUD_COOKIES_FILE', 'cookies/soundcloud.txt')
YANDEX_COOKIES_FILE = os.getenv('YANDEX_COOKIES_FILE', 'cookies/yandex.txt')
SPOTIFY_COOKIES_FILE = os.getenv('SPOTIFY_COOKIES_FILE', 'cookies/spotify.txt')
YOUTUBE_COOKIES_FILE = os.getenv('YOUTUBE_COOKIES_FILE', 'cookies/youtube.txt')

# Доступ к боту (оставьте пустым списком для открытого доступа)
ALLOWED_USERS = [1090508225, 5231935041, 357974771, 6673270481]
