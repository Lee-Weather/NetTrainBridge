---
name: gm-ntb-preflight
description: >-
  R1-3 startup checks for gm/ntb workflow on training repo: conda ntb env, ntb health,
  gm auth, train.py exists. Provides gm.ps1 and ntb.ps1 wrappers. Use for preflight,
  environment check, ntb health, before gm train, ntb train, or ntb test-only (mode E).
---

# gm-ntb 启动检测

在**训练仓库根目录**执行；失败则只修环境，不创建任务。

## 脚本路径（相对训练仓库根）

| 脚本 | 用途 |
|:---|:---|
| `.cursor/skills/gm-ntb-preflight/scripts/preflight.ps1` | 全量检测 |
| `.cursor/skills/gm-ntb-preflight/scripts/gm.ps1` | gm 包装（PowerShell 须用，避免 `gm`→`Get-Member`） |
| `.cursor/skills/gm-ntb-preflight/scripts/ntb.ps1` | ntb 包装（conda env `ntb`） |

Git Bash 用对应 `.sh`。

## 执行

```powershell
# 全量（默认）
powershell -ExecutionPolicy Bypass -File .cursor\skills\gm-ntb-preflight\scripts\preflight.ps1

# 仅 gm 路径
powershell -File .cursor\skills\gm-ntb-preflight\scripts\preflight.ps1 -For gm

# 仅 ntb 路径
powershell -File .cursor\skills\gm-ntb-preflight\scripts\preflight.ps1 -For ntb
```

## 环境要求

| 组件 | 要求 |
|:---|:---|
| **gm** | `npm i -g @limxdynamics/gm-cli`；PowerShell 经 `gm.ps1` 调用 |
| **ntb** | 安装在 conda 环境 `ntb`（`NTB_CONDA_ENV` 可覆盖） |
| **ntb config** | `%USERPROFILE%\.nettrainbridge\config.json` 指向云 Server |

交互式终端可 `conda activate ntb` 后直接 `ntb`；Agent 必须用 `ntb.ps1`。

## 通过后（按模式）

| 模式 | preflight | 下一步 |
|:---|:---|:---|
| A 全流程（gm 路径） | `-For all` 或 `-For gm` 再 `-For ntb` | `gm-ntb-gm-train` |
| B 全流程（ntb 路径） | `-For ntb` | `gm-ntb-ntb-train` |
| C 仅 gm 训练 | `-For gm` | `gm-ntb-gm-train` |
| D 仅 ntb 训练 | `-For ntb` | `gm-ntb-ntb-train` |
| **E 仅 test** | **`-For ntb`** | `gm-ntb-ntb-test` |

## 故障排查

| 现象 | 处置 |
|:---|:---|
| `ntb: command not found` | 用 `ntb.ps1` 或 `conda activate ntb` |
| `ntb health` 失败 | 检查 `config.json` 的 `server_url` |
| `gm` 在 PS 报错 | 必须用 `gm.ps1`，不要裸调 `gm` |
