---
name: gm-ntb-ntb-train
description: >-
  Run ntb cloud training only (mode D) or as step before ntb test (mode B): ntb train run
  --watch, checkpoint list, record TRAIN_JOB_ID LOAD_RUN CHECKPOINT. ntb in conda env
  via ntb.ps1. Use for ntb train only, ntb training. NOT for gm train or ntb test alone.
  Run gm-ntb-preflight -For ntb first. For mode selection see gm-ntb-r1.
---

# ntb 云训练

适用编排模式：**B**（ntb 训练 → 后续 test）、**D**（仅 ntb 训练，**不**进入 ntb test）。

## 前置

```powershell
powershell -File .cursor\skills\gm-ntb-preflight\scripts\preflight.ps1 -For ntb
```

确认训练机 Agent 已启动（ntb 训练也依赖 Agent）。

## 包装脚本

```powershell
$NTB = "powershell -File .cursor\skills\gm-ntb-preflight\scripts\ntb.ps1"
$env:COMMIT_SHA = git rev-parse HEAD
```

## 训练

```powershell
& $NTB train run --task x1_dh_stand --run-name <RUN_NAME> --watch
```

记下 `TRAIN_JOB_ID`（命令输出或 `ntb job list`）。

## 查 checkpoint

```powershell
& $NTB checkpoint list <TRAIN_JOB_ID>
```

| 变量 | 说明 |
|:---|:---|
| `TRAIN_JOB_ID` | ntb 训练 job ID |
| `LOAD_RUN` | `<时间戳><run_name>` |
| `CHECKPOINT` | 如 `3000` |
| `COMMIT_SHA` | 当前 HEAD |

## load_run 格式

```text
2026-01-14_09-58-10test_20_video = <时间戳> + <run_name>（无分隔符）
```

产物路径：`logs/x1_dh_stand/exported_data/<load_run>/model_<N>.pt`

可选：写入 `record-run.json`（`"mode": "D"` 或 `"B"`）。

## 完成后的分支

| 用户意图 | 动作 |
|:---|:---|
| **模式 D**（仅训练） | 汇报 `TRAIN_JOB_ID` / `LOAD_RUN` / `CHECKPOINT` / `COMMIT_SHA`，**结束** |
| **模式 B**（还要 test） | 用户确认后 → **`gm-ntb-ntb-test`** 或编排 **E/B** |
| **模式 D 完成后用户说「只 test」** | 编排 **E-ntb** |

模式 D 下**不要**主动调用 ntb-test，除非用户改口要做全流程。
