# 第三阶段：完整训练流 + Web Dashboard 开发计划

## 目标

在阶段一（云服务器 API）和阶段二（Agent 基础版）已跑通的前提下，基于训练仓库 [Lee-Weather/agi_origin](https://github.com/Lee-Weather/agi_origin) 完成 **GitOps 全自动真实训练流** 和 **可视化监控**：

- `git push` agi_origin → GitHub Webhook → 云服务器自动建任务 → Agent clone 并执行真实 RL 训练
- 浏览器 Dashboard 实时查看 Loss/Reward 曲线、训练日志、GPU 心跳
- 通过 `train_with_metrics.py` 将 agi_origin 训练日志桥接为 GradMotion 所需的 `metrics.jsonl`

## 前提条件

| 项 | 要求 | 状态 |
|:---|:---|:---|
| 阶段二 Agent 全链路 | 抢占、clone、训练、上报、完成 | ✅ 已验证 |
| 云服务器 | 公网可访问，如 `http://47.103.63.175:8000`，conda `nettrain` | ✅ |
| 训练机环境 | conda `F1` + Isaac Gym + PyTorch | ✅ 已配好 |
| 训练仓库 | [agi_origin](https://github.com/Lee-Weather/agi_origin) 可 clone | ✅ |
| Agent 默认命令 | 指向 `humanoid/scripts/train.py` | ✅ 阶段二已配置 |

---

## 0. 阶段二已完成项（本阶段不再重复开发）

| 模块 | 文件 | 状态 |
|:---|:---|:---|
| 任务列表 API | `server/api/jobs.py` `GET /jobs` | ✅ Step 1 |
| SSE 日志流 | `server/api/logs.py` `GET /jobs/{id}/logs/stream` | ✅ Step 2 |
| 指标查询 API | `server/api/metrics.py` | ✅ |
| 心跳 API | `server/api/heartbeat.py` | ✅ |
| GitHub Webhook 接收 | `server/api/webhook.py` | ✅ 基础版，待加固 |
| Agent 上报主循环 | `agent/agent.py` | ✅ |
| 最小任务列表页 | `server/static/index.html` | ✅ 待增强跳转 |

---

## 1. agi_origin 训练项目说明

### 1.1 仓库结构（与 GradMotion 相关部分）

```text
agi_origin/
├── humanoid/
│   ├── scripts/
│   │   ├── train.py                  # 原训练入口（阶段二已用）
│   │   └── train_with_metrics.py     # 【阶段三新增】指标桥接包装脚本
│   ├── algo/                         # RL 算法（不改）
│   └── envs/                         # 环境配置
├── log/                              # 模型输出（README 约定路径）
│   └── <experiment>/exported_data/<datetime><run_name>/model_<iter>.pt
├── resources/robots/x1/              # 机器人资源
├── czy/                              # 自定义扩展目录
└── setup.py
```

> **路径注意**：agi_origin README 写模型在 `log/`，Agent 默认搜索 `logs/**/model_*.pt`。阶段三需确认实际输出路径，必要时调整 `GRADMOTION_MODEL_SEARCH_PATTERN` 或训练配置中的 `experiment_name`。

### 1.2 原训练命令

```bash
# agi_origin README 约定（工作目录为 humanoid/scripts 或仓库根目录 + 路径前缀）
python humanoid/scripts/train.py --task=x1_dh_stand --run_name={job_id} --headless
```

### 1.3 GradMotion 与 agi_origin 的衔接缺口

| agi_origin 原生行为 | GradMotion 需要 | 解决方案 |
|:---|:---|:---|
| 日志输出到 stdout | Agent 采集日志 → Dashboard SSE | ✅ 已有，无需改 |
| 不写 metrics.jsonl | Agent 读 `GRADMOTION_METRICS_FILE` 上报曲线 | **train_with_metrics.py** |
| 模型存 `log/.../model_*.pt` | Agent 搜索并上传 checkpoint | 确认 glob 路径匹配 |

### 1.4 指标桥接原理

```text
train_with_metrics.py
    │
    ├─ 子进程启动 humanoid/scripts/train.py（透传所有 CLI 参数）
    ├─ 实时读取 stdout，原样打印（→ Agent → train.log → SSE）
    ├─ 正则解析: iteration: N, mean_reward: X, loss: Y
    └─ 追加写入 GRADMOTION_METRICS_FILE（metrics.jsonl）
            │
            ▼
    Agent metrics_reader → POST /jobs/{id}/metrics → Dashboard ECharts
```

---

## 2. 技术栈

### 云服务器（NetTrainBridge/server）
- FastAPI + SQLite
- SSE 实时日志（已完成）
- Dashboard：HTML + JavaScript + ECharts

### 训练机（Agent + agi_origin）
- Python 3.8，conda `F1`
- Isaac Gym + PyTorch 1.13
- 训练入口：`humanoid/scripts/train_with_metrics.py`

### GitHub
- 仓库：`https://github.com/Lee-Weather/agi_origin.git`
- Webhook：Push 事件 → 云服务器 `/webhook/github`

---

## 3. 目录结构（阶段三新增/变更）

```text
NetTrainBridge/                        # 平台代码（云服务器 + Agent）
├── server/
│   ├── api/webhook.py                 # 加固
│   ├── static/
│   │   ├── index.html                 # 增强：跳转详情
│   │   └── dashboard.html             # 【新增】曲线 + 日志 + 心跳
│   └── test_phase3.sh                 # 【新增】验收脚本
└── plan/phase3_dev_plan.md

agi_origin/                            # 训练代码（独立仓库，push 到 GitHub）
└── humanoid/scripts/
    └── train_with_metrics.py          # 【新增】指标桥接
```

---

## 4. 开发顺序（6 个子阶段）

### Step 1: 任务列表 API 补强 ✅ 已完成

- `GET /jobs`，支持 `?status=&limit=`
- `index.html` 改用 `/jobs` 拉取全量任务

---

### Step 2: 日志 SSE 实时推送 ✅ 已完成

- `GET /jobs/{job_id}/logs/stream`
- 响应头：`Cache-Control: no-cache`、`X-Accel-Buffering: no`

---

### Step 3: agi_origin 指标桥接脚本（核心） ✅ 已完成

**产出**: `contrib/agi_origin/humanoid/scripts/train_with_metrics.py`（部署到 agi_origin 同名路径）

**功能**:
- 读取环境变量 `GRADMOTION_METRICS_FILE`（Agent 自动注入为 `{job_dir}/metrics.jsonl`）
- 以子进程方式调用 `train.py`，透传 `--task`、`--run_name`、`--headless` 等参数
- 实时转发 stdout/stderr（保证 Agent 日志采集不变）
- 解析 `dh_on_policy_runner.py` 日志并写入 metrics.jsonl

```python
# agi_origin 实际日志格式（非单行 iteration:）
#   Learning iteration 3/1000
#   Value function loss: 0.1234
#   Surrogate loss: 0.5678
#   Mean reward: 2.50
ITERATION_PATTERN = re.compile(r"Learning iteration\s+(\d+)/")
MEAN_REWARD_PATTERN = re.compile(r"Mean reward:\s+([-\d.eE+]+)")
VALUE_LOSS_PATTERN = re.compile(r"Value function loss:\s+([-\d.eE+]+)")
SURROGATE_LOSS_PATTERN = re.compile(r"Surrogate loss:\s+([-\d.eE+]+)")
```

**部署到 agi_origin**:
```bash
cp contrib/agi_origin/humanoid/scripts/train_with_metrics.py \
   <agi_origin>/humanoid/scripts/train_with_metrics.py
cd <agi_origin> && git add humanoid/scripts/train_with_metrics.py && git commit -m "add train_with_metrics" && git push
```

**训练机 Agent 配置**（阶段三标准）:
```bash
export GRADMOTION_SERVER_URL=http://47.103.63.175:8000
export GRADMOTION_CONDA_ENV=F1
export GRADMOTION_TRAIN_COMMAND="python humanoid/scripts/train_with_metrics.py --task=x1_dh_stand --run_name={job_id} --headless"
# 若模型路径不匹配，按需调整：
# export GRADMOTION_MODEL_SEARCH_PATTERN="log/**/model_*.pt"
```

**本地验证**（训练机，不经过 Agent）:
```bash
conda activate F1
git clone https://github.com/Lee-Weather/agi_origin.git && cd agi_origin
pip install -e .

export GRADMOTION_METRICS_FILE=/tmp/metrics.jsonl
export GRADMOTION_JOB_ID=local-test

# 可加 --max_iterations=50 缩短测试（若 train.py 支持）
python humanoid/scripts/train_with_metrics.py \
  --task=x1_dh_stand --run_name=local-test --headless

# 另开终端观察
tail -f /tmp/metrics.jsonl
```

**验收标准**:
- `metrics.jsonl` 随训练迭代持续增长
- 每行含 `step`（iteration）、`loss`、`reward`（mean_reward）
- 原 `train.py` 行为不受影响（模型仍正常保存）

---

### Step 4: Webhook 加固 + GitHub 配置

**产出**: `server/api/webhook.py` 小改 + `server/config.py` 补充配置项

**功能增强**:
- Webhook 签名校验（`GRADMOTION_WEBHOOK_SECRET`）
- 仓库白名单（`GRADMOTION_ALLOWED_REPOS`，仅允许 agi_origin）
- 同一 `commit_sha` + `repo_url` 去重
- 修复 `_create_job_task`：`asyncio.run()` 嵌套 → 同步 `INSERT`

**GitHub 配置**（[agi_origin](https://github.com/Lee-Weather/agi_origin) → Settings → Webhooks）:

| 配置项 | 值 |
|:---|:---|
| Payload URL | `http://47.103.63.175:8000/webhook/github` |
| Content type | `application/json` |
| Secret | 与 `GRADMOTION_WEBHOOK_SECRET` 一致（可选） |
| Events | Just the push event |

**云服务器环境变量**:
```bash
export GRADMOTION_ALLOWED_REPOS=https://github.com/Lee-Weather/agi_origin.git
export GRADMOTION_WEBHOOK_SECRET=<your-secret>   # 可选
```

**验证**:
```bash
curl -X POST http://47.103.63.175:8000/webhook/github \
  -H "X-GitHub-Event: push" \
  -H "Content-Type: application/json" \
  -d '{
    "repository": {"clone_url": "https://github.com/Lee-Weather/agi_origin.git"},
    "ref": "refs/heads/main",
    "after": "abc1234"
  }'
```

**GitOps 端到端**:
```bash
cd agi_origin
git commit --allow-empty -m "trigger gradmotion"
git push
# → 云服务器 PENDING 任务 → Agent clone 并启动 train_with_metrics.py
```

---

### Step 5: Dashboard 任务详情页（ECharts 曲线）

**产出**: `server/static/dashboard.html`

**页面布局**:
```
┌─────────────────────────────────────────────────────────┐
│  GradMotion - 任务 {job_id}                             │
├─────────────────────────────────────────────────────────┤
│  状态: RUNNING   Agent: agent-001   GPU: 85%            │
├──────────────────────┬──────────────────────────────────┤
│  Loss / Reward 曲线   │  实时日志 (SSE)                   │
│  (ECharts 每 5s)    │  (自动滚动)                       │
├──────────────────────┴──────────────────────────────────┤
│  [下载模型]  [返回列表]                                  │
└─────────────────────────────────────────────────────────┘
```

**数据拉取**:
- 指标：`GET /jobs/{id}/metrics?since_step={last_step}` 每 5s 增量轮询
- 日志：`EventSource('/jobs/{id}/logs/stream')`
- 心跳：`GET /jobs/{id}/heartbeat` 每 10s
- 元信息：`GET /jobs/{id}`

**验证**（需 agi_origin 真实训练跑起来）:
1. `http://47.103.63.175:8000/static/dashboard.html?id={job_id}`
2. Loss/Reward 曲线随 `train_with_metrics.py` 写入的 metrics 实时更新
3. 日志区显示 Isaac Gym 训练输出
4. 训练结束后状态变 `COMPLETED`，可下载模型

---

### Step 6: 组装验收 + 文档更新 ✅ 已完成

**产出**:
- `server/test_phase3.sh` — 阶段三自动化验收
- 更新 `README.md` — Dashboard、Webhook、agi_origin 训练命令说明
- 更新 `dev_phases.md` — 标记阶段三完成标准

**test_phase3.sh 检查项**（平台 API，不跑真实训练）:
1. `GET /jobs` 返回列表
2. Webhook 模拟 agi_origin push 创建任务
3. SSE 日志流可连接
4. `dashboard.html` 静态文件可访问

**完整端到端验收**（需训练机配合）:
1. agi_origin push → Webhook 自动建任务
2. Agent 执行 `train_with_metrics.py`，任务 RUNNING
3. `GET /jobs/{id}/metrics` 有真实 iteration 数据
4. Dashboard 曲线 + 日志 + 心跳正常
5. 训练结束 COMPLETED，模型可下载

---

## 5. 完整数据流

```text
家里修改 agi_origin 代码
    │
    ▼ git push
GitHub Webhook ──POST──▶ 云服务器 /webhook/github
                              │
                              ▼ 创建 PENDING 任务 (repo=agi_origin)
                         SQLite jobs 表
                              │
    公司训练机 Agent 轮询 ◀──┘
         │
         ├─ git clone agi_origin
         ├─ pip install -e .
         ├─ 执行 train_with_metrics.py → train.py (Isaac Gym RL)
         │       ├─ stdout → train.log → POST /logs → SSE → Dashboard
         │       └─ 解析日志 → metrics.jsonl → POST /metrics → ECharts
         ├─ POST /jobs/{id}/heartbeat → Dashboard GPU 卡片
         └─ 训练完成 → 上传 log/**/model_*.pt → COMPLETED
```

---

## 6. API 变更清单

| 方法 | 路径 | 说明 | 状态 |
|:---|:---|:---|:---|
| `GET` | `/jobs` | 任务列表 | ✅ |
| `GET` | `/jobs/{id}/logs/stream` | SSE 日志流 | ✅ |
| `GET` | `/jobs/{id}/metrics` | 历史指标 | ✅ |
| `GET` | `/jobs/{id}/heartbeat` | 最新心跳 | ✅ |
| `POST` | `/webhook/github` | Push 自动建任务 | ✅ |

---

## 7. 验证标准（阶段三必须通过）

1. **GitOps**: push agi_origin → Webhook → 云服务器出现 `PENDING` 任务
2. **真实训练**: Agent clone agi_origin，在 F1 环境执行 `train_with_metrics.py`
3. **指标曲线**: Dashboard Loss/Reward 随真实训练 iteration 更新
4. **日志流**: Dashboard 显示 Isaac Gym 训练日志（SSE）
5. **模型上传**: 训练结束后 `COMPLETED`，checkpoint 可下载
6. **状态正确**: 训练失败时 `FAILED` 并记录 `error_msg`

---

## 8. 测试方案

### 8.1 训练机本地：验证 train_with_metrics.py

```bash
conda activate F1
cd agi_origin && pip install -e .
export GRADMOTION_METRICS_FILE=/tmp/metrics.jsonl
export GRADMOTION_JOB_ID=test

python humanoid/scripts/train_with_metrics.py \
  --task=x1_dh_stand --run_name=test --headless

# 确认 metrics 有数据
cat /tmp/metrics.jsonl
```

### 8.2 手动创建任务 + Agent 执行

```bash
# 云服务器
conda activate nettrain && cd server && python main.py

# 创建任务
curl -X POST http://47.103.63.175:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/Lee-Weather/agi_origin.git","commit_sha":"main"}'

# 训练机 Agent
export GRADMOTION_SERVER_URL=http://47.103.63.175:8000
export GRADMOTION_TRAIN_COMMAND="python humanoid/scripts/train_with_metrics.py --task=x1_dh_stand --run_name={job_id} --headless"
python agent/agent.py

# 观察
curl http://47.103.63.175:8000/jobs/{job_id}/metrics
open http://47.103.63.175:8000/static/dashboard.html?id={job_id}
```

### 8.3 完整 GitOps 验收

```bash
# 1. agi_origin 配置 Webhook → 云服务器
# 2. 训练机 Agent 常驻（train_with_metrics 命令）
# 3. agi_origin 任意 commit push
git commit --allow-empty -m "gradmotion e2e test" && git push
# 4. Dashboard 自动出现新任务，曲线随真实训练更新
```

---

## 9. 风险与对策

| 风险 | 对策 |
|:---|:---|
| GitHub Webhook 无法访问云服务器 | 检查安全组 8000 端口；内网穿透或 Actions 中转 |
| train.py 日志格式与正则不匹配 | 已按 `dh_on_policy_runner.py` 实际格式解析；可用 `--self-test` 验证 |
| 模型路径 `log/` vs `logs/` 不匹配 | 调整 `GRADMOTION_MODEL_SEARCH_PATTERN="log/**/model_*.pt"` |
| 真实训练耗时长，Dashboard 开发阻塞 | 本地用 `--max_iterations=50` 缩短；或先用 POST metrics 灌数据测前端 |
| Isaac Gym 训练失败 | 检查 F1 环境、GPU 驱动；任务状态应为 FAILED |
| SSE 被 Nginx 缓冲 | 已加 `X-Accel-Buffering: no` |
| Webhook 重复建任务 | commit_sha + repo_url 去重 |
| `asyncio.run` 嵌套 bug | webhook 改为同步 INSERT |

---

## 10. 时间估算

| 步骤 | 预计工作量 | 状态 |
|:---|:---|:---|
| Step 1: GET /jobs | 0.5 天 | ✅ |
| Step 2: SSE 日志流 | 0.5 天 | ✅ |
| Step 3: train_with_metrics.py | 1 天 | ✅ |
| Step 4: Webhook 加固 | 0.5 天 | ✅ |
| Step 5: Dashboard 详情页 | 1–1.5 天 | ✅ |
| Step 6: 验收 + 文档 | 0.5 天 | ✅ |
| **阶段三** | | **✅ 完成** |
| **剩余** | **约 3–3.5 天** | |

---

## 11. 与阶段四的边界

阶段三 **不做**：

- API Token 认证
- Agent 断网重连增强
- systemd 部署脚本
- Dashboard 登录页

---

## 12. 参考资料

- [agi_origin 仓库](https://github.com/Lee-Weather/agi_origin) — X1 人形机器人 RL 训练代码
- [架构蓝图](plan_1.md) — `metrics.jsonl` 约定
- [开发阶段规划](dev_phases.md)
- [阶段一服务器计划](phase1_server_dev_plan.md)
- [阶段二 Agent 计划](phase2_agent_dev_plan.md)
- [NetTrainBridge 仓库](https://github.com/Lee-Weather/NetTrainBridge) — 平台代码，集成脚本在 `contrib/agi_origin/`
