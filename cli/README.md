# ntb CLI 使用说明

`ntb` 是 NetTrainBridge 的**家里命令行客户端**：通过 HTTP 访问云 Server，创建/监控 train、sync、test 任务，下载 checkpoint 与测试产物。

典型使用场景：在**训练代码仓库**（如 `agi_origin`）根目录执行；与 **gm CLI** 配合完成「gm 训练 → ntb 真实 sim2sim 验证」（R1-3）。

---

## 安装与运行

### 已安装（推荐）

确认 `ntb` 在 PATH：

```powershell
ntb --help
ntb health
```

### 未安装 / 开发模式

在 NetTrainBridge 仓库根目录：

```bash
pip install -e ".[dev]"
```

或临时调用：

```bash
python cli/ntb.py health
python -m nettrainbridge_cli health
```

### Windows（PowerShell）

- 配置路径：`%USERPROFILE%\.nettrainbridge\config.json`
- 多行命令用 `` ` `` 续行
- 环境变量：`$env:NETTRAINBRIDGE_SERVER_URL = "http://..."`

### 配置

```bash
ntb config init --server-url http://<云IP>:8000
ntb config path
```

配置文件 `cli.server_url` 指向云 Server。可选 `api_token`（或环境变量 `NETTRAINBRIDGE_API_TOKEN`）用于 Bearer 认证。

**gm test 路径（Plan 03）**：家里还需在 `cli` 段配置 gm 凭证（与 `gm auth status` 同账号），用于 `ntb test run` 自动上传 checkpoint 到 Server：

```json
{
  "cli": {
    "server_url": "http://47.103.63.175:8000",
    "gm_api_key": "<你的 gm API Key>",
    "gm_base_url": "https://internal.limxdynamics.com/dev-api"
  }
}
```

也可用环境变量 `GM_API_KEY` / `GM_BASE_URL`。训练机 Agent **默认不需要** gm 配置。

优先级：`--server` 参数 > 环境变量 > 配置文件。

---

## 与 gm 的分工

| 工具 | 跑在哪 | 用途 |
|:---|:---|:---|
| **gm** | 家里 | 云端训练：`task create` / `run` / `model list` |
| **ntb** | 家里 | 任务调度、**从 gm 取模上传 Server**、test sim2sim、指标/产物下载 |
| **Agent** | 公司训练机 | clone、从 **Server 拉模型**、play.py（默认不连 gm） |

主路径：**gm 训练** → 满意后 **`ntb test run`**（家里自动 stage → 训练机 pull → 真实 sim2sim）。

详见 [plan/03plan/plan03-checkpoint-hub.md](../plan/03plan/plan03-checkpoint-hub.md)。

---

## 命令总览

```text
ntb health
ntb jobs [--status STATUS] [--limit N]
ntb jobs clear --yes          # 清空 Server 全部任务（不可恢复）
ntb job <job_id>

ntb sync [--repo URL] [--commit SHA] [--branch NAME]
ntb train run [--repo] [--commit] [--watch] [--interval SEC]

ntb test run --load-run <name> \
  (--gm-task-id <id> | --train-job-id <id>) \
  [--task x1_dh_stand] [--checkpoint N|latest] [--commit SHA] [--watch] \
  [--no-stage-checkpoint] [--fetch-from-gm]

ntb metrics <job_id> [--limit N] [--since-step N]
ntb heartbeat <job_id>
ntb logs <job_id> [--tail N] [-f]
ntb watch <job_id> [--interval SEC] [--once]

ntb checkpoint list <job_id>
ntb checkpoint download <job_id> [-o path] [--filename name]
ntb checkpoint upload <job_id> -f ./model_50.pt
ntb checkpoint stage-from-gm <job_id> --task-id TASK_xxx [--checkpoint 50]

ntb artifacts list <job_id>
ntb artifacts download <job_id> -o path.zip

ntb config init | path
```

完整帮助：`ntb <命令> --help`。

---

## 全局选项

| 选项 | 说明 |
|:---|:---|
| `--server URL` | 临时指定云 Server |
| `--json` | 输出 JSON（脚本友好） |

---

## 任务类型与状态

### job_type

| 类型 | 创建方式 | 说明 |
|:---|:---|:---|
| `train` | `ntb train run` | 兜底训练 |
| `sync` | `ntb sync` | 仅同步代码 |
| `test` | `ntb test run` | sim2sim 测试 |

### 状态流转

```text
PENDING → ASSIGNED → RUNNING → COMPLETED / FAILED
```

test job 另有 **phase**：

```text
gm 默认（Plan 03）：sync → pull → test → done
gm 兜底（--fetch-from-gm）：sync → fetch → test → done
ntb 父任务：sync → test → done
```

### 查看任务

```powershell
# 列表
ntb jobs
ntb jobs --status RUNNING --limit 50

# 详情（含 load_run、checkpoint、gm_task_id）
ntb job <job_id>
ntb job <job_id> --json
```

仅 test 任务（API 过滤）：

```bash
curl -s "http://<server>/jobs?job_type=test&limit=20"
```

### 清空全部任务

```powershell
ntb jobs clear --yes
```

删除 Server 上**所有**任务的 DB 记录与 `data/` 目录，**不可恢复**；不加 `--yes` 会拒绝执行。

---

## sync / train（兜底训练）

在训练代码仓库根目录：

```powershell
# 仅同步代码到训练机
ntb sync --commit $env:COMMIT_SHA

# 兜底训练（gm 不可用时）
ntb train run --watch

# 显式指定仓库
ntb train run --repo https://github.com/org/agi_origin.git --commit abc123 --watch
```

完成后：

```powershell
ntb job <train_job_id>
ntb metrics <train_job_id>
ntb checkpoint list <train_job_id>
ntb checkpoint download <train_job_id> -o .\model.pt
```

---

## test run（R1 真实 sim2sim）

### 必填与互斥

| 参数 | 说明 |
|:---|:---|
| `--load-run` | **必填**。训练 logs 目录名，如 `2026-01-14_09-58-10test_20_video` |
| `--gm-task-id` | 与 `--train-job-id` **二选一** |
| `--train-job-id` | ntb 兜底训练 job id；此时 `--checkpoint` 须为**整数** |
| `--task` | 默认 `x1_dh_stand` |
| `--checkpoint` | gm 路径：`latest` / `50` / `model_50.pt`；ntb 路径：整数如 `3000` |
| `--commit` | 与 gm 训练 push 一致的 SHA |
| `--repo` / `--branch` | 默认当前 git `origin` / `HEAD` |
| `--watch` | 创建后轮询直到结束 |
| `--no-stage-checkpoint` | gm 路径：不自动从 gm 上传 Server（需手动 `checkpoint stage-from-gm`） |
| `--fetch-from-gm` | gm 路径：训练机 Agent 直拉 gm（旧 5B，需训练机 `gm_api_key`） |

### Plan 03：gm checkpoint 中转（默认）

`ntb test run --gm-task-id` 时，家里 CLI 会：

1. 创建 test job（`fetch_mode=server`）
2. 调用 gm API 查询 checkpoint → 下载 `policUrlDown`
3. 上传到 Server `data/{test_job_id}/models/`
4. 训练机 Agent **pull** 到同窗 `logs/.../exported_data/{load_run}/`

```text
家里 gm CLI / ntb  ──取模──▶  gm 云端
       │
       └──上传──▶  云 Server  ──下载──▶  训练机 Agent  ──▶  play.py
```

### 场景 A：gm 训练后 test（推荐）

```powershell
$env:COMMIT_SHA = git rev-parse HEAD

ntb test run `
  --gm-task-id "task_gm_xxx" `
  --load-run "2026-07-01_10-00-00r1_3_test" `
  --task x1_dh_stand `
  --checkpoint latest `
  --commit $env:COMMIT_SHA `
  --watch
```

Agent 流程：`sync` → **Server PULL**（默认）→ `test_with_metrics.py` → 真实 `play.py`。  
家里 `ntb test run --gm-task-id` 会自动从 gm 取模并上传 Server；训练机**无需** `gm_api_key`。

旧路径（可选）：`ntb test run ... --fetch-from-gm` → Agent 直拉 gm（需训练机 gm 配置）。

### 场景 A'：分步 stage（调试 / 大模型）

```powershell
# 仅创建 job，不上传模型
ntb test run --gm-task-id "task_gm_xxx" --load-run "..." --checkpoint 50 --no-stage-checkpoint

# 手动从 gm 上传
ntb checkpoint stage-from-gm <test_job_id> --task-id task_gm_xxx --checkpoint 50

ntb watch <test_job_id>
```

或上传本地已有文件：

```powershell
ntb checkpoint upload <test_job_id> -f .\model_50.pt
```

### 场景 B：ntb 训练后 test

```powershell
ntb test run `
  --train-job-id "<train_job_id>" `
  --load-run "2026-07-01_10-00-00r1_3_test" `
  --checkpoint 3000 `
  --commit $env:COMMIT_SHA `
  --watch
```

无 gm 拉取；Agent 从 Server **父 train job** 下载 checkpoint。

### 验收（test 完成后）

```powershell
ntb job <test_job_id>              # phase=done, status=COMPLETED
ntb metrics <test_job_id>          # 应无 "mock": true
ntb artifacts list <test_job_id>
ntb artifacts download <test_job_id> -o .\test-artifacts.zip
ntb checkpoint list <test_job_id>
```

`summary.json` 中应为 `"mode": "real"`，含 `success_rate`、`final_reward`。

---

## 监控与日志

```powershell
ntb watch <job_id>                 # 指标 + GPU，5s 轮询
ntb watch <job_id> --once --json   # 单轮 JSON

ntb logs <job_id> --tail 100
ntb logs <job_id> -f               # SSE 实时
```

---

## R1-3 端到端（本机 + 训练仓库）

建议在训练代码仓库安装 Cursor Skill（复制自 NetTrainBridge）：

```text
<训练仓库>/.cursor/skills/gm-ntb-r1-e2e/
├── SKILL.md          # AI 操作指南
└── scripts/
    ├── preflight.ps1   # Windows 开工检查
    └── verify-test.ps1 # test 完成后验收
```

**假定**：本机已安装 `ntb` 与 `gm`；Cursor 打开**训练仓库**根目录。

```powershell
# 1. 开工检查
powershell -ExecutionPolicy Bypass -File .cursor\skills\gm-ntb-r1-e2e\scripts\preflight.ps1

# 2. gm 训练（见 gm CLI）
gm task create --file .\create-train.json
gm task run --task-id task_gm_xxx

# 3. ntb test
ntb test run --gm-task-id task_gm_xxx --load-run <load_run> --watch

# 4. 验收
powershell -File .cursor\skills\gm-ntb-r1-e2e\scripts\verify-test.ps1 <test_job_id> -Source gm
```

详细步骤：[plan/r1-3-manual-acceptance.md](../plan/r1-3-manual-acceptance.md)

---

## 常见问题

| 现象 | 处理 |
|:---|:---|
| `无法连接服务器` | 检查 Server 是否启动、`ntb config` / `--server` |
| test 一直 PENDING | 训练机 Agent 未启动或未 claim 任务 |
| PULL 失败 / 等待超时 | 确认家里 stage 完成：`ntb checkpoint list <job_id>`；或重跑 `stage-from-gm` |
| FETCH 失败（`--fetch-from-gm`） | 训练机需 `agent.gm_api_key`；OSS 问题见 `agent/scripts/gm_probe.py --download` |
| gm API 401（家里 stage） | 检查 `cli.gm_api_key`（须 `X-Api-Key`，与 gm CLI 同账号） |
| gm test 默认路径 | **CLI → Server → Agent**；`test run --gm-task-id` 自动 stage |
| 缺 `load_run` 400 | `ntb test run` 必须带 `--load-run` |
| ntb 路径 checkpoint 报错 | 使用整数 `--checkpoint 3000`，不用 `latest` |
| summary 仍是 mock | Agent 勿设 `NETTRAINBRIDGE_TEST_COMMAND=...--mock` |
| `ntb` 找不到 | 确认 PATH 或 `pip install -e ".[dev]"` |

---

## 目录结构

```text
cli/
├── README.md                 # 本文件
├── ntb.py                    # 入口脚本
├── requirements.txt
└── nettrainbridge_cli/
    ├── main.py               # 命令实现
    ├── gm_stage.py           # gm → Server staging
    └── checkpoint_io.py      # checkpoint 上传
```

---

## 相关文档

| 文档 | 内容 |
|:---|:---|
| [../README.md](../README.md) | 项目总览 |
| [../plan/03plan/plan03-checkpoint-hub.md](../plan/03plan/plan03-checkpoint-hub.md) | Plan 03：CLI → Server → Agent |
| [../plan/r1-3-manual-acceptance.md](../plan/r1-3-manual-acceptance.md) | R1-3 手动验收 |
| [../plan/manual-operations-v02.md](../plan/manual-operations-v02.md) | v0.2 操作手册 |
| [../plan/diff/gm-cli/SKILL.md](../plan/diff/gm-cli/SKILL.md) | gm CLI 参考 |
| [../.cursor/skills/gm-ntb-r1-e2e/SKILL.md](../.cursor/skills/gm-ntb-r1-e2e/SKILL.md) | Cursor Skill 模板（复制到训练仓库） |
