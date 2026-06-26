# 第三阶段：完整训练流 + Web Dashboard 开发计划

## 目标

在阶段一（云服务器 API）和阶段二（Agent 基础版）已跑通的前提下，完成 **GitOps 全自动训练流** 和 **可视化监控**：

- `git push` → GitHub Webhook → 云服务器自动建任务 → Agent 自动训练
- 浏览器 Dashboard 实时查看 Loss/Reward 曲线、日志、GPU 心跳
- 提供可复现的模拟训练脚本，用于快速验收阶段三
- 适配 `agi_origin` 仓库的指标输出（`metrics.jsonl`）

## 前提条件

- 阶段二已通过验证（Agent 能抢占、clone、训练、上报、完成）
- 云服务器已部署并可公网访问（如 `http://47.103.63.175:8000`）
- 训练机 Agent 长期运行，conda 环境 `F1` 已配置
- GitHub 仓库 [Lee-Weather/agi_origin](https://github.com/Lee-Weather/agi_origin) 可访问

---

## 0. 阶段二已完成项（本阶段不再重复开发）

以下能力在阶段一/二中已实现，阶段三直接复用：

| 模块 | 文件 | 状态 |
|:---|:---|:---|
| 指标查询 API | `server/api/metrics.py` `GET /jobs/{id}/metrics` | ✅ |
| 日志查询 API | `server/api/logs.py` `GET /jobs/{id}/logs` | ✅ |
| 心跳 API | `server/api/heartbeat.py` | ✅ |
| GitHub Webhook 接收 | `server/api/webhook.py` | ✅ 基础版 |
| 日志增量读取 | `agent/log_monitor.py` | ✅ |
| 指标增量读取 | `agent/metrics_reader.py` | ✅ |
| Agent 上报主循环 | `agent/agent.py` | ✅ |
| 最小任务列表页 | `server/static/index.html` | ✅ 仅列表，无曲线 |

---

## 1. 技术栈

### 云服务器
- FastAPI（SSE 日志流）
- SQLite（指标历史）
- 纯前端 Dashboard：HTML + JavaScript + [ECharts](https://echarts.apache.org/)

### Agent / 训练
- 现有 Agent 无需大改，重点是 **训练脚本写 metrics.jsonl**
- Python 3.8（conda `F1`）

### GitHub
- Webhook（Push 事件）
- 仓库：`https://github.com/Lee-Weather/agi_origin.git`

---

## 2. 目录结构（阶段三新增/变更）

```text
NetTrainBridge/
├── server/
│   ├── api/
│   │   ├── jobs.py              # 补充 GET /jobs 列表
│   │   └── logs.py              # 补充 SSE 日志流
│   ├── static/
│   │   ├── index.html           # 任务列表（增强：跳转详情页）
│   │   ├── dashboard.html       # 任务详情：曲线 + 日志 + 心跳
│   │   └── js/
│   │       └── dashboard.js     # 可选：抽离图表逻辑
│   └── test_phase3.sh           # 阶段三验收脚本
│
├── examples/
│   ├── train_mock.py            # 模拟训练（写 metrics.jsonl + 模型）
│   └── README.md                # 使用说明
│
├── agent/                         # 阶段三仅小改（可选）
│   └── config.py                  # 可选：mock 训练命令配置
│
└── plan/
    └── phase3_dev_plan.md         # 本文件
```

---

## 3. 开发顺序（7 个子阶段）

### Step 1: 任务列表 API 补强

**产出**: `server/api/jobs.py` 补充 `GET /jobs`

**背景**: 当前 `index.html` 用 `localStorage` 拼凑任务列表，无法可靠展示全部历史任务。

**功能**:
- `GET /jobs` — 返回所有任务，支持 `?status=RUNNING&limit=50`
- 默认按 `create_time DESC` 排序

```python
@router.get("", response_model=list[JobResponse])
async def list_jobs(status: Optional[str] = None, limit: int = 100):
    ...
```

**验证**:
```bash
curl http://47.103.63.175:8000/jobs
curl "http://47.103.63.175:8000/jobs?status=COMPLETED&limit=10"
```

---

### Step 2: 日志 SSE 实时推送

**产出**: `server/api/logs.py` 补充 SSE 端点

**功能**:
- `GET /jobs/{job_id}/logs/stream` — Server-Sent Events 推送新日志
- 客户端连接后，每 1s 检查缓存是否有新行并推送
- 与现有 `POST /jobs/{id}/logs` 内存缓存兼容

```python
from fastapi.responses import StreamingResponse

@router.get("/{job_id}/logs/stream")
async def stream_logs(job_id: str):
    async def event_generator():
        last_count = 0
        while True:
            buffer = _get_log_buffer(job_id)
            if len(buffer) > last_count:
                for line in list(buffer)[last_count:]:
                    yield f"data: {line}\n\n"
                last_count = len(buffer)
            await asyncio.sleep(1)
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**验证**:
```bash
# 终端 1：订阅日志流
curl -N http://47.103.63.175:8000/jobs/{job_id}/logs/stream

# 终端 2：模拟上报
curl -X POST http://47.103.63.175:8000/jobs/{job_id}/logs \
  -H "Content-Type: application/json" \
  -d '{"content": "test line"}'
```

---

### Step 3: 模拟训练脚本

**产出**: `examples/train_mock.py` + `examples/README.md`

**功能**:
- 读取环境变量 `GRADMOTION_JOB_ID`、`GRADMOTION_METRICS_FILE`
- 每 2s 写一行 metrics.jsonl：`{"step", "loss", "reward"}`
- 打印日志到 stdout（被 Agent 重定向到 train.log）
- 结束时生成 `logs/mock_run/exported_data/model_1.pt`（匹配 Agent 模型搜索规则）

```python
# 核心逻辑示意
metrics_file = Path(os.environ["GRADMOTION_METRICS_FILE"])
for step in range(1, 21):
    print(f"[mock] step={step} loss={1.0/step:.4f}", flush=True)
    append_jsonl(metrics_file, {"step": step * 100, "loss": 1.0/step, "reward": step})
    time.sleep(2)
save_model("logs/mock_run/exported_data/model_1.pt")
```

**验证**（训练机本地）:
```bash
conda activate F1
export GRADMOTION_JOB_ID=test
export GRADMOTION_METRICS_FILE=/tmp/metrics.jsonl
python examples/train_mock.py
cat /tmp/metrics.jsonl
```

---

### Step 4: Webhook 加固 + GitHub 配置

**产出**: `server/api/webhook.py` 小改 + 配置文档

**功能增强**:
- Webhook 签名校验（可选，`GRADMOTION_WEBHOOK_SECRET`）
- 仅处理指定仓库（白名单 `GRADMOTION_ALLOWED_REPOS`）
- 同一 commit 去重（避免重复 push 创建多个任务）
- 修复 `_create_job_task`：避免 `asyncio.run(create_job())` 嵌套问题，改为同步建任务

**GitHub 配置步骤**（一次性）:

| 配置项 | 值 |
|:---|:---|
| Payload URL | `http://47.103.63.175:8000/webhook/github` |
| Content type | `application/json` |
| Secret | 与 `GRADMOTION_WEBHOOK_SECRET` 一致（可选） |
| Events | Just the push event |

**验证**:
```bash
# 模拟 GitHub push
curl -X POST http://47.103.63.175:8000/webhook/github \
  -H "X-GitHub-Event: push" \
  -H "Content-Type: application/json" \
  -d '{
    "repository": {"clone_url": "https://github.com/Lee-Weather/agi_origin.git"},
    "ref": "refs/heads/main",
    "after": "abc1234"
  }'

curl http://47.103.63.175:8000/jobs/pending
```

**端到端验证**:
```bash
# 在 agi_origin 仓库
git commit --allow-empty -m "trigger gradmotion"
git push
# → 云服务器自动创建 PENDING 任务 → Agent 自动执行
```

---

### Step 5: Dashboard 任务详情页（ECharts 曲线）

**产出**: `server/static/dashboard.html`

**页面布局**:

```
┌─────────────────────────────────────────────────────────┐
│  GradMotion - 任务 3009f75d                             │
├─────────────────────────────────────────────────────────┤
│  状态: RUNNING   Agent: agent-001   GPU: 85%            │
├──────────────────────┬──────────────────────────────────┤
│  Loss / Reward 曲线   │  实时日志 (SSE)                   │
│  (ECharts 每 5s 刷新) │  (自动滚动)                       │
├──────────────────────┴──────────────────────────────────┤
│  [下载模型]  [返回列表]                                  │
└─────────────────────────────────────────────────────────┘
```

**数据拉取**:
- 指标：`GET /jobs/{id}/metrics?since_step={last_step}` 增量轮询
- 日志：`EventSource('/jobs/{id}/logs/stream')` 或 `?tail=50` 轮询
- 心跳：`GET /jobs/{id}/heartbeat` 每 10s
- 任务元信息：`GET /jobs/{id}`

**ECharts 配置要点**:
```javascript
// 每 5s 拉取新指标
const resp = await fetch(`/jobs/${jobId}/metrics?since_step=${lastStep}`);
const newMetrics = await resp.json();
// 追加到 series.data，调用 chart.setOption()
```

**路由**:
- 列表页：`/static/index.html`
- 详情页：`/static/dashboard.html?id={job_id}`
- `index.html` 每行增加「查看详情」链接

**验证**:
1. 浏览器打开 `http://47.103.63.175:8000/static/dashboard.html?id={job_id}`
2. 运行 `train_mock` 任务，曲线实时更新
3. 日志区域自动追加新行

---

### Step 6: agi_origin 指标适配

**产出**: 在 `agi_origin` 仓库添加指标输出（二选一）

#### 方案 A（推荐）：包装脚本 `humanoid/scripts/train_with_metrics.py`

- 调用原 `train.py`，拦截 stdout 解析 `iteration: N, mean_reward: X, loss: Y`
- 写入 `GRADMOTION_METRICS_FILE` 环境变量指定的 jsonl 文件

```python
# 解析行示例: "iteration: 100, mean_reward: 1.23, loss: 0.45"
METRIC_PATTERN = re.compile(
    r"iteration:\s*(\d+).*?mean_reward:\s*([\d.]+).*?loss:\s*([\d.]+)"
)
```

Agent 配置切换：
```bash
export GRADMOTION_TRAIN_COMMAND="python humanoid/scripts/train_with_metrics.py --task=x1_dh_stand --run_name={job_id} --headless"
```

#### 方案 B：直接修改 `humanoid/algo/` 训练循环

- 在每次 log 时追加写 metrics.jsonl
- 改动面大，不推荐作为阶段三首选

**验证**:
```bash
# 创建 agi_origin 任务，确认 metrics API 有数据
curl http://47.103.63.175:8000/jobs/{job_id}/metrics
```

---

### Step 7: 组装验收 + 文档更新

**产出**:
- `server/test_phase3.sh` — 阶段三自动化验收
- 更新 `README.md` — Dashboard 使用说明、Webhook 配置
- 更新 `dev_phases.md` — 标记阶段三完成标准

**test_phase3.sh 检查项**:
1. `GET /jobs` 返回列表
2. Webhook 模拟 push 创建任务
3. `GET /jobs/{id}/metrics` 有数据（需 mock 训练跑一会儿）
4. SSE 日志流可连接
5. `dashboard.html` 静态文件可访问

---

## 4. 完整数据流（阶段三）

```text
你家 git push
    │
    ▼
GitHub Webhook ──POST──▶ 云服务器 /webhook/github
                              │
                              ▼ 创建 PENDING 任务
                         SQLite jobs 表
                              │
    公司训练机 Agent 轮询 ◀──┘
         │
         ├─ clone agi_origin / 执行 train_mock
         ├─ POST /jobs/{id}/logs      ──▶ 内存日志缓存 ──▶ SSE ──▶ Dashboard
         ├─ POST /jobs/{id}/metrics   ──▶ SQLite metrics ──▶ ECharts 曲线
         └─ POST /jobs/{id}/heartbeat ──▶ SQLite heartbeats ──▶ Dashboard GPU 卡片
```

---

## 5. API 变更清单（阶段三新增）

| 方法 | 路径 | 说明 | 状态 |
|:---|:---|:---|:---|
| `GET` | `/jobs` | 任务列表（支持 status/limit 过滤） | 待开发 |
| `GET` | `/jobs/{id}/logs/stream` | SSE 实时日志流 | 待开发 |
| `GET` | `/jobs/{id}/metrics` | 历史指标（已有，Dashboard 直接用） | ✅ |
| `GET` | `/jobs/{id}/heartbeat` | 最新心跳（已有） | ✅ |
| `POST` | `/webhook/github` | Push 自动建任务（加固） | 部分完成 |

---

## 6. 验证标准（阶段三必须通过）

1. **GitOps 触发**: `git push` → Webhook → 云服务器出现 `PENDING` 任务
2. **Agent 自动执行**: 无需手动 `curl` 创建任务，Agent 自动抢占并训练
3. **指标曲线**: Dashboard 详情页 Loss/Reward 曲线随训练实时更新
4. **日志流**: Dashboard 日志区实时显示训练输出（SSE 或轮询）
5. **状态正确**: 训练结束后任务变为 `COMPLETED`，失败为 `FAILED`
6. **mock 验收**: 用 `examples/train_mock.py` 可在 1 分钟内完成一次完整演示

---

## 7. 测试方案

### 7.1 快速验收（推荐，用 mock）

```bash
# 1. 云服务器启动
cd server && python main.py

# 2. 创建 mock 训练任务
curl -X POST http://47.103.63.175:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/Lee-Weather/agi_origin.git",
    "commit_sha": "main"
  }'

# 3. 训练机 Agent（使用 mock 命令）
export GRADMOTION_SERVER_URL=http://47.103.63.175:8000
export GRADMOTION_TRAIN_COMMAND="python examples/train_mock.py"
python agent.py

# 4. 浏览器验收
open http://47.103.63.175:8000/static/dashboard.html?id={job_id}
```

> 注：`train_mock.py` 可放在 NetTrainBridge/examples/ 并 push 到 agi_origin，或作为 agi_origin 仓库内脚本。

### 7.2 完整 GitOps 验收

```bash
# 1. 配置 GitHub Webhook 指向云服务器
# 2. 训练机 Agent 常驻运行（真实 train_command）
# 3. 在 agi_origin 修改代码并 push
git add . && git commit -m "test gradmotion" && git push
# 4. 观察 Dashboard 自动出现新任务并跑曲线
```

### 7.3 真实 agi_origin 训练验收

```bash
# Agent 使用默认命令（阶段二已验证）
export GRADMOTION_TRAIN_COMMAND="python humanoid/scripts/train_with_metrics.py --task=x1_dh_stand --run_name={job_id} --headless"

# push 触发 或 手动 curl 创建任务
# Dashboard 应能看到日志；指标取决于 train_with_metrics 是否部署
```

---

## 8. 风险与对策

| 风险 | 对策 |
|:---|:---|
| GitHub Webhook 无法访问云服务器 | 检查安全组 8000 端口；考虑内网穿透或 GitHub Actions 中转 |
| agi_origin 不写 metrics.jsonl | 阶段三用 `train_mock` 验收曲线；真实训练用 `train_with_metrics.py` |
| SSE 被 Nginx 缓冲 | 响应头加 `Cache-Control: no-cache`、`X-Accel-Buffering: no` |
| Dashboard 指标过多卡顿 | `since_step` 增量拉取；ECharts 只保留最近 1000 点 |
| Webhook 重复创建任务 | 同一 `commit_sha` + `repo_url` 去重 |
| `asyncio.run` 嵌套 bug | webhook 后台任务改为同步 `INSERT` |

---

## 9. 时间估算

| 步骤 | 预计工作量 |
|:---|:---|
| Step 1: GET /jobs 列表 | 0.5 天 |
| Step 2: SSE 日志流 | 0.5 天 |
| Step 3: train_mock.py | 0.5 天 |
| Step 4: Webhook 加固 + GitHub 配置 | 0.5 天 |
| Step 5: Dashboard ECharts 详情页 | 1–1.5 天 |
| Step 6: agi_origin 指标适配 | 1 天 |
| Step 7: 验收脚本 + 文档 | 0.5 天 |
| **总计** | **约 4–5 天** |

---

## 10. 与阶段四的边界

阶段三 **不做** 以下内容（留给阶段四）：

- API Token 认证（`auth.py`）
- Agent 断网重连增强
- systemd 部署脚本
- 模型分片上传优化（阶段二已基本实现）
- Dashboard 登录页

---

## 11. 参考资料

- [架构蓝图](plan_1.md) — Dashboard URL、`metrics.jsonl` 约定
- [开发阶段规划](dev_phases.md)
- [阶段一服务器计划](phase1_server_dev_plan.md)
- [阶段二 Agent 计划](phase2_agent_dev_plan.md)
- [agi_origin 仓库](https://github.com/Lee-Weather/agi_origin)
