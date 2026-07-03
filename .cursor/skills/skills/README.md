# gm → ntb R1-3 Skills

**ntb / gm CLI 完整命令参考**：[czy/skills/cli-readme.md](../../czy/skills/cli-readme.md)

## 五种模式（见 [gm-ntb-r1](gm-ntb-r1/SKILL.md)）

| 模式 | 流程 |
|:---|:---|
| **A** | gm 训练 → ntb test |
| **B** | ntb 训练 → ntb test |
| **C** | 仅 gm 训练 |
| **D** | 仅 ntb 训练 |
| **E** | **仅 ntb test**（已有 checkpoint） |

## Skill 索引

| Skill | 用途 |
|:---|:---|
| [gm-ntb-r1](gm-ntb-r1/SKILL.md) | 编排 + 模式选择 |
| [gm-ntb-preflight](gm-ntb-preflight/SKILL.md) | 启动检测 + 包装脚本 |
| [gm-ntb-gm-train](gm-ntb-gm-train/SKILL.md) | gm 训练（A、C） |
| [gm-ntb-ntb-train](gm-ntb-ntb-train/SKILL.md) | ntb 训练（B、D） |
| [gm-ntb-ntb-test](gm-ntb-ntb-test/SKILL.md) | ntb test（A、B、**E**） |
| [gm-ntb-r1-e2e](gm-ntb-r1-e2e/SKILL.md) | 已废弃 |

状态文件：[`gm-ntb-r1/record-run.json`](gm-ntb-r1/record-run.example.json)（本地，gitignore）

```powershell
# 仅 test（模式 E）
powershell -File .cursor\skills\gm-ntb-r1\scripts\read-record-run.ps1
powershell -File .cursor\skills\gm-ntb-preflight\scripts\preflight.ps1 -For ntb
# 然后 gm-ntb-ntb-test
```
