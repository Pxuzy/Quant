import React from 'react';
import ReactDOM from 'react-dom/client';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import { AppProviders } from './app/AppProviders';
import { AppThemeProvider } from './app/ThemeProvider';
import { App } from './app/App';
import './styles.css';

dayjs.locale('zh-cn');

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <AppThemeProvider>
      <AppProviders>
        <App />
      </AppProviders>
    </AppThemeProvider>
  </React.StrictMode>,
);
