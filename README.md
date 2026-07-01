# NetTrainBridge

在家 `git push` 同步代码；**训练首选 Gradmotion（gm）**；gm 不可用时用 **`ntb train run`** 在公司训练机兜底训练；可选 **`ntb sync`** 仅同步代码、**`ntb test run`** 做 sim2sim（后续版本）。

## 做什么

- 家里 `git push` 同步代码到 GitHub
- **主路径**：在 gm 云端训练（`gm task create` + `run`）
- **兜底**：`ntb train run` 在公司训练机训练（gm 故障/环境不兼容时）
- **同步**：`ntb sync` 仅把代码拉到训练机，不训练
- 家里用 `ntb watch` 看 NTB 任务指标；训练完 checkpoint 在 Server `data/{job_id}/`
- 训练完成后 Agent 写入 `meta.json`（`train_source: ntb`）

无需内网穿透、无需 SSH 到训练机。

## 架构

```
家里 (gm 训练 + ntb sync/train/test) ──HTTP──▶ 云服务器 FastAPI :8000
                                                    ▲
公司训练机 Agent (sync / 兜底 train / test) ──HTTP(+代理)──┘
Gradmotion 云端 GPU（主路径训练）
```

## 三端分工


| 角色         | conda      | 安装                            | `pip install -e .`？ |
| ---------- | ---------- | ----------------------------- | ------------------- |
| **云服务器**   | `nettrain` | `server/requirements.txt`     | 否                   |
| **训练机**    | `F1`       | `agent/requirements.txt`      | 否                   |
| **家里 CLI** | 任意 3.8+    | 仓库根 `pip install -e ".[dev]"` | 是（仅此处）              |


## 启动

配置文件路径：`~/.nettrainbridge/config.json`（三端共用；优先级：环境变量 > 配置文件 > 默认值）。

### 云服务器

**配置（首次）**

```bash
mkdir -p ~/.nettrainbridge
cp config.example.json ~/.nettrainbridge/config.json
```

编辑 `server` 段（按需改 `webhook_secret`、`allowed_repos`）：

```json
"server": {
  "host": "0.0.0.0",
  "port": 8000,
  "webhook_secret": "",
  "allowed_repos": ["https://github.com/Lee-Weather/agi_origin.git"]
}
```

**启动**

```bash
git pull
conda activate nettrain
cd server && pip install -r requirements.txt   # 首次
python main.py
```

启动日志应出现 `配置文件: ~/.nettrainbridge/config.json`。  
自检：`curl http://127.0.0.1:8000/health`

### 训练机

**配置（首次）**

```bash
mkdir -p ~/.nettrainbridge
cp config.example.json ~/.nettrainbridge/config.json
```

编辑 `agent` 段（`proxy` 按公司实际代理修改）：

```json
"agent": {
  "server_url": "http://47.103.63.175:8000",
  "proxy": "http://10.12.201.122:39000",
  "agent_id": "agent-001",
  "workspace": "~/czy/nettrainbridge",
  "conda_env": "F1",
  "train_command": "python humanoid/scripts/train_with_metrics.py --task=x1_dh_stand --run_name={job_id} --headless"
}
```

**启动**

```bash
git pull
conda activate F1
cd agent && pip install -r requirements.txt   # 首次
python agent.py
```

启动日志应出现 Agent ID、服务器地址、workspace。  
自检：`curl -x http://10.12.201.122:39000 http://47.103.63.175:8000/health`

### 家里（监控）

**配置（首次）**

```bash
pip install -e ".[dev]"
ntb config init
```

或手动复制模板后编辑 `cli` 段：

```json
"cli": {
  "server_url": "http://47.103.63.175:8000"
}
```

**使用**

```bash
ntb health
ntb sync                 # 仅同步代码到训练机
ntb train run            # 兜底训练（gm 不可用时）
ntb train run --watch
ntb trigger              # 已弃用，等同 train run
ntb jobs
ntb job <job_id>         # 含类型、训练来源（meta）
ntb watch <job_id>
```

未安装包时：`python cli/ntb.py` 或 `python -m nettrainbridge_cli`（同样读 `~/.nettrainbridge/config.json`）。

### 端到端顺序

```text
【主路径 — gm 训练】
1. git push
2. gm task create + gm task run
3. gm task logs --follow

【兜底 — ntb 训练】
1. 云服务器  python main.py
2. 训练机    python agent.py
3. 家里      git push
4. 家里      ntb train run [--watch]
5. 家里      ntb job <id>   # 完成后可见 train_source=ntb

【仅同步代码】
ntb sync --commit <sha>
```

验收（云服务器 `server/` 目录）：

```bash
bash test_phase3.sh http://localhost:8000
bash test_cli.sh http://localhost:8000
```

## GitHub Webhook（可选，默认不用）

手动触发模式下 **无需配置 Webhook**。若 GitHub 上仍保留旧的 push Webhook，请在仓库 Settings → Webhooks 中 **Disable 或 Delete**，避免 push 时重复创建任务。

如需恢复 push 自动触发，可重新启用 Webhook：

在 [agi_origin](https://github.com/Lee-Weather/agi_origin) → Settings → Webhooks：


| 项            | 值                                     |
| ------------ | ------------------------------------- |
| Payload URL  | `http://<云服务器IP>:8000/webhook/github` |
| Content type | `application/json`                    |
| Events       | Just the push event                   |


## CLI 速查

完整帮助：`ntb --help`、`ntb <命令> --help`。

### 全局选项（所有子命令可用）


| 选项             | 说明               |
| -------------- | ---------------- |
| `--server URL` | 临时指定云服务器（覆盖配置文件） |
| `--json`       | 输出原始 JSON        |


配置文件 `cli.server_url`；可选 `api_token`（或环境变量 `NETTRAINBRIDGE_API_TOKEN`）用于 Bearer 认证。

### 命令


| 命令 | 说明 |
|:---|:---|
| `ntb health` | 服务器健康检查 |
| `ntb sync` | 仅同步代码到训练机（不训练） |
| `ntb train run` | **兜底**训练任务（`job_type=train`） |
| `ntb trigger` | 已弃用，等同 `train run` |
| `ntb jobs` | 任务列表 |
| `ntb job <id>` | 单任务详情（含 meta 训练来源/模型） |
| `ntb metrics <id>`   | 训练指标表格                             |
| `ntb heartbeat <id>` | 最新 GPU 心跳（利用率、显存）                  |
| `ntb logs <id>`      | 查询日志                               |
| `ntb logs <id> -f`   | SSE 实时跟踪日志                         |
| `ntb watch <id>`     | 综合监控（指标 + GPU，默认 5s 轮询）            |
| `ntb config init`    | 生成 `~/.nettrainbridge/config.json` |
| `ntb config path`    | 显示配置文件查找路径                         |


### 常用参数


| 命令 | 参数 | 说明 |
|:---|:---|:---|
| `train run` / `sync` | `--repo URL` | 仓库地址（默认 `git remote get-url origin`） |
| `train run` / `sync` | `--commit SHA` | Commit SHA（默认当前 HEAD） |
| `train run` / `sync` | `--branch NAME` | 分支名（与 `--commit` 互斥） |
| `train run` | `--watch` | 创建后立即 watch |
| `train run` | `--interval SEC` | watch 轮询间隔（默认 5） |
| `trigger` | （同 train run） | 已弃用 |
| `jobs`        | `--status STATUS`  | 筛选：`PENDING` / `ASSIGNED` / `RUNNING` / `COMPLETED` / `FAILED` |
| `jobs`        | `--limit N`        | 最多返回 N 条（默认 20）                                                |
| `metrics`     | `--limit N`        | 最近 N 条指标                                                       |
| `metrics`     | `--since-step N`   | 只返回 step > N 的记录                                               |
| `logs`        | `--tail N`         | 只显示最后 N 行                                                      |
| `watch`       | `--interval SEC`   | 轮询间隔秒数（默认 5）                                                   |
| `watch`       | `--once`           | 只拉一轮（脚本/调试）                                                    |
| `config init` | `--server-url URL` | 写入的服务器地址                                                       |
| `config init` | `--path PATH`      | 自定义写入路径                                                        |
| `config init` | `--force`          | 覆盖已有文件                                                         |


### 示例

```bash
cd agi_origin && git push
ntb train run --watch
ntb sync --commit $(git rev-parse HEAD)
```

## 任务状态

```
PENDING → ASSIGNED → RUNNING → COMPLETED / FAILED
```

## 目录概览

```
NetTrainBridge/
├── server/          # 云 API
├── agent/           # 训练机 Agent
├── cli/             # ntb 客户端
├── nettrainbridge_common/   # 共享配置加载
├── config.example.json
└── plan/            # 设计文档（见 plan/README.md）
```

设计与阶段规划见 [plan/README.md](plan/README.md)。