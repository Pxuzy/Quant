import { Link } from '@tanstack/react-router';
import { FileTextOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { Button, Empty, Space, Table, Typography } from 'antd';

import type { IngestBatch, SyncTask } from '../../../../features/sync-tasks/types';
import { formatDate, formatDateTime, formatNumber } from '../../../../shared/components/formatters';
import { StatusTag } from '../../../../shared/components/StatusTag';
import { formatMarket, formatSourceMode } from '../../../../shared/domain/labels';

function getBatchDataset(batch: IngestBatch) {
  return batch.dataset_name ?? batch.datasetName ?? '-';
}

function getBatchRequestedSource(batch: IngestBatch) {
  return batch.requested_source ?? batch.requestedSource;
}

function getBatchMarket(batch: IngestBatch) {
  return batch.market;
}

function getBatchSymbol(batch: IngestBatch) {
  return batch.symbol;
}

function getBatchStartDate(batch: IngestBatch) {
  return batch.start_date ?? batch.startDate;
}

function getBatchEndDate(batch: IngestBatch) {
  return batch.end_date ?? batch.endDate;
}

function getBatchSchemaVersion(batch: IngestBatch) {
  return batch.schema_version ?? batch.schemaVersion ?? '-';
}

function getBatchNormalizeVersion(batch: IngestBatch) {
  return batch.normalize_version ?? batch.normalizeVersion ?? '-';
}

function getBatchRawRecords(batch: IngestBatch) {
  return batch.raw_records ?? batch.rawRecords ?? 0;
}

function getBatchNormalizedRecords(batch: IngestBatch) {
  return batch.normalized_records ?? batch.normalizedRecords ?? 0;
}

function getBatchDroppedRecords(batch: IngestBatch) {
  return batch.dropped_records ?? batch.droppedRecords ?? 0;
}

function getBatchRecordsWritten(batch: IngestBatch) {
  return batch.records_written ?? batch.recordsWritten ?? 0;
}

function getBatchValidationErrors(batch: IngestBatch) {
  return batch.validation_errors_json ?? batch.validationErrorsJson ?? [];
}

function getBatchErrorMessage(batch: IngestBatch) {
  return batch.error_message ?? batch.errorMessage;
}

function getBatchQualityStatus(batch: IngestBatch) {
  return batch.quality_status ?? batch.qualityStatus ?? '-';
}

function getBatchStartedAt(batch: IngestBatch) {
  return batch.started_at ?? batch.startedAt;
}

function getBatchFinishedAt(batch: IngestBatch) {
  return batch.finished_at ?? batch.finishedAt;
}

function formatTaskSource(value?: string | null) {
  return value === 'auto' ? formatSourceMode(value) : value || '-';
}

function formatIngestBatchRange(batch: IngestBatch) {
  const startDate = getBatchStartDate(batch);
  const endDate = getBatchEndDate(batch);
  if (!startDate && !endDate) {
    return '-';
  }
  if (startDate && endDate && startDate !== endDate) {
    return `${formatDate(startDate)} ~ ${formatDate(endDate)}`;
  }
  return formatDate(endDate ?? startDate);
}

function canTraceBatchToStock(batch: IngestBatch) {
  return getBatchDataset(batch) === 'daily_bars' && Boolean(getBatchSymbol(batch));
}

type TaskBatchesTableProps = {
  task?: SyncTask;
  batches: IngestBatch[];
  loading: boolean;
  error: boolean;
};

export function TaskBatchesTable({ task, batches, loading, error }: TaskBatchesTableProps) {
  const columns: ColumnsType<IngestBatch> = [
    {
      title: '批次',
      dataIndex: 'id',
      width: 82,
      render: (value) => <Typography.Text strong>#{value}</Typography.Text>,
    },
    {
      title: '数据集',
      dataIndex: 'dataset_name',
      width: 132,
      render: (_, record) => getBatchDataset(record),
    },
    {
      title: '范围',
      key: 'range',
      width: 210,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{formatIngestBatchRange(record)}</Typography.Text>
          <Typography.Text type="secondary">
            {formatMarket(getBatchMarket(record), '全部市场')}
            {getBatchSymbol(record) ? ` / ${getBatchSymbol(record)}` : ''}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '实际来源',
      dataIndex: 'source',
      width: 120,
      render: (value) => value || '-',
    },
    {
      title: '请求来源',
      dataIndex: 'requested_source',
      width: 150,
      render: (_, record) => formatTaskSource(getBatchRequestedSource(record)),
    },
    {
      title: '校验',
      dataIndex: 'status',
      width: 112,
      render: (_, record) => <StatusTag value={record.status} />,
    },
    {
      title: '记录',
      key: 'records',
      width: 190,
      render: (_, record) => (
        <Typography.Text>
          原始 {formatNumber(getBatchRawRecords(record))} / 标准化 {formatNumber(getBatchNormalizedRecords(record))} / 丢弃 {formatNumber(getBatchDroppedRecords(record))} / 写入 {formatNumber(getBatchRecordsWritten(record))}
        </Typography.Text>
      ),
    },
    {
      title: '版本',
      key: 'versions',
      width: 150,
      render: (_, record) => (
        <Typography.Text type="secondary">
          schema {getBatchSchemaVersion(record)} / normalize {getBatchNormalizeVersion(record)}
        </Typography.Text>
      ),
    },
    {
      title: '质量',
      dataIndex: 'quality_status',
      width: 100,
      render: (_, record) => <StatusTag value={getBatchQualityStatus(record)} />,
    },
    {
      title: '追溯',
      key: 'trace',
      fixed: 'right',
      width: 104,
      render: (_, record) =>
        canTraceBatchToStock(record) ? (
          <Link to="/data-system/stocks/$symbol" params={{ symbol: getBatchSymbol(record) ?? '' }}>
            <Button type="link" size="small" icon={<FileTextOutlined />}>
              查看股票
            </Button>
          </Link>
        ) : (
          '-'
        ),
    },
  ];

  return (
    <div>
      <Typography.Title level={5}>数据整合批次</Typography.Title>
      {error ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="批次信息加载失败" />
      ) : batches.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据整合批次" />
      ) : (
        <Table<IngestBatch>
          className="task-ingest-batches-table"
          rowKey={(record) => String(record.id)}
          columns={columns}
          dataSource={batches}
          loading={loading}
          pagination={false}
          size="small"
          scroll={{ x: 1350 }}
          expandable={{
            expandedRowRender: (record) => {
              const validationErrors = getBatchValidationErrors(record);
              const errorMessage = getBatchErrorMessage(record);
              if (!validationErrors.length && !errorMessage) {
                return <Typography.Text type="secondary">校验通过，无错误信息。</Typography.Text>;
              }
              return (
                <Space direction="vertical" size={4}>
                  {errorMessage ? <Typography.Text type="danger">{errorMessage}</Typography.Text> : null}
                  {validationErrors.map((validationError) => (
                    <Typography.Text key={validationError} code>
                      {validationError}
                    </Typography.Text>
                  ))}
                </Space>
              );
            },
          }}
        />
      )}
    </div>
  );
}
