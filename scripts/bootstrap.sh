#!/usr/bin/env bash
# bootstrap.sh · 一条命令把"该对 agent 说的话"生成好
# 用法： bash scripts/bootstrap.sh <题目路径> [总分钟数] [--api 模式]
set -eu

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASK_DIR="${1:-}"
MINUTES="${2:-480}"

if [ -z "$TASK_DIR" ]; then
  echo "用法: bash scripts/bootstrap.sh <题目路径> [总分钟数]"
  exit 2
fi

# 绝对路径化（macOS / Linux 都能用）
if command -v realpath >/dev/null 2>&1; then
  TASK_ABS="$(realpath "$TASK_DIR" 2>/dev/null || echo "$TASK_DIR")"
else
  TASK_ABS="$(cd "$TASK_DIR" 2>/dev/null && pwd || echo "$TASK_DIR")"
fi

if [ ! -e "$TASK_ABS" ]; then
  echo "× 路径不存在: $TASK_ABS"
  echo "  提示：先 ls 一下确认真实挂载点（例如 /vepfs-readonly、/vepfs、~/work）"
  exit 2
fi

cd "$REPO"
mkdir -p runs/{10_cards,20_plan,50_logs,70_ckpt,90_submission}

echo "=============================================================="
echo " 工作台已建好： $REPO/runs"
echo " 题目路径     ： $TASK_ABS"
echo " 总时长       ： ${MINUTES} 分钟"
echo "=============================================================="
echo
echo "【这里的东西先自己看一眼】"
find "$TASK_ABS" -maxdepth 2 -type f 2>/dev/null | head -20 || true
echo
echo "=============================================================="
echo " 把下面整段复制给 agent（Codex / Claude Code / DSH / Cursor 都行）"
echo "=============================================================="
cat <<PROMPT
你在这台机器上执行科研实训任务。工作仓库在 ${REPO}，题目在 ${TASK_ABS}，总时长 ${MINUTES} 分钟，现在开始计时。

第一步（不要跳过）：完整读 ${REPO}/AGENTS.md，它是你的执行契约；再读 ${REPO}/docs/00-playbook.md 的时间盒与题型映射；提示词按编号去 ${REPO}/prompts/ 取（合并版 ${REPO}/PROMPTS.md）。

然后严格按门控推进，产物全部落在 ${REPO}/runs/：
G0 用 P1 产出 00_task.md（题面 outputs 必须逐字抄）→ P1.5 产出 01_env.md（依赖白名单）
G1 用 P2 开 5 个视角并行侦察（TASK/DATA/METHOD/METRIC/RISK）→ P3 产出 10_brief.md
G2 用 P4 出三方案 → P5 红队裁决（末行必须有 DECISION:）→ P6 出 30_spec.json
G3 用 P7 写代码（配 ${REPO}/tools/train_template.py 骨架），--mode smoke 退出码 0 才算过
G4 用 P8 启动并监控 → 出错走 P9（配额 3）→ 有余量走 P10
G5 用 P11 固化指标 → P12 出交付物 → P13 验收（必须 QA_RESULT: PASS）

纪律：一次只改一个变量；没有 smoke 通过不许开训练；到 ${MINUTES} 分钟的 80% 时先产出一版可提交内容。
自主决定超参、结构、后处理、放弃某方案，不要问我；只在「会导致判 0 分的题面歧义 / 需要网络或权限 / 数据完全不可读」这三种情况下停下来。

每完成一个门控只回一行：[GATE Gx] ok <关键数字> artifact=<路径>
现在开始：先做 G0。
PROMPT
echo
echo "--------------------------------------------------------------"
echo " 想让它无人值守跑完（有 API Key 时）："
echo "   export MARS_BASE_URL=https://api.deepseek.com/v1 MARS_API_KEY=sk-... MARS_MODEL=deepseek-chat"
echo "   python3 ${REPO}/tools/orchestrator-mars.py --task <题目文件> --stages all --allow-exec --minutes ${MINUTES}"
echo "--------------------------------------------------------------"
