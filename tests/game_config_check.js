/* Checks that each game's skin supplies everything the shared front end reads.

   app.js is shared by both trainers and takes everything game-specific from
   window.MathHunterGame (web/<game>/game.js).  A missing key there would only
   show up as a broken page, so this check reads app.js, collects every setting
   it touches, and looks for each one in every game's config.

   It also checks the forge rules each game ships against the same limits the
   Python engine enforces, so the preview can never offer a hunt the server
   would refuse.

   Run by tests/test_front_end.py, or on its own with
   `node tests/game_config_check.js`. */

"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const WEB = path.join(__dirname, "..", "src", "mathhunters", "web");
const GAMES = ["subtraction", "multiplication"];

// Mirrors engine.py — the server's answer to "is this hunt allowed?".
const RULES = { max_operand: 999, max_pool_size: 64, mastery_target: 3 };

let checks = 0;
const failures = [];

function check(what, condition) {
  checks += 1;
  if (!condition) failures.push(what);
}

/* --- what app.js expects to find --------------------------------------- */

const appSource = fs.readFileSync(path.join(WEB, "app.js"), "utf8");

const used = (pattern) => {
  const names = new Set();
  for (const match of appSource.matchAll(pattern)) names.add(match[1]);
  return [...names];
};

const words = used(/\bWORDS\.([a-zA-Z_]+)/g);
const palette = used(/\bGAME\.palette\.([a-zA-Z_]+)/g);
const pool = used(/\bGAME\.pool\.([a-zA-Z_]+)/g);
const settings = used(/\bGAME\.(?!palette\b|pool\b|words\b)([a-zA-Z_]+)/g);

check("app.js reads words from the game config", words.length >= 8);
check("app.js reads a palette from the game config", palette.length >= 4);

/* --- every game supplies it -------------------------------------------- */

for (const game of GAMES) {
  const file = path.join(WEB, game, "game.js");
  const sandbox = { window: {} };
  vm.runInNewContext(fs.readFileSync(file, "utf8"), sandbox, { filename: file });
  const config = sandbox.window.MathHunterGame;

  check(`${game}: game.js defines window.MathHunterGame`, !!config);
  if (!config) continue;

  check(`${game}: names itself`, config.id === game);
  check(`${game}: has an operator glyph`, typeof config.glyph === "string" && config.glyph.length === 1);
  check(`${game}: namespaces its saved preferences`, typeof config.storage === "string" && config.storage.length > 0);
  check(`${game}: says whether it goes below zero`, typeof config.negativeOption === "boolean");
  check(`${game}: opens the forge on a shape`, config.sideModes && config.sideModes.m && config.sideModes.s);

  for (const key of settings) {
    check(`${game}: supplies GAME.${key}`, config[key] !== undefined);
  }
  for (const key of words) {
    const value = config.words[key];
    check(`${game}: supplies words.${key}`, value !== undefined && value !== "");
    if (Array.isArray(value)) check(`${game}: words.${key} is not empty`, value.length > 0);
  }
  for (const key of palette) {
    check(`${game}: supplies palette.${key}`, config.palette[key] !== undefined);
  }
  for (const key of pool) {
    check(`${game}: supplies pool.${key}()`, typeof config.pool[key] === "function");
  }

  // The words that go on screen with a number in them.
  check(`${game}: counts one problem in the singular`, /\b1\b/.test(config.words.poolCount(1)) && !/1 \w+s\b/.test(config.words.poolCount(1)));
  check(`${game}: counts several problems in the plural`, /\b7 \w+s\b/.test(config.words.poolCount(7)));

  /* --- the forge rules agree with the server ------------------------- */

  const shape = (m1, m2, s1, s2, allow_negative = false) => ({ m1, m2, s1, s2, allow_negative });
  const ok = (values) => config.pool.validate(values, RULES) === null;

  check(`${game}: a sensible hunt is accepted`, ok(shape(3, 3, 1, 6)));
  check(`${game}: backwards ranges are refused`, !ok(shape(5, 2, 1, 6)) && !ok(shape(2, 5, 6, 1)));
  check(`${game}: negative numbers are refused`, !ok(shape(-1, 3, 1, 6)));
  check(`${game}: numbers past the operand cap are refused`, !ok(shape(1, 1000, 1, 2)));
  check(`${game}: too big a pool is refused`, !ok(shape(1, 12, 1, 12)));
  check(
    `${game}: the pool it counts is the pool it lists`,
    config.pool.count(shape(2, 6, 1, 5)) === config.pool.pairs(shape(2, 6, 1, 5)).length
  );
  check(
    `${game}: an accepted hunt fits inside the pool cap`,
    config.pool.count(shape(2, 6, 1, 5)) <= RULES.max_pool_size
  );

  if (game === "subtraction") {
    check("subtraction: pairs below zero are left out", config.pool.count(shape(0, 3, 5, 9)) === 0);
    check("subtraction: a pool of only below-zero pairs is refused", !ok(shape(0, 3, 5, 9)));
    check("subtraction: below-zero pairs are kept when asked for", ok(shape(0, 3, 5, 9, true)));
  } else {
    check("multiplication: every pair is kept", config.pool.count(shape(2, 4, 0, 3)) === 12);
    check("multiplication: answers past the pad are refused", !ok(shape(30, 30, 40, 40)));
    check("multiplication: the biggest typeable answer is allowed", ok(shape(9, 9, 111, 111)));
  }
}

/* --- every element app.js reaches for is in every skin ----------------- */

// app.js finds elements by id.  A skin missing one would only show up as a
// broken page, so check the ids it uses against both index.html files.  A few
// are optional: only some trainers have anything below zero to allow.
const OPTIONAL_IDS = new Set(["negative-toggle"]);

const ids = used(/\$\("([a-z0-9-]+)"\)/g);
check("app.js reaches for elements by id", ids.length > 20);

for (const game of GAMES) {
  const page = fs.readFileSync(path.join(WEB, game, "index.html"), "utf8");
  const present = new Set([...page.matchAll(/\bid="([a-z0-9-]+)"/g)].map((m) => m[1]));
  const missing = ids.filter((id) => !present.has(id) && !OPTIONAL_IDS.has(id));
  check(`${game}: index.html has every element app.js uses (missing: ${missing})`, missing.length === 0);

  // The page has to load the shared script and its own skin, in that order.
  check(`${game}: loads the shared front end`, page.includes('src="/static/app.js"'));
  check(`${game}: loads its own settings before it`,
    page.indexOf('src="/static/game.js"') > 0 &&
    page.indexOf('src="/static/game.js"') < page.indexOf('src="/static/app.js"'));
  check(`${game}: loads its strategies`, page.includes('src="/static/strategies.js"'));
  check(`${game}: loads the shared layout, then its skin`,
    page.indexOf('href="/static/theme.css"') > 0 &&
    page.indexOf('href="/static/theme.css"') < page.indexOf('href="/static/skin.css"'));
}

/* --- the two games stay out of each other's way ------------------------ */

const configs = GAMES.map((game) => {
  const sandbox = { window: {} };
  const file = path.join(WEB, game, "game.js");
  vm.runInNewContext(fs.readFileSync(file, "utf8"), sandbox, { filename: file });
  return sandbox.window.MathHunterGame;
});

check("the games use different operators", configs[0].glyph !== configs[1].glyph);
check(
  "the games namespace their preferences apart",
  configs[0].storage !== configs[1].storage
);

/* --- report ------------------------------------------------------------ */

if (failures.length) {
  console.error(`${failures.length} of ${checks} checks failed:`);
  for (const failure of failures.slice(0, 20)) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log(`ok — ${checks} checks over ${GAMES.length} game configs`);
