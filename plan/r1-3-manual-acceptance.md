# R1-3 手动操作指南与验收清单

> 对应 [r1-sim2sim-plan.md](r1-sim2sim-plan.md) § R1-3  
> 前置：R1-0 / R1-1 / R1-2 已完成  
> 关联：[r1-0-play-investigation.md](r1-0-play-investigation.md)、[manual-operations-v02.md](manual-operations-v02.md)

R1-3 是**端到端真实 sim2sim 联调**：从家里 `ntb test run` 出发，经 Server → Agent → 真实 `play.py`（Isaac），最后在家里查真实指标。单次 test 约 **9 分钟**（与 R1-0 一致）。

在 [§一](#一开工前检查三端) 完成三端检查后，建议顺序：

```text
场景 A：阶段 0～3（gm 训练）→ 阶段 4～6（ntb test）→ §四 验收清单
场景 B：§三（ntb 训练 + test）→ §四 验收清单
```

---

## 一、开工前检查（三端）

### 1. 云 Server

```bash
cd server
conda activate nettrain
python main.py
```

另开终端：

```bash
curl http://<云IP>:8000/health    # → {"status":"ok"}
```

### 2. 公司训练机 Agent

```bash
cd agent
conda activate F1    # 或 config 里配置的 conda_env
python agent.py
```

确认 `~/.nettrainbridge/config.json`：

| 配置项 | 要求 |
|:---|:---|
| `server_url` | 指向云 Server |
| `workspace` | 可写目录，如 `~/czy/nettrainbridge` |
| `conda_env` | 含 Isaac Gym，如 `F1` |
| `test_command` | **不要**设 `NETTRAINBRIDGE_TEST_COMMAND=...--mock...`（R1-3 要跑真实 play） |

gm 路径还需配置 gm 凭证（供 Agent **FETCH** 阶段拉取 checkpoint）。**推荐写入配置文件**，无需每次 `export`：

在 `~/.nettrainbridge/config.json` 的 `agent` 段增加：

```json
{
  "agent": {
    "server_url": "http://<云IP>:8000",
    "proxy": "http://<公司代理>:端口",
    "agent_id": "agent-001",
    "workspace": "~/czy/nettrainbridge",
    "conda_env": "F1",
    "gm_api_key": "<你的 gm API Key>",
    "gm_base_url": "https://<gm 服务地址>"
  }
}
```

配置优先级：**环境变量 > 配置文件 > 默认值**。若同时设置了 `export GM_API_KEY=...`，环境变量会覆盖配置文件。

也可用环境变量（临时调试或不想落盘时）：

```bash
export GM_API_KEY="<你的 gm API Key>"
export GM_BASE_URL="https://<gm 服务地址>"
```

> **说明**：上述字段仅 **训练机 Agent** 的 FETCH 使用。家里 **`gm` CLI** 仍用 `gm auth login` 或 gm 自有配置，不读 NetTrainBridge 的 `config.json`。

### 3. 家里 CLI

```bash
pip install -e ".[dev]"    # 确保含 R1-2 的 --load-run
ntb config init --server-url http://<云IP>:8000
ntb health
```

### 4. 提前准备的参数

**场景 A（从头 gm 训练）**：开工时只需确定 `run_name`（如 `r1_3_test`）；`load_run`、`checkpoint`、`task_gm_xxx` 在 **gm 训练跑完后** 再记录。

**场景 B（ntb 兜底）**：需已有父 train job，并事先知道 `load_run` 与 checkpoint 整数。

| 参数 | 说明 | 何时确定 | 示例 |
|:---|:---|:---|:---|
| `run_name` | gm 训练 `--run_name`，拼进 `load_run` | 创建 gm 任务前 | `r1_3_test` |
| `load_run` | `{date_time}{run_name}` | **gm 训练完成后** | `2026-07-01_10-00-00r1_3_test` |
| `task` | 训练任务名 | 创建 gm 任务前 | `x1_dh_stand`（默认） |
| `checkpoint` | 整数，对应 `model_{N}.pt` | **gm 训练完成后** | `3000` |
| `commit` | 与训练一致的代码 SHA | push 后 | `git rev-parse HEAD` |
| `task_gm_xxx` | gm 任务 ID | `gm task create` 返回后 | `task_xxx` |
| `repo` | 训练代码仓库 | 创建 gm 任务前 | 与 gm `codeUrl` 一致 |

> `load_run` 命名规则：`{date_time}{run_name}`（无分隔符）。训练日志或 gm 产物路径中可见，形如 `logs/x1_dh_stand/exported_data/<load_run>/model_*.pt`。详见 [r1-0-play-investigation.md](r1-0-play-investigation.md)。

---

## 二、场景 A：gm 训练 → ntb test（主路径，从头开始）

本场景分两段：**先在家里用 gm 完成训练**，满意后再 **`ntb test run` 做真实 sim2sim**。  
此阶段 **NTB 不参与训练**，只在你决定 test 时才介入。

### 阶段 0：开工前（家里 gm CLI）

确认 gm 已登录、能访问项目与资源：

```bash
gm auth status
gm auth whoami
gm project list --page 1 --limit 10
```

若未登录：

```bash
gm auth login --api-key "<YOUR_GM_API_KEY>"
```

记下后续 `create-train.json` 需要的字段（按你环境替换）：

| 字段 | 获取方式 |
|:---|:---|
| `projectId` | `gm project list` |
| `goodsId` | `gm task resource list --goods-back-category 3`（填任务时用 `goodsId`，非 `goodsBackId`） |
| `imageId` / `imageVersion` | `gm task image official` 或 `gm task image personal` + `gm task image versions` |

训练机 Agent 侧仍需配置 `GM_API_KEY` / `GM_BASE_URL`（供后续 FETCH 用），见 [§一.2](#2-公司训练机-agent)。

---

### 阶段 1：推送训练代码

```bash
cd agi_origin    # 或 agibot_x1_train / 你的训练仓库

git add .
git commit -m "r1-3: prepare for gm train + test"
git push origin main
```

**务必记下 commit SHA**（test 时 `--commit` 须与此一致）：

```bash
export COMMIT_SHA=$(git rev-parse HEAD)
echo "commit=$COMMIT_SHA"
```

---

### 阶段 2：在 gm 上创建训练任务

#### 2.1 确定训练参数

建议为本轮 R1-3 使用**新的** `run_name`，便于与历史实验区分：

```bash
export RUN_NAME="r1_3_test"    # 自定，会拼进 load_run
export TASK="x1_dh_stand"
```

训练入口（本仓库约定）：

```text
humanoid/scripts/train.py
```

`startScript` **必须以 `gm-run` 开头**（gm 硬限制），示例：

```text
gm-run <仓库根目录名>/humanoid/scripts/train.py --task=x1_dh_stand --run_name=r1_3_test --headless
```

> `<仓库根目录名>` 与 `codeUrl` clone 下来的顶层目录一致（如 `agi_origin`）。

#### 2.2 编写 create-train.json

在家目录或仓库内创建（**替换** `proj_xxx`、`goods_xxx`、镜像版本、仓库 URL 等）：

```json
{
  "taskBaseInfo": {
    "projectId": "proj_xxx",
    "taskType": "1",
    "trainType": "1",
    "taskName": "r1-3-gm-train",
    "taskDescription": "R1-3 end-to-end gm train",
    "taskTag": ["r1-3"],
    "goodsId": "goods_xxx",
    "imageId": "BJX00000001",
    "imageVersion": "V000057",
    "personalDataPath": "/personal"
  },
  "taskCodeInfo": {
    "codeType": "2",
    "codeUrl": "[{\"codeUrl\":\"https://github.com/<org>/agi_origin.git\",\"versionType\":\"1\",\"versionName\":\"main\"}]",
    "mainCodeUri": "agi_origin/humanoid/scripts/train.py",
    "startScript": "gm-run agi_origin/humanoid/scripts/train.py --task=x1_dh_stand --run_name=r1_3_test --headless",
    "isOpen": "1"
  },
  "runtimeReminderConfig": {
    "enableRuntimeReminder": false,
    "reminderDurations": []
  }
}
```

可先预览再创建：

```bash
gm task create --file ./create-train.json --dry-run
gm task create --file ./create-train.json
```

从返回结果记下 **`task_gm_xxx`**（即 `<gm_task_id>`）。

#### 2.3 启动训练

```bash
gm task run --task-id "task_gm_xxx"
gm task logs --task-id "task_gm_xxx" --follow
```

---

### 阶段 3：等待 gm 训练完成并记录关键参数

训练结束后执行：

```bash
gm task info --task-id "task_gm_xxx"
gm task model list --task-id "task_gm_xxx" --page 1 --limit 20
```

**必须记下**（供 `ntb test run` 使用）：

| 记录项 | 说明 | 示例 |
|:---|:---|:---|
| `<gm_task_id>` | 创建时已有 | `task_gm_xxx` |
| `<commit_sha>` | 阶段 1 的 push SHA | `4a27d320...` |
| `<run_name>` | 与 `startScript` 中一致 | `r1_3_test` |
| `<load_run>` | `{date_time}{run_name}` | 从 model 路径或训练日志确认 |
| `<checkpoint>` | 要测的迭代数 | `3000` 或 `latest` |

**如何确认 `load_run`**：

1. `gm task model list` 返回的模型路径 / 元数据中常含目录名；或  
2. gm 训练日志里搜索 `exported_data/` 下一级目录；或  
3. 规则为 **训练开始时间戳 + `run_name`**，例如 `2026-07-01_10-00-00` + `r1_3_test` → `2026-07-01_10-00-00r1_3_test`。

参考（R1-0 已跑通的历史样例，非本次必用）：

```text
run_name  = test_20_video
load_run  = 2026-01-14_09-58-10test_20_video
checkpoint = 3000
```

#### 训练阶段验收（仅 gm，尚未 test）

| # | 检查项 | 命令 | 预期 |
|:--|:---|:---|:---|
| T1 | 任务已结束 | `gm task info` | 状态为完成/成功 |
| T2 | 有 checkpoint | `gm task model list` | 至少 1 个 `.pt` |
| T3 | 已记录 load_run | 笔记 / 本地记录 | 非空，与 `run_name` 对应 |
| T4 | commit 已记录 | `echo $COMMIT_SHA` | 与 push 一致 |

> 人对训练曲线/指标满意后，再进入阶段 4。此阶段 **无需** 创建 NTB job。

---

### 阶段 4：家里创建 test job（真实 sim2sim）

确认三端（Server、Agent、家里 CLI）已就绪，且 Agent **未**设置 Mock 覆盖命令。

在训练代码仓库目录执行：

```bash
cd agi_origin

ntb test run \
  --gm-task-id task_gm_xxx \
  --load-run <load_run> \
  --task x1_dh_stand \
  --checkpoint latest \
  --commit $COMMIT_SHA \
  --watch
```

说明：

- `--load-run` **必填**，填阶段 3 记下的 `<load_run>`
- `--checkpoint` 可用 `latest` 或 `3000` 或 `model_3000.pt`（仅 gm 路径）
- `--commit` 必须与 gm 训练用的代码 SHA 一致
- `--watch` 会轮询直到结束；也可记下 job id 后手动查

记下输出的 **`<test_job_id>`**。

---

### 阶段 5：观察 Agent 阶段流转

Agent 日志应依次出现：

```text
phase=sync   → git clone + checkout + pip install -e .
phase=fetch  → gm FETCH → 落盘 logs/.../exported_data/<load_run>/model_*.pt
phase=test   → test_with_metrics.py → subprocess play.py
phase=done   → 上传 metrics / summary / checkpoint
```

训练机可检查同窗布局：

```bash
JOB=<test_job_id>
WS=~/czy/nettrainbridge    # 按你的 workspace 调整
LOAD_RUN=<load_run>

ls $WS/$JOB/logs/x1_dh_stand/exported_data/$LOAD_RUN/model_*.pt
ls $WS/$JOB/test/isaac_diag_*.csv
ls $WS/$JOB/test/summary.json
tail -f $WS/$JOB/test/test.log
```

`test.log` 中应看到：

```text
Loading model from: .../model_3000.pt
CSV saved to: ...
[test_with_metrics] real sim2sim complete
success_rate=... final_reward=...
```

**不应**出现 `mock sim2sim` 或 `"mode": "mock"`。

---

### 阶段 6：家里验收（test 结果）

```bash
TEST_ID=<test_job_id>

ntb job $TEST_ID
ntb metrics $TEST_ID
ntb logs $TEST_ID
ntb checkpoint list $TEST_ID
ntb checkpoint download $TEST_ID -o ./gm_test_model.pt
ntb artifacts list $TEST_ID
ntb artifacts download $TEST_ID -o ./r1-3-gm-artifacts.zip
```

解压 artifacts 查看 summary：

```bash
unzip -l ./r1-3-gm-artifacts.zip
unzip -p ./r1-3-gm-artifacts.zip summary.json | python3 -m json.tool
```

场景 A 的逐项打勾见 [§四 验收清单](#四验收清单逐项打勾)。

---

## 三、场景 B：ntb 训练 → ntb test（兜底路径）

### 前置条件

- 已有 **COMPLETED** 的 ntb train job
- 父任务 checkpoint 已上传到 Server

若没有父 train job，先跑：

```bash
ntb train run --watch
# 记下 <train_job_id>，等待 COMPLETED
ntb checkpoint list <train_job_id>
```

### 步骤 1：家里创建 test job

```bash
ntb test run \
  --train-job-id <train_job_id> \
  --load-run 2026-01-14_09-58-10test_20_video \
  --task x1_dh_stand \
  --checkpoint 3000 \
  --commit $(git rev-parse HEAD) \
  --watch
```

注意：

- ntb 路径 **`--checkpoint` 必须是整数**（如 `3000`），不能用 `latest`
- **不会**调用 gm FETCH；Agent 从 Server 下载父任务 checkpoint 到同窗 logs 路径

### 步骤 2～3

与场景 A 相同，观察 `sync → test → done`（**无 fetch 阶段**），家里用同样命令验收。

---

## 四、验收清单（逐项打勾）

### A. 任务状态（家里）

| # | 检查项 | 命令 / 方式 | 预期 |
|:--|:---|:---|:---|
| A1 | 任务类型 | `ntb job <id>` | `type=test` |
| A2 | 训练来源 | 场景 A：`train_source=gm`；场景 B：`train_source=ntb` | 与路径一致 |
| A3 | 最终状态 | `ntb job <id>` | `status=COMPLETED` |
| A4 | 阶段 | `ntb job <id>` 或 meta | `phase=done` |
| A5 | 无错误 | `ntb job <id>` | 无 `error_msg` |
| A6 | meta 字段 | Server `GET /jobs/<id>/meta` 或 `ntb job` | 含 `load_run`、`task`、`checkpoint` |
| A7 | commit 对齐 | `ntb job <id>` | `commit_sha` 与你指定的 `--commit` 一致 |

### B. 训练机同窗布局

| # | 检查项 | 路径 | 预期 |
|:--|:---|:---|:---|
| B1 | 工程根 | `{workspace}/{job_id}/` | 含 `humanoid/scripts/play.py` |
| B2 | 模型位置 | `logs/x1_dh_stand/exported_data/<load_run>/model_{N}.pt` | 文件存在且非空 |
| B3 | 无旧布局依赖 | `fetched_models/` | 可有可无；play 应走 logs 路径 |
| B4 | CSV 产出 | `{job_dir}/test/isaac_diag_*.csv` | 至少 1 个，有内容 |
| B5 | summary | `{job_dir}/test/summary.json` | `"mode": "real"` |
| B6 | 测试日志 | `{job_dir}/test/test.log` | 含 `real sim2sim complete` |

### C. 指标与产物（家里）

| # | 检查项 | 命令 | 预期 |
|:--|:---|:---|:---|
| C1 | 真实指标 | `ntb metrics <id>` | 有 `kind=test` 记录 |
| C2 | 非 Mock | `ntb metrics <id>` | **无** `"mock": true` |
| C3 | summary 模式 | `artifacts` 中 `summary.json` | `"mode": "real"` |
| C4 | 业务指标 | `summary.json` | 含 `success_rate`、`final_reward`（非占位 0.85） |
| C5 | 参数回写 | `summary.json` | 含 `load_run`、`checkpoint`、`task` |
| C6 | checkpoint 可下 | `ntb checkpoint list/download` | 能列出并下载 `.pt` |
| C7 | artifacts 完整 | `ntb artifacts download` | zip 含 `summary.json`、`metrics.jsonl` |

### D. 场景差异项

| # | 场景 | 检查项 | 预期 |
|:--|:---|:---|:---|
| D1 | A（gm） | Agent 有 fetch 阶段 | `phase` 曾经过 `fetch` |
| D2 | A（gm） | `gm_task_id` | 与 `--gm-task-id` 一致 |
| D3 | A（gm） | FETCH 落盘 | 模型在 logs 路径，非仅 `fetched_models/` |
| D4 | B（ntb） | 父任务关联 | `parent_train_job_id` 正确 |
| D5 | B（ntb） | 无 gm 调用 | Agent 日志无 gm FETCH |
| D6 | B（ntb） | checkpoint 来源 | 来自父 train job 的 Server models |

### E. 参考值（R1-0 / R1-1 已验证）

用示例 `model_3000.pt` 时，可参考：

- `success_rate` ≈ `0.968`
- `final_reward` ≈ `0.318`
- 耗时 ≈ **9 分钟**

数值不必完全一致，但应处于合理范围，且明显不是 Mock 占位值（`success_rate=0.85`、`mode=mock`）。

---

## 五、验收记录模板（建议填写）

```text
R1-3 验收记录
日期：
操作人：

【场景 A - gm 训练（阶段 1～3）】
gm_task_id:
run_name:
commit_sha:
load_run:                    # 训练完成后填写
checkpoint:                  # 如 3000 / latest
gm 训练完成: Y/N
训练阶段结论: PASS / FAIL / 跳过(已有模型)

【场景 A - ntb test（阶段 4～6）】
test_job_id:
load_run:
checkpoint:
status / phase:
summary success_rate / final_reward:
训练机 model 路径是否存在: Y/N
artifacts 已下载: Y/N
结论: PASS / FAIL
备注:

【场景 B - ntb】
test_job_id:
parent_train_job_id:
load_run:
checkpoint:
status / phase:
summary success_rate / final_reward:
结论: PASS / FAIL
备注:
```

**R1-3 通过标准**：场景 A、B **各至少 1 次**全部 A～D 项通过（E 作参考）。

---

## 六、常见问题排查

| 现象 | 可能原因 | 处理 |
|:---|:---|:---|
| 缺 `load_run` 创建失败 | CLI 版本旧 | `pip install -e ".[dev]"` |
| FETCH 失败 | `GM_API_KEY` 未设或 task id 错 | 检查 Agent 环境变量与 `gm task model list` |
| `Loading model` 找不到 pt | `load_run` 与训练不一致 | 核对 `logs/.../exported_data/` 目录名 |
| `LEGGED_GYM_ROOT_DIR` 错 | 未 `pip install -e .` | 看 Agent sync 日志；手动在 job_dir 执行 |
| 仍是 Mock 结果 | 设置了 `NETTRAINBRIDGE_TEST_COMMAND=...--mock` | 去掉该环境变量，重启 Agent |
| ntb 路径报缺 checkpoint | 未传整数 | `--checkpoint 3000`（非 `latest`） |
| 父任务 checkpoint 404 | train job 未完成或未上传 | `ntb checkpoint list <parent>` |
| test 超时 / FAILED | Isaac/GPU 问题 | 看 `{job_dir}/test/test.log` 全文 |
| `ntb metrics` 无数据 | test 未跑完或上传失败 | 查 Agent 日志与 Server `data/<id>/` |

---

## 七、与 v0.2 手册的差异

[manual-operations-v02.md](manual-operations-v02.md) 仍写 Mock sim2sim；R1-3 需注意：

1. 必须加 **`--load-run`**
2. 预期 **`summary.json` 中 `"mode": "real"`**，不是 `"mock"`
3. 验收以 **CSV + summary** 为准，不录屏
4. Agent 默认 `test_command` 已无 `--mock`

---

## 八、相关文档

- 总计划：[r1-sim2sim-plan.md](r1-sim2sim-plan.md)
- play 调研：[r1-0-play-investigation.md](r1-0-play-investigation.md)
- 训练代码示例：[diff/agibot_x1_train-main](diff/agibot_x1_train-main)
- v0.2 操作手册：[manual-operations-v02.md](manual-operations-v02.md)
