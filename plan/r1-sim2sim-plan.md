# R1 真实 sim2sim 实现计划

> **目标**：在 v0.2 Mock 链路已打通的基础上，实现 `test_with_metrics.py` 内 `run_real_sim2sim()`，对接训练代码的 `play.py` / `sim2sim.py`，产出有业务意义的测试指标。  
> **前置原则**：**训练项目代码与 gm 最新模型必须放在同一工程目录下**，且模型须落在训练代码**原生 logs 路径**，`play.py` 才能通过 `--load_run` / `--checkpoint` 加载。  
> **训练代码示例**：[diff/agibot_x1_train-main](diff/agibot_x1_train-main)（与 agi_origin / agibot_x1_train 同结构）  
> 关联文档：[sim2sim-framework.md](sim2sim-framework.md)、[plan02-gm-ntb-framework.md](plan02-gm-ntb-framework.md)、[plan02-implementation.md](plan02-implementation.md)

---

## 1. 背景

### 1.1 v0.2 已完成

| 能力 | 状态 |
|:---|:---|
| `ntb test run` 创建 test job | ✅ |
| Agent：sync → fetch(gm) → Mock sim2sim | ✅ |
| Server 存 `models/`、`test/summary.json`、test metrics | ✅ |
| `test_with_metrics.py --mock` 占位指标 | ✅ |

### 1.2 R1 要补齐

| 能力 | 状态 |
|:---|:---|
| 真实 Isaac / play.py 仿真 | ❌ 待做 |
| `run_real_sim2sim()` | ❌ `NotImplementedError` |
| 代码 + 模型同窗的可复现布局 | ❌ 待规范 |
| Agent `test_command` 去掉 `--mock` | ❌ 待切换 |
| 真实 reward / success_rate 验收 | ❌ 待定义 |

### 1.3 为什么必须先「同窗」

真实 sim2sim 不是单独跑一个 `.pt` 文件，而是：

```text
agibot_x1_train / agi_origin 完整代码（humanoid、配置、依赖）
        +
gm 训练产出的 checkpoint 放入原生 logs 路径（见 §3.1）
        +
与训练对齐的 conda / Isaac 环境
        ↓
play.py 通过 --load_run + --checkpoint 加载并在 Isaac 中 rollout
```

当前 v0.2 Mock 阶段**不依赖**完整代码库，因此 `contrib/agi_origin` 里只有桥接脚本。  
R1 起，**必须把「代码仓库 checkout」与「gm 最新模型」放进同一 `job_dir`**，且模型**不能**随意放在根目录 `models/`——须按训练代码约定落在 `logs/<experiment_name>/exported_data/<load_run>/` 下，否则 `get_load_path()` 找不到权重。

---

## 2. 核心理念

| 原则 | 说明 |
|:---|:---|
| **同窗原则** | 一个 test 工程 = 一份确定 commit 的训练代码 + 一个落在原生 logs 路径的 checkpoint |
| **原生 logs 路径** | gm 模型放入 `logs/x1_dh_stand/exported_data/<load_run>/model_<N>.pt`，与 `play.py` 加载逻辑一致 |
| **commit 对齐** | test 用的代码 SHA 应与 gm 训练时一致（或人明确指定的兼容 SHA） |
| **模型可追溯** | `meta.json` 记录 `gm_task_id`、`load_run`、`checkpoint`、`commit_sha` |
| **先本地、后 Agent** | R1 先在训练机本地拼好「同窗工程」跑通 play，再接入 NTB Agent |
| **Mock 保留** | `--mock` 继续用于 CI / 无 Isaac 环境，不删除 |

---

## 3. 统一工程目录规范（R1 基石）

### 3.0 训练代码参考示例

本仓库内已有一份完整训练工程快照，供 R1 对照路径与命令：

**路径**：[`plan/diff/agibot_x1_train-main`](diff/agibot_x1_train-main)

| 项 | 值（当前示例） |
|:---|:---|
| 任务名 `--task` | `x1_dh_stand` |
| `experiment_name`（config） | `x1_dh_stand` |
| `run_name`（gm 训练时） | `test_20_video` |
| `load_run`（目录名） | `2026-01-14_09-58-10test_20_video` |
| checkpoint | `3000` → `model_3000.pt` |

**gm 模型落盘位置（R1 规范）**：

```text
plan/diff/agibot_x1_train-main/
└── logs/
    └── x1_dh_stand/
        └── exported_data/                          # ⚠️ 必须有这一层
            └── 2026-01-14_09-58-10test_20_video/   # load_run = {date_time}{run_name}
                └── model_3000.pt                   # gm 最新模型放这里
```

> 训练代码 `task_registry.make_alg_runner()` 的 `log_root` 默认为  
> `logs/<experiment_name>/exported_data`；`get_load_path()` 再拼 `<load_run>/model_<checkpoint>.pt`。  
> 验证 checkpoint 时必须查**含 `exported_data/` 的完整路径**，否则会误报缺失。

**play.py 加载方式**（不走绝对路径，走训练代码约定）：

```bash
cd plan/diff/agibot_x1_train-main   # 或训练机 {job_dir}
conda activate F1

python humanoid/scripts/play.py \
  --task=x1_dh_stand \
  --load_run=2026-01-14_09-58-10test_20_video \
  --checkpoint=3000
```

### 3.1 Agent test job 标准布局

test job 在训练机 `workspace` 下每个任务一个目录，R1 固定为：

```text
{workspace}/{test_job_id}/          # 工程根 = git clone 的训练代码根
├── humanoid/
│   └── scripts/
│       ├── train_with_metrics.py
│       ├── test_with_metrics.py    # R1：run_real_sim2sim() 在此
│       ├── play.py                 # Isaac 仿真验证
│       └── sim2sim.py              # 可选：MuJoCo sim2sim
├── logs/
│   └── x1_dh_stand/
│       └── exported_data/
│           └── {load_run}/         # 如 2026-01-14_09-58-10test_20_video
│               └── model_{N}.pt    # gm FETCH 或 ntb 父任务下载后落盘
├── test/                           # NTB 测试产物（CSV + summary，不录屏）
│   ├── test.log
│   ├── isaac_diag_*.csv
│   ├── summary.json
│   └── videos/                     # 可选：外部视频，R1 不做 play 录屏
├── metrics.jsonl                   # 测试指标（kind=test）
└── meta.local.json                 # 可选：load_run / checkpoint / commit
```

**与 v0.2 的差异**：

| v0.2（Mock） | R1（真实） |
|:---|:---|
| gm 模型在 `fetched_models/` | 落到 `logs/.../exported_data/<load_run>/` |
| 任意路径传 `--checkpoint` | `play.py` 用 `--load_run` + `--checkpoint`（整数） |
| 只验证链路，不要求 play.py | 必须有完整训练代码 + 原生 logs 目录 |
| `test_command` 带 `--mock` | 去掉 `--mock`，传 `--task` / `--load_run` / `--checkpoint` |

> **Server 侧** `data/{id}/models/` 仍用于家里下载；训练机同窗工程内须**额外**按 §3.0 布局落盘，供 `play.py` 加载。

### 3.2 gm 路径：代码 + 模型如何同窗

```text
ntb test run --gm-task-id task_gm_xxx \
             --load-run 2026-01-14_09-58-10test_20_video \
             --checkpoint 3000 \
             --commit <SHA>
    │
    ├─ SYNC    git clone @ <SHA>           →  {job_dir}/
    ├─ FETCH   gm model list → download    →  {job_dir}/logs/x1_dh_stand/exported_data/<load_run>/model_3000.pt
    └─ TEST    test_with_metrics.py        →  内部调 play.py --load_run ... --checkpoint ...
```

### 3.3 ntb 兜底训练路径：代码 + 模型如何同窗

```text
ntb test run --train-job-id <train_job_id> [--commit <SHA>]
    │
    ├─ SYNC（可选）
    ├─ 无 FETCH
    ├─ 从 Server 下载父 train checkpoint
    │     → {job_dir}/logs/x1_dh_stand/exported_data/<load_run>/model_{N}.pt
    └─ TEST    同上
```

### 3.4 本地开发用「同窗工程」（R1-0）

可直接使用仓库内示例，或 Agent 跑完 SYNC+FETCH 后的 `{job_dir}`：

```bash
# 方式 A：用 plan 内示例（已含 model_3000.pt）
cd plan/diff/agibot_x1_train-main
ls logs/x1_dh_stand/exported_data/2026-01-14_09-58-10test_20_video/model_3000.pt

python humanoid/scripts/play.py \
  --task=x1_dh_stand \
  --load_run=2026-01-14_09-58-10test_20_video \
  --checkpoint=3000
```

```bash
# 方式 B：训练机拼工程（gm 模型下载到原生 logs 路径）
cd ~/r1_workspace/agibot_x1_train
git checkout <与 gm 训练一致的 SHA>

mkdir -p logs/x1_dh_stand/exported_data/2026-01-14_09-58-10test_20_video
# gm task model list + curl → 放到上述目录
cp /path/from/gm/model_3000.pt \
   logs/x1_dh_stand/exported_data/2026-01-14_09-58-10test_20_video/

python humanoid/scripts/play.py \
  --task=x1_dh_stand \
  --load_run=2026-01-14_09-58-10test_20_video \
  --checkpoint=3000
```

**验收**：`model_*.pt` 在 `logs/x1_dh_stand/exported_data/<load_run>/` 下，`play.py` 能启动 Isaac 并完成 rollout。

---

## 4. 现状与差距分析

| 项 | 现状 | R1 需要 |
|:---|:---|:---|
| 训练代码参考 | [`plan/diff/agibot_x1_train-main`](diff/agibot_x1_train-main) | 作为路径与 play 命令的权威示例 |
| NetTrainBridge `contrib/` | 仅 2 个桥接脚本 | 完整代码靠 **git clone** |
| Agent FETCH 落盘 | `fetched_models/` | 改为 `logs/x1_dh_stand/exported_data/<load_run>/` |
| `play.py` 加载 | `--load_run` + `--checkpoint`（整数） | `test_with_metrics` / Agent 传这两参数，非绝对路径 |
| `load_run` 命名 | `{date_time}{run_name}` | 如 `2026-01-14_09-58-10test_20_video`；需 CLI `--load-run` 或 meta |
| gm 训练 commit | 人记 SHA / gm task env | test job `--commit` 对齐 |

---

## 5. 分阶段实施计划

```text
R1-0  同窗工程规范 + 本地手动拼工程 + 调研 play.py          ✅
R1-1  实现 run_real_sim2sim()（subprocess 调 play.py，解析 CSV） ✅
R1-2  Agent 布局调整（models/ 路径、去掉 --mock） ✅
R1-3  端到端：ntb test run 真实 sim2sim（gm 路径 + ntb 路径）
R1-4  文档、验收清单
```

### R1-0：同窗工程 + 调研（第一步）

> **状态：✅ 已完成**（2026-07-01）— 详见 [r1-0-play-investigation.md](r1-0-play-investigation.md)

**交付**：

1. 确认 agi_origin 中 `play.py`（或等价 eval 入口）路径、CLI 参数、stdout 格式  
2. 确定「gm 训练 task → 应对齐的 commit SHA」获取方式（人工 / `gm task info` / task env）  
3. 在训练机拼一个本地同窗工程，**手动**跑通一次 play（不经过 NTB）  
4. 输出 `meta.local.json` 模板字段：

```json
{
  "commit_sha": "4a27d320df1cfea38c542fed15d695897d938a6a",
  "gm_task_id": "task_gm_xxx",
  "task": "x1_dh_stand",
  "load_run": "2026-01-14_09-58-10test_20_video",
  "checkpoint": 3000,
  "model_path": "logs/x1_dh_stand/exported_data/2026-01-14_09-58-10test_20_video/model_3000.pt"
}
```

**工具脚本**：

```bash
bash plan/r1-0-validate.sh              # 路径自检（无 Isaac）
bash plan/r1-0-run-play.sh              # 手动 play（需 F1 + Isaac）
NETTRAINBRIDGE_PLAY_RENDER=0 bash plan/r1-0-run-play.sh   # 默认不录屏
```

**验收**：

- [x] 同一目录树下：训练代码 + `logs/x1_dh_stand/exported_data/<load_run>/model_*.pt` 存在  
- [x] 在 `plan/diff/agibot_x1_train-main` 示例上 `play.py` 能加载 `model_3000.pt` 并写完 CSV  
- [x] 记录 play 输出路径（CSV）与指标方案（解析 CSV → summary.json）  

**不测**：NTB Agent、Server 上传。

---

### R1-1：实现 `run_real_sim2sim()`

> **状态：✅ 已完成**（2026-07-01）— 验收 `bash plan/r1-1-validate.sh`；真实 Isaac：`RUN_R1_1_ISAAC=1 bash plan/r1-1-validate.sh`

**交付**（`contrib/agi_origin/humanoid/scripts/test_with_metrics.py`，同步到训练仓库）：

1. `run_real_sim2sim()` 内 subprocess 调用 `play.py`（参数：`--task`、`--load_run`、`--checkpoint`）  
2. 实时解析 stdout → 追加 `metrics.jsonl`（`kind: test`，**无** `mock: true`）  
3. 结束后写 `test/summary.json`：`final_reward`、`success_rate`、`load_run`、`checkpoint` 等  
4. 保留 `--mock`；`--self-test` 仍只测 Mock  
5. `play.py`：`RENDER=False`（**不录屏**）；`NETTRAINBRIDGE_TEST_OUTPUT_DIR` → `{job_dir}/test/`  
6. 指标：play 结束后**解析 CSV** 写入 `summary.json`（非 stdout）

**CLI 扩展**（`test_with_metrics.py`）：

| 参数 | 说明 |
|:---|:---|
| `--task` | 默认 `x1_dh_stand` |
| `--load-run` | 对应 `logs/.../exported_data/<load_run>/` 目录名 |
| `--checkpoint` | 整数，对应 `model_{N}.pt` |
| `--headless` | 传给 play（若 play 支持） |

**接口约定**（与 Agent 已注入环境变量对齐）：

| 变量 | 用途 |
|:---|:---|
| `NETTRAINBRIDGE_LOAD_RUN` | 覆盖 `--load-run` |
| `NETTRAINBRIDGE_CHECKPOINT` | 覆盖 `--checkpoint`（整数） |
| `NETTRAINBRIDGE_METRICS_FILE` | metrics.jsonl 路径 |
| `NETTRAINBRIDGE_JOB_ID` | 写入 summary |
| `NETTRAINBRIDGE_TEST_OUTPUT_DIR` | play CSV 输出目录 → `{job_dir}/test/` |
| `NETTRAINBRIDGE_PLAY_RENDER` | 固定 `0`，不录屏 |

**验收**：

- [x] `--self-test` 含 CSV 解析单测  
- [x] `--mock` 回归  
- [x] `play.py` 支持 `NETTRAINBRIDGE_TEST_OUTPUT_DIR` / `PLAY_RENDER`  
- [x] 真实 sim2sim：`test_with_metrics --load-run ... --checkpoint ...`（见 `RUN_R1_1_ISAAC=1`）  

**工具**：

```bash
bash plan/r1-1-validate.sh
RUN_R1_1_ISAAC=1 bash plan/r1-1-validate.sh   # 含真实 play，约 9 分钟
```

---

### R1-2：Agent 布局与配置调整

> **状态：✅ 已完成**（2026-07-01）— 验收 `bash plan/r1-2-validate.sh`

**交付**：

| 模块 | 改动 |
|:---|:---|
| `agent/checkpoint_layout.py` | **新建**：`logs_export_dir`、`model_path_in_logs`、checkpoint 解析 |
| `agent/test_context.py` | **新建**：`resolve_test_context()`（gm/ntb 路径 + `fetched_models` 兼容迁移） |
| `agent/agent.py` | FETCH 后模型落盘 `logs/<task>/exported_data/<load_run>/model_{N}.pt` |
| `agent/agent.py` | test 阶段用 `resolve_test_context`；meta 写入 `load_run`/`checkpoint`/`task` |
| `agent/job_runner.py` | `start_test(test_ctx)`；`test_command` 格式化 `{task},{load_run},{checkpoint}` |
| `agent/config.py` | `test_command` 去掉 `--mock`，使用 `--load-run={load_run} --checkpoint={checkpoint}` |
| `cli/` | `ntb test run` 新增 `--load-run`（**必填**） |
| `server/models.py` | `JobCreate` / meta 增加 `load_run`、`task`、`checkpoint` |
| `server/api/jobs.py` | test job 校验 `load_run` 必填 |

**test_command 示例（R1）**：

```json
"test_command": "python humanoid/scripts/test_with_metrics.py --task=x1_dh_stand --load-run={load_run} --checkpoint={checkpoint} --headless"
```

**双份存储**：

| 位置 | 用途 |
|:---|:---|
| `{job_dir}/logs/.../exported_data/<load_run>/model_{N}.pt` | **play.py 加载**（同窗工程内） |
| Server `data/{id}/models/` | 家里 `ntb checkpoint download`（保持 v0.2） |

**验收**：

- [x] `bash plan/r1-2-validate.sh` 全绿（含 `test_v02_step8` / `test_v02_test_job` 回归）  
- [x] test job 缺 `load_run` → 400  
- [x] `meta.json` 含 `load_run` / `checkpoint` / `task`  
- [ ] Agent 真实 test job：SYNC+FETCH 后 `logs/.../exported_data/<load_run>/` 有 pt（**R1-3**）  

**工具**：

```bash
bash plan/r1-2-validate.sh http://127.0.0.1:8000
```

---

### R1-3：端到端真实 sim2sim

**场景 A — gm 训练后 test**：

```bash
# 家里
ntb test run --gm-task-id task_gm_xxx --checkpoint latest --commit <SHA> --watch
```

**场景 B — ntb 兜底训练后 test**：

```bash
ntb test run --train-job-id <train_job_id> --watch
```

**验收**：

| # | 检查项 |
|:---|:---|
| 1 | `ntb job` → `phase=done`，`train_source` 正确 |
| 2 | `ntb metrics` → 真实指标，无 `mock: true` |
| 3 | `ntb artifacts download` → `summary.json` 含真实 success_rate |
| 4 | `data/{id}/models/` 与训练机同窗布局一致 |
| 5 | commit_sha 与 gm 训练一致（gm 路径） |

---

### R1-4：文档与收尾

- 更新 [sim2sim-framework.md](sim2sim-framework.md) 验收清单（Mock vs 真实分列）  
- 更新 [manual-operations-v02.md](manual-operations-v02.md) R1 操作说明  
- 更新根 [README.md](../README.md)：`ntb test run` 为真实 sim2sim（非「后续版本」）  
- 可选：`ntb test bundle` 或脚本：一键在本地拼同窗工程（clone + gm 下载）  

---

## 6. `run_real_sim2sim()` 技术方案（草案）

### 6.1 调用方式（subprocess 调 play.py）

与 `train_with_metrics.py` 一致，subprocess 包装 `play.py`，**使用训练代码原生参数**：

```bash
python humanoid/scripts/play.py \
  --task=x1_dh_stand \
  --load_run=2026-01-14_09-58-10test_20_video \
  --checkpoint=3000
```

`get_load_path()` 内部解析为：

```text
logs/x1_dh_stand/exported_data/2026-01-14_09-58-10test_20_video/model_3000.pt
```

优点：与 gm / 本地训练产物路径完全一致；无需改 `play.py` 加载逻辑。

### 6.2 指标解析

需 R1-0 调研后填具体正则，预期字段：

| 字段 | 来源 |
|:---|:---|
| `step` / `episode` | play stdout |
| `reward` | episode return / mean reward |
| `success_rate` | eval 汇总行 |
| `kind` | 固定 `"test"` |

### 6.3 失败处理

- checkpoint 不存在 → exit 1，Agent 标 `FAILED`  
- play 超时 → 可配置 `test_timeout_sec`（后续）  
- Isaac 启动失败 → 日志写入 `test/test.log`，便于 `ntb logs` 排查  

---

## 7. 环境与版本对齐

| 风险 | 对策 |
|:---|:---|
| gm 云端镜像 ≠ 公司 F1 Isaac 版本 | R1-0 记录 gm task 的 image / env；test 前核对 conda 依赖 |
| commit 与模型不匹配 | test job 强制 `--commit`；meta 写入 `gm_task_id` + `commit_sha` |
| `play.py` 参数随 agi_origin 变更 | test_command 可配置；文档写明最低 agi_origin 版本 |

---

## 8. 与 NTB 架构的关系

```text
                    gm 训练（主路径）
                         │
                         ▼
              ntb test run --gm-task-id
                         │
         ┌───────────────┴───────────────┐
         │  Agent 同窗工程 {job_dir}/     │
         │  · agi_origin @ commit        │
         │  · models/ ← gm FETCH         │
         │  · test_with_metrics (真实)   │
         └───────────────┬───────────────┘
                         ▼
                   NTB Server
              metrics / summary / artifacts
                         │
                         ▼
                   家里 ntb watch / artifacts download
```

**R1 不改变** v0.2 的 job 类型、phase 流转、FETCH 5B 策略；只替换 Mock 为真实 sim2sim，并规范同窗目录。

---

## 9. 验收标准（R1 完成定义）

| # | 标准 |
|:---|:---|
| 1 | 训练代码与 gm 模型在同一 `{job_dir}`，模型在 `logs/x1_dh_stand/exported_data/<load_run>/` |
| 2 | `plan/diff/agibot_x1_train-main` 示例路径可复现 play |
| 3 | `run_real_sim2sim()` 实现且本地可跑通 |
| 4 | `ntb test run --gm-task-id` 端到端真实指标上线 |
| 5 | `ntb test run --train-job-id` 端到端无需 gm FETCH |
| 6 | `--mock` 与 v0.2 回归仍可用 |

---

## 10. 待定项（R1 过程中决议）

| # | 议题 | 建议默认 |
|:---|:---|:---|
| T1 | gm task 的 commit SHA | 首期 **人工 `--commit`** |
| T2 | `load_run` 来源 | 首期 **人工 `--load-run`**（与 gm 训练 run 名一致） |
| T3 | `play.py` vs `sim2sim.py` | R1-0 先 **play.py**（Isaac）；sim2sim 作备选 |
| T4 | v0.2 `fetched_models/` 兼容 | Agent 读 `fetched_models/` 仅作 Mock 回归回退 |
| T5 | Server `models/` vs 训练机 `logs/` | **双份**：Server 供下载，训练机用 logs 供 play |
| T6 | play 录屏 / `test/videos/` | **不做**；gm 或业务侧已有视频则无需 NTB 再录 |

---

## 11. 建议开工顺序

```text
1. R1-0  用 plan/diff/agibot_x1_train-main 示例，确认 play.py + logs 路径
2. R1-1  实现 run_real_sim2sim()（--load-run + --checkpoint）
3. R1-2  改 Agent FETCH 落盘到 logs/.../exported_data/<load_run>/ ✅
4. R1-3  ntb test run 端到端
5. R1-4  文档与验收
```

**第一步具体动作**：在 `plan/diff/agibot_x1_train-main` 上执行：

```bash
ls logs/x1_dh_stand/exported_data/2026-01-14_09-58-10test_20_video/model_3000.pt
python humanoid/scripts/play.py \
  --task=x1_dh_stand \
  --load_run=2026-01-14_09-58-10test_20_video \
  --checkpoint=3000
```

---

## 12. 相关文档

- 训练代码示例（含 model_3000.pt）：[diff/agibot_x1_train-main](diff/agibot_x1_train-main)
- Mock 阶段说明：[sim2sim-framework.md](sim2sim-framework.md)
- v0.2 框架：[plan02-gm-ntb-framework.md](plan02-gm-ntb-framework.md)
- 手动操作：[manual-operations-v02.md](manual-operations-v02.md)
- gm 模型下载：[plan/diff/gm-cli/SKILL.md](diff/gm-cli/SKILL.md)
- 桥接脚本：`contrib/agi_origin/humanoid/scripts/test_with_metrics.py`
