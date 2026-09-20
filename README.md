# LastFM ↔ Discogs handshake

Scrobble an album to Last.fm, from your Discogs collection or from
Discogs' full database. Two interfaces, same underlying logic
(`core.py`):

- **`app.py`** — a local browser-based GUI: searchable album grid with
  cover art, a toggle to search your collection or all of Discogs,
  click an album to see its tracklist, one button to scrobble
- **`scrobble.py`** — a terminal-only CLI, collection-only, if you
  prefer that

Both run entirely on your own machine. Nothing is hosted publicly.

## How it works

1. Fetches your Discogs collection (the "All" folder) via the Discogs
   API; the GUI can also search the full Discogs database on demand
2. You search/pick a release
3. Fetches that release's full tracklist from Discogs (lazy-loaded on
   demand, not for your whole collection up front)
4. Scrobbles each track to Last.fm, with timestamps spaced backward from
   now using each track's actual duration — so it looks like a normal,
   real listen ending now, not a burst of identical timestamps

## Setup

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in:

- `LASTFM_API_KEY` / `LASTFM_API_SECRET` — register an app at
  https://www.last.fm/api/account/create
- `DISCOGS_TOKEN` — generate a personal access token at
  https://www.discogs.com/settings/developers
- `DISCOGS_USERNAME` — your Discogs username

That's the only manual setup step — connecting to Last.fm itself happens
inside the GUI (see below).

## Usage

### GUI (recommended)

```
source venv/bin/activate
python3 app.py
```

Or on macOS, just double-click **`Launch Scrobbler.command`** in Finder
instead of using the terminal at all (first time you run it, macOS may
warn it's from an unidentified developer — right-click it and choose
**Open** to allow it once).

Either way, it opens `http://127.0.0.1:5050` in your browser
automatically (override with `PORT=...` if 5050 is also taken). If you
haven't connected to Last.fm yet, a banner at the
top offers a **Connect to Last.fm** button — click it, approve access on
the Last.fm page that opens, then come back and click the button again
to finish (this only needs to happen once; it saves a session key to
`.lastfm_session_key`, gitignored, reused on every future run).

Then search or browse the grid, click an album to see its tracklist,
tick/untick "Dry run" and click **Scrobble to Last.fm**.

Use the **My collection / All of Discogs** toggle above the search box
to switch between filtering your own collection and searching the full
Discogs database — the latter works for any release, not just ones you
own. If you've added something to your Discogs collection since the app
started, click **Refresh** to re-fetch it without restarting.

### CLI

```
source venv/bin/activate
python3 auth_lastfm.py   # one-time Last.fm authorization, if not already done via the GUI
python3 scrobble.py
```

Search your collection, pick a release, review the tracklist, confirm.

To preview without submitting anything to Last.fm:

```
python3 scrobble.py --dry-run
```

## Notes

- Last.fm's guidelines discourage scrobbling music you didn't actually
  listen to. This tool is meant for logging physical/vinyl listens you
  actually had, not for inflating play counts — use it accordingly.
- Tracks without a Discogs-listed duration default to 3 minutes for
  timestamp spacing purposes.
- `.env` and `.lastfm_session_key` are gitignored — never commit them.
