import { expect, test } from '@playwright/test';

const stream = {
  id: 'stream-1', youtubeVideoId: 'abcdefghijk', sourceUrl: 'https://youtu.be/abcdefghijk',
  title: 'チャット閲覧テスト', channelTitle: '配信者', thumbnailUrl: 'https://example.test/t.jpg',
  actualStartAt: '2026-01-01T10:00:00Z', actualEndAt: '2026-01-01T11:00:00Z', durationSeconds: 3600,
  createdAt: '2026-01-01T12:00:00Z',
};

test('チャットを時系列表示し次ページを読み込める', async ({ page }) => {
  await page.route('**/api/streams/stream-1', (route) => route.fulfill({ json: stream }));
  await page.route('**/api/streams/stream-1/chat-messages**', async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.has('cursor')) {
      await route.fulfill({ json: { items: [{ id: '3', externalMessageId: 'c', authorName: 'Carol', messageText: 'third', publishedAt: '2026-01-01T10:00:03Z', elapsedMilliseconds: 3000 }], nextCursor: null } });
      return;
    }
    await route.fulfill({ json: { items: [{ id: '1', externalMessageId: 'a', authorName: 'Alice', messageText: 'first', publishedAt: '2026-01-01T10:00:01Z', elapsedMilliseconds: 1000 }, { id: '2', externalMessageId: 'b', authorName: 'Bob', messageText: 'second', publishedAt: '2026-01-01T10:00:02Z', elapsedMilliseconds: 2000 }], nextCursor: 'next' } });
  });

  await page.goto('/streams/stream-1/chat');
  await expect(page.getByRole('heading', { name: 'チャット閲覧テスト' })).toBeVisible();
  await expect(page.getByLabel('チャット時系列').getByRole('listitem')).toHaveCount(2);
  await expect(page.getByText('00:00:01')).toBeVisible();
  await page.getByRole('button', { name: '次の100件を読み込む' }).click();
  await expect(page.getByLabel('チャット時系列').getByRole('listitem')).toHaveCount(3);
});

test('0件と取得失敗を区別できる', async ({ page }) => {
  await page.route('**/api/streams/stream-1', (route) => route.fulfill({ json: stream }));
  await page.route('**/api/streams/stream-1/chat-messages**', (route) => route.fulfill({ json: { items: [], nextCursor: null } }));
  await page.goto('/streams/stream-1/chat');
  await expect(page.getByRole('heading', { name: '収集済みチャットはありません' })).toBeVisible();
});
