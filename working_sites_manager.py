import json
import os
import time
import threading

WORKING_SITES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "working_sites.json")

_pending = set()
_pending_lock = threading.Lock()
_last_flush = 0.0


def load_good_tidal_urls() -> list[str]:
    if not os.path.isfile(WORKING_SITES_FILE):
        return []
    try:
        with open(WORKING_SITES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("tidal", {}).get("good", [])
    except Exception as e:
        print(f"[WS] load error: {e}")
        return []


def save_good_tidal_urls(urls: list[str]):
    try:
        data = {}
        if os.path.isfile(WORKING_SITES_FILE):
            try:
                with open(WORKING_SITES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        if "tidal" not in data:
            data["tidal"] = {}
        data["tidal"]["good"] = list(dict.fromkeys(u.rstrip("/") for u in urls if u.strip()))
        with open(WORKING_SITES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[WS] save error: {e}")


def add_good_tidal_url(url: str):
    url = url.strip().rstrip("/")
    if not url:
        return
    with _pending_lock:
        _pending.add(url)
    _maybe_flush()


def remove_good_tidal_url(url: str):
    url = url.strip().rstrip("/")
    current = load_good_tidal_urls()
    if url in current:
        current.remove(url)
        save_good_tidal_urls(current)
        print(f"[WS] removed dead URL: {url}")


def _maybe_flush(force=False):
    global _last_flush
    now = time.time()
    with _pending_lock:
        if not _pending:
            return
        if not force and now - _last_flush < 30:
            return
        urls = list(_pending)
        _pending.clear()
    current = load_good_tidal_urls()
    changed = any(u not in current for u in urls)
    if changed:
        all_urls = list(dict.fromkeys(current + urls))
        save_good_tidal_urls(all_urls)
        print(f"[WS] saved {len(all_urls)} good URLs")
    _last_flush = now


def flush_good_urls():
    _maybe_flush(force=True)


def patch_tidal_apis():
    from SpotiFLAC.providers import tidal as tidal_mod
    good = load_good_tidal_urls()
    if not good:
        return
    original = list(tidal_mod._TIDAL_APIS_GET)
    ordered = list(dict.fromkeys(good + original))
    if ordered != original:
        try:
            state = tidal_mod._load_tidal_api_list_state_locked()
            if state["urls"]:
                state["urls"] = list(dict.fromkeys(good + state["urls"]))
                tidal_mod._save_tidal_api_list_state_locked(state)
        except Exception:
            pass
        tidal_mod._TIDAL_APIS_GET = ordered
        print(f"[WS] patched Tidal APIs: {len(good)} good, {len(original)} total")


def install_success_hook():
    from SpotiFLAC.providers import tidal as tidal_mod
    original = tidal_mod.remember_tidal_api_usage

    if getattr(original, "_ws_hooked", False):
        return

    def _hooked(api_url):
        add_good_tidal_url(api_url)
        original(api_url)

    _hooked._ws_hooked = True
    tidal_mod.remember_tidal_api_usage = _hooked
    print("[WS] installed success hook")


def patch_spotify_metadata():
    """
    Monkey-patch SpotifyMetadataClient.get_url to bypass geo-blocking
    (403 "unavailable in this country") by using song.link API as fallback.
    """
    from SpotiFLAC.providers import spotify_metadata as sm
    import requests as _req

    original_get_url = sm.SpotifyMetadataClient.get_url
    original_get_track = sm.SpotifyMetadataClient.get_track

    if getattr(original_get_url, "_ws_patched", False):
        return

    def _patched_get_url(self, spotify_url, include_featuring=False):
        try:
            return original_get_url(self, spotify_url, include_featuring)
        except Exception as orig_err:
            print(f"[WS] Spotify API failed ({orig_err}), trying song.link fallback...")
        # Fallback: song.link API
        info = sm.parse_spotify_url(spotify_url)
        if info is None:
            return "Unknown", []
        if info["type"] != "track":
            return "Unknown", []
        track_id = info["id"]
        try:
            resp = _req.get(
                f"https://api.song.link/v1-alpha.1/links?url=https://open.spotify.com/track/{track_id}&userCountry=US",
                timeout=15,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"song.link HTTP {resp.status_code}")
            data = resp.json()
            artist = ""
            title = ""
            for uid, ent in data.get("entitiesByUniqueId", {}).items():
                if not title:
                    title = ent.get("title", "Unknown")
                if not artist:
                    artist = ent.get("artistName", "Unknown")
                if title and artist:
                    break
            if not title:
                raise RuntimeError("no title in song.link response")
            from SpotiFLAC.core.models import TrackMetadata
            meta = TrackMetadata(
                id=track_id,
                title=title,
                artists=artist,
                album=title,
                album_artist=artist,
                external_url=f"https://open.spotify.com/track/{track_id}",
            )
            return meta.title, [meta]
        except Exception as e2:
            print(f"[WS] song.link fallback error: {e2}")
            return "Unknown", []

    sm.SpotifyMetadataClient.get_url = _patched_get_url
    sm.SpotifyMetadataClient.get_url._ws_patched = True
    print("[WS] patched Spotify metadata (song.link fallback)")
