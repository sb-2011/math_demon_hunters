"""Optional drop-in artwork and sound.

Everything in the app is drawn procedurally, so the game is complete with an
empty ``assets/`` folder.  If a file matching one of the slots below is present
at startup the front end uses it instead of the generated version -- that is the
hook for dropping in your own Kpop Demon Hunters art later.
"""

from __future__ import annotations

from pathlib import Path

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif")
AUDIO_EXTS = (".mp3", ".ogg", ".wav", ".m4a")

MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".avif": "image/avif",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
}

# slot name -> allowed extensions
SLOTS: dict[str, tuple[str, ...]] = {
    "backdrop": IMAGE_EXTS,
    "logo": IMAGE_EXTS,
    "demon": IMAGE_EXTS,
    "hunter": IMAGE_EXTS,
    "victory": IMAGE_EXTS,
    "sfx-correct": AUDIO_EXTS,
    "sfx-wrong": AUDIO_EXTS,
    "sfx-victory": AUDIO_EXTS,
    "music": AUDIO_EXTS,
}


def scan(assets_dir: Path) -> dict[str, str]:
    """Map each filled slot to the URL the browser should request."""
    found: dict[str, str] = {}
    if not assets_dir.is_dir():
        return found
    for slot, exts in SLOTS.items():
        for ext in exts:
            candidate = assets_dir / f"{slot}{ext}"
            if candidate.is_file():
                found[slot] = f"/assets/{candidate.name}"
                break
    return found


def content_type(path: Path) -> str:
    return MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")


def is_allowed(path: Path) -> bool:
    """Only serve files that fill a known slot, and only from the assets dir."""
    stem, ext = path.stem.lower(), path.suffix.lower()
    return stem in SLOTS and ext in SLOTS[stem]
