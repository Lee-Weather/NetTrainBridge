# GradMotion

将本地 `agibot_x1_train-runner` 项目通过 SSH 传输到远程训练服务器 `10.12.201.5`，自动完成环境检查、代码上传、依赖安装与训练启动。

当前版本（阶段一）提供**命令行工具** `gradmotion-pipeline`，行为与 [`post-201-5/SKILL.md`](post-201-5/SKILL.md) 中的流程一致。后续版本将提供 Web 界面。

## 环境要求

| 项 | 要求 |
| --- | --- |
| 操作系统 | Windows 10+（已验证 OpenSSH） |
| Python | 3.10+ |
| 网络 | 可访问 `10.12.201.5:22` |
| SSH | 首次使用需服务器**用户名 + 密码**（用于一次性配置）；配置完成后使用密钥免密登录 |
| 本地项目 | 含 `humanoid/scripts/train.py`；若 `--resume`，还需含对应 checkpoint |

Checkpoint 路径须含 `exported_data/` 层，例如：

```
logs/x1_dh_stand/exported_data/2026-01-14_09-58-10test_20_video/model_6000.pt
```

## 安装

```powershell
cd e:\gradmotion

# 建议使用虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -e ".[dev]"
```

安装后可使用：

- `gradmotion-pipeline`（推荐）
- `python -m core`（等价入口）

验证安装：

```powershell
gradmotion-pipeline --help
```

## 配置

默认配置在仓库根目录 [`config.yaml`](config.yaml)（**通用模板**，不含本机路径）。

### 本机覆盖（必做）

复制示例并改名为 `config.local.yaml`（已在 `.gitignore` 中，不会提交）：

```powershell
copy config.local.yaml.example config.local.yaml
```

只写需要改的字段即可；未写的字段继续沿用 `config.yaml`：

```yaml
remote:
  host: "10.12.201.5"    # 若服务器不同可改
  user: "robot"          # 远程登录用户名

defaults:
  local_path: "e:\\你的路径\\agibot_x1_train-runner"
  run_name: "test_20_video"
  load_run: "2026-01-14_09-58-10test_20_video"
  checkpoint: 6000
```

### 环境变量（可选）

| 变量 | 作用 |
| --- | --- |
| `GRADMOTION_REMOTE_HOST` | 覆盖远程主机 |
| `GRADMOTION_LOCAL_PATH` | 覆盖默认本地项目路径 |
| `GRADMOTION_LOG=DEBUG` | 打印 ssh/scp 命令参数 |

### 主要配置项说明

| 配置 | `config.yaml` 模板值 | 说明 |
| --- | --- | --- |
| `remote.host` | `YOUR_SERVER_IP` | 在 `config.local.yaml` 中填写真实地址 |
| `remote.user` | `YOUR_SSH_USER` | SSH 用户名 |
| `remote.exp_base` | `/home/YOUR_USER/experiments` | 远程实验根目录 |
| `conda.env` | `YOUR_CONDA_ENV` | Conda 环境名 |
| `defaults.local_path` | `C:\path\to\...` | 在 `config.local.yaml` 中填写本机项目路径 |
| `defaults.task` | `x1_dh_stand` | 训练任务 |
| `server.poll_interval_sec` | `15` | `run` 监视日志时的轮询间隔（秒） |

## 首次使用：配置 SSH 免密登录

GradMotion 通过 OpenSSH 连接服务器（`BatchMode=yes`，不支持每次手输密码）。**首次使用前**需完成一次性配置：在本机生成密钥，并把公钥写入服务器。

### 方式一：专用命令（推荐）

```powershell
gradmotion-pipeline setup-ssh
```

按提示输入服务器密码（仅此次使用，不会保存到配置文件）。成功后输出：

```
Passwordless SSH OK for robot@10.12.201.5
```

### 方式二：提交训练时自动引导

直接运行 `run` / `preflight` 等命令时，若检测到尚未配置免密登录，终端会询问：

```
SSH key authentication is not configured for robot@10.12.201.5.
Configure passwordless SSH now? [Y/n]:
```

输入 `y` 并输入密码即可完成配置。

### 工作原理

1. 若本机没有 `~/.ssh/id_ed25519`（或 `id_rsa`），自动 `ssh-keygen` 生成密钥对  
2. 使用密码登录服务器一次，将公钥追加到 `~/.ssh/authorized_keys`  
3. 之后所有命令均走密钥免密，与手动配置效果相同  

### 前提与限制

| 条件 | 说明 |
| --- | --- |
| 服务器允许密码登录 | `sshd` 需开启 `PasswordAuthentication`（至少首次配置时） |
| 用户有写权限 | 能写入自己的 `~/.ssh/authorized_keys` |
| 密码禁用场景 | 若服务器完全禁止密码登录，需管理员手动将你的公钥加入 `authorized_keys` |

验证免密是否生效：

```powershell
ssh -p 22 -o BatchMode=yes robot@10.12.201.5 "echo connected"
```

应直接输出 `connected`，不要求输入密码。

## 快速开始

```powershell
# 1. 首次：配置 SSH 免密（仅需一次）
gradmotion-pipeline setup-ssh

# 2. 创建 config.local.yaml，设置 defaults.local_path 等（见上文）

# 3. 检查 SSH 与 conda 环境
gradmotion-pipeline preflight

# 4. 预览将要执行的远程命令（不真正执行）
gradmotion-pipeline dry-run --path "e:\X1\real_test\exp1\agibot_x1_train-runner"

# 5. 提交并运行完整流水线（会 scp 上传并占用 GPU）
gradmotion-pipeline run --path "e:\X1\real_test\exp1\agibot_x1_train-runner"
```

成功启动后终端会输出实验目录与远程 PID，例如：

```
Experiment directory: exp_20260611_153045
Remote PID: 12345
```

## 命令参考

### `setup-ssh` — 一次性配置免密登录

在本机生成（或复用）SSH 密钥，并用服务器密码将公钥安装到 `authorized_keys`。

```powershell
gradmotion-pipeline setup-ssh
```

若已配置成功，会提示 `Passwordless SSH already works` 并直接退出。

---

### `preflight` — 连通性与环境预检

仅检查 SSH 登录和 conda `F1` 环境，不上传代码、不启动训练。执行前会检查 SSH 是否已配置（未配置则引导 `setup-ssh`）。

```powershell
gradmotion-pipeline preflight
```

预期输出含 `F1_OK`。

---

### `dry-run` — 预览命令

打印流水线各步骤将执行的远程命令，不发起 scp 或训练，**不需要** SSH 已配置。

```powershell
gradmotion-pipeline dry-run
gradmotion-pipeline dry-run --path "e:\...\agibot_x1_train-runner"
```

---

### `run` — 完整训练流水线

自动执行：预检 → 创建实验目录 → scp 传输 → 验证 → pip install → nohup 启动 → 轮询日志。执行前会检查 SSH 是否已配置。

```powershell
# 使用 config 中的默认路径与参数
gradmotion-pipeline run

# 指定本地路径
gradmotion-pipeline run --path "e:\...\agibot_x1_train-runner"

# 启动后立即退出，不阻塞监视日志
gradmotion-pipeline run --no-watch

# 远程已有 train.py 时仍强制启动（慎用，可能多进程抢 GPU）
gradmotion-pipeline run --force
```

**训练参数**（均可覆盖 `config.yaml` 默认值）：

| 参数 | 说明 |
| --- | --- |
| `--path` | 本地项目根目录 |
| `--task` | 训练任务，如 `x1_dh_stand` |
| `--run-name` | 运行名称 |
| `--headless` / `--no-headless` | 是否 headless |
| `--resume` / `--no-resume` | 是否从 checkpoint 恢复 |
| `--load-run` | resume 时的 load_run |
| `--checkpoint` | checkpoint 编号，如 `6000` |

示例：从零训练（不 resume）

```powershell
gradmotion-pipeline run --no-resume --path "e:\...\agibot_x1_train-runner"
```

---

### `status` / `logs` / `watch` — 查看已有实验

```powershell
# 列出远程所有正在训练的项目（无需参数）
gradmotion-pipeline status

# 查看指定实验的进程与最新指标
gradmotion-pipeline status exp_20260611_153045

# 拉取日志末尾 45 行
gradmotion-pipeline logs exp_20260611_153045

# 指定行数
gradmotion-pipeline logs exp_20260611_153045 --lines 100

# 持续轮询日志（每 15s，直到训练结束）
gradmotion-pipeline watch exp_20260611_153045
```

无参数 `status` 输出示例（多个训练并行时逐条列出）：

```
Found 2 running training job(s):

--- [1] exp_20260611_153045 ---
pid=12345
task=x1_dh_stand
run_name=test_20_video
project_path=/home/robot/czy/exp1/exp_20260611_153045/agibot_x1_train-runner
log_file=train_test_20_video.log
learning_iteration=142/5000
mean_reward=12.34
mean_episode_length=1288.0
```

指定时间戳时输出示例：

```
alive=True pid=12345
learning_iteration=142/5000
mean_reward=12.34
mean_episode_length=1288.0
```

若无运行中的训练，输出 `No running training jobs.`。

---

### `stop` — 停止远程训练

```powershell
gradmotion-pipeline stop exp_20260611_153045

# 或直接指定 PID
gradmotion-pipeline stop exp_20260611_153045 --pid 12345
```

## 流水线说明

每次 `run` 会在远程创建独立实验目录：

```
/home/robot/czy/exp1/exp_<YYYYMMDD_HHMMSS>/agibot_x1_train-runner/
```

执行步骤：

1. **preflight** — SSH + conda `F1` 验证  
2. **mkdir** — 创建带时间戳的实验目录  
3. **transferring** — `scp -r` 上传项目；完成后删除远程 `skills/`、`czy/data/`  
4. **verifying** — 检查 `train.py` 与 checkpoint（resume 时）  
5. **installing** — `pip install -e .`  
6. **starting** — `nohup python humanoid/scripts/train.py ...`  
7. **running** — 轮询进程与日志（`run` 默认开启，除非 `--no-watch`）

训练日志文件：`train_<run_name>.log`（位于远程项目根目录）。

## 提交前校验

`run` 会在本地自动检查：

- 项目路径存在且含 `humanoid/scripts/train.py`
- `--resume` 时 checkpoint 文件存在（路径含 `exported_data/`）
- 远程是否已有 `train.py` 进程（有则拒绝，除非加 `--force`）

## 测试

```powershell
# 单元测试与 mock 集成测试（不连接真实服务器）
python -m pytest tests/ -q
```

## 常见问题

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| `SSH key authentication is not configured` | 尚未配置免密登录 | 运行 `gradmotion-pipeline setup-ssh`，或在 `run` 时按提示配置 |
| `Permission denied (publickey)` | 密钥未生效或服务器未收录公钥 | 重新运行 `setup-ssh`；或检查 `~/.ssh/id_ed25519.pub` 是否在服务器 `authorized_keys` 中 |
| `Authentication failed (wrong password...)` | 密码错误或服务器禁用密码登录 | 确认密码；若禁用密码，请管理员手动添加公钥 |
| `Validation error: checkpoint not found` | 本地缺 checkpoint 或路径不对 | 确认 `logs/<task>/exported_data/<load_run>/model_<N>.pt` 存在 |
| `Remote train.py already running` | 远程已有训练 | 先 `stop`，或确认后加 `--force` |
| `run` 在 starting 阶段卡住较久 | nohup 导致 SSH 超时 | 属正常现象；约 45s 后会检查 PID |
| scp 耗时很长 | 项目含 logs/*.pt 体积大 | 等待完成；传输期间勿重复 `run` |
| `CKPT_MISSING`（远程验证失败） | checkpoint 未随代码上传 | 确认本地 logs 目录完整 |

手动检查远程训练进程：

```powershell
ssh -p 22 -o BatchMode=yes robot@10.12.201.5 "ps aux | grep train.py | grep -v grep"
```

## 项目结构

```
gradmotion/
├── config.yaml              # 通用配置模板（提交 git）
├── config.local.yaml        # 本机覆盖（自行创建，不提交）
├── config.local.yaml.example  # 本机配置示例
├── core/                # 训练流水线核心
│   ├── cli.py           # 命令行入口
│   ├── pipeline.py      # 流水线编排
│   ├── ssh.py           # ssh/scp 封装
│   └── ssh_setup.py     # 首次免密配置
├── post-201-5/          # Agent Skill 文档
├── plan/                # 产品规划
├── tests/               # 测试
└── README.md
```

## 路线图

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| 阶段一 | CLI 流水线（`gradmotion-pipeline`） | ✅ 当前 |
| 阶段二 | FastAPI + SQLite Job 管理 | 计划中 |
| 阶段三 | Web 图形界面 | 计划中 |

详细规划见 [`plan/plan_1.md`](plan/plan_1.md)。
