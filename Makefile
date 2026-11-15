# zhang2026 · 常用操作（make 不在也没关系，命令本身都在 README 里）
.PHONY: help selftest dry smoke prompts search push clean

help:
	@echo "make selftest  # 离线自检：29 项，验证流水线在你机器上可跑"
	@echo "make dry       # 看 10 阶段执行计划，不联网"
	@echo "make smoke     # 训练骨架 30 秒自检"
	@echo "make prompts   # 由 prompts/ 重建 PROMPTS.md"
	@echo "make search Q=\"关键词\"  # 命令行检索"
	@echo "make push      # 推送（需 GITHUB_TOKEN）"

selftest:
	@python3 tools/selftest.py

dry:
	@python3 tools/orchestrator-mars.py --dry-run

smoke:
	@cd tools && python3 train_template.py --mode smoke

prompts:
	@python3 tools/build_prompts.py

search:
	@python3 tools/netsearch.py "$(Q)"

push:
	@bash scripts/push.sh

clean:
	@rm -rf runs __pycache__ tools/__pycache__ && echo "已清理 runs/ 与缓存"
