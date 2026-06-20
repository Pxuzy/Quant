import { useMemo, useRef } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  ApiOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  GlobalOutlined,
  NotificationOutlined,
  ReadOutlined,
  ReloadOutlined,
  RightOutlined,
  StockOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Alert, Button, Card, Col, Empty, List, Progress, Row, Space, Statistic, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { formatNumber } from '../../../shared/components/formatters';
import { fadeInUp, useGSAP } from '../../../shared/motion/gsapMotion';

type NewsSentiment = 'positive' | 'neutral' | 'negative';
type NewsSourceStatus = 'healthy' | 'warning' | 'pending';

type NewsSource = {
  key: string;
  name: string;
  type: string;
  status: NewsSourceStatus;
  todayCount: number;
  coverage: number;
  latency: string;
  lastPulledAt: string;
};

type TopicCluster = {
  key: string;
  name: string;
  count: number;
  heat: number;
  trend: string;
  sentiment: NewsSentiment;
  symbols: string[];
};

type NewsItem = {
  id: string;
  title: string;
  summary: string;
  source: string;
  category: string;
  topic: string;
  time: string;
  sentiment: NewsSentiment;
  impactScore: number;
  symbols: string[];
};

const NEWS_INTERFACE_READY = false;

const newsSources: NewsSource[] = [
  {
    key: 'exchange',
    name: '交易所公告',
    type: '公告',
    status: 'healthy',
    todayCount: 128,
    coverage: 96,
    latency: '3 min',
    lastPulledAt: '今日 10:48',
  },
  {
    key: 'media',
    name: '财经媒体',
    type: '资讯',
    status: 'healthy',
    todayCount: 312,
    coverage: 91,
    latency: '6 min',
    lastPulledAt: '今日 10:45',
  },
  {
    key: 'research',
    name: '研报摘要',
    type: '研报',
    status: 'warning',
    todayCount: 46,
    coverage: 74,
    latency: '22 min',
    lastPulledAt: '今日 10:18',
  },
  {
    key: 'policy',
    name: '政策动态',
    type: '宏观',
    status: 'healthy',
    todayCount: 37,
    coverage: 88,
    latency: '8 min',
    lastPulledAt: '今日 10:41',
  },
];

const topicClusters: TopicCluster[] = [
  {
    key: 'ai-chip',
    name: 'AI 算力与半导体',
    count: 62,
    heat: 86,
    trend: '+18%',
    sentiment: 'positive',
    symbols: ['688981', '603986', '300308'],
  },
  {
    key: 'consumption',
    name: '消费复苏',
    count: 48,
    heat: 72,
    trend: '+9%',
    sentiment: 'neutral',
    symbols: ['600519', '000858', '603288'],
  },
  {
    key: 'new-energy',
    name: '新能源价格链',
    count: 41,
    heat: 66,
    trend: '-6%',
    sentiment: 'negative',
    symbols: ['300750', '002594', '601012'],
  },
  {
    key: 'brokerage',
    name: '券商并购与资本市场',
    count: 29,
    heat: 58,
    trend: '+5%',
    sentiment: 'positive',
    symbols: ['600030', '601688', '000776'],
  },
];

const newsItems: NewsItem[] = [
  {
    id: 'n-001',
    title: '半导体设备订单改善，先进制程扩产预期升温',
    summary: '产业链反馈设备交付节奏较上月加快，市场关注国产替代订单释放。',
    source: '财经媒体',
    category: '产业',
    topic: 'AI 算力与半导体',
    time: '今日 10:36',
    sentiment: 'positive',
    impactScore: 86,
    symbols: ['688981', '603986'],
  },
  {
    id: 'n-002',
    title: '白酒渠道库存继续去化，端午后批价保持平稳',
    summary: '高端酒批价波动收敛，渠道反馈补货节奏仍偏谨慎。',
    source: '研报摘要',
    category: '消费',
    topic: '消费复苏',
    time: '今日 10:12',
    sentiment: 'neutral',
    impactScore: 63,
    symbols: ['600519', '000858'],
  },
  {
    id: 'n-003',
    title: '锂电材料价格延续回落，二线厂商盈利承压',
    summary: '碳酸锂现货报价继续下探，成本曲线较高的公司被重点关注。',
    source: '财经媒体',
    category: '产业',
    topic: '新能源价格链',
    time: '今日 09:58',
    sentiment: 'negative',
    impactScore: 74,
    symbols: ['300750', '002812'],
  },
  {
    id: 'n-004',
    title: '交易所披露多家公司回购进展，电子与医药占比较高',
    summary: '多家公司更新回购比例与资金上限，稳定股价信号增强。',
    source: '交易所公告',
    category: '公告',
    topic: '回购与增持',
    time: '今日 09:42',
    sentiment: 'positive',
    impactScore: 68,
    symbols: ['002475', '300760', '688111'],
  },
  {
    id: 'n-005',
    title: '多地发布低空经济配套政策，应用场景继续扩容',
    summary: '地方补贴、空域管理和基础设施规划密集落地，主题热度回升。',
    source: '政策动态',
    category: '政策',
    topic: '低空经济',
    time: '今日 09:21',
    sentiment: 'positive',
    impactScore: 71,
    symbols: ['000099', '002085'],
  },
];

const sentimentMeta: Record<NewsSentiment, { label: string; color: string; className: string }> = {
  positive: { label: '正面', color: 'red', className: 'is-positive' },
  neutral: { label: '中性', color: 'blue', className: 'is-neutral' },
  negative: { label: '负面', color: 'green', className: 'is-negative' },
};

const sourceStatusMeta: Record<NewsSourceStatus, { label: string; color: string }> = {
  healthy: { label: '正常', color: 'green' },
  warning: { label: '延迟', color: 'warning' },
  pending: { label: '待接入', color: 'default' },
};

const displayedSourceStatus = (status: NewsSourceStatus) => (NEWS_INTERFACE_READY ? status : 'pending');

function getSentimentCount(items: NewsItem[], sentiment: NewsSentiment) {
  return items.filter((item) => item.sentiment === sentiment).length;
}

function buildNewsColumns(): ColumnsType<NewsItem> {
  return [
    {
      title: '新闻内容',
      dataIndex: 'title',
      width: 420,
      render: (_, record) => (
        <Space className="news-title-cell" direction="vertical" size={4}>
          <Typography.Text strong>{record.title}</Typography.Text>
          <Typography.Text type="secondary">{record.summary}</Typography.Text>
          <Space wrap size={[6, 4]}>
            <Tag>{record.topic}</Tag>
            <Tag color="cyan">{record.category}</Tag>
          </Space>
        </Space>
      ),
    },
    {
      title: '情绪',
      dataIndex: 'sentiment',
      width: 92,
      render: (value: NewsSentiment) => <Tag color={sentimentMeta[value].color}>{sentimentMeta[value].label}</Tag>,
    },
    {
      title: '影响分',
      dataIndex: 'impactScore',
      width: 150,
      render: (value: number) => <Progress percent={value} size="small" strokeColor="#2f6f9f" />,
    },
    {
      title: '关联股票',
      dataIndex: 'symbols',
      width: 180,
      render: (symbols: string[]) => (
        <Space wrap size={[4, 4]}>
          {symbols.map((symbol) => (
            <Tag key={symbol}>{symbol}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '来源 / 时间',
      dataIndex: 'source',
      width: 160,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{record.source}</Typography.Text>
          <Typography.Text type="secondary">{record.time}</Typography.Text>
        </Space>
      ),
    },
  ];
}

export function NewsSummaryPage() {
  const pageRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const columns = useMemo(() => buildNewsColumns(), []);

  const todayTotal = useMemo(
    () => newsSources.reduce((sum, source) => sum + source.todayCount, 0),
    [],
  );
  const watchedSymbols = useMemo(
    () => new Set(newsItems.flatMap((item) => item.symbols)).size,
    [],
  );
  const sentimentStats = useMemo(
    () => [
      { key: 'positive' as const, value: getSentimentCount(newsItems, 'positive') },
      { key: 'neutral' as const, value: getSentimentCount(newsItems, 'neutral') },
      { key: 'negative' as const, value: getSentimentCount(newsItems, 'negative') },
    ],
    [],
  );
  // 新闻页先把需要的能力摊开，真实接口接入前也能确认后续工作流。
  const newsWorkflowItems = [
    {
      key: 'ingest',
      title: '采集新闻',
      value: `${formatNumber(todayTotal)} 条`,
      description: '公告、资讯、研报、政策动态统一入库',
      icon: <ReadOutlined />,
    },
    {
      key: 'dedupe',
      title: '去重解析',
      value: '标题 + 正文',
      description: '合并重复新闻，提取时间、来源和类别',
      icon: <FileTextOutlined />,
    },
    {
      key: 'link',
      title: '关联股票',
      value: `${formatNumber(watchedSymbols)} 只`,
      description: '按股票代码、公司名和主题标签关联',
      icon: <StockOutlined />,
    },
    {
      key: 'score',
      title: '情绪与影响',
      value: `${topicClusters[0].heat} 分`,
      description: '形成主题热度、情绪分布和影响分',
      icon: <ThunderboltOutlined />,
    },
  ];

  useGSAP(
    () => {
      const root = pageRef.current;
      if (!root) {
        return;
      }

      fadeInUp(root.querySelectorAll('.motion-summary-card'), { stagger: 0.045, y: 8 });
      fadeInUp(root.querySelectorAll('.command-panel'), { delay: 0.08, stagger: 0.04, y: 10 });
    },
    { scope: pageRef },
  );

  return (
    <div className="workbench data-command-page news-summary-page" ref={pageRef}>
      <div className="workbench-heading command-heading">
        <Space direction="vertical" size={4}>
          <Typography.Title level={3}>新闻汇总</Typography.Title>
          <Typography.Text type="secondary">新闻接口待接入，当前先保留汇总页结构和后续接入入口</Typography.Text>
        </Space>
        <Space className="command-actions" wrap>
          <Button icon={<ReloadOutlined />} disabled={!NEWS_INTERFACE_READY}>
            刷新新闻
          </Button>
          <Button icon={<StockOutlined />} onClick={() => void navigate({ to: '/data-system/stocks' })}>
            查看股票池
          </Button>
          <Button type="primary" icon={<RightOutlined />} onClick={() => void navigate({ to: '/data-system/data-sources' })}>
            数据源管理
          </Button>
        </Space>
      </div>

      <Alert
        className="news-boundary-alert"
        type="info"
        showIcon
        message="新闻汇总暂未接入真实后端接口"
        description="本页下方保留的是目标结构样例，用来确认你后续需要公告、资讯、研报、政策动态、主题聚类和股票关联。当前不会作为策略、回测或数据质量判断依据。"
        action={
          <Button size="small" type="primary" icon={<ApiOutlined />} onClick={() => void navigate({ to: '/data-system/data-sources' })}>
            接入新闻源
          </Button>
        }
      />

      <div className="news-workflow-strip">
        {newsWorkflowItems.map((item) => (
          <div className="news-workflow-item" key={item.key}>
            <span className="news-workflow-icon">{item.icon}</span>
            <div>
              <Typography.Text type="secondary">{item.title}</Typography.Text>
              <Typography.Title level={5}>{item.value}</Typography.Title>
              <Typography.Text type="secondary">{item.description}</Typography.Text>
            </div>
          </div>
        ))}
      </div>

      <Row gutter={[14, 14]} className="summary-row command-summary-row">
        <Col span={6}>
          <Card className="motion-summary-card command-kpi-card accent-blue">
            <Statistic title="今日新闻量" value={todayTotal} prefix={<ReadOutlined />} suffix="条" />
            <Typography.Text type="secondary">样例数据，真实接口接入后启用</Typography.Text>
          </Card>
        </Col>
        <Col span={6}>
          <Card className="motion-summary-card command-kpi-card accent-green">
            <Statistic title="关联股票" value={watchedSymbols} prefix={<StockOutlined />} suffix="只" />
            <Typography.Text type="secondary">按新闻标题、正文与标签聚合</Typography.Text>
          </Card>
        </Col>
        <Col span={6}>
          <Card className="motion-summary-card command-kpi-card accent-amber">
            <Statistic title="高热主题" value={topicClusters[0].heat} prefix={<ThunderboltOutlined />} suffix="分" />
            <Typography.Text type="secondary">{topicClusters[0].name}</Typography.Text>
          </Card>
        </Col>
        <Col span={6}>
          <Card className="motion-summary-card command-kpi-card accent-cyan">
            <Statistic title="平均延迟" value={7} prefix={<ClockCircleOutlined />} suffix="min" />
            <Typography.Text type="secondary">待后端采集任务上报</Typography.Text>
          </Card>
        </Col>
      </Row>

      <Row gutter={[14, 14]} align="stretch">
        <Col span={15}>
          <Card className="command-panel news-flow-panel" title="重点新闻流样例">
            <Table<NewsItem>
              rowKey="id"
              columns={columns}
              dataSource={newsItems}
              pagination={false}
              scroll={{ x: 960 }}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无新闻" /> }}
            />
          </Card>
        </Col>
        <Col span={9}>
          <Card className="command-panel news-sentiment-panel" title="情绪分布">
            <Space className="news-sentiment-stack" direction="vertical" size={12}>
              {sentimentStats.map((item) => {
                const meta = sentimentMeta[item.key];
                const percent = newsItems.length ? Math.round((item.value / newsItems.length) * 100) : 0;
                return (
                  <div className={`news-sentiment-row ${meta.className}`} key={item.key}>
                    <Space className="news-sentiment-row-head">
                      <Typography.Text strong>{meta.label}</Typography.Text>
                      <Typography.Text type="secondary">
                        {formatNumber(item.value)} 条 / {percent}%
                      </Typography.Text>
                    </Space>
                    <Progress percent={percent} showInfo={false} size="small" />
                  </div>
                );
              })}
            </Space>
          </Card>

          <Card className="command-panel news-source-panel" title="新闻源接入状态">
            <List
              className="news-source-list"
              dataSource={newsSources}
              renderItem={(source) => (
                <List.Item>
                  <Space className="news-source-item" direction="vertical" size={8}>
                    <Space className="news-source-heading">
                      <Space>
                        <GlobalOutlined />
                        <Typography.Text strong>{source.name}</Typography.Text>
                      </Space>
                      <Tag color={sourceStatusMeta[displayedSourceStatus(source.status)].color}>
                        {sourceStatusMeta[displayedSourceStatus(source.status)].label}
                      </Tag>
                    </Space>
                    <div className="news-source-metrics">
                      <div>
                        <Typography.Text type="secondary">今日</Typography.Text>
                        <Typography.Text strong>{formatNumber(source.todayCount)}</Typography.Text>
                      </div>
                      <div>
                        <Typography.Text type="secondary">覆盖</Typography.Text>
                        <Typography.Text strong>{source.coverage}%</Typography.Text>
                      </div>
                      <div>
                        <Typography.Text type="secondary">延迟</Typography.Text>
                        <Typography.Text strong>{source.latency}</Typography.Text>
                      </div>
                    </div>
                    <Typography.Text type="secondary">
                      {NEWS_INTERFACE_READY ? source.lastPulledAt : `${source.type}接口待接入`}
                    </Typography.Text>
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[14, 14]} align="stretch">
        <Col span={16}>
          <Card className="command-panel news-topic-panel" title="主题聚类">
            <div className="news-topic-grid">
              {topicClusters.map((topic) => (
                <div className="news-topic-card" key={topic.key}>
                  <Space className="news-topic-heading">
                    <Space>
                      <NotificationOutlined />
                      <Typography.Text strong>{topic.name}</Typography.Text>
                    </Space>
                    <Tag color={sentimentMeta[topic.sentiment].color}>{sentimentMeta[topic.sentiment].label}</Tag>
                  </Space>
                  <div className="news-topic-number-row">
                    <Typography.Title level={4}>{formatNumber(topic.count)}</Typography.Title>
                    <Typography.Text type={topic.trend.startsWith('-') ? 'danger' : 'success'}>{topic.trend}</Typography.Text>
                  </div>
                  <Progress percent={topic.heat} size="small" strokeColor="#2f6f9f" />
                  <Space wrap size={[4, 4]}>
                    {topic.symbols.map((symbol) => (
                      <Tag key={symbol}>{symbol}</Tag>
                    ))}
                  </Space>
                </div>
              ))}
            </div>
          </Card>
        </Col>
        <Col span={8}>
          <Card className="command-panel news-ingest-panel" title="入库管线">
            <Space className="news-pipeline" direction="vertical" size={10}>
              {[
                { label: '拉取', value: '492 条', icon: <ReadOutlined /> },
                { label: '去重', value: '31 条', icon: <FileTextOutlined /> },
                { label: '解析', value: '461 条', icon: <ThunderboltOutlined /> },
                { label: '关联股票', value: `${watchedSymbols} 只`, icon: <StockOutlined /> },
              ].map((step) => (
                <div className="news-pipeline-step" key={step.label}>
                  <span className="news-pipeline-icon">{step.icon}</span>
                  <Typography.Text>{step.label}</Typography.Text>
                  <Typography.Text strong>{step.value}</Typography.Text>
                </div>
              ))}
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
