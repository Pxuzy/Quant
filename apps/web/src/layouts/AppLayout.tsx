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
} from '@ant-design/icons';
import { Button, Layout, Menu, Space, Typography } from 'antd';
import { useThemeMode } from '../app/ThemeProvider';

type NavItem = {
  key: string;
  label: string;
  path:
    | '/data-system/overview'
    | '/data-system/numeric-summary'
    | '/data-system/news-summary'
    | '/data-system/stocks'
    | '/data-system/sync-tasks'
    | '/data-system/database'
    | '/data-system/data-sources';
  icon: ReactNode;
  aliases?: string[];
};

const NAV_ITEMS: NavItem[] = [
  { key: 'overview', label: '总控台', path: '/data-system/overview', icon: <DashboardOutlined /> },
  { key: 'news-summary', label: '新闻汇总', path: '/data-system/news-summary', icon: <ReadOutlined /> },
  { key: 'numeric-summary', label: '数值数据', path: '/data-system/numeric-summary', icon: <BarChartOutlined />, aliases: ['/data-system/market-data'] },
  { key: 'stocks', label: '股票池', path: '/data-system/stocks', icon: <TableOutlined /> },
  { key: 'data-sources', label: '数据源管理', path: '/data-system/data-sources', icon: <ApiOutlined /> },
  { key: 'sync-tasks', label: '同步调度', path: '/data-system/sync-tasks', icon: <SyncOutlined /> },
  { key: 'database', label: '数据库管理', path: '/data-system/database', icon: <AreaChartOutlined />, aliases: ['/data-system/data-quality', '/data-system/datasets', '/data-system/trading-calendars'] },
];

function findNavItem(pathname: string) {
  return (
    NAV_ITEMS.find((item) => pathname.startsWith(item.path) || item.aliases?.some((alias) => pathname.startsWith(alias))) ??
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
          items={NAV_ITEMS.map((item) => ({
            key: item.key,
            icon: item.icon,
            label: item.label,
          }))}
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
