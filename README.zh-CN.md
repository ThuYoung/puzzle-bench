# PuzzleBench

[English](README.md) | 中文

预算化提示（hint economy）评测框架的 pilot 工程。设计文档见 `spec-v0.3.md`（v0.1/v0.2 保留备查）。

核心机制：题目配提示阶梯（L1..LK 逐级售卖）→ 模型在共享钱包预算下自由购买或受控逐级授予 → 判分器对里程碑做时间戳归因（提示揭示前达成 = 自主分）→ 同一条轨迹读出双分数（自答分 / 完成分）+ 以模型自身能力矩阵为基的个体化遗憾值。

## 当前状态

两套环境共用同一条判分管线（grader / Wallet / 协议 A/B / 遗憾值 oracle / 指标层）：

- **wordle 自检环境**（`envs/wordle.py`）：微型信息经济，判分管线的首个验证床
- **Track B 调试经济原型**（`envs/debug.py` + `tasks_debug.py`）：buggy 代码 + 隐藏测试套件；公开测试免费回显，隐藏测试信息按 L1 失败名 → L2 断言 diff → L3 裁剪栈 → L4 故障行区间 → L5 修复草图分级售卖；里程碑含 F2P 推进、P2P 回归守卫、区域一致性（购 L4/L5 后首个 patch 必须触及揭示区域）
- **合成变异管道**（`mutate.py` + `seeds_debug.py`）：SWE-smith 式题库扩容——15 个正确种子（9 基础 + 6 困难层：嵌套分支/链式比较/环绕索引/多循环进位）× 7 类 AST 定位文本剪接变异算子 × k 点 HOM 高阶组合（拒绝采样 + if-only 否定，保证多故障题存活率）× 执行过滤（挂死/等价/全灭变异一律丢弃），确定性生成
- **全新规格种子**（`seeds_novel.py`）：6 个自编规则题（Echo 历法/潮汐编码/镜像行走/平衡三进制/跳跃队列/口吃合并）——训练分布外规格，封死"凭记忆重写"捷径；每题 2-3 个"略读即错"的文档内陷阱条款，让首次尝试天然出错、提示揭示规则真正有价值（pilot 动机：经典种子被前沿模型全天花板秒穿）
- **Track B2 有状态系统 + 反惯性陷阱**（`tasks_systems.py`）：14 道手写题。前 8 道为 60-100 行系统（版本化文本缓冲/FIFO 仓储/周期调度器/账户账本/文档历史/配置合并/排名表/折扣舍入），后 6 道为反惯性规则函数（inclusive stop/b 优先平局/折叠空字段/环绕 clamp/向零截断/向上取整）——全部"文档写明但反直觉"：bug 逐行阅读合理，只有触发序列/边界值暴露；公开测试仅覆盖双方一致的用例（buggy 上全绿），隐藏测试携带陷阱，F2P/P2P 分区与公开不变量导入时断言
- **Track B3 表达式语言求值器**（`tasks_expr.py`）：2 道手写题（Zolarith 整数算术/Zoologic 整数逻辑），每题约 120 行 tokenizer+递归下降求值器；文档写明的语法规则每条都反主流语言惯性（`^` 左结合/一元负号紧于幂/比较不链式/and-or 同级左扫），**每题种 2 个交互 bug**（按惯性实现文档规则），症状互相掩盖；隐藏测试另含"惯性重写探测器"（buggy 实现本来遵守的规则，重写一发即死）
- **Track B4 多文件包**（`tasks_multifile.py`）：2 道手写题（zelang lexer/parser/evaluator 三模块 + ledgerd store/logic/facade 三模块），**每题 2 个 bug 种在 2 个不同模块**——故障在 A 文件、症状从 B 文件冒出（parser 的结合性错误经 evaluator 数值暴露、store 的别名经 facade 审计日志暴露、logic 的违规贷记经 facade 余额暴露）；patch 协议支持 ` ```python:<module> ` 按文件替换（无标记块替换入口模块）,L4 提示列全部故障区域，手术精度按文件统计；pilot 动机：单文件规格符合性检查已被前沿模型完全解决（B3 双交互陷阱 1 回合手术修复），结果层加压只剩尺度杠杆
- **Track B5 体量升级**（`tasks_big.py`）：11 模块约 750 行的玩具数据库 minidb（types/lexer/parser/expr/store/index/agg/serde/query/txn/api），**3 个 bug 种在 3 个不同模块且每条违反的规则写在另一模块的 docstring**（比较契约在 dbtypes 文档、可见性规则在 dbapi 文档、NULL 排序契约在 dbstore 文档），症状只能经 dbapi.select 端到端暴露；聚合与序列化机制不藏 bug，纯作阅读负载与重写探测器；F2P/P2P 分区导入时断言（6 F2P + 21 P2P，含一条需双故障同修的交互测试）；pilot 动机：容量压强（注意力/检索上限）是七代题库全穿后剩余的体量杠杆——**结果：双臂 1 回合满分、诊断全对，容量压强同样证伪**
- **Track B6 涌现式规则交互**（`tasks_emergent.py`）：2 道手写题（creditd 利息计提基数 × 多日复利 / voted 法定人数分母 × 缺席失权时机 × 连缺计数重置）。每道题的规则**各自在文档中精确写出、从不联合出现**——交集行为只能推导不能查表：同日存款当日计息（R1 期末余额 × R2 立即生效）、第二次连缺仍计入当次分母（R1 闭幕时分母 × R2 闭幕时生效）；buggy 代码用领域本能解开组合（期初余额惯例/单利批处理/先更新状态再计票/重新激活不清连缺）；公开测试避开一切组合边界（双方全绿），隐藏测试直击组合点（5+3 F2P，含跨故障交互题）
- **诊断探针 + 手术精度**（判分侧升级）：任务携带 `fault_choices`（4 选 1 故障陈述，真相选项位置跨题打散，干扰项含"只中一半"与"规则方向说反"）；**解出后**才在 patch 回显里揭示选项（此前揭示=白送 L5），模型一次性 `PROBE: n` 作答，diagnosis 里程碑（0.10）分离"定位修复"与"蒙到全绿"，L5 购买污染之；`meta.surgical.precision` 统计最终 diff 落在 fault_region 内的行占比（定位修复=1.0，全文重写→0），只入 meta 不动权重
- **双表征**（`banks.py` + `render_human.py`）：每道题都有两份——机器版 `DebugTask`（唯一事实源）与由它渲染的人读版 HTML 页面。`banks.py` 是共用 bank 注册表，保证模型跑批与人读渲染看到同一任务列表；`render_human.py` 为每题生成一个自足页面：逐字一致的 docstring 规格、带行号的 buggy 源码（与 L4 故障区域文本对齐）、公开测试、同价同文的 L1-L5 提示阶梯（提示文本按初始 buggy 状态生成）、一次性诊断题——人类解题者面对的信息与模型完全相同，可直接做人对模型的行为校准
- **失败信号入回显**（`envs/debug.py`）：step 回显含隐藏测试**通过计数**（聚合信号免费）；具体是哪个测试/为何失败仍是 L1/L2 的商品——pilot 证明这是提示经济启动的必要条件（无信号时模型收到公开全绿即 DONE，以 0.06 分结束且零购买；有信号后出现首个完整经济 episode：失败→买 L1→按测试名修复→解出）
- **沙箱执行**（`sandbox.py`）：常驻 worker 子进程 + 单测 SIGALRM 超时 + 死亡自动重生；env 与过滤器共用，真实模型 patch 永不进 harness 进程（进程级隔离，非容器；文件系统/网络限制是上真实榜前的要求）
- **真实模型适配器**（`agents/llm.py`）：httpx 直连（无 SDK），双 provider——Anthropic 原生 + OpenAI 兼容（Moonshot/DeepSeek/vLLM/Kimi 同格式；reasoning-only 端点支持 `reasoning_effort` 透传）；协议 `BUY: k` / fenced patch / `PROBE: n` / `DONE`，畸形回复校正重试、瞬态错误退避、token 用量累计
- **多模型跑批**（`main_llm.py` + `models.toml`）：模型清单声明 provider/model/key_env（密钥只进环境变量不进文件）；同一题库同一预算同一种子对每个模型跑协议 B（`--protocol-a` 加跑能力矩阵），缺 key 的模型自动跳过，原始结果落 `results/*.json`（可重算）

已验证的机制（125 个测试）：

- 里程碑归因：服务端回合时钟 + spoil 映射，提示揭示前后的达成严格可分（不靠模型自述）
- 共享钱包：协议 B 一轮 run 一个钱包，跨题分配才是真实决策（否则遗憾值退化）；跨题饥饿有确定性单测
- 协议 A 纯度：受控格零钱包禁购，回归测试断言格内无 turn>0 购买；授予提示的完整文本随 reset 注入
- 阶梯顺序：提示逐级售卖，与 oracle 的累计成本口径一致
- 双读数：自答分 / 完成分；购买门控里程碑整体退出自答分（分子分母同时），不适用时退出全部分母
- 遗憾值 oracle：对模型自身协议 A 矩阵做背包 DP，离线枚举最优分配；缺测格按单调性向下填充
- 负遗憾值现象：自适应购买（卡住才买）可优于盲分配 oracle，是真实信号不是噪声
- 调试经济全链路：分级信息商品价格快照（购买时刻的失败状态）、spoil 污点（L5 草图揭示后 solved 不计自答分）、区域一致性判定、零信息购买不适用化
- 变异管道纪律：执行过滤保证入库题必有 ≥1 F2P 且 ≥1 P2P（回归守卫永远有料）；fault_region 由 diff-span 自动给出；公开测试在 buggy 源码上必红（agent 起步即有信号）
- 沙箱与真实模型通路：挂死 patch 标记 hang 且 worker 存活、自杀式 patch（os._exit）标记 sandbox 且下次请求自动重生、沙箱与进程内参照执行逐测一致、LLM 协议解析/校正/退避全路径 mock 覆盖

## 结构

```
puzzlebench/
  schema.py      # 领域模型（dataclasses）：TaskSpec/MilestoneSpec/事件/结果
  grader.py      # 归因、双读数、终止标量（纯函数，静默判分）
  economy.py     # Wallet：共享钱包
  protocols.py   # 协议 A（逐级授予建能力矩阵）/ 协议 B（自由购买）/ 遗憾值 oracle
  metrics.py     # SR(b,θ) 曲线 + 二项 SE、AUC + bootstrap CI、提示利用率 E_k
  sandbox.py     # 常驻 worker 沙箱：JSON-lines 协议、单测超时、死亡重生
  config.py      # pydantic-settings + get_settings()（含 LLM 配置项）
  logging.py     # loguru + stdlib 拦截
  words.py       # wordle 词表（全量对 agent 可见：构念纯度）
  tasks_debug.py # Track B 手工任务库：4 道原创 bug + 阶梯/里程碑规格
  seeds_debug.py # 变异种子库：15 个经典正确实现 + 测试套件（9 基础 + 6 困难层）
  seeds_novel.py # 全新规格种子库：6 个自编规则题（分布外，反记忆重写）
  tasks_systems.py # Track B2：有状态系统 + 反惯性陷阱（缺失/替代语义/状态流/反直觉规则）
  tasks_expr.py  # Track B3：表达式语言求值器（双交互语法陷阱 bug + 诊断选项）
  tasks_multifile.py # Track B4：多文件包（跨模块双故障，症状经接口暴露）
  tasks_big.py   # Track B5：11 模块玩具数据库（体量升级，跨模块契约故障）
  tasks_emergent.py # Track B6：涌现式规则交互（规则各自写明、交集需推导）
  banks.py       # bank 注册表：load_bank 供模型跑批与人读渲染共用
  render_human.py # 人读站点生成器：每题一个可交互 HTML 页面
  mutate.py      # 合成变异管道：算子/执行过滤/任务生成/CLI
  envs/wordle.py # 自检环境：解析、标记、一致性检查、提示发放、里程碑收割
  envs/debug.py  # 调试经济环境：沙箱测试执行、分级信息商品、区域一致性
  agents/scripted.py       # wordle 脚本化代理：skill/consistency/hint_policy 可调
  agents/debug_scripted.py # 调试脚本化代理：有效技能随持有提示提升
  agents/llm.py            # 真实模型适配器：httpx 直连、协议解析、退避
main.py          # wordle demo：SR 曲线 + 预算档 {0,3,7} × 三原型三联指标
main_debug.py    # Track B demo：手工库 + 合成库（子采样）双跑
main_llm.py      # 真实模型 pilot（需 HINTBENCH_ANTHROPIC_API_KEY）
tests/           # pytest + pytest-asyncio
```

## 运行

```bash
uv sync
uv run pytest                          # 125 个测试
uv run python main.py                  # wordle demo
uv run python main_debug.py            # Track B 调试经济 demo
uv run python -m puzzlebench.mutate --per-seed 2 --hom-per-seed 1  # 生成合成题库
uv run python -m puzzlebench.render_human          # 生成人读站点到 docs/

# 真实模型评测（多模型）
export HINTBENCH_ANTHROPIC_API_KEY=sk-ant-...   # 或 MOONSHOT_API_KEY / OPENAI_API_KEY
uv run python main_llm.py                        # models.toml 里所有有 key 的模型
uv run python main_llm.py --only kimi-k2.8-coding --bank systems   # Track B2 陷阱库
uv run python main_llm.py --bank expr            # Track B3 表达式陷阱 + 诊断探针
uv run python main_llm.py --bank systems --protocol-a --seeds 1    # + 能力矩阵 + 个体化遗憾值
```

`--bank`:`hand`(4 手工题）/`synth`(43 经典+困难变异+HOM）/`novel`(17 全新规格变异）/`systems`(14 反惯性陷阱，前沿模型 pilot 主库）/`expr`(2 表达式求值器，双交互 bug + 诊断探针）/`multi`(2 多文件包，跨模块双故障）/`big`(1 道 11 模块玩具数据库，体量升级）/`em`(2 道涌现式规则交互题）。

在 `models.toml` 里加一行 `[[models]]` 即可接入新模型（Anthropic 原生或 OpenAI 兼容端点均可）。

## 下一步

1. **对照模型验证区分度（最高优先）**：九代题库对 kimi-for-coding 结果层全部封顶（手工/变异/HOM/全新规格/反惯性/表达式/多文件/750 行大体量/涌现交互，最后一代双臂 1 回合满分+手术 1.0+诊断全对）——**单模型结果层难度已穷尽，判别轴在行为层**：诊断探针方向说反模式（systems window low 臂 3/3）、手术风格方差、购买时机、effort 敏感性。接入第二个模型（models.toml 加一段）验收 spec §12 标准 2/4；次前沿模型应重新出结果层梯度
2. 题库校准与扩容：BugsInPy/Defects4J 锚题接入（只作难度锚不作题库）；变异算子难度序用参考模型失败分布回填；成本核算（目标 ≤$0.2/题，当前合成管道零 LLM 成本）
3. 沙箱升级：文件系统/网络限制（容器或沙箱策略），上真实榜前必做
