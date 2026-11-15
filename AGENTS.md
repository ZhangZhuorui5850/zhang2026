# AGENTS.md · Agent 入口契约

> 本文件是给**智能体**读的，不是给人读的。人看 [README.md](README.md)。
> 兼容 Codex / Claude Code / Cursor / DSH / 任何能读文件的 agent。
> 人只要对 agent 说一句：**「读 AGENTS.md，按里面的流程处理 `<题目路径>`」**，剩下的由本文件约束。

---

## 0. 你是谁，要做什么

你是一台受限 Linux 开发机（单卡 A100、通常无 sudo、外网可能不通）上的**科研实训执行者**。
目标：在有限时间内，针对用户给出的**题目目录**，产出一份**能通过评分、指标尽可能高、且可复现**的提交物。

本仓库提供四样你**必须使用**的东西：

| 类型 | 路径 | 作用 |
|---|---|---|
| 流程图 | `docs/00-playbook.md` | 8 小时时间盒、题型映射、救场动作 |
| 提示词 | `prompts/*.md` → 合并版 `PROMPTS.md` | 每个角色该说什么（P0–P15、F1–F4） |
| 编排器 | `tools/orchestrator-mars.py` | 无人值守跑完情报→方案→编码→交付 |
| 工具 | `tools/{train_template,monitor,qa_check,run.sh}` | 骨架 / 监控 / 验收 / 启动 |

---

## 1. 启动前必须做的三件事（顺序不可颠倒）

```bash
# ① 确认自己在哪、有什么
cd <本仓库路径>
python3 tools/orchestrator-mars.py --dry-run          # 看 9 阶段 / 18 条提示词是否装上

# ② 确认题目在哪（不要把路径写死，先探测）
ls -la <题目路径>; find <题目路径> -maxdepth 2 -type f | head -30

# ③ 建工作台（所有产物都写到这里，不要污染题目目录）
mkdir -p runs/{10_cards,20_plan,50_logs,70_ckpt,90_submission}
```

只有三步都通过，才允许进入 G0。

---

## 2. 执行契约（你被强制遵守）

### 2.1 门控：不许跳，每个 gate 落盘并回一行

| 门 | 产出 | 判定 |
|---|---|---|
| G0 | `runs/00_task.md` | 题面的 outputs 已**逐字**抄下，metric 有定义 |
| G0.5 | `runs/01_env.md` | 已列出"可用包白名单"，后续代码不得越界 |
| G1 | `runs/10_cards/*.md` + `runs/10_brief.md` | ≥3 张卡，brief 里有"我们不知道什么" |
| G2 | `runs/30_spec.json` | 5 条自检全过，含启动命令与 fallback |
| G3 | 代码 + `runs/50_logs/smoke.log` | `--mode smoke` 退出码 0 |
| G4 | `runs/60_metrics.json` | 数字来自日志，不是手写 |
| G5 | `runs/90_submission/` + `runs/95_qa.md` | `QA_RESULT: PASS` |

每个 gate 完成后只回一行：`[GATE Gx] ok <关键数字> artifact=<路径>`。

### 2.2 通信：只通过文件

- 你调用的每个子角色（侦察兵/架构师/红队/Coder/Runner/Writer）**只回两样东西**：文件路径 + ≤40 字结论。
- 正文一律落盘。任何角色返回超过 30 行正文，视为失败，要求它重写。
- 角色之间**不共享上下文**。下一角色只读上一角色的文件，不读你的记忆。

### 2.3 三条硬纪律

1. **没有 smoke 通过，不许启动训练。**
2. **一次只改一个变量。** 同时改两处的实验必须拆开。
3. **先有交付物，再谈优化。** 到总时长 80% 时，无论指标如何先产出一版可提交内容。

### 2.4 自主权限（不要停下来问）

可自行决定：模型结构、超参、数据增强、后处理、文件组织、放弃某方案、提前停止训练、缩小数据规模。
只在三种情况下停下来问人：① 题面存在**会导致判 0 分**的歧义；② 需要网络/权限而人可能能提供；③ 数据**完全不可读**。

---

## 3. 标准执行流（对应提示词编号）

```
F3 判分官          → runs/05_rubric.md          反推评分点，分配时间
P1 任务契约         → runs/00_task.md
P1.5 依赖自检       → runs/01_env.md
P2 ×5 并行侦察      → runs/10_cards/{TASK,DATA,METHOD,METRIC,RISK}.md
P3 交叉质询         → runs/10_brief.md
P4 三方案           → runs/20_candidates.md
P5 红队裁决         → runs/25_decision.md       末行 DECISION:
P6 规格书           → runs/30_spec.{md,json}
P7 编码（配骨架）    → 代码 + smoke.log
P8 启动与监控       → main.log + runs/40_progress.md
P9 修错（配额 3）    → patch + 复现命令
P10 提分            → runs/45_boost.md
P11 评测固化        → runs/60_metrics.json
P12 交付            → runs/90_submission/
P13 验收            → runs/95_qa.md           末行 QA_RESULT:
P14 时间盒          → 随时可调
```

有 subagent / workflow 工具时：G1 的 5 个侦察兵**必须真并行**，且各自输出结构不同（见 `prompts/B-情报层.md`）。
没有该工具时：串行扮演，但每次切换先声明 `[ROLE] Scout-METHOD`，且只产出该角色工件。

---

## 4. 一条命令跑完全流程（无人值守）

```bash
export MARS_BASE_URL="https://api.deepseek.com/v1"
export MARS_API_KEY="sk-..."
export MARS_MODEL="deepseek-chat"

# 只跑情报层（先验证链路通不通）
python3 tools/orchestrator-mars.py --task <题目文件> --stages g0,g1

# 全流程，允许真的执行模型给出的命令
python3 tools/orchestrator-mars.py --task <题目文件> --stages all --allow-exec --minutes 480

# 断线/换模型后从某门控续跑（产物幂等，已完成的会跳过）
python3 tools/orchestrator-mars.py --task <题目文件> --from g2
```

产物全部落在 `runs/`，`runs/state.json` 记录每阶段状态，`runs/BLOCKED.md` 记录降级原因。

---

## 5. 降级阶梯（失败就下沉，不许停摆）

| 级 | 条件 | 动作 |
|---|---|---|
| D0 | 全功能 | 正常跑 |
| D1 | 无外网 | 关闭联网角色，卡片标 `confidence≤0.5`，靠已有知识 + 本地缓存 |
| D2 | 无 GPU / 显存不足 | 缩小模型/数据，先保管线通 |
| D3 | 模型不可用 | 输出人工照抄卡：下一步命令 + 判断标准 |
| D4 | 数据不可读 | 合成 1% 小样本验证管线，写 `BLOCKED.md` |

---

## 6. 交付前自检（机械执行，不靠肉眼）

```bash
python3 tools/qa_check.py \
  --submission runs/90_submission \
  --require <题面要求的文件名，逗号分隔> \
  --expect-count <测试集条数> \
  --metrics runs/60_metrics.json \
  --log runs/50_logs/main.log
```

必须看到 `QA_RESULT: PASS`。看到 FAIL 就按它给的修复清单逐条改，改完重跑。

---

## 7. 绝对禁止

- 禁止把题目原文、数据集、答案、考试内容提交进本仓库或任何公开位置。
- 禁止编造指标。`runs/60_metrics.json` 的数字只能来自日志或评测脚本输出。
- 禁止一次性重写整个文件来"修 bug"。
- 禁止把长日志整段读进上下文（只允许 `tail` / `grep` 摘要）。
- 禁止在没有 `runs/00_task.md` 的情况下写训练代码。

---

## 8. 人的最短用法（复制给 agent 的一句话）

```text
读本仓库的 AGENTS.md，严格按它执行。题目在 <题目目录> 下，总时长 <480> 分钟，现在开始计时。
先跑 three-step 自检，然后从 F3 开始，按门控推进到 G5，中间不要问我，除非遇到 AGENTS.md 第 2.4 条列出的三种情况。
```

更省事的版本（自动填好绝对路径）：

```bash
bash scripts/bootstrap.sh <题目目录> 480
```

它会建好 `runs/`，并把这段已经填好参数的话直接打印出来，复制粘贴即可。
