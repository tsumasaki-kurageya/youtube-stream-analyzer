import { FormEvent, StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

type StreamMetadata = {
  youtubeVideoId: string;
  title: string;
  channelTitle: string;
  thumbnailUrl: string;
  actualStartAt: string;
  actualEndAt: string;
  durationSeconds: number;
};

type RegisteredStream = StreamMetadata & { id: string; sourceUrl: string };
type ProblemDetails = { code?: string; title?: string };

const messages: Record<string, string> = {
  INVALID_YOUTUBE_URL: '対応するYouTube配信URLを入力してください。',
  YOUTUBE_VIDEO_NOT_FOUND: '動画が見つからないか、公開されていません。',
  NOT_ENDED_LIVE_STREAM: '終了済みのライブ配信を指定してください。',
  YOUTUBE_ACCESS_DENIED: 'YouTubeから情報を取得できませんでした。',
  YOUTUBE_QUOTA_EXCEEDED: 'YouTube APIの利用上限に達しています。',
  YOUTUBE_TEMPORARILY_UNAVAILABLE: 'YouTubeから一時的に情報を取得できません。',
  INTERNAL_ERROR: '配信を登録できませんでした。',
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

function App() {
  const [url, setUrl] = useState('');
  const [metadata, setMetadata] = useState<StreamMetadata | null>(null);
  const [registered, setRegistered] = useState<RegisteredStream | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [registering, setRegistering] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setMetadata(null);
    setRegistered(null);
    if (!url.trim()) {
      setError('YouTube配信URLを入力してください。');
      return;
    }
    setLoading(true);
    try {
      const response = await fetch('/api/streams/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() }),
      });
      if (!response.ok) throw new Error(await problemMessage(response));
      setMetadata((await response.json()) as StreamMetadata);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '配信情報を取得できませんでした。');
    } finally {
      setLoading(false);
    }
  }

  async function register() {
    setError('');
    setRegistering(true);
    try {
      const response = await fetch('/api/streams', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() }),
      });
      if (!response.ok) throw new Error(await problemMessage(response));
      const stream = (await response.json()) as RegisteredStream;
      setRegistered(stream);
      setMetadata(null);
      window.history.pushState({}, '', `/streams/${stream.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '配信を登録できませんでした。');
    } finally {
      setRegistering(false);
    }
  }

  function reset() {
    setMetadata(null);
    setRegistered(null);
    setError('');
    setUrl('');
    window.history.pushState({}, '', '/');
  }

  return (
    <main>
      <header>
        <p className="eyebrow">YouTube Stream Analyzer</p>
        <h1>{registered ? '配信を登録しました' : '配信を登録'}</h1>
        <p>終了済みのYouTubeライブ配信URLを確認してから登録します。</p>
      </header>

      {!registered && (
        <form onSubmit={submit} noValidate>
          <label htmlFor="stream-url">YouTube配信URL</label>
          <div className="input-row">
            <input
              id="stream-url"
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://www.youtube.com/watch?v=..."
              aria-describedby={error ? 'form-error' : undefined}
              disabled={loading || registering}
            />
            <button type="submit" disabled={loading || registering}>{loading ? '確認中…' : '配信情報を確認'}</button>
          </div>
        </form>
      )}

      {error && <p id="form-error" role="alert" className="error">{error}</p>}

      {metadata && (
        <section className="preview" aria-labelledby="preview-title">
          <img src={metadata.thumbnailUrl} alt="" />
          <div>
            <p className="eyebrow">登録内容の確認</p>
            <h2 id="preview-title">{metadata.title}</h2>
            <dl>
              <div><dt>チャンネル</dt><dd>{metadata.channelTitle}</dd></div>
              <div><dt>配信開始</dt><dd>{new Date(metadata.actualStartAt).toLocaleString('ja-JP')}</dd></div>
              <div><dt>動画時間</dt><dd>{duration(metadata.durationSeconds)}</dd></div>
            </dl>
            <div className="actions">
              <button type="button" onClick={register} disabled={registering}>{registering ? '登録中…' : 'この配信を登録'}</button>
              <button type="button" className="secondary" onClick={reset} disabled={registering}>別のURLを確認</button>
            </div>
          </div>
        </section>
      )}

      {registered && (
        <section className="preview" aria-labelledby="registered-title">
          <img src={registered.thumbnailUrl} alt="" />
          <div>
            <p className="eyebrow">登録済み</p>
            <h2 id="registered-title">{registered.title}</h2>
            <p>{registered.channelTitle}</p>
            <p role="status">同じURLを再登録しても、この配信が重複して作成されることはありません。</p>
            <button type="button" className="secondary" onClick={reset}>別の配信を登録</button>
          </div>
        </section>
      )}
    </main>
  );
}

const root = document.getElementById('root');
if (!root) throw new Error('root element not found');
createRoot(root).render(<StrictMode><App /></StrictMode>);
