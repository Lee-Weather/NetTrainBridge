# GradMotion 开发阶段规划

> 按依赖顺序分 4 个阶段，每个阶段有明确的交付物和验证标准。

---

## 总览

```
阶段 1          阶段 2            阶段 3              阶段 4
云服务器 API ──▶ Agent 基础版 ──▶ 完整训练流+Dashboard ──▶ 容错+安全
(1天)           (1-2天)           (2-3天)              (1-2天)
```

**核心原则**: 先写云服务器，再写 Agent。云服务器是中枢，Agent 依赖它。

---

## 阶段 1: 云服务器 API 基础

**为什么先写云服务器**: Agent 的所有请求都发往云服务器，没有 API 就无法开发 Agent。

### 1.1 项目初始化

```
server/
├── main.py              # FastAPI 入口 + 路由注册
├── config.py            # 配置 (端口、数据库路径、Token)
├── database.py          # SQLite 连接 + 表初始化
├── models.py            # Pydantic 数据模型
├── api/
│   ├── __init__.py
│   ├── jobs.py          # 任务 CRUD + 抢占
│   ├── webhook.py       # GitHub Webhook 接收
│   ├── logs.py          # 日志接收
│   ├── metrics.py       # 指标接收
│   └── checkpoint.py    # 模型上传接收
└── requirements.txt
```

### 1.2 开发顺序

| 步骤 | 文件 | 功能 | 代码量 |
|:---|:---|:---|:---|
| 1 | `database.py` | SQLite 连接，创建 jobs / metrics 表 | 30 行 |
| 2 | `models.py` | JobCreate, JobResponse, MetricCreate 等 Pydantic 模型 | 40 行 |
| 3 | `api/jobs.py` | `GET /jobs/pending`、`POST /jobs`、`PUT /jobs/{id}/claim`、`PUT /jobs/{id}/status` | 80 行 |
| 4 | `api/webhook.py` | `POST /webhook/github`，解析 push 事件自动创建任务 | 40 行 |
| 5 | `api/logs.py` | `POST /jobs/{id}/logs`，内存缓存最近 5000 行 | 30 行 |
| 6 | `api/metrics.py` | `POST /jobs/{id}/metrics`，写入 SQLite | 30 行 |
| 7 | `api/checkpoint.py` | `POST /jobs/{id}/checkpoint`，接收模型文件存本地磁盘 | 40 行 |
| 8 | `main.py` | FastAPI app，注册路由，启动时初始化数据库 | 30 行 |

### 1.3 数据库设计

```sql
-- 任务表
CREATE TABLE jobs (
    id          TEXT PRIMARY KEY,
    status      TEXT DEFAULT 'PENDING',  -- PENDING/ASSIGNED/RUNNING/COMPLETED/FAILED
    repo_url    TEXT NOT NULL,
    commit_sha  TEXT NOT NULL,
    agent_id    TEXT,                     -- 哪个 Agent 抢占的
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    start_time  DATETIME,
    end_time    DATETIME,
    error_msg   TEXT
);

-- 指标表
CREATE TABLE metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      TEXT NOT NULL,
    step        INTEGER NOT NULL,
    loss        REAL,
    reward      REAL,
    lr          REAL,
    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);
```

### 1.4 验证方式

```bash
# 启动服务器
cd server && uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 手动创建任务
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/test/repo", "commit_sha": "abc123"}'

# 查看待处理任务
curl http://localhost:8000/jobs/pending

# 抢占任务
curl -X PUT http://localhost:8000/jobs/1/claim

# 上报指标
curl -X POST http://localhost:8000/jobs/1/metrics \
  -H "Content-Type: application/json" \
  -d '[{"step": 100, "loss": 0.5}]'

# 上报日志
curl -X POST http://localhost:8000/jobs/1/logs \
  -H "Content-Type: application/json" \
  -d '{"content": "Epoch 1, Loss: 0.5"}'
```

---

## 阶段 2: Agent 基础版

**前提**: 阶段 1 的 API 已就绪并可访问。

### 2.1 项目结构

```
agent/
├── agent.py              # 主程序入口 (状态机循环)
├── config.py             # 配置 (云服务器地址、代理、轮询间隔)
├── job_runner.py         # 任务执行器 (clone + 启动训练)
├── api_client.py         # 云服务器 API 客户端 (封装所有 HTTP 请求)
└── requirements.txt
```

### 2.2 开发顺序

| 步骤 | 文件 | 功能 | 代码量 |
|:---|:---|:---|:---|
| 1 | `config.py` | AgentConfig dataclass，代理/服务器/路径配置 | 30 行 |
| 2 | `api_client.py` | 封装所有对云服务器的 HTTP 请求，含重试逻辑 | 80 行 |
| 3 | `job_runner.py` | git clone + checkout + pip install + 启动子进程 | 100 行 |
| 4 | `agent.py` | 主循环：轮询 → 抢占 → 执行 → 心跳 → 完成 | 120 行 |

### 2.3 验证方式

```bash
# 在公司训练机上启动 Agent
cd agent && python agent.py

# 观察日志输出
# [INFO] Agent 启动, 轮询间隔: 30s
# [INFO] 发现任务 1, 正在抢占...
# [INFO] 抢占成功, 开始 clone 代码...
# [INFO] 训练进程已启动, PID=12345
# [INFO] 心跳上报: GPU 85%, MEM 20GB/24GB
# [INFO] 训练完成, exit_code=0
```

---

## 阶段 3: 完整训练流 + Web Dashboard

**前提**: 阶段 2 的 Agent 能启动训练并上报心跳。

> 详细开发计划见 [phase3_dev_plan.md](phase3_dev_plan.md)

### 3.0 阶段二已具备（阶段三直接复用）

| 能力 | 状态 |
|:---|:---|
| `GET /jobs/{id}/metrics` 指标查询 | ✅ |
| Agent 日志/指标上报循环 | ✅ |
| GitHub Webhook 基础接收 | ✅ |
| 最小任务列表 `index.html` | ✅ |

### 3.1 云服务器新增

| 步骤 | 文件 | 功能 | 代码量 |
|:---|:---|:---|:---|
| 1 | `api/jobs.py` 补充 | `GET /jobs` 任务列表 API | 30 行 |
| 2 | `api/logs.py` 补充 | `GET /jobs/{id}/logs/stream` SSE 日志流 | 40 行 |
| 3 | `api/webhook.py` 加固 | 签名校验、去重、仓库白名单 | 30 行 |
| 4 | `static/dashboard.html` | ECharts 实时曲线 + 日志 + 心跳 | 250 行 |
| 5 | `static/index.html` 增强 | 跳转详情页、调用 `GET /jobs` | 20 行 |

### 3.2 示例与训练适配

| 步骤 | 文件 | 功能 | 代码量 |
|:---|:---|:---|:---|
| 1 | `contrib/agi_origin/.../train_with_metrics.py` | agi_origin 指标桥接脚本 | 200 行 |
| 2 | `agi_origin` 仓库 | `train_with_metrics.py` 指标输出适配 | 80 行 |

### 3.3 验证方式

```
1. git push → GitHub Webhook → 云服务器创建任务
2. Agent 自动拉取 → 执行 train_with_metrics.py（真实训练）
3. 浏览器打开 dashboard.html?id={job_id} → 看到实时 Loss 曲线
4. 训练结束 → 任务状态变为 COMPLETED
```

**检查点**: `bash server/test_phase3.sh http://云服务器IP:8000`

---

## 阶段 4: 模型上传 + 容错 + 安全

**前提**: 阶段 3 的完整训练流已跑通。

### 4.1 开发顺序

| 步骤 | 组件 | 功能 | 代码量 |
|:---|:---|:---|:---|
| 1 | Agent `uploader.py` | 分片上传 best_model.pt | 80 行 |
| 2 | 云服务器 `checkpoint.py` 补充 | 接收分片、合并文件 | 40 行 |
| 3 | 云服务器 `auth.py` | API Token 认证中间件 | 30 行 |
| 4 | Agent `api_client.py` 补充 | 请求带 Token | 5 行 |
| 5 | Agent `agent.py` 补充 | 崩溃恢复：启动时检查未完成任务 | 30 行 |
| 6 | Dashboard | 简单登录页 | 30 行 |
| 7 | 部署脚本 | systemd service 文件 + start/stop 脚本 | - |

### 4.2 验证方式

```
1. 训练完成 → Agent 自动上传 best_model.pt → 云服务器收到
2. wget 下载模型 → 文件完整可加载
3. 不带 Token 请求 API → 403 拒绝
4. kill Agent → 重启后正确处理未完成任务
5. 断网 30s → 恢复后 Agent 自动重连继续上报
```

---

## 完整文件清单 (最终)

```
NetTrainBridge/
├── server/                          # 云服务器 (阶段 1 开始)
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── auth.py                      # 阶段 4
│   ├── api/
│   │   ├── __init__.py
│   │   ├── jobs.py
│   │   ├── webhook.py
│   │   ├── logs.py
│   │   ├── metrics.py
│   │   └── checkpoint.py
│   ├── static/
│   │   └── dashboard.html           # 阶段 3
│   └── requirements.txt
│
├── agent/                           # 公司训练机 (阶段 2 开始)
│   ├── agent.py
│   ├── config.py
│   ├── api_client.py
│   ├── job_runner.py
│   ├── log_monitor.py               # 阶段 3
│   ├── metrics_reader.py            # 阶段 3
│   ├── uploader.py                  # 阶段 4
│   └── requirements.txt
│
├── contrib/agi_origin/                # agi_origin 集成脚本 (阶段 3)
│   └── humanoid/scripts/train_with_metrics.py
│
├── deploy/                          # 部署脚本 (阶段 4)
│   ├── agent.service
│   ├── start_agent.sh
│   └── stop_agent.sh
│
└── plan/                            # 设计文档
    ├── plan_1.md                    # 架构蓝图
    ├── dev_phases.md                # 开发阶段规划（本文件）
    ├── phase1_server_dev_plan.md    # 阶段一详细计划
    ├── phase2_agent_dev_plan.md     # 阶段二详细计划
    └── phase3_dev_plan.md           # 阶段三详细计划
```

---

## 每阶段结束的检查点

| 阶段 | 必须通过的检查 |
|:---|:---|
| **阶段 1** | `curl` 能完成：创建任务 → 查询任务 → 抢占任务 → 上报指标/日志 → 更新状态 |
| **阶段 2** | Agent 启动后能自动：轮询 → 抢占 → clone 代码 → 启动模拟训练 → 心跳上报 → 标记完成 |
| **阶段 3** | `git push` → Webhook 触发 → Agent 自动训练 → Dashboard 实时看曲线 → 训练结束状态正确 |
| **阶段 4** | 模型上传下载完整 + Token 认证生效 + Agent 崩溃恢复 + 断网重连 |
