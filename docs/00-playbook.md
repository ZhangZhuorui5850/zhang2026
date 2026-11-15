# 00 · 考场作战手册（8 小时版）

> 这是**操作手册**。原理在 `01`，提示词在 `02`，可直接跑的工具在 `03`/`04`。
> 本文回答一个问题：**从坐下到交卷，每一分钟该干什么、粘哪段提示词。**

---

## 0. 开场 60 秒：先决定走哪条路

坐下先判断你手上有什么，再决定用哪种跑法（四条路的工件格式完全相同，中途可换）：

| 你手上的条件 | 走哪条 | 第一步动作 |
|---|---|---|
| 有 CLI Agent（Codex / DSH / Claude Code）+ 能调模型 | **A 全自动** | 粘 `F1 一键总启动` + 题面路径 |
| 只有 API Key，能跑 Python | **B 半自动** | `export MARS_API_KEY=...` → 跑 `tools/orchestrator-mars.py` |
| 只有网页对话框 | **C 单会话角色扮演** | 粘 `P0 宪法`，之后每换角色先写 `[ROLE] xxx` |
| 什么都没有 / 模型连不上 | **D 人工** | 打印 `05-一页纸速查卡`，照做 |

**不要在这里犹豫超过 2 分钟。** D 路线也能拿到及格以上的分，卡在选择上才是真的亏。

---

## 1. 考前就绪清单（前一晚 / 入场 10 分钟）

### 本地（你的 Mac，考前做完）

- [ ] `实训准备/科研实训-多智能体/` 整个目录拷到 U 盘或网盘，能离线打开
- [ ] 打印 `05-一页纸速查卡`（**必须纸质**，防止屏幕被占满）
- [ ] `PROMPTS.md` 在编辑器里打开，学会 `Ctrl+F` 搜 `## P7` 这种用法
- [ ] 把 `tools/` 里的 5 个文件拷进一个 `kit/` 目录，随时 `scp` 上去
- [ ] 演练一次：用 `train_template.py --mode smoke` 跑通（30 秒）
- [ ] 记住三个环境变量名：`MARS_BASE_URL` / `MARS_API_KEY` / `MARS_MODEL`

### 考试机（入场 10 分钟，一条条来）

```bash
# 1) 摸环境
whoami; hostname; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
python3 -V; nproc; df -h ~ | tail -1

# 2) 建工作台（所有产物都在这）
mkdir -p ~/work/runs/{10_cards,50_logs,70_ckpt,90_submission} && cd ~/work

# 3) 开 tmux（断线不丢进度，这一步别省）
tmux new -s work

# 4) 探题面与数据
ls -la /vepfs-readonly/ 2>/dev/null; ls -la /vepfs/ 2>/dev/null
find /vepfs-readonly -maxdepth 2 | head -30

# 5) 网络三连（决定走 D0 还是 D1）
curl -m 6 -sI https://pypi.org/simple/ | head -1
curl -m 6 -sI https://huggingface.co | head -1
curl -m 6 -sI https://registry.npmmirror.com | head -1
```

> 路径以本届实际为准。`/vepfs-readonly`（只读素材）与 `/vepfs`（个人工作+提交）是**往届**惯例，进场先 `ls` 确认，别照抄。

---

## 1.5 题面解剖：真题是六段式（30 秒定位法）

这一届（秋季营/冬令营）的实训题面基本是同一套模板。**认结构比读内容更快**：

| # | 段落标题 | 里面一定有 | 立刻要做的动作 | 产物 |
|---|---|---|---|---|
| 1 | 题目 | 一句话任务名 | 记下关键词，用于 G1 检索 | `objective` |
| 2 | 题目背景与目标 | 领域意义 + 输入形式 + 输出形式 + **指标** | 抄下指标名与方向（越大越好？） | `metric` |
| 3 | 数据集加载 | 现成的 Dataset 类名、`training/valid/test` 划分、只读路径 | **先跑通这个类**，比读题更重要 | `inputs`、`01_env.md` |
| 4 | 模型与特征提取 | checkpoint 路径、加载函数、tokenizer、表征形状、建议 pooling | 确认 ckpt 真实存在 + 能 load | `20_candidates.md` 改动清单 |
| 5 | 设置要求（编号） | 禁止项 / 二选一 / "需在报告中说明" | 逐条抄进 `constraints.forbidden` | `30_spec.json` |
| 6 | 提交内容 + 评分 | **逐字文件名**、字段、条数、顺序、提交目录、同分规则 | 原样抄，一个字符都不改 | `outputs`、P13 清单 |

### 三类"看着像废话、其实是硬约束"的句子

| 句式 | 真实含义 | 不做的后果 |
|---|---|---|
| "需在报告中说明并固定" | 这是评分项。必须写明选了哪个、为什么，且**代码与 README 一致** | 方法分直接扣，答不上来 |
| "二选一" | 必须在交付物里显式声明选择 | 评审无法判定你用的是什么，按未做处理 |
| "禁止 / 不得 / 不允许" | 硬性红线 | 一旦触发，接近 0 分 |

### 题型识别 → 直接跳到现成做法

看到这些特征，对应 `examples/` 里的模板，直接套它的参数区间与坑清单：

| 题面里有 | 题型 | 模板 | SAFE 方案（先做这个） |
|---|---|---|---|
| checkpoint 路径 + tokenizer + "禁止改动词表" | 微调 | `examples/task-01-finetune.md` | 冻结主干 + 轻量头 + 1 epoch |
| 文档库 + "答案必须基于文档" + 引用 | RAG | `examples/task-02-rag.md` | 字面/BM25 检索 + 抽取式回答 |
| csv/parquet + 特征说明 + 交叉验证要求 | 表格 | `examples/task-03-tabular.md` | LightGBM 默认参数 + 5 折 CV |
| **不给**预训练权重 + 要求消融 | 从零训练 | `examples/task-04-scratch.md` | 统计基线（3σ / IQR / PCA 重构） |

> 模板全是虚构的占位符示例，只用来看**结构**和**坑**，不许套用里面的任何数字、路径、指标。

### 一段压缩版"风格样例"（虚构，仅示意密度）

> **题目：某序列性质预测**
> **背景与目标**：给定已训练好的 X 模型 checkpoint，构建 Y 性质预测的完整微调流程。输入为序列，输出为标签（二分类）。
> **数据集加载**：提供 `DS.load(lmdb_path)` 返回 train/valid/test，每样本含 `seq` 与 `label`。
> **模型与特征提取**：从 `/path/ckpt` 加载，用自带 alphabet 的 `batch_converter`；表征形状 `[B, L, H]`。
> **设置要求**：① 沿用原 tokenizer，禁止改词表；② pooling 二选一并说明；③ 固定 seed。
> **提交内容**：`test_result.json`、`README.md`、代码、`train.log` 至 `/path/mine`。
> **评分**：Accuracy。

**看这份样例时，脑子里应该同时亮起这几个灯**：ckpt 在不在 → Dataset 类能不能 load → pooling 选了哪个有没有写进 README → json 条数等于测试集 → 提交目录对不对。

## 2. 八小时时间盒（核心表）

以 480 分钟计。每段时间盒结束必须做**判据检查**，不过就下沉降级，不许硬撑。

| 时段 | 分钟 | 干什么 | 粘哪条 | 产出 | 判据（不过就降级） |
|---|---|---|---|---|---|
| ① 开局 | 0–15 | 环境清点、建工作台、tmux | — | `~/work/runs/` | `nvidia-smi` 有输出 |
| ② 反推评分 | 15–25 | 让 Agent 站在判分侧拆权重 | `F3 判分官` | `runs/05_rubric.md` | 能说出前 3 个得分项 |
| ③ 任务契约 | 25–45 | 读题、六段解剖、抄提交清单、抽 JSON | `P1` + `P1.2` + `P1.5` | `00_task.md` `01_env.md` | outputs 逐字抄完、依赖白名单有内容 |
| ④ 情报 | 45–100 | 5 视角并行检索 + 矛盾裁决 | `P2`×5 → `P3` | `10_cards/*` `10_brief.md` | ≥3 张卡，brief 里有"不知道什么" |
| ⑤ 三方案 | 100–120 | SAFE / SOTA / GREEDY | `P4` | `20_candidates.md` | 三个方案都有回滚点 |
| ⑥ 裁决 | 120–135 | 红队打分 + 定主线与切换条件 | `P5` | `25_decision.md` | 末行有 `DECISION:` |
| ⑦ 规格 | 135–150 | 写死启动命令、时间盒、兜底 | `P6` | `30_spec.json` | 5 条自检全过 |
| ⑧ 编码 | 150–195 | 写代码 + smoke 通过 | `P7` + 骨架 | 代码 + `smoke.log` | `--mode smoke` 退出码 0 |
| ⑨ 主训 | 195–330 | 启动、盯、修 | `P8` `P9` | `main.log` `40_progress.md` | 有 `[STEP]` 且 verdict≠DEAD |
| ⑩ 提分 | 330–400 | 误差分析 → 只做 ROI 第一 | `P10` | `45_boost.md` | Δ>0 才保留 |
| ⑪ 评测 | 400–415 | 固化指标、两次复现 | `P11` | `60_metrics.json` | 两次结果一致 |
| ⑫ 交付 | 415–445 | 生成题面要求的全部文件 | `P12` | `90_submission/` | json 能 load、条数对 |
| ⑬ 验收 | 445–465 | 机械检查 + 人工抽查 | `P13` + `qa_check.py` | `95_qa.md` | `QA_RESULT: PASS` |
| ⑭ 冻结 | 465–480 | 只读。打包备份 | `P14` | `submission_backup.tgz` | 不许再改代码 |

**三个硬节点（背下来）**

- **T+195（约 3.25h）**：smoke 还没过 → 立刻砍模型、砍数据、砍改动，用最笨方法先出分。
- **T+384（80%）**：无论指标多少，先跑一遍 `P12` 产出一个可提交版本。**先有，再好**。
- **T+456（95%）**：冻结。此后只准 `ls`/`cat`/`python -c "json.load"`，不准 `vim`。

---

## 3. 四类题型的落地映射

同一套流水线，换的是第 ⑧⑨ 步的具体做法。以下是这一届最可能出现的四类：

### A. 微调预训练模型（如蛋白质溶解度、文本分类）

```bash
# 关键：先用 1% 数据跑通全链路，再放大
python3 train.py --mode smoke --config config.json      # 60 秒
python3 train.py --mode train  --config config.json      # 先 epochs=1 看曲线
```
- 显存：A100 80G 下 `batch=16 + max_len=512 + bf16` 是小模型微调的稳妥起点；OOM 就减 batch，别改结构
- 必做：`freeze backbone 前 N 层` 跑一轮（快、稳、常意外好用）
- 提分顺序：**阈值/早停选点 → 长度分桶分析 → 类别权重 → 多 seed 平均**

### B. 表格 / 传统 ML（特征工程类）

- 先 `LightGBM/XGBoost + 默认参数` 出分（5 分钟），它就是你的 SAFE
- 提分顺序：**交叉验证重划分 → 类别特征编码 → 缺失值标记位 → 目标编码 → 模型融合**
- 别一上来上深度学习，样本几千条时树模型几乎总是赢

### C. RAG / 问答 / 检索

- 分两层评测：检索层（hit@k、MRR）+ 生成层（答案正确率、引用命中率），**分别报**
- 提分顺序：**切块策略（256/512 + 重叠 64）→ top-k 与重排 → query 改写 → 提示词约束"只依据原文"**
- 兜底：检索无命中必须回"未找到"，别硬编

### D. 从零训练 / 复现论文

- 先跑通一个"能出数"的最小网络（哪怕指标很差），再逐步加结构
- 优先保 `可复现`：seed、确定性、两次评测一致
- 消融表就是你的主要得分点，别只交一个最终数字

---

## 4. 考场硬约束的应对（来自你自己的调研报告）

| 约束 | 症状 | 应对 |
|---|---|---|
| 无 sudo | `apt/pip install -g` 报 Permission denied | 全部装到 `~/.local`：`PYTHONUSERBASE=~/.local pip install --user`；`npm config set prefix ~/.local` |
| 无外网 | `pip install` 转圈、`git clone` 超时 | 先 `curl` 测三连；不通就用 `-i https://pypi.tuna.tsinghua.edu.cn/simple` 或 `registry.npmmirror.com`；仍不通 → D1：只用已有包（`01_env.md` 白名单） |
| 断线 | SSH 掉，训练白跑 | `tmux new -s work`；已有任务用 `nohup ... &` + `echo $! > pid`；重连后 `bash run.sh status` |
| 显存不足 | `CUDA out of memory` | 降 batch 一半 → 降 `max_len` → 开 `bf16` → 梯度累积代替大 batch |
| 数据只读 | 往 `/vepfs-readonly` 写失败 | 只读区永远只读；所有输出写 `~/work` 或 `/vepfs/<你的目录>` |
| 提交路径严格 | 交上去找不到文件 | `P1` 就把路径逐字抄进 `00_task.md`；`P13` 再用脚本核一次 |
| 模型端点不稳 | 调用 429 / 超时 | 编排器已内置 3 次退避重试；持续失败就走 C/D 路线，别耗在重试上 |

---

## 5. 五个"必死场景"与 30 秒救场

| 场景 | 30 秒动作 |
|---|---|
| 题面看不懂 / 交付物不清 | 别问人，先 `find` 目录里的 `README`/`*.md`/`eval*.py`；用 `P1` 让 Agent 把"未知"列出来，挑代价最低的一个先验证 |
| 数据读不出来 | `file`、`head -c 200`、`python -c "import lmdb..."`；10 分钟内读不出 → 用合成小数据先把管线跑通，同时写 `BLOCKED.md` 说明 |
| 代码跑一次炸一次 | 进 `P9`：一次一个假设、只给 diff、配额 3 次；用完就切 SAFE |
| 训练 40 分钟没动静 | `bash run.sh status`；`[STEP]` 没有 → 大概率 dataloader，`num_workers=0` 复测 |
| 只剩 40 分钟还没交付物 | 直接 `P12` + `qa_check.py`，用现有 best 出分。**交一个 0.6 的完整包，胜过交一个 0.85 的半成品** |

---

## 6. 提示词粘贴时间线（一张图）

```
坐下
 ├─ F3 判分官 ────────────────→ 决定时间怎么分
 ├─ P1 任务契约 + P1.2 解剖 + P1.5 依赖 → 00_task.md / 01_env.md
 ├─ P2 ×5 并行侦察兵 ────────→ 10_cards/
 ├─ P3 交叉质询 ─────────────→ 10_brief.md
 ├─ P4 三方案 ───────────────→ 20_candidates.md
 ├─ P5 红队裁决 ─────────────→ 25_decision.md（有 DECISION 行）
 ├─ P6 规格书 ───────────────→ 30_spec.json
 ├─ P7 Coder（配 04 骨架）───→ 代码 + SMOKE_OK
 ├─ P8 启动与监控 ───────────→ main.log / 40_progress.md
 │    └─ 出错 → P9（配额 3）
 ├─ P10 提分冲刺 ────────────→ 45_boost.md
 ├─ P11 评测固化 ────────────→ 60_metrics.json
 ├─ P12 交付物 ──────────────→ 90_submission/
 ├─ P13 验收 + qa_check.py ──→ QA_RESULT: PASS
 └─ P14 时间盒收尾 ──────────→ 冻结 + 打包
```

**只想记三条**：`F3` 开场算账 → `P1–P6` 想清楚 → `P7–P13` 做出来并交出去。

---

## 7. 答辩 / 巡场被问到时（90 秒脚本）

> **"你的方法是什么？"**
> 我先用最笨的合法方法把管线跑通拿到基线（XXX，用时 40 分钟），之后每次只改一个变量。最终提交是基线 + 两处改动：A（因为误差分析显示短序列样本错误率是长序列的 2.3 倍）和 B（阈值从 0.5 调到 0.42，因为验证集正类先验是 0.43）。指标从 X 提到 Y，改动记录在 `45_boost.md` 里。

> **"你怎么保证不是碰巧？"**
> 固定 seed，同一个 checkpoint 评测两次结果完全一致，日志在 `61_eval.log`。另外我留了消融表，每一项的 before/after 都在。

> **"时间不够时你放弃了什么？"**
> 放弃了集成和多 seed 平均，因为单次训练 35 分钟，两次来不及；README 第 6 段写了如果多 1 小时会先做哪个。

> **"这套流程是你自己想的？"**
> 参考了多智能体科研自动化的常见做法（视角化检索、评审剪枝、双层账本），把它压成了能在 8 小时内跑完的版本：情报并行、方案三选一、执行单变量、交付前机械验收。

---

## 8. 今晚就要做的四件事（别拖到考场）

1. **跑一次空转演练**：在本地建个假题面，跑
   `python3 tools/orchestrator-mars.py --task 假题目.md --dry-run`
   确认 9 个阶段、23 条提示词都装上了。
2. **跑一次骨架演练**：`cd tools && python3 train_template.py --mode smoke`，看到 `SMOKE_OK`。
3. **跑一次 bootstrap 演练**：`bash scripts/bootstrap.sh ~/Desktop 480`，把打印出来的那段话复制给 agent 试一遍（用 examples/ 里的虚构题面即可）。
4. **背下三个时间节点**：T+195 出 baseline、T+384 有可提交版、T+456 冻结。
