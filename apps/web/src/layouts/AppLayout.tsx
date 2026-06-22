import { Suspense } from 'react';
import type { ReactNode } from 'react';
import { Outlet, useLocation, useNavigate } from '@tanstack/react-router';
import {
  ApiOutlined,
  AreaChartOutlined,
  BarChartOutlined,
  CloudSyncOutlined,
  DashboardOutlined,
  LineChartOutlined,
  MoonOutlined,
  ReadOutlined,
  SunOutlined,
  SyncOutlined,
  TableOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Button, Layout, Menu, Space, Typography } from 'antd';
import { useThemeMode } from '../app/ThemeProvider';

type NavItem = {
  key: string;
  label: string;
  path:
    | '/dashboard'
    | '/stock/$code'
    | '/news'
    | '/data-system'
    | '/data-system/pipeline'
    | '/data-system/alerts'
    | '/data-system/numeric-summary'
    | '/data-system/news-summary'
    | '/data-system/stocks'
    | '/data-system/sync-tasks'
    | '/data-system/database'
    | '/data-system/data-sources';
  icon: ReactNode;
  aliases?: string[];
  group?: 'workbench' | 'admin';
};

const NAV_ITEMS: NavItem[] = [
  // 工作台
  { key: 'dashboard', label: '仪表盘', path: '/dashboard', icon: <DashboardOutlined />, group: 'workbench' },
  { key: 'news', label: '新闻', path: '/news', icon: <ReadOutlined />, group: 'workbench' },
  { key: 'data-sources', label: '数据源', path: '/data-sources', icon: <ApiOutlined />, group: 'workbench' },
  // 数据后台
  { key: 'overview', label: '状态总览', path: '/data-system', icon: <DashboardOutlined />, group: 'admin' },
  { key: 'pipeline', label: '数据链路', path: '/data-system/pipeline', icon: <SyncOutlined />, group: 'admin' },
  { key: 'alerts', label: '异常中心', path: '/data-system/alerts', icon: <WarningOutlined />, group: 'admin' },
  { key: 'stocks', label: '股票池', path: '/data-system/stocks', icon: <TableOutlined />, group: 'admin' },
  { key: 'data-sources-admin', label: '数据源(后台)', path: '/data-system/data-sources', icon: <ApiOutlined />, group: 'admin' },
  { key: 'sync-tasks', label: '同步调度', path: '/data-system/sync-tasks', icon: <CloudSyncOutlined />, group: 'admin' },
  { key: 'database', label: '数据库管理', path: '/data-system/database', icon: <AreaChartOutlined />, aliases: ['/data-system/data-quality', '/data-system/datasets', '/data-system/trading-calendars'], group: 'admin' },
];

function findNavItem(pathname: string) {
  // 精确匹配 /dashboard
  if (pathname === '/dashboard') return NAV_ITEMS.find((i) => i.key === 'dashboard')!;
  // 匹配 /stock/xxx
  if (pathname.startsWith('/stock/')) return NAV_ITEMS.find((i) => i.key === 'dashboard')!;
  // 匹配 /news
  if (pathname === '/news') return NAV_ITEMS.find((i) => i.key === 'news')!;
  // 匹配 /data-sources（工作台层）
  if (pathname === '/data-sources') return NAV_ITEMS.find((i) => i.key === 'data-sources')!;
  // 匹配 /data-system/*
  return (
    NAV_ITEMS.find((item) => item.group === 'admin' && (pathname.startsWith(item.path) || item.aliases?.some((alias) => pathname.startsWith(alias)))) ??
    NAV_ITEMS[0]
  );
}

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { mode, toggleMode } = useThemeMode();
  const currentNavItem = findNavItem(location.pathname);

  return (
    <Layout className="app-shell">
      <Layout.Sider className="app-sider" width={224}>
        <div className="brand">
          <div className="brand-mark">
            <LineChartOutlined />
          </div>
          <div>
            <Typography.Text className="brand-name">Quant</Typography.Text>
            <Typography.Text className="brand-subtitle">股票数据库工作台</Typography.Text>
          </div>
        </div>

        <Menu
          mode="inline"
          selectedKeys={[currentNavItem.key]}
          onClick={({ key }) => {
            const target = NAV_ITEMS.find((item) => item.key === key);
            if (target) {
              void navigate({ to: target.path });
            }
          }}
          items={[
            ...NAV_ITEMS.filter((i) => i.group === 'workbench').map((item) => ({
              key: item.key,
              icon: item.icon,
              label: item.label,
            })),
            { type: 'divider' as const, key: 'divider' },
            ...NAV_ITEMS.filter((i) => i.group === 'admin').map((item) => ({
              key: item.key,
              icon: item.icon,
              label: item.label,
            })),
          ]}
        />
      </Layout.Sider>

      <Layout>
        <Layout.Header className="app-header">
          <Space className="header-left" size={12}>
            <Space className="header-crumb" size={10}>
              <Typography.Text strong>{currentNavItem.label}</Typography.Text>
              <Typography.Text type="secondary">A_SHARE</Typography.Text>
            </Space>
          </Space>

          <Space className="header-right" size={10}>
            <Button
              className="header-sync-button"
              type="primary"
              icon={<CloudSyncOutlined />}
              onClick={() =>
                void navigate({
                  to: '/data-system/sync-tasks',
                  search: { focus: 'daily-bars-market-repair' },
                })
              }
            >
              补日线
            </Button>
            <Button
              className="theme-toggle"
              icon={mode === 'dark' ? <SunOutlined /> : <MoonOutlined />}
              onClick={toggleMode}
            >
              {mode === 'dark' ? '浅色' : '深色'}
            </Button>
          </Space>
        </Layout.Header>

        <Layout.Content className="app-content">
          <Suspense fallback={<div className="route-loading">页面加载中...</div>}>
            <Outlet />
          </Suspense>
        </Layout.Content>
      </Layout>
    </Layout>
  );
}
