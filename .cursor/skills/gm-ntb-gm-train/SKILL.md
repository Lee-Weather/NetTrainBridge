---
name: gm-ntb-gm-train
description: >-
  Push training code and run gm cloud training (mode A/C): preflight, git push,
  create-train.json or copy from reference task, gm task create/run with dry-run,
  poll status, model list, record-run.json. Use for gm train only, push to gm,
  check training status. Optional gm-accounts.json for api_key. Follows gm-cli agent safety (--yes, dry-run exit 10).
  NOT for ntb test (gm-ntb-ntb-test). Run gm-ntb-preflight -For gm first.
  Deep gm-cli reference: .trae/skills/gm-cli/SKILL.md
---

# gm 云训练

适用编排模式：**A**（gm 训练 → 后续 test）、**C**（仅 gm 训练，**不**进入 ntb test）。

gm 通用能力（认证、edit、resume、退出码）见 **`.trae/skills/gm-cli/SKILL.md`**；本文只写 R1-3 + `x1_dh_stand` 训练路径。

## 前置

```powershell
powershell -File .cursor\skills\gm-ntb-preflight\scripts\preflight.ps1 -For gm
```

向用户确认（若未给出）：

| 项 | 说明 |
|:---|:---|
| `RUN_NAME` | 如 `r1_3_test`，拼进 `load_run` |
| `projectId` | 不指定时可列项目让用户选 |
| `goodsId` / 镜像 | 不指定时走下方「资源发现」或复用参考任务 |
| 模式 | A（后续 test）或 C（仅训练） |

## gm 账号配置（gm-accounts.json）

单账号本地配置；`gm.ps1` / `gm.sh` 自动注入 `--base-url` 与 `--api-key`。

### 配置

```powershell
Copy-Item .cursor\skills\gm-ntb-gm-train\gm-accounts.example.json `
          .cursor\skills\gm-ntb-gm-train\gm-accounts.json
# 编辑 gm-accounts.json，填入 api_key（已 gitignore，勿提交）
```

```json
{
  "base_url": "https://internal.limxdynamics.com/dev-api",
  "api_key": "<YOUR_API_KEY>"
}
```

### 验证

```powershell
powershell -File .cursor\skills\gm-ntb-gm-train\scripts\gm-account.ps1
# 或
powershell -File .cursor\skills\gm-ntb-preflight\scripts\gm.ps1 auth whoami
```

未创建 `gm-accounts.json` 时，走 gm-cli 本机默认配置（Keychain / `gm auth login`）。

| 环境变量 | 说明 |
|:---|:---|
| `GM_ACCOUNTS_FILE` | 自定义配置文件路径 |

**禁止**在对话、skill、git 中回显完整 `api_key`。

## 包装脚本（PowerShell 必读）

```powershell
$GM = "powershell -File .cursor\skills\gm-ntb-preflight\scripts\gm.ps1"
```

- PowerShell **禁止**裸调 `gm`（`gm` = `Get-Member` 别名）
- Agent **禁止** `--human`（须解析 JSON stdout）
- 临时 JSON 用相对路径：`--file ./create-train.json`
- 写操作顺序：`--dry-run`（**exit 10 = 预览通过**）→ 去掉 `--dry-run` 正式执行（**exit 0**）
- `stop` / `delete` 等危险操作 Agent **必须** `--yes`（见 gm-cli）

## 阶段 1 — 推送

```powershell
git push origin main
$env:COMMIT_SHA = git rev-parse HEAD
```

`codeUrl` 的 `versionName` 须与 push 分支一致（通常 `main`）。

## 阶段 2 — 准备任务 JSON

### 路径规则（易错）

gm 拉代码后顶层目录名 = **remote 仓库名**，不是本机文件夹名。

| 本机目录 | remote | clone 后路径 |
|:---|:---|:---|
| `agibot_x1_train-main_t` | `agi_origin.git` | `agi_origin/` |

```text
mainCodeUri: agi_origin/humanoid/scripts/train.py
startScript: gm-run agi_origin/humanoid/scripts/train.py --task=x1_dh_stand --run_name=<RUN_NAME> --headless
```

**训练轮数**：`startScript` **不要**写 `--max_iterations`，使用任务配置默认值。  
`x1_dh_stand` 对应 `humanoid/envs/x1/x1_dh_stand_config.py` → `X1DHStandCfgPPO.runner.max_iterations`（当前 **50**）。  
仅当用户明确要求时才加 `--max_iterations=N`（会覆盖配置，见 `humanoid/utils/helpers.py`）。

`startScript` **必须以 `gm-run` 开头**（gm-cli 硬限制）；禁止 `python` / `bash` 启动。

本仓库一般**无**独立 `hparamsPath`（官方 X1 任务亦为 `null`），可不填。

### 方式 A：资源发现后新建（推荐首次）

```powershell
& $GM project list --page 1 --limit 10
& $GM task resource list --goods-back-category 3 --page 1 --limit 10
& $GM task image official
```

填 JSON 时注意（gm-cli）：

| 字段 | 来源 | 勿混用 |
|:---|:---|:---|
| `goodsId` | `resource list` 的 `goodsId`（如 `ESKU000001`） | ≠ `goodsBackId` |
| `imageId` | 官方镜像列表 | |
| `imageVersion` | `image versions` 返回的 **`id`**（如 `V000021`） | ≠ `versionCode` |

Isaac Gym 训练**默认算力与环境**（本仓库 R1-3，与官方 X1 任务一致）：

| 项 | 值 | 说明 |
|:---|:---|:---|
| **算力 goodsId** | `ESKU000001` | 1×4090D 24G |
| **资源 SKU** | `SL00000002` / `SKUSL000002` | gm 后台算力标识 |
| **镜像 imageId** | `BJX00000001` | Isaac GYM:preview-4 |
| **镜像版本 imageVersion** | `V000021` | 对应 `isaac-gym-v14` |
| **容器环境** | Isaac Gym preview-4, Python 3.8.20, PyTorch 2.4.1, Ubuntu 20.04, CUDA 12.1 | |
| **训练 conda 环境** | `pointfoot_legged_gym` | gm 镜像内预装，日志可见 |

换算力/镜像须用户确认后改 `goodsId` / `imageVersion`；用 `gm task resource list` / `gm task image official` 查询。

`create-train.json` 模板：

```json
{
  "taskBaseInfo": {
    "projectId": "<PRO_xxx>",
    "taskType": "1",
    "trainType": "1",
    "taskName": "r1-3-x1-<RUN_NAME>",
    "taskDescription": "R1-3 gm train",
    "taskTag": ["r1-3", "x1_dh_stand"],
    "goodsId": "<ESKU_xxx>",
    "imageId": "BJX00000001",
    "imageVersion": "V000021",
    "personalDataPath": "/personal"
  },
  "taskCodeInfo": {
    "codeType": "2",
    "codeUrl": "[{\"codeUrl\":\"https://github.com/Lee-Weather/agi_origin.git\",\"versionType\":\"1\",\"versionName\":\"main\"}]",
    "mainCodeUri": "agi_origin/humanoid/scripts/train.py",
    "startScript": "gm-run agi_origin/humanoid/scripts/train.py --task=x1_dh_stand --run_name=<RUN_NAME> --headless",
    "isOpen": "1"
  },
  "runtimeReminderConfig": { "enableRuntimeReminder": false, "reminderDurations": [] }
}
```

### 方式 B：复制参考任务后改代码（推荐二次实验）

官方 X1 任务 `TASK_20260701_130`（智元机器人X1）环境与脚本已验证：

```powershell
& $GM task info --task-id "TASK_20260701_130"
```

以 `task info` 返回的 `taskBaseInfo` + `taskCodeInfo` 为基准，**仅改**：

- `codeUrl` → 你的 `agi_origin` 仓库与分支
- `mainCodeUri` / `startScript` → `agi_origin/...` + 新 `run_name`
- `taskName` / `taskTag`

或用 `gm task copy`（见 gm-cli §task copy），再 `gm task edit`（**必须先 info 再全量合并**，见 gm-cli 警告）。

### 创建与运行

```powershell
& $GM task create --file ./create-train.json --dry-run   # exit 10 = OK
& $GM task create --file ./create-train.json             # exit 0，记下 taskId
& $GM task info --task-id "TASK_xxx"                     # 预检 goodsId/镜像/状态
& $GM task run --task-id "TASK_xxx"
```

创建成功后**立即删除** `create-train.json`。

`task run` 前预检（gm-cli）：`goodsId`、`imageId`、`imageVersion` 须完整；草稿态 `taskStatus=0` 最理想，已创建未跑的任务也可 run。

## 阶段 3 — 监控

### 状态码

| taskStatus | 含义 |
|:---:|:---|
| 0 | 草稿 |
| 1 | 排队 |
| 2 | 启动中 |
| 3 | **运行中** |
| 5 | **已完成** |
| 6 | 失败 |
| 7 | 已停止 |

```powershell
& $GM task info --task-id "TASK_xxx"
& $GM task list --status "3" --limit 10
```

### 日志

```powershell
# 单次 JSON
& $GM task logs --task-id "TASK_xxx"

# 跟踪（Agent 可分轮对话，不必长时间 --follow）
& $GM task logs --task-id "TASK_xxx" --follow --interval 2s --timeout 1m

# 纯日志正文
& $GM task logs --task-id "TASK_xxx" --raw --no-request-log
```

### Checkpoint 与 load_run

```powershell
& $GM task model list --task-id "TASK_xxx" --page 1 --limit 20
& $GM task model list --task-id "TASK_xxx" --checkpoint "3000" --limit 1
```

| 变量 | 来源 |
|:---|:---|
| `GM_TASK_ID` | `TASK_xxx` |
| `LOAD_RUN` | 日志目录 `<时间戳><run_name>`，如 `2026-07-02_11-17-44r1_3_test` |
| `CHECKPOINT` | `model list` 中的步数，如 `3000` |
| `COMMIT_SHA` | 阶段 1 的 HEAD |

`task info` 的 `commitId` 应与 `COMMIT_SHA` 一致。

下载模型（可选）：`model list` 的 `policUrlDown` + `curl`（见 gm-cli §模型文件下载）。

## 记录 run 状态

更新 `.cursor/skills/gm-ntb-r1/record-run.json`（勿提交 git）：

```json
{
  "mode": "C",
  "run_name": "<RUN_NAME>",
  "task": "x1_dh_stand",
  "commit_sha": "<COMMIT_SHA>",
  "gm_task_id": "TASK_xxx",
  "train_job_id": "",
  "load_run": "<LOAD_RUN>",
  "checkpoint": "<CHECKPOINT>",
  "test_job_id": ""
}
```

模式 A 将 `"mode"` 设为 `"A"`；每完成一阶段更新对应字段。

## 故障排查

| 现象 | 处置 |
|:---|:---|
| dry-run exit 10 | 正常，去掉 `--dry-run` 再执行 |
| exit 2 `NON_INTERACTIVE` | 危险操作补 `--yes` |
| exit 4 | `gm auth login` / 检查 API Key |
| run 失败 / 资源错误 | `task info` 查 `goodsId`、镜像是否为空 |
| 日志无 iteration | 可能仍在编译 gymtorch，继续轮询 |
| `load_run` 不确定 | 从日志或 gm Web 图表路径推断；格式见 `gm-ntb-r1` |

停止训练（须用户明确要求）：

```powershell
& $GM task stop --task-id "TASK_xxx" --dry-run
& $GM --yes task stop --task-id "TASK_xxx"
```

## 禁止

- 不写 API Key 进 JSON / 对话 / skill
- 不未经 `--yes` 执行 stop/delete
- Agent 不用 `--human`

## 完成后的分支

| 用户意图 | 动作 |
|:---|:---|
| **模式 C** | 汇报四元组 + 更新 `record-run.json`，**结束** |
| **模式 A** | 用户确认训练满意 → **`gm-ntb-ntb-test`** 或编排 **E-gm** |
| **模式 C 完成后「只 test」** | 编排 **模式 E**（读 `record-run.json`） |

模式 C **不要**主动调用 ntb-test。

## 延伸阅读

- 全量 gm-cli：`.trae/skills/gm-cli/SKILL.md`
- 编排与模式：`.cursor/skills/gm-ntb-r1/SKILL.md`
