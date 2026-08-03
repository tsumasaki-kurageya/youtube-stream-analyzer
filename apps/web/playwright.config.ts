import { defineConfig, devices } from '@playwright/test';

const databaseUrl = process.env.YSA_DATABASE_URL ?? 'postgres://ysa:ysa@localhost:5432/youtube_stream_analyzer?sslmode=disable';
const gatewayToken = 'e2e-gateway-token';
const gatewayURL = 'http://127.0.0.1:18081';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'go run ./cmd/youtube-stub',
      cwd: '../api',
      port: 18080,
      reuseExistingServer: !process.env.CI,
      env: { YSA_YOUTUBE_STUB_ADDRESS: ':18080' },
    },
    {
      command: 'python tests/e2e_server.py',
      cwd: '../youtube-data-gateway',
      port: 18081,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: 'go run ./cmd/api',
      cwd: '../api',
      port: 8080,
      reuseExistingServer: !process.env.CI,
      env: {
        YSA_API_ADDRESS: ':8080',
        YSA_DATABASE_URL: databaseUrl,
        YSA_YOUTUBE_API_KEY: 'e2e-key',
        YSA_YOUTUBE_API_BASE_URL: 'http://127.0.0.1:18080',
      },
    },
    {
      command: 'python tests/e2e_server.py',
      cwd: '../worker',
      port: 18082,
      reuseExistingServer: !process.env.CI,
      env: {
        YSA_DATABASE_URL: databaseUrl,
        YSA_WORKER_ID: 'e2e-worker',
        YSA_WORKER_POLL_INTERVAL_SECONDS: '0.2',
        YSA_WORKER_HEARTBEAT_INTERVAL_SECONDS: '1',
        YSA_WORKER_LEASE_SECONDS: '10',
        YSA_YOUTUBE_API_KEY: 'e2e-key',
        YSA_YOUTUBE_API_BASE_URL: 'http://127.0.0.1:18080',
        YSA_YOUTUBE_TIMEOUT_SECONDS: '2',
        YSA_GATEWAY_BEARER_TOKEN: gatewayToken,
        YSA_CHAT_REPLAY_BASE_URL: gatewayURL,
        YSA_CHAT_REPLAY_TIMEOUT_SECONDS: '2',
        YSA_TRANSCRIPT_BASE_URL: gatewayURL,
        YSA_TRANSCRIPT_TIMEOUT_SECONDS: '2',
      },
    },
    {
      command: 'npm run dev',
      cwd: '.',
      port: 5173,
      reuseExistingServer: !process.env.CI,
    },
  ],
});
