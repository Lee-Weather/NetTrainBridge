# v0.2 手动操作命令手册（gm 训练 + ntb 兜底 + 可选 test）

> 对应架构：[plan02-gm-ntb-framework.md](plan02-gm-ntb-framework.md)  
> 步骤 10 人工验收用。当前 sim2sim 为 **Mock**（`test_with_metrics.py --mock`），指标为占位值。

---

## 1. 角色与分工

| 在哪里执行 | 谁 | 做什么 |
|:---|:---|:---|
| **家里** | 开发者 | `git push`、gm CLI、`ntb` 创建/监控任务、下载结果 |
| **gm 云端** | Gradmotion | **主路径训练**（默认） |
| **公司训练机** | NTB Agent | 兜底训练、sync、test（含 gm FETCH） |
| **云 Server** | FastAPI | 任务调度、存指标/模型/测试产物 |

**原则**：

- **gm 训练不依赖 NTB**（步骤 10 场景 1）。
- **ntb train run** 仅在 gm 不可用或需公司环境训练时使用（场景 2）。
- **ntb test run** 为可选，人看完训练结果后再决定是否执行（场景 3、4）。

---

## 2. 开工前检查（三端）

### 2.1 云 Server

```bash
cd server
conda activate nettrain
python main.py
# 另开终端：
curl http://<云IP>:8000/health    # → {"status":"ok"}
```

### 2.2 公司训练机 Agent

```bash
cd agent
conda activate F1
python agent.py
```

`~/.nettrainbridge/config.json` 中 `agent` 段至少包含：

```json
{
  "agent": {
    "server_url": "http://<云IP>:8000",
    "proxy": "http://<公司代理>:端口",
    "agent_id": "agent-001",
    "workspace": "~/czy/nettrainbridge",
    "conda_env": "F1",
    "train_command": "python humanoid/scripts/train_with_metrics.py --task=x1_dh_stand --run_name={job_id} --headless"
  }
}
```

**若要走 gm → test**，训练机还需（环境变量或配置）：

```bash
export GM_API_KEY="<你的 gm API Key>"
export GM_BASE_URL="https://<gm 服务地址>"
# 仓库尚无 test 脚本时：
export NETTRAINBRIDGE_TEST_SCRIPT="python /path/to/NetTrainBridge/contrib/agi_origin/humanoid/scripts/test_with_metrics.py --mock --checkpoint={checkpoint_path} --headless"
```

### 2.3 家里 CLI

```bash
pip install -e ".[dev]"
ntb config init --server-url http://<云IP>:8000
ntb health
```

gm CLI（主路径训练）需已 `gm auth login` 或配置 `GM_API_KEY`。

---

## 3. 路径 A：gm 训练（主路径）

**NTB 不参与训练**，只在你决定做 sim2sim 时才用 `ntb test run`。

### 3.1 推送代码

```bash
cd agi_origin          # 或你的训练仓库
git add .
git commit -m "..."
git push origin main
```

记下 commit SHA（test 时 `--commit` 用）：

```bash
git rev-parse HEAD
```

### 3.2 在 gm 上创建并运行训练

```bash
# 按项目准备 create-train.json 后：
gm task create --file ./create-train.json
gm task run --task-id "task_gm_xxx"

# 监控
gm task logs --task-id "task_gm_xxx" --follow

# 查看 checkpoint 列表（决策 test 时用）
gm task model list --task-id "task_gm_xxx" --page 1 --limit 20
```

记下 **`task_gm_xxx`** 与目标 checkpoint（如 `latest` 或 `model_3000.pt`）。

### 3.3 验收（仅训练，场景 1）

| 检查项 | 命令 / 方式 |
|:---|:---|
| 训练在 gm 完成 | `gm task info --task-id task_gm_xxx` |
| 曲线 / 指标 | `gm task logs` / `gm task data get` |
| checkpoint | `gm task model list` |
| **无需** NTB job | 此阶段无 `ntb train run` |

---

## 4. 路径 A 续：gm 训练 → ntb test（可选，场景 3）

人为主观决策：对 gm 训练结果满意后再执行。

### 4.1 家里创建 test job

```bash
cd agi_origin    # 与 push 同一仓库，默认读 origin / HEAD

ntb test run \
  --gm-task-id task_gm_xxx \
  --checkpoint latest \
  --commit <与测试代码一致的 SHA> \
  --watch
```

说明：

- `--gm-task-id` 与 `--train-job-id` **二选一**。
- `--checkpoint` 默认 `latest`；也可 `model_3000.pt` 等。
- Agent 自动：`sync` → **gm FETCH (5B)** → **Mock sim2sim** → 上传产物。

### 4.2 监控与取结果

```bash
ntb job <test_job_id>              # type=test, train_source=gm, phase=done
ntb metrics <test_job_id>          # Mock 测试指标（kind=test）
ntb logs <test_job_id>
ntb logs <test_job_id> -f

ntb checkpoint list <test_job_id>    # gm 拉取并上传的模型
ntb checkpoint download <test_job_id> -o ./model.pt

ntb artifacts list <test_job_id>    # summary.json, metrics.jsonl
ntb artifacts download <test_job_id> -o ./test-artifacts.zip
```

### 4.3 预期

| 项 | 预期 |
|:---|:---|
| 任务状态 | `COMPLETED`，`phase=done` |
| Server 目录 | `data/<test_job_id>/models/*.pt` |
| 测试产物 | `data/<test_job_id>/test/summary.json` |
| sim2sim | **Mock**，`summary.json` 中 `"mode": "mock"` |

---

## 5. 路径 B：ntb 兜底训练（场景 2）

gm 不可用、或必须在公司训练机环境跑训练时使用。

### 5.1 推送代码

```bash
cd agi_origin
git push origin main
```

### 5.2 家里触发兜底训练

```bash
ntb train run --watch
# 或显式指定：
ntb train run --repo https://github.com/<org>/agi_origin.git --commit $(git rev-parse HEAD) --watch
```

Agent 流程：`clone` → `train_with_metrics.py` → 上传 checkpoint → `COMPLETED`。

### 5.3 验收（仅训练）

```bash
ntb job <train_job_id>              # type=train, train_source=ntb, COMPLETED
ntb metrics <train_job_id>
ntb logs <train_job_id>

ntb checkpoint list <train_job_id>
ntb checkpoint download <train_job_id> -o ./train_model.pt
```

记下 **`<train_job_id>`**，供下一步 test 使用。

---

## 6. 路径 B 续：ntb 训练 → ntb test（可选，场景 4）

```bash
ntb test run \
  --train-job-id <train_job_id> \
  --commit <与测试代码一致的 SHA> \
  --watch
```

说明：

- **不会**调用 gm API / FETCH。
- Agent 从 Server 下载父训练任务的 checkpoint，再跑 Mock sim2sim。

验收命令同 [§4.2](#42-监控与取结果)，但 `train_source=ntb`，且无 `gm_task_id`。

---

## 7. 仅同步代码：ntb sync（场景 5）

不训练、不测试，只让训练机 clone 指定 commit。

```bash
cd agi_origin
git push origin main

ntb sync --commit $(git rev-parse HEAD)
ntb job <sync_job_id>    # type=sync, COMPLETED；无 checkpoint / test 产物
```

---

## 8. 步骤 10 验收清单（对照打勾）

| # | 场景 | 关键输入命令 | 通过标准 |
|:---|:---|:---|:---|
| 1 | gm 主路径训练 | `git push` → `gm task create/run` | gm 任务完成；**无需 NTB** |
| 2 | ntb 兜底训练 | `ntb train run --watch` | `COMPLETED`；`checkpoint list` 有 `.pt` |
| 3 | gm → test | `ntb test run --gm-task-id ... --watch` | `models/` + `test/summary.json`；Mock 指标 |
| 4 | ntb → test | `ntb test run --train-job-id ... --watch` | 无 gm fetch；同上 |
| 5 | 仅 sync | `ntb sync` | `job_type=sync`，`COMPLETED` |
| 6 | 自动化回归 | 见下节 | 全绿（Webhook 段可忽略） |

---

## 9. 自动化回归（云 Server 上执行）

```bash
cd server
bash test_v02_artifacts.sh http://localhost:8000
bash test_v02_step8_test.sh http://localhost:8000
bash test_e2e.sh http://localhost:8000          # §15 Webhook 两项已知例外
bash test_phase3.sh http://localhost:8000
bash test_cli.sh http://localhost:8000
```

---

## 10. 命令速查表

### gm（训练主路径）

| 目的 | 命令 |
|:---|:---|
| 创建任务 | `gm task create --file ./create-train.json` |
| 运行 | `gm task run --task-id "task_gm_xxx"` |
| 日志 | `gm task logs --task-id "task_gm_xxx" --follow` |
| 模型列表 | `gm task model list --task-id "task_gm_xxx"` |

### ntb（兜底 / 测试 / 同步）

| 目的 | 命令 |
|:---|:---|
| 健康检查 | `ntb health` |
| 兜底训练 | `ntb train run [--repo URL] [--commit SHA] [--watch]` |
| gm 后测试 | `ntb test run --gm-task-id <id> [--checkpoint latest] [--commit SHA] [--watch]` |
| ntb 后测试 | `ntb test run --train-job-id <train_id> [--commit SHA] [--watch]` |
| 仅同步 | `ntb sync [--commit SHA]` |
| 任务详情 | `ntb job <id>` |
| 监控 | `ntb watch <id>` |
| 指标 / 日志 | `ntb metrics <id>` / `ntb logs <id> [-f]` |
| 下载模型 | `ntb checkpoint list/download <id>` |
| 下载测试产物 | `ntb artifacts list/download <id> -o xxx.zip` |

---

## 11. 常见决策树

```text
git push
    │
    ├─ gm 可用？ ──是──▶ gm task run（主路径）
    │                      │
    │                      └─ 满意？ ──是──▶ ntb test run --gm-task-id ...
    │
    └─ gm 不可用 / 需公司环境 ──▶ ntb train run
                                    │
                                    └─ 满意？ ──是──▶ ntb test run --train-job-id ...

仅需训练机有代码、不训练 ──▶ ntb sync
```

---

## 12. 当前限制（v0.2）

| 项 | 说明 |
|:---|:---|
| sim2sim | **Mock 占位**，非真实 Isaac 仿真（R1 接 `play.py`） |
| gm 训练 | 不由 NTB 自动触发，需人工 `gm task run` |
| test 触发 | 不自动；需人工 `ntb test run` |
| `ntb doctor` | 未实现（可选后续） |
| Webhook 自动建任务 | 默认关闭；用手动 `ntb train run` / `ntb test run` |

---

## 13. 相关文档

- 架构框架：[plan02-gm-ntb-framework.md](plan02-gm-ntb-framework.md)
- 分步实现：[plan02-implementation.md](plan02-implementation.md)
- sim2sim 分阶段：[sim2sim-framework.md](sim2sim-framework.md)
- gm CLI 参考：[diff/gm-cli/SKILL.md](diff/gm-cli/SKILL.md)
- 仓库操作总览：[../README.md](../README.md)
