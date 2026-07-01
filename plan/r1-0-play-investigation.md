# R1-0 调研报告：play.py 与同窗工程

> 对应 [r1-sim2sim-plan.md](r1-sim2sim-plan.md) § R1-0  
> 训练代码示例：[diff/agibot_x1_train-main](diff/agibot_x1_train-main)

---

## 1. 结论摘要

| 项 | 结论 |
|:---|:---|
| eval 入口 | `humanoid/scripts/play.py`（Isaac Gym）；备选 `humanoid/scripts/sim2sim.py`（MuJoCo） |
| 模型输入路径 | `logs/x1_dh_stand/exported_data/<load_run>/model_<N>.pt` |
| 加载参数 | `--task=x1_dh_stand --load_run=<load_run> --checkpoint=<int> [--run_name=<name>]` |
| 模型加载 | ✅ 已在示例工程验证：`Loading model from: .../model_3000.pt` |
| CSV 输出 | `{job_dir}/test/isaac_diag_{ts}.csv`（**必做**，R1-1 改 env） |
| 视频 MP4 | **不做录屏**（见 §9）；`play.py` 默认 `RENDER=False` |
| `--headless` | Agent / NTB test **固定** `--headless` + `RENDER=False` |
| `pip install -e .` | **必须**在工程根执行，否则 `LEGGED_GYM_ROOT_DIR` 指向错误 clone，找不到 `logs/` |
| gm commit SHA | **首期人工** `--commit`；后续可查 `gm task env get` / task 创建 JSON |

---

## 2. play.py CLI 参数（R1 相关）

来源：`humanoid/utils/helpers.py` → `get_args()`

| 参数 | 类型 | R1 用途 |
|:---|:---|:---|
| `--task` | str | 固定 `x1_dh_stand` |
| `--load_run` | str | 目录名，如 `2026-01-14_09-58-10test_20_video` |
| `--checkpoint` | int | 如 `3000` → `model_3000.pt` |
| `--run_name` | str | 仅影响 play 内部命名；NTB test **不依赖** |
| `--headless` | flag | Agent 固定开启 |
| `--rl_device` | str | 默认 `cuda:0` |

**模型解析链**（`task_registry.make_alg_runner`）：

```text
log_root = {LEGGED_GYM_ROOT_DIR}/logs/x1_dh_stand/exported_data
resume_path = get_load_path(log_root, load_run, checkpoint)
→ .../exported_data/<load_run>/model_<checkpoint>.pt
```

---

## 3. 输出文件路径

`play.py` 第 144 行：

```python
custom_save_path = "/personal/train-more"  # R1-1 改为读 NETTRAINBRIDGE_TEST_OUTPUT_DIR
```

| 产物 | 路径 | NTB test |
|:---|:---|:---|
| CSV 诊断 | `{custom_save_path}/isaac_diag_{ts}.csv` | **必做**（`LOG_CSV=True`） |
| 视频 MP4 | `play.py` 内 Isaac 相机录屏 | **不做**（`RENDER=False`） |

**R1-1 目标布局**（`{job_dir}/test/`）：

```text
{job_dir}/test/
├── isaac_diag_*.csv       # play 产出，用于汇总指标
├── summary.json           # test_with_metrics 写
└── test.log               # Agent 重定向
```

> **决策**：gm 训练或业务侧若已有视频，NTB sim2sim **不再录屏**。test job 以 CSV + `summary.json` 为验收产物；`test/videos/` 仅在未来「外部视频拷贝上传」时可选使用，非 R1 必做。

---

## 4. stdout / 可解析指标（R1-1 用）

`play.py` **不向 stdout 打印结构化 reward/success_rate**；主要可解析行：

| 行内容 | 用途 |
|:---|:---|
| `Loading model from: <path>` | 确认 checkpoint 加载成功 |
| `CSV logging to: <path>` | 确认 CSV 路径 |
| `CSV saved to: <path>` | 正常结束标志 |
| `feet body indices ...` | 环境初始化成功 |

episode 级 reward 在 `Logger.log_rewards(infos["episode"], ...)` 内处理，**默认不写 stdout**。  
R1-1 指标来源建议：

1. **主路径**：解析结束后读 CSV（`base_lin_vel_x`、`feet_contact` 等）汇总为 `summary.json`  
2. **备选**：改 `play.py` 在结束时 `print(json.dumps({...}))`（R1-1 可选小改）  
3. **勿依赖** Mock 式逐步 `reward=` 打印（play 无此输出）

---

## 5. 本地验证记录（2026-07-01）

**环境**：conda `F1`，Isaac Gym，`plan/diff/agibot_x1_train-main`

```bash
cd plan/diff/agibot_x1_train-main
pip install -e .
python humanoid/scripts/play.py \
  --task=x1_dh_stand \
  --load_run=2026-01-14_09-58-10test_20_video \
  --checkpoint=3000 \
  --run_name=test_20_video \
  --headless
```

**结果**：

- ✅ 模型加载：`.../model_3000.pt`
- ✅ CSV 完整写入（`RENDER=False`，约 9 分钟）
- ⏭️ 录屏：NTB test **不启用**（有 gm/业务视频时无需 play 再录）

**完整跑通命令**（R1-0 验收）：

```bash
NETTRAINBRIDGE_PLAY_RENDER=0 bash plan/r1-0-run-play.sh
# 或: bash plan/r1-0-validate.sh && ...
```

---

## 6. gm commit SHA 获取（首期）

| 方式 | 说明 |
|:---|:---|
| **人工**（首期） | `ntb test run --commit $(git rev-parse HEAD)`，与 gm 训练时 push 的 SHA 一致 |
| `gm task env get` | 后续可查任务环境是否含 git commit |
| `gm task hp get` | 辅助核对超参与任务配置 |

示例工程当前 commit：`4a27d320df1cfea38c542fed15d695897d938a6a`（见 `meta.local.json`）。

---

## 7. R1-0 验收清单

| # | 项 | 状态 |
|:---|:---|:---|
| 1 | 同窗路径：`logs/.../model_3000.pt` 存在 | ✅ |
| 2 | `play.py` 能加载该 checkpoint | ✅ |
| 3 | 记录 CSV 输出路径与命名 | ✅ |
| 4 | 记录 stdout 可解析内容 / 指标替代方案 | ✅ |
| 5 | `meta.local.json` 模板 | ✅ |
| 6 | `bash plan/r1-0-validate.sh` 路径自检 | 脚本已提供 |
| 7 | play **完整跑完**（CSV） | ✅ `NETTRAINBRIDGE_PLAY_RENDER=0` + `r1-0-run-play.sh` |

---

## 8. R1-1 待实现环境变量（R1-0 仅命名）

| 变量 | 默认 | 说明 |
|:---|:---|:---|
| `NETTRAINBRIDGE_TEST_OUTPUT_DIR` | `/personal/train-more` | 替代 `custom_save_path` → `{job_dir}/test/` |
| `NETTRAINBRIDGE_PLAY_RENDER` | `0` | **固定关**，不录屏 |
| `NETTRAINBRIDGE_PLAY_LOG_CSV` | `1` | 写 CSV |

---

## 9. 决策：不录屏

| 场景 | 做法 |
|:---|:---|
| gm 训练已有视频 / 业务已有素材 | NTB test **不**再让 `play.py` 录 MP4 |
| NTB sim2sim 验收 | **CSV** → 汇总 `summary.json`；`ntb metrics` 看解析指标 |
| `play.py` `RENDER` | R1-1 默认 `False`；仅本地人工调试可手动开 |
| Server `test/videos/` | R1 不实现上传；若日后需挂载外部视频再单独做 |
