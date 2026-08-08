import { expect, test, type Page } from '@playwright/test';

type ReservationState = 'scheduled' | 'monitoring' | 'live' | 'waiting_for_archive' | 'collecting' | 'completed' | 'cancelled' | 'failed';
type CollectionStatus = 'queued' | 'running' | 'succeeded' | 'partial' | 'failed' | 'cancelled' | null;

type Reservation = {
  id: string;
  youtubeVideoId: string;
  sourceUrl: string;
  state: ReservationState;
  scheduledStartAt: string | null;
  actualStartAt: string | null;
  actualEndAt: string | null;
  nextCheckAt: string;
  lastCheckedAt: string | null;
  monitorAttempt: number;
  lastErrorCode: string | null;
  lastErrorMessage: string | null;
  lastErrorRetryable: boolean | null;
  streamId: string | null;
  collectionJobId: string | null;
  collectionStatus: CollectionStatus;
  collectionErrorCode: string | null;
  collectionErrorMessage: string | null;
  canCancel: boolean;
  cancelledAt: string | null;
  completedAt: string | null;
  failedAt: string | null;
  createdAt: string;
  updatedAt: string;
};

const baseTime = '2026-08-03T00:00:00Z';

function reservation(overrides: Partial<Reservation> & Pick<Reservation, 'id' | 'state'>): Reservation {
  return {
    id: overrides.id,
    youtubeVideoId: 'abcdefghijk',
    sourceUrl: 'https://www.youtube.com/watch?v=abcdefghijk',
    state: overrides.state,
    scheduledStartAt: '2026-08-03T03:00:00Z',
    actualStartAt: null,
    actualEndAt: null,
    nextCheckAt: '2026-08-03T02:55:00Z',
    lastCheckedAt: baseTime,
    monitorAttempt: 2,
    lastErrorCode: null,
    lastErrorMessage: null,
    lastErrorRetryable: null,
    streamId: null,
    collectionJobId: null,
    collectionStatus: null,
    collectionErrorCode: null,
    collectionErrorMessage: null,
    canCancel: ['scheduled', 'monitoring', 'live', 'waiting_for_archive'].includes(overrides.state),
    cancelledAt: null,
    completedAt: null,
    failedAt: null,
    createdAt: baseTime,
    updatedAt: baseTime,
    ...overrides,
  };
}

async function blockThumbnails(page: Page) {
  await page.route('https://i.ytimg.com/**', (route) => route.abort());
}

test('開始前・配信中URLを確認して解析予約を登録できる', async ({ page }) => {
  await blockThumbnails(page);
  const created = reservation({ id: 'reservation-created', state: 'scheduled' });

  await page.route('**/api/reservations', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    expect(route.request().postDataJSON()).toEqual({ url: created.sourceUrl });
    await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(created) });
  });
  await page.route('**/api/reservations/reservation-created', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(created) });
  });

  await page.goto('/reservations/new');
  await page.getByLabel('YouTube配信URL').fill(created.sourceUrl);
  await page.getByRole('button', { name: '予約内容を確認' }).click();

  await expect(page.getByRole('heading', { name: 'この配信を終了後に自動収集します' })).toBeVisible();
  await expect(page.getByText('abcdefghijk', { exact: true })).toBeVisible();
  await expect(page.getByText('登録時にYouTubeへ問い合わせ')).toBeVisible();

  await page.getByRole('button', { name: 'この配信を解析予約' }).click();
  await expect(page).toHaveURL(/\/reservations\/reservation-created$/);
  await expect(page.getByRole('heading', { name: '配信 abcdefghijk' })).toBeVisible();
  await expect(page.getByText('予約待ち', { exact: true }).first()).toBeVisible();
});

test('予約一覧で全主要状態と収集状態を判別できる', async ({ page }) => {
  await blockThumbnails(page);
  const items: Reservation[] = [
    reservation({ id: 'scheduled', state: 'scheduled', youtubeVideoId: 'state000001' }),
    reservation({ id: 'monitoring', state: 'monitoring', youtubeVideoId: 'state000002' }),
    reservation({ id: 'live', state: 'live', youtubeVideoId: 'state000003' }),
    reservation({ id: 'archive', state: 'waiting_for_archive', youtubeVideoId: 'state000004' }),
    reservation({ id: 'collecting', state: 'collecting', youtubeVideoId: 'state000005', canCancel: false, collectionStatus: 'running' }),
    reservation({ id: 'completed', state: 'completed', youtubeVideoId: 'state000006', canCancel: false, collectionStatus: 'succeeded', completedAt: baseTime }),
    reservation({ id: 'cancelled', state: 'cancelled', youtubeVideoId: 'state000007', canCancel: false, collectionStatus: 'cancelled', cancelledAt: baseTime }),
    reservation({ id: 'failed', state: 'failed', youtubeVideoId: 'state000008', canCancel: false, collectionStatus: 'partial', failedAt: baseTime }),
  ];

  await page.route(/\/api\/reservations\?limit=100$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items, total: items.length, limit: 100, offset: 0 }),
    });
  });

  await page.goto('/reservations');
  const list = page.getByRole('list', { name: '解析予約一覧' });
  for (const label of ['予約待ち', '監視中', '配信中', 'アーカイブ待ち', 'データ収集中', '完了', 'キャンセル済み', '失敗']) {
    await expect(list.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(list.getByText('収集: 収集中', { exact: true })).toBeVisible();
  await expect(list.getByText('収集: 一部収集失敗', { exact: true })).toBeVisible();
});

test('キャンセル可能な予約をキャンセルし、禁止状態を説明できる', async ({ page }) => {
  await blockThumbnails(page);
  const live = reservation({ id: 'reservation-live', state: 'live' });
  const cancelled = reservation({
    ...live,
    state: 'cancelled',
    canCancel: false,
    cancelledAt: baseTime,
    updatedAt: '2026-08-03T00:05:00Z',
  });

  await page.route('**/api/reservations/reservation-live', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(live) });
  });
  await page.route('**/api/reservations/reservation-live/cancel', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(cancelled) });
  });

  await page.goto('/reservations/reservation-live');
  await expect(page.getByRole('button', { name: '解析予約をキャンセル' })).toBeVisible();
  await page.getByRole('button', { name: '解析予約をキャンセル' }).click();
  await expect(page.getByText('キャンセル済み', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: '解析予約をキャンセル' })).toHaveCount(0);
  await expect(page.getByText('終了済みの予約に対する操作はありません。')).toBeVisible();
});

test('完了した予約から収集済み配信へ移動し、部分失敗を表示できる', async ({ page }) => {
  await blockThumbnails(page);
  const completed = reservation({
    id: 'reservation-completed',
    state: 'completed',
    canCancel: false,
    streamId: '00000000-0000-0000-0000-000000000123',
    collectionStatus: 'partial',
    collectionErrorCode: 'TRANSCRIPT_UNAVAILABLE',
    collectionErrorMessage: '字幕のみ取得できませんでした。',
    completedAt: baseTime,
  });

  await page.route('**/api/reservations/reservation-completed', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(completed) });
  });

  await page.goto('/reservations/reservation-completed');
  await expect(page.getByRole('heading', { name: '自動収集の結果' })).toBeVisible();
  await expect(page.getByText('字幕のみ取得できませんでした。')).toBeVisible();
  await page.getByRole('button', { name: '収集済み配信を開く' }).click();
  await expect(page).toHaveURL(/\/streams\/00000000-0000-0000-0000-000000000123$/);
});
