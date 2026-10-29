# Tracing under the DOSBox-X debugger

`dosdbg` starts `dosbox-x` (built from source with `--enable-debug=heavy`;
the Ubuntu package has no debugger) inside a
tmux session on the SDL dummy video/audio drivers, with `DEBUGBOX PROGRAM`
in the autoexec, and waits until the debugger stops at the program entry.
`dbgdrive` (CLI and importable module) types into the ncurses debugger with
`tmux send-keys` and reads it back with `capture-pane`. There is no window:
everything you learn is through breakpoints, registers and memory reads.

Work dir: `$DOSDBG_WORK` (default `./.dosdbg`) holds `dosdbg.conf`,
`dosbox.log` and the default `C:` drive. Keep it on an exec-capable disk
under `/work` so its logs survive the container.

## Scenario skeleton

The addresses below are Cyberia 2 GAME.EXE link addresses (its level
router and chosen-level cell), shown for shape only.

```python
#!/usr/bin/env python3
# NON-ASM tooling: the claims go in the notes, citing this log.
import time, dbgdrive as d

t0 = time.time()
log = open('scenario.log', 'w')
def say(msg):
    line = '%8.1fs %s' % (time.time() - t0, msg)
    print(line); log.write(line + '\n'); log.flush()

d.send('BPINT 21 3D')                     # 1. file opens: armed at entry
while True:                               # 2. reach protected mode
    assert d.run(60), 'no break'
    if d.regs()['mode'] == 'Pr32':
        break
d.bp_code(0x1b40c)                        # 3. NOW the code BPs (link addrs)
while d.run(600):
    r = d.regs()
    if r['mode'] != 'Pr32':
        continue                          # DOS/4GW's real-mode reflection
    if r['link_eip'] == 0x1b40c:
        say('router: level %d' % d.dump(d.DS_SEL, d.rt_data(0x40c5e), 1)[0])
    else:
        say('open %s' % d.cstr(r['DS'], r['EDX']))
```

Run it: `DBG_CODE_DELTA=1c3000 DBG_DATA_DELTA=1c1000 dosdbg -C cdrive -S scenario.py GAME.EXE`.
Log link addresses, never runtime ones, so log lines can be looked up in
the listing.

## Link ↔ runtime addresses

DOS/4GW does not load LE objects at their link bases: each object lands at
link + a per-object delta, flat selectors (e.g. `CS=0160 DS=0168`, base 0).
Export the deltas as `DBG_CODE_DELTA` / `DBG_DATA_DELTA` (hex) and use
`rt_code()` / `rt_data()` / `link_code()` / `link_data()`.

The deltas depend on `memsize` and the DOSBox-X build. Measure them once
per configuration and again whenever either changes:

1. In the listing, find the program's own DOS open: `mov ah,0x3d` …
   `int 0x21` inside the CRT's `open`. SITE is the link address of that
   `int 0x21` (a BPINT break reports EIP *at* the int instruction).
2. Pick a string in the data object you can name (`asmview --xref` on a
   path literal finds one) for the data check.
3. `DBG_DATA_DELTA=<guess> dbgdrive calibrate SITE DATA_LINK EXPECT` — it
   arms `BPINT 21 3D`, runs to the first `Pr32` break, prints
   `CODE_DELTA = EIP - SITE`, the filename at `DS:EDX`, and `OK` /
   `MISMATCH` for the string. On a mismatch, read the string's runtime
   address off a `D` view and set `DBG_DATA_DELTA` to the difference.

Reference result (Cyberia 2, memsize 32, DOSBox-X 2026.05.02 debug build):
`calibrate 3356B 400D4 'c:\cyberia2'` → code `0x1c3000`, data `0x1c1000`
OK, selectors `CS=0160 DS=0168`.

## Rules (each one cost a run)

- **Breakpoints are INT3 patches placed at set time.** A `BP sel:off`
  typed while the CPU is still in the real-mode stub lands in conventional
  memory and never fires. Arm `BPINT 21 3D` at entry, run to the first
  `Pr32` break, then set code breakpoints.
- **Nothing interrupts a running emulation.** The debugger reads keys only
  while stopped. Every "look at the state now" must be a breakpoint armed
  beforehand; plan the stops before you press run.
- **Never queue a second F5.** An F5 typed while running is consumed at
  the next break and silently continues past it. Use `dbgdrive.run()`,
  which presses F5 only when the `I->` prompt is showing.
- **Each DOS/4GW `int 21h` breaks twice**: the protected-mode call and the
  extender's real-mode reflection. Filter on `regs()['mode'] == 'Pr32'`.
- **`BPINT 21 3D` is a free scene clock.** Engines open their per-scene
  files through DOS, so every scene transition and prefetch shows up as a
  break with the filename at `DS:EDX`.
- **Memory watches are slow; code breakpoints are free.** `BPLM` checks
  every instruction. A memory-change break reports the instruction
  *after* the write.
- **Input is poked, not typed.** Find the game's keyboard-state cells
  (the ISR's last-scancode / key-mask bytes) in the listing, break inside
  the UI loop's poll, `dbgdrive.poke(cell, value)`, continue. A mask the
  ISR only rebuilds on key events stays "held" until you poke it back.
- **Jump to the state under test through the engine's own path** — poke
  the cells its own menu or router reads, at the point it reads them.
  Poking a later variable skips bookkeeping and gives a state the
  shipped game never reaches.
- **The `D` view shows 7 lines (112 bytes).** `dbgdrive.dump()` returns
  what was on screen; loop for more, or use `MEMDUMPBIN` for bulk.
- **`run()` timing out with unchanged registers means the program is
  running — or has exited to DOS.** `dbgdrive screen` shows `(Running)`
  either way; read the `Output` pane (video-mode switches back to
  720x400 text = it quit, typically on a missing data file).
- **One scenario per session.** A scenario left running keeps typing into
  the next session; `dosdbg` kills the previous one by pid and
  `dosdbg stop` ends both.

## Debugger commands used

| Command | Effect |
|---|---|
| `BP sel:off` | code breakpoint (INT3 patch, see above) |
| `BPINT nn [ah]` | break on interrupt `nn`, optionally only for that AH |
| `BPLM linear` | break when the byte at a linear address changes |
| `BPPM sel:off` / `BPM seg:off` | the same, protected-mode / real-mode addressed |
| `BPLIST`, `BPDEL n` / `BPDEL *` | list / delete breakpoints |
| `D sel:off` | data view at address |
| `C sel:off` | code view at address |
| `SM sel:off b b …` | set memory bytes |
| `SR reg value` | set a register |
| `MEMDUMPBIN sel:off len` | write memory to `MEMDUMP.BIN` in DOSBox-X's cwd (the work dir); `MEMDUMP` = hex text |
| `LOG n` / `LOGS n` / `LOGL n` | trace the next n instructions to the CPU log (normal / short / long) |
| F5 / F10 / F11 | run / step over / trace into |

`HELP` inside the debugger lists the rest.
