#!/usr/bin/env python3
"""Local web GUI for scrobbling albums from your Discogs collection to
Last.fm. Runs entirely on your own machine -- nothing is hosted publicly.

Usage:
  python3 app.py
  then open http://127.0.0.1:5050 in your browser (opens automatically)
"""
import os
import sys
import threading
import webbrowser

from flask import Flask, jsonify, render_template, request

import core

app = Flask(__name__)

# 5000 is macOS's AirPlay Receiver port -- if it's enabled it'll grab the
# port before this app can bind it. Default somewhere else to sidestep
# that entirely; override with PORT= if 5050 is also taken.
PORT = int(os.environ.get("PORT", 5050))

# Populated once at startup; a personal single-user local tool doesn't need
# per-request reloading or multi-user cache invalidation.
_collection = []
_discogs_client = None
_discogs_user = None

# Every release we know about, keyed by id -- collection items loaded at
# startup, plus anything turned up by a general Discogs search. This is
# what /api/release and /api/scrobble look items up in, so a search result
# doesn't need to be in your collection to view its tracklist or scrobble it.
_release_cache = {}

# Holds the in-progress Last.fm web-auth handshake between the
# start-auth and complete-auth calls below.
_lastfm_auth_pending = {}


def _find_by_id(release_id):
    return _release_cache.get(release_id)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/lastfm/status")
def api_lastfm_status():
    return jsonify({"connected": core.has_lastfm_session()})


@app.route("/api/lastfm/start-auth", methods=["POST"])
def api_lastfm_start_auth():
    try:
        skg, auth_url = core.start_lastfm_auth()
    except core.ConfigError as e:
        return jsonify({"error": str(e)}), 400
    _lastfm_auth_pending["skg"] = skg
    _lastfm_auth_pending["auth_url"] = auth_url
    return jsonify({"auth_url": auth_url})


@app.route("/api/lastfm/complete-auth", methods=["POST"])
def api_lastfm_complete_auth():
    skg = _lastfm_auth_pending.get("skg")
    auth_url = _lastfm_auth_pending.get("auth_url")
    if not skg or not auth_url:
        return jsonify({"error": "Click \"Connect to Last.fm\" first."}), 400
    try:
        core.complete_lastfm_auth(skg, auth_url)
    except Exception:
        return jsonify({
            "error": "Couldn't complete authorization -- did you click "
                     "\"Allow access\" on the Last.fm page that opened?"
        }), 400
    _lastfm_auth_pending.clear()
    return jsonify({"connected": True})


@app.route("/api/collection")
def api_collection():
    return jsonify([
        {"id": i["id"], "artist": i["artist"], "title": i["title"], "year": i["year"], "thumb": i["thumb"]}
        for i in _collection
    ])


@app.route("/api/collection/refresh", methods=["POST"])
def api_collection_refresh():
    global _collection
    try:
        _collection = core.load_collection(_discogs_user)
    except Exception as e:
        return jsonify({"error": f"Couldn't refresh your collection: {e}"}), 502
    for item in _collection:
        _release_cache[item["id"]] = item
    return jsonify({"count": len(_collection)})


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])

    try:
        found = core.search_discogs(_discogs_client, query)
    except Exception as e:
        return jsonify({"error": f"Discogs search failed: {e}"}), 502

    results = []
    for item in found:
        # Keep the collection's copy if we already have one -- it has a
        # properly split artist name instead of search's parsed guess.
        cached = _release_cache.setdefault(item["id"], item)
        results.append({
            "id": cached["id"],
            "artist": cached["artist"],
            "title": cached["title"],
            "year": cached["year"],
            "thumb": cached["thumb"],
        })
    return jsonify(results)


@app.route("/api/release/<int:release_id>")
def api_release(release_id):
    item = _find_by_id(release_id)
    if item is None:
        return jsonify({"error": "Release not found in your collection."}), 404
    tracks = core.build_tracks(item["release"])
    return jsonify({
        "id": item["id"],
        "artist": item["artist"],
        "title": item["title"],
        "tracks": tracks,
    })


@app.route("/api/scrobble", methods=["POST"])
def api_scrobble():
    data = request.get_json(force=True)
    release_id = data.get("release_id")
    dry_run = bool(data.get("dry_run"))

    item = _find_by_id(release_id)
    if item is None:
        return jsonify({"error": "Release not found in your collection."}), 404

    tracks = core.build_tracks(item["release"])
    if not tracks:
        return jsonify({"error": "No tracks found on this release."}), 400

    planned = core.plan_scrobbles(tracks)

    if not dry_run:
        try:
            network = core.connect_lastfm()
        except core.ConfigError as e:
            return jsonify({"error": str(e)}), 400
        core.submit_scrobbles(network, planned, item["title"])

    return jsonify({"ok": True, "dry_run": dry_run, "planned": planned})


def main():
    global _collection, _discogs_client, _discogs_user

    try:
        _discogs_client, _discogs_user = core.connect_discogs()
    except core.ConfigError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print("Loading your Discogs collection (this can take a moment for large collections)...")
    _collection = core.load_collection(_discogs_user)
    for item in _collection:
        _release_cache[item["id"]] = item
    print(f"Loaded {len(_collection)} releases.")

    url = f"http://127.0.0.1:{PORT}"
    print(f"\nStarting local server at {url} (opening in your browser)...")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    app.run(host="127.0.0.1", port=PORT, debug=False)


if __name__ == "__main__":
    main()
