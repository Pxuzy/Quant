# Quant 项目文档中心

本文档中心采用“总览 -> 产品定义 -> 技术 -> 数据 -> 运行 -> 状态”的结构。首读文档先说明 Quant 要解决什么问题，再进入架构、接口和运行细节。

## 阅读路径

新成员建议按下面顺序阅读：

1. [项目总览](./overview/project-overview.md)
2. [个人股票数据管理工作台产品定义](./product/stock-workbench-product-definition.md)
3. [功能矩阵](./product/feature-catalog.md)
4. [系统架构总览](./architecture/system-overview.md)
5. [Dataset Version、Manifest 与 Snapshot 规格](./architecture/dataset-version-snapshot-design.md)
6. [股票数据全生命周期管理](./data/lifecycle.md)
7. [开发运行手册](./operations/development-runbook.md)
8. [路线图和当前状态](./status/roadmap.md)

## 文档分区

| 分区 | 用途 | 主要文档 |
| --- | --- | --- |
| `overview/` | 项目定位、目标、术语 | [项目总览](./overview/project-overview.md), [术语表](./overview/glossary.md) |
| `product/` | 产品定位、页面和功能 | [个人股票数据管理工作台产品定义](./product/stock-workbench-product-definition.md), [功能矩阵](./product/feature-catalog.md) |
| `architecture/` | 系统结构、模块边界、API、数据模型 | [系统架构总览](./architecture/system-overview.md), [API 目录](./architecture/api-catalog.md), [数据模型](./architecture/data-model.md) |
| `data/` | 数据源、同步、质量、血缘、数据集和生命周期 | [生命周期管理](./data/lifecycle.md), [数据源和同步治理](./data/data-source-and-sync-governance.md) |
| `decisions/` | 已接受架构决策及其取舍 | [ADR-001：Raw Artifact 与离线 Replay](./decisions/ADR-001-raw-artifacts-and-offline-replay.md) |
| `operations/` | 本地启动、环境变量、验证命令 | [开发运行手册](./operations/development-runbook.md) |
| `status/` | 当前进度、路线图、决策记录 | [路线图和当前状态](./status/roadmap.md) |

## 当前产品口径

Quant 是一个本地优先的个人股票研究工作台。研究台面向日常使用，数据可信后台负责 provider、同步任务、质量、批次、血缘和缺口修复。

后续新增功能应先判断属于“股票研究台”还是“数据可信后台”。不要把研究视图、同步运维和底层表结构都堆到同一个页面。

## 事实来源优先级

当前行为以代码和测试为准；当前架构与数据规范解释代码，不重新发明接口；运行手册只记录已验证可执行的命令；路线图只记录状态；历史文档只保留背景。发生冲突时按以下顺序处理：

```text
代码/测试 > 当前 data/ 与 architecture/ 规范 > operations/ runbook > roadmap > history
```

## 文档维护规则

- 产品方向变化时先更新 [个人股票数据管理工作台产品定义](./product/stock-workbench-product-definition.md)。
- 新增页面时更新 [功能矩阵](./product/feature-catalog.md) 和 [API 目录](./architecture/api-catalog.md)。
- 新增数据表、数据集或任务类型时更新 [数据模型](./architecture/data-model.md) 和 [数据源和同步治理](./data/data-source-and-sync-governance.md)。
- 完成功能或调整优先级时更新 [路线图和当前状态](./status/roadmap.md)。
