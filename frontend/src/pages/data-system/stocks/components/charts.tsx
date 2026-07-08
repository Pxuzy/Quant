// Extracted from StockDetailPage — chart and quality tag sub-components
import { Empty, Space, Tag, Typography } from 'antd';
import { formatDate, formatDecimal, formatNumber } from '../../../../shared/components/formatters';
import type { ChartModel, QualitySummary } from './utils';
import { CHART_HEIGHT, CHART_PADDING, CHART_WIDTH } from './utils';


export function CloseVolumeChart({ model }: { model: ChartModel | null }) {
  if (!model) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无日线数据，先在同步调度中同步该股票日线。" />;
  }

  const isUp = model.latest.close >= model.first.close;
  const ticks = [model.maxPrice, (model.maxPrice + model.minPrice) / 2, model.minPrice];
  const plotHeight = CHART_HEIGHT - CHART_PADDING.top - CHART_PADDING.bottom;
  const priceToY = (value: number) =>
    CHART_PADDING.top + ((model.upperBound - value) / Math.max(model.upperBound - model.lowerBound, 1)) * plotHeight;

  return (
    <div className={`stock-detail-chart ${isUp ? 'is-up' : 'is-down'}`}>
      <div className="stock-detail-chart-meta">
        <Space size={12} wrap>
          <Tag color="blue">K 线</Tag>
          <Tag>收盘趋势</Tag>
          <Tag>成交量</Tag>
          <Typography.Text type="secondary">
            {formatDate(model.first.trade_date)} ~ {formatDate(model.latest.trade_date)}
          </Typography.Text>
        </Space>
      </div>
      <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} role="img" aria-label="单股收盘趋势和成交量">
        <defs>
          <linearGradient id="stockDetailTrendFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.16" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {ticks.map((tick) => {
          const y = priceToY(tick);
          return (
            <g key={tick}>
              <line className="stock-detail-grid" x1={CHART_PADDING.left} x2={CHART_WIDTH - CHART_PADDING.right} y1={y} y2={y} />
              <text className="stock-detail-axis" x={CHART_PADDING.left - 10} y={y + 4} textAnchor="end">
                {formatDecimal(tick)}
              </text>
            </g>
          );
        })}
        {model.volumeBars.map((bar, index) => (
          <rect
            key={`${model.rows[index].trade_date}-volume`}
            className={`stock-detail-volume ${bar.isUp ? 'is-up' : 'is-down'}`}
            x={bar.x}
            y={bar.y}
            width={bar.width}
            height={bar.height}
            rx={3}
          />
        ))}
        <path className="stock-detail-area" d={model.areaPath} />
        {model.candles.map((candle) => {
          const bodyY = Math.min(candle.openY, candle.closeY);
          const bodyHeight = Math.max(Math.abs(candle.closeY - candle.openY), 2);
          return (
            <g key={`${candle.row.trade_date}-candle`} className={`stock-detail-candle ${candle.isUp ? 'is-up' : 'is-down'}`}>
              <line className="stock-detail-candle-wick" x1={candle.x} x2={candle.x} y1={candle.highY} y2={candle.lowY} />
              <rect
                className="stock-detail-candle-body"
                x={candle.x - candle.width / 2}
                y={bodyY}
                width={candle.width}
                height={bodyHeight}
                rx={1.5}
              >
                <title>
                  {`${formatDate(candle.row.trade_date)} 开 ${formatDecimal(candle.row.open)} 高 ${formatDecimal(candle.row.high)} 低 ${formatDecimal(candle.row.low)} 收 ${formatDecimal(candle.row.close)}`}
                </title>
              </rect>
            </g>
          );
        })}
        <path className="stock-detail-line" d={model.linePath} />
        {model.points.map((point) => (
          <circle key={point.row.trade_date} className="stock-detail-point" cx={point.x} cy={point.y} r={3.2}>
            <title>{`${formatDate(point.row.trade_date)} 收盘 ${formatDecimal(point.row.close)}`}</title>
          </circle>
        ))}
        <text className="stock-detail-axis" x={model.points[0].x} y={CHART_HEIGHT - 8} textAnchor="start">
          {formatDate(model.first.trade_date)}
        </text>
        <text className="stock-detail-axis" x={model.points[model.points.length - 1].x} y={CHART_HEIGHT - 8} textAnchor="end">
          {formatDate(model.latest.trade_date)}
        </text>
      </svg>
    </div>
  );
}

export function QualityTags({ summary }: { summary: QualitySummary }) {
  if (!summary.checkedRows) {
    return <Tag>暂无样本</Tag>;
  }

  return (
    <Space wrap size={[8, 8]}>
      <Tag color={summary.duplicateDates ? 'red' : 'green'}>重复日期 {formatNumber(summary.duplicateDates)}</Tag>
      <Tag color={summary.priceErrors ? 'red' : 'green'}>价格异常 {formatNumber(summary.priceErrors)}</Tag>
      <Tag color={summary.missingSampleGaps ? 'warning' : 'green'}>大间隔样本 {formatNumber(summary.missingSampleGaps)}</Tag>
      <Tag color="blue">检查样本 {formatNumber(summary.checkedRows)} 条</Tag>
    </Space>
  );
}
