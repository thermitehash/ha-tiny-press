<p align="center">
  <img src="custom_components/tiny_press/brand/logo.png" alt="Tiny Press" height="96">
</p>

# Tiny Press

A Home Assistant integration that turns an Epson receipt printer into a household fun-printer. It prints mazes, word searches, math strips, jokes, fun facts, notes and pictures today; adult puzzles, bedtime stories and a morning slip are coming. Everything is printed on demand: from buttons, actions, Assist voice phrases or Siri.

- **Printer:** Epson TM-m30III (other ESC/POS printers that answer `DLE EOT` on port 9100 should work)
- **Paper:** 80 mm (576 dots, the default) or 58 mm (420 dots)
- **Home Assistant:** 2026.11.0 or newer
- **Nothing prints automatically.** Tiny Press ships no schedules or time-based automations.

> **Status: v0.4.0.** Adult puzzles (sudoku, crossword, cryptogram, puzzle pack) on top of v0.3.0. **v0.3.0:** Kid pack (profiles, maze, word search, math strip, jokes and fun facts), a dashboard card with kid mode, kid-mode print limits, previews and answer keys. See the [roadmap](docs/roadmap.md) for what's next.

<!-- Screenshot placeholders -->
<!-- ![Device page](docs/images/device.png) -->
<!-- ![A printed maze](docs/images/maze.jpg) -->

## 1. Printer network setup

1. Connect the TM-m30III to your network (Ethernet, or Wi-Fi on Wi-Fi models).
2. Find its IP address in your router's list of clients, or print the printer's network status sheet (see the Epson manual for the button sequence).
3. Give the printer a fixed address: either a **DHCP reservation** in your router (recommended) or a static IP set in the printer's web page (`http://<printer-ip>/`, under **Network → TCP/IP**).
4. Confirm raw printing on port 9100 is open. From a computer on the same network, run `nc -vz <printer-ip> 9100`; it should report "succeeded" or "open". Port 9100 is enabled by default on TM printers.
5. **58 mm paper:** fit the 58 mm roll guides that came with the printer, then change the paper width in the printer's settings (TM-m30III Utility or software setting mode). Choose 58 mm in Tiny Press too. Epson warns against switching back to 80 mm after long use at 58 mm.

## 2. Install with HACS

1. In HACS, open the menu (⋮) → **Custom repositories**.
2. Add `https://github.com/thermitehash/ha-tiny-press` with type **Integration**.
3. Install **Tiny Press** and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Tiny Press**. Enter the printer's IP address (port 9100), choose the paper width, and leave **Print a test page now** ticked.

If DHCP discovery sees an Epson device that answers receipt-printer status requests, it appears under **Discovered**.

### Options

| Option | Default | What it does |
|---|---|---|
| Longest single print | 600 mm | Any print longer than this is trimmed and ends with a "trimmed" note, so a runaway print can't empty the roll. |
| Status check interval | 60 s | How often paper and cover status are read. Status is never read while a job is printing. |
| AI task entity | none | Optional. Any `ai_task` entity (for example the Anthropic integration's). Used for bedtime stories in a later version. |
| Weather entity | none | Used by the Weather print. Not needed if you only have one weather entity. |
| Use AI for jokes and fun facts | off | Off: jokes and facts come from bundled, human-written lists (facts from NOAA, NASA and the National Park Service, with credits). On: the AI is asked first. |

### Profiles

Open **Settings → Devices & services → Tiny Press → Configure** to add, edit or remove people.

| Kid profile | |
|---|---|
| Name | Shown on the Kid profile select; may be used in stories later |
| Reading grade | K–5 (default 3). Sets word lists, grid size and math level. |
| Interests | Free text such as `dinosaurs, space, horses`. Themed words appear in word searches (and in AI jokes if switched on). |
| Stretch | Makes puzzles one grade harder (reading stays at their grade) |
| Spelling list (to-do list) | Optional: a `todo` list, one word per item. Check a word off when it's learned; prints use the unchecked words. Add words by voice: "Add *because* to Rosie's spelling list". |
| Spelling words | Optional typed list (commas or new lines), used when no to-do list is set |

An adult profile has a name and a default puzzle difficulty (used by the adult puzzles). Add as many profiles as you like, for example a younger sibling later.

What each grade gets:

| Grade | Word search | Math strip |
|---|---|---|
| K–1 | 10×10, across and down | add/subtract within 10 (K) or 20 (1) |
| 2 | 10×10, across and down | two-digit add/subtract, every problem needs regrouping |
| 3 | 10×10, plus diagonals | adds ×/÷ facts to 10 and two word problems |
| 4–5 | 12×12, more diagonals | bigger numbers, ×/÷ to 12, multi-digit × |

Every math strip ends with a harder ★ bonus problem. Kid sudoku (numbers) is 4×4 for K–1, 6×6 for grades 2–3, and a harder 6×6 for grades 4–5.

## 3. Entities

| Entity | What it shows |
|---|---|
| `binary_sensor.tiny_press_online` | On when the printer answers and is online |
| `sensor.tiny_press_paper` | `ok`, `near_end`, `out`, `cover_open` or `offline` |
| `sensor.tiny_press_paper_used` | Millimetres printed in total (estimated from each print's length) |
| `sensor.tiny_press_last_print` | Type of the last print. Attributes: `print_id`, `printed_at`, `length_mm`, `profile`, `difficulty` |
| `button.tiny_press_maze` | Prints a maze at the selected difficulty |
| `button.tiny_press_word_search` | Prints a word search for the selected kid |
| `button.tiny_press_math` | Prints a math strip for the selected kid |
| `button.tiny_press_joke` | Prints a joke (punchline upside down below a fold line) |
| `button.tiny_press_kid_pack` | Prints a maze, word search and math strip in one go |
| `button.tiny_press_kid_sudoku` | Prints a 4×4 or 6×6 number sudoku |
| `button.tiny_press_spelling` | Prints unscramble and missing-letter practice from the kid's spelling list |
| `button.tiny_press_spelling_search` | Prints a word search of the kid's spelling list |
| `button.tiny_press_sudoku` | Prints a 9×9 sudoku (difficulty from the Sudoku difficulty select) |
| `button.tiny_press_crossword` | Prints a criss-cross crossword for the selected adult |
| `button.tiny_press_cryptogram` | Prints a cryptogram from a public-domain quote |
| `button.tiny_press_puzzle_pack` | Prints sudoku, crossword and cryptogram in one go |
| `button.tiny_press_weather` | Prints current weather and a forecast of up to 10 days |
| `button.tiny_press_answers` | Prints the answer key for the newest puzzle |
| `button.tiny_press_test_page` | Prints the test page |
| `sensor.tiny_press_kid_prints_left_today` | Kid prints left today when kid-mode limits are on. Attributes: `next_print_at`, `paper_left_mm`, `blocked_reason` |
| `select.tiny_press_kid_profile` | Who the buttons print for |
| `select.tiny_press_adult_profile` | Who the adult puzzles are for |
| `select.tiny_press_maze_difficulty` | Easy, medium or hard |
| `select.tiny_press_sudoku_difficulty` | Easy, medium or hard (defaults to the adult's difficulty) |

If the printer is unreachable for more than 24 hours, a **Repairs** issue appears. It clears itself once the printer answers again.

Every printout ends with a small footer: the print type, difficulty, date and a short ID such as `#K7Q2`. Use the ID to match answer keys later.

## 4. Actions

Every action returns response data, so a script or an iOS Shortcut can speak the result:

```yaml
print_id: K7Q2
type: maze
profile: null
length_mm: 148.5
truncated: false
```

Jokes and facts also return `setup`, `punchline` and `source` (`ai` or `offline`), so a Shortcut can read the joke aloud. A kid pack returns `print_ids` for its three puzzles.

Each successful or failed print also fires the event `tiny_press_printed` with `type`, `print_id`, `profile` and `success`.

If you have more than one Tiny Press printer, add `config_entry_id` to choose one.

### `tiny_press.print`

This is the general entry point that every button and voice phrase uses.

| Field | Notes |
|---|---|
| `type` | `maze`, `word_search`, `math`, `joke`, `fact`, `kid_pack`, `kid_sudoku`, `spelling`, `spelling_search`, `sudoku`, `crossword`, `cryptogram`, `puzzle_pack`, `weather` or `test_page` |
| `words` | For `spelling` and `spelling_search`: words to practice. Empty uses the kid profile's spelling list. |
| `profile` | Kid profile name for word searches, math, jokes and kid packs. Empty uses the Kid profile select. |
| `difficulty` | For mazes (and the maze in a kid pack). Loose words work: `easy`, `medium`, `hard`, `harder`, `tricky`, `a little harder`. Empty uses the Maze difficulty select. |
| `seed` | The same seed prints the same puzzle again (and the same bundled joke) |

```yaml
action: tiny_press.print
data:
  type: maze
  difficulty: tricky
response_variable: printed
```

```yaml
action: tiny_press.print
data:
  type: kid_pack
  profile: Rosie
```

### `tiny_press.preview`

Draws a print without printing it. Returns `image` (a PNG data URI), `seed` and the usual fields. Call `tiny_press.print` with the same `seed` to print exactly what you saw.

### `tiny_press.print_answers`

Prints the answer key for the newest puzzle, or for a footer ID: `print_id: K7Q2`. Answer keys are kept for the last 20 puzzles.

### `tiny_press.print_text`

```yaml
action: tiny_press.print_text
data:
  title: Grocery run
  text: |
    Milk
    Eggs
    Something fun
  size: normal   # small, normal or large
```

### `tiny_press.print_image`

Prints a picture, dithered to black and white at the paper width. The file must be under `/media` or `/config/www`.

```yaml
action: tiny_press.print_image
data:
  path: /config/www/drawings/rocket.png
```

## Dashboard card

Tiny Press includes a dashboard card. It loads automatically; there's nothing extra to install. Edit a dashboard, choose **Add card**, and search for **Tiny Press**.

```yaml
type: custom:tiny-press-card
title: Rosie's printer
kid_mode: true          # hold-to-print, no settings or answers, shows limits
show_preview: false     # true: see the print first, then Shuffle or Print
buttons: [maze, word_search, math, kid_sudoku, spelling, joke, kid_pack, sudoku, crossword, cryptogram, puzzle_pack, weather]
# ignore_limits: true   # for a parents' dashboard
```

<!-- ![Dashboard card](docs/images/card.png) -->

## Kid-mode limits

Under **Configure → Kid-mode limits** you can turn on a wait between prints (default 2 minutes), prints per hour (4), prints per day (10) and a daily paper budget (1.5 m).

- **Who they apply to:** kid prints from every button, card, action, voice phrase and Siri shortcut. Counts reset at midnight.
- **What she sees:** when a print is blocked, she gets a friendly message ("Just a moment! The next print is ready at 3:42 PM"), and Tiny Press fires `tiny_press_rate_limited` so you can be notified.
- **Parents skip the limits** with `ignore_limits: true`:

```yaml
action: tiny_press.print
data:
  type: kid_pack
  ignore_limits: true
```

## 5. Voice and Siri

Assist voice phrases (an automation blueprint) and Siri shortcuts arrive in **v0.7.0**.

> **Heads-up for later:** the voice phrases use sentence triggers, which only run when Home Assistant's built-in conversation agent handles the sentence. If your Assist pipeline uses Claude/Anthropic (or another LLM) as its agent, turn on **"Prefer handling commands locally"** in the pipeline settings, or the phrases won't work.

## 6. Thermal paper notes

- Thermal prints **fade over months**, faster in sunlight, heat or contact with vinyl and plastic sleeves. Photocopy anything worth keeping.
- Buy **BPA-free and BPS-free** rolls (often sold as "phenol-free"). Kids handle these prints.
- Use 80 mm wide rolls (or 58 mm with the roll guides fitted); the Epson manual gives the largest roll diameter that fits. Store spare rolls somewhere cool and dark.

## How it works

- **Transport:** raw ESC/POS over TCP port 9100 using asyncio, with no drivers. Epson's ePOS-Print HTTP endpoint isn't used, because port 9100 already covers every command Tiny Press needs, including real-time status (`DLE EOT`).
- **Rendering:** each printout is drawn as a 1-bit Pillow image at exactly the paper's dot width and sent as `GS v 0` raster in 128-row bands. Rendering runs in Home Assistant's executor, never in the event loop.
- **Queue:** one `asyncio.Lock` per printer, so two prints never interleave. If the connection fails before any byte is sent, the job is retried once; a job that was partly sent is never resent.
- **Fonts:** [Atkinson Hyperlegible](https://www.brailleinstitute.org/freefont/) and [JetBrains Mono](https://www.jetbrains.com/lp/mono/), both under the SIL Open Font License 1.1 (license files are in `custom_components/tiny_press/render/fonts/`). The logo wordmark uses DM Sans Bold (SIL OFL 1.1).

## Development

```sh
pip install -r requirements_test.txt
ruff format . && ruff check .
python -m pytest tests --cov=custom_components.tiny_press
python script/gen_translations.py   # after editing strings.json
./script/render_brand.sh            # after editing assets/*.svg (needs rsvg-convert, ImageMagick, optipng)
```

Versioning is SemVer. `manifest.json` is the single source of truth: bump the minor version for a feature or phase, and the patch version for fixes. CI fails a pull request that changes `custom_components/` without bumping the version. Release notes go in `docs/releases/vX.Y.Z.md`.

## Content sources

Bundled content comes from sources that allow redistribution: fun facts from NOAA, NASA and the National Park Service (U.S. government works, public domain), K–3 words from the Dolch sight-word lists, and cryptogram quotes from public-domain works (Roosevelt, Muir, Lincoln, Shakespeare) as collected by the National Park Service. Jokes and the NYT-style crossword clues were written for Tiny Press. See [`data/LICENSE.md`](custom_components/tiny_press/data/LICENSE.md) for every source.

## License

MIT. See [LICENSE](LICENSE).
