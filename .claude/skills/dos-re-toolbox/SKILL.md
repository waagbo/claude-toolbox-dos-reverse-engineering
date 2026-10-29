---
name: dos-re-toolbox
description: >-
  Disassemble and reverse-engineer DOS-era binaries inside the dos-re-toolbox
  container: unpack a Watcom LE / DOS/4GW executable, produce the objdump
  listing and LE fixups, run Ghidra headless (import, decomp corpus, diff
  builds), trace the shipped program under the DOSBox-X debugger, or render
  a decoded format to png/mp4/wav for inspection.
---

# dos-re-toolbox

Everything runs in the `dos-re-toolbox` image (repo
`waagbo/claude-toolbox-dos-reverse-engineering`, cloned here at
`~/code/dos-re-toolbox`; prebuilt as
`ghcr.io/waagbo/claude-toolbox-dos-reverse-engineering:latest`, usable
via `REBOX_IMAGE=<that> rebox shell` when the host uid is 1000).
Every toolbox script prints its usage when run with no arguments — that
usage text is the authoritative flag reference; this skill is the workflow
and the gotchas.

## 0. Get a shell

```bash
~/code/dos-re-toolbox/rebox build          # once; re-run after Dockerfile/tools edits
~/code/dos-re-toolbox/rebox shell DIR      # DIR (default $PWD) mounted at /work
~/code/dos-re-toolbox/rebox run DIR -- CMD # one-shot, non-interactive
```

Only `/work` survives the container. Put Ghidra projects, listings,
decomp corpora and debugger work dirs under it. Done when `analyzeHeadless`
and `le-unpack` both resolve on `PATH`.

## 1. Unpack and list — the asm is the source of truth

```bash
le-unpack GAME.EXE out/                 # objN.bin + le_report.txt
flatdis out/obj1.bin 0x10000 > out/obj1.asm   # BASE = obj1's link base from the report
le-fixups GAME.EXE > out/fixups.tsv     # stderr must say "desynced pages 0"
```

- Take each object's base and the entry point from `le_report.txt`; never
  assume them. Two different binaries from the same toolchain can share
  identical bases (`0x10000` code / `0x40000` data in both Cyberia games),
  so an address is meaningless without the binary it belongs to — qualify
  every citation as `BINARY:0xADDR`.
- Absolute operands in an unrelocated object are **object-relative**:
  objdump prints `ds:0xbbc4` for flat `0x4bbc4`. Read listings through
  `asmview`, which appends the fixup target and any string literal:

  ```bash
  asmview out/obj1.asm -f out/fixups.tsv -s out/obj2.bin@0x40000 0x1b2c0 0x1b400
  asmview out/obj1.asm -f out/fixups.tsv -s out/obj2.bin@0x40000 --func 0x1b2c0
  asmview out/obj1.asm -f out/fixups.tsv --xref 0x40bee     # who touches this cell
  ```

- objdump disassembles linearly; data inside code (jump tables, the Watcom
  copyright banner) desyncs it until the next aligned instruction. When a
  function start looks wrong, re-list from the true entry:
  `flatdis out/obj1.bin 0x10000 0x23960 +0x200`.
- Sanity check for the unpack: at the LE entry point a Watcom binary has
  `EB xx` + `"WATCOM C/C++32 Run-Time system"`. If it does not, the object
  slicing is off (the classic bug: treating the LE+0x80 data-pages offset
  as LE-relative instead of file-relative shifts everything by e_lfanew).
- 16-bit code (real-mode stub, overlays): `FLATDIS_MODE=i8086 flatdis …`
  or `ndisasm -b16 -o BASE FILE`.

## 2. Ghidra headless — the decomp is a hint

```bash
ghidra-import ghidra-proj game GAME.EXE              # import + auto-analysis; slow
ghidra-dump  ghidra-proj game GAME.EXE out/decomp    # {addr}_{name}.c + _index.tsv
grep -P '\tFUN_0001b360\t' out/decomp/_index.tsv     # address, name, size, file
```

- Omit `-loader`; auto-detection picks the ghidra-lx-loader's
  **LE-Style** loader for Watcom LE. (Its LX and VxD loaders reject LE.)
- Ghidra's addresses match `le-unpack` + `flatdis` at the link base; that
  agreement is your check that the listing is aligned.
- Read every decomp next to its asm. Ghidra elides stack arguments
  (`void FUN_x(void)` that really takes args — look for `in_stack_*` and
  the pushes before each `call`), and `WARNING: Removing unreachable
  block` means it gave up on a switch or computed jump. When they
  disagree, the asm wins.
- `_index.tsv` rows whose file column starts `FAIL:` are functions the
  decompiler could not do — read those in asm only.
- Comparing builds (regional / patched versions of one game): dump both
  corpora, then `decomp-diff A/decomp ADDR_A B/decomp ADDR_B`. Empty output
  means the same code at a different address. The full method is the
  `reverse-engineer-compare-game-versions` skill.
- Re-run `ghidra-dump` after every re-import or rename pass so the corpus
  on disk matches the project.

Next steps live in their own skills: porting a function (or a script VM)
to C is `reverse-engineer-to-c99`; proving the port matches is
`reverse-engineer-validation`; comparing builds or games on one engine
(`decomp-match`, `xbin-*`, `bincmp`, `tree-census`) is
`reverse-engineer-compare-game-versions`.

## 3. Dynamic trace — the DOSBox-X debugger

Static reading cannot settle some questions (who writes a cell, which exit
a scene takes, what the timer really ticks at). Run the shipped binary:

```bash
dosdbg -C cdrive -D disc -e 'SET DOS4G=QUIET' GAME.EXE   # stops at entry
dbgdrive send 'BPINT 21 3D'      # file opens = free scene clock
dbgdrive run; dbgdrive regs      # first Pr32 break: now link addresses are mapped
dosdbg -C cdrive -S scenario.py GAME.EXE                 # scripted run
```

Read [`DOSDBG.md`](DOSDBG.md) before writing a scenario or setting any
code breakpoint: it covers the load-delta calibration, why breakpoints set
too early never fire, the F5 trap, and input injection.

## 4. Render what you decoded

A format is read when its output has been looked at, not when the parser
stops throwing. Every decoded format gets artifacts under
`artifacts/<topic>/` with an `INDEX.md` saying what each file is and what
the reviewer should see in it (including "this one is noise"). Recipes:
[`ARTIFACTS.md`](ARTIFACTS.md).

## Notes discipline

- Cite `BINARY:0xADDR` (or `listing:line`) for every load-bearing claim;
  an uncited claim is a hypothesis.
- Date-stamp findings with their evidence; correct old notes in place when
  a finding is overturned, and add a row to the project's `RETRACTIONS.md`
  (retracted belief → truth, evidence, commit). Check it before porting
  from any note.
- Label invented harness/viewer code NON-ASM; behaviour comes from the
  binary.
