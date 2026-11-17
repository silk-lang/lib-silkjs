# JIT plan sources and recovery audit

Checked 2026-11-17 against this session's history, VM files, local Git objects, and GitHub branch heads.

## Which document to use

- **Latest coordination plan/status found:** [HANDOFF.md on `claude/sweet-ptolemy-f5t7na`](https://github.com/silk-lang/lib-silkjs/blob/claude/sweet-ptolemy-f5t7na/docs/jit/HANDOFF.md). The verified branch head was `ea9965d0c48d2777a6fa30bbbff23c0bfceb632c`; [this pinned copy](https://github.com/silk-lang/lib-silkjs/blob/ea9965d0c48d2777a6fa30bbbff23c0bfceb632c/docs/jit/HANDOFF.md) has 551 lines. It explicitly replaces `t3/jit-compiler-plan`, records later work through milestone 7, and links design and measurement documents. Its implementation/test claims were read, not rerun in this audit.
- **Full original strategic plan:** [restored HTML from 12 November](archive/2026-11-12-plan.html), recovered from the complete 384-line file-creation diff. This is the original text, not a reconstruction from the shorter handoff. [The later inline-preview variant](archive/2026-11-12-plan-inline.html) is also restored; it adapts presentation and minor wording, retaining the phase and verification content.
- **Additions after the HTML:** [AOT discussion and Bun research](archive/2026-11-12-aot-discussion.md), recovered from the later assistant messages. The HTML predates the user's explicit AOT request.
- **Original implementation specifications:** the [scorecard](archive/briefs/scorecard.md), [tier seam](archive/briefs/tier-seam.md), [code memory/assembler](archive/briefs/code-memory-assembler.md), [memory/feedback research](archive/briefs/memory-feedback-research.md), and [latest differential runner brief](archive/briefs/differential-latest.md). The superseded [original differential brief](archive/briefs/differential-original.md) and [relaunch brief](archive/briefs/differential-relaunch.md) are archived too. Briefs are historical requirements, not completed work or authorization to resume workers.
- **This branch's older recovery status:** [HANDOFF.md](HANDOFF.md), verified on 16 November before the later work. Keep it as a historical record, not current project status.
- **Recovered technical research:** [memory-feedback-research.md](memory-feedback-research.md), which distinguishes observations, hypotheses, and missing measurements.

## Is the earlier handoff complete?

No. It preserves the main constraints and a useful recovery sequence, but it is not the complete original plan, and it is no longer the latest implementation status.

Details in the original HTML that the short handoff omitted or compressed include:

- Explicit win conditions for peak throughput, time to peak, pause/memory, and startup. The numerical targets are aspirations, not achieved results.
- Phase 0–4 deliverables and individual exit criteria; quick and full compiler modes; architecture order; a separate regexp track.
- The full verification matrix: interpreter/compile-everything/quick/full configurations, scheduled deopt failures, allocation/count stress, test262 per tier, Node compatibility under compiled execution, and interpreter performance/size gates.
- Background compilation and safepoint installation, data-only inline caches and immutable code, native-call type/effect declarations, JS-written hot builtins, generators/async, and cross-module assumptions.
- The original decision table, memory-model alternatives, risks, and outstanding evidence.

The task briefs are more operationally specific than either plan: exact proposed interfaces and files, encoding/ABI tests, benchmark methods, generator categories, minimization, and pass criteria. They should be checked against current code before reuse.

The newer handoff copied this branch's seven milestone definitions, then added implementation details and validation records. It still says the original HTML was lost and that its abbreviated milestones were the fullest surviving plan. The recovery here supersedes those two statements. It also mixes historical and later status: for example an early limitations section says there is no compiled-entry hook, while later sections describe compiled entry and OSR. Use the dated later sections and linked implementation documents to resolve those differences.

## Historical text is not a current specification

The recovered HTML is deliberately unchanged. Several statements need qualification before being adopted into a current design:

- Its single-run benchmark table used a stale binary and was never a current-head baseline. Claims that it necessarily understates SilkJS, or that the entire gap is compiler-related, are not established by those measurements.
- Its wording that RC has no pauses omits deferred destruction and cycle collection. Its claim that every value copy writes a count omits borrowed/raw copies; the recovered research explains the actual ownership API.
- Feedback vectors are not guaranteed to accelerate the interpreter. Own-field reads already have inline bytecode keys; the research explicitly advises measuring migration.
- The HTML's fixed known-failure count, toolchain version, phase durations, unverified calling convention, and unimplemented-feature statements are historical. A direct C-ABI constant-call test does not prove every custom calling convention.
- The user mandated optional JIT and better measured outcomes, not a permanently fixed number of tiers or a particular collector. Later research kept collector changes experimental.
- AOT was added afterward. The newer handoff reports further user direction: start AOT only if it is cheap as the same compiler run at another time, and allow substantial engine restructuring while retaining interpreter-only operation. Those later directions are not present in this session's original HTML.
- Bun/LXR claims and competitor-design generalizations in the historical material were not independently revalidated during this audit. Preserve them as research leads, not design proofs.

## Provenance and search scope

Source session: <t3-thread://v2/df925567-22cf-40cf-9a2c-46fb2bd05b71/3d78b1cc-ea92-4e4d-9957-9b496b4a1270>.

- Activity 51: full creation diff for `/tmp/silkjs-jit-plan/silkjs-jit-plan.html`, item `turn-item:provider:claudeAgent:native-item:toolu_0166Br2HZ4DJ8p4ZmozDjNyq`. All 384 added lines were returned, with no truncation.
- Activity 57: complete HTML supplied to the attempted inline preview, item `turn-item:provider:claudeAgent:native-item:toolu_012QfsSiPb3tnx4q8bp7qn7H`.
- Activities 70, 72, 74, 76, 102, 121, 127: full task inputs, individually retrieved without truncation; each archived brief records its source item.
- Activities 84 and 98: AOT design response and subsequent Bun research response.
- VM searches covered relevant T3 worktrees, Claude project/memory directories, additional plan filenames under Codex/cache directories, the SilkJS checkouts, user document directories, and accessible `/tmp` paths. No standalone original HTML copy was found. Inaccessible system-private temporary directories were not searched.
- Git history revealed the newer coordination branch and its supporting `compiled-entry.md`, `feedback.md`, `ssa.md`, `tier-seam.md`, `osr.md`, `doubles.md`, `scorecard.md`, and `jit-scorecard.md`. They are available in the [newer branch's docs directory](https://github.com/silk-lang/lib-silkjs/tree/claude/sweet-ptolemy-f5t7na/docs/jit). GitHub confirmed the branch head above; the measurement branch `claude/project-thread-6ys4ab` at `7b04131e` has the same handoff and later scorecard edits.

The archives recover what was written; they do not merge the newer code, restart agents, or certify those branches' tests. There is no single fully reconciled document combining all original ambitions, subsequent decisions, and the latest implementation status.
