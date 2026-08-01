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

type ProblemDetails = { code?: string; title?: string };

const messages: Record<string, string> = {
  INVALID_YOUTUBE_URL: '対応するYouTube配信URLを入力してください。',
  YOUTUBE_VIDEO_NOT_FOUND: '動画が見つからないか、公開されていません。',
  NOT_ENDED_LIVE_STREAM: '終了済みのライブ配信を指定してください。',
  YOUTUBE_ACCESS_DENIED: 'YouTubeから情報を取得できませんでした。',
  YOUTUBE_QUOTA_EXCEEDED: 'YouTube APIの利用上限に達しています。',
  YOUTUBE_TEMPORARILY_UNAVAILABLE: 'YouTubeから一時的に情報を取得できません。',
};

function duration(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  return [hours, minutes, rest].map((value) => String(value).padStart(2, '0')).join(':');
}

function App() {
  const [url, setUrl] = useState('');
  const [metadata, setMetadata] = useState<StreamMetadata | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setMetadata(null);
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
      if (!response.ok) {
        const problem = (await response.json()) as ProblemDetails;
        throw new Error(messages[problem.code ?? ''] ?? problem.title ?? '配信情報を取得できませんでした。');
      }
      setMetadata((await response.json()) as StreamMetadata);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '配信情報を取得できませんでした。');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <header>
        <p className="eyebrow">YouTube Stream Analyzer</p>
        <h1>配信情報を確認</h1>
        <p>終了済みのYouTubeライブ配信URLから、登録前に配信情報を確認します。</p>
      </header>

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
          />
          <button type="submit" disabled={loading}>{loading ? '確認中…' : '配信情報を確認'}</button>
        </div>
        {error && <p id="form-error" role="alert" className="error">{error}</p>}
      </form>

      {metadata && (
        <section className="preview" aria-labelledby="preview-title">
          <img src={metadata.thumbnailUrl} alt="" />
          <div>
            <p className="eyebrow">確認結果</p>
            <h2 id="preview-title">{metadata.title}</h2>
            <dl>
              <div><dt>チャンネル</dt><dd>{metadata.channelTitle}</dd></div>
              <div><dt>配信開始</dt><dd>{new Date(metadata.actualStartAt).toLocaleString('ja-JP')}</dd></div>
              <div><dt>動画時間</dt><dd>{duration(metadata.durationSeconds)}</dd></div>
            </dl>
            <button type="button" className="secondary" onClick={() => { setMetadata(null); setUrl(''); }}>別のURLを確認</button>
          </div>
        </section>
      )}
    </main>
  );
}

const root = document.getElementById('root');
if (!root) throw new Error('root element not found');
createRoot(root).render(<StrictMode><App /></StrictMode>);
