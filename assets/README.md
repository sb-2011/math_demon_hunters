# Custom artwork (optional)

The game is complete with this folder empty — every visual is drawn in code.
Drop a file here with one of the names below and the app uses it instead, from
the next page reload. Nothing is downloaded and nothing is uploaded.

| File name      | What it replaces                                    |
| -------------- | --------------------------------------------------- |
| `backdrop.*`   | The night-sky background (a dark overlay is applied) |
| `logo.*`       | Artwork above the title on the home screen           |
| `demon.*`      | The demon on the play screen (replaces the SVG mask) |
| `hunter.*`     | Reserved for a hunter character                      |
| `victory.*`    | Artwork on the celebration screen                    |
| `sfx-correct.*`| Sound for a correct answer                           |
| `sfx-wrong.*`  | Sound for a wrong answer                             |
| `sfx-victory.*`| Sound when a series is mastered                      |
| `music.*`      | Background music (loops quietly, respects the mute button) |

Images: `.png` `.jpg` `.jpeg` `.webp` `.gif` `.svg` `.avif`
Audio: `.mp3` `.ogg` `.wav` `.m4a`

Example: saving a picture as `demon.png` in this folder swaps out the demon.

Files with any other name are ignored and are not served — only the slots above
are reachable from the browser.

A note on sourcing: use art you have the right to use. Official Kpop Demon
Hunters artwork belongs to its rights holders, so it's fine for your own kid's
copy at home, but don't redistribute the app with that artwork bundled in.
