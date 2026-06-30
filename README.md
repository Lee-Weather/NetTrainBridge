# NetTrainBridge

在家推送代码，公司训练机自动训练，云端查看进度。

## 项目简介

NetTrainBridge 是一个分布式强化学习训练任务管理系统，让你可以：

- 在家里用 `git push` 提交训练代码
- 公司内网训练机自动拉取并执行训练
- 通过命令行 `ntb` 查看任务状态、训练指标和日志
- 训练完成后从云端下载模型

**核心优势**：无需内网穿透、无需 SSH、全程 GitOps 驱动。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           你 的 家 里 (Home)                                │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  你的电脑 (Client)                                                │      │
│  │  • 写代码、git push 到 GitHub                                     │      │
│  │  • 终端 ntb watch 查看训练进度                                    │      │
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
│  │  • 纯 REST API（无 Web GUI）                                      │      │
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
│  │  训练服务器 (GPU 机器, conda 环境 F1)                           │      │
│  │  ┌────────────────────────────────────────────────────────┐      │      │
│  │  │  Agent - 长期运行的后台进程                             │      │      │
│  │  │  • 轮询云服务器、抢占任务、clone 代码                   │      │      │
│  │  │  • conda run -n F1 启动训练子进程                       │      │      │
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
│   ├── test_e2e.sh                  # 全链路验证脚本
│   ├── test_phase3.sh               # 阶段三验收脚本
│   ├── test_cli.sh                  # CLI 验收脚本
│   └── requirements.txt
│
├── pyproject.toml                   # pip install -e ".[dev]" → ntb 命令
├── nettrainbridge_common/           # 共享配置加载
│   └── config_loader.py
├── cli/                             # 命令行客户端 (去 GUI 化 ✅)
│   ├── nettrainbridge_cli/          # ntb 包入口
│   └── ntb.py                       # 向后兼容 shim
│
├── contrib/agi_origin/              # agi_origin 集成脚本 (阶段三 ✅)
│   └── humanoid/scripts/train_with_metrics.py
│
├── agent/                           # 公司训练机 (阶段二 ✅)
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
│   ├── phase2_agent_dev_plan.md     # 阶段二详细计划
│   └── phase3_dev_plan.md           # 阶段三详细计划
│
└── README.md
```

## 快速开始

### 1. 部署云服务器

```bash
conda activate nettrain   # 云服务器 Python 环境
cd server
pip install -r requirements.txt

python main.py
```

**推荐：用配置文件（三端共用一份，不用每次 export）**

```bash
# 任意机器执行一次（会写入 ~/.nettrainbridge/config.json）
ntb config init

# 编辑配置文件中的 server 段，例如 webhook_secret、allowed_repos
# Linux: ~/.nettrainbridge/config.json
# Windows: C:\Users\你的用户名\.nettrainbridge\config.json
```

`server` 段示例：

```json
"server": {
  "host": "0.0.0.0",
  "port": 8000,
  "webhook_secret": "your-secret",
  "allowed_repos": ["https://github.com/Lee-Weather/agi_origin.git"]
}
```

启动后日志会显示 `配置文件: ...`，表示已从文件读取。  
环境变量仍可覆盖配置文件（可选）。

```bash
# 服务运行在 http://0.0.0.0:8000
# API 说明: curl http://localhost:8000/

# 验收
bash test_phase3.sh http://localhost:8000
bash test_cli.sh http://localhost:8000
bash test_e2e.sh http://localhost:8000
```

### 2. 配置 GitHub Webhook

在 [agi_origin](https://github.com/Lee-Weather/agi_origin) 仓库 Settings → Webhooks 添加：

| 配置项 | 值 |
|:---|:---|
| Payload URL | `http://你的云服务器IP:8000/webhook/github` |
| Content type | `application/json` |
| Secret | 与 `NETTRAINBRIDGE_WEBHOOK_SECRET` 一致（可选） |
| Events | Just the push event |

云服务器也可在配置文件的 `server.allowed_repos` 中设置白名单（见上文），或使用环境变量。

### 3. 部署 Agent（公司训练机）

训练服务器使用 conda 环境 `F1`（Python 3.8.20，已安装训练依赖）：

```bash
conda activate F1
cd agent
pip install -r requirements.txt

# 首次：生成或编辑 ~/.nettrainbridge/config.json 中的 agent 段
# 可用: ntb config init（需先在仓库根目录 pip install -e ".[dev]"）
python agent.py
```

`agent` 段示例（与 CLI、Server 可写在同一文件）：

```json
"agent": {
  "server_url": "http://47.103.63.175:8000",
  "proxy": "http://10.12.201.122:39000",
  "workspace": "~/czy/nettrainbridge",
  "conda_env": "F1",
  "train_command": "python humanoid/scripts/train_with_metrics.py --task=x1_dh_stand --run_name={job_id} --headless"
}
```

配置好后**直接 `python agent.py`**，无需每次 export 环境变量。

训练和 `pip install` 会通过 `conda run -n F1` 在指定环境中执行，与手动 `conda activate F1` 后运行效果一致。

### 4. 安装 CLI（在家查看进度）

在仓库根目录执行（推荐，安装后可直接使用 `ntb` 命令）：

```bash
pip install -e ".[dev]"
```

向后兼容：未安装时仍可用 `python cli/ntb.py` 或 `python -m nettrainbridge_cli`。

**一次配置，无需每次 export 环境变量：**

```bash
# 生成配置文件（Windows / Linux / macOS 通用）
ntb config init

# Windows 配置文件位置示例：
# C:\Users\你的用户名\.nettrainbridge\config.json
```

也可复制仓库根目录的 `config.example.json` 到上述路径后按需修改。  
环境变量仍可覆盖配置文件（部署时有用）。

## 使用流程

### 日常使用（在家）

```bash
# 1. 修改训练代码
vim train.py

# 2. 提交并推送
git add . && git commit -m "tune learning rate" && git push

# 3. 自动触发训练
# GitHub Webhook → 云服务器创建任务 → Agent 自动执行

# 4. 终端查看进度（需先 ntb config init 或配置 ~/.nettrainbridge/config.json）
ntb jobs                              # 任务列表
ntb job <job_id>                      # 任务详情
ntb watch <job_id>                    # 实时指标 + GPU（推荐）
ntb logs <job_id> -f                  # 另开终端：实时日志

# 5. 训练完成后下载模型
wget http://云服务器IP:8000/jobs/<job_id>/checkpoint/<filename>.pt
```

## CLI 命令速查

| 命令 | 说明 |
|:---|:---|
| `ntb health` | 服务器健康检查 |
| `ntb jobs` | 任务列表 |
| `ntb job <id>` | 任务详情 |
| `ntb watch <id>` | 综合监控（Loss/Reward/GPU，每 5s） |
| `ntb metrics <id>` | 指标表格 |
| `ntb heartbeat <id>` | 最新 GPU 心跳 |
| `ntb logs <id> --tail 50` | 最近 50 行日志 |
| `ntb logs <id> -f` | SSE 实时日志 |

| `ntb config init` | 生成默认配置文件 |
| `ntb config path` | 查看配置文件路径 |

加 `--json` 输出原始 JSON；`--server URL` 可临时指定服务器（覆盖配置文件）。

## 服务器 API

### 任务接口

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| `GET` | `/health` | 健康检查 |
| `POST` | `/jobs` | 创建任务 |
| `GET` | `/jobs` | 任务列表（支持 `?status=&limit=`） |
| `GET` | `/jobs/pending` | 查询待处理任务 |
| `GET` | `/jobs/{id}` | 查询单个任务 |
| `PUT` | `/jobs/{id}/claim` | Agent 抢占任务 |
| `PUT` | `/jobs/{id}/status` | 更新任务状态 |

### 上报与查询接口

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| `POST` | `/jobs/{id}/logs` | 上报训练日志 |
| `GET` | `/jobs/{id}/logs` | 查询日志（支持 `?tail=N`） |
| `GET` | `/jobs/{id}/logs/stream` | SSE 实时日志流 |
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

CLI、Agent、Server **共用一份配置文件**，默认路径：

| 系统 | 路径 |
|:---|:---|
| Linux / macOS | `~/.nettrainbridge/config.json` |
| Windows | `C:\Users\你的用户名\.nettrainbridge\config.json` |

生成模板：`ntb config init`（或复制仓库根目录 `config.example.json`）。

优先级：**环境变量 > 配置文件 > 内置默认值**（日常用配置文件即可；部署时可用环境变量覆盖）。

### 云服务器配置（`server` 段或环境变量）

| 环境变量 | 默认值 | 说明 |
|:---|:---|:---|
| `NETTRAINBRIDGE_HOST` | 0.0.0.0 | 监听地址 |
| `NETTRAINBRIDGE_PORT` | 8000 | 监听端口 |
| `NETTRAINBRIDGE_DB_PATH` | data/server.db | SQLite 数据库路径 |
| `NETTRAINBRIDGE_DATA_DIR` | data | 数据存储目录 |
| `NETTRAINBRIDGE_WEBHOOK_SECRET` | （空） | GitHub Webhook 签名密钥 |
| `NETTRAINBRIDGE_ALLOWED_REPOS` | （空） | 允许的仓库 URL，逗号分隔 |

### Agent 配置（`agent` 段或环境变量）

| 环境变量 | 默认值 | 说明 |
|:---|:---|:---|
| `NETTRAINBRIDGE_SERVER_URL` | http://localhost:8000 | 云服务器地址 |
| `NETTRAINBRIDGE_PROXY` | 空 | 公司 HTTP 代理，如 `http://10.12.201.122:39000` |
| `NETTRAINBRIDGE_AGENT_ID` | agent-001 | Agent 唯一标识 |
| `NETTRAINBRIDGE_POLL_INTERVAL` | 30 | 任务轮询间隔（秒） |
| `NETTRAINBRIDGE_HEARTBEAT_INTERVAL` | 30 | 心跳上报间隔（秒） |
| `NETTRAINBRIDGE_LOG_UPLOAD_INTERVAL` | 5 | 日志上报间隔（秒） |
| `NETTRAINBRIDGE_METRICS_UPLOAD_INTERVAL` | 10 | 指标上报间隔（秒） |
| `NETTRAINBRIDGE_WORKSPACE` | ~/czy/nettrainbridge | 任务工作目录（clone 代码存放位置） |
| `NETTRAINBRIDGE_CONDA_ENV` | F1 | 训练用 Conda 环境名，空则使用系统 Python |
| `NETTRAINBRIDGE_TRAIN_COMMAND` | 见下方 | 训练启动命令模板 |
| `NETTRAINBRIDGE_REQUEST_TIMEOUT` | 30 | HTTP 请求超时（秒） |
| `NETTRAINBRIDGE_MAX_RETRIES` | 3 | 网络请求最大重试次数 |

默认训练命令（阶段三，使用 `train_with_metrics.py` 写入 metrics.jsonl）：

```bash
python humanoid/scripts/train_with_metrics.py --task=x1_dh_stand --run_name={job_id} --headless
```

脚本位于 [agi_origin](https://github.com/Lee-Weather/agi_origin) 仓库 `humanoid/scripts/train_with_metrics.py`（开发源在 `contrib/agi_origin/`）。

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

Agent 在 `F1` conda 环境中执行：

```bash
conda run -n F1 python humanoid/scripts/train.py \
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
| 阶段一 | 云服务器 API | ✅ 完成 |
| 阶段二 | Agent 基础版 | ✅ 完成 |
| 阶段三 | 完整训练流 + CLI (`ntb`) | ✅ 完成 |
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

- **云服务器**: FastAPI + SQLite + Uvicorn（纯 API，无 Web GUI）
- **CLI**: Python + httpx（`pip install -e ".[dev]"` → `ntb`）
- **Agent**: Python 3.8+ + httpx + asyncio
- **训练环境**: Conda (`F1`, Python 3.8.20) + Isaac Gym + PyTorch

## 参考资料

- [去 GUI 化改造计划](plan/remove_gui_plan.md)
- [架构蓝图](plan/plan_1.md)
- [开发阶段规划](plan/dev_phases.md)
- [阶段一服务器开发计划](plan/phase1_server_dev_plan.md)
- [阶段二 Agent 开发计划](plan/phase2_agent_dev_plan.md)
- [阶段三训练流开发计划](plan/phase3_dev_plan.md)（Dashboard 已废弃，见 remove_gui_plan.md）
