#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selftest.py · 离线自检（不联网、不花钱、不碰真模型）
==================================================

在本地起一个 mock 的 OpenAI 兼容端点，把整条流水线真跑一遍，验证：
  1) 编排器能加载仓库里的 24 条提示词
  2) 10 个阶段全部门控通过（含 g3 写码执行、g3b 指标抽取、g5 交付）
  3) 指标能从日志里被确定性抽出（不是模型编的）
  4) 断点续跑幂等（第二次全部跳过）
  5) 端点挂掉时按 D1 降级而不是崩

用法：
    python3 tools/selftest.py            # 跑全部检查
    python3 tools/selftest.py --keep     # 保留临时目录，方便看产物
    python3 tools/selftest.py -v         # 打印每个阶段的输出

退出码：0 全通过；1 有失败项。
"""

import argparse
import importlib.util
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORCH_PATH = Path(__file__).resolve().parent / "orchestrator-mars.py"

RESULTS = []


def record(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print("  %s %-46s %s" % ("√" if ok else "×", name, detail))
    return ok


# ---------------------------------------------------------------------------
# mock 模型：按阶段返回不同内容
# ---------------------------------------------------------------------------

CARD = """## VIEW: {view}
### 硬结论
| # | 结论 | 置信度 | 来源 | 1 分钟验证命令 |
|---|---|---|---|---|
| 1 | 先用最笨方法出分 | 0.9 | https://example.com/a | python3 -c "print(1)" |
| 2 | 单卡 80G 足够 | 0.6 | 推理 | nvidia-smi |

### 可直接落地的动作
1. 跑 smoke
### 死路
- 换大模型
### 我还不知道的
- 真实指标（5 分钟）
### 一句话给总控
先跑通再优化。
"""

TRAIN_PY = r'''
import argparse, json, sys
from pathlib import Path
p = argparse.ArgumentParser(); p.add_argument("--mode", default="smoke")
a = p.parse_args()
print("[CONFIG] bs=8 mode=%s" % a.mode)
if a.mode == "smoke":
    print("SMOKE_OK"); sys.exit(0)
log = Path("../50_logs/main.log"); log.parent.mkdir(parents=True, exist_ok=True)
with log.open("a") as fh:
    fh.write("[STEP] step=1 epoch=0 loss=0.42 sec_per_step=0.8\n")
    fh.write("[EVAL] epoch=0 acc=0.8123 n=128\n")
    fh.write("[DONE] total_min=3.1 best_acc=0.8123\n")
print("[DONE] ok")
'''


def reply(user):
    import re
    stage = "?"
    m = re.search(r"stage=(\w+)", user)
    if m:
        stage = m.group(1)
    view = re.search(r"\[VIEW=(\w+)\]", user)
    view = view.group(1) if view else "TASK"

    if stage == "g0":
        body = {"objective": "mock 任务：把最笨基线跑通",
                "inputs": [{"path": "/data/mock", "type": "jsonl", "schema": "seq,label"}],
                "outputs": [{"path": "test_result.json", "format": "json"}],
                "metric": {"name": "acc", "direction": "max"},
                "constraints": {"no_net": True, "allow_pretrained": True},
                "unknowns": [{"q": "测试集条数", "resolve_by": "wc -l", "cost_min": 2}],
                "scoring_hypothesis": [{"item": "指标", "weight_guess": 0.6, "evidence": "题面"}],
                "red_flags": ["提交格式", "smoke 未过"]}
        return "# 任务契约\n\n```json\n" + json.dumps(body, ensure_ascii=False, indent=2) + "\n```\n"
    if stage == "g1":
        if "## 工具返回" not in user:
            # 第一轮：只发工具调用，验证编排器真的执行并回灌
            return "<search>mock query %s</search>" % view
        return CARD.format(view=view)
    if stage == "g1s":
        return "# 情报简报（G1）\n## 一句话结论\n走 SAFE。\n## 矛盾与裁决\n| 矛盾 | 裁决 |\n|---|---|\n| mock | mock |\n"
    if stage == "g2a":
        return "# 三方案候选\n## SAFE\n冻结主干 + 轻量头\n## SOTA\n全参微调\n## GREEDY\n阈值搜索\n"
    if stage == "g2b":
        return ("# 决策\n\n| 维度 | 权重 | SAFE | SOTA | GREEDY |\n|---|---|---|---|---|\n"
                "| 跑通 | 0.30 | 5 | 3 | 4 |\n\n"
                "DECISION: main=SAFE fallback=GREEDY switch_at=300 switch_if=metric<0.5\n")
    if stage == "g2c":
        spec = {"mission_id": "mock-001", "deadline_min": 480,
                "task_dir": "/tmp/mock",
                "data": {"train": "/data/mock/train"},
                "submission": {"files": [{"path": "test_result.json", "format": "json"}],
                               "dir": "runs/90_submission"},
                "metric": {"name": "acc", "direction": "max",
                           "eval_cmd": "python3 train.py --mode eval"},
                "main_plan": "SAFE", "code_entry": "train.py",
                "smoke_test": "python3 train.py --mode smoke",
                "time_boxes": [{"stage": "baseline", "max_min": 60}],
                "success_criteria": [{"at_min": 120, "check": "metrics 有值", "else": "降级"}],
                "fallback": {"trigger": "t>300 且无分数", "action": "切 GREEDY"}}
        return "# 规格书\n\n```json\n" + json.dumps(spec, ensure_ascii=False, indent=2) + "\n```\n"
    if stage == "g3":
        return ('写好了。\n\n<write path="train.py">\n' + TRAIN_PY + '\n</write>\n\n'
                '<run>python3 train.py --mode smoke</run>\n'
                '<run>python3 train.py --mode train</run>\n')
    if stage == "g4":
        return "# 提分\n| 改动 | before | after | Δ | 耗时 | 是否保留 |\n|---|---|---|---|---|---|\n| 阈值 0.42 | 0.81 | 0.83 | +0.02 | 10 | 是 |\n"
    if stage == "g5":
        if "P13" in user and "验收" in user:
            return "# 验收\n| # | 检查项 | 结果 | 通过? |\n|---|---|---|---|\n| 1 | 文件存在 | 是 | Y |\n\nQA_RESULT: PASS\n"
        return ("# README\n\n## 1. 任务理解\nmock\n\n## 2. 方法\nmock\n\n## 3. 复现命令\n"
                "```\npython3 train.py --mode smoke\n```\n\n## 4. 结果\n| 配置 | acc |\n|---|---|\n| safe | 0.83 |\n\n"
                "## 5. 失败与取舍\nmock\n\n## 6. 未完成与后续\nmock\n")
    return "ok"


class MockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n).decode("utf-8"))
        user = "\n".join(m.get("content", "") for m in req.get("messages", []))
        body = json.dumps({"choices": [{"message": {"role": "assistant", "content": reply(user)}}]},
                          ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class StubSearch(object):
    """离线替身：证明工具循环在工作，不产生真实网络请求。"""
    calls = []

    @classmethod
    def search(cls, query, limit=5):
        cls.calls.append(query)
        return [{"title": "stub result for %s" % query,
                 "url": "https://example.com/stub",
                 "snippet": "stub snippet", "backend": "stub"}]

    @staticmethod
    def fetch(url, max_chars=8000):
        return "stub page body"

    @staticmethod
    def format_results(results, max_items=5):
        return "\n".join("%d. %s\n   %s" % (i, r["url"], r["snippet"])
                         for i, r in enumerate(results, 1)) or "(无结果)"


def start_mock():
    srv = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    return srv, port


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def load_orch():
    spec = importlib.util.spec_from_file_location("orchestrator_mars", str(ORCH_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def run_pipeline(mod, workdir, base_url, minutes=10, stages="all", force=False, verbose=False):
    board = mod.Board(str(workdir / "runs"))
    client = mod.Client(base_url, "mock-key", "mock-model", max_calls=200)
    prompts = mod.load_prompt_library(str(ROOT / "prompts"))
    orch = mod.Orchestrator(board, client, prompts, "mock 题面：给定 mock 数据，预测标签，指标 acc。",
                            minutes=minutes, allow_exec=True, force=force)
    stage_list = mod.parse_stages(stages)
    if not verbose:
        mod.log = lambda *a, **k: None  # 静音
    results = orch.run(stage_list)
    return orch, board, results


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    print("=" * 70)
    print("MARS-8H 离线自检")
    print("=" * 70)

    if not ORCH_PATH.exists():
        print("× 找不到 tools/orchestrator-mars.py")
        return 1

    workdir = Path(tempfile.mkdtemp(prefix="mars_selftest_"))
    print("临时目录 : %s\n" % workdir)

    mod = load_orch()
    real_netsearch = mod.netsearch
    mod.netsearch = StubSearch        # 自检默认离线，用 stub 验证工具循环
    prompts = mod.load_prompt_library(str(ROOT / "prompts"))
    record("提示词装载（应 ≥ 24 条）", len(prompts) >= 24, "%d 条" % len(prompts))
    record("netsearch 可导入", real_netsearch is not None,
           "有联网检索" if real_netsearch else "缺失（不影响离线自检）")

    srv, port = start_mock()
    base_url = "http://127.0.0.1:%d/v1" % port

    print("\n[1] 全流程（10 阶段）")
    orch, board, results = run_pipeline(mod, workdir, base_url, verbose=args.verbose)
    for st in mod.STAGE_ORDER:
        record("阶段 %-4s 门控通过" % st, results.get(st, False))

    print("\n[2] 产物检查")
    metrics_raw = board.read("60_metrics.json")
    try:
        metrics = json.loads(metrics_raw)
    except ValueError:
        metrics = {}
    record("60_metrics.json 可解析", bool(metrics))
    record("指标由日志确定性抽取（非模型生成）",
           metrics.get("derived_by", "").startswith("stage_g3b"),
           "value=%s" % metrics.get("value"))
    record("指标值正确（日志里是 0.8123）",
           abs(float(metrics.get("value") or 0) - 0.8123) < 1e-6)
    record("00_task.md 落盘", board.exists("00_task.md"))
    record("10_cards 五张卡片", len(board.listdir("10_cards")) == 5,
           "%d 张" % len(board.listdir("10_cards")))
    record("25_decision 有 DECISION 行", "DECISION:" in board.read("25_decision.md"))
    record("30_spec.json 通过字段校验", "mission_id" in board.read("30_spec.json"))
    record("g3 产出了可执行代码", board.exists("40_code/train.py"))
    record("95_qa.md 有 QA_RESULT", "QA_RESULT" in board.read("95_qa.md"))
    tool_log = board.read("50_logs/tool_calls.log")
    record("侦察兵真的发起了检索（工具循环生效）",
           "search=" in tool_log, "%d 次检索" % tool_log.count("search="))
    record("5 个视角各查了一次", len(set(StubSearch.calls)) == 5,
           "查询 %d 条" % len(StubSearch.calls))

    print("\n[3] 幂等续跑（第二次应全部跳过、不再调模型）")
    before = orch.client.calls
    orch2, _, results2 = run_pipeline(mod, workdir, base_url, verbose=args.verbose)
    record("续跑不再调用模型", orch2.client.calls == 0, "+%d 次调用" % orch2.client.calls)
    record("续跑结果仍全 PASS", all(results2.values()))

    print("\n[4] 端点不可用 → D1 降级（不许崩）")
    dead_url = "http://127.0.0.1:%d/v1" % free_port()
    wd2 = Path(tempfile.mkdtemp(prefix="mars_selftest_dead_"))
    try:
        mod.log = lambda *a, **k: None
        _, board2, res2 = run_pipeline(mod, wd2, dead_url, minutes=3,
                                       stages="g0,g1", verbose=args.verbose)
        crashed = False
    except Exception:  # noqa: BLE001
        crashed = True
        board2 = None
    record("端点挂掉不崩溃", not crashed)
    if board2:
        record("降级卡片已落盘", len(board2.listdir("10_cards")) == 5,
               "%d 张" % len(board2.listdir("10_cards")))
        record("BLOCKED.md 记录了原因", "调用失败" in board2.read("BLOCKED.md"))

    print("\n[5] 预算保护（max_calls）")
    c = mod.Client(base_url, "k", "m", max_calls=2)
    c.chat("s", "stage=g0 u")
    c.chat("s", "stage=g0 u")
    try:
        c.chat("s", "stage=g0 u")
        record("超出 max_calls 时拒绝调用", False, "未触发")
    except mod.LLMError as exc:
        record("超出 max_calls 时拒绝调用", "上限" in str(exc))

    srv.shutdown()

    print("\n" + "=" * 70)
    failed = [r for r in RESULTS if not r[1]]
    print("结果：%d/%d 通过" % (len(RESULTS) - len(failed), len(RESULTS)))
    if failed:
        print("\n未通过：")
        for name, _, detail in failed:
            print("  × %s  %s" % (name, detail))
    else:
        print("全部通过：这条流水线在你机器上是可跑的。")
    print("=" * 70)

    if args.keep:
        print("\n产物保留在：%s" % workdir)
        print("  ls %s" % (workdir / "runs"))
    else:
        shutil.rmtree(workdir, ignore_errors=True)

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
