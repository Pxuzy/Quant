# Quant Project - Coding Workflow

## ⚠️ 编码工作流（所有编码任务必须严格遵循）

接到任何写代码/改架构/做设计的任务时，**必须**按以下流程执行：

### Phase 0：侦察
- 用一句话复述需求，确认理解
- 检查相关文档（README / docs/）
- 确认验收标准

### Phase 1：读代码
- **必须**先调用 `codegraph` 了解代码结构
- **必须**先调用 `mcp_codebase_memory_*` 获取代码知识图谱
- 此阶段**禁止**修改任何文件

### Phase 2：定方案
- **必须**用 brainstorming 生成 2-3 个方案
- **必须**用 writing-plans 写执行计划
- **HARD GATE**：用户未确认方案，不得进入写代码阶段

### Phase 3：写代码
- **必须**遵循 **Ponytail 懒模式**：YAGNI → stdlib → native → 已有依赖 → one line → minimum
- **必须**先写测试（TDD）
- 输出格式：`[代码] → skipped: [X], add when [Y].`

**Ponytail 禁止事项**：
- 不写"以后可能用到"的代码
- 不写注释解释烂代码——重写代码
- 不写超过 3 层嵌套
- 不写超过 50 行的函数（除非数据转换）
- 不引入新依赖前，先确认标准库/已有依赖搞不定
- 不写 interface 只有一个实现、factory 只有一个 product、config 没人设置的抽象

**Ponytail 安全底线（绝不简化）**：
- 输入验证（trust boundary）
- 错误处理（防止数据丢失）
- 安全措施
- 无障碍基础
- 用户明确要求的功能

### Phase 4：验证
- **必须**截图发给用户确认
- 不能只靠 curl 检查，必须有视觉证据

### Phase 5：提交
- **必须**等用户明确说"提交"再执行
- 展示变更摘要（文件列表 + diff 概要）
- 不要自动 commit/push

## 工具选择
| 场景 | 用谁 |
|------|------|
| 读代码 | codegraph + rg |
| 写测试 | TDD 红绿循环 |
| 写代码 | Ponytail 懒模式 |
| 验证 | 浏览器截图 |
| 提交 | 等用户确认后 commit |

## Quant 技能入口

当任务涉及 Quant 仓库的改动、排障、重构、验证或文档更新时，优先使用 `.agents/skills/quant-workflow/SKILL.md` 里的 Quant Workflow 技能。它把这份工作流收敛成可复用的执行步骤，并要求按 gstack 的验证节奏和 ponytail 的最小实现原则推进。
