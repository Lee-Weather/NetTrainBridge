# sim2sim 实现分阶段说明

> 总规划见 [plan02-gm-ntb-framework.md](plan02-gm-ntb-framework.md)、[plan02-implementation.md](plan02-implementation.md)。

---

## 策略：先 Mock 框架，后真实实现

| 阶段 | 计划步骤 | 内容 | 状态 |
|:---|:---|:---|:---|
| **框架 + Mock** | 步骤 7 | `test_with_metrics.py` 占位脚本（`--mock` / `--self-test`） | 脚本骨架已建 |
| **链路打通** | 步骤 8 | Agent `test_command` 调 Mock；`ntb test run` 端到端 | 待做 |
| **真实 sim2sim** | **R1（后续）** | `run_real_sim2sim()` 对接 `play.py` / Isaac | **刻意延后** |

**原则**：步骤 5～8 只验证「test job → fetch 模型 → 跑脚本 → 上报 metrics/logs/产物」，**不要求仿真环境可跑**。

---

## 占位脚本

路径：`contrib/agi_origin/humanoid/scripts/test_with_metrics.py`

```
test_with_metrics.py
├── run_mock_sim2sim()      ← 步骤 7～8 使用（写假 metrics + summary.json）
├── run_real_sim2sim()      ← R1 实现（当前 NotImplementedError）
└── main()                  ← --mock | --self-test | （未来）真实参数
```

### 本地验证 Mock

```bash
python contrib/agi_origin/humanoid/scripts/test_with_metrics.py --self-test

export NETTRAINBRIDGE_METRICS_FILE=/tmp/test_metrics.jsonl
export NETTRAINBRIDGE_JOB_ID=local-mock
touch /tmp/model.pt
python contrib/agi_origin/humanoid/scripts/test_with_metrics.py \
  --mock --checkpoint /tmp/model.pt
```

### Agent 配置（步骤 8 暂定）

```json
"test_command": "python humanoid/scripts/test_with_metrics.py --mock --task=x1_dh_stand --checkpoint={checkpoint_path} --headless"
```

环境变量（Agent 注入，与训练对齐）：

| 变量 | 用途 |
|:---|:---|
| `NETTRAINBRIDGE_CHECKPOINT_PATH` | 模型路径 |
| `NETTRAINBRIDGE_METRICS_FILE` | 测试 metrics.jsonl |
| `NETTRAINBRIDGE_JOB_ID` | 任务 ID |

---

## R1：真实 sim2sim 待办（现在不写）

1. 调研 agi_origin `play.py` 参数与 stdout 格式  
2. 在 `run_real_sim2sim()` 内 subprocess 包装 play，或 import 调用  
3. 解析测试指标字段（reward、success_rate、episode_length 等）  
4. 与 gm / ntb 训练 checkpoint 加载路径对齐  
5. 环境一致性：gm 镜像 vs 训练机 conda Isaac 版本  
6. 可选：录屏 / 轨迹文件上传 Server `data/{id}/test/`  
7. 将 `test_command` 从 `--mock` 改为真实参数；保留 `--mock` 供 CI  

---

## 与实现步骤的对应

```text
步骤 5   test job + Server 目录        （无脚本）
步骤 6   gm FETCH                      （无脚本）
步骤 7   test_with_metrics.py 框架     ← Mock 脚本 ✅
步骤 8   ntb test run + Agent TEST     ← 调 Mock 脚本
R1       run_real_sim2sim()            ← 真实 sim2sim（后续）
```

---

## 验收口径（步骤 7～8）

| 项 | Mock 阶段要求 |
|:---|:---|
| 产出 metrics.jsonl | ✅ 含 `kind: test`, `mock: true` |
| 产出 test/summary.json | ✅ |
| 真实 Isaac 仿真 | ❌ 不要求 |
| 指标有业务意义 | ❌ 仅占位数值 |

R1 完成后另行更新验收清单。
