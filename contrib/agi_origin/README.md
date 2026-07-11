# agi_origin NetTrainBridge 集成文件

将以下脚本推送到 [agi_origin](https://github.com/Lee-Weather/agi_origin)（或你的训练仓库），供 Agent 训练 / 真实 sim2sim 使用：

| 脚本 | 用途 |
|:---|:---|
| `humanoid/scripts/train_with_metrics.py` | 训练指标桥接 → `metrics.jsonl` |
| `humanoid/scripts/test_with_metrics.py` | sim2sim：调 `play.py`，解析 CSV → 指标 |

另需训练仓 `play.py` 支持：

- `NETTRAINBRIDGE_PLAY_RENDER=0`（headless **不录屏**）
- `NETTRAINBRIDGE_TEST_OUTPUT_DIR`（CSV 写到 `{job}/test/`）
- `NETTRAINBRIDGE_PLAY_LOG_CSV=1`

## 部署到训练仓库

```bash
# 在训练仓库根目录
NTB=/path/to/NetTrainBridge
cp "$NTB/contrib/agi_origin/humanoid/scripts/train_with_metrics.py" humanoid/scripts/
cp "$NTB/contrib/agi_origin/humanoid/scripts/test_with_metrics.py" humanoid/scripts/

git add humanoid/scripts/train_with_metrics.py humanoid/scripts/test_with_metrics.py
git commit -m "add NetTrainBridge train/test metrics bridge"
git push
```

## Agent 配置

```bash
# ~/.nettrainbridge/config.json → agent.train_command 示例：
# python humanoid/scripts/train_with_metrics.py --task=x1_dh_stand --run_name={job_id} --headless
```

Agent 自动注入 `NETTRAINBRIDGE_METRICS_FILE` 等。test 成功后上传最新 `isaac_diag_*.csv` 到 Server；流式指标仍走 `ntb metrics`。

## 本地自检

```bash
cd <训练仓库>
python humanoid/scripts/train_with_metrics.py --self-test
python humanoid/scripts/test_with_metrics.py --self-test

# Mock（不跑 Isaac，仅打通链路）
export NETTRAINBRIDGE_METRICS_FILE=/tmp/test_metrics.jsonl
touch /tmp/model.pt
python humanoid/scripts/test_with_metrics.py --mock --checkpoint /tmp/model.pt
```

真实 sim2sim（需 F1 + Isaac + 模型）：

```bash
export NETTRAINBRIDGE_PLAY_RENDER=0
export NETTRAINBRIDGE_PLAY_LOG_CSV=1
python humanoid/scripts/test_with_metrics.py \
  --task=x1_dh_stand --load-run=<load_run> --checkpoint=50 --headless
```

详见 [docs/acceptance.md](../../docs/acceptance.md)、[docs/checkpoint-hub.md](../../docs/checkpoint-hub.md)、[agent/README.md](../../agent/README.md)。
