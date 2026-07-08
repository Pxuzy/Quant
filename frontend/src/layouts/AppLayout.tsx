import { Suspense, type ReactNode } from 'react';
import { Outlet, useLocation, useNavigate } from '@tanstack/react-router';
import * as Icons from '@ant-design/icons';
import { Button, Layout, Menu, Space, Typography } from 'antd';
import { useThemeMode } from '../app/ThemeProvider';

type NavItem = {
  key: string;
  label: string;
  path: string;
  icon: ReactNode;
  aliases?: string[];
  group?: 'workbench' | 'admin';
};

const NAV_ITEMS: NavItem[] = [
  // 工作台
  { key: 'dashboard', label: '仪表盘', path: '/dashboard', icon: <Icons.DashboardOutlined />, group: 'workbench' },
  { key: 'news', label: '新闻', path: '/news', icon: <Icons.ReadOutlined />, group: 'workbench' },
  { key: 'data-sources', label: '数据源', path: '/data-system/data-sources', icon: <Icons.ApiOutlined />, group: 'workbench' },
  // 数据后台
  { key: 'alerts', label: '异常中心', path: '/data-system/alerts', icon: <Icons.WarningOutlined />, group: 'admin' },
  { key: 'stocks', label: '股票池', path: '/data-system/stocks', icon: <Icons.TableOutlined />, group: 'admin' },
  { key: 'sync-tasks', label: '同步调度', path: '/data-system/sync-tasks', icon: <Icons.CloudSyncOutlined />, group: 'admin' },
  { key: 'database', label: '数据库', path: '/data-system/database', icon: <Icons.AreaChartOutlined />, aliases: ['/data-system/data-quality', '/data-system/datasets', '/data-system/trading-calendars'], group: 'admin' },
];

// ponytail: 用循环替代逐条 if，新增路由只需在 NAV_ITEMS 添加一行，无需改 findNavItem
function findNavItem(pathname: string) {
  // 精确匹配工作台路由
  const exact = NAV_ITEMS.find((i) => i.group === 'workbench' && pathname === i.path);
  if (exact) return exact;
  // 前缀匹配（/stock/xxx 等动态路由）
  const prefix = NAV_ITEMS.find((i) => i.group === 'workbench' && pathname.startsWith(i.path + '/'));
  if (prefix) return prefix;
  // 数据后台路由
  return NAV_ITEMS.find((i) => i.group === 'admin' && (pathname.startsWith(i.path) || i.aliases?.some((a) => pathname.startsWith(a)))) ?? NAV_ITEMS[0];
}

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { mode, toggleMode } = useThemeMode();
  const pathname = location?.pathname || '/';
  const current = findNavItem(pathname);

  return (
    <Layout className="app-shell">
      <Layout.Sider className="app-sider" style={{ background: 'var(--app-surface)' }} width={224}>
        <div className="brand">
          <div className="brand-mark"><Icons.LineChartOutlined /></div>
          <div>
            <Typography.Text className="brand-name">Quant</Typography.Text>
            <Typography.Text className="brand-subtitle">股票数据库工作台</Typography.Text>
          </div>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[current.key]}
          theme={mode}
          onClick={({ key }) => {
            const target = NAV_ITEMS.find((i) => i.key === key);
            if (target) void navigate({ to: target.path });
          }}
          items={[
            ...NAV_ITEMS.filter((i) => i.group === 'workbench').map((i) => ({ key: i.key, icon: i.icon, label: i.label })),
            { type: 'divider' as const, key: 'divider' },
            ...NAV_ITEMS.filter((i) => i.group === 'admin').map((i) => ({ key: i.key, icon: i.icon, label: i.label })),
          ]}
        />
      </Layout.Sider>
      <Layout>
        <Layout.Header className="app-header">
          <Space className="header-left" size={12}>
            <Space className="header-crumb" size={10}>
              <Typography.Text strong>{current.label}</Typography.Text>
            </Space>
          </Space>
          <Space className="header-right" size={10}>
            <Button className="header-sync-button" type="primary" icon={<Icons.CloudSyncOutlined />}
              onClick={() => void navigate({ to: '/data-system/sync-tasks', search: { focus: 'daily-bars-market-repair' } })}>
              补日线
            </Button>
            <Button className="theme-toggle" icon={mode === 'dark' ? <Icons.SunOutlined /> : <Icons.MoonOutlined />} onClick={toggleMode}>
              {mode === 'dark' ? '浅色' : '深色'}
            </Button>
          </Space>
        </Layout.Header>
        <Layout.Content className="app-content">
          <Suspense fallback={<div className="route-loading">加载中...</div>}>
            <Outlet />
          </Suspense>
        </Layout.Content>
      </Layout>
    </Layout>
  );
}
