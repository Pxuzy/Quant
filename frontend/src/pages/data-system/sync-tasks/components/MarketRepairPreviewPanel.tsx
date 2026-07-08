/**
 * MarketRepairPreviewPanel component extracted from SyncTasksPage.
 */
import { useMemo } from 'react';
import { Alert, Descriptions, Empty, Skeleton, Space, Statistic, Table, Tag, Typography } from 'antd';
import type { DailyBarsMarketRepairPreviewResponse } from '../../../../features/market-data/types';
import { formatDate, formatNumber } from '../../../../shared/components/formatters';
import { formatMarket } from '../../../../shared/domain/labels';
import { buildMarketRepairPreviewColumns } from './columns';
import { formatMarketRepairStartPolicy, formatTaskSource } from './utils';

export function MarketRepairPreviewPanel({
  preview,
  loading,
  error,
}: {
  preview?: DailyBarsMarketRepairPreviewResponse;
  loading: boolean;
  error?: unknown;
}) {
  const sampleItems = preview?.sample_items ?? [];
  const columns = useMemo(() => buildMarketRepairPreviewColumns(), []);
  const candidateSources = preview?.candidate_sources ?? [];
  const supportedExchanges = preview?.supported_exchanges ?? [];

  if (loading) {
    return (
      <div className="market-repair-preview-panel">
        <Alert type="info" showIcon message="正在生成补齐计划预览" description="系统会检查股票池、开市日和现有日线缺口。" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="market-repair-preview-panel">
        <Alert
          type="error"
          showIcon
          message="补齐计划预览失败"
          description={error instanceof Error ? error.message : '预览接口暂不可用，请稍后重试或直接创建任务。'}
        />
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="market-repair-preview-panel market-repair-preview-empty">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未预览补齐计划" />
      </div>
    );
  }

  return (
    <div className="market-repair-preview-panel">
      <div className="market-repair-preview-heading">
        <Typography.Text strong>补齐计划预览</Typography.Text>
        <Space size={[6, 6]} wrap>
          <Tag color="blue">{formatMarket(preview.market, '全部市场')}</Tag>
          {preview.selected_source ? <Tag color="green">实际来源 {preview.selected_source}</Tag> : null}
        </Space>
      </div>
      {preview.message ? <Alert type="success" showIcon message={preview.message} /> : null}
      <div className="market-repair-preview-stats">
        <Statistic title="计划股票" value={preview.planned_symbols ?? 0} suffix="只" />
        <Statistic title="预计缺口" value={preview.planned_missing_symbol_days ?? 0} suffix="日" />
        <Statistic title="开市日" value={preview.open_dates_count ?? 0} suffix="天" />
        <Statistic title="安全上限" value={preview.max_symbols ?? 0} suffix="只" />
      </div>
      <Descriptions size="small" column={1} bordered>
        <Descriptions.Item label="日期范围">
          {formatDate(preview.start_date)} ~ {formatDate(preview.end_date)}
        </Descriptions.Item>
        <Descriptions.Item label="补齐起点">{formatMarketRepairStartPolicy(preview.start_policy)}</Descriptions.Item>
        <Descriptions.Item label="股票池">{formatNumber(preview.stock_pool_count)} 只</Descriptions.Item>
        <Descriptions.Item label="预览来源">
          请求 {formatTaskSource(preview.source)} / 实际 {formatTaskSource(preview.selected_source)}
        </Descriptions.Item>
        <Descriptions.Item label="候选来源">
          {candidateSources.length ? (
            <Space size={[6, 6]} wrap>
              {candidateSources.map((source) => (
                <Tag key={source}>{source}</Tag>
              ))}
            </Space>
          ) : (
            '-'
          )}
        </Descriptions.Item>
        <Descriptions.Item label="支持交易所">
          {supportedExchanges.length ? (
            <Space size={[6, 6]} wrap>
              {supportedExchanges.map((exchange) => (
                <Tag color="geekblue" key={exchange}>
                  {exchange}
                </Tag>
              ))}
            </Space>
          ) : (
            '-'
          )}
        </Descriptions.Item>
      </Descriptions>
      <Table
        rowKey={(record) => `${record.symbol}-${record.exchange}-${record.start_date}-${record.end_date}`}
        columns={columns}
        dataSource={sampleItems}
        pagination={false}
        size="small"
        scroll={{ x: 420 }}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无样例股票" /> }}
      />
    </div>
  );
}

