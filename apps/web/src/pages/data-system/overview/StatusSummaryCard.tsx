import { Button, Card, Space, Tag, Typography } from 'antd';
import { ArrowRightOutlined } from '@ant-design/icons';
import type { AlertItem } from './AlertBanner';
import { AlertBanner } from './AlertBanner';

export function StatusSummaryCard({
  decisionTone,
  decisionTitle,
  decisionDescription,
  decisionActionLabel,
  onDecisionAction,
  dailySyncLabel,
  onDailySync,
  dailySyncLoading,
  alerts,
}: {
  decisionTone: 'success' | 'warning' | 'danger';
  decisionTitle: string;
  decisionDescription: string;
  decisionActionLabel: string;
  onDecisionAction: () => void;
  dailySyncLabel: string;
  onDailySync: () => void;
  dailySyncLoading?: boolean;
  alerts: AlertItem[];
}) {
  const toneColor = {
    success: '#52c41a',
    warning: '#faad14',
    danger: '#ff4d4f',
  } as const;

  return (
    <Card className="overview-panel motion-summary-card" style={{ marginBottom: 16 }}>
      <AlertBanner alerts={alerts} />
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Space align="start" size={12}>
          <Tag color={toneColor[decisionTone]}>{decisionTone === 'success' ? '正常' : decisionTone === 'warning' ? '注意' : '异常'}</Tag>
          <Space direction="vertical" size={4}>
            <Typography.Title level={4} style={{ margin: 0 }}>{decisionTitle}</Typography.Title>
            <Typography.Text type="secondary">{decisionDescription}</Typography.Text>
          </Space>
        </Space>
        <Space>
          <Button type="primary" icon={<ArrowRightOutlined />} onClick={onDecisionAction}>
            {decisionActionLabel}
          </Button>
          <Button loading={dailySyncLoading} onClick={onDailySync}>
            {dailySyncLabel}
          </Button>
        </Space>
      </Space>
    </Card>
  );
}
