# {题目名}

## 1. 任务理解

一句话：给定 `{输入}`，预测 `{输出}`，评价指标为 `{指标}`（{方向}），提交 `{文件名}`。

- 数据规模：训练 `{}` / 验证 `{}` / 测试 `{}`
- 硬约束：单卡 A100 80GB、总时长 {} 小时、{是否允许预训练权重}

## 2. 方法

- **骨架**：{backbone / 模型}，来自 {来源：已有权重 / 自己实现}
- **训练**：{loss}、{优化器}、lr={}、batch={}、epochs={}，{混合精度/梯度裁剪}
- **关键改动 1**：{做了什么} —— 因为 {为什么}
- **关键改动 2**：{做了什么} —— 因为 {为什么}
- **后处理**：{阈值搜索 / TTA / 规则修正}

## 3. 复现命令

```bash
# 0) 环境自检（60 秒内应输出 SMOKE_OK）
python3 train.py --mode smoke --config config.json

# 1) 训练
python3 train.py --mode train --config config.json | tee runs/50_logs/main.log

# 2) 评测（产生 runs/60_metrics.json）
python3 train.py --mode eval --ckpt runs/70_ckpt/best.pt

# 3) 生成提交文件
python3 train.py --mode predict --ckpt runs/70_ckpt/best.pt --out test_result.json
```

## 4. 结果

| 配置 | 指标 | 训练耗时 | 备注 |
|---|---|---|---|
| baseline（{最简方法}） | {} | {} min | 第一次跑通 |
| + {改动1} | {} | {} min | |
| + {改动2}（最终） | {} | {} min | 提交版本 |

> 上表每个数字都能在 `runs/60_metrics.json` 与 `runs/50_logs/main.log` 中检索到。

## 5. 失败与取舍

| 尝试 | 结果 | 结论 |
|---|---|---|
| {改动A} | 指标下降 {} | 已回滚，原因：{} |
| {改动B} | 训练 OOM | 改为 {}  后可用 |
| {改动C} | 无显著变化 | 放弃，收益不抵时间成本 |

## 6. 未完成与后续

- 未完成：{例如 未做多 seed 集成 / 未调后处理阈值}
- 若有更多时间：先做 {}（预计 +{}），再做 {}（预计 +{}）
- 已知局限：{例如 验证集仅 {} 条，指标波动约 ±{}}
