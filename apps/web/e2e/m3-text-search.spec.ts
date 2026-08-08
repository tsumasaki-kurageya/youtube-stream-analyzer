import { expect, test, type Page } from '@playwright/test';

const stream = {
  id: '22222222-2222-2222-2222-222222222222',
  youtubeVideoId: 'searchvideo1',
  sourceUrl: 'https://www.youtube.com/watch?v=searchvideo1',
  title: '検索テスト配信',
  channelTitle: 'テストチャンネル',
  thumbnailUrl: 'https://example.test/thumbnail.jpg',
  actualStartAt: '2026-08-01T00:00:00Z',
  actualEndAt: '2026-08-01T01:00:00Z',
  durationSeconds: 3600,
  createdAt: '2026-08-01T02:00:00Z',
};

async function prepare(page: Page) {
  await page.addInitScript(() => {
    const state = { current: 0 };
    Object.assign(window, { __ysaSearchPlayerState: state });
    Object.assign(window, {
      __YSA_YOUTUBE_PLAYER_FACTORY__: (
        element: HTMLElement,
        _videoId: string,
        onReady: (adapter: unknown) => void,
      ) => {
        const frame = document.createElement('iframe');
        frame.title = 'search player';
        element.append(frame);
        const adapter = {
          play() {},
          pause() {},
          seekTo(seconds: number) { state.current = seconds; },
          getCurrentTime: () => state.current,
          destroy() { frame.remove(); },
        };
        queueMicrotask(() => onReady(adapter));
        return adapter;
      },
    });
  });
  await page.route(`**/api/streams/${stream.id}`, (route) => route.fulfill({ json: stream }));
  await page.route(`**/api/streams/${stream.id}/chat-messages?*`, (route) =>
    route.fulfill({ json: { items: [] } }),
  );
  await page.route(`**/api/streams/${stream.id}/transcript-segments?*`, (route) =>
    route.fulfill({ json: { items: [] } }),
  );
  await page.route(`**/api/streams/${stream.id}/collections/latest`, (route) =>
    route.fulfill({ json: { steps: [{ name: 'transcript', status: 'no_data' }] } }),
  );
}

test('チャットと字幕を横断検索し結果から動画時刻へ移動する', async ({ page }) => {
  await prepare(page);
  let searchRequests = 0;
  await page.route(`**/api/streams/${stream.id}/search?*`, (route) => {
    searchRequests += 1;
    const url = new URL(route.request().url());
    expect(url.searchParams.get('q')).toBe('重要');
    route.fulfill({
      json: {
        items: [
          {
            id: 'chat-1', type: 'chat', offsetMilliseconds: 125000,
            text: '重要なチャット発言', speaker: 'alice',
          },
          {
            id: 'transcript-1', type: 'transcript', offsetMilliseconds: 180000,
            endOffsetMilliseconds: 182000, text: '重要な字幕です', languageCode: 'ja',
          },
        ],
        hasMore: false,
      },
    });
  });

  await page.goto(`/streams/${stream.id}`);
  const input = page.getByLabel('検索語');
  await expect(input).toBeVisible();
  await input.fill('重');
  await input.fill('重要');
  await expect(page.getByRole('list', { name: 'チャット・字幕検索結果' })).toBeVisible();
  expect(searchRequests).toBe(1);

  await expect(page.getByText('チャット · 00:02:05 · alice')).toBeVisible();
  await expect(page.getByText('字幕 · 00:03:00 · ja')).toBeVisible();
  await expect(page.locator('mark').first()).toHaveText('重要');

  await page.getByRole('button', { name: /チャット · 00:02:05/ }).click();
  await expect(page.getByLabel('現在の再生時刻')).toHaveText('00:02:05');
  const state = await page.evaluate(() =>
    (window as typeof window & { __ysaSearchPlayerState: { current: number } }).__ysaSearchPlayerState,
  );
  expect(state.current).toBe(125);
});

test('検索0件とカーソルページングを表示する', async ({ page }) => {
  await prepare(page);
  await page.route(`**/api/streams/${stream.id}/search?*`, (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get('q') === 'なし') {
      route.fulfill({ json: { items: [], hasMore: false } });
      return;
    }
    if (url.searchParams.has('cursor')) {
      route.fulfill({
        json: {
          items: [{ id: '2', type: 'transcript', offsetMilliseconds: 2000, text: '続き', languageCode: 'ja' }],
          hasMore: false,
        },
      });
      return;
    }
    route.fulfill({
      json: {
        items: [{ id: '1', type: 'chat', offsetMilliseconds: 1000, text: '最初', speaker: 'alice' }],
        nextCursor: 'next',
        hasMore: true,
      },
    });
  });

  await page.goto(`/streams/${stream.id}`);
  const input = page.getByLabel('検索語');
  await input.fill('なし');
  await expect(page.getByText('「なし」に一致するチャット・字幕はありません。')).toBeVisible();

  await input.fill('結果');
  await expect(page.getByRole('button', { name: '次の50件を読み込む' })).toBeVisible();
  await page.getByRole('button', { name: '次の50件を読み込む' }).click();
  await expect(page.getByText('続き')).toBeVisible();
  await expect(page.getByRole('list', { name: 'チャット・字幕検索結果' }).getByRole('listitem')).toHaveCount(2);
});
