# agi_origin GradMotion 集成文件

将本目录内容复制到 [Lee-Weather/agi_origin](https://github.com/Lee-Weather/agi_origin) 仓库对应路径后 push。

## 文件

| 文件 | 目标路径 |
|:---|:---|
| `humanoid/scripts/train_with_metrics.py` | `agi_origin/humanoid/scripts/train_with_metrics.py` |

## 部署

```bash
git clone https://github.com/Lee-Weather/agi_origin.git
cd agi_origin

# 从 NetTrainBridge 复制
cp /path/to/NetTrainBridge/contrib/agi_origin/humanoid/scripts/train_with_metrics.py \
   humanoid/scripts/train_with_metrics.py

git add humanoid/scripts/train_with_metrics.py
git commit -m "add train_with_metrics for GradMotion"
git push
```

## 训练机 Agent 配置

```bash
export GRADMOTION_SERVER_URL=http://<云服务器IP>:8000
export GRADMOTION_TRAIN_COMMAND="python humanoid/scripts/train_with_metrics.py --task=x1_dh_stand --run_name={job_id} --headless"
```

Agent 会自动注入 `GRADMOTION_METRICS_FILE={job_dir}/metrics.jsonl`。

## 本地验证

```bash
# 1. 解析器自测（无需 Isaac Gym）
python humanoid/scripts/train_with_metrics.py --self-test

# 2. 真实训练（需 F1 + Isaac Gym）
conda activate F1
pip install -e .
export GRADMOTION_METRICS_FILE=/tmp/metrics.jsonl
export GRADMOTION_JOB_ID=local-test

python humanoid/scripts/train_with_metrics.py \
  --task=x1_dh_stand --run_name=local-test --headless --max_iterations=10

cat /tmp/metrics.jsonl
```

## 指标格式

从 `dh_on_policy_runner.py` 日志解析：

- `step` ← `Learning iteration N/...`
- `reward` ← `Mean reward:`
- `loss` ← `Value function loss` 与 `Surrogate loss` 的均值

写入 `metrics.jsonl` 示例：

```json
{"step": 3, "loss": 0.3456, "reward": 2.5}
```
