"""Image packs: folders of pictures that get woven into the hunt.

``images/`` holds one subfolder per pack (``images/kpop-demon-hunters/``,
``images/space/``, …).  One is selected at launch::

    python3 play.py --images images/kpop-demon-hunters

Each problem in a pool is bound to one image from the pack, so ``10 − 7`` always
shows the same picture.  That stable pairing is the point: a kid ends up
recognising the fact by its picture, which is another retrieval cue on top of
the numbers.  Packs with fewer images than the pool simply repeat.
"""

from __future__ import annotations

import urllib.parse
from pathlib import Path

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".svg")

MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".avif": "image/avif",
    ".svg": "image/svg+xml",
}

MAX_IMAGES_PER_PACK = 200


def is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTS


def pack_images(pack_dir: Path) -> list[str]:
    """Sorted image file names inside one pack folder."""
    if not pack_dir.is_dir():
        return []
    names = sorted(p.name for p in pack_dir.iterdir() if is_image(p) and not p.name.startswith("."))
    return names[:MAX_IMAGES_PER_PACK]


def list_packs(images_root: Path) -> list[dict]:
    """Every pack under ``images_root`` that actually holds pictures."""
    if not images_root.is_dir():
        return []
    packs = []
    for child in sorted(images_root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        names = pack_images(child)
        if not names:
            continue
        packs.append(
            {
                "name": child.name,
                "count": len(names),
                "images": [image_url(child.name, name) for name in names],
            }
        )
    return packs


def image_url(pack_name: str, file_name: str) -> str:
    """URL for one pack image.

    Pictures saved from a browser routinely have spaces, ``#``, ``&``,
    parentheses or non-ASCII in their names, so every segment is percent-encoded
    here -- otherwise the browser rewrites or truncates the request and the
    image silently fails to load.
    """
    quote = urllib.parse.quote
    return f"/pack/{quote(pack_name, safe='')}/{quote(file_name, safe='')}"


def content_type(path: Path) -> str:
    return MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")


def resolve_selection(selected: Path | None) -> str | None:
    """Turn a ``--images`` path into the pack name the UI should start on."""
    if selected is None:
        return None
    selected = selected.expanduser()
    if not selected.is_dir():
        raise FileNotFoundError(f"image folder not found: {selected}")
    if not pack_images(selected):
        raise ValueError(f"no images found in {selected} (looked for {', '.join(IMAGE_EXTS)})")
    return selected.resolve().name
