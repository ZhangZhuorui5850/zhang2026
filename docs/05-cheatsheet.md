# 05 · 一页纸速查卡（建议打印）

```
════════════════════════════════════════════════════════════════
 科研实训 · 8 小时速查                       打印出来，贴在手边
════════════════════════════════════════════════════════════════

【T+0 开场 60 秒】
  whoami; hostname; nvidia-smi; python3 -V; nproc
  mkdir -p ~/work/runs/{10_cards,50_logs,70_ckpt,90_submission}; cd ~/work
  tmux new -s work
  ls /vepfs-readonly /vepfs

【四个硬节点】
  T+195  必须出 baseline（跑不通就砍模型/砍数据/砍改动）
  T+336  提分截止（只做 ROI 第一名的改动）
  T+384  必须先产出一个可提交版本（先有，再好）
  T+456  冻结：只准 ls / cat / json.load，不准 vim

【提示词顺序】
  开局   F3              → 反推评分点，分配时间
  任务   P1 + P1.5       → 00_task.md / 01_env.md
  情报   P2×5 + P3       → 10_cards/ + 10_brief.md
  方案   P4 + P5 + P6    → 25_decision.md（要有 DECISION 行）
  执行   P7 + P8 + P9    → 代码 + smoke + 主训（修错配额 3）
  冲刺   P10             → 一次一个变量，Δ≤0 回滚
  交付   P11 + P12 + P13 → 60_metrics.json + 90_submission/ + QA PASS
  收尾   P14             → 冻结 + 打包

【smoke 三件套】
  python3 train.py --mode smoke            → 必须 60 秒内 SMOKE_OK
  bash run.sh start main                   → tmux/nohup + 自检
  python3 monitor.py --log runs/50_logs/main.log --every 60

【六态判定】
  RUNNING 推进 | STALL 无新 step | DIVERGE nan/loss 回升
  OOM 显存 | DEAD [FATAL] | DONE 完成
  OOM   → batch 减半，别的都别动
  STALL → num_workers=0 复测
  DIVERGE → lr ×0.3 或回滚 best

【显存不够的降级顺序】
  batch 减半 → max_len 减半 → 开 bf16 → 梯度累积 → 冻 backbone 前 N 层

【提分优先级（低风险→高风险）】
  1 确认评测口径/split 没搞错   2 开 TTA        3 后处理阈值搜索
  4 多 seed 平均            5 类别权重/重采样  6 换 backbone

【交付前 8 条（qa_check.py 会查）】
  □ 题面要求的文件名逐字一致（大小写！）
  □ python -c "import json;json.load(open('x'))" 通过
  □ 条数 == 测试集样本数
  □ README 六段：任务/方法/复现命令/结果/失败取舍/未完成
  □ README 里每个数字都能在 metrics.json 里 grep 到
  □ 无 /Users /home 绝对路径；无 __pycache__
  □ train.log 有 [DONE] 或结束标记，无 ANSI 转义
  □ 从提交目录跑一次 --mode smoke 能过

【一句话原则】
  交一个 0.6 的完整包  >  交一个 0.85 的半成品
  一次只改一个变量    >  同时改三处然后"好像好了"
  先跑通再优化        >  先想清楚再动手（想清楚的样子叫 smoke）
════════════════════════════════════════════════════════════════
```
