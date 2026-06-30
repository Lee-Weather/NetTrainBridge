# 去 GUI 化改造计划：API + CLI 替代 Web Dashboard

> 项目名称：**NetTrainBridge**（不再使用 GradMotion 命名）

## 1. 背景与目标

### 1.1 现状

阶段三已完成 **Web Dashboard**（`index.html` 任务列表 + `dashboard.html` 曲线/日志），但存在以下问题：

| 问题 | 说明 |
|:---|:---|
| ECharts 依赖 CDN | 国内网络不稳定，图表常空白 |
| 维护成本高 | HTML/JS 与后端 API 双轨维护 |
| 使用场景不匹配 | 实际使用以 `git push` + 终端为主，浏览器非刚需 |
| 阶段四冲突 | 原计划「Dashboard 登录页」进一步增加 GUI 复杂度 |

### 1.2 改造目标

**去掉一切图形界面，保留纯 API 服务 + 命令行监控工具。**

```
改造前:  git push → Agent 训练 → 浏览器打开 Dashboard 看曲线
改造后:  git push → Agent 训练 → 终端 ntb watch <job_id> 看状态/指标/日志
```

### 1.3 设计原则

1. **云服务器只做 API**：不托管任何 HTML/CSS/JS 静态资源
2. **CLI 只调现有 API**：不新增业务逻辑到服务端（除根路径重定向可选）
3. **SSE 保留**：`/jobs/{id}/logs/stream` 是流式 API，非 GUI，CLI `ntb logs --follow` 可消费
4. **最小破坏**：Agent、Webhook、metrics、checkpoint 链路零改动（环境变量名同步迁移，见 §9）

---

## 2. 范围界定

### 2.1 删除项

| 类别 | 文件/代码 | 操作 |
|:---|:---|:---|
| 静态页面 | `server/static/index.html` | 删除 |
| 静态页面 | `server/static/dashboard.html` | 删除 |
| 静态目录 | `server/static/` | 整目录删除 |
| 服务挂载 | `main.py` 中 `StaticFiles` mount | 删除 |
| 验收检查 | `test_phase3.sh` / `test_e2e.sh` 中 static 200 检查 | 删除并替换 |
| 阶段四 GUI | `dev_phases.md` 中「Dashboard 简单登录页」 | 从计划中移除 |
| 旧品牌文案 | 代码/文档中的 `GradMotion`、`gradmotion` | 统一改为 `NetTrainBridge` / `nettrainbridge` |

### 2.2 保留项（不变）

| 模块 | 说明 |
|:---|:---|
| `server/api/jobs.py` | 任务 CRUD、抢占、状态 |
| `server/api/webhook.py` | GitHub Webhook |
| `server/api/logs.py` | 日志上报、查询、**SSE 流** |
| `server/api/metrics.py` | 指标上报、增量查询 |
| `server/api/heartbeat.py` | GPU 心跳 |
| `server/api/checkpoint.py` | 模型上传/下载 |
| `agent/*` | Agent 全模块 |
| `contrib/agi_origin/.../train_with_metrics.py` | 指标桥接脚本 |

### 2.3 新增项

| 模块 | 说明 |
|:---|:---|
| `cli/ntb.py` | 命令行入口（单文件，约 200–300 行） |
| `cli/requirements.txt` | 依赖 `httpx`（与 Agent 一致） |
| `server/test_cli.sh` | CLI 冒烟测试（可选，或并入 test_phase3.sh） |

---

## 3. CLI 设计（`ntb` 命令）

CLI 名称取 **NetTrainBridge** 缩写 `ntb`，入口文件 `cli/ntb.py`。

### 3.1 安装与配置

```bash
cd cli && pip install -r requirements.txt

# 与 Agent 共用同一环境变量（新前缀）
export NETTRAINBRIDGE_SERVER_URL=http://47.103.63.175:8000
```

### 3.2 子命令一览

| 命令 | 功能 | 对应 API |
|:---|:---|:---|
| `ntb health` | 健康检查 | `GET /health` |
| `ntb jobs` | 任务列表 | `GET /jobs?status=&limit=` |
| `ntb job <id>` | 单任务详情 | `GET /jobs/{id}` |
| `ntb logs <id>` | 打印最近 N 行日志 | `GET /jobs/{id}/logs?tail=N` |
| `ntb logs <id> -f` | 实时跟踪日志 | `GET /jobs/{id}/logs/stream`（SSE） |
| `ntb metrics <id>` | 打印指标表格 | `GET /jobs/{id}/metrics` |
| `ntb heartbeat <id>` | 打印最新 GPU 心跳 | `GET /jobs/{id}/heartbeat` |
| `ntb watch <id>` | **综合监控**（推荐） | 轮询 job + metrics + heartbeat，每 5s 刷新 |
| `ntb create` | 手动创建任务（调试用） | `POST /jobs` |

### 3.3 `ntb watch` 终端输出示例（替代 Dashboard）

```
NetTrainBridge watch  77c412f1392c  [RUNNING]  agent-001
────────────────────────────────────────────────────
Step   Loss      Reward    GPU     Mem
  21   0.0124    3.10      92.1%   18.2/24.0 GB
  22   0.0118    3.18      91.8%   18.2/24.0 GB
  23   0.0149    3.24      92.0%   18.2/24.0 GB
────────────────────────────────────────────────────
[Ctrl+C 退出]  日志: ntb logs 77c412f1392c -f
```

### 3.4 实现要点

- 使用 `argparse` 子命令，无第三方 CLI 框架
- `ntb watch`：`since_step` 增量拉 metrics，只打印新 step
- `ntb logs -f`：解析 SSE `data:` 行，stdout 实时输出
- 错误处理：404 打印友好提示；网络失败 exit code 1
- 输出默认人类可读表格；加 `--json` 时输出原始 JSON（便于脚本集成）

---

## 4. 服务端改动

### 4.1 `server/main.py`

```diff
- from fastapi.staticfiles import StaticFiles
  ...
- app.mount("/static", StaticFiles(directory="static"), name="static")
```

可选：根路径返回 API 说明 JSON（非 GUI）：

```python
@app.get("/")
async def root():
    return {
        "name": "NetTrainBridge Server",
        "docs": "/docs",
        "health": "/health",
        "cli": "ntb jobs / ntb watch <job_id>",
    }
```

### 4.2 无数据库 / 无 API 契约变更

所有现有 REST 端点保持兼容；Agent 与 GitHub Webhook 仅需同步环境变量前缀（见 §9）。

---

## 5. 文档更新清单

| 文件 | 改动 |
|:---|:---|
| `README.md` | 标题改为 NetTrainBridge；删除 Dashboard 链接；增加 `ntb watch` 用法 |
| `server/README.md` | 删除浏览器访问说明；补充 CLI 示例 |
| `plan/dev_phases.md` | 阶段三改为「完整训练流 + CLI」；阶段四去掉登录页 |
| `plan/phase3_dev_plan.md` | 文首加注「Dashboard 已废弃，见 remove_gui_plan.md」 |
| `plan/plan_1.md` | 架构图与文案统一为 NetTrainBridge |
| 全仓库 | `GradMotion` → `NetTrainBridge`，`GRADMOTION_*` → `NETTRAINBRIDGE_*` |

---

## 6. 测试与验收

### 6.1 修改 `server/test_phase3.sh`

| 原检查项 | 新检查项 |
|:---|:---|
| `dashboard.html` 200 | 删除 |
| `index.html` 200 | 删除 |
| — | `GET /` 返回 JSON 或 404（按实现） |
| — | `python cli/ntb.py health` 通过 |
| — | `python cli/ntb.py jobs` 返回列表 |

### 6.2 端到端验收流程（替代浏览器）

```bash
# 1. 平台 API 验收
bash server/test_phase3.sh http://47.103.63.175:8000

# 2. 创建或 Webhook 触发任务后
export NETTRAINBRIDGE_SERVER_URL=http://47.103.63.175:8000
python cli/ntb.py jobs
python cli/ntb.py watch <job_id>          # 终端看指标
python cli/ntb.py logs <job_id> -f        # 另开终端看日志

# 3. 训练完成后
python cli/ntb.py job <job_id>            # 状态 COMPLETED
wget http://47.103.63.175:8000/jobs/<job_id>/checkpoint/model_1.pt
```

### 6.3 完成标准

| # | 检查项 |
|:---|:---|
| 1 | `server/static/` 目录不存在 |
| 2 | `curl /static/dashboard.html` 返回 404 |
| 3 | Agent 正常上报 metrics/logs，API 可查 |
| 4 | `ntb watch` 能实时显示 loss/reward 增量 |
| 5 | `ntb logs -f` 能消费 SSE |
| 6 | `test_phase3.sh` 全部通过（无 static 项） |
| 7 | README 无浏览器 Dashboard 引用 |
| 8 | 文档与日志中不再出现 GradMotion / `GRADMOTION_*`（旧名仅代码内兼容读取） |

---

## 7. 实施步骤（建议顺序）

| 步骤 | 内容 | 预估 | 依赖 |
|:---|:---|:---|:---|
| **Step 0** | 全仓库品牌重命名：`GradMotion`→`NetTrainBridge`，`GRADMOTION_*`→`NETTRAINBRIDGE_*`（保留旧 env 兼容） | 0.3 天 | ✅ 已完成 |
| **Step 1** | 新建 `cli/ntb.py` + `requirements.txt`，实现 `health` / `jobs` / `job` | 0.5 天 | ✅ 已完成 |
| **Step 2** | 实现 `metrics` / `heartbeat` / `logs` / `logs -f` | 0.5 天 | ✅ 已完成 |
| **Step 3** | 实现 `ntb watch`（核心替代 Dashboard） | 0.5 天 | ✅ 已完成 |
| **Step 4** | 删除 `server/static/`，修改 `main.py` | 0.1 天 | ✅ 已完成 |
| **Step 5** | 更新 `test_phase3.sh`、`test_e2e.sh` | 0.2 天 | ✅ 已完成 |
| **Step 6** | 更新 README、`dev_phases.md` 等文档 | 0.2 天 | ✅ 已完成 |
| **Step 7** | 云服务器部署 + 端到端验证 | 0.3 天 | Step 6 |

**合计：约 2.5 天**

---

## 8. 风险与回滚

| 风险 | 缓解 |
|:---|:---|
| 用户习惯浏览器 | README 提供 `ntb watch` 一键命令；`curl` 示例保留 |
| CLI 未安装 Python | 云服务器 / 本机均有 conda；可后续打包 `pip install nettrainbridge-cli` |
| 误删 SSE | SSE 是 API 能力，明确保留；仅删 HTML |
| 需要回滚 GUI | `git revert` 恢复 `static/` 与 `main.py` mount |
| 旧环境变量失效 | `config.py` 同时读取 `NETTRAINBRIDGE_*` 与 `GRADMOTION_*`（后者 deprecated） |

---

## 9. 环境变量重命名（GradMotion → NetTrainBridge）

### 9.1 映射表

| 旧名（deprecated） | 新名 |
|:---|:---|
| `GRADMOTION_SERVER_URL` | `NETTRAINBRIDGE_SERVER_URL` |
| `GRADMOTION_PROXY` | `NETTRAINBRIDGE_PROXY` |
| `GRADMOTION_AGENT_ID` | `NETTRAINBRIDGE_AGENT_ID` |
| `GRADMOTION_WORKSPACE` | `NETTRAINBRIDGE_WORKSPACE`（默认 `~/czy/nettrainbridge`） |
| `GRADMOTION_CONDA_ENV` | `NETTRAINBRIDGE_CONDA_ENV` |
| `GRADMOTION_TRAIN_COMMAND` | `NETTRAINBRIDGE_TRAIN_COMMAND` |
| `GRADMOTION_METRICS_FILE` | `NETTRAINBRIDGE_METRICS_FILE` |
| `GRADMOTION_JOB_ID` | `NETTRAINBRIDGE_JOB_ID` |
| `GRADMOTION_WEBHOOK_SECRET` | `NETTRAINBRIDGE_WEBHOOK_SECRET` |
| `GRADMOTION_ALLOWED_REPOS` | `NETTRAINBRIDGE_ALLOWED_REPOS` |
| `GRADMOTION_HOST` / `PORT` / `DB_PATH` / `DATA_DIR` | `NETTRAINBRIDGE_HOST` 等 |
| `GRADMOTION_API_TOKEN` | `NETTRAINBRIDGE_API_TOKEN` |

### 9.2 兼容策略

`agent/config.py`、`server/config.py` 优先读 `NETTRAINBRIDGE_*`；若未设置则回退 `GRADMOTION_*` 并打 deprecation 日志。一个版本后移除旧名。

### 9.3 日志 logger 名

| 旧 | 新 |
|:---|:---|
| `gradmotion` | `nettrainbridge` |
| `gradmotion.agent` | `nettrainbridge.agent` |

---

## 10. 对阶段四的影响

| 原阶段四项 | 调整后 |
|:---|:---|
| Dashboard 简单登录页 | **取消** |
| API Token 认证 | **保留**，CLI 通过 `NETTRAINBRIDGE_API_TOKEN` 传 Header |
| Agent 崩溃恢复 | **保留** |
| systemd 部署脚本 | **保留** |
| 分片上传模型 | **保留**（已实现） |

阶段四 CLI 适配：所有 `ntb` 请求增加可选 Header `Authorization: Bearer $NETTRAINBRIDGE_API_TOKEN`。

---

## 11. 改造后目录结构

```
NetTrainBridge/
├── server/                    # 纯 API，无 static/
│   ├── main.py
│   ├── api/
│   └── test_phase3.sh
├── cli/                       # 【新增】
│   ├── ntb.py
│   └── requirements.txt
├── agent/                     # 环境变量前缀迁移
├── contrib/agi_origin/        # NETTRAINBRIDGE_METRICS_FILE
└── plan/
    ├── remove_gui_plan.md     # 本文件
    └── dev_phases.md          # 更新阶段描述
```

---

## 12. 决策记录

| 决策 | 选择 | 理由 |
|:---|:---|:---|
| 项目名称 | NetTrainBridge | 与仓库名一致，弃用 GradMotion |
| CLI 命令名 | `ntb` | NetTrainBridge 缩写，简短好打 |
| 是否保留 SSE | 保留 | CLI follow 日志需要；非 GUI |
| CLI 语言 | Python + httpx | 与 Agent 技术栈一致，可复用配置 |
| 是否做 Web API 文档页 | 保留 FastAPI `/docs` | 开发调试够用，非面向用户的 GUI |
| 是否删除 metrics 存储 | 不删 | CLI watch 依赖服务端 metrics API |
| 单文件 vs 多模块 CLI | 先单文件 `ntb.py` | 符合最小范围原则，后续可拆分 |
| 旧环境变量 | 保留一个版本兼容 | 避免训练机/云服务器同时改配置 |

---

## 13. 下一步

**请确认本计划后，按 Step 0 → Step 7 顺序实施。** 确认事项：

1. `ntb watch` 终端表格样式是否满足监控需求？
2. 是否需要 `ntb create` 手动建任务（调试）？
3. 根路径 `/` 返回 JSON 说明还是直接 404？

确认后即可开始编码，不再新增 Web 页面。
