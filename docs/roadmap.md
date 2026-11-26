# Roadmap

| Phase | Version | Scope |
|---|---|---|
| 1 | 0.1.0 | Printer transport, queue and status; rendering; `print_text`, `print_image`; test page; maze; status entities |
| 2 | 0.2.0 | Kid pack: word search, math strip, joke/fun fact, kid profiles, combined Kid pack |
| 3 | 0.3.0 | Adult puzzles: sudoku, criss-cross crossword, cryptogram, answer keys, puzzle pack |
| 4 | 0.4.0 | Bedtime story and serial choose-your-own-adventure via `ai_task`, with offline fallback |
| 5 | 0.5.0 | Morning slip (manual only) |
| 6 | 0.6.0 | Voice blueprint and Siri docs |
| 7 | — | Skylight (planning only, below) |

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
