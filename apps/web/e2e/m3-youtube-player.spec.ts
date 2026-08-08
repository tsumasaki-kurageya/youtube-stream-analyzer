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

test('詳細画面ではYouTubeプレーヤー自身の操作UIだけを表示する', async ({ page }) => {
  await page.addInitScript(() => {
    Object.assign(window, {
      __YSA_YOUTUBE_PLAYER_FACTORY__: (
        element: HTMLElement,
        videoId: string,
        onReady: (adapter: unknown) => void,
      ) => {
        const frame = document.createElement('iframe');
        frame.title = `stub player ${videoId}`;
        element.append(frame);
        const adapter = { destroy: () => frame.remove() };
        queueMicrotask(() => onReady(adapter));
        return adapter;
      },
    });
  });
  await mockDetail(page);
  await page.goto(`/streams/${stream.id}`);

  const player = page.getByLabel('配信プレーヤー');
  await expect(player.locator('.player-frame')).toHaveAttribute('data-video-id', stream.youtubeVideoId);
  const playerFrame = await player.locator('.player-frame').boundingBox();
  expect(playerFrame?.width).toBeLessThanOrEqual(970);
  await expect(player.getByRole('button')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'チャット・字幕' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '配信内を検索' })).toHaveCount(0);
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
        return { destroy() {} };
      },
    });
  });
  await mockDetail(page);
  await page.goto(`/streams/${stream.id}`);

  const player = page.getByLabel('配信プレーヤー');
  await expect(player.getByRole('alert')).toContainText('埋め込み再生できません');
  await expect(player.getByRole('link', { name: 'YouTubeで元配信を開く' })).toHaveAttribute('href', stream.sourceUrl);
});
