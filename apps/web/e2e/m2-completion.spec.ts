import { expect, test, type Page } from '@playwright/test';

async function registerStream(page: Page, videoId: string) {
  await page.goto('/register');
  await page.getByLabel('YouTube配信URL').fill(`https://www.youtube.com/watch?v=${videoId}`);
  await page.getByRole('button', { name: '配信情報を確認' }).click();
  await expect(page.getByRole('heading', { name: 'Stub stream' })).toBeVisible();
  await page.getByRole('button', { name: 'この配信を登録' }).click();
  await expect(page).toHaveURL(/\/streams\/[0-9a-f-]+$/);
  return page.url().split('/').at(-1)!;
}

async function waitForCollection(page: Page, status: '収集完了' | '収集失敗') {
  await expect(page.getByRole('status').filter({ hasText: status })).toBeVisible({ timeout: 20_000 });
}

test('M2の収集開始から時系列閲覧と冪等な再収集まで完了する', async ({ page, request }) => {
  const streamId = await registerStream(page, 'fullflow001');

  await page.getByRole('button', { name: 'チャット収集を開始' }).click();
  await expect(page.getByText(/開始待ち|収集中/)).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'チャット収集' })).toBeVisible();
  await waitForCollection(page, '収集完了');
  await expect(page.getByText('3件')).toBeVisible();

  await page.getByRole('button', { name: '収集したチャットを見る' }).click();
  await expect(page.getByRole('heading', { name: 'チャット時系列' })).toBeVisible();
  await expect(page.locator('.chat-message')).toHaveCount(3);
  await expect(page.locator('.chat-time')).toHaveText(['00:00:01', '00:00:02', '00:00:03']);
  await expect(page.getByText('first message')).toBeVisible();
  await expect(page.getByText('third message')).toBeVisible();

  const second = await request.post(`/api/streams/${streamId}/chat-collections`);
  expect(second.status()).toBe(202);
  await expect.poll(async () => {
    const response = await request.get(`/api/streams/${streamId}/chat-collections/latest`);
    return (await response.json()).status;
  }, { timeout: 20_000 }).toBe('succeeded');
  const messages = await request.get(`/api/streams/${streamId}/chat-messages?limit=100`);
  expect((await messages.json()).items).toHaveLength(3);
});

test('失敗理由を表示し再実行で完了する', async ({ page }) => {
  await registerStream(page, 'failchat001');
  await page.getByRole('button', { name: 'チャット収集を開始' }).click();
  await waitForCollection(page, '収集失敗');
  await expect(page.getByText(/temporarily unavailable|request failed|一時/)).toBeVisible();
  await page.getByRole('button', { name: 'チャット収集を再実行' }).click();
  await waitForCollection(page, '収集完了');
  await page.getByRole('button', { name: '収集したチャットを見る' }).click();
  await expect(page.locator('.chat-message')).toHaveCount(3);
});
