# 第一阶段：云服务器开发计划

## 目标
在 `server/` 中实现 FastAPI 服务，支持任务调度、指标上报、日志接收和模型上传，并为第二阶段的 Agent 提供完整 API。

## 1. 技术栈
- Web 框架: FastAPI
- 数据库: SQLite（轻量、易部署）
- 数据校验: Pydantic
- HTTP 客户端: httpx（Agent 调用用）

## 2. 目录结构
```text
server/
├── main.py          # 应用入口 + 路由注册
├── config.py        # 配置读取（端口、DB路径等）
├── database.py      # SQLite 初始化与连接
├── models.py        # Pydantic 模型
├── api/
│   ├── __init__.py
│   ├── jobs.py      # 任务 CRUD / 抢占
│   ├── webhook.py   # GitHub Webhook
│   ├── logs.py      # 日志上报
│   ├── metrics.py   # 指标上报
│   └── checkpoint.py # 模型上传
├── static/
│   └── index.html   # 最小 Dashboard（Step 5）
└── requirements.txt
```

## 3. 开发顺序（8 个子阶段，每个结束都有可运行代码）

### Step 1: 基础设施
**产出**: `requirements.txt` + `config.py` + `database.py`
- 创建 `requirements.txt`（fastapi, uvicorn, pydantic, httpx, aiofiles）
- 完成 `config.py`（默认值 + 环境变量覆盖）
- 完成 `database.py`（建表、连接管理）
- **验证**: `python -c "from database import init_db; init_db()"` 无报错，db 文件生成

### Step 2: 数据模型
**产出**: `models.py`
- 定义 JobCreate、JobResponse、MetricCreate、LogMessage、CheckpointChunk 等模型
- 确保字段类型、约束清晰
- **验证**: `python -c "from models import JobCreate"` 无报错

### Step 3A: 任务基础
**产出**: `api/__init__.py` + `api/jobs.py` + `api/webhook.py` + `main.py`（最小版）
- `api/jobs.py` — GET /jobs/pending、POST /jobs、PUT /jobs/{id}/claim、PUT /jobs/{id}/status
- `api/webhook.py` — POST /webhook/github（解析 push 事件自动创建任务）
- `main.py` 最小版，仅注册 jobs + webhook 路由 + health
- **验证**: curl 创建任务 → 查询 pending → 抢占 → 更新状态，全链路跑通

### Step 3B: 上报通道
**产出**: `api/logs.py` + `api/metrics.py`
- `api/logs.py` — POST /jobs/{id}/logs（内存缓存 deque(5000)）
- `api/metrics.py` — POST /jobs/{id}/metrics（写入 SQLite）
- `main.py` 补充注册 logs + metrics 路由
- **验证**: curl 上报日志 → 上报指标 → 查询指标，数据落库正确

### Step 3C: 文件上传
**产出**: `api/checkpoint.py`
- `api/checkpoint.py` — POST /jobs/{id}/checkpoint（分片上传 + 临时文件合并）+ GET 下载
- `main.py` 补充注册 checkpoint 路由
- **验证**: curl 上传小文件 → 下载 → md5 一致

### Step 4: 组装 + 全链路验证
**产出**: 完整 `main.py` + curl 验证脚本
- 确认所有路由注册、启动时初始化数据库
- 增加启动事件、异常处理
- **验证**: 按「验证标准」第 6 节逐项通过

### Step 5: 最小 Dashboard（阶段 1 内即可看进度）
**产出**: `server/static/index.html`
- 任务列表：显示所有任务的状态、创建时间、Agent ID
- 状态卡片：PENDING / RUNNING / COMPLETED / FAILED 用颜色区分
- 自动刷新：每 10 秒拉取 `/jobs/pending` + 其他状态任务
- 纯前端，调用已有 API，无需新增后端代码
- `main.py` 挂载 static 目录：`app.mount("/static", StaticFiles(...))`
- **验证**: 浏览器打开 `http://云服务器IP:8000/static/index.html`，能看到任务列表和状态

## 4. 核心数据模型
### 任务表 (jobs)
- id, status, repo_url, commit_sha, agent_id, create_time, start_time, end_time, error_msg

### 指标表 (metrics)
- id, job_id, step, loss, reward, lr, timestamp

### 日志缓存
- 内存字典 key=job_id -> deque(maxlen=5000)

### 模型存储
- 目录: `/data/gradmotion/{job_id}/best_model.pt`

## 5. API 清单
### 任务接口
- `GET /jobs/pending`
- `POST /jobs`
- `PUT /jobs/{job_id}/claim`
- `PUT /jobs/{job_id}/status`

### 上报接口
- `POST /jobs/{job_id}/logs`
- `POST /jobs/{job_id}/metrics`
- `POST /jobs/{job_id}/heartbeat`

### 模型接口
- `POST /jobs/{job_id}/checkpoint`（分片）
- `GET /jobs/{job_id}/checkpoint/best_model.pt`

### 其他
- `GET /health`
- `POST /webhook/github`

## 6. 验证标准（阶段一必须通过）
1. 可用 curl 完成：创建任务 → 查询任务 → 抢占任务 → 上报指标 → 上报日志 → 更新状态
2. 数据库文件存在且表结构正确
3. 无认证时仍可创建任务和上报数据（后续阶段再加鉴权）
4. 浏览器打开 `/static/index.html` 能看到任务列表，自动刷新正常

## 7. 风险与对策
- **并发抢占冲突**: 使用 SQLite 原子更新或乐观锁
- **大文件上传卡顿**: checkpoint 使用分片+临时文件再重命名
- **日志暴涨撑爆内存**: 限制最大条数，历史落盘可选扩展
