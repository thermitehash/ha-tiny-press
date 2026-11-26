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
| 6 | 0.8.0 | Voice blueprint and Siri docs |
| 7 | — | Skylight (planning only, below) |
| later | — | Selfie prints and AI-generated kid-safe pictures (planning only, below) |
| later | — | RSS/Atom feed prints and a live quote of the day (planning only, below) |

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
- From a phone: the iOS Shortcut can send a photo to `/config/www/tiny_press/` and then call `print_image`. Document this as an alternative that doesn't need a camera entity.

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

## Later: RSS/Atom feeds and a live quote of the day (planning only)

### Feed prints
- A `tiny_press.print_feed` action (and card buttons) that prints the newest items from any RSS or Atom feed: headline, date, a short summary, the source's name and a QR code linking to the item.
- Reuse Home Assistant's `feedreader` integration where it's set up (its events and entities), or fetch a feed URL directly with HA's shared HTTP session, with a timeout and size cap.
- Strip HTML down to plain text; never print images or scripts from a feed.
- Always print the feed's title and link as attribution. Leave paywalled or "no reuse" feeds to the user's judgment and say so in the docs.
- Manual prints only, like everything else.

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
  - **Enforced in the integration, not just the card**, so the same limits apply to buttons, voice phrases and Siri. Kid-facing entry points count toward the limit.
    - Adults can bypass it: an "adult" flag on the action call, and actions run by admin users.
    - Limits are set in the options flow and reset at local midnight.
    - Blocked attempts fire `tiny_press_rate_limited`, so a parent can be notified if they want.
- **Packaging:**
  - Ship the card's JavaScript inside the integration and register it as a frontend resource automatically, so there's no separate HACS "Dashboard" repository to install.
  - Configure it in the visual card editor (the printer device, and which buttons to show).
  - Works in light and dark themes.
- Nothing prints on its own. The card only prints when someone presses a button.
