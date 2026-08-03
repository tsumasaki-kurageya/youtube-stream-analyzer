import { FormEvent, useEffect, useState, type ReactNode } from 'react';

export type Navigate = (path: string) => void;

type ReservationState =
  | 'scheduled'
  | 'monitoring'
  | 'live'
  | 'waiting_for_archive'
  | 'collecting'
  | 'completed'
  | 'cancelled'
  | 'failed';

type CollectionStatus = 'queued' | 'running' | 'succeeded' | 'partial' | 'failed' | 'cancelled' | null;

type Reservation = {
  id: string;
  youtubeVideoId: string;
  sourceUrl: string;
  state: ReservationState;
  scheduledStartAt?: string | null;
  actualStartAt?: string | null;
  actualEndAt?: string | null;
  nextCheckAt: string;
  lastCheckedAt?: string | null;
  monitorAttempt: number;
  lastErrorCode?: string | null;
  lastErrorMessage?: string | null;
  lastErrorRetryable?: boolean | null;
  streamId?: string | null;
  collectionJobId?: string | null;
  collectionStatus?: CollectionStatus;
  collectionErrorCode?: string | null;
  collectionErrorMessage?: string | null;
  canCancel: boolean;
  cancelledAt?: string | null;
  completedAt?: string | null;
  failedAt?: string | null;
  createdAt: string;
  updatedAt: string;
};

type ReservationList = { items: Reservation[]; total: number; limit: number; offset: number };
type ProblemDetails = { code?: string; title?: string; detail?: string };

type PageProps = {
  navigation: ReactNode;
  navigate: Navigate;
};

const stateLabels: Record<ReservationState, string> = {
  scheduled: '予約待ち',
  monitoring: '監視中',
  live: '配信中',
  waiting_for_archive: 'アーカイブ待ち',
  collecting: 'データ収集中',
  completed: '完了',
  cancelled: 'キャンセル済み',
  failed: '失敗',
};

const collectionLabels: Record<Exclude<CollectionStatus, null>, string> = {
  queued: '収集開始待ち',
  running: '収集中',
  succeeded: '収集完了',
  partial: '一部収集失敗',
  failed: '収集失敗',
  cancelled: '収集キャンセル済み',
};

const problemMessages: Record<string, string> = {
  INVALID_RESERVATION_URL: '対応するYouTube配信URLを入力してください。',
  RESERVATION_VIDEO_NOT_FOUND: '動画が見つからないか、公開されていません。',
  RESERVATION_ALREADY_ACTIVE: 'この配信には有効な解析予約があります。',
  RESERVATION_NOT_FOUND: '解析予約が見つかりません。',
  RESERVATION_NOT_CANCELLABLE: 'この状態の解析予約はキャンセルできません。',
  RESERVATION_MONITORING_FAILED: '配信状態の監視に失敗しました。',
  YOUTUBE_ACCESS_DENIED: 'YouTubeから配信情報を取得できませんでした。',
  YOUTUBE_QUOTA_EXCEEDED: 'YouTube APIの利用上限に達しています。',
  YOUTUBE_TEMPORARILY_UNAVAILABLE: 'YouTubeから一時的に情報を取得できません。',
  INVALID_RESERVATION_STATE: '予約状態の指定が不正です。',
  INVALID_PAGINATION: '予約一覧の取得条件が不正です。',
  INTERNAL_ERROR: '処理を完了できませんでした。',
};

const terminalStates = new Set<ReservationState>(['completed', 'cancelled', 'failed']);

function dateTime(value?: string | null) {
  return value ? new Date(value).toLocaleString('ja-JP') : '—';
}

function isActive(state: ReservationState) {
  return !terminalStates.has(state);
}

function youtubeVideoId(value: string) {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/^www\./, '');
    let candidate: string | null = null;
    if (host === 'youtu.be') {
      candidate = url.pathname.split('/').filter(Boolean)[0] ?? null;
    } else if (host === 'youtube.com' || host.endsWith('.youtube.com')) {
      candidate = url.searchParams.get('v');
      if (!candidate) {
        const segments = url.pathname.split('/').filter(Boolean);
        if (['live', 'shorts', 'embed'].includes(segments[0] ?? '')) candidate = segments[1] ?? null;
      }
    }
    return candidate && /^[A-Za-z0-9_-]{11}$/.test(candidate) ? candidate : null;
  } catch {
    return null;
  }
}

async function problemMessage(response: Response) {
  try {
    const problem = (await response.json()) as ProblemDetails;
    return problemMessages[problem.code ?? ''] ?? problem.detail ?? problem.title ?? '処理を完了できませんでした。';
  } catch {
    return '処理を完了できませんでした。';
  }
}

function StateBadge({ state }: { state: ReservationState }) {
  return <span className={`status-pill status-${state}`}>{stateLabels[state]}</span>;
}

function CollectionBadge({ status }: { status?: CollectionStatus }) {
  if (!status) return <span className="muted">未開始</span>;
  return <span className={`status-pill collection-${status}`}>{collectionLabels[status]}</span>;
}

function ReservationThumbnail({ reservation }: { reservation: Pick<Reservation, 'youtubeVideoId' | 'sourceUrl'> }) {
  return (
    <a className="reservation-thumbnail" href={reservation.sourceUrl} target="_blank" rel="noreferrer">
      <img src={`https://i.ytimg.com/vi/${reservation.youtubeVideoId}/hqdefault.jpg`} alt="予約対象のYouTube配信サムネイル" />
      <span>YouTubeで確認</span>
    </a>
  );
}

export function ReservationCreatePage({ navigation, navigate }: PageProps) {
  const [url, setUrl] = useState('');
  const [previewVideoId, setPreviewVideoId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  function preview(event: FormEvent) {
    event.preventDefault();
    setError('');
    const videoId = youtubeVideoId(url.trim());
    if (!videoId) {
      setPreviewVideoId(null);
      setError('対応するYouTube配信URLを入力してください。');
      return;
    }
    setPreviewVideoId(videoId);
  }

  async function createReservation() {
    setSubmitting(true);
    setError('');
    try {
      const response = await fetch('/api/reservations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() }),
      });
      if (!response.ok) throw new Error(await problemMessage(response));
      const reservation = (await response.json()) as Reservation;
      navigate(`/reservations/${reservation.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '解析予約を登録できませんでした。');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main>
      {navigation}
      <header>
        <p className="eyebrow">自動収集</p>
        <h1>解析予約を登録</h1>
        <p>開始前または配信中のYouTubeライブ配信を登録すると、終了後に自動でデータ収集を開始します。</p>
      </header>
      <form onSubmit={preview} noValidate>
        <label htmlFor="reservation-url">YouTube配信URL</label>
        <div className="input-row">
          <input
            id="reservation-url"
            type="url"
            value={url}
            onChange={(event) => {
              setUrl(event.target.value);
              setPreviewVideoId(null);
              setError('');
            }}
            placeholder="https://www.youtube.com/watch?v=..."
            disabled={submitting}
          />
          <button type="submit" disabled={submitting}>予約内容を確認</button>
        </div>
      </form>
      {error && <p role="alert" className="error">{error}</p>}
      {previewVideoId && (
        <section className="reservation-preview" aria-labelledby="reservation-preview-title">
          <ReservationThumbnail reservation={{ youtubeVideoId: previewVideoId, sourceUrl: url.trim() }} />
          <div>
            <p className="eyebrow">予約内容</p>
            <h2 id="reservation-preview-title">この配信を終了後に自動収集します</h2>
            <dl>
              <div><dt>動画ID</dt><dd>{previewVideoId}</dd></div>
              <div><dt>対象URL</dt><dd className="breakable">{url.trim()}</dd></div>
            </dl>
            <p className="muted">登録時にYouTubeへ問い合わせ、開始予定・配信中・終了直後の状態を確認します。</p>
            <div className="actions">
              <button type="button" onClick={createReservation} disabled={submitting}>
                {submitting ? '予約登録中…' : 'この配信を解析予約'}
              </button>
              <button type="button" className="secondary" onClick={() => setPreviewVideoId(null)} disabled={submitting}>URLを修正</button>
            </div>
          </div>
        </section>
      )}
      <button className="secondary page-back" onClick={() => navigate('/reservations')}>予約一覧へ戻る</button>
    </main>
  );
}

export function ReservationListPage({ navigation, navigate }: PageProps) {
  const [data, setData] = useState<ReservationList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function load(silent = false) {
    if (!silent) setLoading(true);
    setError('');
    try {
      const response = await fetch('/api/reservations?limit=100');
      if (!response.ok) throw new Error(await problemMessage(response));
      setData((await response.json()) as ReservationList);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '解析予約一覧を取得できませんでした。');
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);
  const hasActiveReservation = data?.items.some((item) => isActive(item.state)) ?? false;
  useEffect(() => {
    if (!hasActiveReservation) return;
    const timer = window.setInterval(() => { void load(true); }, 10000);
    return () => window.clearInterval(timer);
  }, [hasActiveReservation]);

  return (
    <main>
      {navigation}
      <header className="header-with-action">
        <div>
          <p className="eyebrow">自動収集</p>
          <h1>解析予約</h1>
          <p>配信状態と終了後の自動収集結果を確認できます。</p>
        </div>
        <button onClick={() => navigate('/reservations/new')}>新しい解析予約</button>
      </header>
      {loading && <p role="status">解析予約を読み込み中…</p>}
      {error && <div><p role="alert" className="error">{error}</p><button onClick={() => load()}>再読み込み</button></div>}
      {!loading && !error && data?.total === 0 && (
        <section className="empty">
          <h2>解析予約はありません</h2>
          <p>開始予定または配信中のURLを登録すると、終了後の収集を自動化できます。</p>
          <button onClick={() => navigate('/reservations/new')}>最初の解析予約を登録</button>
        </section>
      )}
      {data && data.items.length > 0 && (
        <ul className="reservation-list" aria-label="解析予約一覧">
          {data.items.map((reservation) => (
            <li key={reservation.id}>
              <button className="reservation-item" onClick={() => navigate(`/reservations/${reservation.id}`)}>
                <img src={`https://i.ytimg.com/vi/${reservation.youtubeVideoId}/mqdefault.jpg`} alt="" />
                <span className="reservation-item-body">
                  <span className="reservation-item-heading">
                    <strong>{reservation.youtubeVideoId}</strong>
                    <StateBadge state={reservation.state} />
                  </span>
                  <span className="reservation-item-meta">
                    {isActive(reservation.state) ? `次回確認 ${dateTime(reservation.nextCheckAt)}` : `更新 ${dateTime(reservation.updatedAt)}`}
                  </span>
                  <span className="reservation-item-meta">収集: {reservation.collectionStatus ? collectionLabels[reservation.collectionStatus] : '未開始'}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

export function ReservationDetailPage({ id, navigation, navigate }: PageProps & { id: string }) {
  const [reservation, setReservation] = useState<Reservation | null>(null);
  const [loading, setLoading] = useState(true);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState('');

  async function load(silent = false) {
    if (!silent) setLoading(true);
    setError('');
    try {
      const response = await fetch(`/api/reservations/${id}`);
      if (!response.ok) throw new Error(await problemMessage(response));
      setReservation((await response.json()) as Reservation);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '解析予約を取得できませんでした。');
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [id]);
  useEffect(() => {
    if (!reservation || !isActive(reservation.state)) return;
    const timer = window.setInterval(() => { void load(true); }, 5000);
    return () => window.clearInterval(timer);
  }, [id, reservation?.state]);

  async function cancel() {
    if (!reservation?.canCancel) return;
    setCancelling(true);
    setError('');
    try {
      const response = await fetch(`/api/reservations/${reservation.id}/cancel`, { method: 'POST' });
      if (!response.ok) throw new Error(await problemMessage(response));
      setReservation((await response.json()) as Reservation);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '解析予約をキャンセルできませんでした。');
    } finally {
      setCancelling(false);
    }
  }

  return (
    <main>
      {navigation}
      {loading && <p role="status">解析予約を読み込み中…</p>}
      {error && !reservation && (
        <section>
          <h1>解析予約を表示できません</h1>
          <p role="alert" className="error">{error}</p>
          <button onClick={() => navigate('/reservations')}>予約一覧へ戻る</button>
        </section>
      )}
      {reservation && (
        <>
          <header className="reservation-detail-header">
            <div>
              <p className="eyebrow">解析予約</p>
              <h1>配信 {reservation.youtubeVideoId}</h1>
            </div>
            <StateBadge state={reservation.state} />
          </header>
          {error && <p role="alert" className="error">{error}</p>}
          <section className="reservation-detail-grid">
            <ReservationThumbnail reservation={reservation} />
            <div className="reservation-status-card">
              <h2>現在の状態</h2>
              <dl>
                <div><dt>予約状態</dt><dd><StateBadge state={reservation.state} /></dd></div>
                <div><dt>次回確認</dt><dd>{isActive(reservation.state) ? dateTime(reservation.nextCheckAt) : '—'}</dd></div>
                <div><dt>最終確認</dt><dd>{dateTime(reservation.lastCheckedAt)}</dd></div>
                <div><dt>監視回数</dt><dd>{reservation.monitorAttempt.toLocaleString('ja-JP')}回</dd></div>
                <div><dt>収集状態</dt><dd><CollectionBadge status={reservation.collectionStatus} /></dd></div>
              </dl>
            </div>
          </section>
          {(reservation.lastErrorMessage || reservation.state === 'failed') && (
            <section className="notice notice-error" aria-labelledby="monitoring-error-title">
              <h2 id="monitoring-error-title">配信監視のエラー</h2>
              <p>{reservation.lastErrorMessage || '配信状態の監視を完了できませんでした。'}</p>
              {reservation.lastErrorCode && <p className="technical-code">エラーコード: {reservation.lastErrorCode}</p>}
              {reservation.lastErrorRetryable === true && <p>一時的なエラーです。次回確認時に自動で再試行します。</p>}
            </section>
          )}
          {(reservation.collectionStatus === 'partial' || reservation.collectionStatus === 'failed' || reservation.collectionErrorMessage) && (
            <section className={`notice ${reservation.collectionStatus === 'partial' ? 'notice-warning' : 'notice-error'}`} aria-labelledby="collection-error-title">
              <h2 id="collection-error-title">自動収集の結果</h2>
              <p>{reservation.collectionErrorMessage || (reservation.collectionStatus === 'partial' ? '一部の収集工程に失敗しました。' : '自動収集に失敗しました。')}</p>
              {reservation.collectionErrorCode && <p className="technical-code">エラーコード: {reservation.collectionErrorCode}</p>}
            </section>
          )}
          <section className="reservation-info" aria-labelledby="reservation-info-title">
            <h2 id="reservation-info-title">配信・予約情報</h2>
            <dl>
              <div><dt>配信予定</dt><dd>{dateTime(reservation.scheduledStartAt)}</dd></div>
              <div><dt>配信開始</dt><dd>{dateTime(reservation.actualStartAt)}</dd></div>
              <div><dt>配信終了</dt><dd>{dateTime(reservation.actualEndAt)}</dd></div>
              <div><dt>予約登録</dt><dd>{dateTime(reservation.createdAt)}</dd></div>
              <div><dt>最終更新</dt><dd>{dateTime(reservation.updatedAt)}</dd></div>
              <div><dt>予約ID</dt><dd className="technical-code">{reservation.id}</dd></div>
            </dl>
          </section>
          <section className="reservation-actions" aria-labelledby="reservation-actions-title">
            <h2 id="reservation-actions-title">操作</h2>
            <div className="actions">
              {reservation.state === 'completed' && reservation.streamId && (
                <button onClick={() => navigate(`/streams/${reservation.streamId}`)}>収集済み配信を開く</button>
              )}
              {reservation.canCancel && (
                <button className="danger" onClick={cancel} disabled={cancelling}>{cancelling ? 'キャンセル中…' : '解析予約をキャンセル'}</button>
              )}
              <button className="secondary" onClick={() => navigate('/reservations')}>予約一覧へ戻る</button>
            </div>
            {!reservation.canCancel && isActive(reservation.state) && <p className="muted">データ収集開始後の予約はキャンセルできません。</p>}
            {terminalStates.has(reservation.state) && reservation.state !== 'completed' && <p className="muted">終了済みの予約に対する操作はありません。</p>}
          </section>
        </>
      )}
    </main>
  );
}
