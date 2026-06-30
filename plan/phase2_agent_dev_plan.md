# 第二阶段：Agent 开发计划

## 目标
在 `agent/` 中实现 Agent 程序，部署在公司训练机上，能够：
- 轮询云服务器获取待处理任务
- 抢占任务并执行训练
- 实时上报日志、指标、心跳
- 训练完成后上传模型

## 前提条件
- 阶段一的云服务器 API 已部署并可访问
- 训练机可通过代理访问云服务器
- 已有测试用的训练脚本

---

## 1. 技术栈
- Python 3.10+
- HTTP 客户端: httpx (支持异步)
- 进程管理: subprocess
- 日志解析: 文件增量读取
- GPU 监控: pynvml (可选，用于心跳上报 GPU 状态)

---

## 2. 目录结构

```text
agent/
├── agent.py              # 主程序入口 (状态机循环)
├── config.py             # 配置 (云服务器地址、代理、轮询间隔)
├── api_client.py         # 云服务器 API 客户端
├── job_runner.py         # 任务执行器 (git clone + 启动训练)
├── log_monitor.py        # 日志监控 (增量读取训练日志)
├── metrics_reader.py     # 指标读取 (解析 metrics.jsonl)
├── heartbeat.py          # 心跳上报 (GPU 状态、进程状态)
├── requirements.txt
└── README.md
```

---

## 3. 开发顺序 (6 个子阶段)

### Step 1: 基础设施
**产出**: `requirements.txt` + `config.py`
- 创建 `requirements.txt` (httpx, pydantic, pynvml)
- 完成 `config.py` (云服务器地址、代理配置、轮询间隔、工作目录)

```python
# config.py 示例
@dataclass
class AgentConfig:
    server_url: str = "http://云服务器IP:8000"
    proxy: str = "http://10.12.201.122:39000"  # 公司代理
    poll_interval: int = 30  # 轮询间隔(秒)
    workspace: str = "/workspace/nettrainbridge"  # 代码存放目录
    agent_id: str = "agent-001"  # Agent 唯一标识
```

**验证**: `python -c "from config import AgentConfig; c = AgentConfig.load(); print(c.server_url)"` 正常输出

---

### Step 2: API 客户端
**产出**: `api_client.py`

封装所有对云服务器的 HTTP 请求，包含：
- 重试逻辑 (网络抖动自动重试)
- 代理支持
- 超时设置

| 方法 | HTTP 请求 | 用途 |
|:---|:---|:---|
| `get_pending_jobs()` | `GET /jobs/pending` | 获取待处理任务 |
| `claim_job(job_id)` | `PUT /jobs/{id}/claim` | 抢占任务 |
| `update_status(job_id, status)` | `PUT /jobs/{id}/status` | 更新任务状态 |
| `append_logs(job_id, content)` | `POST /jobs/{id}/logs` | 上报日志 |
| `append_metrics(job_id, metrics)` | `POST /jobs/{id}/metrics` | 上报指标 |
| `send_heartbeat(job_id, gpu_info)` | `POST /jobs/{id}/heartbeat` | 发送心跳 |
| `upload_checkpoint(job_id, file_path)` | `POST /jobs/{id}/checkpoint` | 上传模型 |

**验证**: 手动调用各方法，确认云服务器返回正确响应

---

### Step 3: 任务执行器
**产出**: `job_runner.py`

负责任务的完整执行流程：

```
clone 代码 → checkout commit → pip install → 启动训练子进程
```

核心功能：
- `clone_repo(repo_url, commit_sha, target_dir)`: 克隆并切换到指定 commit
- `install_dependencies(job_dir)`: 安装 Python 依赖
- `start_training(job_dir, job_id)`: 启动训练子进程，返回 Popen 对象
- `cleanup_job(job_dir)`: 清理工作目录 (可选)

```python
# job_runner.py 核心接口
class JobRunner:
    def __init__(self, config: AgentConfig, api_client: APIClient):
        ...

    async def prepare(self, job: JobResponse) -> Path:
        """准备任务环境: clone + install"""
        ...

    def start(self, job_dir: Path, job_id: str) -> subprocess.Popen:
        """启动训练进程"""
        ...

    def wait(self, process: subprocess.Popen) -> int:
        """等待训练完成，返回 exit_code"""
        ...
```

**验证**: 手动创建任务，调用 `prepare` + `start`，确认训练脚本正确执行

---

### Step 4: 日志与指标监控
**产出**: `log_monitor.py` + `metrics_reader.py`

#### 4.1 日志监控 (log_monitor.py)
基于文件偏移量增量读取日志文件，避免重复读取：

```python
class LogMonitor:
    def __init__(self, log_file: Path):
        self.log_file = log_file
        self.position = 0  # 当前读取位置

    def read_new_lines(self) -> list[str]:
        """读取上次位置之后的新行"""
        with open(self.log_file, 'r') as f:
            f.seek(self.position)
            lines = f.readlines()
            self.position = f.tell()
        return [line.strip() for line in lines if line.strip()]
```

#### 4.2 指标读取 (metrics_reader.py)
解析 `metrics.jsonl` 文件中的新增行：

```python
# metrics.jsonl 格式 (训练脚本写入)
# {"step": 100, "loss": 0.5, "reward": 1.2}
# {"step": 200, "loss": 0.3, "reward": 1.5}

class MetricsReader:
    def __init__(self, metrics_file: Path):
        self.metrics_file = metrics_file
        self.last_step = -1

    def read_new_metrics(self) -> list[dict]:
        """读取 step > last_step 的新指标"""
        ...
```

**验证**: 创建测试日志文件和 metrics.jsonl，调用读取方法确认正确增量读取

---

### Step 5: 心跳上报
**产出**: `heartbeat.py`

定期采集系统状态并上报：

```python
class HeartbeatReporter:
    def __init__(self, api_client: APIClient, interval: int = 30):
        ...

    def collect_gpu_info(self) -> dict:
        """使用 pynvml 采集 GPU 信息"""
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            return {
                "gpu_util": util.gpu,
                "gpu_mem_used": mem.used / 1024**3,  # GB
                "gpu_mem_total": mem.total / 1024**3,  # GB
            }
        except:
            return {}

    async def start(self, job_id: str):
        """启动心跳上报循环"""
        while True:
            gpu_info = self.collect_gpu_info()
            await self.api_client.send_heartbeat(job_id, gpu_info)
            await asyncio.sleep(self.interval)
```

**验证**: 运行心跳上报，在云服务器数据库中确认收到心跳数据

---

### Step 6: Agent 主程序
**产出**: `agent.py`

主程序状态机循环：

```
┌──────────────────────────────────────────────────────────────┐
│                        Agent 主循环                          │
│                                                              │
│  ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐ │
│  │  IDLE   │───▶│ PREPARE  │───▶│ RUNNING  │───▶│ UPLOAD  │ │
│  │ (等待)  │    │ (准备)   │    │ (训练中) │    │ (上传)  │ │
│  └────▲────┘    └──────────┘    └──────────┘    └────┬────┘ │
│       │                                              │      │
│       └──────────────────────────────────────────────┘      │
│                                                              │
│  IDLE: 轮询 /jobs/pending，发现任务则抢占                    │
│  PREPARE: clone + pip install                               │
│  RUNNING: 监控进程 + 上报日志/指标/心跳                      │
│  UPLOAD: 训练完成后上传模型                                  │
└──────────────────────────────────────────────────────────────┘
```

核心代码结构：

```python
class Agent:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.api_client = APIClient(config)
        self.job_runner = JobRunner(config, self.api_client)
        self.current_job = None
        self.process = None

    async def run(self):
        """主循环"""
        while True:
            try:
                if self.current_job is None:
                    await self._poll_and_claim()
                else:
                    await self._monitor_running_job()
            except Exception as e:
                logger.error(f"Agent error: {e}")
            await asyncio.sleep(self.config.poll_interval)

    async def _poll_and_claim(self):
        """轮询并抢占任务"""
        jobs = await self.api_client.get_pending_jobs()
        if jobs:
            job = jobs[0]
            await self.api_client.claim_job(job.id)
            await self._prepare_and_start(job)

    async def _prepare_and_start(self, job: JobResponse):
        """准备环境并启动训练"""
        job_dir = await self.job_runner.prepare(job)
        self.process = self.job_runner.start(job_dir, job.id)
        await self.api_client.update_status(job.id, "RUNNING")
        self.current_job = job

    async def _monitor_running_job(self):
        """监控运行中的任务"""
        # 1. 检查进程状态
        if self.process.poll() is not None:
            exit_code = self.process.returncode
            await self._on_training_complete(exit_code)
            return

        # 2. 上报日志
        # 3. 上报指标
        # 4. 心跳 (在独立协程中)

    async def _on_training_complete(self, exit_code: int):
        """训练完成处理"""
        if exit_code == 0:
            # 上传模型
            await self.api_client.update_status(self.current_job.id, "COMPLETED")
        else:
            await self.api_client.update_status(
                self.current_job.id, "FAILED",
                error_msg=f"Training failed with exit code {exit_code}"
            )
        self.current_job = None
        self.process = None
```

**验证**:
1. 云服务器创建任务
2. Agent 自动抢占并执行
3. 查看日志输出和云服务器状态变化

---

## 4. 并发模型

Agent 使用 `asyncio` 实现并发：

```python
# agent.py 主循环并发任务
async def run(self):
    tasks = [
        asyncio.create_task(self._main_loop()),      # 主循环 (轮询/抢占)
        asyncio.create_task(self._heartbeat_loop()), # 心跳上报
        asyncio.create_task(self._log_loop()),       # 日志上报
        asyncio.create_task(self._metrics_loop()),   # 指标上报
    ]
    await asyncio.gather(*tasks)
```

各任务独立运行，互不阻塞。

---

## 5. 错误处理

| 场景 | 处理策略 |
|:---|:---|
| 网络请求失败 | 重试 3 次，间隔指数退避 (1s, 2s, 4s) |
| git clone 失败 | 标记任务 FAILED，记录错误信息 |
| 训练进程崩溃 | 标记任务 FAILED，上传已有日志 |
| Agent 重启 | 启动时检查是否有 ASSIGNED 状态的任务，继续执行 |

---

## 6. 配置示例

```python
# config.py
from dataclasses import dataclass, field
import os

@dataclass
class AgentConfig:
    server_url: str = "http://云服务器IP:8000"
    proxy: str = ""  # 公司代理地址
    poll_interval: int = 30
    workspace: str = "/workspace/nettrainbridge"
    agent_id: str = "agent-001"
    heartbeat_interval: int = 30
    log_upload_interval: int = 5
    metrics_upload_interval: int = 10

    @classmethod
    def load(cls) -> "AgentConfig":
        instance = cls()
        # 环境变量覆盖
        if os.environ.get("NETTRAINBRIDGE_SERVER_URL"):
            instance.server_url = os.environ["NETTRAINBRIDGE_SERVER_URL"]
        if os.environ.get("NETTRAINBRIDGE_PROXY"):
            instance.proxy = os.environ["NETTRAINBRIDGE_PROXY"]
        if os.environ.get("NETTRAINBRIDGE_AGENT_ID"):
            instance.agent_id = os.environ["NETTRAINBRIDGE_AGENT_ID"]
        return instance
```

---

## 7. 验证标准 (阶段二必须通过)

1. **轮询抢占**: Agent 能自动发现 PENDING 任务并成功抢占
2. **代码拉取**: 能正确 clone 指定 repo 并 checkout 到指定 commit
3. **训练执行**: 能启动训练子进程并监控其状态
4. **日志上报**: 训练日志能实时出现在云服务器
5. **指标上报**: metrics.jsonl 中的指标能写入云服务器数据库
6. **心跳上报**: 云服务器能收到 GPU 状态
7. **状态流转**: PENDING → ASSIGNED → RUNNING → COMPLETED/FAILED 全流程正确
8. **崩溃恢复**: Agent 重启后能正确处理未完成任务

---

## 8. 测试方案

### 8.1 单元测试
```bash
# 测试 API 客户端
pytest tests/test_api_client.py

# 测试日志监控
pytest tests/test_log_monitor.py

# 测试指标读取
pytest tests/test_metrics_reader.py
```

### 8.2 集成测试
```bash
# 1. 启动云服务器
cd server && uvicorn main:app --host 0.0.0.0 --port 8000

# 2. 创建测试任务
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/your/test-repo", "commit_sha": "main"}'

# 3. 启动 Agent
cd agent && python agent.py

# 4. 观察日志
# [INFO] Agent 启动, ID: agent-001
# [INFO] 发现任务 abc123, 正在抢占...
# [INFO] 抢占成功, 开始 clone 代码...
# [INFO] 训练进程已启动, PID=12345
# [INFO] 心跳上报: GPU 85%, MEM 20GB/24GB
# [INFO] 训练完成, exit_code=0
# [INFO] 模型上传成功: best_model.pt (123.4 MB)
```

---

## 9. 风险与对策

| 风险 | 对策 |
|:---|:---|
| 网络不稳定导致抢占失败 | 乐观锁重试，失败后等待下一轮 |
| 训练进程卡死 | 心跳检测超时后 kill 并标记 FAILED |
| 磁盘空间不足 | 任务开始前检查，不足则跳过 |
| 代码仓库私有 | 支持 SSH key 或 Token 认证 |
| 多 Agent 同时抢占 | 云服务器使用乐观锁保证原子性 |

---

## 10. 时间估算

| 步骤 | 预计工作量 |
|:---|:---|
| Step 1: 基础设施 | 0.5 天 |
| Step 2: API 客户端 | 0.5 天 |
| Step 3: 任务执行器 | 1 天 |
| Step 4: 日志与指标监控 | 0.5 天 |
| Step 5: 心跳上报 | 0.5 天 |
| Step 6: Agent 主程序 | 1 天 |
| 测试与调试 | 0.5-1 天 |
| **总计** | **4-5 天** |

---

## 11. 依赖阶段一 API 清单

Agent 依赖以下云服务器 API（已在阶段一实现）：

| API | 用途 |
|:---|:---|
| `GET /jobs/pending` | 获取待处理任务列表 |
| `PUT /jobs/{id}/claim` | 抢占任务 |
| `PUT /jobs/{id}/status` | 更新任务状态 |
| `POST /jobs/{id}/logs` | 上报训练日志 |
| `POST /jobs/{id}/metrics` | 上报训练指标 |
| `POST /jobs/{id}/heartbeat` | 上报心跳 (待实现) |
| `POST /jobs/{id}/checkpoint` | 上传模型文件 |
| `GET /jobs/{id}` | 查询任务详情 (用于恢复) |

---

## 12. 训练仓库对接说明

### 12.1 目标仓库
- **仓库地址**: `https://github.com/Lee-Weather/agi_origin.git`
- **项目说明**: AgiBot X1 人形机器人强化学习训练代码，基于 Isaac Gym

### 12.2 训练启动命令

仓库的标准训练命令：
```bash
python scripts/train.py --task=x1_dh_stand --run_name=<run_name> --headless
```

Agent 需要适配的启动方式：
```bash
cd /workspace/nettrainbridge/<job_id>/agi_origin
python scripts/train.py --task=x1_dh_stand --run_name=<job_id> --headless
```

### 12.3 模型输出位置

训练产生的模型文件存放路径：
```
logs/<experiment_name>/exported_data/<date_time><run_name>/model_<iteration>.pt
```

Agent 需要查找最终模型的位置：
- 训练完成后，找到 `logs/` 目录下最新的 `model_*.pt`
- JIT 模型位于 `log/exported_policies/<date_time>/`

### 12.4 指标读取适配

仓库使用 Isaac Gym 进行训练，指标通过标准输出打印。需要 Agent：

1. **解析训练日志**：从 stdout 捕获类似以下格式的输出
   ```
   iteration: 100, mean_reward: 1.23, loss: 0.45
   ```

2. **或修改训练脚本**：在 `humanoid/algo/` 中添加指标写入 `metrics.jsonl` 的代码

建议方案：在仓库中添加一个包装脚本 `train_with_metrics.py`，自动将指标写入 `metrics.jsonl`：
```python
# train_with_metrics.py (添加到仓库)
import json
import sys
from pathlib import Path

# 拦截 stdout，解析指标并写入 metrics.jsonl
class MetricWriter:
    def __init__(self, metrics_file: Path):
        self.metrics_file = metrics_file

    def write(self, line: str):
        # 解析类似 "iteration: 100, mean_reward: 1.23" 的行
        if "iteration:" in line:
            # 提取指标并写入 jsonl
            ...
```

### 12.5 依赖安装

仓库需要以下依赖（Agent 在 `prepare` 阶段执行）：

```bash
# 1. 创建虚拟环境 (可选，Agent 可使用系统 Python)
conda create -n agi_env python=3.8 -y

# 2. 安装 PyTorch 1.13 + CUDA 11.7
conda install pytorch==1.13.1 torchvision==0.14.1 torchaudio==0.13.1 pytorch-cuda=11.7 -c pytorch -c nvidia -y

# 3. 安装 numpy
conda install numpy=1.23 -y

# 4. 安装 Isaac Gym (需要预先下载)
# Agent 假设 Isaac Gym 已预装在训练机上

# 5. 安装仓库
pip install -e .
```

### 12.6 JobRunner 适配代码

针对此仓库的 `job_runner.py` 启动逻辑：

```python
def start(self, job_dir: Path, job_id: str) -> subprocess.Popen:
    """启动 agi_origin 训练"""
    log_file = job_dir / "train.log"
    metrics_file = job_dir / "metrics.jsonl"

    # 构建训练命令
    cmd = [
        "python", "scripts/train_with_metrics.py",  # 使用带指标输出的包装脚本
        "--task=x1_dh_stand",
        f"--run_name={job_id}",
        "--headless",
        f"--metrics_file={metrics_file}",  # 传递指标文件路径
    ]

    with open(log_file, "w") as f:
        return subprocess.Popen(
            cmd,
            cwd=job_dir / "agi_origin",
            stdout=f,
            stderr=subprocess.STDOUT,
        )
```

### 12.7 模型上传适配

训练完成后，Agent 需要查找并上传模型：

```python
async def _upload_best_model(self, job_dir: Path, job_id: str):
    """查找并上传最佳模型"""
    logs_dir = job_dir / "agi_origin" / "logs"

    # 方案1: 上传最新的 checkpoint
    model_files = list(logs_dir.rglob("model_*.pt"))
    if model_files:
        # 按修改时间排序，取最新的
        best_model = max(model_files, key=lambda p: p.stat().st_mtime)
        await self.api_client.upload_checkpoint(job_id, best_model)

    # 方案2: 上传 JIT 模型
    jit_dir = logs_dir / "exported_policies"
    if jit_dir.exists():
        jit_files = list(jit_dir.glob("*.pt"))
        if jit_files:
            await self.api_client.upload_checkpoint(job_id, jit_files[0])
```

---

## 13. 后续扩展 (阶段三/四)

- 支持多任务并行 (多 GPU 场景)
- 断点续训支持
- 模型自动选择 best_model.pt
- 更完善的错误恢复机制
- Dashboard 实时展示 Agent 状态
