# Compile cost (milestone 7b, stream O2)

Built on [ssa.md](ssa.md), [compiled-entry.md](compiled-entry.md) and [osr.md](osr.md).
Statements are design unless marked measured or ran. Numbers are instruction counts under
callgrind (`--smc-check=all-non-file`) for one fixed iteration, or `--jit-stats` counters.

## What it cost, and why

Measured at integration ea9965d0, Octane zlib, one iteration, `--jit`: 83.8G instructions
against 56.0G plain, 27.7G of them in `compileHot`, 24 MB of machine code. Mandreel: 36.0G
against 23.3G, 12.8G compiling, 23 MB of code. Four causes, largest first:

1. Every loop header of a hot function got its own OSR artefact, each a whole run of the
   pipeline over the whole function, again at every report. zlib has one function of 41,803
   bytecode bytes with 47 headers.
2. The ownership pass was quadratic: a sweep of the function per replaced value
   (`replaceAll`), a sweep per unboxed parameter web, a compaction after every pass.
3. Every exit names every local and operand, so exit slots outnumber instructions about ten
   to one (measured on box2d's compiled functions: 8,252 instructions, 3,707 exits, 82,211
   slots). Anything that walks slots per pass, or per value, multiplies that.
4. The backend emitted code per exit slot: 24 MB for zlib.

## What changed

- Loops compile one at a time, when a poll lands in them, bounded to the loop, with a budget
  and a backoff when the code deoptimizes (the loops stream; [osr.md](osr.md)).
- The ownership pass applies replacements through a forward map in one sweep, indexes
  incoming edges, hashes common values (the doubles stream), and:
  - decides parameter unboxing for the whole function first, as fixed points over the
    incoming edges, then rewrites instructions, edges and exit slots in one sweep
    (`ssa_ownership.unboxParams`). The SSA it produces is the same; the goldens did not move.
  - gives exit slots their modes from a table computed once per value (`fixSlots`).
  - compacts only where the next pass reads what a rewrite left stale: block ranges after an
    insertion, parameter ranges after a removal. Passes skip removed instructions.
- The verifier's ownership check counts the distinct moves of an exit against the number of
  outstanding owned values, linear in the exit's slots. It only walks every value, as before,
  to name the offending one when that count fails, so it accepts and rejects exactly what it
  did.
- `--jit-compile-budget=N` (default 32768) caps the bytecode bytes translated for one
  function over all its entry compilations (the doubles stream).
- A function unlinked for deoptimizing waits before it is compiled again: 8 hot budgets of
  entries before the first recompilation, 64 before the second (`jit_recompile.backoff`). A
  report from a loop poll compiles at once: that loop is running now.
- Exits are tables (next section).

## Exit tables

Compiled code no longer carries code per exit. A guard jumps to a two-instruction stub
(`lea rax, [record]`, `jmp common`); the function's one common stub stores the registers
that may hold values below the frame and calls helper `EXIT_STATE` (index 120,
`jit_exit_state.jitExitState`), which writes the interpreter state the record describes and
returns the exit status. The tables are read-only words after the code.

Record, in u32 words: pc, operand stack depth, code, slot count, entry count, then one word
per chunk: the chunk's byte offset from the record. `code` is the status to return, or
`CODE_FROM_FRAME` plus the frame offset of a u32 that holds it (a call's exit). A chunk is
eight entries of two words, kind and operand; equal chunks are stored once per function, so
exits that agree on a run of eight slots share it. Kinds: an i32, bool or double in a frame
slot or in a register; a constant; a value handed over as it is; a value with one count added
(a borrow); and, after the slots, a value the exit releases.

Nothing in a record is an address or a runtime identity: offsets are relative to the record,
so the code stays loadable into another runtime.

Measured (code bytes, one iteration, `--jit`): zlib 24.3 MB to 3.05 MB and mandreel 23.2 MB
to 4.79 MB with the tables alone; 234 KB and 864 KB with per-loop OSR as well.

## Counters

`--jit-stats` adds `translate-ns optimize-ns verify-ns backend-ns` (wall time by phase,
refusals included), `attempts` (pipeline runs), `bytecode-bytes` (handed to the translator),
`ssa-translated` and `ssa-optimized` (instructions before and after the ownership pass),
`over-budget` and `waited`. `--jit-dump` prints one `jit: cost entry|osr ...` line per
pipeline run and the SSA the backend receives (`jit: optimized ssa`).

## The test

`ssa.Function.work` counts the instructions and exit slots the rewriting passes walk
(compaction, forward-map sweeps, slot fixing, unboxing). `ssa_tests.compileWorkStaysLinear`
builds the same straight-line function at two sizes and fails when 3.7 times the bytecode
costs more than 6 times the work, or when the work per bytecode byte exceeds twice what it
was when written (78; the bound is 160). Before the one-pass unboxing the larger function
cost 13 times the smaller and 1,220 per byte.

## What is left

- Exits times locals is still the unit of cost. Sharing one snapshot of the locals between
  exits where no local changed would cut the slots about four times on box2d (82,211 to
  19,808, counted from the dumps). It changes `Function.slot` and every pass that walks
  slots, and the calls stream is extending exits now, so it is not done here.
- Compaction costs about 350 instructions per SSA instruction and still runs about eight
  times per compilation.
- Code that is compiled and then unlinked is the largest waste left: on box2d with
  `--jit-calls`, 26 of 30 compiled functions are unlinked within one iteration. The first
  compilation guesses int32 everywhere; type feedback for it would avoid most of these.
