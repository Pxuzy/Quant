/**
 * Column builder functions extracted from DatabaseManagementPage.
 */
import { Link } from '@tanstack/react-router';
import { CloudSyncOutlined, FileSearchOutlined, ProfileOutlined, StockOutlined } from '@ant-design/icons';
import { Button, Space, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { Dataset } from '../../../../features/datasets/types';
import type { DataQualityReport } from '../../../../features/data-quality/types';
import type { DataSource } from '../../../../features/data-sources/types';
import type {
  DatabaseCoverageSummary,
  DatabaseLineageItem,
  DatasetSnapshot,
  ProviderIntegration,
  RecentIngestBatch,
  SyncWatermark,
} from '../../../../features/database/types';
import { StatusTag } from '../../../../shared/components/StatusTag';
import { formatDate, formatDateTime, formatNumber } from '../../../../shared/components/formatters';
import {
  formatCapability,
  formatExchange,
  formatLayer,
  formatMarket,
  formatProviderType,
  formatStability,
  formatStorageType,
  formatTaskType,
  formatQualityCheckType,
  formatAuthMode,
} from '../../../../shared/domain/labels';
import type { TraceQualityReportBatch } from './utils';
import {
  formatWatermarkScope,
  formatRepairRange,
  getRepairFocus,
  getRepairSearch,
  getSourceMetadata,
  getSourceCapabilities,
  formatCapabilitySummary,
  formatDailyBarExchanges,
  getSourceLastSmoke,
  formatSourceHealthMessage,
  formatSmokeSample,
  formatRange,
  getQualityReportAction,
  getNumericTaskId,
  getNumericRecordId,
} from './utils';

export function buildDatasetColumns(): ColumnsType<Dataset> {
  return [
    {
      title: '数据内容',
      dataIndex: 'name',
      width: 180,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{formatCapability(record.name)}</Typography.Text>
          <Typography.Text type="secondary">{record.name}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '数据层级',
      dataIndex: 'layer',
      width: 120,
      render: (value) => <Tag>{formatLayer(value)}</Tag>,
    },
    {
      title: '主存储介质',
      dataIndex: 'storage_type',
      width: 130,
      render: (value) => <Tag color="blue">{formatStorageType(value)}</Tag>,
    },
    {
      title: '记录数',
      dataIndex: 'row_count',
      width: 130,
      render: (value) => formatNumber(value),
    },
    {
      title: '最新日期',
      dataIndex: 'latest_data_date',
      width: 140,
      render: (value) => formatDate(value),
    },
    {
      title: '质量',
      dataIndex: 'quality_status',
      width: 110,
      render: (value) => <StatusTag value={value} />,
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 180,
      render: (value) => formatDateTime(value),
    },
  ];
}

export function buildSnapshotColumns(): ColumnsType<DatasetSnapshot> {
  return [
    {
      title: '数据集快照',
      dataIndex: 'dataset_name',
      width: 190,
      render: (_, snapshot) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{formatCapability(snapshot.dataset_name)}</Typography.Text>
          <Typography.Text type="secondary">{snapshot.dataset_version}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '来源/层级',
      dataIndex: 'source',
      width: 160,
      render: (_, snapshot) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{snapshot.source}</Typography.Text>
          <Typography.Text type="secondary">
            {formatLayer(snapshot.layer)} / {formatStorageType(snapshot.storage_type)}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '记录数',
      dataIndex: 'row_count',
      width: 110,
      render: (value) => formatNumber(value),
    },
    {
      title: '最新日期',
      dataIndex: 'latest_data_date',
      width: 130,
      render: (value) => formatDate(value),
    },
    {
      title: '契约',
      dataIndex: 'schema_fields_count',
      width: 180,
      render: (_, snapshot) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{formatNumber(snapshot.schema_fields_count)} 个字段</Typography.Text>
          <Typography.Text type="secondary">主键 {snapshot.primary_keys_json.join(', ') || '-'}</Typography.Text>
          <Typography.Text type="secondary">分区 {snapshot.partition_keys_json.join(', ') || '-'}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '质量',
      dataIndex: 'quality_status',
      width: 100,
      render: (value) => <StatusTag value={value} />,
    },
  ];
}

export function buildWatermarkColumns(coverage?: DatabaseCoverageSummary): ColumnsType<SyncWatermark> {
  return [
    {
      title: '数据类型',
      dataIndex: 'dataset_name',
      width: 130,
      render: (value) => <Typography.Text strong>{formatCapability(value)}</Typography.Text>,
    },
    {
      title: '范围',
      width: 150,
      render: (_, watermark) => formatWatermarkScope(watermark),
    },
    {
      title: '实际来源',
      dataIndex: 'source',
      width: 150,
      render: (_, watermark) => (
        <Space direction="vertical" size={0}>
          <Tag color="blue">{watermark.source}</Tag>
          <Typography.Text type="secondary">请求 {watermark.requested_source || '-'}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '最新成功日期',
      dataIndex: 'latest_success_date',
      width: 130,
      render: (value) => formatDate(value),
    },
    {
      title: '待补范围',
      width: 190,
      render: (_, watermark) =>
        watermark.repair_start_date || watermark.repair_end_date ? (
          <Space direction="vertical" size={0}>
            <Typography.Text>{formatRepairRange(watermark)}</Typography.Text>
            <Typography.Text type="secondary" ellipsis title={watermark.repair_reason ?? undefined}>
              {watermark.repair_reason ?? '建议补齐缺口'}
            </Typography.Text>
          </Space>
        ) : (
          <Typography.Text type="secondary">{watermark.repair_reason ?? '暂无建议'}</Typography.Text>
        ),
    },
    {
      title: '最近失败',
      width: 190,
      render: (_, watermark) =>
        watermark.last_failed_at || watermark.last_failure_reason ? (
          <Space direction="vertical" size={0}>
            <Typography.Text type="danger">{formatDateTime(watermark.last_failed_at)}</Typography.Text>
            {watermark.last_failure_batch_id ? (
              <Typography.Text type="secondary">失败批次 #{watermark.last_failure_batch_id}</Typography.Text>
            ) : null}
            <Typography.Text type="secondary" ellipsis title={watermark.last_failure_reason ?? undefined}>
              {watermark.last_failure_reason ?? '未记录原因'}
            </Typography.Text>
          </Space>
        ) : (
          <Typography.Text type="secondary">无</Typography.Text>
        ),
    },
    {
      title: '写入',
      dataIndex: 'records_written',
      width: 100,
      render: (value) => formatNumber(value),
    },
    {
      title: '质量',
      dataIndex: 'quality_status',
      width: 100,
      render: (value) => <StatusTag value={value} />,
    },
    {
      title: '最近成功',
      dataIndex: 'last_success_at',
      width: 170,
      render: (_, watermark) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{formatDateTime(watermark.last_success_at)}</Typography.Text>
          <Typography.Text type="secondary">成功批次 #{watermark.batch_id}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '追溯',
      key: 'trace',
      fixed: 'right',
      width: 150,
      render: (_, watermark) => {
        const taskId = getNumericTaskId(watermark.task_id);
        const failureTaskId = getNumericTaskId(watermark.last_failure_task_id);
        const focus = getRepairFocus(watermark, coverage);
        return (
          <Space size={2}>
            {taskId ? (
              <Link to="/sync-tasks" search={{ taskId, page: 1, pageSize: 10 }}>
                <Button type="link" size="small" icon={<ProfileOutlined />}>
                  任务
                </Button>
              </Link>
            ) : null}
            {failureTaskId ? (
              <Link to="/sync-tasks" search={{ taskId: failureTaskId, page: 1, pageSize: 10 }}>
                <Button type="link" size="small">
                  失败
                </Button>
              </Link>
            ) : null}
            {focus ? (
              <Link to="/sync-tasks" search={getRepairSearch(watermark, coverage)}>
                <Button type="link" size="small" icon={<CloudSyncOutlined />}>
                  补数
                </Button>
              </Link>
            ) : null}
          </Space>
        );
      },
    },
  ];
}

export function buildProviderColumns(): ColumnsType<ProviderIntegration> {
  return [
    {
      title: '数据源',
      dataIndex: 'source',
      width: 120,
      render: (value) => <Typography.Text strong>{value}</Typography.Text>,
    },
    {
      title: '尝试/成功/失败',
      width: 150,
      render: (_, provider) => `${formatNumber(provider.attempts)} / ${formatNumber(provider.successes)} / ${formatNumber(provider.failures)}`,
    },
    {
      title: '自动降级写入',
      dataIndex: 'fallback_successes',
      width: 130,
      render: (value) => <Tag color={value > 0 ? 'green' : 'default'}>{formatNumber(value)}</Tag>,
    },
    {
      title: '写入行数',
      dataIndex: 'records_written',
      width: 120,
      render: (value) => formatNumber(value),
    },
    {
      title: '最近成功',
      dataIndex: 'last_success_at',
      width: 170,
      render: (value) => formatDateTime(value),
    },
    {
      title: '最近失败',
      dataIndex: 'last_failure_at',
      width: 170,
      render: (value) => formatDateTime(value),
    },
  ];
}

export function buildProviderStatusColumns(): ColumnsType<DataSource> {
  return [
    {
      title: 'Provider',
      dataIndex: 'code',
      width: 150,
      render: (_, source) => {
        const metadata = getSourceMetadata(source);
        return (
          <Space direction="vertical" size={2}>
            <Space wrap size={[6, 4]}>
              <Typography.Text strong>{source.name}</Typography.Text>
              <Typography.Text type="secondary">{source.code}</Typography.Text>
            </Space>
            <Space wrap size={[4, 4]}>
              <Tag color="geekblue">{formatProviderType(metadata.provider_type ?? 'external_api')}</Tag>
              <Tag>{formatStability(metadata.stability ?? 'community')}</Tag>
            </Space>
          </Space>
        );
      },
    },
    {
      title: '健康/启用',
      width: 150,
      render: (_, source) => (
        <Space direction="vertical" size={2}>
          <Space wrap size={[4, 4]}>
            <StatusTag value={source.health_status} />
            <Tag color={source.enabled ? 'green' : 'default'}>{source.enabled ? '已启用' : '已禁用'}</Tag>
          </Space>
          <Typography.Text type="secondary">最近检查 {formatDateTime(source.last_checked_at)}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '能力声明',
      width: 210,
      render: (_, source) => {
        const capabilities = getSourceCapabilities(source);
        return (
          <Space direction="vertical" size={2}>
            <Typography.Text>{formatCapabilitySummary(capabilities)}</Typography.Text>
            <Typography.Text type="secondary">日线覆盖 {formatDailyBarExchanges(capabilities)}</Typography.Text>
          </Space>
        );
      },
    },
    {
      title: '接入信息',
      width: 220,
      render: (_, source) => {
        const metadata = getSourceMetadata(source);
        return (
          <Space direction="vertical" size={2}>
            <Space wrap size={[4, 4]}>
              <Tag color={source.requires_token ? 'warning' : 'blue'}>
                {formatAuthMode(metadata.auth_mode ?? (source.requires_token ? 'token' : 'none'))}
              </Tag>
              <Tag>优先级 {formatNumber(source.priority)}</Tag>
            </Space>
            <Typography.Text type="secondary" ellipsis title={metadata.install_note ?? undefined}>
              {metadata.install_note || '无额外安装说明'}
            </Typography.Text>
          </Space>
        );
      },
    },
    {
      title: '最近真实取样',
      width: 260,
      render: (_, source) => {
        const lastSmoke = getSourceLastSmoke(source);
        if (!lastSmoke) {
          return (
            <Space direction="vertical" size={2}>
              <Typography.Text type="secondary">尚未取样</Typography.Text>
              <Typography.Text type="secondary">{formatSourceHealthMessage(source)}</Typography.Text>
            </Space>
          );
        }
        return (
          <Space direction="vertical" size={2}>
            <Space wrap size={[4, 4]}>
              <Tag>{formatCapability(lastSmoke.capability)}</Tag>
              <StatusTag value={lastSmoke.status} />
              <Tag>
                原始 {formatNumber(lastSmoke.raw_records)} / 标准化 {formatNumber(lastSmoke.normalized_records)}
              </Tag>
            </Space>
            <Typography.Text type="secondary" ellipsis title={formatSmokeSample(lastSmoke.sample)}>
              {formatSmokeSample(lastSmoke.sample)}
            </Typography.Text>
          </Space>
        );
      },
    },
  ];
}

export function buildBatchColumns(onTraceBatch?: (batch: RecentIngestBatch) => void): ColumnsType<RecentIngestBatch> {
  return [
    {
      title: '批次',
      dataIndex: 'id',
      width: 100,
      render: (value) => <Typography.Text code>#{value}</Typography.Text>,
    },
    {
      title: '数据类型',
      dataIndex: 'dataset_name',
      width: 130,
      render: (value) => formatCapability(value),
    },
    {
      title: '来源',
      width: 150,
      render: (_, batch) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{batch.source}</Typography.Text>
          <Typography.Text type="secondary">请求 {batch.requested_source}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '范围',
      width: 180,
      render: (_, batch) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{formatRange(batch.start_date, batch.end_date)}</Typography.Text>
          <Typography.Text type="secondary">
            {formatMarket(batch.market)}
            {batch.symbol ? ` / ${batch.symbol}` : ''}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '版本',
      width: 130,
      render: (_, batch) => `${batch.schema_version} / ${batch.normalize_version}`,
    },
    {
      title: '写入',
      dataIndex: 'records_written',
      width: 100,
      render: (value) => formatNumber(value),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (_, batch) => (
        <Space direction="vertical" size={0}>
          <StatusTag value={batch.status} />
          <Typography.Text type="secondary">{batch.quality_status}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '完成时间',
      dataIndex: 'finished_at',
      width: 170,
      render: (value) => formatDateTime(value),
    },
    {
      title: '追溯',
      key: 'trace',
      fixed: 'right',
      width: 150,
      render: (_, batch) => {
        const taskId = getNumericTaskId(batch.task_id);
        return (
          <Space size={2}>
            {taskId ? (
              <Link to="/sync-tasks" search={{ taskId, page: 1, pageSize: 10 }}>
                <Button type="link" size="small" icon={<ProfileOutlined />}>
                  任务
                </Button>
              </Link>
            ) : null}
            {batch.dataset_name === 'daily_bars' && batch.symbol ? (
              <Link to="/stocks/$symbol" params={{ symbol: batch.symbol }}>
                <Button type="link" size="small" icon={<StockOutlined />}>
                  股票
                </Button>
              </Link>
            ) : null}
            <Button type="link" size="small" onClick={() => onTraceBatch?.(batch)}>
              血缘
            </Button>
            {!taskId && !(batch.dataset_name === 'daily_bars' && batch.symbol) ? '-' : null}
          </Space>
        );
      },
    },
  ];
}

export function buildLineageColumns(): ColumnsType<DatabaseLineageItem> {
  return [
    {
      title: '批次',
      dataIndex: 'id',
      width: 96,
      render: (value, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text code>#{value}</Typography.Text>
          <StatusTag value={item.status} />
        </Space>
      ),
    },
    {
      title: '写入对象',
      width: 190,
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{formatCapability(item.dataset_name)}</Typography.Text>
          <Typography.Text type="secondary">
            {formatMarket(item.market)}
            {item.symbol ? ` / ${item.symbol}` : ''}
          </Typography.Text>
          <Typography.Text type="secondary">{formatRange(item.start_date, item.end_date)}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '来源链路',
      width: 180,
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>
            请求 {item.requested_source} 到实际 {item.source}
          </Typography.Text>
          <Typography.Text type="secondary">
            任务 {formatTaskType(item.task_type)} / {item.task_source}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '处理版本',
      width: 160,
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>Schema {item.schema_version}</Typography.Text>
          <Typography.Text type="secondary">Normalize {item.normalize_version}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '记录数',
      width: 160,
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>写入 {formatNumber(item.records_written)}</Typography.Text>
          <Typography.Text type="secondary">
            原始 {formatNumber(item.raw_records)} / 标准化 {formatNumber(item.normalized_records)} / 丢弃 {formatNumber(item.dropped_records)}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '质量',
      dataIndex: 'quality_status',
      width: 110,
      render: (value) => <StatusTag value={value} />,
    },
    {
      title: '执行时间',
      width: 190,
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{formatDateTime(item.started_at)}</Typography.Text>
          <Typography.Text type="secondary">完成 {formatDateTime(item.finished_at)}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '错误',
      width: 190,
      render: (_, item) => {
        const message = item.error_message || item.task_error_message || item.validation_errors_json?.[0];
        return message ? (
          <Typography.Text type="danger" ellipsis title={message}>
            {message}
          </Typography.Text>
        ) : (
          <Typography.Text type="secondary">无</Typography.Text>
        );
      },
    },
    {
      title: '追溯',
      key: 'trace',
      fixed: 'right',
      width: 150,
      render: (_, item) => {
        const taskId = getNumericTaskId(item.task_id);
        return (
          <Space size={2}>
            {taskId ? (
              <Link to="/sync-tasks" search={{ taskId, page: 1, pageSize: 10 }}>
                <Button type="link" size="small" icon={<ProfileOutlined />}>
                  任务
                </Button>
              </Link>
            ) : null}
            {item.dataset_name === 'daily_bars' && item.symbol ? (
              <Link to="/stocks/$symbol" params={{ symbol: item.symbol }}>
                <Button type="link" size="small" icon={<StockOutlined />}>
                  股票
                </Button>
              </Link>
            ) : null}
          </Space>
        );
      },
    },
  ];
}

export function buildReportColumns(
  coverage?: DatabaseCoverageSummary,
  onTraceBatch?: TraceQualityReportBatch,
): ColumnsType<DataQualityReport> {
  return [
    {
      title: '数据集',
      dataIndex: 'dataset_name',
      width: 150,
      render: (value) => <Typography.Text strong>{formatCapability(value)}</Typography.Text>,
    },
    {
      title: '检查项',
      dataIndex: 'check_type',
      width: 150,
      render: (value) => formatQualityCheckType(value),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 96,
      render: (value) => <StatusTag value={value} />,
    },
    {
      title: '级别',
      dataIndex: 'severity',
      width: 100,
      render: (value) => <StatusTag value={value} />,
    },
    {
      title: '指标',
      width: 220,
      render: (_, report) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{report.metric_name}</Typography.Text>
          <Typography.Text type="secondary">
            实际 {report.metric_value ?? '-'} / 期望 {report.expected_value ?? '-'}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '说明',
      dataIndex: 'message',
      render: (value) => <Typography.Text>{value}</Typography.Text>,
    },
    {
      title: '回溯',
      key: 'trace',
      width: 260,
      render: (_, report) => {
        const trace = report.trace;
        if (!trace) {
          return <Typography.Text type="secondary">暂无批次记录</Typography.Text>;
        }
        const taskId = getNumericTaskId(trace.latest_task_id);
        const batchId = getNumericRecordId(trace.latest_batch_id);
        const batchLabel = trace.latest_batch_id ? `批次 #${trace.latest_batch_id}` : '暂无批次';
        const sourceLabel = trace.latest_batch_source || trace.dataset_source || '-';
        return (
          <Space direction="vertical" size={2}>
            <Space wrap size={[6, 4]}>
              <Tag color="blue">来源 {sourceLabel}</Tag>
              <Tag>{formatStorageType(trace.storage_type || '-')}</Tag>
              <Tag>{formatNumber(trace.row_count ?? 0)} 行</Tag>
            </Space>
            <Typography.Text type="secondary">
              Schema {formatNumber(trace.schema_fields_count ?? 0)} 字段 / 主键 {trace.primary_keys_json?.join(', ') || '-'}
            </Typography.Text>
            <Space wrap size={[6, 4]}>
              <Typography.Text type="secondary">
                {batchLabel}
                {trace.latest_batch_schema_version || trace.latest_batch_normalize_version
                  ? ` / ${trace.latest_batch_schema_version || '-'} / ${trace.latest_batch_normalize_version || '-'}`
                  : ''}
              </Typography.Text>
              {taskId ? (
                <Link to="/sync-tasks" search={{ taskId, page: 1, pageSize: 10 }}>
                  <Button type="link" size="small" icon={<ProfileOutlined />}>
                    任务
                  </Button>
                </Link>
              ) : null}
              {batchId && onTraceBatch ? (
                <Button type="link" size="small" icon={<FileSearchOutlined />} onClick={() => onTraceBatch(report)}>
                  血缘
                </Button>
              ) : null}
            </Space>
          </Space>
        );
      },
    },
    {
      title: '检查时间',
      dataIndex: 'checked_at',
      width: 180,
      render: (value) => formatDateTime(value),
    },
    {
      title: '治理',
      key: 'action',
      fixed: 'right',
      width: 120,
      render: (_, report) => {
        const action = getQualityReportAction(report, coverage);
        return action ? (
          <Link to={action.to} search={action.search}>
            <Button type="link" size="small" icon={<CloudSyncOutlined />}>
              {action.label}
            </Button>
          </Link>
        ) : (
          <Typography.Text type="secondary">查看说明</Typography.Text>
        );
      },
    },
  ];
}

