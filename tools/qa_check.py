#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qa_check.py · 交付物机械验收（P13 的可执行部分）
================================================

把 P13 那 20 条里能自动化的部分做成一条命令。最后 20 分钟跑它，比肉眼检查可靠。

用法
----
python3 qa_check.py --submission runs/90_submission \
                    --require test_result.json,README.md,train.py,train.log \
                    --expect-count 2000 \
                    --metrics runs/60_metrics.json \
                    --log runs/50_logs/main.log

退出码：0 = 全绿；1 = 有必修项；2 = 参数/路径错误
"""

import argparse
import json
import re
import sys
from pathlib import Path

IMPORT_RE = re.compile(r"^\s*(?:import\s+([a-zA-Z0-9_.]+)|from\s+([a-zA-Z0-9_.]+)\s+import)", re.M)
ABS_PATH_RE = re.compile(r"(/Users/[^\s\"']+|/home/[^\s\"']+|[A-Z]:\\\\Users)")
FLOAT_RE = re.compile(r"\b\d+\.\d+\b")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
README_SECTIONS = [
    ("任务理解", ("任务理解", "问题定义", "任务定义")),
    ("方法", ("方法", "approach", "method")),
    ("复现命令", ("复现", "reproduce", "运行", "usage")),
    ("结果", ("结果", "result", "指标")),
    ("失败与取舍", ("失败", "取舍", "尝试", "局限")),
    ("未完成", ("未完成", "后续", "future", "todo")),
]
JUNK = ("__pycache__", ".ipynb_checkpoints", ".pytest_cache", ".git", ".DS_Store")


class Checker(object):
    def __init__(self, args):
        self.args = args
        self.sub = Path(args.submission)
        self.rows = []

    def add(self, item, detail, ok, must=True):
        self.rows.append({"item": item, "detail": str(detail), "ok": bool(ok),
                          "must": bool(must)})

    # -- 各项检查 -----------------------------------------------------------
    def check_structure(self):
        self.add("提交目录存在", self.sub, self.sub.is_dir())

        required = [x.strip() for x in (self.args.require or "").split(",") if x.strip()]
        missing = [r for r in required if not (self.sub / r).exists()]
        self.add("必需文件齐全", "缺 %s" % missing if missing else "%d 个齐全" % len(required),
                 not missing)

        junk = []
        for p in self.sub.rglob("*"):
            if any(j in str(p) for j in JUNK):
                junk.append(str(p.relative_to(self.sub)))
        self.add("无缓存垃圾文件", junk[:3] if junk else "clean", not junk, must=False)

        big = [(str(p.relative_to(self.sub)), p.stat().st_size // (1024 * 1024))
               for p in self.sub.rglob("*") if p.is_file() and p.stat().st_size > 200 * 1024 * 1024]
        self.add("无超大文件(>200MB)", big if big else "ok", not big)

        weird = [p.name for p in self.sub.rglob("*") if p.is_file()
                 and (re.search(r"[\s\u4e00-\u9fff]", p.name))]
        self.add("文件名无空格/中文", weird[:3] if weird else "ok", not weird)

    def check_files(self):
        jsons = sorted(self.sub.rglob("*.json"))
        for p in jsons:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                n = len(data) if isinstance(data, (list, dict)) else "scalar"
                self.add("json 可解析: %s" % p.name, "%s len=%s" % (type(data).__name__, n), True)
            except Exception as exc:  # noqa: BLE001
                self.add("json 可解析: %s" % p.name, "%s: %s" % (type(exc).__name__, exc), False)
                continue

            if self.args.expect_count:
                got = None
                if isinstance(data, list):
                    got = len(data)
                elif isinstance(data, dict):
                    for key in ("predictions", "results", "data", "answers", "outputs"):
                        if isinstance(data.get(key), list):
                            got = len(data[key])
                            break
                self.add("样本数吻合: %s" % p.name,
                         "期望 %d 实际 %s" % (self.args.expect_count, got),
                         got == self.args.expect_count)

        for p in self.sub.rglob("*"):
            if not p.is_file() or p.suffix.lower() in (".pt", ".bin", ".pkl", ".zip", ".png", ".jpg"):
                continue
            raw = p.read_bytes()[:3]
            if raw == b"\xef\xbb\xbf":
                self.add("无 BOM: %s" % p.name, "有 BOM", False)
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                self.add("UTF-8 可解码: %s" % p.name, "解码失败", False)
                continue
            hits = ABS_PATH_RE.findall(text)[:2]
            self.add("无绝对路径: %s" % p.name, hits if hits else "ok", not hits, must=False)

    def check_readme(self):
        readme = None
        for name in ("README.md", "readme.md", "README.txt"):
            if (self.sub / name).exists():
                readme = self.sub / name
                break
        if not readme:
            self.add("README 存在", "缺失", False)
            return
        text = readme.read_text(encoding="utf-8", errors="replace")
        self.add("README 存在", "%d 字" % len(text), True)
        for label, keys in README_SECTIONS:
            hit = any(k.lower() in text.lower() for k in keys)
            self.add("README 段落: %s" % label, "有" if hit else "缺", hit, must=False)

        if self.args.metrics and Path(self.args.metrics).exists():
            metrics_text = Path(self.args.metrics).read_text(encoding="utf-8", errors="replace")
            nums = set(FLOAT_RE.findall(text))
            unmatched = [n for n in nums if n not in metrics_text]
            self.add("README 数字可溯源", "未在 metrics 中: %s" % unmatched[:5] if unmatched else "全部命中",
                     not unmatched)

    def check_log(self):
        log = None
        cand = Path(self.args.log) if self.args.log else None
        if cand and cand.exists():
            log = cand
        else:
            for p in self.sub.rglob("*.log"):
                log = p
                break
        if not log:
            self.add("train.log 存在", "缺失", False)
            return
        text = log.read_text(encoding="utf-8", errors="replace")
        self.add("train.log 存在", "%.1f KB" % (log.stat().st_size / 1024), True)
        self.add("日志有结束标记", "[DONE]/[FATAL]/结束 | 见下",
                 ("[DONE]" in text) or self.args.allow_no_done, must=False)
        self.add("日志无 FATAL", "有 FATAL，需在 README 说明" if "[FATAL]" in text else "ok",
                 "[FATAL]" not in text)
        self.add("日志无 ANSI 转义", "有" if ANSI_RE.search(text) else "ok",
                 not ANSI_RE.search(text), must=False)
        self.add("日志有实质内容", "%.1f KB" % (log.stat().st_size / 1024),
                 log.stat().st_size > 200, must=False)

    def check_code(self):
        pys = sorted(self.sub.rglob("*.py"))
        self.add("有代码文件", "%d 个 .py" % len(pys), bool(pys))
        if not pys:
            return
        mods = set()
        for p in pys:
            for m in IMPORT_RE.findall(p.read_text(encoding="utf-8", errors="replace")):
                name = (m[0] or m[1]).split(".")[0]
                if name:
                    mods.add(name)
        import importlib.util
        missing = sorted(m for m in mods
                         if importlib.util.find_spec(m) is None
                         and m not in ("__future__",))
        self.add("依赖可导入", "缺 %s" % missing if missing else "%d 个模块全部可导入" % len(mods),
                 not missing)

        no_smoke = [p.name for p in pys if "smoke" not in p.read_text(encoding="utf-8", errors="replace")]
        self.add("代码含 smoke 模式", "缺: %s" % no_smoke[:3] if no_smoke else "ok", not no_smoke, must=False)

    def check_metrics(self):
        if not self.args.metrics:
            return
        mp = Path(self.args.metrics)
        if not mp.exists():
            self.add("metrics.json 存在", mp, False)
            return
        try:
            data = json.loads(mp.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            self.add("metrics.json 可解析", str(exc), False)
            return
        self.add("metrics.json 可解析", "keys=%s" % ",".join(sorted(data)[:6]), True)
        self.add("metrics 有数值", "value=%s" % data.get("value"), data.get("value") is not None)
        self.add("metrics 有评测命令", data.get("eval_cmd", "缺失"), bool(data.get("eval_cmd")), must=False)

    # -- 汇总 ---------------------------------------------------------------
    def run(self):
        if not self.sub.exists():
            print("× 提交目录不存在: %s" % self.sub)
            return 2
        self.check_structure()
        self.check_files()
        self.check_readme()
        self.check_log()
        self.check_code()
        self.check_metrics()

        print("\n" + "=" * 78)
        print("QA 验收报告  %s" % self.sub.resolve())
        print("=" * 78)
        print("%-30s %-34s %-4s" % ("检查项", "详情", "结果"))
        print("-" * 78)
        fails = []
        for r in self.rows:
            flag = "PASS" if r["ok"] else ("FAIL" if r["must"] else "WARN")
            if not r["ok"]:
                (fails if r["must"] else []).append(r)
                if not r["must"]:
                    fails_soft = True  # noqa: F841
            print("%-30s %-34s %-4s" % (r["item"][:28], r["detail"][:32], flag))
        print("-" * 78)
        must_fail = [r for r in self.rows if not r["ok"] and r["must"]]
        soft = [r for r in self.rows if not r["ok"] and not r["must"]]
        print("必修项 %d/%d 通过；建议项 %d 条未过"
              % (len([r for r in self.rows if r["must"]]) - len(must_fail),
                 len([r for r in self.rows if r["must"]]), len(soft)))
        if must_fail:
            print("\n必修项修复清单（按影响排序）：")
            for i, r in enumerate(must_fail, 1):
                print("  %d. %s —— %s" % (i, r["item"], r["detail"]))
        print("\nQA_RESULT: %s" % ("PASS" if not must_fail else "FAIL"))
        print("=" * 78 + "\n")
        return 0 if not must_fail else 1


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission", required=True)
    ap.add_argument("--require", default="", help="逗号分隔的必需文件（相对提交目录）")
    ap.add_argument("--expect-count", type=int, default=0)
    ap.add_argument("--metrics", default="")
    ap.add_argument("--log", default="")
    ap.add_argument("--allow-no-done", action="store_true")
    args = ap.parse_args(argv)
    return Checker(args).run()


if __name__ == "__main__":
    sys.exit(main())
