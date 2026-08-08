import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '../../', 'YSA_');

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: env.YSA_API_ORIGIN || 'http://localhost:8080',
          changeOrigin: true,
        },
      },
    },
  };
});
