# Checkpoint 中转（CLI → Server → Agent）

> **状态**：已落地（0.2 默认路径）  
> **原则**：gm 训练后的 `ntb test run` 默认由**家里**取模并上传 Server；训练机 Agent **默认不需要** gm API Key / OSS。

---

## 1. 为什么要中转

| 旧路径（`--fetch-from-gm`） | 新默认（Plan 03） |
|:---|:---|
| 训练机 Agent 直拉 gm + OSS | 家里 CLI 取模 → 上传 Server |
| 训练机需 `gm_api_key` + 代理/OSS | 训练机只连 Server + GitHub |
| phase：`sync → fetch → test` | phase：`sync → pull → test` |

问题背景：训练机经公司代理访问 OSS 易 403；凭证双份维护成本高。

---

## 2. 架构

```text
家里 gm CLI / ntb
  │  gm task model list + 下载 policUrlDown
  │  POST /jobs（test）+ POST /checkpoint
  ▼
云 Server  data/{test_job_id}/models/
  │  Agent GET /checkpoint
  ▼
训练机 Agent
  落盘 logs/{task}/exported_data/{load_run}/model_*.pt
  → test_with_metrics.py → play.py
  → 上传 isaac_diag_*.csv；流式 POST /metrics
```

| 入口 | `train_source` | 模型在 Server 的位置 |
|:---|:---|:---|
| `--gm-task-id`（默认） | `gm` | **本 test job** `models/`（家里 stage） |
| `--train-job-id` | `ntb` | **父 train job** `models/` |
| `--fetch-from-gm` | `gm` | Agent 直拉 gm（兜底，需训练机 gm 配置） |

---

## 3. 关键 meta / phase

| 字段 | 说明 |
|:---|:---|
| `fetch_mode` | `server`（默认）\| `gm`（兜底） |
| `checkpoint_staged` | 家里已上传模型到本 job |
| `load_run` / `checkpoint` / `task` | play 加载参数 |
| `gm_task_id` / `gm_checkpoint` | 追溯用 |
| `test_artifact` | 成功后写入的 CSV 文件名（可选） |

```text
gm 默认：     sync → pull → test → done
gm 兜底：     sync → fetch → test → done   # --fetch-from-gm
ntb 父任务：  sync → test → done
```

---

## 4. 家里用法

```powershell
# 默认：自动 stage-from-gm 再 watch
ntb test run `
  --gm-task-id TASK_xxx `
  --load-run 2026-07-01_10-00-00r1_3_test `
  --checkpoint 50 `
  --commit <sha> `
  --watch

# 分步（调试 / 大模型）
ntb test run ... --no-stage-checkpoint
ntb checkpoint stage-from-gm <test_job_id> --task-id TASK_xxx --checkpoint 50
ntb watch <test_job_id>
```

配置（家里 `cli` 段）：

```json
{
  "cli": {
    "server_url": "http://<云IP>:8000",
    "gm_api_key": "<与 gm CLI 同账号>",
    "gm_base_url": "https://internal.limxdynamics.com/dev-api"
  }
}
```

训练机 `agent` 段**默认无需** `gm_api_key`（仅 `--fetch-from-gm` 时需要）。

---

## 5. 产物约定（0.2）

| 数据 | 路径 / 命令 |
|:---|:---|
| 流式 test 指标 | `ntb metrics <id>`（SQLite，保留） |
| 诊断 CSV | Server `data/{id}/test/isaac_diag_*.csv` → `ntb artifacts download` |
| 本地 summary | 训练机 `{job}/test/summary.json`（可不上传） |

详见 [acceptance.md](acceptance.md)。
