#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MARS-8H · 科研实训多智能体编排器
================================================

零依赖（只用标准库），对接任意 OpenAI 兼容端点（DeepSeek / 中转站 / 本地 vLLM 均可）。
把 02-提示词总库.md 里的 P 系列提示词，串成一条带门控、带预算、带黑板（文件）的流水线。

快速开始
--------
# 1) 只看流水线长什么样，不联网（考前自查用）
python3 03-orchestrator-mars.py --dry-run

# 2) 真跑情报层：5 个侦察兵并行 + 交叉质询
export MARS_BASE_URL="https://api.deepseek.com/v1"
export MARS_API_KEY="sk-..."
export MARS_MODEL="deepseek-chat"
python3 03-orchestrator-mars.py --task 题目.md --stages g0,g1

# 3) 全流程（含写代码 + 跑 smoke，需显式授权执行）
python3 03-orchestrator-mars.py --task 题目.md --stages all --allow-exec --minutes 480

# 4) 从某个门控续跑（断线/换模型后恢复）
python3 03-orchestrator-mars.py --task 题目.md --from g2

设计要点（对应 01-多智能体架构设计.md）
--------------------------------------
* 角色之间只通过 runs/ 下的文件通信，不共享上下文 → 不爆炸、可续跑
* 每个 stage 有产出契约；已存在的产物默认跳过（幂等）
* 全局 deadline：到点即停，未完成阶段写 BLOCKED.md
* 侦察兵用线程池真并行；其余串行，避免互相污染
"""

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

# ----------------------------------------------------------------------------
# 0. 常量与默认值
# ----------------------------------------------------------------------------

DEFAULT_BASE_URL = os.environ.get("MARS_BASE_URL", "http://127.0.0.1:8000/v1")
DEFAULT_API_KEY = os.environ.get("MARS_API_KEY", "")
DEFAULT_MODEL = os.environ.get("MARS_MODEL", "deepseek-chat")
CHEAP_MODEL = os.environ.get("MARS_MODEL_CHEAP", DEFAULT_MODEL)

VIEWS = ["TASK", "DATA", "METHOD", "METRIC", "RISK"]

# stage -> (说明, 需要的 P 编号, 并行度, 产出相对路径)
STAGES = {
    "g0":  ("任务契约：环境清点 + 题面解析 + 输出清单",        "P1",   1, "00_task.md"),
    "g1":  ("情报侦察：5 视角并行检索",                        "P2",   5, "10_cards/"),
    "g1s": ("情报收口：矛盾裁决 + Brief",                      "P3",   1, "10_brief.md"),
    "g2a": ("方案生成：SAFE / SOTA / GREEDY",                  "P4",   1, "20_candidates.md"),
    "g2b": ("红队评审 + 决策矩阵",                             "P5",   1, "25_decision.md"),
    "g2c": ("实验规格书（json + md）",                          "P6",   1, "30_spec.json"),
    "g3":  ("Coder：写代码 + smoke 自检 + 修错",               "P7",   1, "40_code/"),
    "g4":  ("提分冲刺：误差分析 → ROI → 只做第一名",           "P10",  1, "45_boost.md"),
    "g5":  ("交付物 + QA 闸门",                                "P12",  1, "90_submission/"),
}
STAGE_ORDER = ["g0", "g1", "g1s", "g2a", "g2b", "g2c", "g3", "g4", "g5"]

# 每个门控完成后必须出现的标志字符串（用于判定该 stage 是否"真的成了"）
GATE_MARK = {
    "g0": "outputs",
    "g1": "### 硬结论",
    "g1s": "## 一句话结论",
    "g2a": "## SAFE",
    "g2b": "DECISION:",
    "g2c": "\"mission_id\"",
    "g3": "SMOKE_OK",
    "g4": "| 改动 |",
    "g5": "QA_RESULT:",
}

CONDUCTOR_SYSTEM = (
    "你是科研实训的总控 Conductor。你只输出可落盘的正式工件，不闲聊、不解释、不复述要求。"
    "所有数字、路径、命令必须具体；不确定的写 null 并列入 unknowns。"
    "你遵守门控纪律：没有跑通的基线不开新分支；一次只改一个变量；指标只来自日志。"
    "输出使用简体中文，代码与命令保持原样。"
)

PRINT_LOCK = threading.Lock()


def log(msg, board=None):
    """线程安全日志：同时打屏与落盘。"""
    stamp = datetime.now().strftime("%H:%M:%S")
    line = "[%s] %s" % (stamp, msg)
    with PRINT_LOCK:
        print(line, flush=True)
        if board is not None:
            try:
                board.append("orchestrator.log", line + "\n")
            except Exception:
                pass


# ----------------------------------------------------------------------------
# 1. 黑板（Blackboard）：runs/ 目录即状态
# ----------------------------------------------------------------------------

class Board(object):
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def p(self, rel):
        path = (self.root / rel).resolve()
        if not str(path).startswith(str(self.root)):
            raise ValueError("路径越界: %s" % rel)
        return path

    def exists(self, rel):
        return self.p(rel).exists()

    def write(self, rel, text):
        path = self.p(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            path.write_text(text, encoding="utf-8")
        return path

    def read(self, rel, limit=None):
        path = self.p(rel)
        if not path.exists():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[:limit] if limit else text

    def append(self, rel, text):
        path = self.p(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(text)

    def listdir(self, rel):
        path = self.p(rel)
        if not path.exists():
            return []
        return sorted(str(x.relative_to(self.root)) for x in path.rglob("*") if x.is_file())

    def tree(self):
        files = self.listdir(".")
        return "\n".join("  %-42s %8d B" % (f, self.p(f).stat().st_size) for f in files)


# ----------------------------------------------------------------------------
# 2. 模型客户端（OpenAI 兼容，标准库实现）
# ----------------------------------------------------------------------------

class LLMError(RuntimeError):
    pass


class Client(object):
    def __init__(self, base_url, api_key, model, temperature=0.4, max_tokens=4096, timeout=600):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.calls = 0
        self.chars = 0
        self._lock = threading.Lock()

    def chat(self, system, user, model=None, temperature=None, max_tokens=None):
        payload = {
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.max_tokens,
            "stream": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key,
            },
            method="POST",
        )
        last_err = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8", "replace"))
                text = data["choices"][0]["message"]["content"]
                with self._lock:
                    self.calls += 1
                    self.chars += len(user) + len(text)
                return text
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                last_err = "HTTP %s: %s" % (exc.code, detail)
                if exc.code in (429, 500, 502, 503, 504):
                    time.sleep(3 * (attempt + 1))
                    continue
                break
            except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
                last_err = "%s: %s" % (type(exc).__name__, exc)
                time.sleep(2 * (attempt + 1))
        raise LLMError(last_err or "unknown LLM failure")


# ----------------------------------------------------------------------------
# 3. 提示词装载：从 prompts/*.md 抽取 ```text 围栏，或走内置精简版
# ----------------------------------------------------------------------------

FALLBACK_PROMPTS = {
    "P1": "产出任务契约：objective/inputs/outputs/metric/constraints/unknowns/scoring_hypothesis/red_flags，"
          "outputs 逐字抄题面。只读不写代码。",
    "P2": "你是侦察兵，视角=VIEW。12 分钟内产出该视角的硬结论表（结论|置信度|来源|1分钟验证命令）、"
          "可落地动作≤5、死路、未知。总字数≤800。",
    "P3": "合成情报：列矛盾→裁决→Top8 事实→未知与最坏情况→三条硬约束→建议路线。≤1200 字。",
    "P4": "产出 SAFE/SOTA/GREEDY 三方案，每个含改动清单、耗时、显存估算、预期区间、失败模式、回滚点、依赖。",
    "P5": "红队三角色评审并打分（0.30 时限跑通/0.25 得分上限/0.15 简单度/0.15 可回滚/0.15 合规），"
          "末行 DECISION: main=.. fallback=.. switch_at=.. switch_if=..",
    "P6": "产出 30_spec.json（字段按规格书）与可复制启动命令；5 条自检必须过。",
    "P7": "按规格书实现：单入口 argparse（smoke/train/eval/predict）、结构化日志、seed、异常落盘、"
          "checkpoint、只用依赖白名单。<write path=\"x.py\">…</write> 写文件，<run>cmd</run> 执行命令。",
    "P10": "先做误差分析，再给候选改动池（≥8 条含 ROI），只执行 Top1，记录 before/after/Δ。",
    "P12": "生成题面逐字要求的提交文件 + README 六段；数字只能来自 metrics.json。",
}


def load_prompt_library(prompts_dir):
    """从 prompts/*.md 抽取 '## Pxx' 之后的第一个 ```text 代码块。"""
    lib = {}
    d = Path(prompts_dir)
    if not d.is_dir():
        return lib
    for f in sorted(d.glob("*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        # 以 "## P" 切段
        chunks = re.split(r"\n##\s+(P[\d.]+)", text)
        for i in range(1, len(chunks) - 1, 2):
            pid, body = chunks[i], chunks[i + 1]
            m = re.search(r"```text\n(.*?)```", body, re.S)
            if m:
                lib[pid] = m.group(1).strip()
    return lib


# ----------------------------------------------------------------------------
# 4. 工具块解析（让模型能真的写文件、跑命令）
# ----------------------------------------------------------------------------

WRITE_RE = re.compile(r"<write\s+path=\"([^\"]+)\">\n?(.*?)</write>", re.S)
RUN_RE = re.compile(r"<run>\n?(.*?)</run>", re.S)


def apply_tool_blocks(text, workdir, allow_exec, timeout=600):
    """执行模型输出里的 <write> / <run> 块，返回执行日志。"""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    report = []

    for rel, content in WRITE_RE.findall(text):
        target = (workdir / rel).resolve()
        if not str(target).startswith(str(workdir.resolve())):
            report.append("[SKIP] 越界写入: %s" % rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        report.append("[WRITE] %s (%d B)" % (rel, len(content)))

    for cmd in RUN_RE.findall(text):
        cmd = cmd.strip()
        if not allow_exec:
            report.append("[DRY-RUN] 未授权执行，跳过: %s" % cmd.splitlines()[0][:80])
            continue
        report.append("[RUN] %s" % cmd.splitlines()[0][:100])
        try:
            proc = subprocess.run(
                cmd, shell=True, cwd=str(workdir), timeout=timeout,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            out = proc.stdout.decode("utf-8", "replace")
            tail = "\n".join(out.strip().splitlines()[-25:])
            report.append("[EXIT] %d\n%s" % (proc.returncode, tail))
        except subprocess.TimeoutExpired:
            report.append("[EXIT] TIMEOUT after %ss" % timeout)
        except Exception as exc:  # noqa: BLE001
            report.append("[EXIT] ERROR %s" % exc)

    return "\n".join(report)


# ----------------------------------------------------------------------------
# 5. 编排器
# ----------------------------------------------------------------------------

class Orchestrator(object):
    def __init__(self, board, client, prompts, task_text, minutes=480, allow_exec=False,
                 dry_run=False, force=False):
        self.board = board
        self.client = client
        self.prompts = prompts
        self.task = task_text
        self.deadline = time.time() + minutes * 60
        self.minutes = minutes
        self.allow_exec = allow_exec
        self.dry_run = dry_run
        self.force = force
        self.t0 = time.time()
        self.state_path = "state.json"
        self.state = self._load_state()

    # -- 状态 ---------------------------------------------------------------
    def _load_state(self):
        raw = self.board.read(self.state_path)
        if raw:
            try:
                return json.loads(raw)
            except ValueError:
                pass
        return {"created": datetime.now().isoformat(timespec="seconds"),
                "stages": {}, "models": {}, "minutes": self.minutes}

    def _save_state(self):
        self.board.write(self.state_path, json.dumps(self.state, ensure_ascii=False, indent=2))

    def elapsed(self):
        return (time.time() - self.t0) / 60.0

    def remaining(self):
        return (self.deadline - time.time()) / 60.0

    # 每个门控的实际判据（产物存在 + 关键标志出现），避免拿目录当文件读
    GATE_FILE = {
        "g0": "00_task.md",
        "g1s": "10_brief.md",
        "g2a": "20_candidates.md",
        "g2b": "25_decision.md",
        "g2c": "30_spec.json",
        "g3": "50_logs/smoke.log",
        "g4": "45_boost.md",
        "g5": "95_qa.md",
    }

    def gate_ok(self, stage):
        mark = GATE_MARK.get(stage)
        if not mark:
            return True
        if stage == "g1":
            cards = self.board.listdir("10_cards")
            if len(cards) < 3:
                return False
            return all(mark in self.board.read(c) for c in cards)
        if stage == "g4" and self.board.exists("60_metrics.json"):
            return True
        if stage == "g3":
            smoke = self.board.read("50_logs/smoke.log")
            # 授权执行时必须有 EXIT 0；未授权时只要求代码已落盘
            return ("[EXIT] 0" in smoke) or ("[WRITE]" in smoke)
        rel = self.GATE_FILE.get(stage)
        if not rel or not self.board.exists(rel):
            return False
        return mark in self.board.read(rel)

    # -- 提示词 -------------------------------------------------------------
    def prompt(self, pid):
        return self.prompts.get(pid) or FALLBACK_PROMPTS.get(pid) or ""

    def header(self, stage, pid, extra="", prompt_text=None):
        """每轮给模型的上下文都用同一套壳，避免它漂移。"""
        body = prompt_text if prompt_text is not None else self.prompt(pid)
        return (
            "## 任务书\n%s\n\n"
            "## 当前阶段\nstage=%s  预算=%d 分钟  已用=%.1f 分钟  剩余=%.1f 分钟\n\n"
            "## 黑板现状\n%s\n\n"
            "%s\n"
            "## 本阶段提示词（%s）\n%s\n"
        ) % (
            self.task[:6000] or "（未提供题面文件，请先自行探测工作目录）",
            stage, self.minutes, self.elapsed(), self.remaining(),
            self.board.tree() or "（空）",
            extra,
            pid, body,
        )

    # -- 单阶段执行 ---------------------------------------------------------
    def run_stage(self, stage):
        desc, pid, _, out = STAGES[stage]
        if self.board.exists(out) and not self.force and self.gate_ok(stage):
            log("跳过 %-4s（产物已存在且过门控）: %s" % (stage, out), self.board)
            return True
        if self.remaining() <= 2 and stage not in ("g5",):
            log("预算耗尽，停在 %s 之前。剩余 %.1f 分钟" % (stage, self.remaining()), self.board)
            self.board.write("BLOCKED.md",
                             "# BLOCKED\n\n预算耗尽，未执行 stage=%s。\n剩余产物见 state.json。\n" % stage)
            return False

        log("开始 %-4s %s" % (stage, desc), self.board)
        started = time.time()
        try:
            ok = getattr(self, "stage_" + stage)(pid)
        except LLMError as exc:
            ok = False
            log("× %-4s 模型调用失败（按 D1 降级继续）：%s" % (stage, exc), self.board)
            self.board.append("BLOCKED.md",
                              "\n## stage=%s 调用失败\n- 时间：%s\n- 原因：%s\n- 处置：D1 降级，"
                              "下游阶段用已有产物继续，标记为未验证。\n"
                              % (stage, datetime.now().strftime("%H:%M:%S"), exc))
        except Exception:  # noqa: BLE001
            ok = False
            tb = traceback.format_exc()
            log("× %-4s 内部异常，已落盘：%s" % (stage, tb.strip().splitlines()[-1]), self.board)
            self.board.append("BLOCKED.md", "\n## stage=%s 内部异常\n```\n%s\n```\n" % (stage, tb))
        cost = time.time() - started
        self.state["stages"][stage] = {
            "ok": bool(ok), "seconds": round(cost, 1),
            "at_min": round(self.elapsed(), 1),
            "calls": self.client.calls,
        }
        self._save_state()
        gate = self.gate_ok(stage)
        log("%s %-4s 用时 %.1fs  gate=%s  calls=%d  chars=%d"
            % ("√" if gate else "×", stage, cost,
               "PASS" if gate else "MISS", self.client.calls, self.client.chars),
            self.board)
        return gate

    # g0 --------------------------------------------------------------------
    def stage_g0(self, pid):
        env_cmds = ("whoami; hostname; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null; "
                    "python3 -V; nproc; df -h ~ | tail -1; ls -la")
        out = self.client.chat(CONDUCTOR_SYSTEM, self.header(
            "g0", pid, "## 环境（供你参考，不要重复执行）\n%s\n" % env_cmds))
        self.board.write("00_task.md", out)
        return True

    # g1：5 视角并行 ---------------------------------------------------------
    def stage_g1(self, pid):
        base = self.prompt(pid)
        extra_ctx = "## 已确认的任务契约（读它，不要重新解析题面）\n%s\n" % self.board.read("00_task.md", 5000)

        def one(view):
            user = self.header("g1", pid, extra_ctx).replace("<VIEW>", view)
            user = "[VIEW=%s]\n\n" % view + user
            try:
                text = self.client.chat(CONDUCTOR_SYSTEM, user, model=CHEAP_MODEL, temperature=0.6)
            except LLMError as exc:
                text = ("## VIEW: %s\n### 硬结论\n| # | 结论 | 置信度 | 来源 | 验证 |\n"
                        "| 0 | 该视角检索失败：%s | 0.1 | DEGRADED=no_net | 跳过 |\n"
                        "### 一句话给总控\n检索失败，建议按 D1 降级。\n") % (view, exc)
            self.board.write("10_cards/%s.md" % view, text)
            log("  scout %-7s 完成 %d B" % (view, len(text)), self.board)
            return view

        with ThreadPoolExecutor(max_workers=len(VIEWS)) as pool:
            list(pool.map(one, VIEWS))
        return self.gate_ok("g1")

    # g1s -------------------------------------------------------------------
    def stage_g1s(self, pid):
        cards = self.board.listdir("10_cards")
        blob = "\n\n".join("<!-- %s -->\n%s" % (c, self.board.read(c, 3500)) for c in cards)
        out = self.client.chat(CONDUCTOR_SYSTEM, self.header("g1s", pid, "## 全部情报卡\n%s\n" % blob))
        self.board.write("10_brief.md", out)
        return True

    # g2a -------------------------------------------------------------------
    def stage_g2a(self, pid):
        ctx = "## 情报简报\n%s\n" % self.board.read("10_brief.md", 6000)
        out = self.client.chat(CONDUCTOR_SYSTEM, self.header("g2a", pid, ctx), temperature=0.7)
        self.board.write("20_candidates.md", out)
        return True

    # g2b -------------------------------------------------------------------
    def stage_g2b(self, pid):
        ctx = "## 三方案\n%s\n" % self.board.read("20_candidates.md", 7000)
        out = self.client.chat(CONDUCTOR_SYSTEM, self.header("g2b", pid, ctx), temperature=0.3)
        self.board.write("25_decision.md", out)
        return True

    # g2c -------------------------------------------------------------------
    def stage_g2c(self, pid):
        ctx = ("## 决策\n%s\n\n## 任务契约（提交物逐字抄它）\n%s\n"
               % (self.board.read("25_decision.md", 4000), self.board.read("00_task.md", 4000)))
        out = self.client.chat(CONDUCTOR_SYSTEM, self.header("g2c", pid, ctx), temperature=0.2)
        self.board.write("30_spec.md", out)
        block = re.search(r"```json\n(.*?)```", out, re.S)
        if block:
            raw = block.group(1).strip()
            try:
                json.loads(raw)
            except ValueError as exc:
                raw = json.dumps({"parse_error": str(exc), "raw": raw[:2000]}, ensure_ascii=False, indent=2)
        else:
            raw = json.dumps({"parse_error": "模型未输出 json 代码块"}, ensure_ascii=False)
        self.board.write("30_spec.json", raw)
        return True

    # g3：写代码 + smoke + 修错 -------------------------------------------------
    def stage_g3(self, pid):
        spec = self.board.read("30_spec.json", 6000)
        env = self.board.read("01_env.md", 3000) or "（未做环境自检，代码必须只用标准库 + numpy/pandas/torch 常见包）"
        ctx = "## 实验规格\n%s\n\n## 依赖白名单\n%s\n" % (spec, env)
        workdir = self.board.p("40_code")
        workdir.mkdir(parents=True, exist_ok=True)

        out = self.client.chat(CONDUCTOR_SYSTEM, self.header("g3", pid, ctx), temperature=0.2)
        report = apply_tool_blocks(out, workdir, self.allow_exec)
        self.board.write("50_logs/g3_round0.md", out)
        self.board.append("50_logs/g3_tools.log", "\n=== round 0 ===\n" + report + "\n")
        log("g3 round0 工具执行:\n" + report, self.board)

        # 修错循环（对应 P9 的配额 3 次，这里保守用 2 次）
        for rnd in range(1, 3):
            if "EXIT] 0" in report or not self.allow_exec:
                break
            log("g3 修错 round%d" % rnd, self.board)
            fix_ctx = ctx + "\n## 上一轮执行结果（含报错）\n%s\n\n只改必要的地方，输出完整 <write> 块与复现命令 <run>。\n" % report[-6000:]
            out = self.client.chat(CONDUCTOR_SYSTEM, self.header("g3", pid, fix_ctx), temperature=0.15)
            report = apply_tool_blocks(out, workdir, self.allow_exec)
            self.board.write("50_logs/g3_round%d.md" % rnd, out)
            self.board.append("50_logs/g3_tools.log", "\n=== round %d ===\n%s\n" % (rnd, report))
            log("g3 round%d:\n%s" % (rnd, report), self.board)

        self.board.write("50_logs/smoke.log", report)
        return "EXIT] 0" in report

    # g4 -------------------------------------------------------------------
    def stage_g4(self, pid):
        ctx = ("## 指标\n%s\n\n## 进度账本\n%s\n"
               % (self.board.read("60_metrics.json", 3000) or "（尚无 metrics）",
                  self.board.read("40_progress.md", 3000) or "（尚无进度记录）"))
        out = self.client.chat(CONDUCTOR_SYSTEM, self.header("g4", pid, ctx), temperature=0.5)
        self.board.write("45_boost.md", out)
        return True

    # g5 -------------------------------------------------------------------
    def stage_g5(self, pid):
        qa_prompt = self.prompt("P13")
        ctx = ("## 任务契约（提交物逐字）\n%s\n\n## 指标\n%s\n\n## 决策\n%s\n"
               % (self.board.read("00_task.md", 4000),
                  self.board.read("60_metrics.json", 2500) or "（无）",
                  self.board.read("25_decision.md", 1500)))
        draft = self.client.chat(CONDUCTOR_SYSTEM, self.header("g5", pid, ctx), temperature=0.3)
        self.board.write("90_submission/README.md", draft)

        qa = self.client.chat(
            CONDUCTOR_SYSTEM,
            self.header("g5", "P13",
                        ctx + "\n## 待验收：提交物草稿\n%s\n" % draft[:5000],
                        prompt_text=qa_prompt),
            temperature=0.1)
        self.board.write("95_qa.md", qa)
        return "QA_RESULT: PASS" in qa

    # -- 主循环 -------------------------------------------------------------
    def run(self, stages):
        log("MARS-8H 启动：%d 个阶段，预算 %d 分钟，执行授权=%s，dry_run=%s"
            % (len(stages), self.minutes, self.allow_exec, self.dry_run), self.board)
        results = {}
        for stage in stages:
            results[stage] = self.run_stage(stage)
            if not results[stage] and stage in ("g0", "g3"):
                log("关键阶段 %s 失败，继续推进但会在最终报告标记" % stage, self.board)
        self.state["finished"] = datetime.now().isoformat(timespec="seconds")
        self.state["results"] = results
        self._save_state()
        return results


# ----------------------------------------------------------------------------
# 6. CLI
# ----------------------------------------------------------------------------

def parse_stages(raw):
    if not raw or raw == "all":
        return list(STAGE_ORDER)
    out = []
    for token in raw.split(","):
        token = token.strip().lower()
        if not token:
            continue
        if token not in STAGES:
            raise SystemExit("未知阶段: %s（可选：%s / all）" % (token, ",".join(STAGE_ORDER)))
        out.append(token)
    return out


def _w(text):
    """按东亚字符宽度计算显示宽度，让中文表格对齐。"""
    width = 0
    for ch in text:
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def _pad(text, width):
    text = str(text)
    return text + " " * max(1, width - _w(text))


def print_plan(prompts, stages, minutes, allow_exec, run_dir):
    line = "=" * 74
    print("\n" + line)
    print("MARS-8H 执行计划（dry-run，不联网）")
    print(line)
    print("黑板目录 : %s" % run_dir)
    print("总预算   : %d 分钟" % minutes)
    print("执行授权 : %s" % ("是（会真的跑命令）" if allow_exec else "否（只写文件，<run> 块跳过）"))
    if prompts:
        print("提示词库 : 已从 prompts/ 装载 %d 条 (%s)" % (len(prompts), ",".join(sorted(prompts))))
    else:
        print("提示词库 : 未找到 prompts/，使用内置精简版")
    print("-" * 74)
    print(_pad("阶段", 6) + _pad("说明", 40) + _pad("提示词", 8) + _pad("并行", 6) + "产出")
    print("-" * 74)
    for s in stages:
        desc, pid, par, out = STAGES[s]
        mark = "sqrt" if pid in prompts else "fb"
        print(_pad(s, 6) + _pad(desc[:38], 40) + _pad(pid, 8) + _pad(str(par), 6) + out)
    print("-" * 74)
    total_par = sum(STAGES[s][2] for s in stages)
    print("阶段数 %d，子任务总数约 %d（含并行侦察兵）" % (len(stages), total_par))
    print("时间分配建议：G0 8% / G1 12% / G2 10% / G3 15% / G4 35% / G5 15% / 缓冲 5%")
    print("时间分配依据：见 01-多智能体架构设计.md 第 4 节")
    print(line + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="MARS-8H 科研实训多智能体编排器")
    ap.add_argument("--task", help="题面文件路径（md/txt）；也可把题面正文直接粘进 --task-text")
    ap.add_argument("--task-text", default="", help="题面正文（与 --task 二选一）")
    ap.add_argument("--run-dir", default="runs", help="黑板目录，默认 ./runs")
    ap.add_argument("--prompts-dir", default=str(Path(__file__).resolve().parent / "prompts"),
                    help="提示词分册目录，默认同目录 prompts/")
    ap.add_argument("--stages", default="all", help="逗号分隔，如 g0,g1 或 all")
    ap.add_argument("--from", dest="from_stage", default=None, help="从某阶段续跑，如 g2")
    ap.add_argument("--only", default=None, help="只跑某阶段")
    ap.add_argument("--minutes", type=int, default=480, help="总预算分钟，默认 480（8 小时）")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--api-key", default=DEFAULT_API_KEY)
    ap.add_argument("--allow-exec", action="store_true", help="真的执行模型输出的 <run> 命令")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不联网")
    ap.add_argument("--force", action="store_true", help="忽略已有产物，强制重跑")
    ap.add_argument("--temp", type=float, default=0.4)
    ap.add_argument("--max-tokens", type=int, default=8192)
    args = ap.parse_args(argv)

    prompts = load_prompt_library(args.prompts_dir)
    stages = parse_stages(args.only or args.stages)
    if args.from_stage:
        idx = STAGE_ORDER.index(args.from_stage)
        stages = STAGE_ORDER[idx:]

    if args.dry_run:
        print_plan(prompts, stages, args.minutes, args.allow_exec, Path(args.run_dir).resolve())
        return 0

    if not args.api_key:
        print("× 缺少 API Key：export MARS_API_KEY=... 或用 --api-key", file=sys.stderr)
        return 2

    task_text = args.task_text
    if args.task:
        path = Path(args.task).expanduser()
        if not path.exists():
            print("× 题面文件不存在: %s" % path, file=sys.stderr)
            return 2
        task_text = path.read_text(encoding="utf-8", errors="replace")

    board = Board(args.run_dir)
    client = Client(args.base_url, args.api_key, args.model,
                    temperature=args.temp, max_tokens=args.max_tokens)
    orch = Orchestrator(board, client, prompts, task_text,
                        minutes=args.minutes, allow_exec=args.allow_exec, force=args.force)
    print_plan(prompts, stages, args.minutes, args.allow_exec, board.root)

    try:
        results = orch.run(stages)
    except KeyboardInterrupt:
        log("中断。可从 --from 续跑，已生成产物保留在 %s" % board.root, board)
        return 130
    except Exception:  # noqa: BLE001
        board.append("orchestrator.log", traceback.format_exc())
        print("× 编排器异常，已写入 %s/orchestrator.log" % board.root, file=sys.stderr)
        return 1

    print("\n" + "=" * 68)
    print("执行结果")
    print("=" * 68)
    for s in stages:
        print("  %-5s %-6s  %s" % (s, "PASS" if results.get(s) else "MISS", STAGES[s][3]))
    print("-" * 68)
    print("模型调用 %d 次，传输字符 ≈ %d" % (client.calls, client.chars))
    print("黑板：%s" % board.root)
    print("=" * 68)
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
