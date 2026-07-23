import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearch } from '@tanstack/react-router';
import { CalendarOutlined, FileTextOutlined, ReloadOutlined, SyncOutlined, CheckCircleOutlined, SendOutlined, DatabaseOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Col,
  Collapse,
  DatePicker,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Progress,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Timeline,
  Tooltip,
  Typography,
} from 'antd';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import { useDataSourcesQuery } from '../../../features/data-sources/api';
import type { DataSource } from '../../../features/data-sources/types';
import { useDatabaseIntegrationOverviewQuery } from '../../../features/database/api';
import type {
  DatabaseCoverageSummary,
  DatabaseIntegrationOverview,
  RecentIngestBatch,
  SyncWatermark,
} from '../../../features/database/types';
import {
  usePreviewDailyBarsMarketRepairMutation,
  useSyncDailyBarsMarketRepairMutation,
  useSyncDailyBarsMutation,
} from '../../../features/market-data/api';
import type { DailyBarsMarketRepairPreviewResponse } from '../../../features/market-data/types';
import { useSyncStocksMutation } from '../../../features/stocks/api';
import {
  useSyncTaskLogsQuery,
  useSyncTaskIngestBatchesQuery,
  useSyncTaskQuery,
  useSyncTasksQuery,
  useSyncRunnerStatusQuery,
  useSyncSchedulesQuery,
  useTriggerSyncScheduleMutation,
  useUpdateSyncScheduleMutation,
} from '../../../features/sync-tasks/api';
import type {
  IngestBatch,
  SyncRunnerStatus,
  SyncRunnerTaskRef,
  SyncSchedule,
  SyncTask,
  SyncTaskLog,
  SyncTaskListParams,
} from '../../../features/sync-tasks/types';
import { useSyncTradingCalendarsMutation } from '../../../features/trading-calendars/api';
import { ErrorState } from '../../../shared/components/ErrorState';
import { formatDate, formatDateTime, formatNumber } from '../../../shared/components/formatters';
import { StatusTag } from '../../../shared/components/StatusTag';
import { formatAdjustType, formatLogLevel, formatMarket, formatSourceMode, formatTaskType } from '../../../shared/domain/labels';
import { fadeInUp, useGSAP } from '../../../shared/motion/gsapMotion';
import { SyncConsolePanel as SyncConsolePanelCard } from './components/SyncConsolePanel';
import { SyncOperationTabs as SyncOperationTabsCard } from './components/SyncOperationTabs';
import { TaskDetailDrawer as SyncTaskDetailDrawer } from './components/TaskDetailDrawer';

// ── Extracted sub-modules ──
import {
  DEFAULT_PAGE_SIZE,
  DEFAULT_MARKET,
  SYMBOL_EXAMPLE,
  DEFAULT_DATE_RANGE,
  DEFAULT_MARKET_REPAIR_MAX_SYMBOLS,
  MAX_MARKET_REPAIR_SYMBOLS,
  DEFAULT_MARKET_REPAIR_START_POLICY,
  DEFAULT_ADJUST_TYPE,
  adjustTypeOptions,
  syncFocusLabels,
  statusOptions,
  taskTypeOptions,
  getTaskType,
  normalizeMarketRepairMaxSymbols,
  getRecordsRead,
  getRecordsWritten,
  getErrorMessage,
  getCreatedAt,
  getStartedAt,
  getFinishedAt,
  getTaskCandidateSources,
  getTaskSelectedSource,
  getDataSourceCapabilities,
  getLogPayload,
  getLogTime,
  formatTaskSource,
  renderTaskSourceEvidence,
  formatWatermarkScope,
  formatWatermarkRepairRange,
  isMarketDailyRepairHint,
  getWatermarkRepairFocus,
  getWatermarkRepairSearch,
  formatBatchRange,
  formatIngestBatchRange,
  canTraceBatchToStock,
  getNumericTaskId,
  getRunnerTaskType,
  getRunnerTaskStatus,
  formatPayload,
  compactValues,
  latestLogMessage,
  summarizeTaskBatches,
  formatValueList,
  formatMarketRepairStartPolicy,
  getValidDateRangeOrDefault,
  getSyncOperationTab,
  getScheduleLastTriggeredAt,
  getScheduleInitialValues,
  getScheduleScope,
  getScheduleCron,
  getScheduleTaskType,
  getScheduleNote,
  formatRunnerMode,
  getRunnerStatusLabel,
  getTaskStatusLabel,
  getScheduleCapability,
  canTriggerSchedule,
  type DailyBarsMode,
  type SyncOperationTab,
  type MarketRepairFormValues,
  type TaskCreatedSearch,
  type ScheduleFormValues,
} from './components/utils';
import {
  getSyncEvidenceDecision,
  buildBatchColumns,
  buildWatermarkColumns,
  buildRecentFailureColumns,
  buildColumns,
} from './components/columns';
import { MarketRepairPreviewPanel } from './components/MarketRepairPreviewPanel';
import { RunnerTaskRefItem } from './components/RunnerTaskRefItem';

export function SyncTasksPage() {
  const { message } = AntApp.useApp();
  const pageRef = useRef<HTMLDivElement>(null);
  const stockCardRef = useRef<HTMLDivElement>(null);
  const dailyBarsCardRef = useRef<HTMLDivElement>(null);
  const calendarCardRef = useRef<HTMLDivElement>(null);
  const search = useSearch({ from: '/data-system/sync-tasks' });
  const navigate = useNavigate({ from: '/data-system/sync-tasks' });
  const [dailyBarsMode, setDailyBarsMode] = useState<DailyBarsMode>(
    search.focus === 'daily-bars-market-repair' ? 'market-repair' : 'single',
  );
  const [operationTab, setOperationTab] = useState<SyncOperationTab>(getSyncOperationTab(search.focus));
  const [stockForm] = Form.useForm<{ source?: string; market?: string }>();
  const [dailyBarsForm] = Form.useForm<{
    source?: string;
    market?: string;
    symbol?: string;
    dateRange?: [Dayjs, Dayjs];
    adjustType?: 'none' | 'qfq' | 'hfq';
  }>();
  const [marketRepairForm] = Form.useForm<MarketRepairFormValues>();
  const [calendarForm] = Form.useForm<{
    source?: string;
    market?: string;
    dateRange?: [Dayjs, Dayjs];
  }>();
  const marketRepairDateRange = Form.useWatch('dateRange', marketRepairForm);

  const params = useMemo<SyncTaskListParams>(
    () => ({
      status: search.status ?? '',
      source: search.source ?? '',
      taskType: search.taskType ?? '',
      market: search.market ?? '',
      symbol: search.symbol ?? '',
      startDate: search.startDate ?? '',
      endDate: search.endDate ?? '',
      page: search.page ?? 1,
      pageSize: search.pageSize ?? DEFAULT_PAGE_SIZE,
    }),
    [
      search.endDate,
      search.market,
      search.page,
      search.pageSize,
      search.source,
      search.startDate,
      search.status,
      search.symbol,
      search.taskType,
    ],
  );

  const selectedTaskId = search.taskId;
  const tasksQuery = useSyncTasksQuery(params);
  const dataSourcesQuery = useDataSourcesQuery();
  const overviewMarket = params.market || DEFAULT_MARKET;
  const integrationOverviewQuery = useDatabaseIntegrationOverviewQuery({ market: overviewMarket });
  const runnerStatusQuery = useSyncRunnerStatusQuery();
  const schedulesQuery = useSyncSchedulesQuery();
  const syncStocksMutation = useSyncStocksMutation();
  const syncDailyBarsMutation = useSyncDailyBarsMutation();
  const syncDailyBarsMarketRepairMutation = useSyncDailyBarsMarketRepairMutation();
  const previewDailyBarsMarketRepairMutation = usePreviewDailyBarsMarketRepairMutation();
  const syncCalendarsMutation = useSyncTradingCalendarsMutation();
  const updateScheduleMutation = useUpdateSyncScheduleMutation();
  const triggerScheduleMutation = useTriggerSyncScheduleMutation();
  const taskQuery = useSyncTaskQuery(selectedTaskId, { refetchWhenActive: true });
  const tasks = tasksQuery.data?.items ?? [];
  const schedules = schedulesQuery.data?.items ?? [];
  const selectedTask = taskQuery.data;
  const selectedTaskIsActive = selectedTask?.status === 'pending' || selectedTask?.status === 'running';
  const logsQuery = useSyncTaskLogsQuery(selectedTaskId, { active: selectedTaskIsActive });
  const batchesQuery = useSyncTaskIngestBatchesQuery(selectedTaskId, { active: selectedTaskIsActive });
  const logs = logsQuery.data?.items ?? [];
  const batches = batchesQuery.data?.items ?? [];
  const integrationOverview = integrationOverviewQuery.data;
  const coverageSummary = integrationOverview?.coverage_summary;
  const watermarks = integrationOverview?.sync_watermarks ?? [];
  const failedBatches = useMemo(
    () => (integrationOverview?.recent_batches ?? []).filter((batch) => batch.status === 'failed').slice(0, 5),
    [integrationOverview?.recent_batches],
  );
  const openTaskDetail = useCallback(
    (taskId: number) => {
      void navigate({
        search: {
          status: params.status || undefined,
          source: params.source || undefined,
          taskType: params.taskType || undefined,
          market: params.market || undefined,
          symbol: params.symbol || undefined,
          startDate: params.startDate || undefined,
          endDate: params.endDate || undefined,
          page: params.page,
          pageSize: params.pageSize,
          taskId,
        },
      });
    },
    [
      navigate,
      params.endDate,
      params.market,
      params.page,
      params.pageSize,
      params.source,
      params.startDate,
      params.status,
      params.symbol,
      params.taskType,
    ],
  );
  const batchColumns = useMemo(() => buildBatchColumns(), []);
  const watermarkColumns = useMemo(() => buildWatermarkColumns(coverageSummary), [coverageSummary]);
  const recentFailureColumns = useMemo(
    () => buildRecentFailureColumns(openTaskDetail),
    [openTaskDetail],
  );
  const runningCount = tasks.filter((task) => task.status === 'pending' || task.status === 'running').length;
  const failedCount = tasks.filter((task) => task.status === 'failed').length;
  const dataSources = dataSourcesQuery.data ?? [];
  const sourceOptionsForCapability = (capability: 'stock_list' | 'daily_bars' | 'calendars') => [
    { label: '自动选择（按优先级）', value: 'auto' },
    ...dataSources
      .filter((source) => source.enabled && getDataSourceCapabilities(source)[capability])
      .map((source) => ({
        label: `${source.name} (${source.code})`,
        value: source.code,
      })),
  ];
  const stockSourceOptions = useMemo(() => sourceOptionsForCapability('stock_list'), [dataSources]);
  const dailyBarsSourceOptions = useMemo(() => sourceOptionsForCapability('daily_bars'), [dataSources]);
  const calendarSourceOptions = useMemo(() => sourceOptionsForCapability('calendars'), [dataSources]);
  const isCreatingTask =
    syncStocksMutation.isPending ||
    syncDailyBarsMutation.isPending ||
    syncDailyBarsMarketRepairMutation.isPending ||
    syncCalendarsMutation.isPending;
  const focusedSyncLabel = search.focus ? syncFocusLabels[search.focus] : undefined;
  const marketRepairDateRangeLabel = useMemo(() => {
    const [startDate, endDate] = marketRepairDateRange ?? [];
    if (!startDate?.isValid() || !endDate?.isValid()) {
      return undefined;
    }
    return `${formatDate(startDate.format('YYYY-MM-DD'))} ~ ${formatDate(endDate.format('YYYY-MM-DD'))}`;
  }, [marketRepairDateRange]);
  const columns = useMemo(
    () =>
      buildColumns((task) => {
        const taskId = Number(task.id);
        if (Number.isFinite(taskId)) {
          openTaskDetail(taskId);
        }
      }),
    [openTaskDetail],
  );

  useGSAP(
    () => {
      const root = pageRef.current;
      if (!root) {
        return;
      }

      fadeInUp(root.querySelectorAll('.sync-console-panel, .sync-operations-card, .sync-tracking-card'), {
        stagger: 0.05,
        y: 8,
      });
    },
    { scope: pageRef },
  );

  useEffect(() => {
    setOperationTab(getSyncOperationTab(search.focus));

    const targetRef =
      search.focus === 'stock-list'
        ? stockCardRef
        : search.focus === 'daily-bars' || search.focus === 'daily-bars-market-repair'
          ? dailyBarsCardRef
          : search.focus === 'calendars'
            ? calendarCardRef
            : null;

    if (!targetRef) {
      return;
    }

    window.requestAnimationFrame(() => {
      targetRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }, [search.focus]);

  useEffect(() => {
    if (search.focus === 'daily-bars-market-repair') {
      setDailyBarsMode('market-repair');
    }
    if (search.focus === 'daily-bars') {
      setDailyBarsMode('single');
    }

    if (search.focus === 'daily-bars') {
      const startDate = search.startDate ? dayjs(search.startDate) : undefined;
      const endDate = search.endDate ? dayjs(search.endDate) : undefined;
      dailyBarsForm.setFieldsValue({
        source: search.syncSource || 'auto',
        market: search.market || DEFAULT_MARKET,
        symbol: search.symbol ?? '',
        dateRange: startDate?.isValid() && endDate?.isValid() ? [startDate, endDate] : undefined,
        adjustType: DEFAULT_ADJUST_TYPE,
      });
    }

    if (search.focus === 'daily-bars-market-repair') {
      const startDate = search.startDate ? dayjs(search.startDate) : undefined;
      const endDate = search.endDate ? dayjs(search.endDate) : undefined;
      marketRepairForm.setFieldsValue({
        source: search.syncSource || 'auto',
        market: search.market || DEFAULT_MARKET,
        dateRange: getValidDateRangeOrDefault(startDate, endDate),
        maxSymbols: normalizeMarketRepairMaxSymbols(search.maxSymbols),
        startPolicy: DEFAULT_MARKET_REPAIR_START_POLICY,
        adjustType: DEFAULT_ADJUST_TYPE,
      });
    }

    if (search.focus === 'calendars') {
      const startDate = search.startDate ? dayjs(search.startDate) : undefined;
      const endDate = search.endDate ? dayjs(search.endDate) : undefined;
      calendarForm.setFieldsValue({
        source: search.syncSource || 'auto',
        market: search.market || DEFAULT_MARKET,
        dateRange: startDate?.isValid() && endDate?.isValid() ? [startDate, endDate] : undefined,
      });
    }

    if (search.focus === 'stock-list') {
      stockForm.setFieldsValue({
        source: search.syncSource || 'auto',
        market: search.market || DEFAULT_MARKET,
      });
    }
  }, [
    calendarForm,
    dailyBarsForm,
    marketRepairForm,
    search.endDate,
    search.focus,
    search.market,
    search.maxSymbols,
    search.startDate,
    search.symbol,
    search.syncSource,
    stockForm,
  ]);

  const closeDrawer = () => {
    void navigate({
      search: {
        status: params.status || undefined,
        source: params.source || undefined,
        taskType: params.taskType || undefined,
        market: params.market || undefined,
        symbol: params.symbol || undefined,
        startDate: params.startDate || undefined,
        endDate: params.endDate || undefined,
        page: params.page,
        pageSize: params.pageSize,
      },
    });
  };

  const refreshTasks = () => {
    void tasksQuery.refetch();
    void integrationOverviewQuery.refetch();
    void runnerStatusQuery.refetch();
    void schedulesQuery.refetch();
  };

  const notifyTaskCreated = (
    label: string,
    task: SyncTask | undefined,
    nextSearch?: Partial<TaskCreatedSearch>,
  ) => {
    const suffix = task?.id ? ` #${task.id}` : '';
    const taskId = getNumericTaskId(task?.id);
    void message.success(
      taskId
        ? `${label}同步任务已创建并入队${suffix}，已打开任务追踪`
        : `${label}同步任务已创建并入队${suffix}，等待 worker 执行`,
    );
    refreshTasks();
    if (taskId) {
      void navigate({
        search: {
          status: params.status || undefined,
          source: params.source || undefined,
          taskType: params.taskType || undefined,
          market: params.market || undefined,
          symbol: params.symbol || undefined,
          startDate: params.startDate || undefined,
          endDate: params.endDate || undefined,
          page: 1,
          pageSize: params.pageSize,
          ...nextSearch,
          taskId,
        },
      });
    }
  };

  const handleStockSync = (values: { source?: string; market?: string }) => {
    syncStocksMutation.mutate(
      {
        source: values.source || 'auto',
        market: values.market || DEFAULT_MARKET,
      },
      {
        onSuccess: (task) =>
          notifyTaskCreated('股票池', task, {
            focus: 'stock-list',
            market: values.market || DEFAULT_MARKET,
          }),
        onError: (error) => {
          void message.error(error instanceof Error ? error.message : '股票池同步任务创建失败');
        },
      },
    );
  };

  const handleDailyBarsSync = (values: {
    source?: string;
    market?: string;
    symbol?: string;
    dateRange?: [Dayjs, Dayjs];
    adjustType?: 'none' | 'qfq' | 'hfq';
  }) => {
    const [startDate, endDate] = values.dateRange ?? DEFAULT_DATE_RANGE;
    const symbol = values.symbol?.trim();
    if (!symbol) {
      void message.warning('请先填写股票代码');
      return;
    }

    syncDailyBarsMutation.mutate(
      {
        source: values.source || 'auto',
        market: values.market || DEFAULT_MARKET,
        symbol,
        start_date: startDate.format('YYYY-MM-DD'),
        end_date: endDate.format('YYYY-MM-DD'),
        adjust_type: values.adjustType || DEFAULT_ADJUST_TYPE,
      },
      {
        onSuccess: (task) =>
          notifyTaskCreated('日线行情', task, {
            focus: 'daily-bars',
            taskType: 'daily_bars',
            market: values.market || DEFAULT_MARKET,
            symbol,
            startDate: startDate.format('YYYY-MM-DD'),
            endDate: endDate.format('YYYY-MM-DD'),
          }),
        onError: (error) => {
          void message.error(error instanceof Error ? error.message : '日线行情同步任务创建失败');
        },
      },
    );
  };

  const handleMarketDailyBarsRepair = (values: MarketRepairFormValues) => {
    const [startDate, endDate] = values.dateRange ?? DEFAULT_DATE_RANGE;
    const startPolicy = values.startPolicy || DEFAULT_MARKET_REPAIR_START_POLICY;
    syncDailyBarsMarketRepairMutation.mutate(
      {
        source: values.source || 'auto',
        market: values.market || DEFAULT_MARKET,
        start_date: startDate.format('YYYY-MM-DD'),
        end_date: endDate.format('YYYY-MM-DD'),
        max_symbols: normalizeMarketRepairMaxSymbols(values.maxSymbols),
        start_policy: startPolicy,
        adjust_type: values.adjustType || DEFAULT_ADJUST_TYPE,
      },
      {
        onSuccess: (task) =>
          notifyTaskCreated('市场级日线缺口补齐', task, {
            focus: 'daily-bars-market-repair',
            taskType: 'daily_bars_market_repair',
            market: values.market || DEFAULT_MARKET,
            symbol: undefined,
            startDate: startDate.format('YYYY-MM-DD'),
            endDate: endDate.format('YYYY-MM-DD'),
          }),
        onError: (error) => {
          void message.error(error instanceof Error ? error.message : '市场级日线缺口补齐任务创建失败');
        },
      },
    );
  };

  const handleMarketDailyBarsRepairPreview = async () => {
    try {
      const values = await marketRepairForm.validateFields();
      const [startDate, endDate] = values.dateRange ?? DEFAULT_DATE_RANGE;
      const startPolicy = values.startPolicy || DEFAULT_MARKET_REPAIR_START_POLICY;
      previewDailyBarsMarketRepairMutation.mutate(
        {
          source: values.source || 'auto',
          market: values.market || DEFAULT_MARKET,
          start_date: startDate.format('YYYY-MM-DD'),
          end_date: endDate.format('YYYY-MM-DD'),
          max_symbols: normalizeMarketRepairMaxSymbols(values.maxSymbols),
          start_policy: startPolicy,
          adjust_type: values.adjustType || DEFAULT_ADJUST_TYPE,
        },
        {
          onError: (error) => {
            void message.error(error instanceof Error ? error.message : '补齐计划预览失败');
          },
        },
      );
    } catch {
      void message.warning('请先完善市场、日期范围和安全上限');
    }
  };

  const handleCalendarSync = (values: { source?: string; market?: string; dateRange?: [Dayjs, Dayjs] }) => {
    const [startDate, endDate] = values.dateRange ?? DEFAULT_DATE_RANGE;
    syncCalendarsMutation.mutate(
      {
        source: values.source || 'auto',
        market: values.market || DEFAULT_MARKET,
        start_date: startDate.format('YYYY-MM-DD'),
        end_date: endDate.format('YYYY-MM-DD'),
      },
      {
        onSuccess: (task) =>
          notifyTaskCreated('交易日历', task, {
            focus: 'calendars',
            taskType: 'calendars',
            market: values.market || DEFAULT_MARKET,
            startDate: startDate.format('YYYY-MM-DD'),
            endDate: endDate.format('YYYY-MM-DD'),
          }),
        onError: (error) => {
          void message.error(error instanceof Error ? error.message : '交易日历同步任务创建失败');
        },
      },
    );
  };

  const handleScheduleToggle = (schedule: SyncSchedule, enabled: boolean) => {
    updateScheduleMutation.mutate(
      {
        code: schedule.code,
        payload: { enabled },
      },
      {
        onSuccess: () => {
          void message.success(enabled ? '定时规则已启用' : '定时规则已停用');
        },
        onError: (error) => {
          void message.error(error instanceof Error ? error.message : '定时规则更新失败');
        },
      },
    );
  };

  const handleScheduleSave = (schedule: SyncSchedule, values: ScheduleFormValues) => {
    const symbol = values.symbol?.trim();
    updateScheduleMutation.mutate(
      {
        code: schedule.code,
        payload: {
          source: values.source || 'auto',
          market: values.market || DEFAULT_MARKET,
          symbol: symbol || '',
          cron_expression: values.cron_expression?.trim() || getScheduleCron(schedule),
        },
      },
      {
        onSuccess: () => {
          void message.success('定时规则配置已保存');
          refreshTasks();
        },
        onError: (error) => {
          void message.error(error instanceof Error ? error.message : '定时规则配置保存失败');
        },
      },
    );
  };

  const handleScheduleTrigger = (schedule: SyncSchedule) => {
    const scheduleTaskType = getScheduleTaskType(schedule);
    const scheduleCapability = getScheduleCapability(schedule);
    const focus =
      scheduleTaskType === 'daily_bars_market_repair'
        ? 'daily-bars-market-repair'
        : scheduleCapability === 'daily_bars'
          ? 'daily-bars'
          : scheduleCapability;

    triggerScheduleMutation.mutate(
      { code: schedule.code },
      {
        onSuccess: (task) => {
          notifyTaskCreated('定时规则', task, {
            focus,
            taskType: scheduleTaskType,
            market: schedule.market || DEFAULT_MARKET,
            symbol: schedule.symbol || undefined,
            source: schedule.source || undefined,
          });
        },
        onError: (error) => {
          void message.error(error instanceof Error ? error.message : '定时规则触发失败');
        },
      },
    );
  };

  const stockListPane = (
    <div className={`sync-operation-pane${search.focus === 'stock-list' ? ' is-focused' : ''}`} ref={stockCardRef}>
      <div className="sync-operation-intro">
        <Space size={8}>
          <SyncOutlined />
          <Typography.Title level={5}>股票池</Typography.Title>
        </Space>
        <Typography.Text type="secondary">从启用来源更新 A 股基础列表，作为日线补齐和交易日历校验的入口数据。</Typography.Text>
      </div>
      <Form
        className="sync-operation-form"
        form={stockForm}
        layout="vertical"
        initialValues={{ source: 'auto', market: DEFAULT_MARKET }}
        onFinish={handleStockSync}
      >
        <Row gutter={12}>
          <Col span={12}>
            <Form.Item label="数据源" name="source">
              <Select options={stockSourceOptions} loading={dataSourcesQuery.isFetching} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item label="市场" name="market">
              <Select options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]} />
            </Form.Item>
          </Col>
        </Row>
        <Button type="primary" htmlType="submit" loading={syncStocksMutation.isPending}>
          更新股票池
        </Button>
      </Form>
    </div>
  );

  const dailyBarsPane = (
    <div
      className={`sync-operation-pane sync-operation-pane-primary${
        search.focus === 'daily-bars' || search.focus === 'daily-bars-market-repair' ? ' is-focused' : ''
      }`}
      ref={dailyBarsCardRef}
    >
      <div className="sync-operation-intro">
        <Space size={8}>
          <FileTextOutlined />
          <Typography.Title level={5}>日线同步</Typography.Title>
        </Space>
        <Typography.Text type="secondary">
          {dailyBarsMode === 'single'
            ? '指定单只股票和日期范围，写入标准日线行情与整合批次。'
            : '按市场和日期范围创建受控补齐任务，由后端逐只修复股票-交易日缺口。'}
        </Typography.Text>
      </div>
      <Segmented
        className="sync-operation-mode"
        block
        value={dailyBarsMode}
        onChange={(value) => {
          setDailyBarsMode(value as DailyBarsMode);
          if (value !== 'market-repair') {
            previewDailyBarsMarketRepairMutation.reset();
          }
        }}
        options={[
          { label: '单股日线', value: 'single' },
          { label: '市场缺口补齐', value: 'market-repair' },
        ]}
      />
      {dailyBarsMode === 'single' ? (
        <Form
          className="sync-operation-form"
          form={dailyBarsForm}
          layout="vertical"
          initialValues={{
            source: 'auto',
            market: DEFAULT_MARKET,
            symbol: '',
            dateRange: DEFAULT_DATE_RANGE,
            adjustType: DEFAULT_ADJUST_TYPE,
          }}
          onFinish={handleDailyBarsSync}
        >
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item label="股票代码" name="symbol" rules={[{ required: true, message: '请输入股票代码' }]}>
                <Input placeholder={`例如 ${SYMBOL_EXAMPLE}`} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="市场" name="market">
                <Select options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item label="日期范围" name="dateRange" rules={[{ required: true, message: '请选择日期范围' }]}>
                <DatePicker.RangePicker className="full-width-control" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="数据源" name="source">
                <Select options={dailyBarsSourceOptions} loading={dataSourcesQuery.isFetching} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="复权口径" name="adjustType">
            <Segmented block options={adjustTypeOptions} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={syncDailyBarsMutation.isPending}>
            同步单股日线
          </Button>
        </Form>
      ) : (
        <Form
          className="sync-operation-form"
          form={marketRepairForm}
          layout="vertical"
          initialValues={{
            source: 'auto',
            market: DEFAULT_MARKET,
            dateRange: DEFAULT_DATE_RANGE,
            maxSymbols: DEFAULT_MARKET_REPAIR_MAX_SYMBOLS,
            startPolicy: DEFAULT_MARKET_REPAIR_START_POLICY,
            adjustType: DEFAULT_ADJUST_TYPE,
          }}
          onFinish={handleMarketDailyBarsRepair}
          onValuesChange={() => previewDailyBarsMarketRepairMutation.reset()}
        >
          <Row gutter={12}>
            <Col span={8}>
              <Form.Item label="市场" name="market">
                <Select options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                label="最大股票数"
                name="maxSymbols"
                rules={[{ required: true, message: '请设置本次最多处理的股票数' }]}
              >
                <InputNumber className="full-width-control" min={1} max={MAX_MARKET_REPAIR_SYMBOLS} precision={0} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="数据源" name="source">
                <Select options={dailyBarsSourceOptions} loading={dataSourcesQuery.isFetching} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item label="日期范围" name="dateRange" rules={[{ required: true, message: '请选择日期范围' }]}>
                <DatePicker.RangePicker className="full-width-control" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="补齐起点" name="startPolicy">
                <Segmented
                  block
                  options={[
                    { label: '按填写起始日', value: 'requested_start' },
                    { label: '从上市日', value: 'listing_date' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="复权口径" name="adjustType">
            <Segmented block options={adjustTypeOptions} />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            message="市场级补齐不填写股票代码，建议先预览股票池、开市日和缺口计划，再创建任务。"
            description={
              marketRepairDateRangeLabel
                ? `当前补齐范围 ${marketRepairDateRangeLabel}；选择“从上市日”时，每只股票会从上市日与填写起始日中较晚的一天开始补齐。`
                : undefined
            }
          />
          <MarketRepairPreviewPanel
            preview={previewDailyBarsMarketRepairMutation.data}
            loading={previewDailyBarsMarketRepairMutation.isPending}
            error={previewDailyBarsMarketRepairMutation.error}
          />
          <Space className="market-repair-actions">
            <Button loading={previewDailyBarsMarketRepairMutation.isPending} onClick={() => void handleMarketDailyBarsRepairPreview()}>
              预览补齐计划
            </Button>
            <Button type="primary" htmlType="submit" loading={syncDailyBarsMarketRepairMutation.isPending}>
              创建市场补齐任务
            </Button>
          </Space>
        </Form>
      )}
    </div>
  );

  const calendarPane = (
    <div className={`sync-operation-pane${search.focus === 'calendars' ? ' is-focused' : ''}`} ref={calendarCardRef}>
      <div className="sync-operation-intro">
        <Space size={8}>
          <CalendarOutlined />
          <Typography.Title level={5}>交易日历</Typography.Title>
        </Space>
        <Typography.Text type="secondary">补齐交易日历覆盖，供日线缺口检查和后续调度判断使用。</Typography.Text>
      </div>
      <Form
        className="sync-operation-form"
        form={calendarForm}
        layout="vertical"
        initialValues={{ source: 'auto', market: DEFAULT_MARKET, dateRange: DEFAULT_DATE_RANGE }}
        onFinish={handleCalendarSync}
      >
        <Row gutter={12}>
          <Col span={8}>
            <Form.Item label="市场" name="market">
              <Select options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="日期范围" name="dateRange" rules={[{ required: true, message: '请选择日期范围' }]}>
              <DatePicker.RangePicker className="full-width-control" />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="数据源" name="source">
              <Select options={calendarSourceOptions} loading={dataSourcesQuery.isFetching} />
            </Form.Item>
          </Col>
        </Row>
        <Button type="primary" htmlType="submit" loading={syncCalendarsMutation.isPending}>
          同步交易日历
        </Button>
      </Form>
    </div>
  );

  const schedulePane = schedulesQuery.isError ? (
    <Alert type="error" showIcon message="定时规则加载失败" description="后端同步计划配置接口暂不可用。" />
  ) : (
    <Row gutter={[12, 12]}>
      {schedules.map((schedule) => (
        <Col span={8} key={schedule.code}>
          <div className="sync-schedule-item">
            <div className="sync-schedule-heading">
              <Typography.Text strong>{schedule.name}</Typography.Text>
              <Space size={8}>
                <Tooltip title={canTriggerSchedule(schedule) ? '按当前规则创建一次同步任务' : '请先在配置规则里填写股票代码'}>
                  <Button
                    size="small"
                    icon={<SyncOutlined />}
                    disabled={!canTriggerSchedule(schedule)}
                    loading={triggerScheduleMutation.isPending && triggerScheduleMutation.variables?.code === schedule.code}
                    onClick={() => handleScheduleTrigger(schedule)}
                  >
                    立即触发
                  </Button>
                </Tooltip>
                <Switch
                  size="small"
                  checked={schedule.enabled}
                  checkedChildren="启用"
                  unCheckedChildren="停用"
                  loading={updateScheduleMutation.isPending}
                  onChange={(checked) => handleScheduleToggle(schedule, checked)}
                />
              </Space>
            </div>
            <Typography.Text type="secondary">{getScheduleNote(schedule)}</Typography.Text>
            <div className="sync-schedule-meta">
              <Tag color={schedule.enabled ? 'success' : 'default'}>{schedule.enabled ? '已启用' : '未启用'}</Tag>
              <Tag>{getScheduleCron(schedule)}</Tag>
            </div>
            <Typography.Text type="secondary">{getScheduleScope(schedule)}</Typography.Text>
            <Typography.Text type="secondary">最近触发：{formatDateTime(getScheduleLastTriggeredAt(schedule))}</Typography.Text>
            <Collapse
              ghost
              size="small"
              className="sync-schedule-config"
              items={[
                {
                  key: 'config',
                  label: '配置规则',
                  children: (
                    <Form<ScheduleFormValues>
                      layout="vertical"
                      initialValues={getScheduleInitialValues(schedule)}
                      onFinish={(values) => handleScheduleSave(schedule, values)}
                    >
                      <Form.Item label="数据源" name="source">
                        <Select options={sourceOptionsForCapability(getScheduleCapability(schedule))} loading={dataSourcesQuery.isFetching} />
                      </Form.Item>
                      <Row gutter={8}>
                        <Col span={12}>
                          <Form.Item label="市场" name="market">
                            <Select options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]} />
                          </Form.Item>
                        </Col>
                        <Col span={12}>
                          <Form.Item
                            label="股票代码"
                            name="symbol"
                            tooltip={
                              getScheduleTaskType(schedule) === 'daily_bars'
                                ? '第一阶段日线规则需要单只股票代码，后续再扩展全市场批量。'
                                : '股票池和交易日历规则可留空。'
                            }
                          >
                            <Input placeholder={getScheduleTaskType(schedule) === 'daily_bars' ? SYMBOL_EXAMPLE : '可留空'} />
                          </Form.Item>
                        </Col>
                      </Row>
                      <Form.Item label="Cron 表达式" name="cron_expression" rules={[{ required: true, message: '请输入 cron 表达式' }]}>
                        <Input placeholder="30 18 * * 1-5" />
                      </Form.Item>
                      <Button size="small" type="primary" htmlType="submit" loading={updateScheduleMutation.isPending} block>
                        保存配置
                      </Button>
                    </Form>
                  ),
                },
              ]}
            />
          </div>
        </Col>
      ))}
      {schedules.length === 0 ? (
        <Col span={24}>
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无定时规则" />
        </Col>
      ) : null}
    </Row>
  );

  const watermarkPane = (
    <Row gutter={[16, 16]} align="stretch" className="sync-watermark-row">
      <Col span={15}>
        {integrationOverviewQuery.isError ? (
          <Alert type="error" showIcon message="同步水位线加载失败" description="后端数据整合总览接口暂不可用。" />
        ) : (
          <Table<SyncWatermark>
            rowKey={(record) => `${record.dataset_name}-${record.source}-${record.market}-${record.symbol}-${record.batch_id}`}
            columns={watermarkColumns}
            dataSource={watermarks}
            loading={integrationOverviewQuery.isFetching}
            pagination={false}
            size="small"
            scroll={{ x: 1340 }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无成功水位线" /> }}
          />
        )}
      </Col>
      <Col span={9}>
        {integrationOverviewQuery.isError ? (
          <Alert type="error" showIcon message="失败批次加载失败" />
        ) : (
          <Table<RecentIngestBatch>
            rowKey={(record) => String(record.id)}
            columns={recentFailureColumns}
            dataSource={failedBatches}
            loading={integrationOverviewQuery.isFetching}
            pagination={false}
            size="small"
            scroll={{ x: 720 }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无失败批次" /> }}
          />
        )}
      </Col>
    </Row>
  );

  const recentTasksPane = (
    <>
      <Form
        key={[params.status, params.source, params.taskType, params.market, params.symbol, params.startDate, params.endDate].join('|')}
        className="stock-filters sync-task-filters"
        layout="inline"
        initialValues={{
          status: params.status,
          source: params.source,
          taskType: params.taskType,
          market: params.market,
          symbol: params.symbol,
          dateRange: params.startDate && params.endDate ? [dayjs(params.startDate), dayjs(params.endDate)] : undefined,
        }}
        onFinish={(values: {
          status?: string;
          source?: string;
          taskType?: string;
          market?: string;
          symbol?: string;
          dateRange?: [Dayjs, Dayjs];
        }) => {
          const [startDate, endDate] = values.dateRange ?? [];
          void navigate({
            search: {
              status: values.status || undefined,
              source: values.source?.trim() || undefined,
              taskType: values.taskType || undefined,
              market: values.market || undefined,
              symbol: values.symbol?.trim() || undefined,
              startDate: startDate?.format('YYYY-MM-DD'),
              endDate: endDate?.format('YYYY-MM-DD'),
              page: 1,
              pageSize: params.pageSize,
            },
          });
        }}
      >
        <Form.Item name="status">
          <Select className="filter-select" options={statusOptions} />
        </Form.Item>
        <Form.Item name="taskType">
          <Select className="filter-select" options={taskTypeOptions} />
        </Form.Item>
        <Form.Item name="market">
          <Select
            allowClear
            className="filter-select"
            options={[{ label: '中国 A 股', value: DEFAULT_MARKET }]}
            placeholder="市场"
          />
        </Form.Item>
        <Form.Item name="source" className="filter-keyword">
          <Input allowClear placeholder="数据源，如 akshare" />
        </Form.Item>
        <Form.Item name="symbol" className="filter-keyword">
          <Input allowClear placeholder={`股票代码，如 ${SYMBOL_EXAMPLE}`} />
        </Form.Item>
        <Form.Item name="dateRange">
          <DatePicker.RangePicker className="full-width-control" />
        </Form.Item>
        <Form.Item className="filter-actions">
          <Space wrap>
            <Button type="primary" htmlType="submit">
              查询
            </Button>
            <Button
              onClick={() => {
                void navigate({
                  search: {
                    page: 1,
                    pageSize: params.pageSize,
                  },
                });
              }}
            >
              重置
            </Button>
            <Button icon={<ReloadOutlined />} loading={tasksQuery.isFetching || isCreatingTask} onClick={refreshTasks}>
              刷新
            </Button>
          </Space>
        </Form.Item>
      </Form>

      {tasksQuery.isError ? (
        <ErrorState error={tasksQuery.error} onRetry={() => void tasksQuery.refetch()} />
      ) : (
        <Table<SyncTask>
          className="sync-tasks-table"
          rowKey={(record) => String(record.id)}
          columns={columns}
          dataSource={tasks}
          loading={tasksQuery.isFetching}
          scroll={{ x: 1290 }}
          locale={{
            emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无同步记录" />,
          }}
          pagination={{
            current: params.page,
            pageSize: params.pageSize,
            total: tasksQuery.data?.total ?? 0,
            showSizeChanger: false,
            showTotal: (totalValue, range) => `${range[0]}-${range[1]} / 共 ${totalValue} 条`,
            onChange: (page, pageSize) => {
              void navigate({
                search: {
                  status: params.status || undefined,
                  source: params.source || undefined,
                  taskType: params.taskType || undefined,
                  market: params.market || undefined,
                  symbol: params.symbol || undefined,
                  startDate: params.startDate || undefined,
                  endDate: params.endDate || undefined,
                  page,
                  pageSize,
                  taskId: selectedTaskId,
                },
              });
            },
          }}
        />
      )}
    </>
  );

  const syncOperationItems = [
    { key: 'daily-bars', label: '日线补齐', children: dailyBarsPane },
    { key: 'stock-list', label: '股票池', children: stockListPane },
    { key: 'calendars', label: '交易日历', children: calendarPane },
  ];

  const trackingItems = [
    { key: 'recent', label: '最近记录', children: recentTasksPane },
    { key: 'watermarks', label: '水位线与失败', children: watermarkPane },
    { key: 'schedules', label: '定时规则', children: schedulePane },
  ];

  return (
    <div className="workbench sync-tasks-page" ref={pageRef}>
      <div className="workbench-heading">
        <Space direction="vertical" size={4}>
          <Typography.Title level={3}>同步调度</Typography.Title>
          <Typography.Text type="secondary">手动同步、定时计划、任务状态</Typography.Text>
        </Space>
        <Space>
          <Button icon={<Icons.CheckCircleOutlined />} onClick={() => message.info('正在触发质量检查')}>质量检查</Button>
          <Button icon={<Icons.SendOutlined />} onClick={() => message.info('正在触发新闻抓取')}>抓取新闻</Button>
          <Button icon={<Icons.DatabaseOutlined />} onClick={() => message.success('行业分类已在服务器端自动完成')}>同步行业</Button>
        </Space>
      </div>

      <SyncConsolePanelCard
        total={tasksQuery.data?.total ?? 0}
        runningCount={runningCount}
        failedCount={failedCount}
        status={runnerStatusQuery.data}
        runnerLoading={runnerStatusQuery.isFetching}
        runnerError={runnerStatusQuery.isError ? runnerStatusQuery.error : null}
        overview={integrationOverview}
        watermarks={watermarks}
        failedBatches={failedBatches}
        evidenceLoading={integrationOverviewQuery.isFetching}
        evidenceError={integrationOverviewQuery.isError}
        onRefresh={refreshTasks}
        onOpenTask={openTaskDetail}
        onOpenFailedTask={openTaskDetail}
      />

      {focusedSyncLabel ? (
        <Alert
          className="sync-focus-alert"
          type="info"
          showIcon
          message={`已定位到${focusedSyncLabel}`}
          description={
            search.focus === 'daily-bars'
              ? '第一版日线同步按单只股票创建任务；如从水位线进入且没有股票代码，请先在数据库管理确认缺口范围。'
              : '可直接确认数据源、市场和日期范围后创建同步任务；任务创建后会进入最近同步记录和同步水位线。'
          }
        />
      ) : null}

      <SyncOperationTabsCard
        searchFocus={search.focus}
        activeTab={operationTab}
        onTabChange={(tab) => setOperationTab(tab === 'daily-bars' ? 'daily-bars' : (tab as SyncOperationTab))}
        dailyBarsMode={dailyBarsMode}
        onDailyBarsModeChange={setDailyBarsMode}
        onResetMarketRepairPreview={() => previewDailyBarsMarketRepairMutation.reset()}
        stockCardRef={stockCardRef}
        dailyBarsCardRef={dailyBarsCardRef}
        calendarCardRef={calendarCardRef}
        stockForm={stockForm}
        dailyBarsForm={dailyBarsForm}
        marketRepairForm={marketRepairForm}
        calendarForm={calendarForm}
        stockSourceOptions={stockSourceOptions}
        dailyBarsSourceOptions={dailyBarsSourceOptions}
        calendarSourceOptions={calendarSourceOptions}
        dataSourcesLoading={dataSourcesQuery.isFetching}
        previewDailyBarsMarketRepairData={previewDailyBarsMarketRepairMutation.data}
        previewDailyBarsMarketRepairLoading={previewDailyBarsMarketRepairMutation.isPending}
        previewDailyBarsMarketRepairError={previewDailyBarsMarketRepairMutation.error}
        isCreatingTask={isCreatingTask}
        onStockSync={handleStockSync}
        onDailyBarsSync={handleDailyBarsSync}
        onMarketDailyBarsRepair={handleMarketDailyBarsRepair}
        onMarketDailyBarsRepairPreview={() => void handleMarketDailyBarsRepairPreview()}
        onCalendarSync={handleCalendarSync}
      />

      <Card className="sync-tracking-card stock-detail-panel" title="运行追踪">
        <Tabs defaultActiveKey="recent" items={trackingItems} />
      </Card>
      <SyncTaskDetailDrawer
        taskId={selectedTaskId}
        task={selectedTask}
        batches={batches}
        logs={logs}
        taskLoading={taskQuery.isFetching}
        batchesLoading={batchesQuery.isFetching}
        logsLoading={logsQuery.isFetching}
        taskError={taskQuery.isError}
        batchesError={batchesQuery.isError}
        logsError={logsQuery.isError}
        onClose={closeDrawer}
      />
    </div>
  );
}
