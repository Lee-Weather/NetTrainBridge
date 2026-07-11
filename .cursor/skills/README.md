# gm → ntb Skills（0.2）

本目录为 Cursor Agent Skill，可复制到**训练代码仓库**的 `.cursor/skills/`。

**CLI 说明**：[cli/README.md](../../cli/README.md)  
**验收**：[docs/acceptance.md](../../docs/acceptance.md)

## 五种模式（见 [gm-ntb-r1](gm-ntb-r1/SKILL.md)）

| 模式 | 流程 |
|:---|:---|
| **A** | gm 训练 → ntb test |
| **B** | ntb 训练 → ntb test |
| **C** | 仅 gm 训练 |
| **D** | 仅 ntb 训练 |
| **E** | 仅 ntb test（已有 checkpoint） |

## Skill 索引

| Skill | 用途 |
|:---|:---|
| [gm-ntb-r1](gm-ntb-r1/SKILL.md) | 编排 + 模式选择 |
| [gm-ntb-preflight](gm-ntb-preflight/SKILL.md) | 启动检测 + 包装脚本 |
| [gm-ntb-gm-train](gm-ntb-gm-train/SKILL.md) | gm 训练（A、C） |
| [gm-ntb-ntb-train](gm-ntb-ntb-train/SKILL.md) | ntb 训练（B、D） |
| [gm-ntb-ntb-test](gm-ntb-ntb-test/SKILL.md) | ntb test + verify（A、B、E） |
| [isaac-diag-eval](isaac-diag-eval/SKILL.md) | 分析 `isaac_diag_*.csv` |
| [lab-notebook](lab-notebook/SKILL.md) | 实验笔记 |

本地密钥 / 运行记录（**勿提交**）：

- `gm-ntb-gm-train/gm-accounts.json` ← 从 `gm-accounts.example.json` 复制
- `gm-ntb-r1/record-run.json` ← 从 `record-run.example.json` 复制

```powershell
powershell -File .cursor\skills\gm-ntb-preflight\scripts\preflight.ps1 -For ntb
powershell -File .cursor\skills\gm-ntb-ntb-test\scripts\verify-test.ps1 <test_job_id> -Source gm
```
