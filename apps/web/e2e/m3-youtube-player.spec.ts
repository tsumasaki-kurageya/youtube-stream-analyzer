import { expect, test, type Page } from '@playwright/test';

const stream = {
  id: '11111111-1111-1111-1111-111111111111',
  youtubeVideoId: 'abcdefghijk',
  sourceUrl: 'https://www.youtube.com/watch?v=abcdefghijk',
  title: 'プレーヤーテスト配信',
  channelTitle: 'テストチャンネル',
  thumbnailUrl: 'https://example.test/thumbnail.jpg',
  actualStartAt: '2026-08-01T00:00:00Z',
  actualEndAt: '2026-08-01T01:00:00Z',
  durationSeconds: 3600,
  createdAt: '2026-08-01T02:00:00Z',
};

async function mockDetail(page: Page) {
  await page.route(`**/api/streams/${stream.id}`, (route) => route.fulfill({ json: stream }));
  await page.route(`**/api/streams/${stream.id}/chat-collections/latest`, (route) =>
    route.fulfill({ status: 404, contentType: 'application/problem+json', body: '{}' }),
  );
}

test('詳細画面で再生・停止・シーク・現在時刻を制御できる', async ({ page }) => {
  await page.addInitScript(() => {
    const state = { current: 0, created: 0, destroyed: 0, played: 0, paused: 0 };
    Object.assign(window, { __ysaPlayerState: state });
    Object.assign(window, {
      __YSA_YOUTUBE_PLAYER_FACTORY__: (
        element: HTMLElement,
        videoId: string,
        onReady: (adapter: unknown) => void,
      ) => {
        state.created += 1;
        const frame = document.createElement('iframe');
        frame.title = `stub player ${videoId}`;
        element.append(frame);
        const adapter = {
          play: () => { state.played += 1; },
          pause: () => { state.paused += 1; },
          seekTo: (seconds: number) => { state.current = seconds; },
          getCurrentTime: () => state.current,
          destroy: () => { state.destroyed += 1; frame.remove(); },
        };
        queueMicrotask(() => onReady(adapter));
        return adapter;
      },
    });
  });
  await mockDetail(page);
  await page.goto(`/streams/${stream.id}`);

  await expect(page.getByRole('heading', { name: '配信プレーヤー' })).toBeVisible();
  await expect(page.locator('.player-frame')).toHaveAttribute('data-video-id', stream.youtubeVideoId);
  await expect(page.getByRole('button', { name: '再生' })).toBeEnabled();

  await page.getByRole('button', { name: '再生' }).click();
  await page.getByRole('button', { name: '一時停止' }).click();
  await page.getByLabel('動画内時刻（秒）').fill('125');
  await page.getByRole('button', { name: '指定時刻へ移動' }).click();
  await expect(page.getByLabel('現在の再生時刻')).toHaveText('00:02:05');

  const state = await page.evaluate(() => (window as typeof window & { __ysaPlayerState: Record<string, number> }).__ysaPlayerState);
  expect(state.played).toBe(1);
  expect(state.paused).toBe(1);
  expect(state.current).toBe(125);
  expect(state.created - state.destroyed).toBe(1);
});

test('埋め込み不可の場合は理由とYouTubeへの導線を表示する', async ({ page }) => {
  await page.addInitScript(() => {
    Object.assign(window, {
      __YSA_YOUTUBE_PLAYER_FACTORY__: (
        _element: HTMLElement,
        _videoId: string,
        _onReady: (adapter: unknown) => void,
        onError: (code?: number) => void,
      ) => {
        queueMicrotask(() => onError(150));
        return { play() {}, pause() {}, seekTo() {}, getCurrentTime: () => 0, destroy() {} };
      },
    });
  });
  await mockDetail(page);
  await page.goto(`/streams/${stream.id}`);

  await expect(page.getByRole('alert')).toContainText('埋め込み再生できません');
  await expect(page.getByRole('link', { name: 'YouTubeで元配信を開く' })).toHaveAttribute('href', stream.sourceUrl);
});
