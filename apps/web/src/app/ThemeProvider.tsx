import { ConfigProvider, theme as antdTheme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import type { ReactNode } from 'react';
import { createContext, useContext, useEffect, useMemo, useState } from 'react';

type ThemeMode = 'dark' | 'light';

type ThemeContextValue = {
  mode: ThemeMode;
  toggleMode: () => void;
  setMode: (mode: ThemeMode) => void;
};

const STORAGE_KEY = 'quant-ui-theme-mode';
const THEME_VERSION_KEY = 'quant-ui-theme-version';
const THEME_VERSION = 'light-command-v1';

const ThemeContext = createContext<ThemeContextValue | null>(null);

function getInitialMode(): ThemeMode {
  if (typeof window === 'undefined') {
    return 'light';
  }

  const storedVersion = window.localStorage.getItem(THEME_VERSION_KEY);
  if (storedVersion !== THEME_VERSION) {
    window.localStorage.setItem(THEME_VERSION_KEY, THEME_VERSION);
    window.localStorage.setItem(STORAGE_KEY, 'light');
    return 'light';
  }

  const storedMode = window.localStorage.getItem(STORAGE_KEY);
  if (storedMode === 'dark' || storedMode === 'light') {
    return storedMode;
  }

  return 'light';
}

type AppThemeProviderProps = {
  children: ReactNode;
};

export function AppThemeProvider({ children }: AppThemeProviderProps) {
  const [mode, setMode] = useState<ThemeMode>(getInitialMode);

  useEffect(() => {
    document.documentElement.dataset.quantTheme = mode;
    document.documentElement.style.colorScheme = mode;
    window.localStorage.setItem(STORAGE_KEY, mode);
    window.localStorage.setItem(THEME_VERSION_KEY, THEME_VERSION);
  }, [mode]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      mode,
      setMode,
      toggleMode: () => setMode((currentMode) => (currentMode === 'dark' ? 'light' : 'dark')),
    }),
    [mode],
  );

  return (
    <ThemeContext.Provider value={value}>
      <ConfigProvider
        locale={zhCN}
        theme={{
          algorithm: mode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
          token: {
            colorPrimary: mode === 'dark' ? '#2f8cff' : '#2f6f9f',
            colorInfo: mode === 'dark' ? '#2f8cff' : '#2f6f9f',
            colorSuccess: mode === 'dark' ? '#2bd982' : '#1f8f59',
            colorWarning: mode === 'dark' ? '#f5b642' : '#b7791f',
            colorError: mode === 'dark' ? '#ff5148' : '#c24132',
            colorBgBase: mode === 'dark' ? '#071018' : '#f3f6fa',
            colorTextBase: mode === 'dark' ? '#dce7f5' : '#172033',
            borderRadius: 6,
            fontFamily:
              '"DIN Alternate", "Bahnschrift", "SF Pro Text", "Segoe UI", ui-sans-serif, system-ui, sans-serif',
          },
          components: {
            Button: {
              controlHeight: 36,
              fontWeight: 700,
              primaryShadow: mode === 'dark' ? '0 0 24px rgba(47, 140, 255, 0.24)' : '0 8px 18px rgba(47, 111, 159, 0.16)',
            },
            Card: {
              colorBgContainer: mode === 'dark' ? '#0b1720' : '#ffffff',
              colorBorderSecondary: mode === 'dark' ? '#223544' : '#dde5ee',
            },
            Layout: {
              siderBg: mode === 'dark' ? '#071018' : '#ffffff',
              headerBg: mode === 'dark' ? '#071018' : '#ffffff',
              bodyBg: mode === 'dark' ? '#08131b' : '#f3f6fa',
            },
            Menu: {
              itemBg: 'transparent',
              itemSelectedBg: mode === 'dark' ? 'rgba(47, 140, 255, 0.16)' : 'rgba(47, 111, 159, 0.1)',
              itemSelectedColor: mode === 'dark' ? '#e7f1ff' : '#1f5578',
              itemColor: mode === 'dark' ? '#9ba9ba' : '#4b5a6f',
            },
            Table: {
              headerBg: mode === 'dark' ? '#101f2a' : '#f6f8fb',
              headerColor: mode === 'dark' ? '#a9b7c8' : '#334155',
              rowHoverBg: mode === 'dark' ? 'rgba(47, 140, 255, 0.08)' : '#f7fbfd',
            },
          },
        }}
      >
        {children}
      </ConfigProvider>
    </ThemeContext.Provider>
  );
}

export function useThemeMode() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useThemeMode must be used inside AppThemeProvider');
  }
  return context;
}
