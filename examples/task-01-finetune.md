# 题型一 · 预训练模型微调（虚构示例，仅示意题面风格）

> ⚠️ 本文件是**虚构的**，用于展示这类题面的**结构与密度**。真实题目完全不同，不要套用任何具体数字或路径。
> 所有 `<>` 都是占位符，考场按实际题面替换。

---

## 题目：<某生物序列性质> 预测

### 题目背景与目标

给定一个已经训练好的 <预训练模型名> 模型 checkpoint，目标是在此基础上构建 <目标性质> 预测的完整微调流程。
该任务要求理解 <领域> 与工程背景，设计合理的输入输出形式与损失函数，并通过标准评测指标在提供的测试集上达到稳定且可复现的性能。

<一句话讲清这个性质为什么重要、和下游什么任务相关>。
模型输入为 <原始模态，如氨基酸序列 / SMILES / 文本>，输出为 <标签形式，如二分类 / 回归值>。

### 数据集加载

数据集已事先准备并划分完毕，提供标准化接口：

```python
from <dataset_module> import <DatasetClass>
ds_train, ds_valid, ds_test = <DatasetClass>.load(<数据路径>)
```

每个样本包含 `<字段1>` 与对应 `<标签字段>`，划分为 `training / valid / test`。
`<数据路径>` 为 LMDB / parquet / jsonl，**只读**。

### 模型与特征提取

<模型名> 基于 Transformer，可从 `<checkpoint 路径>` 加载提供的权重，并通过自带的 `<alphabet / tokenizer>` 获得分词器与批转换器：

```python
import torch
from pathlib import Path
data = torch.load(<ckpt_path>, map_location='cpu')
model, alphabet = <load_fn>(Path(<ckpt_path>).stem, data, None)
batch_converter = alphabet.get_batch_converter()
```

`token_representations` 形状为 `[batch, seq_len, hidden]`，通常做 **mean-pool** 或取 **[CLS]** 得到全局表示，再输入轻量分类/回归头。

### 模型与微调设置要求

1. 输入层：沿用 <模型> 的 tokenizer/embedding；**禁止改动词表**。
2. 表征汇聚（二选一，需在报告中说明并固定）：`[CLS]` 向量 / mean-pool。
3. 微调策略（二选一）：全参微调 / 冻结主干前 N 层只训头部。
4. 损失函数与输出形式需与任务匹配，并在 README 中说明理由。
5. 必须固定随机种子，保证**同一 checkpoint 评测两次结果一致**。

### 提交内容（逐字对齐，大小写敏感）

| 文件 | 内容 |
|---|---|
| `test_result.json` | `{"predictions": [...]}`，条数 = 测试集样本数，顺序与测试集一致 |
| `README.md` | 任务理解 / 方法 / 复现命令 / 结果表 / 失败与取舍 / 未完成 |
| `代码` | 能 `--mode smoke` 一键验证 |
| `train.log` | 完整训练日志，含超参与最终指标 |

提交到 `<专属目录>`。

### 评分

主指标 **Accuracy**（越大越好）。同分时看：可复现性 → README 质量 → 消融完整性。

---

## 这一题型该走哪条线

| 步骤 | 做法 | 提示词 |
|---|---|---|
| 情报 | 必查：该模型的标准微调姿势、pooling 对指标的影响、该数据集有没有已知泄漏 | P2 (METHOD/DATA) |
| 方案 | SAFE = 冻结主干 + 头部 + 1 epoch；SOTA = 全参 + cosine + 分层 lr；GREEDY = 阈值搜索 + 多 seed | P4 |
| 执行 | 先 `max_len` 砍到 256 跑通，再放大 | P7 / 骨架 |
| 提分顺序 | 早停选点 → 长度分桶分析 → 冻结层数搜索 → 多 seed 平均 | P10 |

## 这类题的五个坑

1. **显存**：`batch=16 × max_len=512` 是起点；OOM 先减 batch，别改结构。
2. **`[CLS]` vs mean-pool 混用**：README 说一套代码做另一套，直接扣方法分。
3. **测试集顺序**：json 里必须按测试集原始顺序，不能按 dict 顺序。
4. **只读目录**：`<数据路径>` 只读，所有输出写 `runs/`。
5. **单轮训练很久**：先跑 1 epoch 拿到分数，再决定要不要加。
