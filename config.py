import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

API_ID = int(os.getenv('API_ID', '35607163'))
API_HASH = os.getenv('API_HASH', '6c91d69aa230dcf7cae207af33b93445')
BOT_TOKEN = os.getenv('BOT_TOKEN', '8781707900:AAHlODNmWL5kN621felcJq1pFKRVuhDlxV0')

TEMP_DIR = os.getenv('TEMP_DIR', 'downloads')
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024
ALLOWED_QUALITIES = ["144p", "240p", "360p", "480p", "720p", "1080p", "1440p", "2160p"]

# Deezer: ARL cookie из браузера (Application → Cookies → deezer.com → arl)
DEEZER_ARL = os.getenv('DEEZER_ARL', '')

# Cookies Netscape-формата (экспорт через расширение «Get cookies.txt LOCALLY» и т.п.)
VK_COOKIES_FILE = os.getenv('VK_COOKIES_FILE', 'vk.com_cookies.txt')
INSTAGRAM_COOKIES_FILE = os.getenv('INSTAGRAM_COOKIES_FILE', 'cookies/instagram.txt')
SOUNDCLOUD_COOKIES_FILE = os.getenv('SOUNDCLOUD_COOKIES_FILE', 'cookies/soundcloud.txt')
YANDEX_COOKIES_FILE = os.getenv('YANDEX_COOKIES_FILE', 'cookies/yandex.txt')
SPOTIFY_COOKIES_FILE = os.getenv('SPOTIFY_COOKIES_FILE', 'cookies/spotify.txt')
YOUTUBE_COOKIES_FILE = os.getenv('YOUTUBE_COOKIES_FILE', 'cookies/youtube.txt')
YOUTUBE_COOKIES_FROM_BROWSER = os.getenv('YOUTUBE_COOKIES_FROM_BROWSER', '')

# VK логин/пароль (альтернатива cookies; лучше через переменные окружения VK_LOGIN / VK_PASSWORD)
VK_LOGIN = os.getenv('VK_LOGIN', '+79187573519')
VK_PASSWORD = os.getenv('VK_PASSWORD', 'Nepobedim97531')

# Cookies из браузера: opera_gx | chrome | edge | firefox | пусто = файл/логин
# Opera GX: закройте браузер перед скачиванием (иначе cookies заблокированы)
VK_COOKIES_FROM_BROWSER = os.getenv('VK_COOKIES_FROM_BROWSER', 'opera_gx')

# Доступ к боту (оставьте пустым для открытого доступа)
ALLOWED_USERS = [1090508225, 5231935041, 357974771, 6673270481]
