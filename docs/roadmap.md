# Roadmap

| Phase | Version | Scope |
|---|---|---|
| 1 | 0.1.0 ✅ | Printer transport, queue and status; rendering; `print_text`, `print_image`; test page; maze; status entities |
| 2 | 0.2.0 ✅ | Kid pack: word search, math strip, joke/fun fact, kid profiles, combined Kid pack |
| — | 0.3.0 ✅ | Dashboard card, kid-mode rate limiter, print preview, answer keys for kid puzzles |
| 3 | 0.4.0 ✅ | Adult puzzles: sudoku, criss-cross crossword, cryptogram, puzzle pack |
| 4 | 0.5.0 ✅ | Bedtime story (short/medium/long) and serial choose-your-own-adventure via `ai_task`, with offline fallback |
| 5 | 0.6.0 ✅ | Morning slip (manual only) |
| — | 0.7.0 ✅ | Sensor history prints (graph, table, timeline) |
| 6 | 0.8.0 ✅ | Assist voice phrases (blueprint) and print tools for AI agents |
| — | 0.9.0 ✅ | RSS/Atom feed prints and live quote of the day from Wikiquote |
| — | 0.10.0 ✅ | Holiday-aware morning slip (day of only), seasonal and holiday puzzle themes, quote from a feed |
| 7 | — | Skylight (planning only, below) |
| later | — | Selfie prints and AI-generated kid-safe pictures (planning only, below) |
| later | — | Recipe prints from Tandoor (idea, below) |

## v0.10.0: holidays and themes (built)

Design decisions (asked one at a time, answered 2026-11-26):
1. **On by default:** seasons and solstices, fun science days (Pi Day, Earth Day, World Ocean Day, Space Day and similar), public holidays from a Holidays calendar if one is added, and a first day of school you set.
2. **Opt-in holiday groups** instead of single holidays (like Gemstone Lights' Autopilot). Pick whole groups, all off by default, then optionally untick single days inside a group. Plus **custom family days** (birthdays, name days, local festivals) with your own banner text.
3. **ASCII art:** centered above the banner text, on recognized days only. Ordinary days look as they do now.
4. **Themed prints:** word search, crossword, maze, and jokes and facts.
5. **Theme control:** under Configure → Settings only (Auto, Off, or a fixed theme).
6. **Feed as quote source:** the newest item's summary is the quote and its title is the author, falling back to the title alone.

### Holiday-aware morning slip
- **Banner under the date** on a holiday: "Today is Diwali, the festival of lights". The one-line description is neutral and factual (what the day is), sourced and credited (for example Library of Congress or Smithsonian educational pages), never devotional.
- **Day of only:** a holiday is recognized only on the day itself, with no countdowns or reminders beforehand.
- **Themed ASCII art with the banner:** a small piece of ASCII art for each observance and season, such as a lantern for Lunar New Year, a diya lamp for Diwali, a sun for the summer solstice or a leaf for autumn.
  - Drawn for Tiny Press, so there are no licensing questions, and kept small: about 6–8 lines, fitting 32 columns so it works on 58 mm paper too.
  - Printed in a monospace font inside the image, so it looks the same on both paper widths.
  - The imagery is festive and neutral (lights, food, nature, celebration), not devotional symbols. The same rule applies to every tradition.
  - Art follows the same opt-in checklist as the banners.
- **Themed fun:** on a holiday, the slip's bottom and that day's puzzles use its theme.
- **Dates:** Home Assistant's Holidays integration calendars (country and region), plus a bundled, sourced table of moving lunar and lunisolar dates for about ten years.

### Not centered on any one tradition
- Nothing religious is on by default. The defaults are secular and natural: seasons, solstices and equinoxes, Earth Day, Pi Day, the first day of school, and your country's public holidays if that calendar is added.
- Faith and cultural observances come in **opt-in groups**, all off by default and all treated the same way. Proposed groups:
  - **East Asian festivals:** Lunar New Year, Mid-Autumn Festival, Chuseok, Obon.
  - **Jewish holidays:** Rosh Hashanah, Yom Kippur, Sukkot, Hanukkah, Purim, Passover.
  - **Muslim holidays:** start of Ramadan, Eid al-Fitr, Eid al-Adha.
  - **Hindu festivals:** Makar Sankranti and Pongal, Holi, Dussehra, Diwali, Onam.
  - **Sikh holidays:** Vaisakhi, Guru Nanak's birthday.
  - **Buddhist holidays:** Losar, Vesak, Bodhi Day.
  - **Christian holidays:** Easter, Orthodox Easter, Christmas.
  - **Persian New Year:** Nowruz.
  - **Cultural and heritage days:** Juneteenth, Indigenous Peoples' Day, Día de los Muertos, Kwanzaa.
  - **Fun days:** Valentine's Day, Halloween, New Year's Eve.

### Puzzle themes
- **Seasonal themes:** word lists for autumn, winter, spring and summer that follow the hemisphere, using Home Assistant's latitude.
- **Holiday themes:** word-search words, themed crossword clues and a themed joke or fact pool, only for observances the household ticked.
- **A Theme select:** Auto (season or today's holiday), Off, or a fixed theme. Kid interests still mix in.
- **Themed mazes:** borders or start/finish icons, such as a lantern, a snowflake or a leaf. Built as the theme's ASCII art and name above the maze.

### Quote source setting
- Wikiquote (default), a feed from the Feeds list (its newest item becomes the quote, credited with the feed's name), or bundled only. This would extend v0.9.1's Online/Local content source for the slip's bottom.

## Later: recipe prints from Tandoor (idea)

[Tandoor Recipes](https://github.com/TandoorRecipes/recipes) is a self-hosted recipe manager with a REST API.
- **Print a recipe:** ingredients as checkboxes and numbered steps, scaled to a chosen number of servings, with an optional QR code back to the recipe.
- **Print today's meal plan** from Tandoor's meal planner, or add it to the morning slip.
- **Print the shopping list** from Tandoor as checkboxes.
- **Setup:** a Tandoor URL and an API token under Configure. Requests go only to that server.
- Manual prints only.
- **To check then:** Tandoor's API version and authentication, and whether a Home Assistant integration for Tandoor exists to build on.

## Phase 7: Skylight family calendar (planning only)

The household plans to bring its Skylight calendar into Home Assistant later.
**Skylight has no official public API.** Whatever exists at that point
(community integrations, calendar sync through Google or iCloud, or a
reverse-engineered client) needs investigating then. Check maintenance,
licensing and terms of service before relying on any of it.

To keep that a no-code change, Tiny Press only reads **generic** entities:

- The morning slip reads any `calendar.*` entities chosen in the options.
- List prints will read any `todo.*` entity.

An integration that exposes Skylight as `calendar` and `todo` entities will
therefore plug in by selecting those entities.

Future print types built on those generic entities:

- **Chore chart:** items from a `todo` entity, each with a printed checkbox, grouped by assignee when the item text allows.
- **Weekly meal plan:** a seven-day grid from a dedicated `calendar` (or `todo`) entity.
- **Weekly family calendar:** a seven-day strip with each day's events from the selected `calendar` entities, all-day events first.

All of these are manual prints, like everything else in Tiny Press: no schedules.

## Later: selfie prints and AI-generated pictures (planning only)

Both build on `print_image`'s existing 1-bit rendering. Like everything else, they are manual prints only.

### Selfie / photo prints
- A `tiny_press.print_camera` action (and an optional button) that takes a snapshot from any `camera.*` entity, for example a tablet or doorbell camera pointed at a "photo booth" spot.
- A photo-booth layout: a high-contrast portrait crop, dithering tuned for faces (Atkinson or Floyd–Steinberg with a gamma lift so skin doesn't go muddy), an optional frame or sticker border, and a caption line ("Rosie, Nov 26").
- An optional "strip" mode: three or four snapshots a few seconds apart, stacked like a photo-booth strip.
- Privacy: snapshots are rendered in memory and never stored by Tiny Press. Diagnostics never include images.

### AI-generated kid-safe pictures
- Use Home Assistant's `ai_task.generate_image` (available on AI task entities that support image generation) to make **coloring pages**: bold black outlines, no shading, white background. That style suits a thermal printer far better than photos.
- Inputs: a prompt or topic, plus the kid profile's interests ("a dinosaur having a picnic"). Combine it with the story feature for a picture of the chapter's scene.
- Safety:
  - A fixed system prompt adds kid-safe rules (no scary, violent or adult content; no real people, brands or copyrighted characters).
  - The user's topic is passed as data, not instructions.
  - If generation fails or is refused, print a bundled coloring page instead and say so in a persistent notification.
- Rendering: threshold rather than dither for line art, auto-crop margins and scale to the paper width, and enforce the usual maximum print length.
- Open questions to settle then:
  - Which `ai_task` providers support image generation, and at what cost per image.
  - Whether to cache generated pages for re-printing.
  - A per-day limit so a voice command can't run up a bill.

## v0.9.0: RSS/Atom feeds and a live quote of the day (built)

Built as planned, with two changes: feeds are set up under Configure → Add a feed (Tiny Press fetches them itself rather than through the Feedreader integration), and Wikiquote has no Quote of the Day RSS feed, so Tiny Press reads its "Main Page/Quote of the day" page through the MediaWiki API (`action=parse`), with the rendered page as a fallback.

### Feed prints
- A `tiny_press.print_feed` action (and card buttons) that prints the newest items from any RSS or Atom feed: headline, date, a short summary, the source's name and a QR code linking to the item.
- Reuse Home Assistant's `feedreader` integration where it's set up (its events and entities), or fetch a feed URL directly with HA's shared HTTP session, with a timeout and size cap.
- Strip HTML down to plain text; never print images or scripts from a feed.
- Always print the feed's title and link as attribution. Leave paywalled or "no reuse" feeds to the user's judgment and say so in the docs.
- Manual prints only, like everything else.
- **Morning slip option:** add "News from a feed" to the morning slip's bottom choices (Configure → Settings), with a feed picked in setup. It prints the newest few headlines with the feed's name, and a QR code for each item if it fits. It falls back to the bundled quotes when the feed can't be read.

### Live quote of the day (with the bundled quotes as fallback)
- A "live" choice for the morning slip's quote: fetch today's quote from a source whose terms allow reuse with attribution. If the fetch fails, times out or returns nothing printable, fall back to the bundled public-domain quotes and print no error.
- **Chosen source: Wikiquote Quote of the Day** (MediaWiki `featuredfeed`, `feed=qotd`, RSS). The page text is CC BY-SA; print the author and "Wikiquote (CC BY-SA)". Send a descriptive User-Agent, as Wikimedia asks. (Not yet tested from the build environment, whose network blocks it.)
- Considered: **ZenQuotes** `today` API (needs a visible "Inspirational quotes provided by ZenQuotes API" credit; run by one person, so less dependable). Any user-chosen feed will also work through the generic feed support above.
- Not used: sites whose terms forbid reuse of their quotes (for example BrainyQuote).
- Cache one quote per day so reprints don't refetch, and filter by length so it fits the slip.

## Dashboard card (built in v0.3.0)

The items below were the plan. Everything is built except the visual-editor niceties beyond the basic form.

A Lovelace card (`custom:tiny-press-card`) so the household gets one tidy,
kid-friendly control instead of a grid of separate button entities.

- **Big print buttons** with icons (Maze, Word search, Math, Joke, Kid pack, and later Sudoku, Story and Next chapter), sized for small fingers on a wall tablet.
- **Profile chips** to switch the active kid or adult, plus a difficulty or story-length toggle next to the relevant buttons.
- **Status strip:** online, paper state (OK / running low / out / cover open) and paper used, with a gentle warning when paper is low.
- **Last print:** type, time and its `#ID`, with an "Answers" button that prints the answer key for it.
- **Preview before printing:** a rendered preview of the next print (the same 1-bit image the printer gets), with Print and Shuffle buttons. This needs a small preview endpoint or action that returns a PNG without printing.
- **Busy state:** buttons disable while a job is printing, and errors show as a friendly message, not a stack trace.
- **Kid mode:** an option to hide settings and adult puzzles, and to require a hold-to-print press so a toddler can't empty the roll.
  - **Rate limiter:** a cooldown between prints (e.g. 2 minutes), a cap on prints per hour and per day (e.g. 4 and 10), and a daily paper budget in mm.
    - The card shows "Next print in 1:30" or "3 prints left today", and a friendly "That's enough printing for today!" when the limit is reached.
  - **Enforced in the integration, not just the card**, so the same limits apply to buttons, the card and voice phrases. Kid-facing entry points count toward the limit.
    - Adults can bypass it: an "adult" flag on the action call, and actions run by admin users.
    - Limits are set in the options flow and reset at local midnight.
    - Blocked attempts fire `tiny_press_rate_limited`, so a parent can be notified if they want.
- **Packaging:**
  - Ship the card's JavaScript inside the integration and register it as a frontend resource automatically, so there's no separate HACS "Dashboard" repository to install.
  - Configure it in the visual card editor (the printer device, and which buttons to show).
  - Works in light and dark themes.
- Nothing prints on its own. The card only prints when someone presses a button.
