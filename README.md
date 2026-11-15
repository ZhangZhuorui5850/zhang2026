# zhang2026 · 科研实训多智能体套件（MARS-8H）

一套面向「一天 8 小时、单卡 A100、无 sudo、外网可能不通」这种**受限科研实训考试**的多智能体协作流水线。
给的是**方法和提示词**，不是答案。题目自己去考场拿。

```
26 条提示词 · 10 个门控阶段 · 7 个可跑工具 · 5 个题型模板 · 29 项离线自检
```

---

## 这是什么 / 不是什么

| 是 | 不是 |
|---|---|
| 一套把"调研 → 方案 → 写码 → 训练 → 监控 → 修错 → 交付 → 验收"串起来的**流程** | 某道题的答案 |
| 26 条可直接粘贴的角色提示词，含输出契约与配额 | 一个需要 API Key 才能用的黑盒服务 |
| 零依赖编排器：5 侦察兵并行、断点续跑、失败降级 | 通用 Agent 框架（不替代 LangGraph/AutoGen） |
| 交付前机械验收（`QA_RESULT: PASS/FAIL`） | 保证提分的东西（它保证**不翻车**） |

> ⚠️ 考场规则禁止公开发布考试相关内容。本仓库只有**通用方法与虚构示例**，不要往这里提交真题、数据或答案。

---

## 30 秒上手

```bash
git clone https://github.com/ZhangZhuorui5850/zhang2026.git
cd zhang2026

# ① 看流水线装没装上（不联网、不花钱）
python3 tools/orchestrator-mars.py --dry-run

# ② 试跑骨架（30 秒，应看到 SMOKE_OK）
cd tools && python3 train_template.py --mode smoke && cd ..

# ③ 给一串题目路径，让它生成"该对 agent 说的话"
bash scripts/bootstrap.sh ~/work/problem1 480
```

---

## 三种用法（按你手上有什么选）

### A. 让 Agent 自己读仓库（最省事）

把仓库 clone 到考试机上，然后对 Codex / Claude Code / DSH / Cursor 说：

```text
读 AGENTS.md，严格按它执行。题目在 /path/to/problem1，总时长 480 分钟，现在开始。
```

`AGENTS.md` 里已经把门控、产物路径、纪律、降级阶梯、禁止事项全写死了，agent 读完就知道该怎么干。
（Claude Code 认 `CLAUDE.md`，仓库里放了一个指向 `AGENTS.md` 的指针文件，不用额外配置。）

### B. 粘一句 bootstrap 提示词

```bash
bash scripts/bootstrap.sh /path/to/problem 480
# 输出一段已填好绝对路径的话，整段复制给 agent 即可
```

适合 agent 没有「读文件」能力、只有对话框的场景。

### C. 纯命令行（有 API Key，不想用 agent）

```bash
export MARS_BASE_URL="https://api.deepseek.com/v1"
export MARS_API_KEY="sk-..."
export MARS_MODEL="deepseek-chat"

python3 tools/orchestrator-mars.py --task 题目.md --stages g0,g1     # 先验链路
python3 tools/orchestrator-mars.py --task 题目.md --stages all --allow-exec --minutes 480
python3 tools/orchestrator-mars.py --task 题目.md --from g2          # 断点续跑
```

---

## 架构：4 层 + 6 门控

```
                Conductor（唯一决策者，只出 [STATE] 行，不输出长文本）
                          │  两本账：Task Ledger + Progress Ledger + 时间预算
   ┌──────────┬───────────┼───────────┬───────────┬──────────┐
 G0 契约    G1 情报     G2 方案     G3-4 执行    G5 交付
   │          │           │           │           │
 P1 题面   5 侦察兵并行  3 方案       Coder       Evaluator
 P1.5 环境   ↓           ↓            Runner      Writer
          P3 交叉质询   P5 红队打分    Monitor     QA
          （矛盾裁决）  P6 规格书      Fixer×3
   └──────────┴───────────┴───────────┴───────────┘
        角色之间只通过 runs/ 下的文件通信，不共享上下文
```

设计依据（都写进 `docs/01-architecture.md`）：

- **视角化检索 + 交叉质询** — 借自 [STORM](https://arxiv.org/abs/2402.14207)：单一 agent 连问五次会得到同质结果，5 个不同视角才会发散
- **树搜索 + 评审剪枝** — 借自 [AI Scientist-v2](https://export.arxiv.org/abs/2504.08066)：3 个风险偏好不同的方案 + 红队加权剪枝
- **双层账本 + 停滞检测** — 借自 [Magentic-One](https://ar5iv.labs.arxiv.org/html/2411.04468v1)：`00_task.md` / `40_progress.md`，六态判定
- **orchestrator-worker 工程教训** — 借自 [Anthropic 多智能体研究系统](https://www.anthropic.com/engineering/multi-agent-research-system)：子任务描述质量决定成败、必须评估轨迹、token 成本要控

---

## 目录

```
zhang2026/
├── README.md                  ← 你在这里
├── AGENTS.md                  ← ★ 给 agent 的入口契约（门控/纪律/降级）
├── CLAUDE.md                  → 指向 AGENTS.md
├── PROMPTS.md                 ← 26 条提示词合并版（Ctrl+F 搜 "## P7"）
├── docs/
│   ├── 00-playbook.md         8 小时时间盒 · 题面六段式解剖 · 救场 · 答辩话术
│   ├── 01-architecture.md     为什么这么设计（被问到时读这个）
│   ├── 02-materials.md        ★ 材料盘点：风格假设来自多少份材料，哪条是单样本推断
│   └── 05-cheatsheet.md       一页纸，打印出来
├── prompts/                   A 宪法 / B 情报 / C 方案 / D 执行 / E 交付 / F 元提示词
├── examples/                  ★ 5 个虚构题型模板（风格参照，不是真题）
├── tools/
│   ├── orchestrator-mars.py   零依赖编排器（10 阶段/检索循环/断点续跑/降级）
│   ├── netsearch.py           零依赖检索（SearXNG / DuckDuckGo，无 key）
│   ├── selftest.py            离线自检 29 项（mock 端点，不联网不花钱）
│   ├── train_template.py      契约合规训练骨架（smoke/train/eval/predict）
│   ├── monitor.py             日志监控，六态判定 + ETA
│   ├── qa_check.py            交付物机械验收
│   ├── run.sh                 启动/观察/停止（tmux 优先）
│   ├── README-TEMPLATE.md     六段式 README 模板
│   └── config.example.json
└── scripts/
    ├── bootstrap.sh           建 runs/ 并生成"该对 agent 说的话"
    └── push.sh                一键推到自己的 GitHub
```

---

## 提示词一览（26 条）

| 编号 | 名称 | 一句话 |
|---|---|---|
| P0 | 总控宪法 | 会话第一条，定义身份、门控、预算、降级 |
| P1 | 任务契约 | 只读不写，产出 `00_task.md`（含 JSON） |
| P1.2 | 题面解剖 | **真题六段式**结构 → 逐段映射到产物 |
| P1.5 | 依赖自检 | 产出"可用包白名单"，防止写到一半发现没装 |
| P2 | 侦察兵 ×5 | TASK/DATA/METHOD/METRIC/RISK 五视角并行 |
| P2.5 | 搜索算子 | 不依赖 agent 也能查的 query 模板 |
| P3 | 交叉质询 | 强制列矛盾 → 裁决 → Top8 事实 |
| P4 | 三方案 | SAFE / SOTA / GREEDY，各带回滚点 |
| P5 | 红队裁决 | 加权矩阵 + 写死切换条件 |
| P6 | 实验规格书 | `30_spec.json`，5 条自检 |
| P7 | 代码契约 | smoke 模式 + 结构化日志 + 单变量 |
| P7.5 | 泄漏审计 | 八项红线自查（ZGCA 量规的红线项） |
| P8 | 运行监控 | 六态判定 + ETA + 只拉 tail |
| P9 | 修错 | 一次一个假设，配额 3 次，只给 diff |
| P10 | 提分冲刺 | 误差分析 → ROI 排序 → 只做第一名 |
| P11 | 评测固化 | 两次复现一致才算数 |
| P12 | 交付物 | 逐字对齐题面 + README 六段 |
| P13 | QA 闸门 | 20 项工程检查，任一红即返工 |
| P13.5 | 量规自评 | 六维 100 分自评 + 三条完整性红线 |
| P14 | 时间盒 | 剩余时间决策树 |
| P15 | 报告/答辩 | 反幻觉三规则 + RAG 双层评测 |
| P16 | 多题调度 | 一场考 4 道题时的排序与放弃清单 |
| F1–F4 | 元提示词 | 一键总启动 / 原生 fan-out / 判分官 / 人工兜底 |

---

## 实测状态

- `selftest.py`：**29 项全通过** —— 10 阶段门控、工具循环真的发起检索、指标从日志确定性抽取（0.8123）、幂等续跑零调用、端点挂掉降级、max_calls 预算保护。CI 在 3 个 Python 版本上重跑。
- `train_template.py`：四模式实测通过，异常落盘 + exit 1 已验证。
- `monitor.py`：RUNNING/STALL/DIVERGE/OOM/DEAD/DONE 六态逐个造日志验证。
- `qa_check.py`：好提交 PASS、坏提交 FAIL 并给修复清单，两路径验证。
- `run.sh`：nohup 启动 → 自检 → status → stop 全链路验证。

**没验证的**：真实模型端点输出质量、真实 GPU、考场内网。这三样只有到现场才能验，所以每一段都配了降级阶梯。

---

## License

MIT。随意改、随意分发。
