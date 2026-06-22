# Quant 优化计划 2026-06-21

## P0: 数据可信闭环稳定性

### P0-1: coverage_summary 查询优化
**问题**: `_coverage_summary` 每次查全量 stock_symbols + open_dates + Parquet，性能差
**方案**: 
- 添加内存缓存（TTL 5分钟），key 为 market
- 增量更新：只在数据变更时刷新缓存
- 超时保护：DuckDB 查询加 30s 超时
**文件**: `apps/api/services/database_integration_service.py`
**验收**: 第二次调用 overview API 时，coverage_summary 应从缓存返回

### P0-2: DuckDB 查询超时保护
**问题**: `DailyBarRepository` 的 DuckDB 查询可能很慢，无超时保护
**方案**: 
- 为所有 DuckDB 查询添加 `statement_timeout` 参数
- 超时后降级到 PyArrow fallback
**文件**: `apps/api/repositories/daily_bars.py`
**验收**: 大查询超时时自动降级，不报错

### P0-3: sync_stocks worker 幂等保护
**问题**: 重复触发同步可能产生重复数据
**方案**: 
- 检查最近 5 分钟内是否有相同类型的 running 任务
- 有则跳过创建，返回已有任务 ID
**文件**: `apps/worker/sync_stocks.py`, `apps/api/services/stock_sync_service.py`
**验收**: 快速连续触发两次同步，只创建一个任务

### P0-4: SQLite 并发写入保护
**问题**: worker + API 同时写可能冲突
**方案**: 
- 添加 `busy_timeout` 配置
- 写操作加 retry 逻辑（最多 3 次，指数退避）
**文件**: `apps/api/db/session.py`
**验收**: 并发写入不报错

## P1: 研究台体验重塑

### P1-1: 总控台改研究首页
**问题**: 当前是后台入口集合，不是研究首页
**方案**:
- 顶部：关注股票池（最近查看/自选股）
- 中部：行情摘要（大盘指数、涨跌分布）
- 底部：最近新闻 + 数据新鲜度
**文件**: `apps/web/src/pages/data-system/overview/DataSystemOverviewPage.tsx`
**验收**: 打开总控台看到研究入口，不是后台管理

### P1-2: 股票详情页聚合
**问题**: 当前只有基础信息 + 日线，太简单
**方案**:
- 添加日线图表（用 lightweight-charts 或 recharts）
- 显示成交量柱状图
- 显示数据覆盖状态、质量报告、最近批次
**文件**: `apps/web/src/pages/data-system/stocks/StockDetailPage.tsx`
**验收**: 股票详情页有图表 + 质量信息

### P1-3: 新闻最小闭环
**问题**: 新闻页是占位页
**方案**:
- 创建 news 领域模块（adapter + repository + service + router + schema）
- 接入一个新闻源（如东方财富新闻）
- 新闻汇总页显示新闻列表 + 股票关联
**文件**: `apps/api/adapters/news_adapter.py` (新增), `apps/api/repositories/news.py` (新增), `apps/api/services/news_service.py` (新增), `apps/api/routers/news.py` (新增)
**验收**: 新闻汇总页显示真实新闻数据

### P1-4: 自选股功能
**问题**: 无自选股，每次都要搜索
**方案**:
- 添加 watchlist 表（user_id, symbol, created_at）
- 添加 API：POST/DELETE /api/watchlist, GET /api/watchlist
- 总控台显示自选股列表
**文件**: `apps/api/models/entities.py`, `apps/api/repositories/watchlist.py` (新增), `apps/api/routers/watchlist.py` (新增)
**验收**: 可以添加/删除自选股，总控台显示自选股

## P2: 代码质量

### P2-1: DataSystemOverviewPage 拆分
**问题**: 1378行，一个页面做了太多事
**方案**:
- 拆分为：SourceHealthPanel, DatasetCoveragePanel, RecentTaskPanel, AlertsPanel
- 每个面板独立文件
**文件**: `apps/web/src/pages/data-system/overview/` (拆分)
**验收**: 每个文件 < 300 行

### P2-2: 补充 database_status_service 测试
**问题**: 无对应测试文件
**方案**: 创建 `tests/api/test_database_status_service.py`
**验收**: 测试覆盖核心逻辑

### P2-3: 补充 dataset_service 测试
**问题**: 无对应测试文件
**方案**: 创建 `tests/api/test_dataset_service.py`
**验收**: 测试覆盖核心逻辑

### P2-4: 补充 normalized_data_validation 测试
**问题**: 核心验证逻辑无测试
**方案**: 创建 `tests/api/test_normalized_data_validation.py`
**验收**: 测试覆盖 validate_stock_records, validate_daily_bar_records, validate_calendar_records

## P3: 性能优化

### P3-1: codegraph 重建索引
**问题**: 旧版本索引，import/call 关系不完整
**方案**: `codegraph index -f .`
**验收**: codegraph status 显示最新版本

### P3-2: 前端重复请求优化
**问题**: 多个页面组件各自请求相同数据
**方案**: 使用 TanStack Query 的 shared cache，避免重复请求
**验收**: 网络面板不显示重复请求

### P3-3: Parquet 分区策略优化
**问题**: 当前按 symbol 分区，范围查询慢
**方案**: 改为按 (market, trade_date) 分区
**验收**: 日期范围查询性能提升
