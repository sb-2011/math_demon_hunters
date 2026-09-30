# Custom artwork (optional)

Both games are complete with this folder empty — every visual is drawn in code.
Drop a file here with one of the names below and the app uses it instead, from
the next page reload. Nothing is downloaded and nothing is uploaded.

Each trainer has its own folder, so they can look different:

| Folder          | Used by                                             |
| --------------- | --------------------------------------------------- |
| `assets/`       | Math Demon Hunters — `python3 play.py`              |
| `assets/jewel/` | Math Jewel Hunters — `python3 play_multiplication.py` |

The slot names are the same in both (`--assets-dir` points either game at any
folder you like).

| File name      | What it replaces                                    |
| -------------- | --------------------------------------------------- |
| `backdrop.*`   | The night-sky background (a dark overlay is applied) |
| `logo.*`       | Artwork above the title on the home screen           |
| `demon.*`      | The foe on the play screen — the demon, or the youkai (replaces the SVG mask) |
| `hunter.*`     | Reserved for a hunter character                      |
| `victory.*`    | Artwork on the celebration screen                    |
| `sfx-correct.*`| Sound for a correct answer                           |
| `sfx-wrong.*`  | Sound for a wrong answer                             |
| `sfx-victory.*`| Sound when a series is mastered                      |
| `music.*`      | Background music (loops quietly, respects the mute button) |

Images: `.png` `.jpg` `.jpeg` `.webp` `.gif` `.svg` `.avif`
Audio: `.mp3` `.ogg` `.wav` `.m4a`

Example: saving a picture as `demon.png` in this folder swaps out the demon in
the subtraction game; `assets/jewel/demon.png` swaps out the youkai in the
multiplication one.

Files with any other name are ignored and are not served — only the slots above
are reachable from the browser.

A note on sourcing: use art you have the right to use. Official Kpop Demon
Hunters and Inuyasha artwork belongs to its rights holders, so it's fine for your
own kid's copy at home, but don't redistribute the app with that artwork bundled
in.
