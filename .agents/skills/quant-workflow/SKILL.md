---
name: quant-workflow
description: Quant 仓库工作流技能。只要用户要修改、排障、评审、重构、规划或验证 Quant 项目，就优先使用它；尤其适用于 React 前端、FastAPI API、worker/数据管道、文档，以及需要选择 Codex 插件、MCP 工具、浏览器/桌面验证路径的任务。
---

# Quant 工作流技能

这个技能把 Quant 项目的常见工作收敛成同一条路线：先定问题，再读代码，先选最小方案，再用浏览器或日志证据收尾。它也把 Codex 的插件、MCP 和 gstack 技能放进同一个工具选择层，避免来回跳工具。

## 适用范围
- `apps/web` 前端
- `apps/api` FastAPI / service / repository
- `apps/worker` 数据同步、定时、质量控制
- `docs/` 文档、架构说明、runbook、产品说明
- Quant 相关的调试、重构、方案评审、验证、发布前检查

## 工具选择原则
1. 先选工具，再动手。
2. 能并行就并行，能复用就复用。
3. 先证据后结论。
4. 只用能解决当前问题的最小工具集。
5. 没有可用的高阶工具时，退回到 `rg`、文件读取和最小改动。

### 推荐顺序
- 代码结构 / 知识图谱：如果当前环境真的提供 `codegraph` 或 `mcp_codebase_memory_*`，先用它们；否则用 `rg` / 精准文件读取。
- 多文件独立读取：`multi_tool_use.parallel`
- 读写仓库：`functions.shell_command`
- 手工改文件：`functions.apply_patch`
- 进度管理：`functions.update_plan`
- 需要人来确认时：`functions.request_user_input`
- 截图 / 图像检查：`functions.view_image`
- JS / 浏览器自动化 / 数据探查：`mcp__node_repl.js`
- Apple 平台工作：`mcp__xcodebuildmcp`（仅在任务真的碰到 iOS/macOS/Simulator 时）
- 工具发现：`tool_search.tool_search_tool`

## Codex 插件与 MCP 生态
把工具按场景选，不要按“工具名多”来堆。

### 1. 读代码与定位
- 先 `tool_search` 看有没有更合适的工具。
- 如果有 codegraph / memory MCP，先读结构，再读目标文件。
- 没有高阶索引时，优先 `rg`、`Get-Content`、`git diff`、`git status`。
- 读多个互不依赖的文件时，用 `multi_tool_use.parallel`。

### 2. UI / 前端 / 浏览器验证
- UI 设计先找 `frontend-design`。
- 浏览器验收优先 `gstack browse` / `agent-browser`。
- 需要真实登录态时用 `setup-browser-cookies`。
- 需要有人和 AI 共享同一个浏览器会话时用 `pair-agent`。
- 需要看截图或对照布局时用 `functions.view_image`。
- 需要做 React / Next / 前端排障时，优先 `build-web-apps:frontend-testing-debugging`。
- 需要控制 Windows 桌面应用或原生弹窗时用 `computer-use:computer-use`。
- 需要控制 Chrome 本体时用 `chrome:control-chrome`。
- 需要优化 React 性能、状态和组件边界时，再看 `build-web-apps:react-best-practices`。

### 3. 调研与外部信息
- 需要查资料时用 `agent-reach`。
- 需要把外部信息落到仓库文档时，用 `document-generate` 或 `document-release`。
- 需要正式对外表达或沉淀时，用 `make-pdf` / `diagram`。

### 4. 运行时和数据探查
- 用 `mcp__node_repl.js` 做轻量脚本、数据检查、临时自动化、浏览器脚本。
- Node REPL 里能完成的事情，不要先上重依赖脚本。
- 临时 helper 尽量放在 REPL，而不是在仓库里落一堆一次性脚本。

### 5. 计划、复盘、发布
- 复杂任务先 `office-hours`、`plan-ceo-review`、`plan-eng-review`。
- UI 方案先 `plan-design-review` 或 `frontend-design`。
- 做完后用 `review`、`qa`、`benchmark`、`canary`、`document-release`、`learn` 收口。
- 需要发版时用 `ship` / `land-and-deploy`。

## Quant 的固定约束
- 前端只调用后端 API contract，不直接碰第三方 provider 或 Parquet 路径。
- 长时同步放到 `worker`。
- 数据写入遵循 `normalize -> schema_validate -> ingest_batches -> quality`。
- 第一阶段依赖尽量少。
- 产品行为、API、数据模型、runbook 改了，就同步文档。
- 不为了“看起来完整”而拆出多余抽象。
- 真有简化意图时，用简短 `ponytail:` 注释标明理由。

## 工作流

### Phase 0: 侦察
- 用一句话复述需求。
- 检查最相关的文档：`README.md`、`docs/INDEX.md`、`docs/overview/project-overview.md`、`docs/product/personal-stock-workbench.md`、`docs/product/phase-1-baseline.md`、`docs/product/feature-catalog.md`、`docs/architecture/system-overview.md`、`docs/operations/development-runbook.md`、`docs/status/roadmap.md`。
- 记录验收标准、非目标和风险。
- 看 `git status`，尊重用户已有修改。

### Phase 1: 读代码
- 先看结构，再看实现。
- 如果 codegraph / memory MCP 可用，先用它们；否则用 `rg` 和入口文件。
- 先看最接近入口的文件，再追到 service / component / route / worker / test。
- 这一阶段禁止改文件。

### Phase 2: 定方案
- 至少给出 2-3 个方案。
- 选能解决真实问题的最小方案。
- 明确影响文件、风险、验证方法和不做什么。
- 需要高风险改动时，先等用户确认。
- 方案没有确认，不进入写代码阶段。

### Phase 3: 写代码
- 按 Ponytail 懒模式推进：YAGNI -> stdlib -> native platform features -> existing dependencies -> one line -> minimum code that works。
- 先写测试，再写实现。
- 函数短、嵌套浅、抽象少。
- 不写“以后可能会用到”的代码。
- 不写单实现 interface、单产品 factory、没人配置的 config 抽象。
- 只有以下内容不许省：输入校验、错误处理、防丢数据、安全、无障碍基础、用户明确要求的功能。
- 如果有简化意图，直接实现最短可行方案，不要靠长注释解释坏代码。

### Phase 4: 验证
- 只认可见证据，不认感觉。
- UI 变更必须有截图。
- 标准顺序：打开页面 -> 看交互状态 -> 执行动作 -> 看 diff/前后变化 -> 截图 -> 查 `console` / `network` -> 必要时做 responsive 检查。
- API / worker / 数据变更要跑目标命令，看日志和返回数据。
- 如果浏览器能看见，就把可见证据给出来。
- 如果不能看见，就说明原因，不要假装完成。

### Phase 5: 交付
- 先讲改了什么，再讲怎么验的。
- 给具体文件路径。
- 说明故意没做什么，以及剩余风险。
- 没有证据就不算完成。
- 用户明确说“提交”前，不 commit / push。

## 常用 gstack 技能路由
- 问题定义不清：`/office-hours`、`/plan-ceo-review`、`/spec`
- 架构 / 数据流 / 约束：`/plan-eng-review`
- UI / 视觉 / 信息密度：`/plan-design-review`、`/design-consultation`、`/design-html`、`/design-review`
- 开发者体验：`/plan-devex-review`、`/devex-review`
- 代码质量 / 排障：`/investigate`、`/review`、`/cso`
- 浏览器验收：`/browse`、`/qa`、`/qa-only`、`/benchmark`、`/canary`
- 发布与沉淀：`/ship`、`/land-and-deploy`、`/document-release`、`/document-generate`、`/retro`、`/learn`
- 协作与产物：`/pair-agent`、`/diagram`、`/make-pdf`

## 输出风格
- 先决策，后细节。
- 说短句，给事实。
- 直接给文件路径、命令、截图位置、风险点。
- 不把“完整”当成目标，把“可验证、可维护、最小改动”当成目标。
