# CHANGELOG

## v0.3 · 2026-11-15

架构升级（都能用 `python3 tools/selftest.py` 验）：

- **检索工具循环**：侦察兵不再只靠模型记忆。新增 `tools/netsearch.py`（零依赖，SearXNG / DuckDuckGo，无 key，失败自动降级），编排器 `g1` 支持 `<search>` / `<fetch>` 往返最多 2 轮，检索记录落 `runs/50_logs/tool_calls.log`。`--no-search` 可强制离线。
- **指标确定性抽取（g3b）**：新增第 10 个阶段，**不调模型**，从日志里正则抽 `[EVAL]`/`[DONE]` 得到 `60_metrics.json`（带 `derived_by` 与代码 hash），并顺手跑 `qa_check.py` 做交付预检。指标不再是模型自述。
- **JSON 产物校验 + 一次自动修补**：`g0` / `g2c` 的 JSON 必须有必填字段，缺了自动发一轮修补，仍缺就落盘标记。
- **预算与容错**：`--max-calls` 调用上限、`--fallback-model` 主模型失败自动切换、单阶段异常不中断全局（写 `BLOCKED.md` 后降级继续）。
- **离线自检 29 项**：`tools/selftest.py` 起 mock 端点跑完整 10 阶段，覆盖门控、工具循环、指标抽取、幂等续跑、D1 降级、max_calls。
- **CI 模板**：`ci/github-actions-selftest.yml`（Python 3.9/3.11/3.12 跑自检 + 校验 `PROMPTS.md` 一致）。复制到 `.github/workflows/` 即启用；未启用也可用 `make selftest`。
- **Makefile**：`make selftest / dry / smoke / prompts / search / push`。

新增提示词：

- **P16 多题调度**：一场考试 4 道题时的排序公式、时间表、**放弃清单**、并发纪律。
- **P7.5 泄漏审计**：八项红线自查（目标泄漏 / 目标编码未折外 / 全量 fit / 重复跨划分 / 时序切分 / 测试集参与训练 / ID 特征 / 口径错位）。

## v0.2 · 2026-11-15

- 扩充材料样本到 42 份（1 份真实实训题 + 4 套实训量规 + 3 份黑客松手册 + 34 份真题）。
- 新增 `P13.5 量规自评`（六维 100 分 + 三条红线）、`examples/task-05-controlled.md`、`docs/02-materials.md`。

## v0.1 · 2026-11-15

- 首版：23 条提示词、9 阶段编排器、4 个工具、5 个题型模板，推送 GitHub。
