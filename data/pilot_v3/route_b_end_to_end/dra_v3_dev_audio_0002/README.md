# Route B 端到端 Pilot

任务：`dra_v3_dev_audio_0002`

本 pilot 使用真实冻结 case、证据 graph、content-addressed blobs、corpus registry、public task 和 protocol manifest，显式选择 `proof_steps_v1` 运行 `score_case_v3.py`。

## Proof DAG

```text
E1-E10  冻结证据步骤
  ↓
B1-B4   跨证据桥接步骤
  ↓
D1      最终选择
```

完整逐步标注见 `ANNOTATION.md` 和 `proof_step_annotation.json`。

## 重放结果

| 场景 | 通过步骤 | Partial Completion | Full Pass | 说明 |
|---|---:|---:|---:|---|
| positive | 15/15 | 1.000 | 1 | 证据、桥接、决策和引用全部通过 |
| partial | 10/15 | 0.667 | 0 | 只列证据，缺少 B1-B4 与 D1 |
| fabricated | 15/15 | 1.000 | 0 | 步骤全部完成，但包含一个伪造 URL |

这验证了两个头条指标的分工：Partial Completion 保留已完成步骤；Full Pass 对完整闭环和引用完整性执行硬门槛。

## 重放命令

```bash
python3 scripts/run_route_b_audio_0002_pilot.py
```

回归测试：

```bash
pytest -q tests/test_route_b_audio_0002_pilot.py
```

## 尚未完成

- 该标注是 `ai_pilot_review`，不是独立人工 gold。
- 既有 case 的大多数证据步骤只列出一个冻结 source ID；需要在存在等价证据时补充替代 source IDs。
- 当前只跑通一个 case，尚未形成 6 个 development cases 的批量面板。
