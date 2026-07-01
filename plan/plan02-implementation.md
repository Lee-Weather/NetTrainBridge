# NetTrainBridge v0.2 分步实现计划

> 依据 [plan02-gm-ntb-framework.md](plan02-gm-ntb-framework.md) 拆解为可编码、可验收的步骤。  
> **原则**：每步合并前必须通过本步测试 + 回归 v0.1 基线；**gm 主路径不依赖 NTB 代码**。

---

## 总览

| 步骤 | 对应框架 | 交付概要 | 预估依赖 |
|:---|:---|:---|:---|
| **0** | 基线 | 确认 v0.1 全绿，锁定回归命令 | — | ✅ |
| **1** | P0 + P1 前半 | CLI：`ntb train run` / deprecated `trigger` | 0 | ✅ |
| **2** | P1 后半 | Server：`job_type` 等字段 + 创建 API | 1 | ✅ |
| **3** | P1 | Agent + `ntb sync`：仅 clone | 2 | ✅ |
| **4** | P0 | Agent：`job_type=train` 显式化（兜底训练不退化） | 2 | ✅ |
| **5** | P2 前半 | Server：`meta.json`、test job 扩展字段、阶段状态 | 2 | ✅ |
| **6** | P2 后半 | Agent：gm FETCH (5B) + 上传 Server | 3, 5 | ✅ |
| **7** | P3 前半 | contrib：`test_with_metrics.py` **框架 + Mock**（真实 sim2sim 见 R1） | 4 | ✅ |
| **8** | P3 后半 | Agent + CLI：`ntb test run` 全流程（**全程 Mock 脚本**） | 6, 7 | ✅ |
| **9** | P4 | `ntb checkpoint` / `ntb artifacts` + Server 列表下载 API | 8 | ✅ |
| **10** | P5 | 文档、gm 提示、端到端验收 | 9 | 📋 见 [manual-operations-v02.md](manual-operations-v02.md) |

```text
0 → 1 → 2 → 3 ─┐
         └→ 4 ──┼→ 5 → 6 → 8 → 9 → 10
              └→ 7 ────────┘
```

---

## 步骤 0：基线锁定（开工前）

> **状态：✅ 已完成**（人工验收）— 详见 [baseline-step0.md](baseline-step0.md)

### 实现内容

- 无功能代码；记录当前可运行的回归命令与版本。
- 确认 README 描述的 `ntb trigger`、Agent 训练、checkpoint 上传均可工作。

### 测试

```bash
# 云服务器目录
cd server
bash test_e2e.sh http://localhost:8000
bash test_phase3.sh http://localhost:8000
bash test_cli.sh http://localhost:8000
```

**通过标准**：三个脚本全绿；手动一次 `ntb trigger`（或现有命令）+ Agent 能跑到 `COMPLETED`（有 GPU/环境时）或至少 `ASSIGNED→RUNNING`（无 GPU 时可测到 claim + clone）。

**已知例外（已接受）**：GitHub Webhook 已关闭（手动 trigger 模式），`test_e2e.sh` §15/§15b、`test_phase3.sh` §2 的 Webhook 用例**不计入失败**。v0.2 回归可跳过该段或后续拆 `test_v02_regression.sh`。

---

## 步骤 1：CLI 6A 入口（不动 Server 行为）

> **状态：✅ 已完成** — 验收：`bash server/test_v02_step1.sh`

### 实现功能

| 模块 | 改动 |
|:---|:---|
| `cli/nettrainbridge_cli/main.py` | 新增子命令组 `ntb train run`（逻辑等同现有 `trigger`） |
| 同上 | 新增 `ntb sync` 占位：暂仍创建普通 job 或返回「未实现」；**本步可先只做 `train run`** |
| 同上 | `ntb trigger` 保留，打印 deprecated 警告，转发到 `train run` |
| `pyproject.toml` | 版本可仍为 `0.1.x` 或 `0.2.0-dev` |

### 测试

```bash
pip install -e ".[dev]"
ntb train run --help
ntb trigger 2>&1 | grep -i deprecat    # 应有警告
NTB=python3 cli/ntb.py bash server/test_cli.sh http://localhost:8000  # 改脚本中 trigger 为 train run（可选）
```

**通过标准**：

- `ntb train run` 创建的 job 与旧 `trigger` 行为一致（同一 `POST /jobs` body）。
- 现有 `test_cli.sh` 绿（或新增 `test_cli_v02_step1.sh` 只测 help + create）。

**不测**：sync、test（尚未实现）。

---

## 步骤 2：Server 任务模型扩展

> **状态：✅ 已完成** — 验收：`bash server/test_v02_jobs.sh`

### 实现功能

| 模块 | 改动 |
|:---|:---|
| `server/database.py` | `jobs` 表增加字段（SQLite migration 或 `ALTER`）：`job_type`（默认 `train`）、`train_source`（默认 `ntb`）、`gm_task_id`、`parent_train_job_id`、`phase`（test 用：`sync`/`fetch`/`test`/`done`） |
| `server/models.py` | Pydantic：`JobCreate` 支持 `job_type`；`JobResponse` 返回新字段 |
| `server/api/jobs.py` | 创建/查询/list 支持按 `job_type` 过滤 |
| `config.example.json` | 文档注释（可选） |

**设计决策（本步固定）**：

- 旧 job 无 `job_type` 视为 `train`，保证兼容。
- `train_source`：`ntb` | `gm`（仅 test job 且来自 gm 时为 `gm`）。

### 测试

新建 `server/test_v02_jobs.sh`：

```bash
# 1. 默认 create 仍为 job_type=train
# 2. POST job_type=sync → 201
# 3. POST job_type=test + gm_task_id → 201
# 4. GET /jobs?job_type=test 过滤
# 5. 跑 test_e2e.sh 回归
bash test_v02_jobs.sh http://localhost:8000
bash test_e2e.sh http://localhost:8000
```

**通过标准**：API 字段正确；旧客户端不传 `job_type` 仍正常。

---

## 步骤 3：Agent + `ntb sync`（仅 clone）

> **状态：✅ 已完成** — 验收：`bash server/test_v02_step3.sh`（Agent 端到端见脚本内手动项）

### 实现功能

| 模块 | 改动 |
|:---|:---|
| `agent/agent.py` | 按 `job_type` 分支：`sync` 只 `prepare()` 后报 `COMPLETED` |
| `agent/job_runner.py` | 抽出 `prepare()` 已有；sync 不调用 `start()` |
| `cli/.../main.py` | `ntb sync`：`POST /jobs` 且 `job_type=sync` |
| `ntb train run` | 显式 `job_type=train`（或依赖 Server 默认） |

### 测试

**自动化（mock 仓库）**：

```bash
# server 起本地；agent 指向小公开仓库
ntb sync --repo https://github.com/some/small-repo.git --commit main
ntb job <id>   # COMPLETED，无 metrics
ntb metrics <id>  # 空或 404 无上报
```

**Agent 日志**：出现 clone/checkout，**不出现** train 子进程。

**回归**：`ntb train run` 仍走训练（步骤 4 前若未改 train 分支，sync 与 train 并行开发时注意 claim 逻辑）。

**通过标准**：sync job 耗时短、状态 `COMPLETED`、训练机 workspace 有目录、无 GPU 训练进程。

---

## 步骤 4：兜底训练显式化（P0）

> **状态：✅ 已完成** — 验收：`bash server/test_v02_step4.sh`

### 实现功能

| 模块 | 改动 |
|:---|:---|
| `agent/agent.py` | `job_type=train`：保持 v0.1 全流程；完成后写 `meta.json`（`train_source: ntb`）到 Server（新 API 或随 checkpoint 上传） |
| `server/api/` | 可选小路由：`PUT /jobs/{id}/meta` 或创建 job 目录写 `meta.json` |
| `README.md` | 文档：`ntb train run` = 兜底；gm = 主路径 |

### 测试

```bash
ntb train run --watch   # 短 train_command 或 mock：sleep + 假 model
ntb job <id>            # COMPLETED
curl .../jobs/<id>/checkpoint/...  # 模型仍在
bash test_phase3.sh     # 回归
```

**通过标准**：兜底训练与 v0.1 能力等价；`job_type=train` 明确。

---

## 步骤 5：test job 骨架 + Server 目录规范

> **状态：✅ 已完成** — 验收脚本 `server/test_v02_test_job.sh`

### 实现功能

| 模块 | 改动 |
|:---|:---|
| `server/job_data.py` | `init_job_layout()`：创建 `models/`、`test/`、`test/videos/` + `meta.json` |
| `server/api/jobs.py` | 创建时初始化目录；test 校验互斥/父任务存在；默认 `phase=sync` |
| `server/models.py` | `JobCreate`：`gm_checkpoint` |
| `cli/` | `ntb test run`：`--gm-task-id` / `--train-job-id` 二选一 |

### 测试

```bash
bash server/test_v02_test_job.sh http://localhost:8000
# - 仅 gm_task_id 创建成功
# - 仅 parent_train_job_id 创建成功
# - 两者皆无 → 400
# - data/{id}/ 目录存在
```

**通过标准**：test job 可创建、目录结构正确；Agent claim 后暂可标记 FAILED「test not implemented」或跳过 claim（`job_type=test` 先不 claim 也可，步骤 8 再打通）。

---

## 步骤 6：Agent gm FETCH (5B)

> **状态：✅ 已完成** — Mock 验收 `agent/test_fetch_mock.py`；API 验收 `server/test_v02_step6_fetch.sh`

### 实现功能

| 模块 | 改动 |
|:---|:---|
| `agent/gm_client.py` | **新建**：`list_models()`、`download()`；`GM_API_KEY` + `proxy` |
| `agent/fetch_runner.py` | **新建**：FETCH 阶段逻辑 |
| `agent/config.py` | `gm_api_key`、`gm_base_url`（`GM_API_KEY`、`GM_BASE_URL`） |
| `agent/agent.py` | test job：`sync → fetch(gm) → phase=test`；不跑 sim2sim |
| `agent/api_client.py` | `get_job_meta`、`update_phase` |
| `server/api/jobs.py` | `PUT /jobs/{id}/phase` |
| `server/api/checkpoint.py` | 上传目标改为 `models/`（下载兼容旧路径） |

### 测试

```bash
python agent/test_fetch_mock.py
bash server/test_v02_step6_fetch.sh http://localhost:8000

# 训练机手动（需真实 GM_API_KEY + GM_BASE_URL）：
ntb test run --gm-task-id <id> --checkpoint latest --commit <sha>
ntb job <id>    # phase=test
ls server/data/<id>/models/   # 有 .pt
```

**通过标准**：gm 路径 test job 经 Agent FETCH 后 Server `models/` 有模型；`meta.json` 含 `gm_task_id`、`gm_checkpoint`；`phase=test`（等待步骤 8 sim2sim）。

---

## 步骤 7：sim2sim 脚本框架（contrib，Mock 占位）

> **策略**：本步只交付**可跑通的占位脚本**，不实现真实 play/eval。详见 [sim2sim-framework.md](sim2sim-framework.md)。

### 实现功能

| 模块 | 改动 | 状态 |
|:---|:---|:---|
| `contrib/.../test_with_metrics.py` | **新建**：`run_mock_sim2sim()` + `run_real_sim2sim()` 空壳（`NotImplementedError`） | ✅ 骨架 |
| 同上 | `--mock` / `--self-test`；输出 `metrics.jsonl` + `test/summary.json` | ✅ |
| `agent/config.py` | `test_command` 模板，`{checkpoint_path}`、`{job_id}` | 步骤 8 |
| **R1（后续）** | `run_real_sim2sim()` 对接 `play.py` / Isaac | **刻意不写** |

### 测试

```bash
# 任意环境（无需 Isaac / conda）
python contrib/agi_origin/humanoid/scripts/test_with_metrics.py --self-test

export NETTRAINBRIDGE_METRICS_FILE=/tmp/test_metrics.jsonl
touch /tmp/model.pt
python contrib/agi_origin/humanoid/scripts/test_with_metrics.py \
  --mock --checkpoint /tmp/model.pt
```

**通过标准**：`--self-test` 绿；生成 `metrics.jsonl`（含 `kind: test`, `mock: true`）与 `test/summary.json`；与 `train_with_metrics.py` 环境变量约定一致。**不要求真实仿真指标**。

---

## 步骤 8：`ntb test run` 全流程打通（Mock sim2sim）

> **状态：✅ 已完成** — `agent/simulate_step8_e2e.py` + `server/test_v02_step8_test.sh`

> Agent 调用 `test_command` 时固定带 `--mock`，仅验证链路；真实 sim2sim 在 **R1** 替换 `run_real_sim2sim()` 后再切配置。

### 实现功能

| 模块 | 改动 |
|:---|:---|
| `agent/agent.py` | test：`sync → fetch(gm) → Mock 脚本 → 上传 test 产物 → `COMPLETED` |
| `agent/agent.py` | `train_source=ntb`：从 Server 下载父训练 checkpoint |
| `agent/job_runner.py` | `start_test()`；`NETTRAINBRIDGE_TEST_SCRIPT` fallback |
| `agent/config.py` | `test_command` 含 `--mock` |
| `server/api/test_files.py` | `POST/GET /jobs/{id}/test/{filename}` |
| `server/api/metrics.py` | `metrics.kind` 列（`train` / `test`） |

### 测试

```bash
python contrib/.../test_with_metrics.py --self-test
python agent/simulate_step8_e2e.py http://localhost:8000
bash server/test_v02_step8_test.sh http://localhost:8000

# 训练机（需 contrib 脚本在仓库或 NETTRAINBRIDGE_TEST_SCRIPT）：
ntb test run --gm-task-id <id> --checkpoint latest --commit <sha> --watch
ntb test run --train-job-id <train_id> --watch
```

**通过标准**：Mock 指标 + `test/summary.json` 在 Server；`phase=done`；`ntb metrics` 可见 test 指标。

---

## R1（后续）：真实 sim2sim 实现

> 不在步骤 5～8 范围内；步骤 8 合并后再开分支。

| 项 | 内容 |
|:---|:---|
| 代码 | 实现 `test_with_metrics.py` 内 `run_real_sim2sim()` |
| 配置 | `test_command` 去掉 `--mock`，补 `--task` / `--headless` 等 |
| 验收 | 真实 reward / success_rate；可选录屏上传 |
| 文档 | 更新 [sim2sim-framework.md](sim2sim-framework.md) 验收清单 |

---

## 步骤 9：artifacts / checkpoint CLI（P4）

> **状态：✅ 已完成** — `bash server/test_v02_artifacts.sh`

### 实现功能

| 模块 | 改动 |
|:---|:---|
| `server/api/checkpoint.py` | `GET /jobs/{id}/checkpoint` 列表（含 meta、primary 标记） |
| `server/api/artifacts.py` | **新建**：`GET /jobs/{id}/artifacts`；`GET .../artifacts/download`（zip） |
| `cli/` | `ntb checkpoint list/download`；`ntb artifacts list/download` |
| `cli/` | `ntb job` 已展示 `job_type`、`train_source`、`phase`、关联 id（步骤 5/8） |

### 测试

```bash
bash server/test_v02_artifacts.sh http://localhost:8000
ntb checkpoint list <job_id>
ntb checkpoint download <job_id> -o /tmp/model.pt
ntb artifacts list <test_job_id>
ntb artifacts download <test_job_id> -o /tmp/artifacts.zip
```

**通过标准**：家里不必手写 wget URL；checkpoint MD5 与 Server 一致；artifacts zip 含 `summary.json`。

---

## 步骤 10：文档 + 端到端验收（P5）

> **人工操作命令**：见 [manual-operations-v02.md](manual-operations-v02.md)（gm 训练 + ntb 兜底 + test 全流程输入示例）。

### 实现功能

| 模块 | 改动 |
|:---|:---|
| `README.md` | 双训练路径 + 三命令（train/test/sync）+ gm 主路径 |
| `plan/plan02-gm-ntb-framework.md` | 链接本实现计划 |
| `cli/` | 可选：`ntb doctor` 检查 gm API + NTB health，失败提示「可改用 ntb train run」 |
| `pyproject.toml` | `0.2.0` |

### 测试

**全链路验收清单**（人工，有 gm 账号 + 训练机环境）：

| # | 场景 | 命令 | 预期 |
|:---|:---|:---|:---|
| 1 | gm 主路径 | git push → gm train | 无需 NTB |
| 2 | ntb 兜底 | `ntb train run` | COMPLETED + checkpoint |
| 3 | gm + test | `ntb test run --gm-task-id` | models + test 产物 |
| 4 | ntb + test | `ntb test run --train-job-id` | 无 gm fetch |
| 5 | 仅 sync | `ntb sync` | 无 train/test |
| 6 | 回归 | `test_e2e.sh` + `test_phase3.sh` + `test_cli.sh` | 全绿 |

---

## 每步通用测试策略

| 类型 | 适用步骤 | 说明 |
|:---|:---|:---|
| **Shell API 测试** | 2, 5, 6, 8, 9 | 不启 Agent，curl + python 断言 JSON |
| **CLI 测试** | 1, 3, 8, 9 | 扩展 `test_cli.sh` 或独立 `test_cli_v02.sh` |
| **Agent 手动** | 3–8 | 训练机 + 小仓库 / mock command |
| **Mock 优先** | 6–8 | gm API、sim2sim 先 mock，再真实环境验证 |
| **回归** | 每步 | 至少跑 `test_e2e.sh` |

---

## 建议的 Git 分支策略

```text
main          ← v0.1 稳定
v0.2-dev      ← 步骤 1 起
  step-01-cli-6a
  step-02-server-job-type
  ...
```

每步一个 PR，合并条件 = 本步测试 + 回归绿。

---

## 第一步写代码从哪里开始？

**从步骤 1 开始**（风险最小）：

1. 只改 CLI：`ntb train run` + deprecated `trigger`
2. 跑 `test_cli.sh` 确认无破坏
3. 再进入步骤 2 改 Server schema

**不要第一步就改 Agent job 分支**，否则 sync/train/test 同时动，难以定位回归问题。

---

## 与框架 TBD 的默认选择（实现时可先按此 coding）

| TBD | 本计划默认 |
|:---|:---|
| #2 单 job vs 多 job | **单 test job + `phase` 字段** |
| #4 gm 封装 | Agent **`httpx` 直调** gm API（不依赖 gm-cli 二进制） |
| #6 metrics 分表 | 首期 **同表 + `kind` 列**（步骤 8 已实现） |
| #1 gm 不可用 | **人工切换**；步骤 10 再加 `ntb doctor` 提示 |

---

## 相关文档

- 架构框架：[plan02-gm-ntb-framework.md](plan02-gm-ntb-framework.md)
- **v0.2 手动操作命令**：[manual-operations-v02.md](manual-operations-v02.md)
- sim2sim 分阶段（Mock → R1）：[sim2sim-framework.md](sim2sim-framework.md)
- v0.1 规划：[plan/README.md](README.md)
- gm CLI 参考：[plan/diff/gm-cli/SKILL.md](diff/gm-cli/SKILL.md)
