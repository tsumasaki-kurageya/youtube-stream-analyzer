import { expect, test, type Page } from '@playwright/test';

const stream = {
  id: '22222222-2222-2222-2222-222222222222',
  youtubeVideoId: 'syncvideo01',
  sourceUrl: 'https://www.youtube.com/watch?v=syncvideo01',
  title: '同期タイムラインテスト配信',
  channelTitle: 'テストチャンネル',
  thumbnailUrl: 'https://example.test/thumbnail.jpg',
  actualStartAt: '2026-08-01T00:00:00Z',
  actualEndAt: '2026-08-01T02:00:00Z',
  durationSeconds: 7200,
  createdAt: '2026-08-01T03:00:00Z',
};

async function installPlayer(page: Page) {
  await page.addInitScript(() => {
    const state = { current: 120, seeks: [] as number[] };
    Object.assign(window, { __ysaSyncPlayerState: state });
    Object.assign(window, {
      __YSA_YOUTUBE_PLAYER_FACTORY__: (
        element: HTMLElement,
        videoId: string,
        onReady: (adapter: unknown) => void,
      ) => {
        const frame = document.createElement('iframe');
        frame.title = `stub player ${videoId}`;
        element.append(frame);
        const adapter = {
          play() {},
          pause() {},
          seekTo(seconds: number) { state.current = seconds; state.seeks.push(seconds); },
          getCurrentTime: () => state.current,
          destroy: () => frame.remove(),
        };
        queueMicrotask(() => onReady(adapter));
        return adapter;
      },
    });
  });
}

async function mockAPIs(page: Page) {
  await page.route(`**/api/streams/${stream.id}`, (route) => route.fulfill({ json: stream }));
  await page.route(`**/api/streams/${stream.id}/chat-collections/latest`, (route) =>
    route.fulfill({ status: 404, contentType: 'application/problem+json', body: '{}' }),
  );
  await page.route(`**/api/streams/${stream.id}/collections/latest`, (route) => route.fulfill({
    json: { steps: [{ name: 'transcript', status: 'succeeded' }] },
  }));
  await page.route(`**/api/streams/${stream.id}/chat-messages?*`, (route) => route.fulfill({
    json: {
      items: [
        { id: 'chat-before', authorName: 'Alice', messageText: '少し前', elapsedMilliseconds: 118000 },
        { id: 'chat-current', authorName: 'Bob', messageText: '現在付近', elapsedMilliseconds: 121000 },
      ],
      nextCursor: null,
    },
  }));
  await page.route(`**/api/streams/${stream.id}/transcript-segments?*`, (route) => route.fulfill({
    json: {
      items: [
        { id: 'segment-current', languageCode: 'ja', startOffsetMilliseconds: 119000, endOffsetMilliseconds: 123000, text: '現在位置の字幕' },
        { id: 'segment-next', languageCode: 'ja', startOffsetMilliseconds: 130000, endOffsetMilliseconds: 134000, text: '次の字幕' },
      ],
      nextCursor: null,
    },
  }));
}

test('現在時刻周辺のチャットと字幕を表示し項目からシークできる', async ({ page }) => {
  await installPlayer(page);
  await mockAPIs(page);
  await page.goto(`/streams/${stream.id}`);

  await expect(page.getByRole('heading', { name: 'チャット・字幕' })).toBeVisible();
  await expect(page.getByRole('list', { name: '現在時刻周辺のチャット' })).toContainText('現在付近');
  await expect(page.getByRole('list', { name: '現在時刻周辺の字幕' })).toContainText('現在位置の字幕');
  await expect(page.getByText('現在位置の字幕').locator('..').locator('..')).toHaveAttribute('aria-current', 'true');

  await page.getByRole('button', { name: /次の字幕/ }).click();
  await expect(page.getByLabel('現在の再生時刻')).toHaveText('00:02:10');

  const state = await page.evaluate(() => (window as typeof window & { __ysaSyncPlayerState: { seeks: number[] } }).__ysaSyncPlayerState);
  expect(state.seeks).toContain(130);

  const follow = page.getByRole('button', { name: '自動追従を停止' });
  await follow.click();
  await expect(page.getByRole('button', { name: '自動追従を再開' })).toHaveAttribute('aria-pressed', 'false');
});

test('字幕なし状態を字幕取得失敗と区別して表示する', async ({ page }) => {
  await installPlayer(page);
  await mockAPIs(page);
  await page.route(`**/api/streams/${stream.id}/collections/latest`, (route) => route.fulfill({
    json: { steps: [{ name: 'transcript', status: 'no_data' }] },
  }));
  await page.route(`**/api/streams/${stream.id}/transcript-segments?*`, (route) => route.fulfill({
    json: { items: [], nextCursor: null },
  }));
  await page.goto(`/streams/${stream.id}`);

  await expect(page.getByText('この配信には利用可能な字幕がありません。')).toBeVisible();
  await expect(page.getByText(/字幕取得失敗/)).toHaveCount(0);
});
