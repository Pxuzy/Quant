import { Suspense, type ReactNode, useState } from 'react';
import { Outlet, useLocation, useNavigate } from '@tanstack/react-router';
import * as Icons from '@ant-design/icons';
import { Layout, Tooltip } from 'antd';
import { useThemeMode } from '../app/ThemeProvider';
import { StatusBar } from './StatusBar';
import { RightPanel } from './RightPanel';

type NavItem = {
  key: string;
  label: string;
  path: string;
  icon: ReactNode;
};

const NAV_ITEMS: NavItem[] = [
  { key: 'dashboard',  label: '仪表盘',  path: '/dashboard',  icon: <Icons.DashboardOutlined /> },
  { key: 'watchlist',  label: '自选股',   path: '/watchlist',  icon: <Icons.StarOutlined /> },
  { key: 'stocks',     label: '股票池',   path: '/stocks',     icon: <Icons.TableOutlined /> },
  { key: 'news',       label: '新闻',     path: '/news',       icon: <Icons.ReadOutlined /> },
  { key: 'sync-tasks', label: '同步任务',  path: '/sync-tasks', icon: <Icons.CloudSyncOutlined /> },
  { key: 'data-sources', label: '数据源', path: '/data-sources', icon: <Icons.ApiOutlined /> },
  { key: 'database',   label: '数据库',   path: '/database',   icon: <Icons.DatabaseOutlined /> },
];

function findCurrent(pathname: string) {
  for (const item of NAV_ITEMS) {
    if (pathname === item.path || pathname.startsWith(item.path + '/')) return item;
  }
  return NAV_ITEMS[0];
}

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { toggleMode } = useThemeMode();
  const [rightOpen, setRightOpen] = useState(true);
  const current = findCurrent(location?.pathname || '/');

  return (
    <Layout className="app-shell">
      {/* ═══ 左侧窄图标栏 ═══ */}
      <nav className="nav-bar">
        <div className="nav-brand" onClick={() => navigate({ to: '/dashboard' })}>
          <Icons.LineChartOutlined style={{ fontSize: 22, color: '#2962ff' }} />
        </div>
        <div className="nav-items">
          {NAV_ITEMS.map((item) => (
            <Tooltip key={item.key} title={item.label} placement="right">
              <div
                className={`nav-item ${current.key === item.key ? 'active' : ''}`}
                onClick={() => navigate({ to: item.path })}
              >
                {item.icon}
              </div>
            </Tooltip>
          ))}
        </div>
        <div className="nav-footer">
          <Tooltip title="切换主题" placement="right">
            <div className="nav-item" onClick={toggleMode}>
              <Icons.SwapOutlined />
            </div>
          </Tooltip>
        </div>
      </nav>

      {/* ═══ 中间主区 ═══ */}
      <Layout className="main-area">
        <Layout.Content className="app-content">
          <Suspense fallback={<div className="route-loading">加载中...</div>}>
            <Outlet />
          </Suspense>
        </Layout.Content>
        <StatusBar />
      </Layout>

      {/* ═══ 右侧面板 ═══ */}
      {rightOpen && (
        <aside className="right-panel">
          <RightPanel />
        </aside>
      )}
      <div className="right-toggle" onClick={() => setRightOpen(!rightOpen)}>
        {rightOpen ? <Icons.RightOutlined /> : <Icons.LeftOutlined />}
      </div>
    </Layout>
  );
}
