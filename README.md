# GradMotion

在家推送代码，公司训练机自动训练，云端查看进度。

## 项目简介

GradMotion 是一个分布式强化学习训练任务管理系统，让你可以：

- 在家里用 `git push` 提交训练代码
- 公司内网训练机自动拉取并执行训练
- 通过 Web Dashboard 查看任务状态和训练进度
- 训练完成后从云端下载模型

**核心优势**：无需内网穿透、无需 SSH、全程 GitOps 驱动。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           你 的 家 里 (Home)                                │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  你的电脑 (Client)                                                │      │
│  │  • 写代码、git push 到 GitHub                                     │      │
│  │  • 浏览器打开 Dashboard 查看任务                                  │      │
│  │  • wget 下载最终模型                                              │      │
│  └──────────────────────────────────────────────────────────────────┘      │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │ HTTP
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          公 网 云 服 务 器                                   │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  FastAPI Server (端口 8000)                                       │      │
│  │  • SQLite: 任务状态、训练指标                                     │      │
│  │  • 本地磁盘: 模型文件                                             │      │
│  │  • Web Dashboard: 任务列表与状态统计                              │      │
│  └──────────────────────────────────────────────────────────────────┘      │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │ Webhook
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          GitHub (代码托管)                                   │
│  • push 后 Webhook 回调云服务器，自动创建训练任务                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                │
                                │ 公司训练机通过代理访问外网
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          公 司 内 网                                        │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  训练服务器 (GPU 机器, conda 环境 nettrain)                     │      │
│  │  ┌────────────────────────────────────────────────────────┐      │      │
│  │  │  Agent - 长期运行的后台进程                             │      │      │
│  │  │  • 轮询云服务器、抢占任务、clone 代码                   │      │      │
│  │  │  • conda run -n nettrain 启动训练子进程                 │      │      │
│  │  │  • 增量上报日志与指标                                   │      │      │
│  │  │  • 训练结束后上传模型                                   │      │      │
│  │  └────────────────────────────────────────────────────────┘      │      │
│  └──────────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 目录结构

```
NetTrainBridge/
├── server/                          # 云服务器 (阶段一 ✅)
│   ├── main.py                      # FastAPI 入口
│   ├── config.py                    # 服务器配置
│   ├── database.py                  # SQLite 初始化
│   ├── models.py                    # Pydantic 数据模型
│   ├── api/                         # API 路由
│   │   ├── jobs.py                  # 任务 CRUD + 抢占
│   │   ├── webhook.py               # GitHub Webhook
│   │   ├── logs.py                  # 日志上报/查询
│   │   ├── metrics.py               # 指标上报/查询
│   │   └── checkpoint.py            # 模型上传/下载
│   ├── static/index.html            # Web Dashboard
│   ├── test_e2e.sh                  # 全链路验证脚本
│   └── requirements.txt
│
├── agent/                           # 公司训练机 (阶段二 🚧)
│   ├── config.py                    # Agent 配置 (含 conda 环境)
│   ├── api_client.py                # 云服务器 HTTP 客户端
│   ├── job_runner.py                # clone / 安装依赖 / 启动训练
│   ├── log_monitor.py               # 训练日志增量读取
│   ├── metrics_reader.py            # metrics.jsonl 增量解析
│   ├── heartbeat.py                 # GPU 心跳上报
│   ├── agent.py                     # 主程序入口
│   └── requirements.txt
│
├── plan/                            # 设计文档
│   ├── plan_1.md                    # 架构蓝图
│   ├── dev_phases.md                # 开发阶段规划
│   ├── phase1_server_dev_plan.md    # 阶段一详细计划
│   └── phase2_agent_dev_plan.md     # 阶段二详细计划
│
└── README.md
```

## 快速开始

### 1. 部署云服务器

```bash
cd server
pip install -r requirements.txt

# 启动服务
python main.py
# 服务运行在 http://0.0.0.0:8000
# Dashboard: http://localhost:8000/static/index.html

# 可选：全链路验证
bash test_e2e.sh http://localhost:8000
```

### 2. 配置 GitHub Webhook

在 GitHub 仓库设置中添加 Webhook：

- **URL**: `http://你的云服务器IP:8000/webhook/github`
- **Content type**: `application/json`
- **Events**: `Just the push event`

### 3. 部署 Agent（公司训练机）

训练服务器使用 conda 环境 `nettrain`：

```bash
conda activate nettrain
cd agent
pip install -r requirements.txt

# 配置云服务器地址与公司代理
export GRADMOTION_SERVER_URL=http://你的云服务器IP:8000
export GRADMOTION_PROXY=http://10.12.201.122:39000   # 按实际代理修改
export GRADMOTION_WORKSPACE=/workspace/gradmotion
export GRADMOTION_CONDA_ENV=nettrain                  # 默认值，可省略

# 启动 Agent
python agent.py
```

训练和 `pip install` 会通过 `conda run -n nettrain` 在指定环境中执行，与手动 `conda activate nettrain` 后运行效果一致。

## 使用流程

### 日常使用（在家）

```bash
# 1. 修改训练代码
vim train.py

# 2. 提交并推送
git add . && git commit -m "tune learning rate" && git push

# 3. 自动触发训练
# GitHub Webhook → 云服务器创建任务 → Agent 自动执行

# 4. 打开浏览器查看进度
open http://云服务器IP:8000/static/index.html

# 5. 训练完成后下载模型
wget http://云服务器IP:8000/jobs/{job_id}/checkpoint/{filename}.pt
```

## 服务器 API

### 任务接口

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| `GET` | `/health` | 健康检查 |
| `POST` | `/jobs` | 创建任务 |
| `GET` | `/jobs/pending` | 查询待处理任务 |
| `GET` | `/jobs/{id}` | 查询单个任务 |
| `PUT` | `/jobs/{id}/claim` | Agent 抢占任务 |
| `PUT` | `/jobs/{id}/status` | 更新任务状态 |

### 上报与查询接口

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| `POST` | `/jobs/{id}/logs` | 上报训练日志 |
| `GET` | `/jobs/{id}/logs` | 查询日志（支持 `?tail=N`） |
| `POST` | `/jobs/{id}/metrics` | 上报训练指标 |
| `GET` | `/jobs/{id}/metrics` | 查询指标（支持 `?since_step=N`） |
| `POST` | `/jobs/{id}/heartbeat` | 上报心跳（GPU 状态） |
| `GET` | `/jobs/{id}/heartbeat` | 查询最新心跳 |
| `POST` | `/jobs/{id}/checkpoint` | 分片上传模型 |
| `GET` | `/jobs/{id}/checkpoint/{filename}` | 下载模型 |

### Webhook

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| `POST` | `/webhook/github` | GitHub Push Webhook |

详细 API 文档见 [server/README.md](server/README.md)。

## 配置说明

### 云服务器配置

| 环境变量 | 默认值 | 说明 |
|:---|:---|:---|
| `GRADMOTION_HOST` | 0.0.0.0 | 监听地址 |
| `GRADMOTION_PORT` | 8000 | 监听端口 |
| `GRADMOTION_DB_PATH` | data/server.db | SQLite 数据库路径 |
| `GRADMOTION_DATA_DIR` | data | 数据存储目录 |

### Agent 配置

| 环境变量 | 默认值 | 说明 |
|:---|:---|:---|
| `GRADMOTION_SERVER_URL` | http://localhost:8000 | 云服务器地址 |
| `GRADMOTION_PROXY` | 空 | 公司 HTTP 代理，如 `http://10.12.201.122:39000` |
| `GRADMOTION_AGENT_ID` | agent-001 | Agent 唯一标识 |
| `GRADMOTION_POLL_INTERVAL` | 30 | 任务轮询间隔（秒） |
| `GRADMOTION_HEARTBEAT_INTERVAL` | 30 | 心跳上报间隔（秒） |
| `GRADMOTION_LOG_UPLOAD_INTERVAL` | 5 | 日志上报间隔（秒） |
| `GRADMOTION_METRICS_UPLOAD_INTERVAL` | 10 | 指标上报间隔（秒） |
| `GRADMOTION_WORKSPACE` | /workspace/gradmotion | 任务工作目录 |
| `GRADMOTION_CONDA_ENV` | nettrain | 训练用 Conda 环境名，空则使用系统 Python |
| `GRADMOTION_TRAIN_COMMAND` | 见下方 | 训练启动命令模板 |
| `GRADMOTION_REQUEST_TIMEOUT` | 30 | HTTP 请求超时（秒） |
| `GRADMOTION_MAX_RETRIES` | 3 | 网络请求最大重试次数 |

默认训练命令（`{job_id}` 会被替换为任务 ID）：

```bash
python humanoid/scripts/train.py --task=x1_dh_stand --run_name={job_id} --headless
```

## 任务状态流转

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

## 训练仓库适配

默认适配 [agi_origin](https://github.com/Lee-Weather/agi_origin.git)（AgiBot X1 人形机器人 RL 训练，基于 Isaac Gym）。

Agent 在 `nettrain` conda 环境中执行：

```bash
conda run -n nettrain python humanoid/scripts/train.py \
  --task=x1_dh_stand --run_name={job_id} --headless
```

模型搜索路径（训练完成后自动查找并上传）：

```
logs/**/model_*.pt
log/exported_policies/**/*.pt
```

指标文件约定（由训练脚本或包装脚本写入）：

```
{workspace}/{job_id}/metrics.jsonl
# 每行 JSON: {"step": 100, "loss": 0.5, "reward": 1.2}
```

## 开发进度

| 阶段 | 内容 | 状态 |
|:---|:---|:---|
| 阶段一 | 云服务器 API + 最小 Dashboard | ✅ 完成 |
| 阶段二 | Agent 基础版 | ✅ 完成 |
| 阶段三 | 完整训练流 + Dashboard 曲线 | 待开发 |
| 阶段四 | 容错 + Token 认证 + 部署脚本 | 待开发 |

### 阶段二细分进度

| 模块 | 文件 | 状态 |
|:---|:---|:---|
| 配置 | `config.py` | ✅ |
| API 客户端 | `api_client.py` | ✅ |
| 任务执行器 | `job_runner.py`（含 conda 支持） | ✅ |
| 日志监控 | `log_monitor.py` | ✅ |
| 指标读取 | `metrics_reader.py` | ✅ |
| 心跳上报 | `heartbeat.py` | ✅ |
| 主程序 | `agent.py` | ✅ |

## 成本估算

| 项目 | 规格 | 月成本 |
|:---|:---|:---|
| 公网云服务器 | 2核2GB, 40GB硬盘 | ≈ 50 元 |
| 公司训练机 | 已有 GPU | 0 元 |
| GitHub | 私有仓库免费 | 0 元 |
| **总计** | | **≈ 50 元/月** |

## 技术栈

- **云服务器**: FastAPI + SQLite + Uvicorn
- **Agent**: Python 3.10+ + httpx + asyncio
- **训练环境**: Conda (`nettrain`) + Isaac Gym + PyTorch

## 参考资料

- [架构蓝图](plan/plan_1.md)
- [开发阶段规划](plan/dev_phases.md)
- [阶段一服务器开发计划](plan/phase1_server_dev_plan.md)
- [阶段二 Agent 开发计划](plan/phase2_agent_dev_plan.md)
