<p align="center">
  <img src="custom_components/tiny_press/brand/logo.png" alt="Tiny Press" height="96">
</p>

# Tiny Press

A Home Assistant integration that turns an Epson receipt printer into a household fun-printer. It prints mazes, word searches, math strips, jokes, fun facts, puzzles, bedtime stories, a morning slip, weather, sensor history, notes and pictures. Everything is printed on demand, from buttons, the dashboard card, actions or Assist voice phrases. The one exception is feed auto-print, which you switch on per feed.

- **Printer:** Epson TM-m30III (other ESC/POS printers that answer `DLE EOT` on port 9100 should work)
- **Paper:** 80 mm (576 dots, the default) or 58 mm (420 dots)
- **Home Assistant:** 2026.11.0 or newer
- **Nothing prints on a schedule.** Tiny Press ships no schedules or time-based automations. The only automatic printing is feed auto-print, which is off until you switch it on for a feed.

> **Status: v0.11.0.** Kid prints (maze, word search, math, kid sudoku, spelling, jokes, facts, kid pack), adult puzzles, bedtime stories, the morning slip, weather, sensor history, a dashboard card with kid mode, and kid-mode limits, Assist voice phrases, AI-agent print tools, feed prints, a live quote of the day, and holidays and themes. See [docs/releases](docs/releases) for each version and the [roadmap](docs/roadmap.md) for what's next.

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
| AI task entity | none | Optional. Any `ai_task` entity (for example the Anthropic integration's). Writes bedtime stories. Without it, bundled stories print instead. |
| Weather entity | none | Used by the Weather print and the morning slip. Not needed if you only have one weather entity. |
| Morning slip calendars | none | Today's events from these calendars print on the morning slip |
| Morning slip to-do lists | none | Optional: unchecked items print as checkboxes |
| Morning slip headlines | none | A feed whose 3 newest headlines print on the morning slip, above its bottom. Leave empty for none |
| Bottom of the morning slip | joke | Joke, fun fact, quote of the day, vocabulary word, small sudoku or nothing |
| Bottom of the slip: content source | Online | **Online** uses live sources where one exists (today: Wikiquote's quote of the day for the Quote bottom, credited), falling back to the bundled content. **A feed** takes the quote from the Quote feed (newest item: summary as the quote, title as the author). **Local** uses bundled content only, with no internet |
| Auto-print quiet hours | 9 PM–7 AM, skip | No feed auto-prints during these hours. Items that arrive then are skipped, or printed when quiet hours end (up to 3 per feed) |
| Use AI for jokes and fun facts | off | Off: jokes and facts come from bundled, human-written lists (facts from NOAA, NASA and the National Park Service, with credits). On: the AI is asked first. |

### Feeds

Configure → **Add a feed**: a name (used on the print and by voice), the feed's URL and how many items to print (1–10). Any RSS or Atom feed works, such as news sites, blogs or podcasts. Tiny Press reads the feed once to check it, then fetches it only when you print it, with a 15-second timeout and a 2 MB cap. Prints carry headlines, dates and short text summaries, never pictures. Remove feeds with Configure → **Remove feeds**.

**Auto-print (off by default):** Configure → **Edit a feed** → **Auto-print new items** prints a short slip each time that feed adds an item.
- **Check every:** 15 minutes by default (5–1440).
- **First check:** only notes what's already in the feed, so turning auto-print on never prints a backlog.
- **Bursts:** at most 3 slips print per check (the newest, oldest first). Items older than 12 hours never auto-print, so a printer that was off overnight doesn't wake up to old news.
- **Quiet hours:** one setting for all feeds, under Configure → Settings, 9 PM–7 AM by default. Choose **Skip them** to drop items that arrive during quiet hours, or **Print them when quiet hours end** for up to 3 per feed. Clear both times to print at any hour.
- **QR code on auto slips:** optional.
- **Printer off:** if a slip can't print, it waits for the next check (up to 3).
- **Limits:** auto slips never count toward kid-mode limits.

### Holidays and themes

Configure → **Holidays and themes**. On a recognized day, the morning slip prints a small piece of ASCII art and a one-line description under the date, on the day itself only, with no countdowns. If several days fall together, the others print as "Also today: …".

**Everyday celebrations** (on by default; untick any):

| Group | Days |
|---|---|
| Seasons and solstices | The equinoxes and solstices, named for your hemisphere (the December solstice is the first day of summer south of the equator) |
| Fun science days | Day of Women and Girls in Science, World Wildlife Day, Pi Day, World Water Day, Earth Day, Arbor Day, Space Day, World Bee Day, World Oceans Day, Asteroid Day, Moon Day, World Animal Day |
| Public holidays | Today's all-day events on the Holidays integration calendars you pick (Settings → Devices & services → Add → Holidays). A country's public holidays can include religious days, such as Christmas or Good Friday, and these print even with that holiday group off |
| First day of school | A date you set |

**Holiday groups** (all off by default, all treated the same way). After ticking groups, a second screen lets you untick single days:

| Group | Days |
|---|---|
| East Asian festivals | Lunar New Year, Mid-Autumn Festival, Chuseok, Obon |
| Jewish holidays | Rosh Hashanah, Yom Kippur, Sukkot, Hanukkah, Purim, Passover |
| Muslim holidays | Start of Ramadan, Eid al-Fitr, Eid al-Adha |
| Hindu festivals | Makar Sankranti and Pongal, Holi, Dussehra, Diwali, Onam |
| Sikh holidays | Vaisakhi, Guru Nanak's birthday, Diwali (as Bandi Chhor Divas) |
| Buddhist holidays | Losar, Vesak, Bodhi Day |
| Christian holidays | Easter, Orthodox Easter, Christmas |
| Nowruz | Nowruz, the spring-equinox new year |
| Cultural and heritage days (US) | Juneteenth, Indigenous Peoples' Day, Día de los Muertos, Kwanzaa |
| Fun days | Valentine's Day, Halloween, New Year's Eve |

**Family days** (Configure → **Add a family day**): birthdays, name days or local festivals, every year on the same date, with your own banner text and a choice of art. Remove them with Configure → **Remove family days**.

**Puzzle theme:** Auto (today's recognized day, else the season), Off, or a fixed theme such as Space or Ocean. Themes reach:
- **Word searches:** up to a third of the words come from the theme, and kid interests still mix in.
- **Crosswords:** up to four themed answers, with clues.
- **Mazes:** the theme's art and name.
- **Facts:** on science days, facts come from the matching source, such as NASA facts on Moon Day.
- **Jokes:** only on science days that have their own, such as Pi Day.

**How the content is written:**
- **Banners** are short, neutral and factual. They say what each day marks in the same way for every tradition, and never devotionally.
- **Art** uses festive, everyday imagery (lights, food, nature, celebration), never religious symbols. The same rule applies to every tradition.
- **No jokes about any religious or cultural observance, ever,** including fun days like Halloween. Themed jokes come only from science days. On a solemn day such as Yom Kippur, no joke prints at all, and a morning slip set to a joke prints a fact.
- **Shared days:** faith and cultural days rank above fun days. Days of the same rank take turns by date, so no tradition always wins a shared day.
- **Who wrote it:** all banners, art, word lists, clues and jokes were written for Tiny Press. An independent review checked them for cultural sensitivity and accuracy. An AI review isn't a substitute for people who live these traditions, so corrections are welcome: please open an issue.

**Dates:**
- **Computed at runtime:**
  - fixed days and "nth weekday" days (Indigenous Peoples' Day, Arbor Day, Space Day)
  - Western and Orthodox Easter
  - the solstices and equinoxes (Meeus' formulas, within minutes)
- **Bundled table:** moving lunar and lunisolar dates for 2026–2035.
  - Generated from the python-holidays library's calendars with `script/build_observances.py`.
  - Islamic dates are calculated, so they can differ by a day where the moon is sighted locally.
  - Vesak uses Indonesia's date; it varies by country.
  - Holidays that begin at sundown are shown on their first full day.

### Profiles

Open **Settings → Devices & services → Tiny Press → Configure** to add, edit or remove people.

| Kid profile | |
|---|---|
| Name | Shown on the Kid profile select, and in the header of their prints ("Rosie's maze", "Joke time, Rosie!") |
| Reading grade | K–5 (default 3). Sets word lists and word search size, spelling, and story reading level. |
| Math grade | K–5 (default: same as the reading grade). Sets the math strip and kid sudoku. A kid can read at grade 3 and do grade 1 math. |
| Home Assistant user | Optional: link this kid to their own login. The card then shows only their prints, limits and story, and limits always apply to them |
| Maze difficulty | This kid's mazes: Easy, Medium or Hard, or follow the Maze difficulty select (the default). Asking for a level, as in "print a hard maze", still wins. |
| Interests | Free text such as `dinosaurs, space, horses`. Themed words appear in word searches (and in AI jokes if switched on). |
| Stretch | Makes puzzles one grade harder, for both reading and math puzzles (stories stay at their reading grade) |
| Spelling list (to-do list) | Optional: a `todo` list, one word per item. Check a word off when it's learned; prints use the unchecked words. Add words by voice: "Add *because* to Rosie's spelling list". |
| Spelling words | Optional typed list (commas or new lines), used when no to-do list is set |

An adult profile has a name, a default puzzle difficulty (used by the adult puzzles) and an optional Home Assistant user. A linked adult's card prints as them, and never counts against kid-mode limits. Add as many profiles as you like, for example a younger sibling later.

What each grade gets (word searches follow the reading grade, math strips the math grade):

| Grade | Word search | Math strip |
|---|---|---|
| K | 10×10, across and down | add/subtract within 10 |
| 1 | 10×10, across and down | single-digit add/subtract (0–9 and 0–9, no negative answers); bonus within 20 |
| 2 | 10×10, across and down | two-digit add/subtract, every problem needs regrouping |
| 3 | 10×10, plus diagonals | adds ×/÷ facts to 10 and two word problems |
| 4–5 | 12×12, more diagonals | bigger numbers, ×/÷ to 12, multi-digit × |

Every math strip ends with a harder ★ bonus problem. Kid sudoku (numbers) follows the math grade: 4×4 for K–1, 6×6 for grades 2–3, and a harder 6×6 for grades 4–5.

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
| `button.tiny_press_bedtime_story` | Prints a bedtime story (Story length select) |
| `button.tiny_press_next_chapter` | Prints the next chapter of the kid's adventure (gentler choice) |
| `button.tiny_press_morning_slip` | Prints today's date, weather, events, to-dos and a joke, fact, quote, vocabulary word or puzzle |
| `button.tiny_press_weather` | Prints current weather and a forecast of up to 10 days |
| `button.tiny_press_answers` | Prints the answer key for the newest puzzle |
| `button.tiny_press_test_page` | Prints the test page |
| `sensor.tiny_press_kid_prints_left_today` | Kid prints left today when kid-mode limits are on. Attributes: `next_print_at`, `paper_left_mm`, `blocked_reason` |
| `select.tiny_press_kid_profile` | Who the buttons print for |
| `select.tiny_press_adult_profile` | Who the adult puzzles are for |
| `select.tiny_press_maze_difficulty` | Easy, medium or hard |
| `select.tiny_press_story_length` | Short, medium or long stories |
| `select.tiny_press_sudoku_difficulty` | Easy, medium or hard (defaults to the adult's difficulty) |

If the printer is unreachable for more than 24 hours, a **Repairs** issue appears. It clears itself once the printer answers again.

Every printout ends with a small footer: the print type, difficulty, date and a short ID such as `#K7Q2`. Use the ID to match answer keys later.

## 4. Actions

Every action returns response data, so a script or automation can speak the result:

```yaml
print_id: K7Q2
type: maze
profile: null
length_mm: 148.5
truncated: false
```

Jokes and facts also return `setup`, `punchline` and `source` (`ai` or `offline`), so a script can read the joke aloud. A kid pack returns `print_ids` for its three puzzles.

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

### `tiny_press.print_story`

```yaml
action: tiny_press.print_story
data:
  topic: a dragon who is afraid of the dark
  length: medium        # short, medium or long
  mode: serial          # or standalone
response_variable: story   # title, chapter, choices {A, B}, source
```

The story is written for the kid's reading grade and interests, with a made-up main character. Her name is never sent to the AI. Without an AI task entity (or if it fails), a bundled story prints and a notification explains why.

### `tiny_press.continue_story`

```yaml
action: tiny_press.continue_story
data:
  choice: B       # as circled on the last chapter; leave out for the gentler one
  # final: true   # wrap the adventure up
```

### `tiny_press.print_morning_slip`

```yaml
action: tiny_press.print_morning_slip
```

Prints today's date, weather, calendar events, optional to-dos and the bottom section you chose. It's manual only, and it doesn't count toward kid-mode limits. Kid-mode dashboard cards may print one a day.

### `tiny_press.print_history`

```yaml
action: tiny_press.print_history
data:
  entity_id: [sensor.bedroom_temperature, sensor.living_room_temperature]
  hours: 24            # or days: 7, or start/end
  style: graph         # graph (default), table or both
  tall: false          # true: long graph turned onto the strip (read it sideways)
  grid: false          # true: time gridlines and a frame
```

Numeric sensors print as a line graph with a summary (now, min, max, average, change). On/off and text sensors print as a timeline with time spent in each state. Tables are ruled into clear columns and rows. Periods over 3 days use hourly statistics. A tall graph reads like a landscape page when you turn the receipt sideways, with the header at the bottom of the strip.

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

### `tiny_press.print_feed`

Prints the newest items from a feed: headline, date and a short summary. Not a kid print, so never limited.

```yaml
action: tiny_press.print_feed
data:
  feed: BBC News   # name or ID; empty prints the first feed
  items: 5         # optional, 1-10; defaults to the feed's setting
  qr: true         # optional: a small QR code under each item opens it on a phone
```

## Dashboard card

Tiny Press includes a dashboard card. It adds itself to your dashboard resources (Settings → Dashboards → ⋮ → Resources), so there's nothing extra to install. Edit a dashboard, choose **Add card**, and find **Tiny Press** under **Custom**, or search for it. If it's missing, restart Home Assistant and refresh the browser. With YAML-mode dashboards, add `/tiny_press/tiny-press-card.js` as a JavaScript module resource yourself.

```yaml
type: custom:tiny-press-card
title: Rosie's printer
kid_mode: true          # hold-to-print, no settings or answers, shows limits
show_preview: false     # true: see the print first, then Shuffle or Print
buttons: [maze, word_search, math, kid_sudoku, spelling, joke, kid_pack, story, next_chapter, sudoku, crossword, cryptogram, puzzle_pack, morning_slip, weather]
# ignore_limits: true   # for a parents' dashboard
history:                # optional one-tap history buttons (hidden in kid mode)
  - {name: Freezer, entity: sensor.freezer_temperature, hours: 24}
  - {name: Garage door, entity: binary_sensor.garage_door, days: 7, tall: true}
feeds:                  # optional feed buttons (hidden in kid mode)
  - {name: News, feed: BBC News, items: 5, qr: true}
```

**The card follows who's logged in:**
- **A kid linked to their Home Assistant user:** the card switches to kid mode for them. That means hold-to-print, no adult puzzles or settings, and only their own prints left, their own time bar and their own story.
- **An admin:** a **Print as** row at the top lists every kid and adult. Print as anyone, and it never counts against limits.
- **An adult linked to their user:** prints as them, never limited.
- **Anyone else (a shared tablet account):** the card's own settings decide (`kid_mode`, `ignore_limits`), using the Kid profile select.

**Also on the card:**
- **Time bar:** while a print has to wait, a live bar sits at the top with the countdown inside it ("Next print in 0:44"), filling until the next print is allowed.
- **Next chapter button:** shows the kid's story in progress ("Chapter 3 · The Lighthouse Fox"), or is greyed out with "No story yet".
- **Header:** shows whose card it is: the logged-in person, the admin's Print as pick, or the active kid.
- **Prints left today:** the chip turns yellow with bold black text for the last three prints, and red with bold white text for the last one.
- **Morning slip:** greyed out as "Printed today" on every card once it has printed that day. Actions and automations can still print it.

<!-- ![Dashboard card](docs/images/card.png) -->

## Kid-mode limits

Under **Configure → Kid-mode limits** you can turn on a wait between prints (default 2 minutes), prints per hour (4), prints per day (10) and a daily paper budget (1.5 m).

- **Each kid has their own limits.** A print counts against the kid it's for, so one kid's cooldown never blocks another. Counts reset at midnight.
- **Who they apply to:** kid prints from every button, card, action and voice phrase.
- **When a print is blocked:** the kid gets a friendly message ("Just a moment! The next print is ready at 3:42 PM"), and Tiny Press fires `tiny_press_rate_limited` (with the kid's name) so you can be notified.
- **A kid's own login:** if a kid profile is linked to a Home Assistant user (Configure → Edit a profile → Home Assistant user), that account always prints as that kid and can't skip the limits, whatever the card or action asks.
- **Parents skip the limits:** admin users and adults linked to a profile never count. Automations and scripts can skip them with `ignore_limits: true`:

```yaml
action: tiny_press.print
data:
  type: kid_pack
  ignore_limits: true
```

## 5. Voice

Two ways to print by voice. Use either or both.

### Voice phrases (Assist blueprint)

[![Import the voice phrases blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fthermitehash%2Fha-tiny-press%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Ftiny_press%2Fvoice_phrases.yaml)

1. Click the button above (or go to Settings → Automations & scenes → Blueprints → Import blueprint and paste `https://github.com/thermitehash/ha-tiny-press/blob/main/blueprints/automation/tiny_press/voice_phrases.yaml`).
2. Create an automation from **Tiny Press voice phrases**, pick your printer and save. All phrases are on; untick any group under **Phrases to use**.
3. Say a phrase to Assist (a voice satellite, the Companion app or the Assist button):

| Say | Prints | Tiny Press says |
|---|---|---|
| "Print a maze", "Print a hard maze for Rosie" | Maze | "Printing a maze for Rosie." |
| "Print a word search / math sheet / kid pack / kid sudoku for Rosie" | That kid print | "Printing a word search for Rosie." |
| "Print spelling practice for Rosie" | Spelling practice | "Printing spelling practice for Rosie." |
| "Tell me a joke", "Tell me a fun fact" | Joke or fact | The joke or fact itself, read aloud |
| "Print a bedtime story", "Print a story about a brave dragon", "Print the next chapter" | Story | "Printing *title*. Sweet dreams!" |
| "Print an easy sudoku / crossword / cryptogram", "Print a puzzle pack" | Adult puzzle | "Printing a sudoku." |
| "Print the morning slip", "Print the weather" | Morning slip or weather | "Printing your morning slip." |
| "Print the news", "Print the headlines from BBC News" | Feed headlines | "Printing 5 headlines from BBC News." |
| "Print a note that says feed the cat" | The note | "Printing your note." |

- **Kid-mode limits apply** to kid prints by voice, exactly as on the card. When a limit is reached, Tiny Press says why instead of printing ("That's enough printing for today! See you tomorrow.").
- **Notes are adult prints.** They never count toward kid-mode limits (like `print_text`) and are capped at 500 characters.
- **Problems are spoken, not silent:** an offline printer, a missing weather entity or an empty spelling list each get a spoken answer.
- **Names:** "for Rosie" picks that kid profile. A name Tiny Press doesn't know uses the active profile.
- **Your own phrases:** every group's phrases are editable in the automation (Kid print phrases, Adult print phrases). `[word]` is optional, `(a|b)` means either, and `{name}`, `{topic}` and `{text}` capture what's said there. Phrases ship in English; type your own in any language Assist supports.
- **AI agents:** sentence phrases only run when Home Assistant's built-in conversation agent handles the sentence. If your Assist pipeline uses Claude, OpenAI or another AI as its agent, turn on **"Prefer handling commands locally"** in the pipeline, or rely on the tools below.

### AI agents (Claude, OpenAI, …)

When an Assist pipeline's agent has **Assist** control turned on (Settings → Voice assistants → your assistant → the agent's options), Tiny Press gives it two tools:

- **Print on Tiny Press** (`tiny_press__print`): any kid print, joke, fact, story (optionally about a topic), next chapter, adult puzzle, morning slip, weather or a feed's headlines, for a named profile, difficulty or feed.
- **Print a note on Tiny Press** (`tiny_press__print_note`): a dictated note.

So "print my daughter a dinosaur story" or "can you print a hard crossword?" just works, with no "Prefer handling commands locally" needed. The same kid-mode limits and length caps apply, and the agent is told what to say back.

### `tiny_press.voice_print`

The action behind both. It prints and always returns `printed` and `speech`, even when nothing printed, so a script can speak the result:

```yaml
action: tiny_press.voice_print
data:
  type: maze            # any kid or adult print, story, next_chapter, morning_slip, weather, note
  profile: Rosie        # optional, as spoken
  sentence: print a hard maze   # optional: a difficulty word in it is used
response_variable: result
# result.speech → "Printing a maze for Rosie."
```

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

Bundled content comes from sources that allow redistribution:
- **Fun facts:** NOAA, NASA and the National Park Service (U.S. government works, public domain).
- **K–3 words:** the Dolch sight-word lists.
- **Cryptogram quotes:** public-domain works (Roosevelt, Muir, Lincoln, Shakespeare), as collected by the National Park Service.
- **Vocabulary definitions:** Open English WordNet (CC BY 4.0).
- **Holiday dates:** generated with the python-holidays library (MIT).
- **Written for Tiny Press:** jokes, the NYT-style crossword clues, and the holiday banners, ASCII art and themed word lists.

**Live content:**
- With the bottom's content source set to Online, the morning slip fetches Wikiquote's quote of the day (CC BY-SA 4.0) and prints its credit.
- Feed prints show each feed's own content and name.

See [`data/LICENSE.md`](custom_components/tiny_press/data/LICENSE.md) for every source.

## License

MIT. See [LICENSE](LICENSE).
