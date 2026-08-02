import { expect, test } from '@playwright/test';

const streamId = '11111111-1111-1111-1111-111111111111';
const stream = {
  id: streamId,
  youtubeVideoId: 'abcdefghijk',
  sourceUrl: 'https://www.youtube.com/watch?v=abcdefghijk',
  title: 'Collection UI test stream',
  channelTitle: 'Test creator',
  thumbnailUrl: 'https://example.test/thumbnail.jpg',
  actualStartAt: '2026-01-01T10:00:00Z',
  actualEndAt: '2026-01-01T11:00:00Z',
  durationSeconds: 3600,
  createdAt: '2026-01-01T12:00:00Z',
};

function job(status: 'queued' | 'running' | 'succeeded' | 'failed') {
  return {
    id: '22222222-2222-2222-2222-222222222222',
    streamId,
    kind: 'chat',
    status,
    attempt: status === 'failed' ? 1 : 2,
    retryOfJobId: null,
    progressCount: status === 'running' || status === 'succeeded' ? 42 : 0,
    errorCode: status === 'failed' ? 'CHAT_REPLAY_TEMPORARY_ERROR' : null,
    errorMessage: status === 'failed' ? '一時的に取得できませんでした' : null,
    startedAt: '2026-01-01T12:01:00Z',
    finishedAt: status === 'succeeded' || status === 'failed' ? '2026-01-01T12:02:00Z' : null,
    createdAt: '2026-01-01T12:00:00Z',
    updatedAt: '2026-01-01T12:02:00Z',
    steps: [{
      id: '33333333-3333-3333-3333-333333333333',
      name: 'chat_replay',
      status,
      progressCount: status === 'running' || status === 'succeeded' ? 42 : 0,
      errorCode: null,
      errorMessage: null,
      startedAt: '2026-01-01T12:01:00Z',
      finishedAt: null,
    }],
  };
}

async function mockStream(page: import('@playwright/test').Page) {
  await page.route(`**/api/streams/${streamId}`, (route) => route.fulfill({ json: stream }));
}

test('未開始からチャット収集を開始できる', async ({ page }) => {
  await mockStream(page);
  await page.route(`**/api/streams/${streamId}/chat-collections/latest`, (route) => route.fulfill({ status: 404, json: { code: 'COLLECTION_JOB_NOT_FOUND' } }));
  await page.route(`**/api/streams/${streamId}/chat-collections`, (route) => route.fulfill({ status: 202, json: job('queued') }));
  await page.goto(`/streams/${streamId}`);
  await page.getByRole('button', { name: 'チャット収集を開始' }).click();
  await expect(page.getByText('開始待ち')).toBeVisible();
});

test('実行中の工程と取得件数をリロード後も表示する', async ({ page }) => {
  await mockStream(page);
  await page.route(`**/api/streams/${streamId}/chat-collections/latest`, (route) => route.fulfill({ json: job('running') }));
  await page.goto(`/streams/${streamId}`);
  await expect(page.getByText('収集中')).toBeVisible();
  await expect(page.getByText('チャットリプレイ取得')).toBeVisible();
  await expect(page.getByText('42件')).toBeVisible();
  await page.reload();
  await expect(page.getByText('収集中')).toBeVisible();
});

test('失敗理由を表示して再実行できる', async ({ page }) => {
  await mockStream(page);
  await page.route(`**/api/streams/${streamId}/chat-collections/latest`, (route) => route.fulfill({ json: job('failed') }));
  await page.route('**/api/collection-jobs/*/retry', (route) => route.fulfill({ status: 202, json: job('queued') }));
  await page.goto(`/streams/${streamId}`);
  await expect(page.getByText('一時的に取得できませんでした')).toBeVisible();
  await page.getByRole('button', { name: 'チャット収集を再実行' }).click();
  await expect(page.getByText('開始待ち')).toBeVisible();
});

test('完了後にチャット一覧への導線を表示する', async ({ page }) => {
  await mockStream(page);
  await page.route(`**/api/streams/${streamId}/chat-collections/latest`, (route) => route.fulfill({ json: job('succeeded') }));
  await page.goto(`/streams/${streamId}`);
  await expect(page.getByRole('button', { name: '収集したチャットを見る' })).toBeVisible();
});
