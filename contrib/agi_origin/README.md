# agi_origin NetTrainBridge 集成文件

将以下脚本推送到 [agi_origin](https://github.com/Lee-Weather/agi_origin) 仓库，供 Agent 训练 / 测试时上报 `metrics.jsonl`：

| 脚本 | 用途 | 阶段 |
|:---|:---|:---|
| `humanoid/scripts/train_with_metrics.py` | 训练指标桥接 | 已用 |
| `humanoid/scripts/test_with_metrics.py` | sim2sim 测试桥接（**框架 + Mock**） | v0.2 步骤 7～8 |

## 部署到 agi_origin

```bash
# 在 agi_origin 仓库根目录
cp /path/to/NetTrainBridge/contrib/agi_origin/humanoid/scripts/train_with_metrics.py \
   humanoid/scripts/train_with_metrics.py

git add humanoid/scripts/train_with_metrics.py
git commit -m "add train_with_metrics for NetTrainBridge"
git push
```

## Agent 配置

```bash
export NETTRAINBRIDGE_SERVER_URL=http://<云服务器IP>:8000
export NETTRAINBRIDGE_TRAIN_COMMAND="python humanoid/scripts/train_with_metrics.py --task=x1_dh_stand --run_name={job_id} --headless"
```

Agent 会自动注入 `NETTRAINBRIDGE_METRICS_FILE={job_dir}/metrics.jsonl`。

> 仍支持已弃用的 `GRADMOTION_*` 环境变量（一个版本后移除）。

## 本地测试

```bash
cd agi_origin
export NETTRAINBRIDGE_METRICS_FILE=/tmp/metrics.jsonl
export NETTRAINBRIDGE_JOB_ID=local-test
python humanoid/scripts/train_with_metrics.py --self-test
```

## test_with_metrics（Mock 框架，步骤 7）

真实 sim2sim（`play.py`）**尚未实现**；当前仅 `--mock` 写占位指标，用于打通 `ntb test run` 链路。

```bash
python humanoid/scripts/test_with_metrics.py --self-test

export NETTRAINBRIDGE_METRICS_FILE=/tmp/test_metrics.jsonl
export NETTRAINBRIDGE_JOB_ID=local-test
touch /tmp/model.pt
python humanoid/scripts/test_with_metrics.py --mock --checkpoint /tmp/model.pt
```

Agent `test_command`（步骤 8 暂定）：

```bash
export NETTRAINBRIDGE_TEST_COMMAND="python humanoid/scripts/test_with_metrics.py --mock --checkpoint={checkpoint_path} --headless"
```

详见 `plan/sim2sim-framework.md`。
