"""Human-readable rendering of the debug-economy banks.

Every task gets one self-contained HTML page presenting exactly what the model
faced: the docstring spec, the buggy source with line numbers, the public
tests, the L1-L5 hint ladder at list price (hint text computed on the initial
buggy state, as a turn-0 grant would see it), and the post-solve diagnosis
probe. A human solver can then check model behavior against identical
information.

The machine-readable DebugTask stays the single source of truth; these pages
are derived artifacts and must never be hand-edited. Regenerate after any
bank change.

CLI: uv run python -m puzzlebench.render_human [--banks em systems] [--out docs]
"""

from __future__ import annotations

import argparse
import ast
import html
import json
from dataclasses import dataclass
from pathlib import Path

from puzzlebench.economy import Wallet
from puzzlebench.envs.debug import DebugEnv, run_tests
from puzzlebench.tasks_debug import DebugTask, make_debug_spec

# pilot default in main_llm.py; the human wallet mirrors it
DEFAULT_BUDGET = 5

BANK_LABELS = {
    "hand": "手工原型",
    "systems": "B2 · 反惯性系统",
    "expr": "B3 · 表达式语言",
    "multi": "B4 · 多文件包",
    "big": "B5 · 大体量 minidb",
    "em": "B6 · 涌现式规则交互",
    "synth": "合成变异",
    "novel": "新规格变异",
}
HINT_NAMES = {
    1: "L1 · 失败测试名",
    2: "L2 · 断言详情",
    3: "L3 · 栈摘要",
    4: "L4 · 故障区域",
    5: "L5 · 修复草图",
}


@dataclass(frozen=True)
class PageTask:
    """Everything one human page needs, derived from a DebugTask."""

    task_id: str
    bank: str
    budget: int
    rule_docs: tuple[tuple[str, str], ...]  # (module label or "", docstring)
    buggy_modules: tuple[tuple[str, str], ...]  # (filename, source)
    fixed_modules: tuple[tuple[str, str], ...]
    public_tests: str
    hint_costs: dict[int, int]
    hint_texts: dict[int, str]
    choices: tuple[str, ...]
    answer: int  # 1-based; -1 when no probe


def _docstrings(task: DebugTask, modules: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    docs: list[tuple[str, str]] = []
    for name, src in modules:
        try:
            doc = ast.get_docstring(ast.parse(src))
        except SyntaxError:
            doc = None
        if doc:
            label = "" if len(modules) == 1 else f"{name}.py"
            docs.append((label, doc))
    return tuple(docs)


def page_task(task: DebugTask, bank: str, budget: int) -> PageTask:
    """Derive the page payload; hint texts come from the env's own renderer
    evaluated on the buggy state (in-process runner for speed)."""
    env = DebugEnv(task, wallet=Wallet(0), runner=run_tests)
    modules = task.files or (("solution", task.buggy_source),)
    fixed = task.fixed_files or (("solution", task.fixed_source),)
    spec = make_debug_spec(task, budget)
    return PageTask(
        task_id=task.task_id,
        bank=bank,
        budget=budget,
        rule_docs=_docstrings(task, modules),
        buggy_modules=tuple((f"{n}.py", s.rstrip("\n")) for n, s in modules),
        fixed_modules=tuple((f"{n}.py", s.rstrip("\n")) for n, s in fixed),
        public_tests="\n\n".join(body for _, body in task.public_tests),
        hint_costs={h.level: h.cost for h in spec.hints},
        hint_texts={h.level: env._hint_text(h.level, env._buggy_files) for h in spec.hints},
        choices=task.fault_choices,
        answer=task.fault_answer,
    )


CSS = """
:root {
  --paper: #F6F7F3; --card: #FFFFFF; --ink: #222B33; --muted: #5C6770;
  --line: #DDE1DA; --seal: #B03A2E; --seal-soft: #F7E9E6;
  --coin: #B98A1C; --coin-soft: #F8F0DA; --ok: #2E6B4F; --ok-soft: #E4F0E9;
  --code-bg: #F0F1EC; --shadow: 0 1px 2px rgba(34,43,51,.06);
  --font-display: "Noto Serif SC", "Songti SC", serif;
  --font-body: "Noto Sans SC", "PingFang SC", sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #17191D; --card: #1E2126; --ink: #E4E0D6; --muted: #98A0A8;
    --line: #33383F; --seal: #E0705F; --seal-soft: #36221F;
    --coin: #D9A94A; --coin-soft: #332A18; --ok: #6FBF94; --ok-soft: #1E2F27;
    --code-bg: #23262C; --shadow: 0 1px 2px rgba(0,0,0,.3);
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --paper: #17191D; --card: #1E2126; --ink: #E4E0D6; --muted: #98A0A8;
  --line: #33383F; --seal: #E0705F; --seal-soft: #36221F;
  --coin: #D9A94A; --coin-soft: #332A18; --ok: #6FBF94; --ok-soft: #1E2F27;
  --code-bg: #23262C; --shadow: 0 1px 2px rgba(0,0,0,.3);
  color-scheme: dark;
}
body { background: var(--paper); color: var(--ink); font-family: var(--font-body); line-height: 1.75; }
* { box-sizing: border-box; }
h1, h2 { font-family: var(--font-display); text-wrap: balance; }
button { font-family: var(--font-body); cursor: pointer; }
button:focus-visible, a:focus-visible, summary:focus-visible { outline: 2px solid var(--seal); outline-offset: 2px; }
.site-head { border-bottom: 2px solid var(--ink); padding: 14px 0; margin-bottom: 28px; }
.site-head .wrap { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
.brand { font-family: var(--font-display); font-size: 22px; font-weight: 700; text-decoration: none; color: var(--ink); }
.brand em { font-style: normal; color: var(--seal); }
.site-sub { color: var(--muted); font-size: 13px; letter-spacing: .06em; }
.wrap { max-width: 1060px; margin: 0 auto; }
.intro { max-width: 68ch; margin-bottom: 26px; }
.intro p { margin: 0 0 10px; }
.intro .proto { font-size: 13.5px; color: var(--muted); border-left: 3px solid var(--coin); padding-left: 12px; }
.bank-h { font-size: 15px; letter-spacing: .12em; color: var(--muted); margin: 26px 0 10px; font-weight: 600; }
.deck { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 3px; padding: 12px 16px;
  box-shadow: var(--shadow); text-decoration: none; color: var(--ink); display: flex; align-items: center; gap: 10px; }
.card:hover { border-color: var(--ink); }
.card .tid { font-family: var(--font-mono); font-size: 12.5px; flex: 1; }
.card .meta { font-size: 11.5px; color: var(--muted); white-space: nowrap; }
.stamp { display: inline-block; font-family: var(--font-display); font-weight: 700; color: var(--seal);
  border: 2px solid var(--seal); border-radius: 3px; padding: 0 8px; font-size: 12px; letter-spacing: .2em;
  transform: rotate(-3deg); opacity: .9; }
.stamp.ok { color: var(--ok); border-color: var(--ok); }
.crumb { font-size: 13px; margin-bottom: 14px; }
.crumb a { color: var(--muted); text-decoration: none; }
.crumb a:hover { color: var(--ink); }
.pz { display: grid; grid-template-columns: minmax(0,1fr) 300px; gap: 26px; align-items: start; }
@media (max-width: 860px) { .pz { grid-template-columns: 1fr; } }
.pz-title { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 4px; }
.pz-title h1 { margin: 0; font-size: 24px; font-family: var(--font-mono); font-weight: 600; }
.blk { margin-bottom: 22px; }
.blk > h3 { font-size: 14px; letter-spacing: .18em; color: var(--muted); margin: 0 0 8px;
  font-family: var(--font-body); font-weight: 600; }
.rules { background: var(--card); border: 1px solid var(--line); border-radius: 3px; padding: 14px 18px; }
.rules .doc-label { font-family: var(--font-mono); font-size: 11.5px; color: var(--muted); margin-bottom: 4px; }
.rules pre { margin: 0 0 12px; white-space: pre-wrap; font-family: var(--font-body); font-size: 14px; line-height: 1.7; }
.rules pre:last-child { margin-bottom: 0; }
.mod-label { font-family: var(--font-mono); font-size: 12px; color: var(--muted); margin: 14px 0 4px; }
.code-wrap { background: var(--code-bg); border: 1px solid var(--line); border-radius: 3px; overflow-x: auto;
  font-family: var(--font-mono); font-size: 12.8px; line-height: 1.6; }
.code-wrap table { border-collapse: collapse; width: 100%; }
.code-wrap td { padding: 0; vertical-align: top; }
.code-wrap td.ln { text-align: right; color: var(--muted); opacity: .65; padding: 0 10px 0 14px;
  user-select: none; width: 1%; border-right: 1px solid var(--line); }
.code-wrap td.src { padding: 0 14px 0 12px; white-space: pre; }
.code-wrap tr:first-child td { padding-top: 10px; }
.code-wrap tr:last-child td { padding-bottom: 10px; }
.side { display: flex; flex-direction: column; gap: 16px; position: sticky; top: calc(env(safe-area-inset-top,0px) + 12px); }
.panel { background: var(--card); border: 1px solid var(--line); border-radius: 3px; padding: 14px 16px; box-shadow: var(--shadow); }
.panel h3 { margin: 0 0 10px; font-size: 13px; letter-spacing: .18em; color: var(--muted); font-weight: 600; }
.wallet { display: flex; align-items: center; justify-content: space-between; background: var(--coin-soft);
  border: 1px solid var(--coin); border-radius: 3px; padding: 10px 14px; font-size: 14px; }
.wallet b { font-family: var(--font-mono); font-size: 18px; color: var(--coin); font-variant-numeric: tabular-nums; }
.hint-btn { display: flex; width: 100%; align-items: center; justify-content: space-between; gap: 8px;
  background: var(--card); border: 1px solid var(--line); border-radius: 3px; padding: 8px 12px; margin-top: 8px;
  font-size: 13.5px; color: var(--ink); text-align: left; }
.hint-btn:hover:not(:disabled) { border-color: var(--coin); }
.hint-btn:disabled { opacity: .45; cursor: not-allowed; }
.hint-btn .cost { font-family: var(--font-mono); color: var(--coin); font-size: 12px; white-space: nowrap; }
.hint-body { border: 1px solid var(--coin); border-top: none; background: var(--coin-soft);
  padding: 10px 14px; font-size: 12.5px; border-radius: 0 0 3px 3px; font-family: var(--font-mono);
  white-space: pre-wrap; word-break: break-word; }
.bought { border-bottom-left-radius: 0; border-bottom-right-radius: 0; border-color: var(--coin); }
.gate-note { font-size: 13px; color: var(--muted); margin-bottom: 10px; }
.btn { background: var(--ink); color: var(--paper); border: none; border-radius: 3px; padding: 9px 18px;
  font-size: 14px; letter-spacing: .04em; }
.btn:hover { opacity: .88; }
.choice { display: flex; gap: 10px; align-items: flex-start; border: 1px solid var(--line); border-radius: 3px;
  background: var(--card); padding: 10px 14px; margin-top: 8px; font-size: 13.5px; width: 100%; text-align: left; }
.choice .no { font-family: var(--font-mono); color: var(--muted); border: 1px solid var(--line);
  border-radius: 2px; padding: 0 6px; flex: none; }
.choice:hover:not(:disabled) { border-color: var(--ink); }
.choice:disabled { cursor: default; }
.choice.right { border-color: var(--ok); background: var(--ok-soft); }
.choice.right .no { color: var(--ok); border-color: var(--ok); }
.choice.wrong { border-color: var(--seal); background: var(--seal-soft); }
.choice.wrong .no { color: var(--seal); border-color: var(--seal); }
.verdict { margin-top: 12px; font-size: 14px; padding: 10px 14px; border-radius: 3px; }
.verdict.ok { background: var(--ok-soft); color: var(--ok); }
.verdict.no { background: var(--seal-soft); color: var(--seal); }
details.answer { margin-top: 26px; border-top: 1px dashed var(--line); padding-top: 14px; }
details.answer summary { cursor: pointer; font-size: 13px; color: var(--muted); letter-spacing: .12em; list-style: none; display: inline-block; }
details.answer summary::before { content: "▸ "; }
details.answer[open] summary::before { content: "▾ "; }
details.answer summary:hover { color: var(--seal); }
footer.site { margin: 44px 0 12px; color: var(--muted); font-size: 12.5px; border-top: 1px solid var(--line); padding-top: 14px; }
"""

PAGE_JS = """
const store = {
  get(k, d) { try { const v = localStorage.getItem("pbh." + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("pbh." + k, JSON.stringify(v)); } catch {} },
};
let S = store.get(TASK.id, { coins: TASK.budget, hints: [], gate: false, probe: null });
function save() { store.set(TASK.id, S); }
function render() {
  const hints = TASK.levels.map(lv => {
    if (S.hints.includes(lv)) {
      return `<button class="hint-btn bought" disabled><span>${TASK.names[lv]}</span><span class="cost">已购</span></button>
        <div class="hint-body">${TASK.hints[lv]}</div>`;
    }
    const ok = S.coins >= TASK.costs[lv];
    return `<button class="hint-btn" data-hint="${lv}" ${ok ? "" : "disabled"}>
      <span>${TASK.names[lv]}</span><span class="cost">${TASK.costs[lv]} 币</span></button>`;
  }).join("");
  document.getElementById("wallet").innerHTML = `<span>提示币余额</span><b>${S.coins}</b>`;
  document.getElementById("ladder").innerHTML = hints;
  const probe = document.getElementById("probe");
  if (!probe) return;
  if (!S.gate) {
    probe.innerHTML = `<p class="gate-note">诊断题在『修复完成』后才解锁——与模型同规则：先让测试全绿，再谈理解。</p>
      <button class="btn" id="gate">我已修复，解锁诊断题</button>`;
    return;
  }
  if (S.probe === null) {
    probe.innerHTML = `<p class="gate-note">下面几个陈述只有一个是真的。<b>只有一次机会</b>，选好再点。</p>` +
      TASK.choices.map((c, i) => `<button class="choice" data-choice="${i + 1}"><span class="no">${i + 1}</span><span>${c}</span></button>`).join("");
    return;
  }
  const ok = S.probe === TASK.answer;
  probe.innerHTML = TASK.choices.map((c, i) => {
    const n = i + 1;
    const cls = n === TASK.answer ? "right" : (n === S.probe ? "wrong" : "");
    return `<button class="choice ${cls}" disabled><span class="no">${n}</span><span>${c}</span></button>`;
  }).join("") + `<div class="verdict ${ok ? "ok" : "no"}">${ok
    ? "✓ 答对了——你不仅修好了，也真懂了。"
    : "✗ 答错。绿色的才是真相——你修好的方式可能对了，但故障陈述选错了。"}</div>`;
}
document.addEventListener("click", ev => {
  const h = ev.target.closest("[data-hint]");
  if (h) {
    const lv = Number(h.dataset.hint);
    if (!S.hints.includes(lv) && S.coins >= TASK.costs[lv]) { S.coins -= TASK.costs[lv]; S.hints.push(lv); save(); render(); }
    return;
  }
  if (ev.target.closest("#gate")) { S.gate = true; save(); render(); return; }
  const c = ev.target.closest("[data-choice]");
  if (c && S.probe === null) { S.probe = Number(c.dataset.choice); save(); render(); }
});
render();
"""

INDEX_JS = """
document.querySelectorAll("[data-task]").forEach(el => {
  try {
    const s = JSON.parse(localStorage.getItem("pbh." + el.dataset.task) || "null");
    if (s && s.probe !== null && s.probe !== undefined) {
      const ok = s.answer === undefined; // index does not know answers; stamp only
      el.insertAdjacentHTML("beforeend", `<span class="stamp">已答</span>`);
    }
  } catch {}
});
"""


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def _code_block(src: str) -> str:
    rows = "".join(
        f'<tr><td class="ln">{i}</td><td class="src">{_esc(line) or " "}</td></tr>'
        for i, line in enumerate(src.split("\n"), 1)
    )
    return f'<div class="code-wrap"><table>{rows}</table></div>'


def _json_for_script(obj) -> str:
    # JSON embedded in a <script>; escape "</" so sources cannot close the tag
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def render_page(t: PageTask) -> str:
    rules = "".join(
        (f'<div class="doc-label">{_esc(label)}</div>' if label else "")
        + f"<pre>{_esc(doc)}</pre>"
        for label, doc in t.rule_docs
    ) or '<pre>（本题没有文档字符串——规格即代码本身。）</pre>'
    buggy = "".join(
        (f'<div class="mod-label">{_esc(name)}</div>' if len(t.buggy_modules) > 1 else "")
        + _code_block(src)
        for name, src in t.buggy_modules
    )
    fixed = "".join(
        (f'<div class="mod-label">{_esc(name)}</div>' if len(t.fixed_modules) > 1 else "")
        + _code_block(src)
        for name, src in t.fixed_modules
    )
    probe_panel = (
        '<div class="blk"><h3>诊 断 题</h3><div id="probe"></div></div>'
        if t.choices
        else '<div class="blk"><h3>诊 断 题</h3><p class="gate-note">本题不设诊断题（该题库无 fault_choices 元数据）。</p></div>'
    )
    task_json = _json_for_script({
        "id": t.task_id,
        "budget": t.budget,
        "levels": sorted(t.hint_costs),
        "costs": t.hint_costs,
        "names": {str(k): v for k, v in HINT_NAMES.items() if k in t.hint_costs},
        "hints": t.hint_texts,
        "choices": list(t.choices),
        "answer": t.answer,
    })
    script = f"<script>\nconst TASK = {task_json};\n{PAGE_JS}\n</script>" if t.choices or True else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{_esc(t.task_id)} · PuzzleBench 人测场</title>
<style>{CSS}</style>
</head>
<body>
<header class="site-head"><div class="wrap">
  <a class="brand" href="index.html">Puzzle<em>Bench</em></a>
  <span class="site-sub">人测校准场 · 同一批题，AI 已交卷</span>
</div></header>
<main class="wrap">
<div class="crumb"><a href="index.html">← 题目列表</a> · {_esc(BANK_LABELS.get(t.bank, t.bank))}</div>
<div class="pz">
  <div>
    <div class="pz-title"><h1>{_esc(t.task_id)}</h1></div>
    <div class="blk"><h3>规　则（与模型所读逐字一致）</h3><div class="rules">{rules}</div></div>
    <div class="blk"><h3>代　码（含故障，行号与 L4 提示对应）</h3>{buggy}</div>
    <div class="blk"><h3>公开测试（可手动自查）</h3>{_code_block(t.public_tests)}</div>
    {probe_panel}
    <details class="answer"><summary>参考答案（建议先用提示）</summary>
      <div class="blk" style="margin-top:12px">{fixed}</div>
    </details>
  </div>
  <div class="side">
    <div class="wallet" id="wallet"></div>
    <div class="panel"><h3>提示阶梯</h3><div id="ladder"></div>
      <p class="gate-note" style="margin-top:10px">提示内容按初始 buggy 状态生成，与模型第 0 回合所见一致。</p></div>
    <div class="panel"><h3>谜题信息</h3>
      <p class="gate-note">题库：{_esc(t.bank)}<br>模块数：{len(t.buggy_modules)}<br>预算：{t.budget} 币 · 定价 {"/".join(str(t.hint_costs[k]) for k in sorted(t.hint_costs))}</p></div>
  </div>
</div>
</main>
<footer class="site wrap">PuzzleBench · 预算化提示经济评测 · 人读版由机器版自动生成，勿手改</footer>
{script}
</body>
</html>
"""


def render_index(groups: dict[str, list[PageTask]]) -> str:
    sections = []
    for bank, tasks in groups.items():
        cards = "".join(
            f'<a class="card" href="{_esc(t.task_id)}.html" data-task="{_esc(t.task_id)}">'
            f'<span class="tid">{_esc(t.task_id)}</span>'
            f'<span class="meta">{"" if t.choices else "无诊断题 · "}{len(t.buggy_modules)} 模块</span></a>'
            for t in tasks
        )
        sections.append(
            f'<h2 class="bank-h">{_esc(BANK_LABELS.get(bank, bank))}（{len(tasks)}）</h2>'
            f'<div class="deck">{cards}</div>'
        )
    total = sum(len(v) for v in groups.values())
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>PuzzleBench 人测场</title>
<style>{CSS}</style>
</head>
<body>
<header class="site-head"><div class="wrap">
  <a class="brand" href="index.html">Puzzle<em>Bench</em></a>
  <span class="site-sub">人测校准场 · 同一批题，AI 已交卷</span>
</div></header>
<main class="wrap">
<div class="intro">
  <p>这里是 PuzzleBench 全库 {total} 道题的人读版。每道题的页面与模型面对的机器版由同一份 TaskSpec 生成：同一份规则文档、同一段 buggy 代码、同价同文的 L1-L5 提示阶梯、同一道诊断题。</p>
  <p class="proto">规则：每题 <b>{DEFAULT_BUDGET} 枚提示币</b>，提示逐级变贵变直白，买不买随你。读懂规则和代码，找出所有 bug；自觉修好后解锁诊断题，从故障陈述里选出真相——<b>只有一次机会</b>。页面无法替你跑隐藏测试，修复靠自觉，诊断见真章。做完一题，再对照该题的模型跑批记录（results/），就是一次人对模型的行为校准。</p>
</div>
{"".join(sections)}
</main>
<footer class="site wrap">PuzzleBench · 人读版由 puzzlebench.render_human 自动生成，勿手改</footer>
<script>{INDEX_JS}</script>
</body>
</html>
"""


def main() -> None:
    from puzzlebench.banks import BANK_NAMES, load_bank

    ap = argparse.ArgumentParser(description="render human-readable pages for the debug banks")
    ap.add_argument("--banks", nargs="*", default=list(BANK_NAMES))
    ap.add_argument("--out", type=Path, default=Path("docs"))
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    groups: dict[str, list[PageTask]] = {}
    for bank in args.banks:
        tasks = load_bank(bank)
        pages = [page_task(t, bank, args.budget) for t in tasks]
        groups[bank] = pages
        for p in pages:
            (args.out / f"{p.task_id}.html").write_text(render_page(p), encoding="utf-8")
        print(f"{bank}: {len(pages)} pages")
    (args.out / "index.html").write_text(render_index(groups), encoding="utf-8")
    print(f"site at {args.out / 'index.html'}")


if __name__ == "__main__":
    main()
