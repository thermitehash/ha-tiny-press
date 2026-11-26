<p align="center">
  <img src="custom_components/tiny_press/brand/logo.png" alt="Tiny Press" height="96">
</p>

# Tiny Press

A Home Assistant integration that turns an Epson receipt printer into a household fun-printer. It prints mazes and notes today; puzzles, math strips, bedtime stories and a morning slip are coming. Everything is printed on demand: from buttons, actions, Assist voice phrases or Siri.

- **Printer:** Epson TM-m30III (other ESC/POS printers that answer `DLE EOT` on port 9100 should work)
- **Paper:** 80 mm (576 dots, the default) or 58 mm (420 dots)
- **Home Assistant:** 2026.11.0 or newer
- **Nothing prints automatically.** Tiny Press ships no schedules or time-based automations.

> **Status: v0.1.0.** Printer connection, status, maze, notes, pictures and test page. See the [roadmap](docs/roadmap.md) for what's next.

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

## 3. Entities

| Entity | What it shows |
|---|---|
| `binary_sensor.tiny_press_online` | On when the printer answers and is online |
| `sensor.tiny_press_paper` | `ok`, `near_end`, `out`, `cover_open` or `offline` |
| `sensor.tiny_press_paper_used` | Millimetres printed in total (estimated from each print's length) |
| `sensor.tiny_press_last_print` | Type of the last print. Attributes: `print_id`, `printed_at`, `length_mm`, `profile`, `difficulty` |
| `button.tiny_press_maze` | Prints a maze at the selected difficulty |
| `button.tiny_press_test_page` | Prints the test page |
| `select.tiny_press_maze_difficulty` | Easy, medium or hard |

If the printer is unreachable for more than 24 hours, a **Repairs** issue appears. It clears itself once the printer answers again.

Every printout ends with a small footer: the print type, difficulty, date and a short ID such as `#K7Q2`. Use the ID to match answer keys later.

## 4. Actions

Every action returns response data, so a script or an iOS Shortcut can speak the result:

```yaml
print_id: K7Q2
type: maze
length_mm: 148.5
truncated: false
```

Each successful or failed print also fires the event `tiny_press_printed` with `type`, `print_id`, `profile` and `success`.

If you have more than one Tiny Press printer, add `config_entry_id` to choose one.

### `tiny_press.print`

This is the general entry point that every button and voice phrase uses.

| Field | Notes |
|---|---|
| `type` | `maze` or `test_page` (more types arrive with each version) |
| `difficulty` | Loose words work: `easy`, `medium`, `hard`, `harder`, `tricky`, `a little harder`. Empty uses the difficulty select. |
| `profile` | Recorded with the print (profiles arrive in v0.2.0) |
| `seed` | The same seed prints the same puzzle again |

```yaml
action: tiny_press.print
data:
  type: maze
  difficulty: tricky
response_variable: printed
```

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

## 5. Voice and Siri

Assist voice phrases (an automation blueprint) and Siri shortcuts arrive in **v0.6.0**.

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

## License

MIT. See [LICENSE](LICENSE).
