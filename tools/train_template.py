#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
train_template.py · 契约合规的训练/推理骨架
===========================================

任何一道实训题，把这个文件当成起点改，比让模型从零写要快得多，也更不容易在
"日志没法看 / 没有 smoke / 报错不落盘" 上翻车。

它已经实现了 P7 要求的全部硬契约：
  * 单入口 + argparse：--mode {smoke,train,eval,predict}
  * smoke 模式 60 秒内跑完，打印 SMOKE_OK 并 exit 0
  * 结构化日志：[CONFIG] [STEP] [EVAL] [SAVE] [DONE]
  * seed 固定、异常落盘、checkpoint 只留最近 2 个 + best
  * 全部超参来自 config（json），代码里没有魔法数字

用法
----
python3 train_template.py --mode smoke
python3 train_template.py --mode train  --config config.json
python3 train_template.py --mode eval   --ckpt runs/70_ckpt/best.pt
python3 train_template.py --mode predict --ckpt runs/70_ckpt/best.pt --out test_result.json

把它改成真题时，只需要动 4 个标记了 TODO 的函数：
  load_data() / build_model() / train_one_epoch() / evaluate()
"""

import argparse
import json
import os
import random
import sys
import time
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# 0. 日志：只打这五种行，任何监控脚本都能解析
# ---------------------------------------------------------------------------

def kv(**kw):
    return " ".join("%s=%s" % (k, v) for k, v in kw.items() if v is not None)


def log(tag, **kw):
    print("[%s] %s" % (tag, kv(**kw)), flush=True)


# ---------------------------------------------------------------------------
# 1. 配置
# ---------------------------------------------------------------------------

DEFAULT_CFG = {
    "seed": 42,
    "data": {"train": "", "val": "", "test": "", "max_samples": 0},
    "model": {"name": "dummy", "hidden": 64},
    "train": {"epochs": 3, "batch_size": 32, "lr": 1e-3, "num_workers": 0},
    "log_every": 20,
    "out_dir": "runs",
}


def deep_merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_cfg(path):
    cfg = dict(DEFAULT_CFG)
    if path and Path(path).exists():
        with open(path, "r", encoding="utf-8") as fh:
            cfg = deep_merge(cfg, json.load(fh))
    return cfg


def seed_everything(seed):
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch
        torch.manual_seed(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# 2. 四个 TODO 点（换成真题的实现）
# ---------------------------------------------------------------------------

def load_data(cfg, split, limit=0):
    """TODO: 读你的数据。返回 (features, labels) 或 dataset 对象。

    契约：
      * split in {"train","val","test"}
      * limit>0 时只取前 limit 条（smoke 模式用）
      * 数据结构不合法要 raise ValueError，不要静默跳过
    """
    n = limit or 64
    if limit == 0:
        n = {"train": 512, "val": 128, "test": 128}[split]
    xs = [[random.random() for _ in range(8)] for _ in range(n)]
    ys = [random.randint(0, 1) for _ in range(n)]
    return xs, ys


def build_model(cfg):
    """TODO: 建模型。返回任何带 fit/predict 或 forward 的对象。

    这里给一个纯 Python 的最近邻，保证不装 torch 也能跑通 smoke。
    """
    class NearestCentroid(object):
        def __init__(self):
            self.centroids = {}

        def fit(self, xs, ys):
            self.centroids = {}          # 重复调用必须重置，否则质心会被当成样本
            for x, y in zip(xs, ys):
                self.centroids.setdefault(y, []).append(x)
            for y, rows in self.centroids.items():
                dim = len(rows[0])
                self.centroids[y] = [sum(r[i] for r in rows) / len(rows) for i in range(dim)]
            return self

        def predict(self, xs):
            out = []
            for x in xs:
                best, best_d = 0, float("inf")
                for y, c in self.centroids.items():
                    d = sum((a - b) ** 2 for a, b in zip(x, c))
                    if d < best_d:
                        best, best_d = y, d
                out.append(best)
            return out

    return NearestCentroid()


def evaluate(model, xs, ys):
    """TODO: 换成题目的指标（务必与官方评测口径一致）。"""
    pred = model.predict(xs)
    acc = sum(int(p == t) for p, t in zip(pred, ys)) / max(1, len(ys))
    return {"acc": round(acc, 6), "n": len(ys)}


# ---------------------------------------------------------------------------
# 3. checkpoint
# ---------------------------------------------------------------------------

def save_ckpt(out_dir, tag, payload):
    ckpt_dir = Path(out_dir) / "70_ckpt"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    path = ckpt_dir / ("%s.json" % tag)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    # 只保留最近 2 个 + best
    epochs = sorted([p for p in ckpt_dir.glob("e*.json")],
                    key=lambda p: p.stat().st_mtime)
    for old in epochs[:-2]:
        try:
            old.unlink()
        except OSError:
            pass
    log("SAVE", epoch=tag, path=str(path))
    return str(path)


# ---------------------------------------------------------------------------
# 4. 三个模式
# ---------------------------------------------------------------------------

def run_smoke(cfg):
    t0 = time.time()
    xs, ys = load_data(cfg, "train", limit=32)
    assert len(xs) == len(ys) > 0, "数据为空，检查路径"
    model = build_model(cfg).fit(xs, ys)
    res = evaluate(model, xs, ys)
    log("EVAL", epoch="smoke", **res)
    print("SMOKE_OK", flush=True)
    log("DONE", mode="smoke", total_min=round((time.time() - t0) / 60, 3))
    return 0


def run_train(cfg):
    t0 = time.time()
    xs, ys = load_data(cfg, "train")
    vx, vy = load_data(cfg, "val")
    log("CONFIG", seed=cfg["seed"], bs=cfg["train"]["batch_size"],
        epochs=cfg["train"]["epochs"], n_train=len(xs), n_val=len(vx))

    model = build_model(cfg)
    best = -1.0
    for epoch in range(1, cfg["train"]["epochs"] + 1):
        step_t0 = time.time()
        model.fit(xs, ys)
        log("STEP", step=epoch, epoch=epoch,
            loss=round(1.0 / epoch, 4), lr=cfg["train"]["lr"],
            sec_per_step=round(time.time() - step_t0, 3))
        res = evaluate(model, vx, vy)
        log("EVAL", epoch=epoch, **res)
        save_ckpt(cfg["out_dir"], "e%d" % epoch, {"epoch": epoch, "metrics": res})
        if res.get("acc", 0) > best:
            best = res["acc"]
            save_ckpt(cfg["out_dir"], "best", {"epoch": epoch, "metrics": res})
        if epoch % cfg.get("log_every", 20) == 0:
            pass
    log("DONE", mode="train", total_min=round((time.time() - t0) / 60, 2), best_acc=best)
    return 0


def run_eval(cfg, ckpt):
    xs, ys = load_data(cfg, "val")
    model = build_model(cfg)
    model.fit(*load_data(cfg, "train"))
    res = evaluate(model, xs, ys)
    log("EVAL", split="val", ckpt=ckpt or "none", **res)
    out = Path(cfg["out_dir"]) / "60_metrics.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "metric_name": "acc", "value": res["acc"], "direction": "max",
        "split": "val", "n_samples": res["n"], "seed": cfg["seed"],
        "checkpoint": ckpt or "in-memory",
        "eval_cmd": "python3 train_template.py --mode eval",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False))
    return 0


def run_predict(cfg, ckpt, out_path):
    xs, _ = load_data(cfg, "test")
    model = build_model(cfg).fit(*load_data(cfg, "train"))
    preds = model.predict(xs)
    # 题面要求什么格式就改成什么格式；样例给 {"predictions": [...]}
    payload = {"predictions": preds}
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    log("DONE", mode="predict", n=len(preds), out=str(out))
    return 0


# ---------------------------------------------------------------------------
# 5. 入口（异常统一落盘并 exit 1）
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="smoke",
                    choices=["smoke", "train", "eval", "predict"])
    ap.add_argument("--config", default="")
    ap.add_argument("--ckpt", default="")
    ap.add_argument("--out", default="test_result.json")
    args = ap.parse_args(argv)

    cfg = load_cfg(args.config)
    seed_everything(cfg["seed"])
    Path(cfg["out_dir"], "50_logs").mkdir(parents=True, exist_ok=True)
    log("CONFIG", mode=args.mode, seed=cfg["seed"], out_dir=cfg["out_dir"])

    if args.mode == "smoke":
        return run_smoke(cfg)
    if args.mode == "train":
        return run_train(cfg)
    if args.mode == "eval":
        return run_eval(cfg, args.ckpt)
    return run_predict(cfg, args.ckpt, args.out)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        tb = traceback.format_exc()
        logdir = Path("runs/50_logs")
        logdir.mkdir(parents=True, exist_ok=True)
        (logdir / "error.log").write_text(tb, encoding="utf-8")
        print("[FATAL] %s: %s" % (type(sys.exc_info()[1]).__name__, sys.exc_info()[1]), flush=True)
        sys.exit(1)
