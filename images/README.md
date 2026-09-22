# Image packs

One folder per theme. Each folder is a **pack** — a movie, show, or anything
else. Pick one at launch:

```bash
python3 play.py --images images/kpop-demon-hunters
```

Sibling packs are offered on the home screen too, so you can switch themes
without restarting.

```
images/
├── kpop-demon-hunters/     ← python3 play.py --images images/kpop-demon-hunters
│   ├── 01-rumi.jpg
│   ├── 02-mira.jpg
│   └── CREDITS.md
└── example-theme/          ← copy this shape for a new show or topic
```

Any of `.png` `.jpg` `.jpeg` `.webp` `.gif` `.avif` `.svg`. Sorted by file name,
so a `01-`, `02-` prefix controls the order. Up to 200 images per pack.

## How the pictures are used

Each problem in a pool is bound to one image **by position**, so `10 − 7` always
shows the same picture for the whole hunt. That stable pairing is deliberate: the
picture becomes a second retrieval cue alongside the numbers, which is exactly
what you want for recall practice.

- The picture is the card you face on the play screen, framed in neon.
- It takes the hit animation on a correct answer and rages on a wrong one.
- When that problem hits 3 points, a gold **SEALED** stamp slams onto it.
- Clearing the whole series shows every picture from the hunt in the
  celebration gallery.

A pack with fewer pictures than the pool just repeats them. 8–15 images is a good
number for a 10-problem hunt.

## Getting images

```bash
# Google image search (official API — needs a free key, see --help-google)
python3 scripts/fetch_images.py kpop-demon-hunters -q "Kpop Demon Hunters movie" -n 12

# Openly licensed images, no setup at all
python3 scripts/fetch_images.py space -q "nebula" -n 10 --source openverse

# URLs you picked yourself (right-click → copy image address)
python3 scripts/fetch_images.py my-theme --source urls --urls-file picks.txt
```

Or just drag image files into a folder here — nothing else is required.

## A note on movie stills

Frames from a film belong to the studio. A handful saved locally so your own kid
can practise subtraction is ordinary personal use; shipping a copy of this app
with them bundled in is not. This folder's contents are gitignored for that
reason — the structure is tracked, the pictures are not.
