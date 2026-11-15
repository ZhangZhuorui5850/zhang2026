#!/usr/bin/env bash
# push.sh · 一键把本仓库推成公开的 zhang2026
#
# 用法：
#   GITHUB_TOKEN=ghp_xxx bash scripts/push.sh
#   bash scripts/push.sh --token ghp_xxx --user 你的用户名
#   bash scripts/push.sh --dry            # 只看会做什么，不联网
#
# Token 权限只需要 classic 的 `repo`（或 fine-grained 的 Administration: Read and write + Contents: Read and write）。
# 注意：脚本推完会把 remote 里的 token 抹掉，避免凭据留在 .git/config。
set -eu

REPO_NAME="zhang2026"
BRANCH="main"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
USER=""
DRY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --token) TOKEN="${2:-}"; shift 2 ;;
    --user)  USER="${2:-}";  shift 2 ;;
    --dry)   DRY=1; shift ;;
    *) echo "未知参数: $1"; exit 2 ;;
  esac
done

echo "=============================================================="
echo " 仓库目录 : $REPO_DIR"
echo " 目标仓库 : github.com/<user>/$REPO_NAME （public）"
echo "=============================================================="

# ---------- 1. 本地 git 初始化 ----------
cd "$REPO_DIR"
if [ ! -d .git ]; then
  git init -q
  git checkout -q -b "$BRANCH" 2>/dev/null || git branch -q -M "$BRANCH"
  echo "√ git init"
else
  echo "√ 已是 git 仓库"
fi

git add -A
if git diff --cached --quiet; then
  echo "√ 无新增改动"
else
  git -c user.name="${GIT_AUTHOR_NAME:-zhang2026}" \
      -c user.email="${GIT_AUTHOR_EMAIL:-zhang2026@users.noreply.github.com}" \
      commit -q -m "feat: MARS-8H 科研实训多智能体套件（提示词 + 编排器 + 交付验收）"
  echo "√ 已提交"
fi

# ---------- 2. 没有 token：给出手动步骤 ----------
if [ -z "$TOKEN" ]; then
  cat <<MANUAL

--------------------------------------------------------------
 没有检测到 GitHub Token，所以没有推送。两种方式任选：
--------------------------------------------------------------
【方式 A · 网页建仓 + 命令行推】（最简单，2 分钟）

 1. 打开 https://github.com/new
    Repository name 填：$REPO_NAME
    选 Public，不要勾 Add a README（否则会冲突），点 Create repository

 2. 回到终端执行（把 <你的用户名> 换掉）：
      cd $REPO_DIR
      git remote add origin https://github.com/<你的用户名>/$REPO_NAME.git
      git push -u origin $BRANCH

    第一次 push 会要求登录，密码处填 Personal Access Token：
    https://github.com/settings/tokens → Generate new token (classic) → 勾 repo

【方式 B · 直接给脚本一个 token】

  GITHUB_TOKEN=ghp_xxxxxxxx bash scripts/push.sh

  脚本会自动建仓、推送、并把 token 从 remote 里抹掉。
--------------------------------------------------------------
MANUAL
  exit 0
fi

API="https://api.github.com"
AUTH=(-H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28")

if [ "$DRY" = "1" ]; then
  echo "[dry] 会执行：GET $API/user ；POST $API/user/repos {\"name\":\"$REPO_NAME\",\"private\":false}"
  echo "[dry] 然后 git push -u origin $BRANCH"
  exit 0
fi

# ---------- 3. 确定用户名 ----------
if [ -z "$USER" ]; then
  USER="$(curl -sS "${AUTH[@]}" "$API/user" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("login",""))')"
fi
if [ -z "$USER" ]; then
  echo "× 拿不到 GitHub 用户名，token 可能无效或权限不足"
  exit 1
fi
echo "√ 认证用户: $USER"

# ---------- 4. 建仓（已存在则跳过） ----------
CODE="$(curl -sS -o /tmp/gh_create.json -w '%{http_code}' -X POST "${AUTH[@]}" \
  "$API/user/repos" \
  -d "{\"name\":\"$REPO_NAME\",\"private\":false,\"description\":\"科研实训多智能体套件（MARS-8H）：18 条提示词 + 零依赖编排器 + 交付验收\",\"has_issues\":true,\"has_wiki\":false}")"

case "$CODE" in
  201) echo "√ 已创建公开仓库 $USER/$REPO_NAME" ;;
  422) echo "√ 仓库已存在，直接推送" ;;
  401) echo "× 401 未授权：token 无效或已过期"; exit 1 ;;
  *)   echo "× 建仓失败 HTTP $CODE"; head -c 400 /tmp/gh_create.json; echo; exit 1 ;;
esac

# ---------- 5. 推送 ----------
CLEAN_URL="https://github.com/${USER}/${REPO_NAME}.git"
AUTH_URL="https://x-access-token:${TOKEN}@github.com/${USER}/${REPO_NAME}.git"

# 无论成功失败，退出时都把 token 从 .git/config 里抹掉
scrub() { git remote set-url origin "$CLEAN_URL" 2>/dev/null || git remote remove origin 2>/dev/null || true; }
trap scrub EXIT INT TERM

git remote remove origin 2>/dev/null || true
git remote add origin "$AUTH_URL"

# credential.helper= 用来屏蔽 macOS 钥匙串助手；它在本机报 -60006，
# 会让 git 在推送成功之后仍然返回非零，看起来像失败。
push_once() {
  GIT_TERMINAL_PROMPT=0 git -c credential.helper= push -u origin "$BRANCH"
}

if ! push_once 2>&1 | tee /tmp/zhang2026_push.log | grep -vE "failed to store"; then
  echo "… 第一次推送未成功，10 秒后重试一次"
  sleep 10
  push_once || { echo "× 推送失败，原始输出："; cat /tmp/zhang2026_push.log; exit 1; }
fi

# 校验远端真的前进了
LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git ls-remote "$CLEAN_URL" "refs/heads/$BRANCH" | cut -f1)"
echo "   local  $LOCAL_SHA"
echo "   remote $REMOTE_SHA"
if [ "$LOCAL_SHA" != "$REMOTE_SHA" ]; then
  echo "× 远端与本地不一致，推送未生效"
  exit 1
fi

echo "√ 已推送（远端已确认）"
echo
echo "=============================================================="
echo " 公开地址： https://github.com/$USER/$REPO_NAME"
echo " Clone   ： git clone https://github.com/$USER/$REPO_NAME.git"
echo "=============================================================="
echo " 在任何机器上："
echo "   git clone https://github.com/$USER/$REPO_NAME.git && cd $REPO_NAME"
echo "   bash scripts/bootstrap.sh <题目路径> 480"
echo "=============================================================="
