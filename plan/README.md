# NetTrainBridge 设计与开发规划

> 阶段一至三已完成。云服务器纯 API + 训练机 Agent + 家里 `ntb` CLI，无 Web GUI。

操作手册见仓库根 [README.md](../README.md)。

---

## 1. 架构

```
家里 (git push + ntb watch)
        │ HTTP
        ▼
云服务器 FastAPI :8000  ←── GitHub Webhook (push)
(SQLite + 磁盘)
        ▲
        │ HTTP + 公司代理
训练机 Agent (conda F1) → train_with_metrics.py
```

| 组件 | 位置 | 职责 |
|:---|:---|:---|
| **CLI (`ntb`)** | 家里电脑 | 查任务、看指标/日志/GPU |
| **Server** | 公网云 | 任务调度、存指标、收模型、Webhook |
| **Agent** | 公司 GPU 机 | 抢任务、clone、训练、上报 |
| **GitHub** | 公网 | 代码托管，push 触发任务 |

**原则**：云服务器只做 API；`git push` 即触发；内网机器只出站连接，无需开入站端口。

---

## 2. 任务生命周期

```
PENDING → ASSIGNED → RUNNING → COMPLETED / FAILED
```

1. 家里 `git push` → GitHub Webhook → 云服务器创建 `PENDING` 任务  
2. Agent 轮询 `GET /jobs/pending`，`PUT /jobs/{id}/claim` 抢占  
3. `git clone` + checkout → `train_with_metrics.py`（Agent 注入 `METRICS_FILE`）  
4. 并行上报：日志 `POST /logs`、指标 `POST /metrics`、GPU `POST /heartbeat`  
5. 家里 `ntb watch <id>` 看曲线；结束后 `wget` 下载 checkpoint  

---

## 3. 三端部署

| 端 | conda | 安装 | `pip install -e .`？ |
|:---|:---|:---|:---|
| 云服务器 | `nettrain` | `server/requirements.txt` | 否 |
| 训练机 | `F1` | `agent/requirements.txt` | 否 |
| 家里 CLI | 任意 3.8+ | 仓库根 `pip install -e ".[dev]"` | 是 |

配置：`~/.nettrainbridge/config.json`（模板 `config.example.json`）。

详细启动步骤见根 [README.md](../README.md#启动)。

---

## 4. 存储策略

| 数据 | 位置 | 说明 |
|:---|:---|:---|
| 任务元数据、指标 | 云 SQLite | 任务状态、loss/reward |
| 实时日志 | 云内存缓存 | 最近 5000 行，重启丢失 |
| 模型 checkpoint | 云磁盘 `data/{job_id}/` | 训练结束上传 |
| 中间 checkpoint | 训练机本地 | Agent 不上传，用于断点续训 |
| 训练代码 | GitHub | 版本管理 |

---

## 5. 网络

| 源 | 目标 | 方式 |
|:---|:---|:---|
| 家里 | 云服务器 | HTTP 直连 |
| 训练机 | 云服务器 | HTTP，经代理 `10.12.201.122:39000` |
| 训练机 | GitHub | git，经代理 |
| GitHub | 云服务器 | Webhook |

---

## 6. 开发阶段（已完成）

```
阶段 1  云服务器 API     ✅
阶段 2  Agent 基础版     ✅
阶段 3  训练流 + CLI     ✅
```

### 阶段 1：云服务器 API

- FastAPI + SQLite：`jobs` / `metrics` / `heartbeats`
- 路由：任务 CRUD、抢占、Webhook、日志、指标、checkpoint、心跳
- 验收：`bash server/test_e2e.sh`

### 阶段 2：Agent

- `agent.py` 主循环：轮询 → 抢占 → `job_runner` clone/安装/启动
- `api_client.py` HTTP 封装；`conda run -n F1` 执行训练
- 验收：Agent 能抢任务、起子进程、上报心跳

### 阶段 3：完整训练流 + CLI

- `contrib/.../train_with_metrics.py` → agi_origin 指标桥接
- Agent 注入 `NETTRAINBRIDGE_METRICS_FILE` / `GRADMOTION_METRICS_FILE`（`conda run -e`）
- 删除 `server/static/`，`GET /` 返回 JSON API 说明
- `cli/ntb`：`health` / `jobs` / `watch` / `logs -f` / `metrics` / `config`
- 验收：`bash server/test_phase3.sh` + `bash server/test_cli.sh`；端到端 `git push` → `ntb watch`

### 去 GUI 化（并入阶段 3）

| 决策 | 选择 |
|:---|:---|
| 监控方式 | `ntb watch` 替代浏览器 Dashboard |
| 云服务器 | 纯 API，无 static |
| SSE | 保留，`ntb logs -f` 消费 |
| 品牌 | NetTrainBridge；`GRADMOTION_*` 环境变量仅代码内兼容 |

---

## 7. 数据库

```sql
CREATE TABLE jobs (
    id          TEXT PRIMARY KEY,
    status      TEXT DEFAULT 'PENDING',
    repo_url    TEXT NOT NULL,
    commit_sha  TEXT NOT NULL,
    agent_id    TEXT,
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    start_time  DATETIME,
    end_time    DATETIME,
    error_msg   TEXT
);

CREATE TABLE metrics (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id    TEXT NOT NULL,
    step      INTEGER NOT NULL,
    loss      REAL,
    reward    REAL,
    lr        REAL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE TABLE heartbeats (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        TEXT NOT NULL,
    agent_id      TEXT NOT NULL,
    gpu_util      REAL,
    gpu_mem_used  REAL,
    gpu_mem_total REAL,
    timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);
```

---

## 8. 配置与环境变量

配置文件段落：`server` / `agent` / `cli`。

| 旧名（兼容） | 新名 |
|:---|:---|
| `GRADMOTION_SERVER_URL` | `NETTRAINBRIDGE_SERVER_URL` |
| `GRADMOTION_PROXY` | `NETTRAINBRIDGE_PROXY` |
| `GRADMOTION_METRICS_FILE` | `NETTRAINBRIDGE_METRICS_FILE` |
| `GRADMOTION_*` | `NETTRAINBRIDGE_*` |

CLI 可选 `api_token` / `NETTRAINBRIDGE_API_TOKEN`（Bearer Header，服务端待统一鉴权）。

---

## 9. 验收清单

| # | 检查项 |
|:---|:---|
| 1 | `server/static/` 不存在 |
| 2 | `curl /static/dashboard.html` → 404 |
| 3 | Agent 上报 metrics/logs 可查 |
| 4 | `ntb watch` 指标增量更新 |
| 5 | `ntb logs -f` SSE 正常 |
| 6 | `test_phase3.sh` + `test_cli.sh` 全绿 |
| 7 | 端到端：`git push` → 训练 → `COMPLETED` |

---

## 10. 仓库结构（当前）

```
NetTrainBridge/
├── server/                 # 云 API
├── agent/                  # 训练机 Agent
├── cli/nettrainbridge_cli/ # ntb 客户端
├── nettrainbridge_common/  # 共享配置
├── contrib/agi_origin/     # train_with_metrics 源
├── config.example.json
├── pyproject.toml          # 仅家里 CLI：pip install -e ".[dev]"
└── plan/README.md          # 本文件
```

---

## 11. 成本

| 项目 | 月成本 |
|:---|:---|
| 云服务器 2C2G | ≈ 50 元 |
| 训练机 GPU | 0（已有） |
| GitHub | 0 |
