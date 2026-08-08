import { expect, test, type APIRequestContext, type Page, type TestInfo } from '@playwright/test';

type Step = { name: string; status: string; attempt: number; errorCode?: string | null };
type Job = { id: string; status: string; steps: Step[] };
type Stream = { id: string };
type PageResult = { items: unknown[] };

function videoID(prefix: 'm3norm' | 'm3none' | 'm3fail', testInfo: TestInfo): string {
  return `${prefix}0000${testInfo.retry}`;
}

async function register(request: APIRequestContext, id: string): Promise<Stream> {
  const response = await request.post('/api/streams', {
    data: { url: `https://www.youtube.com/watch?v=${id}` },
  });
  expect(response.status()).toBe(201);
  return await response.json() as Stream;
}

async function startFull(request: APIRequestContext, streamID: string): Promise<Job> {
  const response = await request.post(`/api/streams/${streamID}/collections`);
  expect(response.status()).toBe(202);
  return await response.json() as Job;
}

async function waitForJob(
  request: APIRequestContext,
  streamID: string,
  expected: string,
): Promise<Job> {
  await expect.poll(async () => {
    const response = await request.get(`/api/streams/${streamID}/collections/latest`);
    if (!response.ok()) return `HTTP ${response.status()}`;
    return ((await response.json()) as Job).status;
  }, { timeout: 30_000, intervals: [200, 500, 1000] }).toBe(expected);
  const response = await request.get(`/api/streams/${streamID}/collections/latest`);
  return await response.json() as Job;
}

async function count(request: APIRequestContext, path: string): Promise<number> {
  const response = await request.get(path);
  expect(response.ok()).toBeTruthy();
  return ((await response.json()) as PageResult).items.length;
}

async function installPlayer(page: Page) {
  await page.addInitScript(() => {
    const state = { current: 0 };
    Object.assign(window, { __ysaM3CompletionPlayer: state });
    Object.assign(window, {
      __YSA_YOUTUBE_PLAYER_FACTORY__: (
        element: HTMLElement,
        _videoId: string,
        onReady: (adapter: unknown) => void,
      ) => {
        const frame = document.createElement('iframe');
        frame.title = 'M3 completion player';
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

test('複数工程収集から同期閲覧・検索・再収集の重複防止まで完了する', async ({ page, request }, testInfo) => {
  const stream = await register(request, videoID('m3norm', testInfo));
  await startFull(request, stream.id);
  const firstJob = await waitForJob(request, stream.id, 'succeeded');
  expect(Object.fromEntries(firstJob.steps.map((step) => [step.name, step.status]))).toEqual({
    metadata: 'succeeded',
    chat_replay: 'succeeded',
    transcript: 'succeeded',
  });

  const initialChatCount = await count(request, `/api/streams/${stream.id}/chat-messages?limit=200`);
  const initialTranscriptCount = await count(request, `/api/streams/${stream.id}/transcript-segments?limit=200`);
  expect(initialChatCount).toBeGreaterThan(0);
  expect(initialTranscriptCount).toBe(3);

  await installPlayer(page);
  await page.goto(`/streams/${stream.id}`);
  await expect(page.getByRole('heading', { name: 'チャット・字幕', exact: true })).toBeVisible();
  await expect(page.getByRole('list', { name: '現在時刻周辺の字幕' })).toContainText('最初の字幕');
  await page.getByRole('list', { name: '現在時刻周辺の字幕' }).getByRole('button').first().click();
  await expect(page.getByLabel('現在の再生時刻')).toHaveText('00:00:01');

  await page.getByLabel('検索語').fill('重要');
  await expect(page.getByRole('list', { name: 'チャット・字幕検索結果' })).toContainText('重要な検索対象の字幕');
  await page.getByRole('button', { name: /字幕 · 00:03:00/ }).click();
  await expect(page.getByLabel('現在の再生時刻')).toHaveText('00:03:00');

  await startFull(request, stream.id);
  await waitForJob(request, stream.id, 'succeeded');
  expect(await count(request, `/api/streams/${stream.id}/chat-messages?limit=200`)).toBe(initialChatCount);
  expect(await count(request, `/api/streams/${stream.id}/transcript-segments?limit=200`)).toBe(initialTranscriptCount);
});

test('字幕なしをno_dataとして正常完了する', async ({ request }, testInfo) => {
  const stream = await register(request, videoID('m3none', testInfo));
  await startFull(request, stream.id);
  const job = await waitForJob(request, stream.id, 'succeeded');
  expect(job.steps.find((step) => step.name === 'transcript')?.status).toBe('no_data');
  expect(await count(request, `/api/streams/${stream.id}/transcript-segments?limit=200`)).toBe(0);
});

test('字幕の一時障害を部分失敗として工程単位で再実行できる', async ({ request }, testInfo) => {
  const stream = await register(request, videoID('m3fail', testInfo));
  await startFull(request, stream.id);
  const partial = await waitForJob(request, stream.id, 'partial');
  const transcript = partial.steps.find((step) => step.name === 'transcript');
  expect(transcript?.status).toBe('failed');
  expect(transcript?.errorCode).toBe('TRANSCRIPT_TEMPORARILY_UNAVAILABLE');

  const retry = await request.post(`/api/collection-jobs/${partial.id}/steps/transcript/retry`);
  expect(retry.status()).toBe(202);
  const completed = await waitForJob(request, stream.id, 'succeeded');
  expect(completed.steps.find((step) => step.name === 'transcript')?.attempt).toBe(2);
  expect(await count(request, `/api/streams/${stream.id}/transcript-segments?limit=200`)).toBe(3);
});
