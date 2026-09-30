# 👺 Math Demon Hunters · 🔮 Math Jewel Hunters

Two maths practice games for kids, built on one engine:

- **Math Demon Hunters** — *subtraction*, themed after *Kpop Demon Hunters*:
  neon Honmoon skies, floating talismans, and a demon that cracks apart as each
  fact gets sealed.
- **Math Jewel Hunters** — *multiplication*, themed after *Inuyasha*: a forest
  night under a spirit barrier, drifting paper charms, and a youkai guarding the
  shards of the Shikon Jewel. Problems are drawn as piles of shards to count.

Same scoring, same scheduler, same screens — a different operation and a
different skin. Python backend, browser front end, **no dependencies to
install**.

```bash
git clone git@github.com:sb-2011/math_demon_hunters.git
cd math_demon_hunters

python3 play.py                   # subtraction    → http://127.0.0.1:8765/
python3 play_multiplication.py    # multiplication → http://127.0.0.1:8766/
```

A browser window opens on the game you launched. Press `Ctrl+C` in the terminal
to stop. Both can be open at once: different ports, separate progress files,
separate picture choices.

Everything below describes both games; where the multiplication one differs it
is gathered under [The multiplication hunt](#the-multiplication-hunt).

That's the whole setup. There is no `pip install`, no virtualenv and no build
step — the app is written against the Python standard library, so any machine
with **Python 3.10 or newer** can run a fresh clone straight away. (macOS and
most Linux distributions already ship one; on Windows use `python` instead of
`python3`.)

A small demo picture pack, `images/example-theme`, is included so the game is
complete on a fresh clone. Drop your own pictures in for the real thing —
see [Picture packs](#picture-packs).

---

## The multiplication hunt

`python3 play_multiplication.py` opens **Math Jewel Hunters**. The engine is the
same one: the same points, the same correction loop, the same scheduler, the
same countdown and hunt clock. What changes is the operation and the skin.

Both sides of the forge are factors, read as groups:

| You set                        | The pool becomes                            |
| ------------------------------ | ------------------------------------------- |
| groups `3`, in each `1–10`     | `3×1, 3×2, … 3×10` — the three times table  |
| groups `2–5`, in each `4`      | `2×4, 3×4, 4×4, 5×4`                        |
| groups `2–4`, in each `1–8`    | every pair from the two ranges              |

Nothing is left out — no pair of factors goes anywhere a kid hasn't been taught
— so there is no *allow answers below zero* switch here. It has one limit of its
own instead: the answer pad holds three digits, so a hunt whose biggest product
runs past **999** is refused before it starts.

### The strategy picture: equal groups

This is what multiplication is drawn as. When a problem is a handful of piles,
the hunt draws them — `4 × 6` is four piles of six shards of the Shikon Jewel,
with a box under each pile:

```
   ╭───────╮  ╭───────╮  ╭───────╮  ╭───────╮
   │ ◈ ◈ ◈ │  │ ◈ ◈ ◈ │  │ ◈ ◈ ◈ │  │ ◈ ◈ ◈ │
   │ ◈ ◈ ◈ │  │ ◈ ◈ ◈ │  │ ◈ ◈ ◈ │  │ ◈ ◈ ◈ │
   ╰───────╯  ╰───────╯  ╰───────╯  ╰───────╯
      (6)  +     (6)  +     (6)  +     (6)        ← count each pile
   └──────────── every pile together ─────────┘   ← that total is the answer
```

Count a pile into its box and the pile lights up; with all of them filled, the
addition is still yours to do — the same shape as the subtraction bridge. Two
strategies cover it:

- **Equal groups** — up to 5 piles of up to 10, drawn as written.
- **Turn it round** — too many piles to lay out but few enough in each to swap:
  `9 × 2` is drawn as two piles of nine, captioned with why that is allowed.
  Turn-around facts are worth learning in their own right.

Beyond that (`7 × 8` and friends) no picture is offered, the same way the
subtraction hunt only draws the problems its bridge covers.

### Same game, different words

Demons are **youkai**, sealing a problem is **purifying a shard**, HQ is
**camp**, and clearing a hunt makes the jewel whole. Progress, artwork and
preferences are kept apart from the other game's, so the two never mix.

---

## How a hunt works

Each side of the problem is either **one number** or **a range**, set
independently. The pool is every pair the two sides make:

| You set                                    | The pool becomes                        |
| ------------------------------------------ | --------------------------------------- |
| start `10`, take away `0–9`                 | `10−0, 10−1, 10−2, … 10−9`              |
| start `5–12`, take away `3`                 | `5−3, 6−3, 7−3, … 12−3`                 |
| start `10–12`, take away `0–4`              | `10−0 … 10−4, 11−0 … 11−4, 12−0 … 12−4` |
| start `7`, take away `4`                    | `7−4` on its own                        |

(That's the subtraction hunt; the multiplication one reads its two sides as
groups — see [above](#the-multiplication-hunt).)

Pairs that would go below zero — `3−8` and friends — are left out, unless you
switch on **allow answers below zero**; that makes a separate hunt with its own
progress. A pool can hold up to **64** problems, counted after the below-zero
pairs are dropped; the forge shows the count and the full list before you start.

### Scoring

- Correct answer: **+1 point** on that problem
- Wrong answer: **−2 points** on that problem
- Points never drop below **0** and never rise above **3**
- A problem is **sealed** at 3 points (**purified**, in the jewel hunt)
- The series is **mastered** when every problem in the pool is sealed →
  celebration, then back to HQ

Miss a sealed problem and the seal cracks: it drops to 1 and has to be earned
back. Mastery means all of them are at 3 *at the same time*.

A missed problem is not swapped out for another one. The correct answer is shown
and the *same problem comes straight back* — as many times as it takes — so every
round ends on the right answer and the problem is back on 1 point before the hunt
moves on. Fixing it that way doesn't count as knowing it: the problem is queued to
return a couple of turns later to be answered cold.

### Strategy pictures

Some problems have a way in — a trick that turns one hard problem into a few
easy ones. When a problem has one, the hunt draws it under the equation. This is
on by default; the **Show the strategy picture** switch at HQ turns it off.

Each game brings its own: the multiplication hunt draws
[equal groups](#the-strategy-picture-equal-groups); the subtraction hunt has one
strategy so far:

**Bridge through 10** — for a teen number take away a single digit (minuend
`11–20`, subtrahend `1–9`). The jump from one number to the other always crosses
10, so 10 makes a stop along the way:

```
20 − 8  =  (10 − 8) + (20 − 10)  =  2 + 10  =  12
```

On a number line those two smaller problems are simply the two hops that make up
the distance between the numbers:

```
        ╭──╮         ╭─────────────╮
        │ 2│         │      10     │        ← one box to fill in per hop
   ──●──┴──●─────────┴─────────────●──
     8    10                      20
     └──────── the whole jump ─────┘        ← that distance is the answer
```

Each hop has a box. Fill one in and its arc lights up and draws itself; get one
wrong and it just shakes — **nothing here is ever scored**, it's scratch paper.
With both hops filled, add them and type the total as your answer. Skipping the
picture and answering straight off is always fine; miss the answer and the whole
bridge is worked out on screen, then the same problem comes back with fresh boxes
to work through.

Adding a strategy means adding one object to that game's `strategies.js`
([subtraction](src/mathhunters/web/subtraction/strategies.js),
[multiplication](src/mathhunters/web/multiplication/strategies.js)): when it
applies, the smaller problems it breaks into, and how to draw it. The app
supplies the boxes, the checking, the sum, and the reveal. The first strategy
that applies to a problem is the one shown.

### Hunt time

Every hunt keeps its own clock, shown as **TIME** in the top-right while
playing. It counts only time actually spent hunting:

- it starts when the hunt is opened and ticks while playing
- it **pauses** on the way back to HQ, and picks up where it left off on resume
- it also pauses if the tab is hidden or closed, so a browser left open
  overnight doesn't bank hours
- it **freezes** the moment the series is mastered, and the total appears on the
  celebration screen and on the hunt's card at HQ
- replaying a mastered hunt starts a fresh clock, so times are comparable

The total is saved with the rest of the progress, so a hunt resumed next week
continues the same clock. It is kept on the server rather than in the browser,
which means it can't drift if the page is reloaded.

### Beat the clock (optional)

Flip **Beat the clock** on the home screen to give each problem a countdown —
10 seconds by default, adjustable from 3 to 120. A bar drains above the problem
and turns magenta with an audible tick for the last three seconds.

Letting the clock run out scores exactly like a wrong answer: **−2**, the correct
answer is shown, and the same problem comes back to be answered. That second go
is **untimed** — fixing an answer isn't a speed test, and a countdown that kept
expiring could never be answered right. The setting is a launch choice, not part
of the hunt's identity — the same hunt can be replayed with or without the clock,
and its progress carries over either way.

### Keeping problems fresh

The whole point is recall, so the picker is built around spacing rather than
drilling one fact to death:

1. **Introduction sweep** — every problem in the pool is asked once before
   anything repeats, so nothing gets crowded out by an early struggle.
2. **Answer it before moving on** — a missed problem stays up until it is
   answered correctly, so the round ends on the right answer rather than on the
   mistake, and the problem starts climbing back at once.
3. **Relapse queue** — once corrected, that problem comes back about two turns
   later to be answered cold, with the answer no longer on screen.
4. **Weighted rotation** — after that, each problem's chance of being picked
   rises with how far it is from 3 points, how long it has gone unseen, and how
   much recent trouble it has caused.
5. **Expanding spacing** — the more solid a problem is, the longer the gap
   before it comes round again.
6. **Review of the shaky ones** — a problem that was *missed at some point* keeps
   coming back for re-testing even after it's sealed, so a lapse is caught rather
   than hidden. A problem answered correctly every time it was asked is treated
   as known and retires for the rest of the hunt: re-asking it is padding, not
   practice. Reviews are also rate-limited and never take priority over a
   problem that isn't finished yet.
7. **Slow but right** — a correct answer that took more than 6 seconds still
   scores +1, but the problem is treated as not-yet-fluent and returns sooner.

The upshot: a kid who gets everything right is asked each problem exactly 3
times and finishes in the minimum number of turns. Extra repetition falls only
where something was actually fumbled.

Progress is saved after every answer, so closing the window mid-hunt loses
nothing.

---

## The screens

**HQ (home)** — forge a new hunt (a number or a range on each side, live preview
of the problem pool, countdown option, picture pack), or pick up a past hunt.
Each past hunt shows a progress ring, how many demons are sealed, and how many
times it's been cleared. Mastered hunts get a crown and a **Replay** button.
(The jewel hunt calls this screen *camp*, and counts shards purified.)

**The hunt** — the picture (or the drawn foe), the countdown if it's on, the
problem, the strategy picture when one applies, three point pips for the current
problem, a hunt clock, a combo counter, and the
*Hunt Board* at the bottom showing every problem in the pool with its points, so
a kid can see exactly what's left. Answer with the on-screen keypad or the real
keyboard (digits, `−`, `Backspace`, `Enter`, `Esc` to quit to HQ). Tapping a box
in the strategy picture types there instead; `Esc` steps back out of it.

**Mastered** — confetti, a spinning seal, a gallery of every picture from the
hunt, and the run's stats. It stays up for as long as you like; **Return to HQ**
dismisses it (or press Enter).

---

## Picture packs

`images/` holds one folder per theme — a movie, a show, anything. Pick one when
you launch:

```bash
python3 play.py --images images/kpop-demon-hunters
```

Sibling packs are also offered on the home screen, so you can switch themes
without restarting.

```
images/
├── kpop-demon-hunters/     ← put movie pictures here
├── example-theme/          ← a small drawn demo pack, included
└── README.md
```

> **Your own pictures are not committed.** `images/` is gitignored apart from
> the demo pack, so cloning onto another machine gives you the app but not your
> movie stills — copy that folder across by hand, or re-run the fetch script.
> If this repo is **private** and you'd rather they travelled with it, add this
> to `.gitignore` and commit them:
>
> ```
> !images/kpop-demon-hunters/**
> ```
>
> Don't do that on a public repo — see the note at the end of this section.

Each problem is bound to one picture **by its position in the pool**, so
`10 − 7` always shows the same image for the whole hunt. That's deliberate: the
picture becomes a second retrieval cue alongside the numbers. The picture is the
card you face, it takes the hit on a correct answer, a gold **SEALED** stamp
slams onto it at 3 points, and every picture from the hunt reappears in the
victory gallery. A pack smaller than the pool just repeats.

### Getting pictures

```bash
# Google image search — the official Custom Search JSON API.
# Needs two free credentials once: python3 scripts/fetch_images.py --help-google
python3 scripts/fetch_images.py kpop-demon-hunters -q "Kpop Demon Hunters movie" -n 12

# Openly licensed images — no key, no setup
python3 scripts/fetch_images.py space -q "nebula" -n 10 --source openverse

# URLs you picked by hand (right-click → copy image address)
python3 scripts/fetch_images.py my-theme --source urls --urls-file picks.txt
```

The script writes a `CREDITS.md` in the pack recording where each file came from.
Dragging image files into a folder works just as well.

**Why not scrape Google Images?** There's no public endpoint for it and scraping
the results page violates Google's terms (and breaks whenever the markup
changes). The Custom Search JSON API is the supported route and its free tier —
100 queries/day, ~1000 images — is far more than this needs. Openverse is there
for when you want something with a clean licence and zero setup.

**On movie stills:** frames from a film belong to the studio. A handful saved
locally so your own kid can practise subtraction is ordinary personal use;
shipping a copy of this app with them bundled in is not. `images/` is gitignored
for that reason — the structure is tracked, the pictures aren't.

---

## Options

```bash
python3 play.py --help                  # or play_multiplication.py --help

  --game GAME          subtraction (default) or multiplication
  --port PORT          preferred port (default: 8765 / 8766, next free one is used)
  --host HOST          bind address (default: 127.0.0.1, loopback only)
  --images DIR         picture pack to play with, e.g. images/example-theme
  --data-dir DIR       where progress is saved
  --assets-dir DIR     folder scanned for custom artwork
  --no-browser         don't open a browser window
```

The two launchers are just `--game` with a default: `python3 play.py` and
`python3 play_multiplication.py` are `python3 -m mathhunters --game subtraction`
and `--game multiplication` (with `src/` on `PYTHONPATH`).

**Progress files** — plain JSON, safe to back up, copy between machines, or
delete to start fresh:

| Game           | File                                                        |
| -------------- | ----------------------------------------------------------- |
| subtraction    | `~/.math-demon-hunters/progress.json`                       |
| multiplication | `~/.math-jewel-hunters/progress-multiplication.json`        |

If one ever gets corrupted the app renames it to `*.corrupt.json` and starts
clean rather than refusing to launch. Hunts saved by an earlier version — back
when one side of the subtraction was always a single fixed number, and before
there was a second game — are upgraded on load and keep every problem and point
they had. The two games never read each other's hunts: their ids carry the
operation, and a store skips anything that isn't its own.

---

## Custom artwork

Separate from picture packs, `assets/` replaces fixed pieces of the interface —
the backdrop, the foe, the logo, the sound effects. Everything there is drawn in
code by default, so both games look complete with the folder empty. The
subtraction game reads `assets/`, the multiplication game `assets/jewel/`. See
[`assets/README.md`](assets/README.md) for the slot names.

---

## Layout

```
math-demon-hunters/
├── play.py                     # launcher — subtraction
├── play_multiplication.py      # launcher — multiplication
├── assets/                     # optional drop-in UI art & audio
│   └── jewel/                  # …the multiplication game's own
├── images/                     # picture packs, one folder per theme
├── scripts/fetch_images.py     # downloads pictures into a pack
├── src/mathhunters/
│   ├── engine.py               # scoring rules, scheduler, and the operations
│   ├── games.py                # the two trainers: operation + skin + where it saves
│   ├── storage.py              # JSON progress file (atomic writes), one per game
│   ├── server.py               # stdlib HTTP server + JSON API
│   ├── packs.py                # discovers image packs under images/
│   ├── assets.py               # scans a game's assets folder for known slots
│   └── web/
│       ├── app.js              # the whole front end, shared by both games
│       ├── theme.css           # the layout, shared by both games
│       ├── subtraction/        # index.html · skin.css · game.js · strategies.js
│       └── multiplication/     # the same four files, Inuyasha side
└── tests/                      # engine rules, scheduler, HTTP API, both skins
```

Adding a third trainer is an `Operation` in `engine.py`, an entry in `games.py`,
and a folder of those four skin files. Nothing in `app.js` knows which operation
it is drilling: it reads the operator, the words, the colours and the forge rules
from the game's `game.js`.

The game rules live entirely in `engine.py` and are covered by tests — the
tunable constants (mastery target, penalties, spacing) are all named at the top
of that file if you want to adjust the difficulty.

## Tests

The app needs nothing, but the test suite uses pytest:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

170 tests covering the scoring rules, the correction loop on a miss, the
countdown, the hunt clock's pause/resume behaviour, the scheduler's freshness
guarantees, save/restore, image packs (including awkward filenames), the HTTP
API, and both games — that they keep their hunts and progress apart, and that
each skin gives the shared front end everything it reads.

The strategy pictures and the skin configs are browser code, so their checks run
under `node` (skipped when node isn't installed):

```bash
node tests/strategies_check_subtraction.js
node tests/strategies_check_multiplication.js
node tests/game_config_check.js
```

---

*Not affiliated with or endorsed by the makers of Kpop Demon Hunters or Inuyasha.
All artwork in this repo is original and drawn in CSS/SVG.*
