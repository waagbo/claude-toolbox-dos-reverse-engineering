---
name: reverse-engineer-compare-game-versions
description: >-
  Compare builds of a DOS game or engine: census regional / patched / OEM /
  ported releases, find what changed between two versions of an executable,
  map functions from a reversed binary onto a sequel or sibling on the same
  engine, carry original symbol names from one build onto another, or tell
  engine changes from asset re-mastering.
---

# Comparing game versions

Two goals, usually both: **what differs** (so the port can support every
build that matters) and **what is the same** (so work done on one binary
transfers to the other without being re-derived). The rule under both: a
claim of sameness or difference is only as good as the comparison behind
it, and **an address proves nothing across binaries**. Two builds from one
toolchain can share a link map: Cyberia 1 and 2 both put code at
`0x10000` and data at `0x40000`, so the same address is a different
function in each.

Tools are on the toolbox `PATH` (each prints usage with no args):
`tree-census`, `decomp-match`, `decomp-diff`, `xbin-match`, `xbin-seek`,
`xbin-diff`, `xbin-coverage`, `bincmp`; unpacking and Ghidra are the
`dos-re-toolbox` skill.

## 1. Census every build

```bash
tree-census us/ norway/ gog/ fmtowns/ --ci > census.tsv   # per-path content labels
md5sum */cyb.exe                                          # which executables are distinct
```

Write one table: build, version string, date, size, md5, where it came
from. Collapse byte-identical copies to one build. Record what each tree
*is*: a play-install directory left by someone's emulator setup is not a
master, and an installer (GOG `.sh`, setup `.exe`) may hold the fullest
master. An executable on a disc can be dead cargo: no extender on the disc,
references to assets the disc lacks, used only as a presence probe by the
real engine. Check that each build actually runs from its disc before
treating it as that release's engine.

## 2. Put each executable in its own address frame

Unpack each build separately (`le-unpack`, `flatdis`, `le-fixups`,
`ghidra-import`/`ghidra-dump` per build, one directory each). Before
comparing anything, **verify each frame**:

- the LE entry holds the Watcom banner;
- nearly every direct `call` target lands on a decomp function start at
  delta 0 (C1: 348 of 352).

A slicing bug shifts the whole image. One C2 extraction sat 0x2A50 low. Its
correspondence results had to be rebased, and its "absent from C2" scans
never saw the first 10 KB. Cite every address as `BINARY:0xADDR`, in notes
*and* in port comments. In a port that covers two games, a bare
`FUN_0001D170` gets checked against the wrong decomp.

## 3. Same engine, different build (patch, region, OEM)

```bash
decomp-match us/decomp no/decomp --labels us no          # identical / unmatched / suggested pairs
decomp-match us/decomp no/decomp --labels us no --align  # unmatched, per gap between anchors
decomp-diff us/decomp 0002ab90 no/decomp 0002ae20        # one pair, address-normalised
```

Then settle each changed pair **in the asm** (`xbin-diff`, `bincmp`):

- A hash mismatch is not a change until the asm says so. Ghidra types a
  relocated global differently between imports. The Cyberia VM showed as
  "changed" in all three builds and was instruction-identical.
- A "new" string or feature may already exist in the older build behind a
  register argument Ghidra dropped. The CD-ROM check and the progress
  writer were both in V1.86.
- Non-monotonic anchors can mean the linker moved whole modules. That is
  layout only: confirm with the deltas.

Classify each delta: bug fix, dead-store removal, reorder, new feature,
platform layer, layout only. Note whether the port already matches the
newer behaviour.

## 4. Different game or port on a shared engine

When builds diverge too far for decomp hashing, match by instruction
shape (addresses and `ds:` displacements normalised away):

```bash
xbin-match c2.asm c1.asm --index-a c2/_index.tsv --index-b c1/_index.tsv > pairs.tsv
xbin-coverage c2.asm --index-a c2/_index.tsv c1.asm > coverage.tsv
xbin-seek c1.asm 0x158fc c2.asm          # handlers reached only via pointer tables
xbin-diff c2.asm 0x21652 c1.asm 0x156ac  # read the pair
bincmp c2/obj1.bin 0x10000 0x21652 c1/obj1.bin 0x10000 0x156ac 0x9f   # settle it
```

- `xbin-match` scores are **leads**. A pair is real once `xbin-diff` reads
  the same and `bincmp` says IDENTICAL, or differs only in rel32/disp32
  operand bytes.
- `xbin-coverage` is the honest reuse number, since it needs no function
  boundary on the far side. Compiler idioms give every function a floor:
  below ~0.5 means shared idioms, not shared code.
- Images based at 0 (Phar Lap P3, raw blobs): pass `--addr-min` low
  enough, or small code addresses survive as literals and nothing matches.
- A different compiler (MetaWare High C vs Watcom) breaks shape matching
  and changes the calling convention. Match on string references, magic
  constants, data tables and call-graph position instead.
- **Symbol tables are the prize.** A port build that ships its symbols
  (FM Towns `cyb.exp`: 959 original names) can name the whole corpus of
  the stripped build. Carry a name across only over a settled match.

Use one relation vocabulary in the write-up:

| Relation | Meaning |
|---|---|
| IDENTICAL | byte-for-byte over the full body |
| SAME | instruction-identical apart from relocated globals and branch targets |
| VARIANT | same semantics, different code (re-emit, don't memcmp) |
| NEW / ABSENT | no counterpart |

## 5. Negative claims need their own evidence

"X is absent from B" needs a **mutually exclusive scan** over a *verified*
image, with its range stated. Example: the C1 LCG multiplier `0x41C64E6D`
occurs once in C1 and zero times in C2, and the C2 LFSR core occurs once in
C2 and zero times in C1. A shape miss is not absence: a VARIANT or a
pointer-table-only routine misses `xbin-match` and is still there.

## 6. Assets: engine change or mastering change?

From the census, split differences into engine (executables, compiled-in
tables) and assets. Inside assets, compare per format with its parser:
audio-only re-dubs, edited scripts (diff the disassembled bytecode, not the
bytes), re-rendered video, graphics edits, cut content (a node no table or
script reaches in any build), dropped files. Asset-side localization can
leave the executable untouched. Check the engine's own asset-name tables
for which files it will try to open, because the disc may ship fewer.

## 7. Write it up and feed the port

- A per-build delta list, and for engine pairs a correspondence table with
  a **port implication** column (reuse verbatim / parameterise the cell /
  extend the dispatch / write from scratch).
- A verdict paragraph: what carries over and what does not. In C1 → C2,
  the media and raster substrate was the same object code, and every
  routine that decides what happens matched nothing.
- When a measurement overturns an earlier guess, record it in a
  "Corrections" section; don't delete the guess. The correction is a
  finding.
- In the port: a shared code layer holds only **code that is the same in
  both originals** (IDENTICAL or SAME). "Looks similar" or "convenient to
  reuse" stays per game, or the shared layer stops being evidence about the
  binaries. Build selection is explicit (a flag or the version found in
  the data, never a guess). A build with an asset slot but no reversed
  engine is "unknown", not "probably the same engine".
