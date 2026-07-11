# NetTrainBridge 文档（0.2）

现行文档。历史 `plan/` 设计稿已移出主交付。

## 设计与验收

| 文档 | 内容 |
|:---|:---|
| [checkpoint-hub.md](checkpoint-hub.md) | gm test：家里 stage → Server → Agent pull |
| [acceptance.md](acceptance.md) | sim2sim 验收清单与常用命令 |

## 分端说明

| 文档 | 内容 |
|:---|:---|
| [../README.md](../README.md) | 项目总览、架构、三端启动 |
| [../cli/README.md](../cli/README.md) | 家里 `ntb` CLI |
| [../server/README.md](../server/README.md) | 云 Server API |
| [../agent/README.md](../agent/README.md) | 训练机 Agent |
| [../contrib/agi_origin/README.md](../contrib/agi_origin/README.md) | 训练仓桥接脚本 |
| [../.cursor/skills/README.md](../.cursor/skills/README.md) | Cursor Skill 索引 |

配置模板唯一路径：`nettrainbridge_common/config.example.json`（`ntb config init` 或手动 `cp`）。
