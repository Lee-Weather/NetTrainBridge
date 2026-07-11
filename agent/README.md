# NetTrainBridge Agent（0.2）

公司训练机进程：轮询云 Server、抢占任务、clone 代码、训练 / sync / 真实 sim2sim。

架构见根 [README.md](../README.md)；验收见 [docs/acceptance.md](../docs/acceptance.md)。

## 启动

```bash
conda activate F1
cd agent
pip install -r requirements.txt   # 首次
python agent.py
```

配置（`~/.nettrainbridge/config.json` 的 `agent` 段）：

```bash
cp ../nettrainbridge_common/config.example.json ~/.nettrainbridge/config.json
```

| 键 | 说明 |
|:---|:---|
| `server_url` | 云 Server |
| `proxy` | 公司出网代理（访问 Server / GitHub） |
| `agent_id` | 如 `agent-001` |
| `workspace` | 任务目录根，如 `~/czy/nettrainbridge` |
| `conda_env` | 含 Isaac 的环境，如 `F1` |
| `train_command` | 兜底训练命令模板 |
| `gm_api_key` / `gm_base_url` | **仅** `--fetch-from-gm` 兜底需要；默认 gm test **不需要** |

启动时会：

1. **与 Server 对齐 workspace**（清理云上已删除的本地 job 目录）
2. 尝试恢复中断任务
3. 每 `poll_interval` 秒轮询；空闲打印「轮询中，无待处理任务」

关闭对齐：`export NETTRAINBRIDGE_WORKSPACE_ALIGN=0`。

## 任务行为

| `job_type` | 行为 |
|:---|:---|
| `train` | clone → `train_command` → 上报 metrics/logs → 上传 checkpoint |
| `sync` | 仅 clone/checkout |
| `test` | sync → **pull**（gm 默认从本 job Server 取模）或 **fetch**（`--fetch-from-gm`）→ `test_with_metrics.py` → `play.py` |

gm 默认落盘：

```text
{workspace}/{job_id}/logs/{task}/exported_data/{load_run}/model_{N}.pt
```

test **成功**后：

- 流式上报 metrics（`ntb metrics` 可见）
- 上传最新 `test/isaac_diag_*.csv` 到 Server（`ntb artifacts`）
- **不**再上传 `summary.json` / `metrics.jsonl` 到 artifacts

## 环境变量（Agent 注入给训练/测试脚本）

| 变量 | 用途 |
|:---|:---|
| `NETTRAINBRIDGE_METRICS_FILE` | metrics.jsonl 路径 |
| `NETTRAINBRIDGE_JOB_ID` | 任务 ID |
| `NETTRAINBRIDGE_TEST_OUTPUT_DIR` | play CSV 目录 → `{job}/test/` |
| `NETTRAINBRIDGE_PLAY_RENDER` | 固定 `0`（不录屏） |
| `NETTRAINBRIDGE_PLAY_LOG_CSV` | `1` |
| `NETTRAINBRIDGE_LOAD_RUN` / `CHECKPOINT` | test 参数 |

训练仓须含 `test_with_metrics.py`，且 `play.py` 支持上述 env（见 [contrib/agi_origin/README.md](../contrib/agi_origin/README.md)）。

## 模块结构

```text
agent/
├── agent.py              # 主循环、claim、phase、对齐 workspace
├── job_runner.py         # clone / conda run / train & test 子进程
├── pull_runner.py        # 从 Server 拉 checkpoint 到 logs 布局
├── fetch_runner.py       # --fetch-from-gm 兜底
├── gm_client.py          # gm API（仅兜底）
├── api_client.py / config.py / heartbeat.py …
└── scripts/gm_probe.py   # 调试 gm / OSS
```

## 相关文档

| 文档 | 内容 |
|:---|:---|
| [../README.md](../README.md) | 总览 |
| [../server/README.md](../server/README.md) | Server API |
| [../cli/README.md](../cli/README.md) | 家里 ntb |
| [../docs/checkpoint-hub.md](../docs/checkpoint-hub.md) | stage → pull |
| [../docs/acceptance.md](../docs/acceptance.md) | 验收 |
