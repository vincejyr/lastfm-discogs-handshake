"""Shared Discogs <-> Last.fm logic used by both scrobble.py (CLI) and
app.py (local web GUI)."""
import itertools
import os
import time

import pylast
import discogs_client
from dotenv import load_dotenv

SESSION_KEY_FILE = ".lastfm_session_key"
DEFAULT_TRACK_SECONDS = 180  # fallback when Discogs has no duration listed

load_dotenv()


class ConfigError(Exception):
    """Missing .env values or Last.fm session."""


def parse_duration(duration_str):
    """Discogs durations look like '3:45' or '1:02:30'; '' if unlisted."""
    if not duration_str:
        return DEFAULT_TRACK_SECONDS
    parts = duration_str.strip().split(":")
    try:
        parts = [int(p) for p in parts]
    except ValueError:
        return DEFAULT_TRACK_SECONDS
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds or DEFAULT_TRACK_SECONDS


def connect_discogs():
    """Returns (client, user) -- the raw API client is needed for
    full-database search, the User for collection access."""
    token = os.environ.get("DISCOGS_TOKEN")
    username = os.environ.get("DISCOGS_USERNAME")
    if not token or not username:
        raise ConfigError("Set DISCOGS_TOKEN and DISCOGS_USERNAME in .env first.")
    client = discogs_client.Client("lastfm-discogs-handshake/1.0", user_token=token)
    return client, client.user(username)


def connect_lastfm():
    api_key = os.environ.get("LASTFM_API_KEY")
    api_secret = os.environ.get("LASTFM_API_SECRET")
    if not api_key or not api_secret:
        raise ConfigError("Set LASTFM_API_KEY and LASTFM_API_SECRET in .env first.")
    if not os.path.exists(SESSION_KEY_FILE):
        raise ConfigError("Not connected to Last.fm yet.")
    with open(SESSION_KEY_FILE) as f:
        session_key = f.read().strip()
    return pylast.LastFMNetwork(api_key=api_key, api_secret=api_secret, session_key=session_key)


def has_lastfm_session():
    return os.path.exists(SESSION_KEY_FILE)


def start_lastfm_auth():
    """Begins the Last.fm web-auth flow. Returns (skg, auth_url); the
    caller must hold onto `skg` and pass it (with the same auth_url) to
    complete_lastfm_auth() once the user has approved access in their
    browser."""
    api_key = os.environ.get("LASTFM_API_KEY")
    api_secret = os.environ.get("LASTFM_API_SECRET")
    if not api_key or not api_secret:
        raise ConfigError("Set LASTFM_API_KEY and LASTFM_API_SECRET in .env first.")
    network = pylast.LastFMNetwork(api_key=api_key, api_secret=api_secret)
    skg = pylast.SessionKeyGenerator(network)
    auth_url = skg.get_web_auth_url()
    return skg, auth_url


def complete_lastfm_auth(skg, auth_url):
    """Exchanges the approved auth_url for a session key and saves it."""
    session_key = skg.get_web_auth_session_key(auth_url)
    with open(SESSION_KEY_FILE, "w") as f:
        f.write(session_key)
    return session_key


def load_collection(user):
    """Returns a list of dicts, one per release in the "All" collection
    folder. Each dict keeps a reference to the live Release object (for
    later lazy-loading its tracklist), plus a stable id and thumbnail
    already available from Discogs' collection response."""
    folder = user.collection_folders[0]  # folder 0 = "All"
    items = []
    for item in folder.releases:
        release = item.release
        artist = ", ".join(a.name for a in release.artists) if release.artists else "Unknown Artist"
        items.append({
            "id": release.id,
            "artist": artist,
            "title": release.title,
            "year": release.year,
            "thumb": release.thumb,
            "release": release,
        })
    return items


def search_collection(items, query):
    if not query:
        return items
    q = query.lower()
    return [i for i in items if q in i["artist"].lower() or q in i["title"].lower()]


def search_discogs(client, query, limit=50):
    """Searches the full Discogs database (not just your collection).
    Search results only carry a combined "Artist - Title" string rather
    than the structured artist list collection items have, so split it
    heuristically."""
    if not query:
        return []
    results = client.search(query, type="release")
    try:
        matches = results[:limit]
    except TypeError:
        matches = itertools.islice(results, limit)

    items = []
    for r in matches:
        raw_title = r.data.get("title") or ""
        if " - " in raw_title:
            artist, title = raw_title.split(" - ", 1)
        else:
            artist, title = "Unknown Artist", raw_title
        items.append({
            "id": r.id,
            "artist": artist,
            "title": title,
            "year": r.data.get("year"),
            "thumb": r.data.get("thumb") or "",
            "release": r,
        })
    return items


def build_tracks(release):
    """Fetches the release's full tracklist (triggers a lazy API call the
    first time, since collection listings only include basic info)."""
    tracks = []
    album_artist = ", ".join(a.name for a in release.artists) if release.artists else "Unknown Artist"
    for t in release.tracklist:
        if not t.title or t.fetch("type_", "track") != "track":
            continue  # skip headings/indexes that aren't actual tracks
        track_artist = ", ".join(a.name for a in t.artists) if t.artists else album_artist
        tracks.append({
            "artist": track_artist,
            "title": t.title,
            "duration": parse_duration(t.duration),
        })
    return tracks


def plan_scrobbles(tracks):
    """Assigns each track a timestamp, spaced backward from now using
    actual track durations, so the whole album appears to have just been
    listened to start-to-finish. Returns a new list of track dicts with a
    'timestamp' key added, in playback order."""
    total_duration = sum(t["duration"] for t in tracks)
    timestamp = int(time.time()) - total_duration
    planned = []
    for t in tracks:
        planned.append({**t, "timestamp": timestamp})
        timestamp += t["duration"]
    return planned


def submit_scrobbles(network, planned, album_title):
    """Actually submits each planned track to Last.fm."""
    for t in planned:
        network.scrobble(
            artist=t["artist"],
            title=t["title"],
            timestamp=t["timestamp"],
            album=album_title,
        )
