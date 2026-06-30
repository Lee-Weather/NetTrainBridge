# GradMotion Server

云服务器端 FastAPI 服务，负责任务调度、指标上报、日志接收和模型上传。

## 快速启动

```bash
conda activate F1
cd server
pip install -r requirements.txt
python main.py
# 服务运行在 http://0.0.0.0:8000
# Dashboard: http://localhost:8000/static/index.html
# 任务详情: http://localhost:8000/static/dashboard.html?id={job_id}
```

## Web Dashboard

浏览器打开 `http://云服务器IP:8000/static/index.html` 查看：

- 任务状态统计卡片（PENDING / RUNNING / COMPLETED / FAILED）
- 任务列表（ID、状态、仓库、Commit、Agent、创建时间）
- 每 10 秒自动刷新
- 下载模型链接

## 配置

通过环境变量覆盖默认配置：

| 环境变量 | 默认值 | 说明 |
|:---|:---|:---|
| `GRADMOTION_HOST` | 0.0.0.0 | 监听地址 |
| `GRADMOTION_PORT` | 8000 | 监听端口 |
| `GRADMOTION_DB_PATH` | data/server.db | SQLite 数据库路径 |
| `GRADMOTION_DATA_DIR` | data | 数据存储目录 |
| `GRADMOTION_WEBHOOK_SECRET` | （空） | GitHub Webhook 签名密钥，未设置则跳过校验 |
| `GRADMOTION_ALLOWED_REPOS` | （空） | 允许的仓库 URL，逗号分隔；空表示不限制 |

## API 接口

### 健康检查

```
GET /health
```

响应：`{"status": "ok"}`

---

### 任务接口

#### 创建任务

```
POST /jobs
Content-Type: application/json

{
  "repo_url": "https://github.com/user/repo",
  "commit_sha": "abc123",
  "id": "optional-custom-id"   // 可选，不传则自动生成
}
```

响应（201）：
```json
{
  "id": "32dccb5461be",
  "status": "PENDING",
  "repo_url": "https://github.com/user/repo",
  "commit_sha": "abc123",
  "agent_id": null,
  "create_time": "2026-06-24T00:54:21",
  "start_time": null,
  "end_time": null,
  "error_msg": null
}
```

#### 查询待处理任务

```
GET /jobs/pending
```

响应：任务列表，按创建时间升序。

#### 查询单个任务

```
GET /jobs/{job_id}
```

#### Agent 抢占任务

```
PUT /jobs/{job_id}/claim
Content-Type: application/json

{
  "agent_id": "agent-1"
}
```

仅当任务状态为 `PENDING` 时可抢占，否则返回 409。

#### 更新任务状态

```
PUT /jobs/{job_id}/status
Content-Type: application/json

{
  "status": "RUNNING",          // RUNNING / COMPLETED / FAILED
  "error_msg": "optional msg"   // 仅 FAILED 时需要
}
```

状态为 `COMPLETED` 或 `FAILED` 时自动记录 `end_time`。

---

### Webhook 接口

#### GitHub Push Webhook

```
POST /webhook/github
X-GitHub-Event: push

{ GitHub push event payload }
```

自动从 payload 提取 `repo_url` 和 `commit_sha`，创建训练任务。

- 配置 `GRADMOTION_WEBHOOK_SECRET` 后校验 `X-Hub-Signature-256`
- 配置 `GRADMOTION_ALLOWED_REPOS` 后仅处理白名单仓库（如 `https://github.com/Lee-Weather/agi_origin.git`）
- 同一 `repo_url` + `commit_sha` 重复 push 返回 `{"status":"duplicate","job_id":"..."}`

**GitHub 配置**（[agi_origin](https://github.com/Lee-Weather/agi_origin) → Settings → Webhooks）:

| 配置项 | 值 |
|:---|:---|
| Payload URL | `http://<云服务器IP>:8000/webhook/github` |
| Content type | `application/json` |
| Secret | 与 `GRADMOTION_WEBHOOK_SECRET` 一致（可选） |
| Events | Just the push event |

---

### 日志接口

#### 上报日志

```
POST /jobs/{job_id}/logs
Content-Type: application/json

{
  "content": "Epoch 1, Loss: 0.5\n"
}
```

响应：`{"status":"ok","lines":1}`

#### 查询日志

```
GET /jobs/{job_id}/logs
GET /jobs/{job_id}/logs?tail=100
```

响应：`{"logs":["Epoch 1, Loss: 0.5", ...]}`

- `tail`：仅返回最后 N 行

#### 清空日志

```
DELETE /jobs/{job_id}/logs
```

---

### 指标接口

#### 上报指标（批量）

```
POST /jobs/{job_id}/metrics
Content-Type: application/json

{
  "metrics": [
    {"step": 100, "loss": 0.5, "reward": 1.2, "lr": 0.001},
    {"step": 200, "loss": 0.3, "reward": 1.5}
  ]
}
```

响应：`{"status":"ok","count":2}`

#### 查询指标

```
GET /jobs/{job_id}/metrics
GET /jobs/{job_id}/metrics?limit=100&since_step=500
```

- `limit`：返回最近 N 条
- `since_step`：仅返回 step > 此值的记录

---

### 模型接口

#### 分片上传

```
POST /jobs/{job_id}/checkpoint?chunk_index=0&total_chunks=1
Content-Type: multipart/form-data

file: @best_model.pt
```

- `chunk_index`：当前分片序号（从 0 开始）
- `total_chunks`：总分片数
- 单片上传时两者均为 0/1

响应（进行中）：`{"status":"partial","filename":"best_model.pt","received":1,"total":3}`

响应（完成）：`{"status":"completed","filename":"best_model.pt","size":1024000}`

#### 下载模型

```
GET /jobs/{job_id}/checkpoint/{filename}
```

直接返回文件流。

---

### 任务状态流转

```
PENDING → ASSIGNED → RUNNING → COMPLETED
                              → FAILED
```

| 状态 | 说明 |
|:---|:---|
| PENDING | 刚创建，等待 Agent 抢占 |
| ASSIGNED | Agent 已抢占，准备 clone 代码 |
| RUNNING | 训练进行中 |
| COMPLETED | 训练成功完成 |
| FAILED | 训练失败 |

---

## 数据库

SQLite，启动时自动建表。

### jobs 表

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| id | TEXT PK | 任务 ID |
| status | TEXT | 任务状态 |
| repo_url | TEXT | 代码仓库地址 |
| commit_sha | TEXT | 提交 SHA |
| agent_id | TEXT | 抢占的 Agent ID |
| create_time | DATETIME | 创建时间 |
| start_time | DATETIME | 开始时间 |
| end_time | DATETIME | 结束时间 |
| error_msg | TEXT | 错误信息 |

### metrics 表

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| id | INTEGER PK | 自增 ID |
| job_id | TEXT FK | 关联任务 |
| step | INTEGER | 训练步数 |
| loss | REAL | 损失值 |
| reward | REAL | 奖励值 |
| lr | REAL | 学习率 |
| timestamp | DATETIME | 记录时间 |

---

## 项目结构

```
server/
├── main.py              # 应用入口
├── config.py            # 配置管理
├── database.py          # 数据库初始化
├── models.py            # Pydantic 数据模型
├── requirements.txt     # Python 依赖
├── test_e2e.sh          # 全链路验证脚本
├── api/
│   ├── __init__.py
│   ├── jobs.py          # 任务 CRUD + 抢占
│   ├── webhook.py       # GitHub Webhook
│   ├── logs.py          # 日志上报/查询
│   ├── metrics.py       # 指标上报/查询
│   └── checkpoint.py    # 模型分片上传/下载
├── static/
│   └── index.html       # Web Dashboard
└── data/
    └── server.db        # SQLite 数据库
```

---

## 测试

```bash
# 全链路验证（需先启动服务）
bash test_e2e.sh

# 或指定服务器地址
bash test_e2e.sh http://your-server:8000
```

测试覆盖 23 个检查项：健康检查、任务 CRUD、抢占、状态更新、日志、指标、模型上传下载、Webhook。
