# Quant 项目文档中心

本文档中心采用“总览 -> 产品方向 -> 产品基线 -> 技术 -> 数据 -> 运行 -> 状态”的结构。首读文档先说明 Quant 要解决什么问题，再进入架构、接口和运行细节。

## 阅读路径

新成员建议按下面顺序阅读：

1. [项目总览](./overview/project-overview.md)
2. [个人股票研究工作台产品方向](./product/personal-stock-workbench.md)
3. [阶段一产品基线](./product/phase-1-baseline.md)
4. [功能矩阵](./product/feature-catalog.md)
5. [系统架构总览](./architecture/system-overview.md)
6. [开发运行手册](./operations/development-runbook.md)
7. [路线图和当前状态](./status/roadmap.md)

## 文档分区

| 分区 | 用途 | 主要文档 |
| --- | --- | --- |
| `overview/` | 项目定位、目标、术语 | [项目总览](./overview/project-overview.md), [术语表](./overview/glossary.md) |
| `product/` | 产品方向、阶段范围、页面和功能 | [个人股票研究工作台产品方向](./product/personal-stock-workbench.md), [阶段一产品基线](./product/phase-1-baseline.md), [功能矩阵](./product/feature-catalog.md) |
| `architecture/` | 系统结构、模块边界、API、数据模型 | [系统架构总览](./architecture/system-overview.md), [API 目录](./architecture/api-catalog.md), [数据模型](./architecture/data-model.md) |
| `data/` | 数据源、同步、质量、血缘、数据集 | [数据源和同步治理](./data/data-source-and-sync-governance.md) |
| `operations/` | 本地启动、环境变量、验证命令 | [开发运行手册](./operations/development-runbook.md) |
| `status/` | 当前进度、路线图、决策记录 | [路线图和当前状态](./status/roadmap.md) |

## 当前产品口径

Quant 是一个本地优先的个人股票研究工作台。研究台面向日常使用，数据可信后台负责 provider、同步任务、质量、批次、血缘和缺口修复。

后续新增功能应先判断属于“股票研究台”还是“数据可信后台”。不要把研究视图、同步运维和底层表结构都堆到同一个页面。

## 现有详细参考

以下文档保留为历史设计和详细说明，不作为新人首读入口：

- [股票数据库工作台项目文档](./architecture/stock-database-workbench.md)
- [股票数据系统架构设计](./architecture/stock-data-system-design.md)
- [轻量后台收敛实施计划](./superpowers/plans/2026-06-17-data-system-lightweight-backoffice-convergence.md)

## 文档维护规则

- 产品方向变化时先更新 [个人股票研究工作台产品方向](./product/personal-stock-workbench.md)。
- 新增页面时更新 [功能矩阵](./product/feature-catalog.md) 和 [API 目录](./architecture/api-catalog.md)。
- 新增数据表、数据集或任务类型时更新 [数据模型](./architecture/data-model.md) 和 [数据源和同步治理](./data/data-source-and-sync-governance.md)。
- 完成功能或调整优先级时更新 [路线图和当前状态](./status/roadmap.md)。
