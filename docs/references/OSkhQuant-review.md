# KHQuant（OSkhQuant）参考评估

> 用途：作为本项目后续研究/回测消费层的参考案例，不作为当前数据治理实现的代码来源或架构模板。本文件区分已验证的仓库事实和可采纳的设计结论。

## 来源与固定版本

- 项目：[`khscience/OSkhQuant`](https://github.com/khscience/OSkhQuant)
- 检查时间：2026-07-18
- 本地只读审查提交：[`7228f55741b445cb25116683e5753f82a5422825`](https://github.com/khscience/OSkhQuant/tree/7228f55741b445cb25116683e5753f82a5422825)
- GitHub 元数据：仓库描述为 A 股可视化回测系统；检查时约 1.4k Stars；GitHub license 字段为 `Other`。

## 已验证的实现事实

| 观察 | 证据 | 对 Quant 的含义 |
| --- | --- | --- |
| 本地桌面 GUI 为主，源文件集中于 PyQt 窗口与框架脚本 | `GUIkhQuant.py`、`GUI.py`、`khFrame.py` | 不适合作为当前 FastAPI + React 架构的 UI 模板。 |
| 行情读取、下载与交易接口直接耦合 MiniQMT/`xtquant` | `khFrame.py` 直接导入 `xtdata`/`XtQuantTrader`；`khQTTools.py` 调用 `download_history_data` | 本项目不能让研究、回测或策略层直接依赖 provider/broker SDK；必须继续经 governed `BarReader`/数据集契约读取。 |
| 回测交易成本以独立组件表达 | `khTrade.py` 定义佣金、印花税、过户费、流量费、tick/比例滑点和 T+0/T+1 规则 | 值得在未来的回测消费层借鉴：交易成本、成交规则与数据读写分离，而不是混进数据同步服务。 |
| 对 A 股交易规则有显式处理 | `khTrade.py` 的 T+1/T+0 可用数量逻辑；README 说明涨跌停、T+1 等本土规则 | 未来回测应以交易日历、市场规则和 dataset snapshot 为输入；不要在 provider adapter 中埋业务交易规则。 |
| README 声明核心用途是研究/回测，官方版本不直接执行实盘交易 | README 与 GUI 免责声明均明确写出这一边界 | 当前项目也应保持：先稳定数据读取、版本、质量与回测输入，再讨论交易执行。 |
| README 说明数据/交易依赖用户本地 MiniQMT，上游数据准确性不由系统担保 | README 相关免责声明 | 支持本项目已有方向：provider 原始输入、source、batch、质量状态和 lineage 必须可追溯。 |

## 可采纳的设计原则

### 1. 独立交易执行模拟层

未来可在 `backtest` 领域新增独立、纯本地的成交模拟服务，输入为：

```text
strategy signals
+ governed BarReader / snapshot
+ trading calendar
+ market-rule profile
+ declared fee/slippage profile
```

输出为订单、成交、费用、持仓、净值和风险指标。该层不能直接读取 provider，也不能调用原始 Parquet 路径。

### 2. 将 A 股规则配置化

可借鉴其把成本、滑点、T+1 作为明确配置的做法，但在 Quant 中应让规则具有：

- 版本号；
- 生效市场与时间范围；
- 回测运行记录关联；
- 可复现的 snapshot / dataset version 引用；
- 明确的默认值与覆盖来源。

### 3. 研究、回测、执行三层分离

KHQuant 将研究、回测和 MiniQMT 集成做成一个本地工具。Quant 应保留相同的用户价值，但采用更严格边界：

```text
provider ingest -> governed datasets -> research API -> offline backtest -> future broker adapter
```

当前不引入 broker execution，也不允许回测模块回写 canonical 行情。

## 不直接采用的部分

| 不采用项 | 原因 |
| --- | --- |
| 在框架/策略代码直接导入 `xtquant` 或调用 `download_history_data` | 会绕过 raw artifact、质量、版本和 provenance。 |
| 用单一 GUI/框架文件同时承担数据下载、策略运行、交易和界面编排 | 可读性、测试隔离和可审计性不足；当前模块化单体边界更合适。 |
| 将 raw provider 数据直接等同为可回测输入 | 本项目需要先通过标准化、质量、dataset version 和 snapshot。 |
| 直接复制仓库代码 | GitHub 元数据为 `Other`，README 还声明 CC BY-NC 4.0；在未单独核实每个文件授权前只借鉴架构思想和公开行为，不复制实现。 |

## 对当前路线图的具体补充

在 `dataset version / manifest / snapshot` 稳定后，按以下顺序推进：

1. 固化 `BarReader` 的多股票、列投影和 snapshot 读取契约；
2. 新建日线离线回测的 `BacktestRun`、`ExecutionPolicy`、`FeeProfile`、`MarketRuleProfile` 元数据；
3. 实现无 broker 依赖的成交模拟与结果审计；
4. 以相同 snapshot 重跑，验证净值/成交结果可复现；
5. 仅在人工明确授权后，设计独立 broker adapter 和模拟/实盘隔离边界。

## 结论

KHQuant 最有价值的参考是：**面向 A 股个人用户的本地化研究体验、交易成本建模、T+1/T+0 规则显式化、研究与回测的工作流**。

Quant 当前更应坚持自己的优势：**provider 原始证据、质量门禁、批次血缘、离线 replay、数据版本与受控读取**。在这些基础完成前，不将 MiniQMT 或实盘接口引入当前数据生命周期主链路。