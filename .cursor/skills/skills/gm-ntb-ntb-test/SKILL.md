---
name: gm-ntb-ntb-test
description: >-
  ntb sim2sim test and verify: modes A/B after training, or E test-only with existing
  GM_TASK_ID or TRAIN_JOB_ID plus LOAD_RUN CHECKPOINT. ntb test run --watch, verify-test.
  Use for ntb test only, sim2sim, verify, test-only mode E. Run gm-ntb-preflight -For ntb.
  Requires checkpoint; Agent must be running.
---

# ntb 测试与验收

适用编排模式：

| 模式 | 说明 |
|:---|:---|
| **A** | gm 训练后 test（`--source gm`） |
| **B** | ntb 训练后 test（`--source ntb`） |
| **E** | **仅 test**，不训练；从 `record-run.json` 或用户参数读取 |

模式 C/D 默认不进本 skill；用户说「只 test / 跑 test」→ **模式 E**。

## 前置

1. `gm-ntb-preflight -For ntb` 通过
2. 已有 `LOAD_RUN` + `CHECKPOINT` + `COMMIT_SHA`
3. **训练机 Agent 已启动**
4. 模式 E：确认 `test_source` 为 `gm` 或 `ntb`，并有所需 task id

读本地状态（模式 E 推荐）：

```powershell
powershell -File .cursor\skills\gm-ntb-r1\scripts\read-record-run.ps1 -ExportEnv
```

## 包装脚本

```powershell
$NTB = "powershell -File .cursor\skills\gm-ntb-preflight\scripts\ntb.ps1"
```

## test run

### source = gm（模式 A / E-gm）

```powershell
& $NTB test run `
  --gm-task-id $env:GM_TASK_ID `
  --load-run $env:LOAD_RUN `
  --task x1_dh_stand `
  --checkpoint $env:CHECKPOINT `
  --commit $env:COMMIT_SHA `
  --watch
```

### source = ntb（模式 B / E-ntb）

```powershell
& $NTB test run `
  --train-job-id $env:TRAIN_JOB_ID `
  --load-run $env:LOAD_RUN `
  --task x1_dh_stand `
  --checkpoint $env:CHECKPOINT `
  --commit $env:COMMIT_SHA `
  --watch
```

`--commit` 须与训练时 push 的 SHA 一致。约 **9 分钟**（真实 Isaac play）。

## 验收

```powershell
powershell -File .cursor\skills\gm-ntb-ntb-test\scripts\verify-test.ps1 <TEST_JOB_ID> -Source gm
powershell -File .cursor\skills\gm-ntb-ntb-test\scripts\verify-test.ps1 <TEST_JOB_ID> -Source ntb -Commit $env:COMMIT_SHA
```

通过后更新 `record-run.json` 的 `test_job_id`，`mode` 可记为 `E`。

## 禁止

- 不用 Mock
- 不未经 `--yes` 执行 `ntb jobs clear`
- 模式 E 缺参数时不猜测 `load_run`，向用户确认

## 故障排查

| 现象 | 处置 |
|:---|:---|
| test 长时间 PENDING | 确认 Agent |
| verify `summary not real` | 禁止 mock |
| `load_run` 找不到 | `logs/x1_dh_stand/exported_data/<load_run>/model_<N>.pt` |
| `commit_sha` 不一致 | 对齐训练 commit |

## CLI 参考

命令参数、状态机、验收字段详见 [czy/skills/cli-readme.md](../../../czy/skills/cli-readme.md)（`test run`、`metrics`、`artifacts` 等）。
