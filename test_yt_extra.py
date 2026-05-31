import sys
sys.path.insert(0, '.')
from downloaders.youtube_downloader import YouTubeDownloader

# Test with no cookies, no browser
ydl = YouTubeDownloader('temp', cookiefile='', cookies_browser='')
print('Test 1 - no cookies, no browser:')
print('  cookiefile:', repr(ydl.cookiefile))
print('  cookies_browser:', repr(ydl.cookies_browser))
extra = ydl._yt_extra()
print('  _yt_extra():', extra)

# Test with empty string browser (from config)
ydl2 = YouTubeDownloader('temp', cookiefile='', cookies_browser='')
print('\\nTest 2 - empty browser string:')
print('  cookies_browser:', repr(ydl2.cookies_browser))
extra2 = ydl2._yt_extra()
print('  _yt_extra():', extra2)

# Test with 'opera' browser (old config)
ydl3 = YouTubeDownloader('temp', cookiefile='', cookies_browser='opera')
print('\\nTest 3 - cookies_browser=\"opera\":')
print('  cookies_browser:', repr(ydl3.cookies_browser))
extra3 = ydl3._yt_extra()
print('  _yt_extra():', extra3)