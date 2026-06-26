import { useState, useCallback } from 'react';
import { Button, Card, Progress, Space, Spin, Typography, message, Tag } from 'antd';
import { CloudDownloadOutlined, DatabaseOutlined, ReloadOutlined, StopOutlined, SyncOutlined } from '@ant-design/icons';

const API = '/api/data-pipeline';

interface PipelineStatus {
  jobs: Record<string, { pid: number; status: string }>;
  raw_files: number;
  raw_size_mb: number;
}

interface FetchStatus {
  completed: number;
  failed: number;
  total: number;
  progress_pct: number;
  status: string;
}

async function apiGet<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function apiPost(url: string, body?: Record<string, unknown>): Promise<unknown> {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body ?? {}) });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export function PipelinePage() {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [fetchStatus, setFetchStatus] = useState<FetchStatus | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [s, f] = await Promise.all([apiGet<PipelineStatus>(`${API}/status`), apiGet<FetchStatus>(`${API}/fetch-status`)]);
      setStatus(s);
      setFetchStatus(f);
    } catch {
      message.error('无法连接后端 API');
    } finally {
      setLoading(false);
    }
  }, []);

  const runFetch = useCallback(async () => {
    try {
      await apiPost(`${API}/run-fetch`);
      message.success('全量拉取已启动');
      setTimeout(refresh, 2000);
    } catch {
      message.error('启动失败');
    }
  }, [refresh]);

  const runMerge = useCallback(async () => {
    try {
      await apiPost(`${API}/run-merge`);
      message.success('合并完成');
      refresh();
    } catch {
      message.error('合并失败');
    }
  }, [refresh]);

  const runUpdate = useCallback(async () => {
    try {
      await apiPost(`${API}/run-update`);
      message.success('增量更新已启动');
      setTimeout(refresh, 2000);
    } catch {
      message.error('启动失败');
    }
  }, [refresh]);

  return (
    <div style={{ padding: 24, maxWidth: 720 }}>
      <Typography.Title level={4}><DatabaseOutlined /> 数据管线管理</Typography.Title>
      <Typography.Paragraph type="secondary">
        全量拉取 A 股日K线 → 合并到银层 → 每日增量更新
      </Typography.Paragraph>

      <Card title="管线状态" extra={<Button icon={<ReloadOutlined />} size="small" onClick={refresh} loading={loading}>刷新</Button>}>
        {status === null ? (
          <Spin />
        ) : (
          <Space direction="vertical" style={{ width: '100%' }}>
            <div><Tag color={Object.values(status.jobs).some(j => j.status === 'running') ? 'processing' : 'default'}>
              运行中: {Object.entries(status.jobs).filter(([, j]) => j.status === 'running').length} 个任务
            </Tag></div>
            <div>原始数据: {status.raw_files} 文件 ({status.raw_size_mb} MB)</div>
            {fetchStatus && (
              <>
                <div>拉取进度: {fetchStatus.completed}/{fetchStatus.total} ({fetchStatus.progress_pct}%)</div>
                <Progress percent={fetchStatus.progress_pct} status={fetchStatus.status === 'finished' ? 'success' : 'active'} />
                <div>失败: {fetchStatus.failed} 只</div>
              </>
            )}
          </Space>
        )}
      </Card>

      <div style={{ height: 16 }} />

      <Card title="操作">
        <Space wrap>
          <Button type="primary" icon={<CloudDownloadOutlined />} onClick={runFetch}>全量拉取</Button>
          <Button icon={<SyncOutlined />} onClick={runMerge}>合并到银层</Button>
          <Button icon={<ReloadOutlined />} onClick={runUpdate}>增量更新</Button>
        </Space>
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, fontSize: 12 }}>
          全量拉取约 25 分钟 | 增量更新约 3 分钟 | 合并约 10 秒
        </Typography.Paragraph>
      </Card>
    </div>
  );
}

export default PipelinePage;
