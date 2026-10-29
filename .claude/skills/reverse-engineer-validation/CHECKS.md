# Content-check metrics

Measured choices from the Cyberia port's suite. Re-derive the numbers for
your own game (§ "choose by experiment"); keep the reasoning.

## Frames: structural statistics, not hashes

A whole-frame hash changes on every legitimate edit (one sprite a pixel
over, one extra HUD glyph). A suite that cries wolf trains people to
re-bless without looking, and the next real regression gets waved through.
Record statistics that stay flat under small edits and move sharply under
the defects that actually ship:

| Metric | Catches | Notes |
|---|---|---|
| **Jaccard of the distinct colour set** (6-bit DAC triples) vs golden | wrong / stale palette | Layout survives, colour set moves wholesale; threshold ≥ 0.90. A routing assertion can never see this. |
| **Tile grid**, per tile: distinct colours, *ink* (pixels ≠ the tile's modal colour), non-black | missing sprite or layer (tiles empty), debug overlay shipped (tiles fill) | 8×10 grid of 40×20 px on 320×200 |
| **Global distinct / non-black** | whole-frame collapse (black, single colour, half drawn) | |
| **Region probes** `[name, x, y, w, h]` | features smaller than a tile (3×6 px typed glyphs) | a 5-px move changed a probe 73 → 43 ink while staying inside the tile envelope |
| **Asset palette coverage**: every colour in the frame exists in the scene asset's palette (swept over the brightness ramp) | wrong scene's palette, with no golden | strictly stronger than a golden where it applies |

**Choose granularity by experiment.** Induce your smallest real defect and
find the coarsest grid that still sees it. At 4×4 and 8×5 tiles a
279-px debug strip over 5 scanlines was invisible: the modal-colour count
absorbed it. At 8×10 it moved four tiles by up to 76 ink px.

**Tolerances are a change budget, not noise.** With the seed pinned the
drives are byte-deterministic, so natural variance is zero. A tolerance
says how much deliberate change may land before a human has to look.
Defaults used: jaccard ≥ 0.90; distinct ± max(3, 15 %); non-black ± 2 % of
the frame; tile ink ± max(24, 10 %); tile distinct ± max(2, 25 %); probes
± max(6, 5 %). Per-case overrides live in the golden and survive a
re-bless.

## Transitions

- **Palette at every cross**: dump a frame at each scene transition; check
  it against the destination asset's palette. Also assert a *minimum
  number of crosses checked*, or a route that silently stops crossing
  passes with zero checks.
- **The black gap**: frames that should be black must be uniform and dark
  (`max_dac` bound); frames that must be picture must have at least
  `min_frac` non-black pixels. A glob matching nothing fails.

## Audio

Tap the mixer output after the mix to a raw PCM file (env-gated), then
compare a chunked RMS envelope against the golden with an energy floor,
plus the voice-install log lines (channel, clip, length). What it catches:
silence, a missing or extra voice, gross timing shifts. What it cannot
catch: wrong-but-similar clips, pitch or rate errors, channel attribution
(the tap is post-mix), A/V sync. Say so in the suite's "cannot prove" list.

## Timing

Assert intervals between two log lines from the log's own timestamps
(`interval_s: from, to, min, max`), in serial cases only. Derive the
expected value from the original's clock (ISR rate, PIT divisor, divide-by
toggles) and state the derivation in the case's `what`.

## Example induced-failure table

| Check | Induced defect | Command | Result |
|---|---|---|---|
| dogfight frame | debug overlay ships (279 px) | `regress --case frame_tf22 --env OPENCYB_TF22_SYNCBAR=1` | FAIL, 4/80 tiles, rows 180–199 |
| dogfight frame | backdrop layer missing | `… --env OPENCYB_TF22_NOBG=1` | FAIL, jaccard 0.16, 56/80 tiles |
| rig timer | walk timebase scaled | `… --case sc257_rig_timer --env OPENCYB_WALK_FAST=8` | FAIL, countdown 1.9 s, want 13.5–17.5 |
| crosspal | stale palette at a cross | file another scene's pixels as the cross snapshot | FAIL, coverage 3.66 % |
| crosspal | route stops crossing | snapshot prefix with no crosses | FAIL, 0 checked, expected ≥ 2 |
