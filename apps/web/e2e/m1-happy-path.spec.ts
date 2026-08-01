import { expect, test } from '@playwright/test';

const streamUrl = 'https://www.youtube.com/watch?v=abcdefghijk';

test('終了済み配信を登録し、詳細・一覧・再読込後も確認できる', async ({ page }) => {
  await page.goto('/streams');
  await expect(page.getByRole('heading', { name: '登録済み配信', exact: true, level: 1 })).toBeVisible();
  await expect(page.getByRole('heading', { name: '登録済み配信はありません', exact: true })).toBeVisible();

  await page.getByRole('button', { name: '最初の配信を登録' }).click();
  await expect(page).toHaveURL(/\/register$/);

  await page.getByLabel('YouTube配信URL').fill(streamUrl);
  await page.getByRole('button', { name: '配信情報を確認' }).click();
  await expect(page.getByRole('heading', { name: 'Stub stream', exact: true, level: 2 })).toBeVisible();
  await expect(page.getByText('Stub creator')).toBeVisible();
  await expect(page.getByText('01:02:03')).toBeVisible();

  await page.getByRole('button', { name: 'この配信を登録' }).click();
  await expect(page).toHaveURL(/\/streams\/[0-9a-f-]+$/);
  await expect(page.getByRole('heading', { name: 'Stub stream', exact: true, level: 1 })).toBeVisible();
  await expect(page.getByRole('link', { name: /YouTube/ })).toHaveAttribute('href', streamUrl);

  const detailUrl = page.url();
  await page.reload();
  await expect(page).toHaveURL(detailUrl);
  await expect(page.getByRole('heading', { name: 'Stub stream', exact: true, level: 1 })).toBeVisible();

  await page.getByRole('button', { name: '登録済み配信' }).click();
  await expect(page).toHaveURL(/\/streams$/);
  await expect(page.getByRole('button', { name: /Stub stream/ })).toBeVisible();

  await page.getByRole('button', { name: /Stub stream/ }).click();
  await expect(page).toHaveURL(detailUrl);
});

test('同じ配信を再登録しても既存詳細へ遷移する', async ({ page }) => {
  await page.goto('/register');
  await page.getByLabel('YouTube配信URL').fill(streamUrl);
  await page.getByRole('button', { name: '配信情報を確認' }).click();
  await expect(page.getByRole('heading', { name: 'Stub stream', exact: true, level: 2 })).toBeVisible();
  await page.getByRole('button', { name: 'この配信を登録' }).click();
  await expect(page).toHaveURL(/\/streams\/[0-9a-f-]+$/);
  await expect(page.getByRole('heading', { name: 'Stub stream', exact: true, level: 1 })).toBeVisible();
});

test('存在しない配信IDでは404状態を表示する', async ({ page }) => {
  await page.goto('/streams/00000000-0000-0000-0000-000000000000');
  await expect(page.getByRole('heading', { name: '配信を表示できません', exact: true })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveText('配信が見つかりません。');
  await expect(page.getByRole('button', { name: '一覧へ戻る' })).toBeVisible();
});
