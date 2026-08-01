import { FormEvent, StrictMode, useEffect, useState, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

type Stream = {
  id: string;
  youtubeVideoId: string;
  sourceUrl: string;
  title: string;
  channelTitle: string;
  thumbnailUrl: string;
  actualStartAt: string;
  actualEndAt: string;
  durationSeconds: number;
  createdAt: string;
};
type StreamList = { items: Stream[]; total: number };
type ProblemDetails = { code?: string; title?: string };

const messages: Record<string, string> = {
  INVALID_YOUTUBE_URL: '対応するYouTube配信URLを入力してください。',
  YOUTUBE_VIDEO_NOT_FOUND: '動画が見つからないか、公開されていません。',
  NOT_ENDED_LIVE_STREAM: '終了済みのライブ配信を指定してください。',
  YOUTUBE_ACCESS_DENIED: 'YouTubeから情報を取得できませんでした。',
  YOUTUBE_QUOTA_EXCEEDED: 'YouTube APIの利用上限に達しています。',
  YOUTUBE_TEMPORARILY_UNAVAILABLE: 'YouTubeから一時的に情報を取得できません。',
  STREAM_NOT_FOUND: '配信が見つかりません。',
  INTERNAL_ERROR: '処理を完了できませんでした。',
};

function duration(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  return [hours, minutes, rest].map((value) => String(value).padStart(2, '0')).join(':');
}

async function problemMessage(response: Response) {
  const problem = (await response.json()) as ProblemDetails;
  return messages[problem.code ?? ''] ?? problem.title ?? '処理を完了できませんでした。';
}

function navigate(path: string) {
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

function App() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const listener = () => setPath(window.location.pathname);
    window.addEventListener('popstate', listener);
    return () => window.removeEventListener('popstate', listener);
  }, []);

  if (path === '/' || path === '/register') return <RegisterPage />;
  if (path === '/streams') return <ListPage />;
  const match = path.match(/^\/streams\/([^/]+)$/);
  if (match) return <DetailPage id={match[1]} />;
  return <NotFoundPage />;
}

function Navigation() {
  return <nav aria-label="主要ナビゲーション"><button className="link" onClick={() => navigate('/streams')}>登録済み配信</button><button className="link" onClick={() => navigate('/register')}>配信を登録</button></nav>;
}

function RegisterPage() {
  const [url, setUrl] = useState('');
  const [preview, setPreview] = useState<Stream | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [registering, setRegistering] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setPreview(null);
    if (!url.trim()) { setError('YouTube配信URLを入力してください。'); return; }
    setLoading(true);
    try {
      const response = await fetch('/api/streams/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: url.trim() }) });
      if (!response.ok) throw new Error(await problemMessage(response));
      setPreview((await response.json()) as Stream);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '配信情報を取得できませんでした。'); }
    finally { setLoading(false); }
  }

  async function register() {
    setError(''); setRegistering(true);
    try {
      const response = await fetch('/api/streams', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: url.trim() }) });
      if (!response.ok) throw new Error(await problemMessage(response));
      const stream = (await response.json()) as Stream;
      navigate(`/streams/${stream.id}`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '配信を登録できませんでした。'); }
    finally { setRegistering(false); }
  }

  return <main><Navigation /><header><p className="eyebrow">YouTube Stream Analyzer</p><h1>配信を登録</h1><p>終了済みのYouTubeライブ配信URLを確認してから登録します。</p></header>
    <form onSubmit={submit} noValidate><label htmlFor="stream-url">YouTube配信URL</label><div className="input-row"><input id="stream-url" type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://www.youtube.com/watch?v=..." disabled={loading || registering}/><button type="submit" disabled={loading || registering}>{loading ? '確認中…' : '配信情報を確認'}</button></div></form>
    {error && <p role="alert" className="error">{error}</p>}
    {preview && <StreamCard stream={preview}><div className="actions"><button type="button" onClick={register} disabled={registering}>{registering ? '登録中…' : 'この配信を登録'}</button><button type="button" className="secondary" onClick={() => { setPreview(null); setUrl(''); }}>別のURLを確認</button></div></StreamCard>}
  </main>;
}

function ListPage() {
  const [data, setData] = useState<StreamList | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  async function load() {
    setLoading(true); setError('');
    try { const response = await fetch('/api/streams'); if (!response.ok) throw new Error(await problemMessage(response)); setData((await response.json()) as StreamList); }
    catch (reason) { setError(reason instanceof Error ? reason.message : '配信一覧を取得できませんでした。'); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);
  return <main><Navigation /><header><p className="eyebrow">YouTube Stream Analyzer</p><h1>登録済み配信</h1></header>
    {loading && <p role="status">読み込み中…</p>}
    {error && <div><p role="alert" className="error">{error}</p><button onClick={load}>再読み込み</button></div>}
    {!loading && !error && data?.total === 0 && <section className="empty"><h2>登録済み配信はありません</h2><p>終了済みの配信URLを登録すると、ここから確認できます。</p><button onClick={() => navigate('/register')}>最初の配信を登録</button></section>}
    {data && data.items.length > 0 && <ul className="stream-list">{data.items.map((stream) => <li key={stream.id}><button className="stream-item" onClick={() => navigate(`/streams/${stream.id}`)}><img src={stream.thumbnailUrl} alt=""/><span><strong>{stream.title}</strong><small>{stream.channelTitle} · {new Date(stream.createdAt).toLocaleString('ja-JP')}</small></span></button></li>)}</ul>}
  </main>;
}

function DetailPage({ id }: { id: string }) {
  const [stream, setStream] = useState<Stream | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => { (async () => { try { const response = await fetch(`/api/streams/${id}`); if (!response.ok) throw new Error(await problemMessage(response)); setStream((await response.json()) as Stream); } catch (reason) { setError(reason instanceof Error ? reason.message : '配信情報を取得できませんでした。'); } finally { setLoading(false); } })(); }, [id]);
  return <main><Navigation />{loading && <p role="status">読み込み中…</p>}{error && <section><h1>配信を表示できません</h1><p role="alert" className="error">{error}</p><button onClick={() => navigate('/streams')}>一覧へ戻る</button></section>}{stream && <><header><p className="eyebrow">登録済み配信</p><h1>{stream.title}</h1></header><StreamCard stream={stream}><p><a href={stream.sourceUrl} target="_blank" rel="noreferrer">YouTubeで元配信を開く</a></p><button className="secondary" onClick={() => navigate('/streams')}>一覧へ戻る</button></StreamCard></>}</main>;
}

function StreamCard({ stream, children }: { stream: Stream; children?: ReactNode }) {
  return <section className="preview"><img src={stream.thumbnailUrl} alt=""/><div><h2>{stream.title}</h2><dl><div><dt>チャンネル</dt><dd>{stream.channelTitle}</dd></div><div><dt>配信開始</dt><dd>{new Date(stream.actualStartAt).toLocaleString('ja-JP')}</dd></div><div><dt>配信終了</dt><dd>{new Date(stream.actualEndAt).toLocaleString('ja-JP')}</dd></div><div><dt>動画時間</dt><dd>{duration(stream.durationSeconds)}</dd></div></dl>{children}</div></section>;
}
function NotFoundPage() { return <main><Navigation /><h1>ページが見つかりません</h1><button onClick={() => navigate('/streams')}>配信一覧へ</button></main>; }

const root = document.getElementById('root');
if (!root) throw new Error('root element not found');
createRoot(root).render(<StrictMode><App /></StrictMode>);
