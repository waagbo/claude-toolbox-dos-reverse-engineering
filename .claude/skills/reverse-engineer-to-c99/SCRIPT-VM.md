# Reversing a script VM

Games of this era put their logic in data: per-scene bytecode, per-actor
programs, trigger records. The interpreter in the binary is small; the
corpus is large, and almost everything you will claim about the game is
read through **your disassembler** of it. A wrong width or label there
corrupts every note written from its output. Cyberia lost months to four
such errors: an operand count, an inverted compare, a trigger mode and two
opcode names. So the disassembler is a port of the interpreter, held to
the same standard as the engine.

## 1. Find the machine

- **Interpreter**: a loop that fetches a word through a PC cell and
  dispatches `call [op*4 + TABLE]` or `jmp [eax*4 + TABLE]`.
- **Dispatch table**: dump it from the data object. Find its **end**
  from the bound check or the first non-code pointer; never stop "where the
  values stop looking plausible" — the neighbouring table holds plausible
  values too. A dispatch with no bound check is a hazard to port as-is
  (an out-of-range opcode calls through whatever follows the table).
- **Register file**: the cells the handlers address by index (scene
  variables, globals, actor fields). Often the actor record *is* the
  register file — `u16 r[n]` indexed by word.
- **Execution model**: run-to-completion per tick, or a **coroutine** (a
  marker word ends the frame and the PC is written back to the actor for
  next tick). Also, who calls the interpreter, when in the frame, and from
  which clock. Scripts, spawn schedules and movie frames often share one
  counter; find its sole incrementer.

## 2. Operand widths come from the handlers

For each opcode, read its handler and count **every** PC advance, summing
them. Handlers that read two operands in two steps each advance the PC
twice, and a scan that collects *distinct* `add pc, imm` values collapses
them to one. That mistake was made three times in two games. Value
decoders recurse (`elapsed(cp[<value>])`), and some modes consume an
operand they never use; both are widths. Build the width table this way,
never from corpus statistics.

## 3. Encodings come from the interpreter, not from the data

Copy the control-flow encoding exactly: a `SWITCH` may be
`selector, N, N×(case, jmp_off)` with the bodies *after* the pair table and
offsets in words, not inline bodies. Copy the comparison table with each
op's orientation and signedness from its `jcc` (`op 2 = b <= a`, signed).
One inverted op made a gate fire *before* a counter reached 10 instead of
after. Copy the trigger / record header layout byte for byte, from the
binder that reads it. A misread "trigger 2 = every frame" was really
"fires when the frame counter equals p1", and it had also dropped p2.

## 4. Names are hypotheses; name by effect

An opcode is named after the cell its handler **writes**, not after where
it appears. "0x21 = GAME_OVER" was a guess from its company in death
scripts; the handler writes the one-shot fade suppressor (NOFADE).
"0x04 = SCENE_RESTART" wrote the walker stand-down latch (WALKER_HOLD).
Record the handler address and written cells beside each name. Carry
opcodes that appear nowhere in the corpus as an explicit caveat.

## 5. Decode the whole corpus — and know what that proves

Run the disassembler over **every** script the game ships. A failure
proves a bug. A clean pass proves less: a wrong width table can self-heal
when a stray operand happens to decode as a valid zero-operand opcode. So
clean termination is a **falsifier, not a prover**. Get independent
ground truth where the binary offers it: the LE relocation table says which
dwords in the data object are pointers (and so where scripts start); the
debugger can stop on the dispatch and show the real PC sequence for one
scene. When you fix the tool, date the fix in its header and in the
retractions ledger. Every dump made before it is suspect.

## 6. Port the interpreter 1:1, then make it explain itself

Port the fetch loop and each handler with its address in a comment, the
register file as named cells (one per asm cell), and the value decoder as
one function. Port hazards as-is (a PC dereferenced before its NULL test);
a guard you add is NON-ASM.

Then give the port **provenance logging**: one line per player-visible
action naming the condition chain that let it run, e.g.:

```
[why] sc162 rec0 trig=5: svar[2] = 1 because ent[2].ctr >= 10 AND svar[2] == 0
      AND ([F] KEY & 1 OR [T] elapsed(cp[0]) > 120)
```

- Spell values exactly as the disassembler does, so a live log line greps
  against a static dump of the same script with no translation.
- A taken `IF` / matched case pushes a scope, so nesting composes as AND;
  an OR marks the arm that authorised it.
- Dedupe per (scene, record, action, chain) per visit. Do not rate-limit:
  that drops distinct causes, which are the information.
- Default it on if it is cheap (it was +0.04 % CPU), and gate it with an
  env var (`…_WHY=0/1/2`).

This was the single most productive debugging tool of the Cyberia port. It
turned "stuck somewhere" bug reports into named mechanisms from the
reporter's pasted log before any code was read. Pair it with an input log
(one line per key event: the key, the input context, the resolved action
or `ignored`).

## 7. Data the VM writes

Scripts and engine handlers may **write** into loaded scene data (an exit
field patched at runtime; node rows disabled by script and restored from
the checkpoint on load). Keep loaded data mutable in the port, and find
every restore path, or state decays monotonically across a session.
