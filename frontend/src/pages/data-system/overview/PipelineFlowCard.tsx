import { Card, Progress, Space, Tag, Typography } from 'antd';
import { ApiOutlined, CheckCircleOutlined, DatabaseOutlined, FileSearchOutlined, SafetyCertificateOutlined, SyncOutlined, WarningOutlined, RightOutlined } from '@ant-design/icons';
import { Button } from 'antd';

interface PipelineNode {
  key: string;
  label: string;
  icon: React.ReactNode;
  status: 'ok' | 'warning' | 'error' | 'idle';
  primaryText: string;
  secondaryText?: string;
}

export function PipelineFlowCard({
  sourceHealthy,
  sourceTotal,
  sourceUnhealthy,
  dailyMissingSymbolDays,
  latestDailyDate,
  coveragePercent,
  datasetCount,
  datasetTotalRows,
  onOpenSources,
  onOpenDatabase,
  onOpenNumericSummary,
  onOpenStocks,
}: {
  sourceHealthy: number;
  sourceTotal: number;
  sourceUnhealthy: number;
  dailyMissingSymbolDays: number;
  latestDailyDate: string | null;
  coveragePercent: number;
  datasetCount: number;
  datasetTotalRows: number;
  onOpenSources: () => void;
  onOpenDatabase: () => void;
  onOpenNumericSummary: () => void;
  onOpenStocks: () => void;
}) {
  const nodes: PipelineNode[] = [
    {
      key: 'sources',
      label: '数据源',
      icon: <ApiOutlined />,
      status: sourceUnhealthy > 0 ? 'warning' : sourceTotal > 0 ? 'ok' : 'idle',
      primaryText: `${sourceHealthy}/${sourceTotal}`,
      secondaryText: sourceUnhealthy > 0 ? `${sourceUnhealthy} 个需处理` : '全部正常',
    },
    {
      key: 'sync',
      label: '同步任务',
      icon: <SyncOutlined />,
      status: 'ok',
      primaryText: '运行中',
      secondaryText: '自动调度',
    },
    {
      key: 'lake',
      label: '数据湖',
      icon: <DatabaseOutlined />,
      status: datasetTotalRows > 0 ? 'ok' : 'idle',
      primaryText: `${datasetCount} 个数据集`,
      secondaryText: datasetTotalRows > 0 ? `${datasetTotalRows.toLocaleString()} 行` : '暂无数据',
    },
    {
      key: 'quality',
      label: '数据质量',
      icon: <SafetyCertificateOutlined />,
      status: dailyMissingSymbolDays > 0 ? 'warning' : 'ok',
      primaryText: `${coveragePercent}%`,
      secondaryText: dailyMissingSymbolDays > 0 ? `${dailyMissingSymbolDays} 缺口` : '完整度良好',
    },
  ];

  const statusIcon = {
    ok: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
    warning: <WarningOutlined style={{ color: '#faad14' }} />,
    error: <WarningOutlined style={{ color: '#ff4d4f' }} />,
    idle: <CheckCircleOutlined style={{ color: '#d9d9d9' }} />,
  };

  const handleClick = (key: string) => {
    switch (key) {
      case 'sources': onOpenSources(); break;
      case 'lake': onOpenDatabase(); break;
      case 'quality': onOpenNumericSummary(); break;
      case 'sync': onOpenStocks(); break;
    }
  };

  return (
    <Card
      className="overview-panel"
      title={
        <Space>
          <FileSearchOutlined />
          <span>数据流</span>
        </Space>
      }
      extra={<Typography.Text type="secondary">从源到质量的完整链路</Typography.Text>}
    >
      <div style={{ display: 'flex', gap: 12, overflowX: 'auto', padding: '8px 0' }}>
        {nodes.map((node, index) => (
          <div key={node.key} style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
            <Button
              type="text"
              onClick={() => handleClick(node.key)}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                width: 120,
                height: 100,
                borderRadius: 12,
                border: '1px solid #f0f0f0',
                background: '#fafafa',
                cursor: 'pointer',
              }}
            >
              <Space direction="vertical" size={4} align="center">
                <span style={{ fontSize: 20 }}>{node.icon}</span>
                <Typography.Text strong style={{ fontSize: 13 }}>{node.label}</Typography.Text>
                <Space size={4}>
                  {statusIcon[node.status]}
                  <Typography.Text style={{ fontSize: 14, fontWeight: 600 }}>{node.primaryText}</Typography.Text>
                </Space>
                {node.secondaryText && (
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>{node.secondaryText}</Typography.Text>
                )}
              </Space>
            </Button>
            {index < nodes.length - 1 && (
              <RightOutlined style={{ color: '#d9d9d9', fontSize: 16 }} />
            )}
          </div>
        ))}
      </div>
      <div style={{ marginTop: 12 }}>
        <Space size={16}>
          <Space size={4}>
            <span>日线最新</span>
            <Typography.Text strong>{latestDailyDate ?? '暂无'}</Typography.Text>
          </Space>
          <Space size={4}>
            <span>完整度</span>
            <Progress percent={coveragePercent} size="small" style={{ width: 80 }} />
          </Space>
          <Tag color={dailyMissingSymbolDays > 0 ? 'orange' : 'green'}>
            {dailyMissingSymbolDays > 0 ? `${dailyMissingSymbolDays} 个缺口待补` : '无缺口'}
          </Tag>
        </Space>
      </div>
    </Card>
  );
}
