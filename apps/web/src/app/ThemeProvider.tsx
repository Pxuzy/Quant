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
const THEME_VERSION = 'quant-workbench-v2';

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
            colorPrimary: mode === 'dark' ? '#4c9cff' : '#23698a',
            colorInfo: mode === 'dark' ? '#4c9cff' : '#23698a',
            colorSuccess: mode === 'dark' ? '#35c980' : '#247a52',
            colorWarning: mode === 'dark' ? '#f2b94b' : '#a66f1c',
            colorError: mode === 'dark' ? '#ff675f' : '#b43b31',
            colorBgBase: mode === 'dark' ? '#080d12' : '#f4f7fb',
            colorBgContainer: mode === 'dark' ? '#101923' : '#ffffff',
            colorBorder: mode === 'dark' ? '#243241' : '#d8e1eb',
            colorTextBase: mode === 'dark' ? '#dce7f5' : '#172033',
            borderRadius: 6,
            borderRadiusLG: 8,
            borderRadiusSM: 4,
            controlHeight: 34,
            controlHeightLG: 38,
            controlHeightSM: 28,
            fontSize: 13,
            fontFamily:
              '"DIN Alternate", "Bahnschrift", "SF Pro Text", "Segoe UI", ui-sans-serif, system-ui, sans-serif',
          },
          components: {
            Button: {
              contentFontSize: 13,
              contentFontSizeSM: 12,
              defaultBg: mode === 'dark' ? '#111d27' : '#ffffff',
              defaultBorderColor: mode === 'dark' ? '#2d4052' : '#cbd7e3',
              defaultHoverBg: mode === 'dark' ? '#142636' : '#f6fafc',
              defaultHoverBorderColor: mode === 'dark' ? '#4c9cff' : '#23698a',
              defaultShadow: 'none',
              fontWeight: 700,
              paddingInline: 14,
              paddingInlineSM: 10,
              primaryShadow: mode === 'dark' ? '0 0 0 1px rgba(76, 156, 255, 0.28)' : '0 0 0 1px rgba(35, 105, 138, 0.1)',
              textHoverBg: mode === 'dark' ? 'rgba(76, 156, 255, 0.12)' : 'rgba(35, 105, 138, 0.08)',
            },
            Card: {
              bodyPadding: 16,
              bodyPaddingSM: 12,
              headerBg: mode === 'dark' ? '#101923' : '#fbfdff',
              headerFontSize: 14,
              headerFontSizeSM: 13,
              headerHeight: 44,
              headerHeightSM: 38,
              headerPadding: 16,
              headerPaddingSM: 12,
            },
            Layout: {
              bodyBg: mode === 'dark' ? '#0a1118' : '#f4f7fb',
              headerBg: mode === 'dark' ? '#0c141c' : '#ffffff',
              headerHeight: 70,
              headerPadding: '0 22px',
              siderBg: mode === 'dark' ? '#0a1118' : '#ffffff',
            },
            Menu: {
              activeBarWidth: 3,
              iconSize: 16,
              itemActiveBg: mode === 'dark' ? 'rgba(76, 156, 255, 0.16)' : 'rgba(35, 105, 138, 0.1)',
              itemBg: 'transparent',
              itemBorderRadius: 6,
              itemColor: mode === 'dark' ? '#9ba9ba' : '#4b5a6f',
              itemHeight: 38,
              itemHoverBg: mode === 'dark' ? 'rgba(147, 164, 183, 0.1)' : 'rgba(23, 32, 51, 0.05)',
              itemHoverColor: mode === 'dark' ? '#f3f8ff' : '#172033',
              itemMarginBlock: 3,
              itemMarginInline: 10,
              itemSelectedBg: mode === 'dark' ? 'rgba(76, 156, 255, 0.18)' : 'rgba(35, 105, 138, 0.1)',
              itemSelectedColor: mode === 'dark' ? '#eef6ff' : '#1f5578',
            },
            Table: {
              borderColor: mode === 'dark' ? '#243241' : '#d8e1eb',
              cellFontSizeSM: 12,
              cellPaddingBlockSM: 6,
              cellPaddingInlineSM: 8,
              headerBg: mode === 'dark' ? '#121d27' : '#f7fafc',
              headerColor: mode === 'dark' ? '#a9b7c8' : '#334155',
              headerSplitColor: mode === 'dark' ? '#243241' : '#d8e1eb',
              rowHoverBg: mode === 'dark' ? 'rgba(76, 156, 255, 0.08)' : '#f6fafc',
              rowSelectedBg: mode === 'dark' ? 'rgba(76, 156, 255, 0.14)' : 'rgba(35, 105, 138, 0.08)',
            },
            Tag: {
              defaultBg: mode === 'dark' ? '#121d27' : '#f7fafc',
              defaultColor: mode === 'dark' ? '#b9c7d7' : '#4b5a6f',
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
