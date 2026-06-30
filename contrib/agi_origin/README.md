# agi_origin NetTrainBridge 集成文件

将 `humanoid/scripts/train_with_metrics.py` 推送到 [agi_origin](https://github.com/Lee-Weather/agi_origin) 仓库，使训练日志自动写入 `metrics.jsonl`，供 Agent 上报。

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
