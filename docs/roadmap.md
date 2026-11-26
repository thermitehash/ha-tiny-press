# Roadmap

| Phase | Version | Scope |
|---|---|---|
| 1 | 0.1.0 ✅ | Printer transport, queue and status; rendering; `print_text`, `print_image`; test page; maze; status entities |
| 2 | 0.2.0 ✅ | Kid pack: word search, math strip, joke/fun fact, kid profiles, combined Kid pack |
| 3 | 0.3.0 | Adult puzzles: sudoku, criss-cross crossword, cryptogram, answer keys, puzzle pack |
| 4 | 0.4.0 | Bedtime story and serial choose-your-own-adventure via `ai_task`, with offline fallback |
| 5 | 0.5.0 | Morning slip (manual only) |
| 6 | 0.6.0 | Voice blueprint and Siri docs |
| 7 | — | Skylight (planning only, below) |
| later | — | Selfie prints and AI-generated kid-safe pictures (planning only, below) |

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
