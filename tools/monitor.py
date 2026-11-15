#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
monitor.py · 日志监控器（把 P8 的六态判定变成一条命令）
=====================================================

用途：训练启动后，在另一个终端跑它，它会每 N 秒扫一次日志，打印一行标准
[MONITOR] 记录并追加到 runs/40_progress.md。你不用再盯着满屏日志猜进度。

用法
----
python3 monitor.py --log runs/50_logs/main.log                 # 一直盯到进程结束/日志 [DONE]
python3 monitor.py --log runs/main.log --every 60 --total-min 480
python3 monitor.py --log runs/main.log --once                  # 只看一眼

判定
----
RUNNING  还在推进
STALL    N 秒内没有新的 [STEP]/[EVAL]
DIVERGE  loss 出现 nan/inf，或连续 3 次 eval 下降
OOM      出现 CUDA out of memory
DEAD     出现 [FATAL]，或 pid 文件存在但进程已消失
DONE     出现 [DONE]
"""

import argparse
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

STEP_RE = re.compile(r"\[STEP\]\s+(.*)")
EVAL_RE = re.compile(r"\[EVAL\]\s+(.*)")
LOSS_RE = re.compile(r"loss=([0-9.eE+-]+|nan|inf)")
STEPNUM_RE = re.compile(r"step=(\d+)")
SPSTEP_RE = re.compile(r"sec_per_step=([0-9.]+)")
ACC_RE = re.compile(r"(acc|f1|auc|score|metric)=([0-9.eE+-]+)")


def tail(path, nbytes=200000):
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > nbytes:
                fh.seek(size - nbytes)
            return fh.read().decode("utf-8", "replace")
    except (OSError, AttributeError):
        return ""


def analyze(text, stall_sec, last_sig, eval_hist):
    """返回 (verdict, steps, evals, sps, advice)。last_sig=(step, n_eval, 上次推进时间)。"""
    lines = text.splitlines()
    steps = [int(m.group(1)) for m in (STEPNUM_RE.search(l) for l in lines if "[STEP]" in l) if m]
    sps = [float(m.group(1)) for m in (SPSTEP_RE.search(l) for l in lines if "[STEP]" in l) if m]

    evals = []
    for line in lines:
        if "[EVAL]" in line:
            m = ACC_RE.search(line)
            if m:
                try:
                    evals.append(float(m.group(2)))
                except ValueError:
                    pass
    eval_hist.extend(evals)
    del eval_hist[:-8]

    losses = []
    for line in lines[-400:]:
        m = LOSS_RE.search(line)
        if m:
            losses.append(m.group(1))

    if "[DONE]" in text:
        return "DONE", steps, evals, sps, "训练已正常结束，进入 P11 评测固化"
    if "[FATAL]" in text:
        return "DEAD", steps, evals, sps, "出现 [FATAL]，读 runs/50_logs/error.log，进入 P9"
    if "CUDA out of memory" in text or "OutOfMemoryError" in text:
        return "OOM", steps, evals, sps, "batch_size 减半重启，别改模型结构"
    if any(x in ("nan", "inf") for x in losses[-5:]):
        return "DIVERGE", steps, evals, sps, "loss 出现 nan/inf：降 lr x0.3 或回滚 checkpoint"
    if len(eval_hist) >= 4:
        tail = eval_hist[-4:]
        if all(tail[i] > tail[i + 1] for i in range(len(tail) - 1)):
            return "DIVERGE", steps, evals, sps, "连续 3 次 eval 下降：早停或回滚 best"

    cur = (steps[-1] if steps else 0, len(evals))
    if cur == tuple(last_sig[:2]) and (time.time() - last_sig[2]) > stall_sec:
        return "STALL", steps, evals, sps, "无新 step：先怀疑 dataloader（num_workers 设 0 复测）"
    return "RUNNING", steps, evals, sps, ""


def one_round(args, state):
    logpath = Path(args.log)
    if not logpath.exists():
        print("[MONITOR] log-not-found path=%s" % logpath)
        return "DEAD", {}
    text = tail(logpath)
    last = state.setdefault("sig", (0, 0, time.time()))
    verdict, steps, evals, sps, advice = analyze(
        text, args.stall_sec, last, state.setdefault("hist", []))

    step = steps[-1] if steps else 0
    metric = evals[-1] if evals else "na"
    sps_v = sps[-1] if sps else 0.0
    eta = "na"
    if steps and sps_v and args.total_steps:
        eta = round((args.total_steps - step) * sps_v / 60.0, 1)

    cur = (step, len(evals))
    if cur != tuple(last[:2]):
        state["sig"] = (cur[0], cur[1], time.time())

    line = "[MONITOR] t=%s step=%s metric=%s sps=%.2f eta=%s verdict=%s" % (
        datetime.now().strftime("%H:%M:%S"), step, metric, sps_v, eta, verdict)
    print(line, flush=True)

    prog = Path(args.progress)
    prog.parent.mkdir(parents=True, exist_ok=True)
    with prog.open("a", encoding="utf-8") as fh:
        fh.write("| %s | %s | %s | %s | %s | %s |\n" % (
            datetime.now().strftime("%H:%M"), step, metric,
            round(sps_v, 2), eta, verdict))
    if advice:
        print("    建议：%s" % advice, flush=True)
    return verdict, {"step": step, "metric": metric, "eta": eta, "advice": advice}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--progress", default="runs/40_progress.md")
    ap.add_argument("--every", type=int, default=60, help="轮询间隔秒")
    ap.add_argument("--stall-sec", type=int, default=300)
    ap.add_argument("--total-steps", type=int, default=0)
    ap.add_argument("--max-min", type=float, default=0, help="最长盯多久（分钟），0=直到 DONE/DEAD")
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args(argv)

    prog = Path(args.progress)
    prog.parent.mkdir(parents=True, exist_ok=True)
    if not prog.exists():
        prog.write_text("# 进度账本（monitor.py 自动追加）\n\n"
                        "| 时间 | step | metric | sec/step | eta(min) | verdict |\n"
                        "|---|---|---|---|---|---|\n", encoding="utf-8")

    state = {}
    t0 = time.time()
    while True:
        verdict, _ = one_round(args, state)
        if args.once or verdict in ("DONE", "DEAD"):
            break
        if args.max_min and (time.time() - t0) / 60.0 > args.max_min:
            print("达到 --max-min，停止监控（训练仍在跑）")
            break
        time.sleep(args.every)
    return 0


if __name__ == "__main__":
    sys.exit(main())
