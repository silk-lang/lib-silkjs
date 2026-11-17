# Later AOT discussion and Bun research

Recovered on 2026-11-17 from the same session as the HTML plan. These assistant messages postdate that plan. Quoted external facts and benchmark claims are historical, not independently revalidated here. Statements about AOT being free, code always needing an interpreter, or the reasons for another engine's performance should not be treated as proven conclusions. Consult the newer coordination handoff for current implementation evidence.

Source: <t3-thread://v2/df925567-22cf-40cf-9a2c-46fb2bd05b71/3d78b1cc-ea92-4e4d-9957-9b496b4a1270>.

## Initial response to the user's AOT requirement (activity 84)

Agreed, and it costs little to design for now. I've saved it as a third standing constraint alongside optional JIT and "better, not simpler".

AOT fits this plan as an extension of something already in it. Phase 4 persists profiles and compiled code so a program's second run starts at peak speed. AOT is the same mechanism run at build time instead of after a first run, so one compiler serves both, provided three rules hold from the start:

- **Relocatable code.** Compiled code never embeds raw heap addresses (shapes, functions, constants, feedback slots). It refers to them through a per-code-unit table that is filled in at load time. A JIT that bakes pointers into instructions cannot be saved to disk.
- **Compiler inputs are serializable.** The compiler takes bytecode plus a feedback snapshot, not live engine state. That is already required for background compilation, so it costs nothing extra.
- **Speculation stays guarded.** AOT code for JavaScript still has to assume types and bail out to the interpreter when wrong. The interpreter therefore ships with every AOT binary, which the optional-JIT constraint already guarantees.

What AOT adds later, beyond persisted JIT code:

- **Profiles from a training run**, or static inference when there is none. TypeScript annotations could serve as hints, though they are unsound and would still need guards.
- **Whole-program assumptions**: a closed module graph, where exports that are never reassigned become constants.
- **A single-file executable**: engine, bytecode and precompiled code together.
- **Platforms that forbid JIT**, such as iOS and locked-down servers, where precompiled code is the only route to compiled speed.

I don't know the specifics of Bun's recent AOT work, so I'm not designing against it; if you have a link or a summary I'll fold it in.

None of the four running agents needs to change: the assembler emits bytes either way, and relocation records sit one layer above it. I'll write the relocation and serializable-input rules into the briefs for the second wave, where the compiler's IR and code-unit format get defined.

## Bun research response (activity 98)

Bun's AOT is real, merged, and experimental. It is also a very different design from what I sketched last turn, and its published results show where our plan could do better. This all postdates my training data, so everything below comes from the primary sources linked at the end.

## What it is

- **Status:** the engine half merged into Bun's WebKit fork on 25 October 2026 and the Bun half on 27 October. Docs list it under Bun v1.4.4 as experimental. `bun compile ./app.ts` is short for `bun build --compile --aot`.
- **Size of the effort:** about 2.3 million added lines in the Bun pull request and 1 million in the WebKit one.
- **Output:** one executable with machine code for every reachable function, npm packages included, and no JIT inside.

## How it works

- **A separate compiler, not the JIT.** Bun's front end turns syntax trees plus TypeScript checker types into a typed SSA IR. Nothing is compiled from bytecode.
- **No profile.** The program never runs at build time. Hot code is guessed from loops and the call graph.
- **Whole-program flow analysis** works out which objects and functions reach each position.
- **Types are predictions, not facts.** A value entering from outside is tested once on arrival. If the test fails, the call continues in a generic version of the same function. Nothing throws because of a type.
- **No deoptimization and no interpreter fallback** for code the build saw. A function that cannot be compiled is a build error. Only `eval`, `new Function` and `node:vm` are interpreted.
- **Fixed object layouts.** Classes and typed literals get a compiler-chosen layout with raw numbers and 32-bit references, which caps each thread at 32 GB of objects.
- **Closed world.** Existing members of built-ins cannot be replaced (`Array.prototype.push = fn` throws), and the program is assumed to have no code beyond what the build reached.
- **No code patching.** The code is mapped read-only from the file, so the kernel shares it between processes.

## Results they publish

| Case | AOT against Bun's JIT |
|---|---|
| TypeScript 6 compiler checking a 370,839-line project | 3.3x faster, 2.7x less memory |
| Claude Code CLI, time to first prompt | 141 ms vs 318 ms |
| Claude Code CLI, peak private memory | 44.7 MB vs 185.4 MB |
| Servers, first second after start | 1.03x to 1.93x more requests |
| Servers, warm: Hono, `Bun.serve`, `node:http` | level (within 3%) |
| Servers, warm: Express, Elysia, Fastify, Koa | 7% to 23% slower |
| 1,814 everyday idioms, compiled as in a very large program | median 1.44x behind the warm JIT |
| JetStream2 | most tests slower |

They state the losses plainly: untyped npm code, code generated with `new Function`, and old-style JavaScript all run slower than on a warm JIT. Builds take tens of seconds and gigabytes with no caching, and there is no cross-compilation.

## What this means for SilkJS

- **Their weak spot is our planned strength.** Every loss they list comes from having no profile and no way to respecialize. Our plan persists profiles and keeps the interpreter for bail-outs, so profile-guided AOT could keep warm-JIT peak speed on untyped code while still getting the startup win. That is a hypothesis until we build it.
- **The memory win needs file-backed code.** Their biggest numbers come from shipping no bytecode, no profiling data and no private JIT pages. For us that means persisted code must be position-independent and reach heap objects through a data-side table. Patching addresses into code at load would make the pages private and lose the sharing.
- **Entry guards with a generic version** are worth adopting alongside deoptimization. They avoid repeated bail-outs when a function is called with unexpected types.
- **Closed-world mode should be opt-in.** Frozen built-ins and a sealed module graph let calls like `arr.push(x)` compile without checks, but they break polyfill libraries, so they cannot be the default.
- **Typed fixed layouts are the expensive part.** They depend on a full TypeScript checker in the build. SilkJS has none, so this is a later decision, not something to design in now.

One thing I could not pin down: Jarred Sumner's earlier posts quote different numbers (24% faster startup, 48% less memory) from a September prototype. I've used the merged pull request's figures instead.

Sources:
- [Bun PR #45631: Compile TypeScript to machine code ahead of time](https://github.com/oven-sh/bun/pull/45631)
- [oven-sh/WebKit PR #757: [JSC] Ahead-of-time compilation](https://github.com/oven-sh/WebKit/pull/757)
- [Bun docs: Ahead-of-time compilation](https://bun.com/docs/compiler/aot)
- [Bun PR #47957: --aot-allow-executable-memory](https://github.com/oven-sh/bun/pull/47957)
- [Jarred Sumner, September preview post](https://x.com/jarredsumner/status/2104739495895781679)
- [Jarred Sumner, pipeline thread](https://x.com/jarredsumner/status/2111024425386877437)
- [daily.dev summary](https://daily.dev/posts/bun-aot-ahead-of-time-compilation-for-server-side-javascript-svlojmtvu)
