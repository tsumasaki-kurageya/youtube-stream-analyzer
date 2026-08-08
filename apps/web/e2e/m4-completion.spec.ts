import { expect, test, type APIRequestContext, type Page, type TestInfo } from '@playwright/test';

type ReservationState =
  | 'scheduled'
  | 'monitoring'
  | 'live'
  | 'waiting_for_archive'
  | 'collecting'
  | 'completed'
  | 'cancelled'
  | 'failed';

type Reservation = {
  id: string;
  youtubeVideoId: string;
  state: ReservationState;
  streamId?: string | null;
  collectionJobId?: string | null;
  collectionStatus?: string | null;
  lastErrorCode?: string | null;
  lastErrorMessage?: string | null;
};

type JobCount = { count: number };

const workerControlURL = 'http://127.0.0.1:18082';

function fixtureID(prefix: string, testInfo: TestInfo): string {
  const id = `${prefix}${testInfo.retry}`;
  if (id.length !== 11) throw new Error(`fixture video ID must be 11 characters: ${id}`);
  return id;
}

async function createReservation(
  request: APIRequestContext,
  videoID: string,
): Promise<Reservation> {
  const response = await request.post('/api/reservations', {
    data: { url: `https://www.youtube.com/watch?v=${videoID}` },
  });
  expect(response.status()).toBe(201);
  return await response.json() as Reservation;
}

async function getReservation(
  request: APIRequestContext,
  reservationID: string,
): Promise<Reservation> {
  const response = await request.get(`/api/reservations/${reservationID}`);
  expect(response.ok()).toBeTruthy();
  return await response.json() as Reservation;
}

async function cancelReservation(
  request: APIRequestContext,
  reservationID: string,
): Promise<Reservation> {
  const response = await request.post(`/api/reservations/${reservationID}/cancel`);
  expect(response.ok()).toBeTruthy();
  return await response.json() as Reservation;
}

async function makeDue(request: APIRequestContext, reservationID: string) {
  const response = await request.post(
    `${workerControlURL}/test/reservations/${reservationID}/due`,
  );
  expect(response.ok()).toBeTruthy();
}

async function restartWorker(request: APIRequestContext) {
  const response = await request.post(`${workerControlURL}/test/restart-worker`);
  expect(response.ok()).toBeTruthy();
}

async function collectionJobCount(
  request: APIRequestContext,
  reservationID: string,
): Promise<number> {
  const response = await request.get(
    `${workerControlURL}/test/reservations/${reservationID}/job-count`,
  );
  expect(response.ok()).toBeTruthy();
  return ((await response.json()) as JobCount).count;
}

async function waitForReservation(
  request: APIRequestContext,
  reservationID: string,
  predicate: (reservation: Reservation) => boolean,
): Promise<Reservation> {
  await expect.poll(async () => {
    const reservation = await getReservation(request, reservationID);
    return predicate(reservation);
  }, { timeout: 30_000, intervals: [200, 500, 1000] }).toBe(true);
  return await getReservation(request, reservationID);
}

async function installPlayer(page: Page) {
  await page.addInitScript(() => {
    const state = { current: 0 };
    Object.assign(window, {
      __YSA_YOUTUBE_PLAYER_FACTORY__: (
        element: HTMLElement,
        _videoId: string,
        onReady: (adapter: unknown) => void,
      ) => {
        const frame = document.createElement('iframe');
        frame.title = 'M4 completion player';
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
}

test('scheduled・live・endedの予約状態を決定的fixtureで作成できる', async ({ request }, testInfo) => {
  const scheduled = await createReservation(request, fixtureID('m4sched000', testInfo));
  const live = await createReservation(request, fixtureID('m4live0000', testInfo));
  const ended = await createReservation(request, fixtureID('m4ended000', testInfo));

  expect(scheduled.state).toBe('scheduled');
  expect(live.state).toBe('live');
  expect(ended.state).toBe('waiting_for_archive');

  await cancelReservation(request, scheduled.id);
  await cancelReservation(request, live.id);
  await cancelReservation(request, ended.id);
});

test('ワーカー再起動後も予約を復元し、自動収集からM3閲覧まで完了する', async ({ page, request }, testInfo) => {
  const reservation = await createReservation(request, fixtureID('m4restart0', testInfo));

  await restartWorker(request);
  await makeDue(request, reservation.id);

  const completed = await waitForReservation(
    request,
    reservation.id,
    (current) => current.state === 'completed' && current.collectionStatus === 'succeeded',
  );
  expect(completed.streamId).toBeTruthy();
  expect(completed.collectionJobId).toBeTruthy();
  expect(await collectionJobCount(request, reservation.id)).toBe(1);

  await makeDue(request, reservation.id);
  await page.waitForTimeout(750);
  expect(await collectionJobCount(request, reservation.id)).toBe(1);

  await installPlayer(page);
  await page.goto(`/reservations/${reservation.id}`);
  await expect(page.getByText('完了', { exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: '収集済み配信を開く' }).click();
  await expect(page.getByRole('heading', { name: 'チャット・字幕', exact: true })).toBeVisible();
  await page.getByLabel('検索語').fill('重要');
  await expect(page.getByRole('list', { name: 'チャット・字幕検索結果' })).toContainText('重要な検索対象の字幕');
});

test('キャンセル済み予約は監視・自動収集されない', async ({ page, request }, testInfo) => {
  const reservation = await createReservation(request, fixtureID('m4cancel00', testInfo));
  const cancelled = await cancelReservation(request, reservation.id);
  expect(cancelled.state).toBe('cancelled');

  await makeDue(request, reservation.id);
  await page.waitForTimeout(1000);

  expect((await getReservation(request, reservation.id)).state).toBe('cancelled');
  expect(await collectionJobCount(request, reservation.id)).toBe(0);

  await page.goto(`/reservations/${reservation.id}`);
  await expect(page.getByText('キャンセル済み', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: '解析予約をキャンセル' })).toHaveCount(0);
});

test('監視障害と収集部分失敗を予約詳細に表示する', async ({ page, request }, testInfo) => {
  const monitoringFailure = await createReservation(
    request,
    fixtureID('m4monfail0', testInfo),
  );
  await makeDue(request, monitoringFailure.id);
  const failedMonitoring = await waitForReservation(
    request,
    monitoringFailure.id,
    (current) => current.lastErrorCode === 'ARCHIVE_READINESS_TEMPORARILY_UNAVAILABLE',
  );
  expect(failedMonitoring.lastErrorMessage).toContain('temporarily unavailable');

  await page.goto(`/reservations/${monitoringFailure.id}`);
  await expect(page.getByRole('heading', { name: '配信監視のエラー' })).toBeVisible();
  await expect(page.getByText('次回確認時に自動で再試行します。')).toBeVisible();

  const collectionFailure = await createReservation(
    request,
    fixtureID('m4colfail0', testInfo),
  );
  await makeDue(request, collectionFailure.id);
  const partial = await waitForReservation(
    request,
    collectionFailure.id,
    (current) => current.collectionStatus === 'partial',
  );
  expect(partial.state).toBe('collecting');

  await page.goto(`/reservations/${collectionFailure.id}`);
  await expect(page.getByRole('heading', { name: '自動収集の結果' })).toBeVisible();
  await expect(page.getByText('一部収集失敗', { exact: true })).toBeVisible();
});
