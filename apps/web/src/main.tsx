import { FormEvent, StrictMode, useEffect, useState, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import { ReservationCreatePage, ReservationDetailPage, ReservationListPage } from './reservation-pages';
import { YouTubePlayer } from './youtube-player';

type Stream = {
  id: string; youtubeVideoId: string; sourceUrl: string; title: string; channelTitle: string;
  thumbnailUrl: string; actualStartAt: string; actualEndAt: string; durationSeconds: number; createdAt: string;
};
type StreamList = { items: Stream[]; total: number };
type ProblemDetails = { code?: string; title?: string };
type CollectionStatus = 'queued' | 'running' | 'succeeded' | 'failed';
type CollectionStep = { id: string; name: string; status: CollectionStatus; progressCount: number; errorMessage?: string | null; heartbeatAt?: string | null; leaseExpiresAt?: string | null; startedAt?: string | null; finishedAt?: string | null };
type CollectionJob = { id: string; streamId: string; kind: string; status: CollectionStatus; attempt: number; progressCount: number; errorMessage?: string | null; startedAt?: string | null; finishedAt?: string | null; createdAt: string; updatedAt: string; steps: CollectionStep[] };
type ChatMessage = { id: string; externalMessageId: string; authorExternalId?: string | null; authorName: string; messageText: string; publishedAt: string; elapsedMilliseconds: number };
type ChatPage = { items: ChatMessage[]; nextCursor?: string | null };

const messages: Record<string, string> = {
  INVALID_YOUTUBE_URL: '対応するYouTube配信URLを入力してください。', YOUTUBE_VIDEO_NOT_FOUND: '動画が見つからないか、公開されていません。',
  NOT_ENDED_LIVE_STREAM: '終了済みのライブ配信を指定してください。', YOUTUBE_ACCESS_DENIED: 'YouTubeから情報を取得できませんでした。',
  YOUTUBE_QUOTA_EXCEEDED: 'YouTube APIの利用上限に達しています。', YOUTUBE_TEMPORARILY_UNAVAILABLE: 'YouTubeから一時的に情報を取得できません。',
  STREAM_NOT_FOUND: '配信が見つかりません。', COLLECTION_JOB_NOT_FOUND: 'チャット収集はまだ開始されていません。',
  COLLECTION_ALREADY_ACTIVE: 'チャット収集はすでに開始されています。', COLLECTION_JOB_NOT_RETRYABLE: 'この収集ジョブは再実行できません。',
  INVALID_CURSOR: 'チャットのページ位置が不正です。', INVALID_PAGINATION: 'ページ件数の指定が不正です。', INTERNAL_ERROR: '処理を完了できませんでした。',
};
const collectionLabels: Record<CollectionStatus, string> = { queued: '開始待ち', running: '収集中', succeeded: '収集完了', failed: '収集失敗' };

function duration(seconds: number) { const h = Math.floor(seconds / 3600); const m = Math.floor((seconds % 3600) / 60); const s = seconds % 60; return [h, m, s].map((v) => String(v).padStart(2, '0')).join(':'); }
function elapsed(milliseconds: number) { return duration(Math.floor(milliseconds / 1000)); }
function dateTime(value?: string | null) { return value ? new Date(value).toLocaleString('ja-JP') : '—'; }
function timeAgo(value?: string | null) { if (!value) return '応答待ち'; const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000)); if (seconds < 10) return 'たった今'; if (seconds < 60) return `${seconds}秒前`; const minutes = Math.floor(seconds / 60); if (minutes < 60) return `${minutes}分前`; return `${Math.floor(minutes / 60)}時間前`; }
async function problemMessage(response: Response) { const problem = (await response.json()) as ProblemDetails; return messages[problem.code ?? ''] ?? problem.title ?? '処理を完了できませんでした。'; }
function navigate(path: string) { window.history.pushState({}, '', path); window.dispatchEvent(new PopStateEvent('popstate')); }

function App() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => { const listener = () => setPath(window.location.pathname); window.addEventListener('popstate', listener); return () => window.removeEventListener('popstate', listener); }, []);
  if (path === '/' || path === '/register') return <RegisterPage />;
  if (path === '/streams') return <ListPage />;
  if (path === '/reservations') return <ReservationListPage navigation={<Navigation />} navigate={navigate} />;
  if (path === '/reservations/new') return <ReservationCreatePage navigation={<Navigation />} navigate={navigate} />;
  const reservationMatch = path.match(/^\/reservations\/([^/]+)$/);
  if (reservationMatch) return <ReservationDetailPage id={reservationMatch[1]} navigation={<Navigation />} navigate={navigate} />;
  const chatMatch = path.match(/^\/streams\/([^/]+)\/chat$/);
  if (chatMatch) return <ChatPageView id={chatMatch[1]} />;
  const match = path.match(/^\/streams\/([^/]+)$/);
  if (match) return <DetailPage id={match[1]} />;
  return <NotFoundPage />;
}

function Navigation() {
  const path = window.location.pathname;
  const item = (href: string, label: string, active: boolean) => (
    <button className="link" aria-current={active ? 'page' : undefined} onClick={() => navigate(href)}>{label}</button>
  );
  return (
    <nav aria-label="主要ナビゲーション">
      <button className="brand" onClick={() => navigate('/streams')} aria-label="YouTube Stream Analyzer ホーム">
        <span className="brand-mark" aria-hidden="true"><i /><i /><i /><i /><i /></span>
        <span><strong>YSA</strong><small>Stream analyzer</small></span>
      </button>
      <div className="nav-links">
        {item('/reservations', '解析予約', path.startsWith('/reservations'))}
        {item('/streams', '配信ライブラリ', path.startsWith('/streams'))}
        {item('/register', '配信を登録', path === '/' || path === '/register')}
      </div>
    </nav>
  );
}

function RegisterPage() {
  const [url, setUrl] = useState(''); const [preview, setPreview] = useState<Stream | null>(null); const [error, setError] = useState(''); const [loading, setLoading] = useState(false); const [registering, setRegistering] = useState(false);
  async function submit(event: FormEvent) { event.preventDefault(); setError(''); setPreview(null); if (!url.trim()) { setError('YouTube配信URLを入力してください。'); return; } setLoading(true); try { const response = await fetch('/api/streams/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: url.trim() }) }); if (!response.ok) throw new Error(await problemMessage(response)); setPreview((await response.json()) as Stream); } catch (reason) { setError(reason instanceof Error ? reason.message : '配信情報を取得できませんでした。'); } finally { setLoading(false); } }
  async function register() { setError(''); setRegistering(true); try { const response = await fetch('/api/streams', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: url.trim() }) }); if (!response.ok) throw new Error(await problemMessage(response)); const stream = (await response.json()) as Stream; navigate(`/streams/${stream.id}`); } catch (reason) { setError(reason instanceof Error ? reason.message : '配信を登録できませんでした。'); } finally { setRegistering(false); } }
  return <main><Navigation /><header><p className="eyebrow">YouTube Stream Analyzer</p><h1>配信を登録</h1><p>終了済みのYouTubeライブ配信URLを確認してから登録します。</p></header><form onSubmit={submit} noValidate><label htmlFor="stream-url">YouTube配信URL</label><div className="input-row"><input id="stream-url" type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://www.youtube.com/watch?v=..." disabled={loading || registering}/><button type="submit" disabled={loading || registering}>{loading ? '確認中…' : '配信情報を確認'}</button></div></form>{error && <p role="alert" className="error">{error}</p>}{preview && <StreamCard stream={preview}><div className="actions"><button type="button" onClick={register} disabled={registering}>{registering ? '登録中…' : 'この配信を登録'}</button><button type="button" className="secondary" onClick={() => { setPreview(null); setUrl(''); }}>別のURLを確認</button></div></StreamCard>}</main>;
}

function ListPage() {
  const [data, setData] = useState<StreamList | null>(null); const [error, setError] = useState(''); const [loading, setLoading] = useState(true);
  async function load() { setLoading(true); setError(''); try { const response = await fetch('/api/streams'); if (!response.ok) throw new Error(await problemMessage(response)); setData((await response.json()) as StreamList); } catch (reason) { setError(reason instanceof Error ? reason.message : '配信一覧を取得できませんでした。'); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, []);
  return <main><Navigation /><header><p className="eyebrow">YouTube Stream Analyzer</p><h1>登録済み配信</h1></header>{loading && <p role="status">読み込み中…</p>}{error && <div><p role="alert" className="error">{error}</p><button onClick={load}>再読み込み</button></div>}{!loading && !error && data?.total === 0 && <section className="empty"><h2>登録済み配信はありません</h2><p>終了済みの配信URLを登録すると、ここから確認できます。</p><button onClick={() => navigate('/register')}>最初の配信を登録</button></section>}{data && data.items.length > 0 && <ul className="stream-list">{data.items.map((stream) => <li key={stream.id}><button className="stream-item" onClick={() => navigate(`/streams/${stream.id}`)}><img src={stream.thumbnailUrl} alt=""/><span><strong>{stream.title}</strong><small>{stream.channelTitle} · {new Date(stream.createdAt).toLocaleString('ja-JP')}</small></span></button></li>)}</ul>}</main>;
}

function DetailPage({ id }: { id: string }) {
  const [stream, setStream] = useState<Stream | null>(null); const [error, setError] = useState(''); const [loading, setLoading] = useState(true);
  useEffect(() => { (async () => { try { const response = await fetch(`/api/streams/${id}`); if (!response.ok) throw new Error(await problemMessage(response)); setStream((await response.json()) as Stream); } catch (reason) { setError(reason instanceof Error ? reason.message : '配信情報を取得できませんでした。'); } finally { setLoading(false); } })(); }, [id]);
  return <main><Navigation />{loading && <p role="status">読み込み中…</p>}{error && <section><h1>配信を表示できません</h1><p role="alert" className="error">{error}</p><button onClick={() => navigate('/streams')}>一覧へ戻る</button></section>}{stream && <><header><p className="eyebrow">登録済み配信</p><h1>{stream.title}</h1></header><YouTubePlayer videoId={stream.youtubeVideoId} sourceUrl={stream.sourceUrl} durationSeconds={stream.durationSeconds} /><StreamCard stream={stream}><p><a href={stream.sourceUrl} target="_blank" rel="noreferrer">YouTubeで元配信を開く</a></p><button className="secondary" onClick={() => navigate('/streams')}>一覧へ戻る</button></StreamCard><CollectionPanel streamId={stream.id} /></>}</main>;
}

function CollectionPanel({ streamId }: { streamId: string }) {
  const [job, setJob] = useState<CollectionJob | null>(null); const [loading, setLoading] = useState(true); const [submitting, setSubmitting] = useState(false); const [error, setError] = useState('');
  async function load(silent = false) { if (!silent) setLoading(true); try { const response = await fetch(`/api/streams/${streamId}/chat-collections/latest`); if (response.status === 404) { setJob(null); setError(''); return; } if (!response.ok) throw new Error(await problemMessage(response)); setJob((await response.json()) as CollectionJob); setError(''); } catch (reason) { setError(reason instanceof Error ? reason.message : '収集状態を取得できませんでした。'); } finally { if (!silent) setLoading(false); } }
  useEffect(() => { void load(); }, [streamId]);
  useEffect(() => { if (job?.status !== 'queued' && job?.status !== 'running') return; const timer = window.setInterval(() => { void load(true); }, 3000); return () => window.clearInterval(timer); }, [job?.status, streamId]);
  async function start() { setSubmitting(true); setError(''); try { const response = await fetch(`/api/streams/${streamId}/chat-collections`, { method: 'POST' }); if (!response.ok) throw new Error(await problemMessage(response)); setJob((await response.json()) as CollectionJob); } catch (reason) { setError(reason instanceof Error ? reason.message : 'チャット収集を開始できませんでした。'); } finally { setSubmitting(false); } }
  async function retry() { if (!job) return; setSubmitting(true); setError(''); try { const response = await fetch(`/api/collection-jobs/${job.id}/retry`, { method: 'POST' }); if (!response.ok) throw new Error(await problemMessage(response)); setJob((await response.json()) as CollectionJob); } catch (reason) { setError(reason instanceof Error ? reason.message : 'チャット収集を再実行できませんでした。'); } finally { setSubmitting(false); } }
  const currentStep = job?.steps.find((step) => step.status === 'running') ?? job?.steps[0];
  const heartbeatStopped = job?.status === 'running' && !!currentStep?.leaseExpiresAt && new Date(currentStep.leaseExpiresAt).getTime() <= Date.now();
  return <section className="preview" aria-labelledby="chat-collection-title"><div><h2 id="chat-collection-title">チャット収集</h2>{loading && <p role="status">収集状態を確認中…</p>}{error && <p role="alert" className="error">{error}</p>}{!loading && !job && <><p>ライブチャットをバックグラウンドで収集します。画面を閉じても処理は継続します。</p><button onClick={start} disabled={submitting}>{submitting ? '開始中…' : 'チャット収集を開始'}</button></>}{job && <><p role="status"><strong>{collectionLabels[job.status]}</strong></p><dl><div><dt>現在工程</dt><dd>{currentStep?.name === 'chat_replay' ? 'チャットリプレイ取得' : currentStep?.name ?? '—'}</dd></div><div><dt>取得件数</dt><dd>{job.progressCount.toLocaleString('ja-JP')}件</dd></div><div><dt>試行回数</dt><dd>{job.attempt}</dd></div><div><dt>開始時刻</dt><dd>{dateTime(job.startedAt ?? job.createdAt)}</dd></div><div><dt>更新時刻</dt><dd>{dateTime(job.updatedAt)}</dd></div>{job.status === 'running' && <div><dt>ワーカー最終応答</dt><dd>{timeAgo(currentStep?.heartbeatAt)}</dd></div>}</dl>{job.status === 'queued' && <p>ワーカーの開始待ちです。このページを閉じても収集は継続します。</p>}{job.status === 'running' && !heartbeatStopped && <p>収集はバックグラウンドで進行しています。</p>}{heartbeatStopped && <p role="alert" className="error">ワーカーからの応答が途絶えています。収集が停止している可能性があります。</p>}{job.status === 'failed' && <><p className="error">{job.errorMessage || currentStep?.errorMessage || 'チャット収集に失敗しました。'}</p><button onClick={retry} disabled={submitting}>{submitting ? '再実行中…' : 'チャット収集を再実行'}</button></>}{job.status === 'succeeded' && <button onClick={() => navigate(`/streams/${streamId}/chat`)}>収集したチャットを見る</button>}</>}</div></section>;
}

function ChatPageView({ id }: { id: string }) {
  const [stream, setStream] = useState<Stream | null>(null); const [items, setItems] = useState<ChatMessage[]>([]); const [cursor, setCursor] = useState<string | null>(null); const [loading, setLoading] = useState(true); const [loadingMore, setLoadingMore] = useState(false); const [error, setError] = useState('');
  async function load(reset = true) { reset ? setLoading(true) : setLoadingMore(true); setError(''); try { if (reset && !stream) { const streamResponse = await fetch(`/api/streams/${id}`); if (!streamResponse.ok) throw new Error(await problemMessage(streamResponse)); setStream((await streamResponse.json()) as Stream); } const suffix = !reset && cursor ? `?limit=100&cursor=${encodeURIComponent(cursor)}` : '?limit=100'; const response = await fetch(`/api/streams/${id}/chat-messages${suffix}`); if (!response.ok) throw new Error(await problemMessage(response)); const page = (await response.json()) as ChatPage; setItems((current) => reset ? page.items : [...current, ...page.items]); setCursor(page.nextCursor ?? null); } catch (reason) { setError(reason instanceof Error ? reason.message : 'チャットを取得できませんでした。'); } finally { setLoading(false); setLoadingMore(false); } }
  useEffect(() => { void load(true); }, [id]);
  return <main><Navigation /><header><p className="eyebrow">収集済みチャット</p><h1>{stream?.title ?? 'チャット時系列'}</h1><button className="secondary" onClick={() => navigate(`/streams/${id}`)}>配信詳細へ戻る</button></header>{loading && <p role="status">チャットを読み込み中…</p>}{error && <div><p role="alert" className="error">{error}</p><button onClick={() => load(true)}>再読み込み</button></div>}{!loading && !error && items.length === 0 && <section className="empty"><h2>収集済みチャットはありません</h2><p>収集完了後も0件の場合、対象配信に保存可能なチャットがありません。</p></section>}{items.length > 0 && <><ol aria-label="チャット時系列" className="chat-list">{items.map((item) => <li key={item.id}><time dateTime={item.publishedAt}>{elapsed(item.elapsedMilliseconds)}</time><div><strong>{item.authorName}</strong><p>{item.messageText || '（本文なし）'}</p></div></li>)}</ol>{cursor && <button onClick={() => load(false)} disabled={loadingMore}>{loadingMore ? '読み込み中…' : '次の100件を読み込む'}</button>}</>}</main>;
}

function StreamCard({ stream, children }: { stream: Stream; children?: ReactNode }) { return <section className="preview"><img src={stream.thumbnailUrl} alt=""/><div><h2>{stream.title}</h2><dl><div><dt>チャンネル</dt><dd>{stream.channelTitle}</dd></div><div><dt>配信開始</dt><dd>{new Date(stream.actualStartAt).toLocaleString('ja-JP')}</dd></div><div><dt>配信終了</dt><dd>{new Date(stream.actualEndAt).toLocaleString('ja-JP')}</dd></div><div><dt>動画時間</dt><dd>{duration(stream.durationSeconds)}</dd></div></dl>{children}</div></section>; }
function NotFoundPage() { return <main><Navigation /><h1>ページが見つかりません</h1><button onClick={() => navigate('/streams')}>配信一覧へ</button></main>; }
const root = document.getElementById('root'); if (!root) throw new Error('root element not found'); createRoot(root).render(<StrictMode><App /></StrictMode>);
