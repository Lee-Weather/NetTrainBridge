# NetTrainBridge Server（0.2）

云端 FastAPI：任务调度、指标/日志、checkpoint 中转、test 产物（`isaac_diag_*.csv`）。

完整架构见根 [README.md](../README.md)；gm test 中转见 [docs/checkpoint-hub.md](../docs/checkpoint-hub.md)。

## 快速启动

```bash
conda activate nettrain
cd server
pip install -r requirements.txt
python main.py
# http://0.0.0.0:8000  ·  /docs  ·  /health
```

配置：

```bash
cp ../nettrainbridge_common/config.example.json ~/.nettrainbridge/config.json
# 编辑 server 段：host / port / allowed_repos / webhook_secret
```

或家里：`ntb config init --server-url http://<云IP>:8000`。

## 任务类型与 phase

| `job_type` | 说明 | 典型 phase |
|:---|:---|:---|
| `train` | 兜底训练 | （无 phase 或训练流程） |
| `sync` | 仅同步代码 | — |
| `test` | sim2sim | gm 默认：`sync → pull → test → done`；兜底：`sync → fetch → test → done`；ntb：`sync → test → done` |

状态机：`PENDING → ASSIGNED → RUNNING → COMPLETED / FAILED`。

## 数据目录

```text
data/{job_id}/
├── meta.json          # load_run、checkpoint、fetch_mode、checkpoint_staged…
├── models/            # checkpoint（.pt）；gm test 由家里 stage 上传
└── test/              # 正式产物：isaac_diag_*.csv（Agent 上传）
```

流式指标在 SQLite（`ntb metrics`），**不**再把 `summary.json` / `metrics.jsonl` 作为 artifacts 主产物。

## 主要 API（摘要）

| 前缀 | 用途 |
|:---|:---|
| `/jobs` | CRUD、pending、claim、status、phase、清空 |
| `/jobs/{id}/meta` | 读写 meta.json |
| `/jobs/{id}/checkpoint` | 模型分片上传 / 列表 / 下载 |
| `/jobs/{id}/metrics` | 训练/测试指标 |
| `/jobs/{id}/logs` | 日志 + SSE |
| `/jobs/{id}/heartbeat` | GPU 心跳 |
| `/jobs/{id}/test/{filename}` | Agent 上传 test 文件（如 CSV） |
| `/jobs/{id}/artifacts` | 列出 / zip 下载 `test/` |
| `/webhook/github` | 可选 push 建任务 |

创建 test job 示例字段：`job_type=test`、`gm_task_id` 或 `parent_train_job_id`、`load_run`、`checkpoint`、`fetch_mode`、`checkpoint_staged`。

家里日常请用 `ntb`，不必手写 curl。详见 [cli/README.md](../cli/README.md)。

## 配置项（`server` 段）

| 键 | 环境变量 | 说明 |
|:---|:---|:---|
| `host` | `NETTRAINBRIDGE_HOST` | 默认 `0.0.0.0` |
| `port` | `NETTRAINBRIDGE_PORT` | 默认 `8000` |
| `db_path` | `NETTRAINBRIDGE_DB_PATH` | 默认 `data/server.db` |
| `data_dir` | `NETTRAINBRIDGE_DATA_DIR` | 默认 `data` |
| `webhook_secret` | `NETTRAINBRIDGE_WEBHOOK_SECRET` | 可选 |
| `allowed_repos` | `NETTRAINBRIDGE_ALLOWED_REPOS` | Webhook 白名单 |

优先级：环境变量 > 配置文件 > 默认值。

## 项目结构

```text
server/
├── main.py
├── config.py / database.py / models.py / job_data.py
├── api/
│   ├── jobs.py / webhook.py / logs.py / metrics.py
│   ├── heartbeat.py / checkpoint.py / meta.py
│   ├── test_files.py / artifacts.py
├── test_*.sh / test_v02_*.sh
└── data/                 # 运行时（gitignore）
```

## 测试

```bash
bash test_cli.sh http://localhost:8000
bash test_v02_artifacts.sh http://localhost:8000   # checkpoint + CSV artifacts
bash test_phase3.sh http://localhost:8000
```

## 相关文档

| 文档 | 内容 |
|:---|:---|
| [../README.md](../README.md) | 总览与三端启动 |
| [../agent/README.md](../agent/README.md) | 训练机 Agent |
| [../cli/README.md](../cli/README.md) | 家里 ntb |
| [../docs/checkpoint-hub.md](../docs/checkpoint-hub.md) | checkpoint 中转 |
| [../docs/acceptance.md](../docs/acceptance.md) | 验收清单 |
