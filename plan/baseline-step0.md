# 步骤 0 基线记录（v0.1）

> **状态**：✅ 已通过（人工验收，2026-06-30）  
> **版本**：`nettrainbridge` **0.1.0**（`pyproject.toml`）  
> **下一 step**：[plan02-implementation.md §步骤 1](plan02-implementation.md#步骤-1cli-6a-入口不动-server-行为)

---

## 验收结论

| 项 | 结果 |
|:---|:---|
| `test_e2e.sh` | ✅ 通过（**§15 Webhook 除外**，见下） |
| `test_phase3.sh` | ✅ 通过（**§2 Webhook 除外**，见下） |
| `test_cli.sh` | ✅ 通过 |
| `ntb trigger` 创建任务 | ✅ 正常 |
| Agent 训练链路 | ✅ 人工确认可用 |
| GitHub Webhook | ⏸ **已关闭**（手动 `ntb trigger` 模式，符合 README） |

---

## 已知例外：Webhook 相关用例

当前产品策略（见 [README.md](../README.md)）：

- 日常用 **`git push` 同步代码 + `ntb trigger` 手动触发**
- GitHub Webhook **已 Disable**，避免 push 自动建任务

因此以下脚本中的 **Webhook 段在基线回归中视为「预期跳过/可失败」**，不计入 step 0 失败：

| 脚本 | 段落 | 原因 |
|:---|:---|:---|
| `server/test_e2e.sh` | §15、§15b | `POST /webhook/github` 与现网策略不一致 |
| `server/test_phase3.sh` | §2 及依赖 webhook 创建的 `JOB_ID` 后续步骤 | 同上 |

**v0.2 回归建议**：

- 跑全量脚本时加环境变量跳过 webhook，或拆 `test_v02_regression.sh` 只跑 job/metrics/logs/checkpoint/CLI 段。
- Webhook 能力保留在 Server 代码中，**不在 v0.2 主路径验收范围**。

---

## 锁定回归命令

```bash
# 云服务器目录，需先 python main.py
cd server
bash test_e2e.sh http://localhost:8000      # Webhook 段已知例外
bash test_phase3.sh http://localhost:8000   # Webhook 段已知例外
bash test_cli.sh http://localhost:8000

# 家里 CLI
pip install -e ".[dev]"
ntb health
ntb trigger --repo <url> --commit <sha>
```

---

## v0.2 开发约束（自 step 1 起）

1. 每步合并前重跑上表脚本（Webhook 段按例外处理）。
2. **`ntb trigger` 在 step 1 之前为基线行为**；step 1 起改为 `ntb train run` + deprecated `trigger`。
3. gm 主路径不依赖 NTB 代码变更。
