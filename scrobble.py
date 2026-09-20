#!/usr/bin/env python3
"""Scrobble an album from your Discogs collection to Last.fm (CLI).

Usage:
  python3 scrobble.py              # search your collection and scrobble
  python3 scrobble.py --dry-run    # preview the scrobble without submitting

For a browser-based GUI instead, run app.py.
"""
import sys
import time
import argparse

import core


def pick_release(matches):
    for idx, item in enumerate(matches, 1):
        year = f" ({item['year']})" if item.get("year") else ""
        print(f"  {idx}. {item['artist']} - {item['title']}{year}")
    while True:
        choice = input("\nPick a number (or 'q' to quit): ").strip()
        if choice.lower() == "q":
            sys.exit(0)
        if choice.isdigit() and 1 <= int(choice) <= len(matches):
            return matches[int(choice) - 1]
        print("Invalid choice, try again.")


def print_plan(planned, album_title, dry_run):
    print(f"\n{'Would scrobble' if dry_run else 'Scrobbling'} {len(planned)} tracks from \"{album_title}\":\n")
    for t in planned:
        when = time.strftime("%H:%M:%S", time.localtime(t["timestamp"]))
        print(f"  [{when}] {t['artist']} - {t['title']} ({t['duration']}s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="preview without submitting to Last.fm")
    args = parser.parse_args()

    try:
        _, discogs_user = core.connect_discogs()
        lastfm_network = None if args.dry_run else core.connect_lastfm()
    except core.ConfigError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print("Loading your Discogs collection (this can take a moment for large collections)...")
    items = core.load_collection(discogs_user)
    print(f"Loaded {len(items)} releases.")

    query = input("\nSearch your collection (artist or album, blank for all): ").strip()
    matches = core.search_collection(items, query)
    if not matches:
        print("No matches found.")
        sys.exit(0)

    chosen = pick_release(matches)
    release = chosen["release"]

    tracks = core.build_tracks(release)
    if not tracks:
        print("No tracks found on this release.")
        sys.exit(0)

    print(f"\nFound {len(tracks)} tracks on \"{chosen['title']}\":")
    for t in tracks:
        print(f"  - {t['artist']} - {t['title']} ({t['duration']}s)")

    if not args.dry_run:
        confirm = input(f"\nScrobble all {len(tracks)} tracks to Last.fm now? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            sys.exit(0)

    planned = core.plan_scrobbles(tracks)
    print_plan(planned, chosen["title"], args.dry_run)

    if args.dry_run:
        print("\nDry run only -- nothing was submitted to Last.fm.")
    else:
        core.submit_scrobbles(lastfm_network, planned, chosen["title"])
        print("\nDone -- scrobbled to Last.fm.")


if __name__ == "__main__":
    main()
