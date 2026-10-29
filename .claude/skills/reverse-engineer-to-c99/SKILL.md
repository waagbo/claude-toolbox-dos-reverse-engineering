---
name: reverse-engineer-to-c99
description: >-
  Port disassembled asm to asm-faithful C99 and reverse the data it reads:
  port FUN_xxxxx to C, reverse a script/bytecode VM or write its disassembler,
  decode a binary format (sprites, video, archives, saves), fix a live bug in
  a port by finding where it left the original, or settle a decomp-vs-asm
  disagreement (missing args, pruned calls, "Removing unreachable block").
---

# Reverse-engineering asm → asm-faithful C99

For a port meant to **behave like the original** — same outputs for the same
inputs, same state transitions, same edge cases. The disassembly is the
spec; Ghidra's decomp is a hint; your own notes are hypotheses. Getting the
listing, fixups, Ghidra corpus and debugger set up is the `dos-re-toolbox`
skill; proving the port matches is `reverse-engineer-validation`.

## Principles

1. **The asm wins.** Over the decomp, over the notes, over a comment in
   your own port, over a label your own tool prints.
2. **Mirror first, refactor never-or-later.** Same control flow, same
   field offsets, same sub-calls in the same order, same signedness. Clean
   up in a separate commit once behaviour matches.
3. **One asm cell, one port variable.** Name each by its address
   (`dat_42836` or a name with the address in its comment). The port's
   vocabulary file (a header of every cell, append-only, each with its
   address) is the map every later reader uses.
4. **Invented structure is the bug farm.** Anything the port has that the
   binary does not — a classifier that sorts scenes into kinds, a channel
   held in `main()` locals, a guard, a merged or split cell — is where
   divergence hides. Label it `NON-ASM` where it is defined, and suspect it
   *first* whenever the port misbehaves.
5. **Behaviour comes only from the binary.** Physics constants, timings,
   input maps, assets: reversed or absent. A feature blocked on unreversed
   code ships as a labelled skeleton ("pending reversal"), never as a
   plausible fake. Viewer and debug tooling may be invented; anything that
   pretends to be game output may not.

## Workflow

### 1. Survey

Decomp corpus + `_index.tsv`, the objdump listing, the LE fixups
(`dos-re-toolbox` §1–2). Grep the index for callers and callees before
reading anything.

### 2. Read the decomp, then the asm, every time

Settle from the asm what the decomp cannot show:

- **Signature.** The pushes before each `call` are the arguments (reverse
  order); args sit at `ebp+0x14…` after the 4-register Watcom prologue.
  `void FUN_x(void)` with `in_stack_*` in the body takes stack args.
  Register args (`eax`/`edx`/`ebx`/`ecx` under Watcom's register
  convention) are dropped silently, and with them the string references
  they carried. A "missing" feature can be a dropped register arg.
- **Pruned side effects.** Ghidra renders a call whose arguments it
  pruned as a bare `FUN_x();`. Three times in Cyberia such a line was a
  `memcpy` or a win check, the note called it "a no-op, ignored for
  now", and the port shipped without it for months. **A decomp line that
  looks pointless is a claim to check in the asm.**
- **Compares.** Port signedness from the branch (`jl/jg` signed, `jb/ja`
  unsigned) and operand order from the `cmp`. A signed limit compare read
  as unsigned froze records keyed on a garbage limit; an operand order read
  backwards inverted a gameplay gate.
- **Switches.** `jmp [reg*4+TABLE]`: the slot count comes from the guarding
  `cmp`. `WARNING: Removing unreachable block` means re-derive the flow
  from the asm.

### 3. Enumerate every writer of every cell you touch

Before porting a cell's behaviour, list *all* its writes and reads via
the fixup table (`asmview --xref ADDR`), not grep — `[reg+disp]` forms and
object-relative operands hide from text search. That list is the cell's
lifecycle, and it settles questions nothing else can: "a stale staged
cross is structurally impossible in the original" was proven by its nine
writes, one of which resets it at the top of every dispatch. A port path
that writes a cell no asm site writes is invented structure. Do the same
for every *reader*: if every loop in the original tests a latch, every loop
in the port tests it.

### 4. Script VMs get their own pass

If the code you are porting interprets data — a fetch loop, a PC cell,
`call [op*4 + TABLE]` — read [`SCRIPT-VM.md`](SCRIPT-VM.md) before porting
any handler or trusting any opcode name. Most of a game's logic lives in
that data, and most of the lasting RE mistakes in Cyberia were made in its
disassembler.

### 5. Port structurally, in asm order

Skeleton first: prologue, control flow, sub-calls stubbed, then leaves.
Keep the original's ordering of side effects inside a function. Order bugs
(a fail-latch clear moved after the state it guards) look correct in every
single-step test.

```c
/* CYB.EXE FUN_00027b48 (size 0x1fc) — per-variant painter dispatcher.
 * asm 0x27b48..0x27d44; decomp 00027b48_FUN_00027b48.c
 * Signature from asm: one byte arg at ebp+0x14 (decomp shows void).
 */
```

Open RE items are inline `TODO`s saying what is known and what is not.
Deviations are `/* NON-ASM: why */`. A bounds check the original lacks is
NON-ASM too, and reaching it means an upstream faithfulness bug, not a
case to handle.

### 6. Verify against the original

Headless, deterministic, on content as well as routing:
`reverse-engineer-validation`. Two facts from this pass shape the test:
the tick model (read the timer ISR and the PIT divisor; a body that runs on
alternate ticks of a 30 Hz counter is 15 Hz) and the input model (read the
ISR: which bit is which verb, which keys are edge-only).

### 7. Document

Every function header cites `BINARY:ADDR` and the decomp file. Findings go
in per-subsystem notes, dated, with evidence. When a finding is overturned:

- correct the note in place (banner or line-level `RETRACTED`), and
- add one row to the project's **retractions ledger** — `RETRACTIONS.md`:
  retracted belief → truth, settling evidence, commit.

Check the ledger before porting from any note. In Cyberia a retracted
label ("opcode 0x21 = GAME_OVER") came back six weeks later in new code
2000 lines below the comment retracting it. Before trusting any name, grep
the port for that opcode's or cell's existing comment.

## Fixing a live bug in the port

A bug report is a pointer to a divergence, not a symptom to patch:

1. Get a headless repro recipe first (one command that shows it).
2. Turn on the provenance and input logs (SCRIPT-VM.md §6) and read *why*
   the port did what it did.
3. If it misbehaves on the real route but not on direct entry (or vice
   versa), suspect invented structure — the route classifier, a held
   channel — before the engine. Direct-entry harnesses hand a scene state
   that no legitimate arrival produces; drive the real inbound edge before
   concluding a record "never fires".
4. Find the asm the port diverged from, port that, cite it in the commit.

## Formats

Probe the header in Python (`struct.unpack`) and dump referenced tables
from the data object by address. Recurring shapes in 90s DOS games: a
`u32` TOC size that doubles as `count*stride`; X packed in 2-px units;
`op & 0x80` literal/run RLE; a trailing 768/776-byte 6-bit DAC palette; a
compression flag that indexes a jump table of decoders. A format is decoded
when a reference decoder written from the asm runs on **every** file of its
type (corpus check) and its output has been rendered and looked at
(`dos-re-toolbox` ARTIFACTS.md). Loaded data can be engine state: an
engine that patches its own scene records at runtime, or restores them per
checkpoint, needs the port to keep them mutable and restorable.

## Before committing a port

- [ ] Decomp *and* asm read; signature from the pushes; no pruned call left as a no-op.
- [ ] Every cell's writers and readers enumerated; one port variable per cell.
- [ ] Signedness and compare orientation from the branch instructions.
- [ ] Side effects in asm order; every NON-ASM line labelled.
- [ ] Opcode / cell names checked against the retractions ledger.
- [ ] A headless check exercises the path, and it fails when the port is wrong.
