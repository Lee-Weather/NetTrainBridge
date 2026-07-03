---
name: gm-ntb-r1-e2e
description: >-
  Guides R1-3 E2E from a training code repo (e.g. agi_origin): gm train create/run,
  record load_run, ntb test run --watch, verify real sim2sim. Assumes ntb CLI is
  already installed on the developer Windows PC (PowerShell) or Git Bash. Skill
  lives under .cursor/skills/ in the training repository root. Use for gm to ntb
  validation, R1-3 acceptance, or sim2sim workflow on the training codebase.
---

# gm → ntb R1-3（训练代码仓库 + 本机 CLI）

## Skill 部署位置（必读）

本 Skill 放在**训练代码仓库**根目录下，不是 NetTrainBridge 仓库：

```text
<训练仓库>/                    # 如 agi_origin，Cursor 打开此目录
├── .cursor/skills/gm-ntb-r1-e2e/
│   ├── SKILL.md
│   └── scripts/
├── humanoid/scripts/train.py
├── humanoid/scripts/play.py
├── create-train.json          # 可选，放仓库根
└── ...
```

**假定**：

- `ntb` CLI **已安装**且在 PATH（不要引导用户 `pip install` NetTrainBridge）
- `gm` CLI 已安装（`npm i -g @limxdynamics/gm-cli`）
- 所有 `git` / `gm` / `ntb` 命令在**训练仓库根目录**执行（无需再 `cd` 到别的路径）
- `ntb config` 已指向云 Server（`%USERPROFILE%\.nettrainbridge\config.json`）

**仓库名变量**：gm clone 后的顶层目录名 = 当前 git 仓库文件夹名。用于 `create-train.json` 的 `mainCodeUri` / `startScript`：

```powershell
# PowerShell
$REPO_DIR = Split-Path -Leaf (git rev-parse --show-toplevel)
# 例: agi_origin → mainCodeUri = agi_origin/humanoid/scripts/train.py
```

```bash
REPO_DIR=$(basename "$(git rev-parse --show-toplevel)")
```

---

## Windows 用户

默认 **PowerShell**；不要用 CMD 的 `export` / `/tmp`。

| 项 | 说明 |
|:---|:---|
| preflight | `powershell -ExecutionPolicy Bypass -File .cursor\skills\gm-ntb-r1-e2e\scripts\preflight.ps1` |
| verify-test | `powershell -File .cursor\skills\gm-ntb-r1-e2e\scripts\verify-test.ps1 <id> -Source gm` |
| commit | `$env:COMMIT_SHA = git rev-parse HEAD` |
| 续行 | PowerShell 用 `` ` `` |

Git Bash 可用 `.sh` 脚本，语法同 Linux。

---

## 三端分工

| 位置 | 职责 | 本 Skill |
|:---|:---|:---|
| **本机（训练仓库）** | `gm`、`ntb`、git | ✅ 直接操作 |
| **云 Server** | 任务调度 | 经 `ntb` 访问 |
| **公司训练机** | Agent + Isaac | ❌ 不 SSH；提醒用户先启动 Agent |

扩展阅读（NetTrainBridge 仓库内文档，可选）：`plan/r1-3-manual-acceptance.md`、`plan/diff/gm-cli/SKILL.md`

---

## 启动时必做

在**训练仓库根目录**执行 preflight；失败则只修环境，不创建任务。

向用户确认（若未给出）：

- 场景 A（gm 训练 → test）或 B（ntb 训练 → test）
- `RUN_NAME`（拼进 `load_run`，如 `r1_3_test`）
- `create-train.json` 是否已有，或需新建

---

## 场景 A：gm 训练 → ntb test

### 阶段 1 — 推送（当前仓库）

```powershell
git push origin main
$env:COMMIT_SHA = git rev-parse HEAD
```

### 阶段 2 — gm 训练

**人工卡点**：`projectId` / `goodsId` / 镜像需用户确认。

`create-train.json` 中路径用 `$REPO_DIR`（见上），示例：

```json
"mainCodeUri": "<REPO_DIR>/humanoid/scripts/train.py",
"startScript": "gm-run <REPO_DIR>/humanoid/scripts/train.py --task=x1_dh_stand --run_name=r1_3_test --headless"
```

```bash
gm task create --file ./create-train.json --dry-run
gm task create --file ./create-train.json
gm task run --task-id "task_gm_xxx"
gm task logs --task-id "task_gm_xxx" --follow
```

训练未完成 **禁止** 进入 test；长任务用 `gm task info` 轮询，可分多轮对话。

### 阶段 3 — 记录参数

```bash
gm task model list --task-id "task_gm_xxx" --page 1 --limit 20
```

记下 `GM_TASK_ID`、`LOAD_RUN`、`CHECKPOINT`、`COMMIT_SHA`。  
**人工卡点**：用户确认训练满意后再 test。

### 阶段 4 — ntb test

```powershell
ntb test run `
  --gm-task-id $GM_TASK_ID `
  --load-run $LOAD_RUN `
  --task x1_dh_stand `
  --checkpoint $CHECKPOINT `
  --commit $env:COMMIT_SHA `
  --watch
```

默认不传 `--repo` / `--commit` 时，`ntb` 会读当前 git 仓库的 `origin` 与 `HEAD`；显式传 `--commit` 须与 gm 训练 push 的 SHA 一致。

约 **9 分钟**（真实 Isaac play）。

### 阶段 5 — 验收

```powershell
powershell -File .cursor\skills\gm-ntb-r1-e2e\scripts\verify-test.ps1 <test_job_id> -Source gm
```

---

## 场景 B：ntb 训练 → ntb test

在本仓库根目录：

1. `ntb train run --watch`
2. `ntb checkpoint list <train_job_id>`
3. `ntb test run --train-job-id ... --load-run ... --checkpoint 3000 --commit ... --watch`
4. `verify-test.ps1 ... -Source ntb`

---

## Agent（训练机，非本机）

训练机 `config.json` 需 `gm_api_key` / `gm_base_url`（与家里 gm 同账号）。本机 **不装 gm 给 Agent 用**。

---

## 禁止事项

- 不写 API Key 进 Skill / 脚本
- 不未经 `--yes` 执行 `ntb jobs clear`
- 不用 Mock：`NETTRAINBRIDGE_TEST_COMMAND=...--mock`
- gm 写操作先 `--dry-run`；`stop`/`delete` 加 `--yes`

---

## 脚本

| 脚本 | 平台 | 时机 |
|:---|:---|:---|
| `scripts/preflight.ps1` | Windows | 操作前 |
| `scripts/verify-test.ps1` | Windows | test 后 |
| `scripts/preflight.sh` | Git Bash | 操作前 |
| `scripts/verify-test.sh` | Git Bash | test 后 |

Windows 默认跑 `.ps1`。所有脚本路径相对于**训练仓库根目录**。

---

## 汇报模板

```text
【R1-3 进度】训练仓库: <REPO_DIR>
阶段: N / 名称
GM_TASK_ID / TEST_JOB_ID / LOAD_RUN
状态: 进行中 | 等待确认 | 完成
下一步: ...
```
