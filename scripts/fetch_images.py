#!/usr/bin/env python3
"""Download images into an image pack under ``images/``.

    python3 scripts/fetch_images.py kpop-demon-hunters --query "Kpop Demon Hunters" -n 12

Three sources, chosen with ``--source``:

``google`` (default)
    Google's official **Custom Search JSON API** — the supported way to run a
    Google image search from a script.  Scraping google.com/images is against
    Google's terms and breaks constantly, so this uses the real API instead.
    Needs two free credentials, once (see ``--help-google``).

``openverse``
    Openverse's CC-licensed image search.  No key, no setup — but it indexes
    openly-licensed media, so it will not have stills from a specific movie.

``urls``
    Read image URLs from a text file, one per line.  The fallback that always
    works: right-click → copy image address on the pictures you actually want,
    paste them into a file, done.

Every download writes a ``CREDITS.md`` in the pack folder recording where each
file came from.  Downloaded images are ignored by git.

Note on movie stills: frames from a film are copyrighted by the studio.  Using a
handful locally so your own kid can practise subtraction is ordinary personal
use; publishing a copy of this app with them bundled in is not.  Keep them in
``images/``, which the repo is set up to leave untracked.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGES_ROOT = PROJECT_ROOT / "images"

USER_AGENT = "MathDemonHunters/1.0 (personal educational use)"
ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
    # SVG is only ever rendered inside an <img>, where scripts cannot run.
    "image/svg+xml": ".svg",
}
MAX_BYTES = 12 * 1024 * 1024
TIMEOUT = 20

GOOGLE_HELP = """
Google Custom Search JSON API — one-time setup (free, ~5 minutes)

1. Create an API key
   https://console.cloud.google.com/apis/credentials
   → Create credentials → API key
   Then enable "Custom Search API" for the project:
   https://console.cloud.google.com/apis/library/customsearch.googleapis.com

2. Create a search engine and get its ID (the "cx")
   https://programmablesearchengine.google.com/controlpanel/create
   → Search the entire web: ON
   → Image search: ON
   Copy the "Search engine ID".

3. Put them in your environment (add to ~/.zshrc to keep them):

   export GOOGLE_API_KEY="AIza..."
   export GOOGLE_CSE_ID="a1b2c3d4e5f6g7h8i"

Free tier is 100 queries/day, which is ~1000 images. Each run of this script
uses one query per 10 images requested.
"""


class FetchError(RuntimeError):
    pass


# --- HTTP helpers ------------------------------------------------------------


def _get(url: str, accept: str = "*/*") -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_BYTES:
            raise FetchError(f"file too large ({int(length) // 1024}KB)")
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise FetchError("file too large")
    return data, content_type


def _get_json(url: str) -> dict:
    data, _ = _get(url, accept="application/json")
    return json.loads(data.decode("utf-8"))


# --- sources -----------------------------------------------------------------


def search_google(query: str, count: int) -> list[dict]:
    """Google Custom Search JSON API — image search, 10 results per request."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    cse_id = os.environ.get("GOOGLE_CSE_ID")
    if not api_key or not cse_id:
        raise FetchError(
            "GOOGLE_API_KEY and GOOGLE_CSE_ID are not set.\n"
            "Run with --help-google for the one-time setup, or use "
            "--source openverse / --source urls instead."
        )

    results: list[dict] = []
    for start in range(1, count + 1, 10):
        params = urllib.parse.urlencode(
            {
                "key": api_key,
                "cx": cse_id,
                "q": query,
                "searchType": "image",
                "num": min(10, count - len(results)),
                "start": start,
                "safe": "active",
                "imgSize": "large",
            }
        )
        try:
            payload = _get_json(f"https://www.googleapis.com/customsearch/v1?{params}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            raise FetchError(f"Google API returned {exc.code}: {detail}")

        items = payload.get("items") or []
        for item in items:
            results.append(
                {
                    "url": item.get("link"),
                    "title": item.get("title") or query,
                    "source": (item.get("image") or {}).get("contextLink") or item.get("displayLink"),
                    "license": "via Google Image Search — check the source page before reuse",
                }
            )
        if len(results) >= count or len(items) < 10:
            break
        time.sleep(0.3)
    return results[:count]


def search_openverse(query: str, count: int) -> list[dict]:
    """Openverse — openly licensed images, no credentials needed."""
    params = urllib.parse.urlencode(
        {"q": query, "page_size": min(count, 50), "mature": "false", "license_type": "all"}
    )
    try:
        payload = _get_json(f"https://api.openverse.org/v1/images/?{params}")
    except urllib.error.HTTPError as exc:
        raise FetchError(f"Openverse returned {exc.code}")

    results = []
    for item in payload.get("results", [])[:count]:
        results.append(
            {
                "url": item.get("url"),
                "title": item.get("title") or query,
                "source": item.get("foreign_landing_url"),
                "license": f"{(item.get('license') or '?').upper()} {item.get('license_version') or ''} "
                f"— by {item.get('creator') or 'unknown'}".strip(),
            }
        )
    return results


def read_urls(path: Path, count: int) -> list[dict]:
    if not path.is_file():
        raise FetchError(f"no such file: {path}")
    urls = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return [{"url": url, "title": "", "source": url, "license": "supplied by hand"} for url in urls[:count]]


# --- download ----------------------------------------------------------------


def safe_stem(text: str, fallback: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (stem or fallback)[:48]


def download(results: list[dict], pack_dir: Path, query: str) -> list[dict]:
    pack_dir.mkdir(parents=True, exist_ok=True)
    existing = len([p for p in pack_dir.iterdir() if p.suffix.lower() in ALLOWED_TYPES.values()])
    saved: list[dict] = []

    for index, item in enumerate(results, start=1):
        url = item.get("url")
        if not url:
            continue
        label = f"[{index}/{len(results)}]"
        try:
            data, content_type = _get(url, accept="image/*")
            suffix = ALLOWED_TYPES.get(content_type)
            if suffix is None:
                raise FetchError(f"not an image ({content_type or 'unknown type'})")

            number = existing + len(saved) + 1
            name = f"{number:02d}-{safe_stem(item.get('title'), safe_stem(query, 'image'))}{suffix}"
            (pack_dir / name).write_bytes(data)
            saved.append({**item, "file": name})
            print(f"  {label} saved {name}  ({len(data) // 1024}KB)")
        except (FetchError, urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
            print(f"  {label} skipped — {exc}")
        time.sleep(0.2)

    return saved


def write_credits(pack_dir: Path, query: str, source: str, saved: list[dict]) -> None:
    credits = pack_dir / "CREDITS.md"
    lines = []
    if not credits.exists():
        lines.append(f"# Image credits — {pack_dir.name}\n")
        lines.append("Where each picture in this pack came from.\n")
    lines.append(f"\n## {time.strftime('%Y-%m-%d %H:%M')} · {source} · \"{query}\"\n")
    for item in saved:
        lines.append(f"- `{item['file']}` — {item.get('license') or 'unknown licence'}")
        if item.get("source"):
            lines.append(f"  - source: {item['source']}")
    with credits.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# --- CLI ---------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download images into an image pack under images/.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            '  python3 scripts/fetch_images.py kpop-demon-hunters -q "Kpop Demon Hunters movie" -n 12\n'
            '  python3 scripts/fetch_images.py space -q "nebula" -n 10 --source openverse\n'
            "  python3 scripts/fetch_images.py my-theme --source urls --urls-file picks.txt\n"
        ),
    )
    parser.add_argument("pack", nargs="?", help="pack folder name, e.g. kpop-demon-hunters")
    parser.add_argument("-q", "--query", help="what to search for")
    parser.add_argument("-n", "--count", type=int, default=12, help="how many images (default: 12)")
    parser.add_argument(
        "--source",
        choices=("google", "openverse", "urls"),
        default="google",
        help="where to search (default: google)",
    )
    parser.add_argument("--urls-file", type=Path, help="text file of image URLs, for --source urls")
    parser.add_argument("--images-root", type=Path, default=IMAGES_ROOT, help=f"default: {IMAGES_ROOT}")
    parser.add_argument("--help-google", action="store_true", help="show Google API setup instructions")
    args = parser.parse_args(argv)

    if args.help_google:
        print(GOOGLE_HELP)
        return 0
    if not args.pack:
        parser.error("a pack name is required (e.g. kpop-demon-hunters)")
    if args.source != "urls" and not args.query:
        parser.error("--query is required unless --source urls is used")
    if args.source == "urls" and not args.urls_file:
        parser.error("--urls-file is required with --source urls")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", args.pack):
        parser.error("pack name may only contain letters, numbers, dots, dashes and underscores")

    pack_dir = args.images_root / args.pack
    print(f"\n  pack    {pack_dir}")
    print(f"  source  {args.source}")
    if args.query:
        print(f"  query   {args.query!r}")
    print(flush=True)  # keep this header ahead of anything written to stderr

    try:
        if args.source == "google":
            results = search_google(args.query, args.count)
        elif args.source == "openverse":
            results = search_openverse(args.query, args.count)
        else:
            results = read_urls(args.urls_file, args.count)
    except FetchError as exc:
        print(f"  {exc}\n", file=sys.stderr)
        return 1

    if not results:
        print("  no results — try a different query or source\n")
        return 1

    saved = download(results, pack_dir, args.query or args.pack)
    if saved:
        write_credits(pack_dir, args.query or "(url list)", args.source, saved)
        total = len([p for p in pack_dir.iterdir() if p.suffix.lower() in ALLOWED_TYPES.values()])
        print(f"\n  {len(saved)} new image(s); {total} in the pack")
        print(f"  credits written to {pack_dir / 'CREDITS.md'}")
        print(f"\n  play with it:\n    python3 play.py --images {pack_dir}\n")
        return 0

    print("\n  nothing downloaded\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
