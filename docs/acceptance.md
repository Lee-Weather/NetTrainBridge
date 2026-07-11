# sim2sim 验收清单（R1-3）

端到端：家里 `ntb test run` → Server → Agent → 真实 `play.py`（Isaac）。单次真实 test 约 **9 分钟**。

---

## 一、开工前（三端）

### 云 Server

```bash
conda activate nettrain
cd server && python main.py
curl http://<云IP>:8000/health
```

### 训练机 Agent

```bash
conda activate F1
cd agent && python agent.py
```

`~/.nettrainbridge/config.json` 的 `agent` 段：`server_url`、`proxy`、`workspace`、`conda_env=F1`。  
**不要**设置 `NETTRAINBRIDGE_TEST_COMMAND=...--mock...`。  
默认路径**不需要** `agent.gm_api_key`。

### 家里 CLI

```bash
pip install -e ".[dev]"
ntb config init --server-url http://<云IP>:8000
# 编辑 cli.gm_api_key / gm_base_url（gm test 必需）
ntb health
```

### 必填参数

| 参数 | 说明 | 示例 |
|:---|:---|:---|
| `load_run` | `{date_time}{run_name}`，无分隔符 | `2026-07-01_10-00-00r1_3_test` |
| `checkpoint` | gm：`latest` / `50`；ntb：整数 | `50` |
| `commit` | 与训练代码一致的 SHA | `git rev-parse HEAD` |
| `gm-task-id` 或 `train-job-id` | 二选一 | `TASK_20260702_088` |

训练仓 `play.py` 须支持 `NETTRAINBRIDGE_PLAY_RENDER=0`（headless 不录屏），否则相机会崩溃。

---

## 二、场景 A：gm 训练 → ntb test（主路径）

```powershell
ntb test run `
  --gm-task-id TASK_xxx `
  --load-run <load_run> `
  --task x1_dh_stand `
  --checkpoint latest `
  --commit $env:COMMIT_SHA `
  --watch
```

Agent 阶段：`sync → pull → test → done`（默认；不是 fetch）。

训练机检查：

```bash
WS=~/czy/nettrainbridge
JOB=<test_job_id>
ls $WS/$JOB/logs/x1_dh_stand/exported_data/<load_run>/model_*.pt
ls $WS/$JOB/test/isaac_diag_*.csv
tail -f $WS/$JOB/test/test.log
```

---

## 三、场景 B：ntb 训练 → ntb test

```powershell
ntb test run `
  --train-job-id <train_job_id> `
  --load-run <load_run> `
  --checkpoint 3000 `
  --commit $env:COMMIT_SHA `
  --watch
```

`--checkpoint` 必须是整数。阶段：`sync → test → done`（无 pull/fetch）。

---

## 四、验收清单

### A. 任务状态（家里）

| # | 检查项 | 预期 |
|:--|:---|:---|
| A1 | `ntb job` 类型 | `job_type=test` |
| A2 | `train_source` | gm / ntb 与入口一致 |
| A3 | 状态 | `COMPLETED`，`phase=done` |
| A4 | 无 `error_msg` | 空 |
| A5 | meta | 含 `load_run`、`checkpoint`、`task` |
| A6 | commit | 与 `--commit` 一致 |

### B. 训练机布局

| # | 路径 | 预期 |
|:--|:---|:---|
| B1 | `{job}/` | 含 `humanoid/scripts/play.py` |
| B2 | `logs/.../exported_data/<load_run>/model_*.pt` | 存在 |
| B3 | `{job}/test/isaac_diag_*.csv` | 至少 1 个 |
| B4 | `{job}/test/test.log` | 含 `real sim2sim complete` |

### C. 家里指标与产物

| # | 命令 | 预期 |
|:--|:---|:---|
| C1 | `ntb metrics <id>` | 有 `kind=test`，**无** `"mock": true` |
| C2 | `ntb artifacts list` | 含 `isaac_diag_*.csv` |
| C3 | `ntb artifacts download` | zip 内为 CSV（无 summary/metrics.jsonl） |
| C4 | `ntb checkpoint list` | 有 `.pt`（gm stage 或父任务） |

本地分析 CSV：用 `.cursor/skills/isaac-diag-eval`。

### D. 场景差异

| # | 场景 | 预期 |
|:--|:---|:---|
| D1 | gm 默认 | 曾经过 `pull`（不是必须 `fetch`） |
| D2 | gm | `gm_task_id` 正确；`fetch_mode=server` |
| D3 | ntb | `parent_train_job_id` 正确；无 gm FETCH 日志 |

### 一键验收（可选）

```powershell
# 本仓 skill（复制到训练仓后路径可能不同）
powershell -File .cursor\skills\gm-ntb-ntb-test\scripts\verify-test.ps1 <test_job_id> -Source gm
```

---

## 五、常见失败

| 现象 | 处理 |
|:---|:---|
| PULL 超时 | `ntb checkpoint list`；重跑 `stage-from-gm` |
| 相机 / reshape 崩溃 | 训练仓 `play.py` 关录屏（`PLAY_RENDER=0`） |
| artifacts 无 CSV | test 须 COMPLETED；看训练机 `test.log` |
| metrics 含 mock | 去掉 Agent 的 mock `TEST_COMMAND` |
