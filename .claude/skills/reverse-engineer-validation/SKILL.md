---
name: reverse-engineer-validation
description: >-
  Prove a reverse-engineered port or decoder matches the original: build or
  extend a regression suite for a game port, add a check for a fix, compare
  port output against the original binary or a reference decoder, re-bless
  goldens, or decide whether a green run actually shows the port is right.
---

# Validating a port against the original

A check is evidence only if it **fails when the port is wrong**. The usual
way a faithful port regresses is a suite that asserts *routing* (which
scene loaded, which transition fired) while the screen shows the wrong
thing. In the Cyberia port a cross-palette change passed every headless
drive and shipped rendering each new scene in the previous scene's colours.

## 1. Pick the strongest oracle available

Ranked. Use the highest one that reaches the behaviour:

1. **The original binary, running.** A scripted DOSBox-X debugger run
   (`dos-re-toolbox` DOSDBG.md) writes an **oracle log**: file opens with
   the frame they happened at, commits, state changes. The port emits the
   same events in the same line shape (an `[open]` line wherever the
   original calls its fopen). They must agree up to the first event the port
   doesn't implement yet. Name that event when you report the match.
2. **A reference decoder written from the asm** (Python, from the same
   reading). Diff the port's raw output **byte for byte**: frames as palette
   indices, palettes in a separate dump so a palette bug cannot mask a codec
   bug. First landing of the C95 codec: 56 files, 9,588 frames, 0 differing
   bytes.
3. **Asset-derived checks.** Reconstruct the expected result from the
   shipped asset (the palette a scene must leave on the DAC, from its own
   file). These cannot drift.
4. **Blessed goldens.** Statistics recorded from a binary someone looked
   at. Weakest: a wrong render blessed by mistake becomes "correct". Record
   which build blessed each one (`blessed_at`: rev + date).

## 2. Make every drive deterministic and bounded

- **Seed** the RNG explicitly on every drive. Have any drive hook force a
  fixed seed when none is given, so an artifact run is reproducible even if
  someone forgets. Keep the original's clock seed for interactive play. A
  `time(NULL)` seed agrees for runs started in the same second and only
  diverges later: a flake that passes determinism checks.
- **Pin** every other input the original reads (player profile, save slot,
  difficulty).
- **Bound wall-clock time** with a hard quit timer (push a real quit event
  after N ms). Tick budgets only bound the loop that counts them: a drive
  that leaves it (death to a load screen, a menu) waits for input forever.
- **Headless** by default (`SDL_VIDEODRIVER=offscreen`,
  `SDL_AUDIODRIVER=dummy`, overridable to watch live). The dummy audio
  device still pulls the mixer at real-time cadence.
- **Real-time assertions run alone** (`serial`), measure from the log's
  own timestamps, and never run under a time-scaling knob.
- **Artifacts go to a per-run directory** and the target is deleted before
  the drive, so a stale file can't score a pass. A missing artifact fails
  the check and proves the drive never got there.
- Any crash signature (SIGSEGV, assertion, sanitizer report) fails any case.

## 3. Drive the real route

Scripted input through the same input path a player uses (a key script
injected into the event pump, not a poke behind the engine). Enter scenes
through their **real inbound edge**. A direct-entry harness (`--scene N`
from some saved state) hands the scene a state no legitimate arrival
produces. In Cyberia it produced two false "this record never fires"
bugs, one of which framed a whole investigation wrongly.

## 4. Check content, not just routing

Any change touching palettes, fades, draw order, compositing, audio
voices or timing gets a content check. Kinds that worked
([`CHECKS.md`](CHECKS.md) has the metrics and how their thresholds were
chosen):

- `frame`: structural statistics of a dumped frame (colour-set Jaccard,
  tile-grid ink), never a whole-frame hash.
- `crosspal` and similar: asset-derived palette coverage at each transition.
- `nonblack` / `crossblack`: frames that must be real picture, gaps that
  must be uniform black.
- `framehold`: two dumps inside a hold are byte-identical, and both differ
  from the dump after release.
- `bytes`: two artifacts the drive dumped must be identical (the 768-byte
  DAC before and after a pause-menu round trip), rather than trusting a log
  line that says "palette restored".
- `audio`: a post-mix PCM tap, compared as a chunk-RMS envelope plus voice
  install/length lines.

## 5. Prove each check fails

For every content check, induce the defect class it targets and record the
result in an **induced-failure table** in the suite's README: check,
induced defect, the exact command, what failed. Inject the defect with an
env knob in the port (draw a debug strip, skip the backdrop layer, scale
the timebase), labelled NON-ASM, never with an `LD_PRELOAD` shim. If you
cannot make a check fail, it tests nothing: drop it and say so.

## 6. Run the right tier, then re-bless honestly

- Two tiers: **fast** (the push gate) and **thorough** (adds the slow
  real-time cases). Run thorough before pushing anything that touches
  render, audio or timing. Once a push went out at "52/52 green" while a
  thorough-only case had been red for two days.
- Re-bless a golden only after: (1) rendering before/after and looking;
  (2) **attributing** the diff, i.e. showing that only the metric the fix
  explains moved; (3) re-proving the case still catches its original defect
  (induce it again). Commit the golden change on its own, saying why it is
  right. Never re-bless to turn a red run green.
- Rebuilding mid-run (another agent, another session) invalidates that run.
  Rerun the tier.
- Assertions must not embed asset paths or other layout. Moving the asset
  tree broke three cases that grepped a literal path.

## 7. Write down what the suite cannot prove

Keep a "cannot prove" section next to the suite and read it before calling
anything verified. Examples: structural frame checks pass a sprite with the
wrong artwork in the right place; the audio envelope passes wrong pitch or
swapped samples; one frame per screen says nothing about animation timing;
ten scripted routes cover a small part of the scene graph. Every remaining
gap needs a live human look or a stronger oracle.

## Suite shape that worked

Cases as data (`cases.json`), a runner that expands `{work}`/`{repo}`,
applies `base_env` (seed, profile), and runs cases in parallel except
`serial` ones. Each case has: `name, tier, what, timeout_s, args, env`,
`assert` (`exit`, `present`/`absent` regex, `count`, `order` subsequence,
`equals`, `interval_s` between two log lines, `wall_max_s`) and an optional
`content` list (§4). One command lists, runs one case verbose with kept
artifacts (`--case NAME -v -k`), re-runs with a defect knob (`--env K=V`),
and blesses.

Diagnostics stay on the console (stderr, env-gated); no debug text on the
game screen, which would also pollute the frame checks.
