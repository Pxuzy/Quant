import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

declare const process: {
  cwd: () => string;
};

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  const apiTarget = env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000';
  const devServerPort = Number(env.VITE_DEV_SERVER_PORT ?? 5174);
  const projectRoot = process.cwd();

  return {
    root: projectRoot,
    plugins: [react()],
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('/node_modules/@ant-design/pro-components/')) {
              return 'antd-pro';
            }
            if (id.includes('/node_modules/antd/') || id.includes('/node_modules/@ant-design/icons/')) {
              return 'antd';
            }
            if (id.includes('/node_modules/gsap/') || id.includes('/node_modules/@gsap/react/')) {
              return 'motion';
            }
            return undefined;
          },
        },
      },
    },
    server: {
      port: Number.isFinite(devServerPort) ? devServerPort : 5173,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
