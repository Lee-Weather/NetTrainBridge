# NetTrainBridge v0.2 框架：双训练路径 + NTB 测试

> **决策已定**  
> - 模型下发（gm → 训练机）：**5B**（Agent 经代理直拉 gm）  
> - CLI 语义：**6A**（`ntb sync` / `ntb train run` / `ntb test run`）  
> - **训练两条路**：**gm 为主**（绝大部分）；**ntb train 为兜底**（仅 gm 出问题时）  
> - **NTB 两项工作**：**训练**（fallback）+ **测试**（sim2sim，gm 训练后的可选链路）  

本文档为框架级方案，**不含实现细节**；各模块细节后续分议题讨论。

操作手册见 [README.md](../README.md)；与 gm-cli 对照见 [plan/diff/gm-cli/SKILL.md](diff/gm-cli/SKILL.md)。

---

## 1. 核心理念

| 原则 | 说明 |
|:---|:---|
| **训练首选 gm** | `git push` 后默认在 Gradmotion 云端训练 |
| **训练兜底 ntb** | gm 不可用/异常时，改用 **`ntb train run`** 在公司训练机训练 |
| **测试可选 NTB** | gm（或 ntb）训练结果满意后，人决策是否 **`ntb test run`** 做 sim2sim |
| **NTB 两项工作** | **train job**：clone + 长训 + 模型上传 Server；**test job**：sync + fetch(gm) + sim2sim |
| **结果汇聚 Server** | 训练产物、测试产物均登记在云 Server（来源字段区分 gm / ntb） |
| **出站-only** | 训练机仍只主动访问外网（经公司代理） |

### 1.1 训练路径选型（框架）

```
git push
    │
    ▼
┌───────────────────────────────────────┐
│  gm 是否正常可用？                      │
└───────────────────────────────────────┘
    │ 是（绝大部分情况）          │ 否（兜底）
    ▼                            ▼
 gm task create/run          ntb train run
 （云端 GPU）                 （公司训练机 Agent）
    │                            │
    └────────────┬───────────────┘
                 ▼
         评估训练结果（gm CLI 或 ntb watch）
                 │
                 ▼
         是否需要 sim2sim？
                 │
        否 ──▶ 结束
        是 ──▶ ntb test run（见 §3.3）
```

| 路径 | 频率 | 触发 | 执行位置 | 家里怎么看 |
|:---|:---|:---|:---|:---|
| **gm 训练** | **主路径 (~95%+)** | `gm task create` + `run` | Gradmotion 云端 | `gm task logs` / `data get` |
| **ntb 训练** | **兜底** | `ntb train run` | 公司训练机 Agent | `ntb watch` / `ntb metrics` |
| **ntb 测试** | **可选** | `ntb test run` | 公司训练机 Agent | `ntb watch`（测试指标） |

**何时走 ntb train（框架，具体条件后续细化）：**

- gm 平台故障、排队过长、配额用尽
- gm 镜像/环境与代码不兼容且短期无法解决
- 必须在公司内网环境验证训练链路
- 实验规模小，不值得开 gm 任务

---

## 2. 角色与职责

```
┌──────────────┐     git push      ┌──────────────┐
│  家里         │ ────────────────▶ │  GitHub      │
│  gm CLI      │                   │  agi_origin  │
│  ntb CLI     │                   └──────┬───────┘
└──────┬───────┘                          │
       │                                  │
       ├──────── gm train ──────▶ ┌──────────────┐
       │                          │  Gradmotion  │
       │                          │  云端 GPU     │
       │                          └──────┬───────┘
       │                                 │ policUrlDown（5B，test 时用）
       │                                 │
       └──────── ntb train/test ──▶ ┌─────▼────────┐
                                    │  NTB Server  │
                                    │  FastAPI     │
                                    └──────▲───────┘
                                           │
                                    ┌──────┴───────┐
                                    │ 公司训练机    │
                                    │ Agent        │
                                    │ train · test │
                                    └──────────────┘
```

| 组件 | 职责 |
|:---|:---|
| **GitHub** | 代码唯一源；gm / ntb 对齐同一 `commit_sha` |
| **gm** | **默认训练**；checkpoint、训练曲线 |
| **NTB Server** | 调度 **train / test** job；存训练模型 + 测试产物 |
| **公司 Agent** | **train**：clone + 长训 + 上传 checkpoint；**test**：sync + fetch(gm) + sim2sim |
| **家里 gm CLI** | 主路径训练与评估 |
| **家里 ntb CLI** | 兜底 `ntb train run`；可选 `ntb test run`；监控与取结果 |

---

## 3. 日常流程

### 3.1 主路径：gm 训练（绝大部分）

```text
1. 家里    git push
2. 家里    gm task create + gm task run
3. 家里    gm task logs --follow
4. 家里    gm task model list / gm task data get
5. 决策    不满意 → 改代码回 1
           满意且不做 sim2sim → 结束
           满意且做 sim2sim → §3.3
```

此阶段 **不占用 NTB**（Server 可无 job，训练机空闲）。

### 3.2 兜底路径：ntb 训练（gm 有问题时）

```text
1. 家里    git push
2. 家里    ntb train run [--commit ...] [--watch]
           └─▶ Server 创建 job_type=train
3. Agent     clone → train_command → 上传 checkpoint → COMPLETED
4. 家里    ntb watch / ntb metrics / ntb logs
5. 决策    是否 sim2sim？
           · 训练来源已是 ntb → test 可走 §3.3b（无需 fetch gm）
           · 仅验证训练 → 结束
```

**与 v0.1 关系**：`ntb train run` 继承现有 `train_command` + `train_with_metrics` 链路；语义上取代旧 `ntb trigger`。

### 3.3 可选路径：ntb 测试（sim2sim）

#### 3.3a 前置：训练来自 **gm**

```text
6. 家里    ntb test run --gm-task-id ... --checkpoint ... [--watch]
7. Agent     sync → fetch(5B) → sim2sim → 上报 Server
8. 家里    ntb watch / ntb metrics / ntb logs
```

#### 3.3b 前置：训练来自 **ntb train**

```text
6. 家里    ntb test run --train-job-id <ntb_train_job_id> [--watch]
           └─▶ 跳过 fetch gm；checkpoint 从 Server data/{train_job_id}/models/
7. Agent     sync（若需要）→ test → 上报 Server
8. 家里    ntb watch / ntb metrics / ntb logs
```

**人为主观决策**：看完训练曲线/指标后再决定是否 `ntb test run`；**不自动触发**。

### 3.4 与旧 README 的差异

| 旧流程 | 新流程 |
|:---|:---|
| `ntb trigger` = 默认训练 | **默认 gm 训练**；`ntb train run` 仅兜底 |
| Agent 唯一职责是训练 | Agent **训练（少）+ 测试（常）** |
| 训练完 wget | 训练结果在 gm 或 Server；测试后在 Server |

---

## 4. NTB Job 类型（框架）

| job_type | 频率 | Agent 行为 | 家里入口 |
|:---|:---|:---|:---|
| **`train`** | 少（兜底） | clone → 长训 → 上传 checkpoint | `ntb train run` |
| **`test`** | 中（可选） | sync → fetch(可选) → sim2sim | `ntb test run` |
| **`sync`** | 低 | 仅 clone（独立或 test 子阶段） | `ntb sync` |

### 4.1 test job 内部编排

**训练来源 = gm：**

```
ntb test run --gm-task-id ...
    ├─ SYNC
    ├─ FETCH (5B)    从 gm 拉 checkpoint → Server models/
    └─ TEST          sim2sim
```

**训练来源 = ntb train：**

```
ntb test run --train-job-id ...
    ├─ SYNC（可选，可与 train 同 commit 则跳过）
    └─ TEST          直接用 Server 上 train job 的 checkpoint
```

### 4.2 CLI 命名（6A）

| 命令 | 用途 | 频率 |
|:---|:---|:---|
| **`ntb train run`** | 兜底训练（原 v0.1 trigger 训练语义） | 少 |
| **`ntb test run`** | sim2sim 测试（含 sync + fetch） | 中 |
| **`ntb sync`** | 仅同步代码 | 低 |
| **`ntb watch`** | 监控 train / test job | — |
| ~~`ntb trigger`~~ | deprecated → 提示改用 `train run` 或说明已默认 gm | — |

```bash
# 兜底训练
ntb train run [--repo URL] [--commit SHA] [--watch]

# gm 训练后的测试
ntb test run --gm-task-id <id> --checkpoint latest [--commit SHA] [--watch]

# ntb 训练后的测试
ntb test run --train-job-id <ntb_job_id> [--watch]
```

---

## 5. Server 存放（训练 + 测试）

### 5.1 目录布局

```
data/
├── {train_job_id}/              # ntb train 产生
│   ├── models/
│   │   └── model_3000.pt
│   └── meta.json                # train_source: "ntb"
│
└── {test_job_id}/               # ntb test 产生
    ├── models/                  # 来自 gm fetch 时才有
    │   └── model_3000.pt
    ├── test/
    │   ├── metrics.jsonl
    │   ├── summary.json
    │   └── videos/
    └── meta.json
```

### 5.2 元数据区分

| 字段 | gm 训练 + test | ntb 训练 | ntb 训练 + test |
|:---|:---|:---|:---|
| `train_source` | `gm` | `ntb` | `ntb` |
| `gm_task_id` | 有 | — | — |
| `parent_train_job_id` | — | — | 有（ntb train job id） |
| `commit_sha` | 有 | 有 | 有 |

**gm 训练的原始结果**主要在 gm 平台；启用 `ntb test run` 后，**checkpoint 副本**进入 Server `models/`。

### 5.3 家里查看结果

| 结果 | gm 训练 | ntb 训练 | sim2sim 测试 |
|:---|:---|:---|:---|
| 训练曲线 | `gm task data get` | `ntb metrics` | — |
| 训练 checkpoint | `gm task model list` | Server / `ntb checkpoint`（待定） | Server `models/` |
| 测试指标 | — | — | `ntb metrics`（test job） |
| 测试日志 | — | — | `ntb logs` |

---

## 6. FETCH 5B（test + gm 训练时）

| 项 | 约定 |
|:---|:---|
| **谁下载** | 公司 Agent |
| **凭证** | 训练机 `GM_API_KEY` |
| **网络** | Agent `proxy` |
| **流程** | `gm task model list` → `policUrlDown` → 本地 → 上传 Server |

ntb train 后的 test **不走 FETCH**。

---

## 7. 日常命令速查

### 主路径（gm 训练 → 可选测试）

```bash
cd agi_origin && git push origin main

gm task create --file ./create-train.json
gm task run --task-id "task_gm_xxx"
gm task logs --task-id "task_gm_xxx" --follow
gm task model list --task-id "task_gm_xxx"

# 决策：是否 sim2sim
ntb test run --gm-task-id task_gm_xxx --checkpoint latest --watch
ntb job / metrics / logs <test_job_id>
```

### 兜底（gm 不可用 → ntb 训练 → 可选测试）

```bash
cd agi_origin && git push origin main

ntb train run --watch
# 决策：是否 sim2sim
ntb test run --train-job-id <train_job_id> --watch
```

---

## 8. 开发阶段（框架）

| 阶段 | 目标 |
|:---|:---|
| **P0** | 保留并明确 **`ntb train run`**（v0.1 训练链路），文档改为兜底定位 |
| **P1** | **6A** CLI 拆分：`train run` / `sync`；deprecated `trigger` |
| **P2** | **test job** + **5B FETCH** + Server `models/` |
| **P3** | sim2sim + `ntb test run`（gm / ntb 双入口） |
| **P4** | `ntb artifacts`、checkpoint 列表/下载 |
| **P5** | 可选：gm 健康检查脚本，失败时提示「改用 ntb train run」 |

**首期必须保留**：`ntb train run` 完整可用（兜底不能阉割）。

---

## 9. TBD 清单

| # | 议题 |
|:---|:---|
| 1 | gm 不可用判定：人工 vs 自动探测 |
| 2 | `ntb test run` 单 job 还是多 job |
| 3 | `--commit` 与 gm 任务关联方式 |
| 4 | Agent 侧 gm API 封装方式 |
| 5 | sim2sim 脚本与 `test_command` |
| 6 | train / test metrics 是否分表 |
| 7 | Server 磁盘清理策略 |
| 8 | `GM_API_KEY` 安全存储 |
| 9 | gm 与训练机环境不一致的处理 |
| 10 | ntb train 与 gm 训练产物字段对齐 |

---

## 10. 验收标准（框架级）

| # | 检查项 |
|:---|:---|
| 1 | **gm 主路径**：`git push` + gm 训练无需 NTB |
| 2 | **ntb 兜底**：gm 不可用时 `ntb train run` 可完成训练并上传 Server |
| 3 | **gm → test**：`ntb test run --gm-task-id` 完成 fetch + sim2sim |
| 4 | **ntb → test**：`ntb test run --train-job-id` 无需 fetch gm |
| 5 | Server 可区分 `train_source`（gm / ntb） |
| 6 | `ntb sync` 仅 clone，不 train 不 test |

---

## 11. 与 plan02.md 的关系

- 原 [plan02.md](plan02.md) 的 test 概念保留并加强。
- **新增**：训练双路径（gm 主 + ntb 兜底）；NTB 明确 **train / test** 两项工作。
- 实现细节确定后合并或替代 plan02 主流程描述。

---

## 12. 分步实现

编码顺序、每步交付与测试方法见 **[plan02-implementation.md](plan02-implementation.md)**。
