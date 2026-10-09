# PuzzleBench

English | [中文](README.zh-CN.md)

A pilot implementation of a **budgeted hint economy** evaluation harness for LLMs. Design document: `spec-v0.3.md` (v0.1/v0.2 kept for the record).

Core mechanism: every task ships with a priced hint ladder (L1..LK, sold in order) → the model either buys freely from a shared wallet (protocol B) or receives hints level-by-level under a controlled grid (protocol A) → the grader attributes milestones by timestamp (achieved before reveal = unaided credit) → a single trajectory yields two scores (unaided / complete) plus an individualized regret value computed against the model's own capability matrix.

## Current state

Two environments share one grading pipeline (grader / Wallet / protocols A+B / regret oracle / metrics):

- **Wordle self-check env** (`envs/wordle.py`): a micro information economy, the first validation bed for the grading pipeline
- **Track B debug economy** (`envs/debug.py` + `tasks_debug.py`): buggy code + hidden test suite; public tests are echoed free, hidden-test information is sold by level — L1 failing names → L2 assertion diffs → L3 trimmed stack → L4 fault line ranges → L5 fix sketch; milestones cover F2P progress, P2P regression guard, and region consistency (after buying L4/L5 the first patch must touch a revealed region)
- **Synthetic mutation pipeline** (`mutate.py` + `seeds_debug.py`): SWE-smith-style bank scaling — 15 correct seeds (9 basic + 6 hard-tier: nested branches / chained comparisons / wraparound indexing / multi-loop carry) × 7 AST-local text-splice mutation operators × k-point HOM higher-order combinations (rejection sampling + if-only negation keep multi-fault tasks alive) × execution filtering (hanging / equivalent / all-dead mutants discarded), deterministic generation
- **Novel-spec seeds** (`seeds_novel.py`): 6 invented-rule tasks (Echo calendar / tide cipher / mirror walk / balanced ternary / jump queue / stutter merge) — out-of-distribution specs that block the "rewrite from memory" shortcut; each carries 2-3 skim-and-miss documentation traps so first attempts naturally fail and hint reveals are genuinely valuable
- **Track B2 stateful systems + anti-inertia traps** (`tasks_systems.py`): 14 hand-written tasks — 8 systems of 60-100 lines (versioned text buffer / FIFO warehouse / periodic scheduler / account ledger / doc history / config merge / rank table / discount rounding) plus 6 anti-inertia rule functions (inclusive stop / b-wins ties / collapsing empty fields / wraparound clamp / toward-zero truncation / ceil). All "documented but counter-intuitive": the bug reads fine line-by-line; only trigger sequences or boundary values expose it. Public tests cover only cases where both sides agree (green on buggy); hidden tests carry the traps; F2P/P2P partitions and public invariants asserted at import
- **Track B3 expression-language evaluators** (`tasks_expr.py`): 2 hand-written tasks (Zolarith integer arithmetic / Zoologic integer logic), ~120 lines of tokenizer + recursive-descent evaluator each; every documented grammar rule defies mainstream-language instinct (`^` left-associative / unary minus binds tighter than power / no comparison chaining / and-or same precedence left-swept); **2 interacting bugs planted per task** (each rule implemented by instinct), symptoms masking each other; hidden tests include inertia-rewrite detectors (rules the buggy code actually obeys — a rewrite dies instantly)
- **Track B4 multi-file packages** (`tasks_multifile.py`): 2 hand-written tasks (zelang lexer/parser/evaluator + ledgerd store/logic/facade), **2 bugs planted in 2 different modules per task** — the fault lives in file A while the symptom surfaces through file B (parser associativity via evaluator numbers, store aliasing via facade audit logs, logic's illicit credit via facade balances); the patch protocol supports per-file replacement via ` ```python:<module> ` blocks (an untagged block replaces the entry module), L4 lists all fault regions, surgical precision is per-file
- **Track B5 volume escalation** (`tasks_big.py`): an 11-module ~750-line toy database minidb (types/lexer/parser/expr/store/index/agg/serde/query/txn/api), **3 bugs in 3 different modules, each violating a rule documented in ANOTHER module's docstring** (comparison contract in dbtypes docs, visibility rule in dbapi docs, NULL ordering contract in dbstore docs); symptoms surface only end-to-end through dbapi.select; the aggregate/serde machinery carries no fault — pure reading load and rewrite detectors; 6 F2P + 21 P2P including one test that needs two faults fixed together. **Result: both effort arms one-turn perfect, diagnosis all correct — capacity pressure falsified as well**
- **Track B6 emergent rule interactions** (`tasks_emergent.py`): 2 hand-written tasks (creditd: interest accrual base × multi-day compounding / voted: quorum denominator × auto-inactivation timing × streak reset). Each task's rules are **stated precisely but never jointly** — the joint behavior must be derived, not looked up: same-day deposits earn interest TODAY (R1 closing balance × R2 immediate effect); the second consecutive miss still counts in THAT vote's denominator (R1 denominator at closing × R2 effective at closing); the buggy code resolves each composition by domain instinct (opening-balance convention / simple-interest batching / update-then-tally / reactivate without streak reset); public tests avoid every composition edge (green both ways), hidden tests hit exactly the compositions (5+3 F2P including cross-fault interaction)
- **Diagnosis probe + surgical precision** (grading-side): tasks carry `fault_choices` (4-choice fault statements, truth position scattered across tasks, distractors include "half-right" and "direction-reversed" variants); options are revealed **only after the suite goes green** (earlier reveal = free L5), the model answers once with `PROBE: n`; the diagnosis milestone (0.10) separates "located the fix" from "stumbled into green", polluted by L5 purchase; `meta.surgical.precision` measures the share of final-diff lines inside the fault regions (surgical fix = 1.0, full rewrite → 0), meta-only, no weight impact
- **Failure signal in the echo** (`envs/debug.py`): step replies include the hidden-test PASS COUNT (aggregate signal is free); WHICH tests fail and why remains the L1/L2 merchandise — pilots proved this is the necessary condition for the hint economy to start (without it, models see public-green and DONE at 0.06 with zero purchases; with it, the first full economic episode appeared: fail → buy L1 → fix by test name → solve)
- **Sandboxed execution** (`sandbox.py`): persistent worker subprocess + per-test SIGALRM timeout + automatic respawn on death; shared by env and mutation filter; real model patches never enter the harness process (process-level isolation, not a container; filesystem/network restriction is a pre-league requirement)
- **Real-model adapter** (`agents/llm.py`): plain httpx (no SDK), two providers — Anthropic native + OpenAI-compatible (Moonshot/DeepSeek/vLLM/Kimi share the format; reasoning-only endpoints support `reasoning_effort` passthrough); protocol `BUY: k` / fenced patch / `PROBE: n` / `DONE`; malformed-reply correction retries, transient-error backoff, token usage accounting
- **Multi-model runner** (`main_llm.py` + `models.toml`): the model list declares provider/model/key_env (keys live in environment variables only, never in files); same bank, budget and seeds per model under protocol B (`--protocol-a` adds the capability matrix); models without keys are skipped; raw results land in `results/*.json` (recomputable)

Verified mechanics (125 tests):

- Milestone attribution: server-side turn clock + spoil mapping; pre/post-reveal achievements are strictly separable (no self-reporting)
- Shared wallet: one wallet per protocol-B run — cross-task allocation is the real decision (otherwise regret degenerates); cross-task starvation has a deterministic unit test
- Protocol A purity: controlled cells run with a zero wallet (no purchases); regression tests assert no turn>0 purchase in-cell; granted hint text is injected in full at reset
- Ladder order: hints sell level by level, matching the oracle's cumulative-cost accounting
- Dual scores: unaided / complete; purchase-gated milestones exit the unaided score entirely (numerator and denominator together); not-applicable exits all denominators
- Regret oracle: knapsack DP over the model's own protocol-A matrix, offline-optimal allocation; missing cells filled downward by monotonicity
- Negative regret phenomenon: adaptive buying (buy only when stuck) can beat blind-allocation oracle — a real signal, not noise
- Full debug-economy chain: graded information price snapshots (failure state at purchase time), spoil taint (solved doesn't count unaided after L5 sketch reveal), region-consistency checks, zero-information purchases not-applicabled
- Mutation pipeline discipline: execution filtering guarantees every bank task has ≥1 F2P and ≥1 P2P (the regression guard always has substance); fault_region comes from the diff span; in the mutation banks public tests are red on the buggy source (the agent starts with a concrete failure), while the hand-written trap banks keep public tests green on buggy and signal failure via the hidden-test count
- Sandbox & real-model path: hanging patches marked hang with the worker alive, suicide patches (os._exit) marked sandbox with automatic respawn, sandbox vs in-process reference executions agree test-by-test, LLM protocol parsing/correction/backoff fully mock-covered

## Layout

```
puzzlebench/
  schema.py      # domain models (dataclasses): TaskSpec/MilestoneSpec/events/results
  grader.py      # attribution, dual scores, terminal scalars (pure functions, silent grading)
  economy.py     # Wallet: the shared wallet
  protocols.py   # protocol A (level-by-level grants → capability matrix) / B (free purchase) / regret oracle
  metrics.py     # SR(b,θ) curve + binomial SE, AUC + bootstrap CI, hint utilization E_k
  sandbox.py     # persistent-worker sandbox: JSON-lines protocol, per-test timeout, respawn
  config.py      # pydantic-settings + get_settings() (incl. LLM settings)
  logging.py     # loguru + stdlib interception
  words.py       # wordle word list (fully visible to the agent: construct purity)
  tasks_debug.py # Track B handmade bank: 4 original bugs + ladder/milestone specs
  seeds_debug.py # mutation seed bank: 15 correct classic implementations + suites (9 basic + 6 hard)
  seeds_novel.py # novel-spec seeds: 6 invented-rule tasks (out-of-distribution, anti-rewrite)
  tasks_systems.py # Track B2: stateful systems + anti-inertia traps (absence / alternative-semantics / state-flow / counter-intuitive rules)
  tasks_expr.py  # Track B3: expression-language evaluators (two interacting grammar traps + diagnosis options)
  tasks_multifile.py # Track B4: multi-file packages (cross-module dual faults, symptoms through interfaces)
  tasks_big.py   # Track B5: 11-module toy database (volume escalation, cross-module contract faults)
  tasks_emergent.py # Track B6: emergent rule interactions (rules stated alone, joint behavior derived)
  mutate.py      # synthetic mutation pipeline: operators / execution filter / task generation / CLI
  envs/wordle.py # self-check env: parsing, marking, consistency checks, hint dispensing, milestone harvest
  envs/debug.py  # debug economy env: sandboxed test execution, graded information goods, region consistency
  agents/scripted.py       # wordle scripted agent: skill/consistency/hint_policy knobs
  agents/debug_scripted.py # debug scripted agent: effective skill rises with held hints
  agents/llm.py            # real-model adapter: httpx direct, protocol parsing, backoff
main.py          # wordle demo: SR curve + budget tiers {0,3,7} × three prototypes × triple metrics
main_debug.py    # Track B demo: handmade + synthetic (subsampled) banks
main_llm.py      # real-model pilot (needs HINTBENCH_ANTHROPIC_API_KEY)
tests/           # pytest + pytest-asyncio
```

## Run

```bash
uv sync
uv run pytest                          # 125 tests
uv run python main.py                  # wordle demo
uv run python main_debug.py            # Track B debug-economy demo
uv run python -m puzzlebench.mutate --per-seed 2 --hom-per-seed 1  # generate the synthetic bank

# real-model evaluation (multi-model)
export HINTBENCH_ANTHROPIC_API_KEY=sk-ant-...   # or MOONSHOT_API_KEY / OPENAI_API_KEY
uv run python main_llm.py                        # every keyed model in models.toml
uv run python main_llm.py --only kimi-k2.8-coding --bank systems   # Track B2 trap bank
uv run python main_llm.py --bank expr            # Track B3 expression traps + diagnosis probe
uv run python main_llm.py --bank systems --protocol-a --seeds 1    # + capability matrix + individualized regret
```

`--bank`: `hand` (4 handmade) / `synth` (43 classic+hard+HOM mutations) / `novel` (17 novel-spec mutations) / `systems` (14 anti-inertia traps, the frontier pilot's main bank) / `expr` (2 expression evaluators, interacting dual bugs + diagnosis probe) / `multi` (2 multi-file packages, cross-module dual faults) / `big` (1 eleven-module toy database, volume escalation) / `em` (2 emergent rule-interaction tasks).

Add one `[[models]]` entry in `models.toml` to onboard a new model (Anthropic native or OpenAI-compatible endpoints both work).

## Pilot findings (kimi-for-coding, 2026-10)

Nine bank generations are all saturated at the result layer for the frontier pilot model — handmade / mutations / HOMs / novel specs / anti-inertia systems / expression grammars / multi-file packages / the 750-line volume package / emergent interactions: both effort arms one-turn perfect, surgical precision ≈1.0, diagnosis all correct. **As long as a rule is derivable from the docs (composed or not, at any scale tried), the model reads the whole thing, extracts it, and repairs surgically.** The remaining discriminative axes are behavioral — the diagnosis probe shows a real gradient (the systems window task: low-effort arm picked the direction-reversed distractor 3/3 times while fixing the code correctly), surgical-style variance across seeds, purchase timing, effort sensitivity — and cross-model comparison (result-layer gradient awaits a sub-frontier model).

## Next steps

1. **Contrast-model discrimination (top priority)**: add a second model (one stanza in models.toml) to accept spec §12 criteria 2/4; a sub-frontier model should restore result-layer gradient
2. Bank calibration & growth: BugsInPy/Defects4J anchor tasks (difficulty anchors only, not bank material); mutation-operator difficulty ordering back-filled from reference-model failure distributions; cost accounting (target ≤$0.2/task; the synthetic pipeline currently costs zero LLM tokens)
3. Sandbox upgrade: filesystem/network restriction (container or sandbox policy), required before any real leaderboard
