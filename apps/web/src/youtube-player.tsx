import { useEffect, useMemo, useRef, useState } from 'react';

export type PlayerState = 'loading' | 'ready' | 'error';

export interface PlayerAdapter {
  play(): void;
  pause(): void;
  seekTo(seconds: number): void;
  getCurrentTime(): number;
  destroy(): void;
}

export type PlayerFactory = (
  element: HTMLElement,
  videoId: string,
  onReady: (adapter: PlayerAdapter) => void,
  onError: (code?: number) => void,
) => PlayerAdapter;

type YouTubePlayerInstance = {
  playVideo(): void;
  pauseVideo(): void;
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  getCurrentTime(): number;
  destroy(): void;
};

type YouTubeNamespace = {
  Player: new (
    element: HTMLElement,
    options: {
      videoId: string;
      playerVars: Record<string, number | string>;
      events: {
        onReady: (event: { target: YouTubePlayerInstance }) => void;
        onError: (event: { data: number }) => void;
      };
    },
  ) => YouTubePlayerInstance;
};

type ChatMessage = {
  id: string;
  authorName: string;
  messageText: string;
  elapsedMilliseconds: number;
};

type TranscriptSegment = {
  id: string;
  languageCode: string;
  startOffsetMilliseconds: number;
  endOffsetMilliseconds: number;
  text: string;
};

type TimelinePage<T> = { items: T[]; nextCursor?: string | null };
type CollectionStep = { name: string; status: string; errorMessage?: string | null };
type CollectionJob = { steps: CollectionStep[] };

declare global {
  interface Window {
    YT?: YouTubeNamespace;
    onYouTubeIframeAPIReady?: () => void;
    __YSA_YOUTUBE_PLAYER_FACTORY__?: PlayerFactory;
  }
}

let apiPromise: Promise<YouTubeNamespace> | null = null;

function loadYouTubeAPI(): Promise<YouTubeNamespace> {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (apiPromise) return apiPromise;
  apiPromise = new Promise((resolve, reject) => {
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      if (window.YT?.Player) resolve(window.YT);
      else reject(new Error('YouTube IFrame APIを初期化できませんでした。'));
    };
    const existing = document.querySelector<HTMLScriptElement>('script[data-ysa-youtube-api]');
    if (existing) return;
    const script = document.createElement('script');
    script.src = 'https://www.youtube.com/iframe_api';
    script.async = true;
    script.dataset.ysaYoutubeApi = 'true';
    script.onerror = () => reject(new Error('YouTube IFrame APIを読み込めませんでした。'));
    document.head.append(script);
  });
  return apiPromise;
}

function adapterFromPlayer(player: YouTubePlayerInstance): PlayerAdapter {
  return {
    play: () => player.playVideo(),
    pause: () => player.pauseVideo(),
    seekTo: (seconds) => player.seekTo(seconds, true),
    getCurrentTime: () => player.getCurrentTime(),
    destroy: () => player.destroy(),
  };
}

export function createYouTubePlayer(
  element: HTMLElement,
  videoId: string,
  onReady: (adapter: PlayerAdapter) => void,
  onError: (code?: number) => void,
): PlayerAdapter {
  let player: YouTubePlayerInstance | null = null;
  let destroyed = false;
  void loadYouTubeAPI()
    .then((YT) => {
      if (destroyed) return;
      player = new YT.Player(element, {
        videoId,
        playerVars: { enablejsapi: 1, playsinline: 1, rel: 0 },
        events: {
          onReady: ({ target }) => {
            player = target;
            if (!destroyed) onReady(adapterFromPlayer(target));
          },
          onError: ({ data }) => {
            if (!destroyed) onError(data);
          },
        },
      });
    })
    .catch(() => {
      if (!destroyed) onError();
    });
  return {
    play: () => player?.playVideo(),
    pause: () => player?.pauseVideo(),
    seekTo: (seconds) => player?.seekTo(seconds, true),
    getCurrentTime: () => player?.getCurrentTime() ?? 0,
    destroy: () => {
      destroyed = true;
      player?.destroy();
      player = null;
    },
  };
}

function formatTime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  return [hours, minutes, remainder].map((value) => String(value).padStart(2, '0')).join(':');
}

function formatMilliseconds(milliseconds: number): string {
  return formatTime(milliseconds / 1000);
}

function errorMessage(code?: number): string {
  if (code === 101 || code === 150) return 'この動画はYouTube側の設定により埋め込み再生できません。';
  if (code === 100) return '動画が削除されたか、非公開になっています。';
  return 'YouTubeプレーヤーを読み込めませんでした。';
}

function streamIDFromPath(): string | null {
  return window.location.pathname.match(/^\/streams\/([^/]+)$/)?.[1] ?? null;
}

function TimelinePanel({
  streamID,
  currentTime,
  onSeek,
}: {
  streamID: string;
  currentTime: number;
  onSeek: (seconds: number) => void;
}) {
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);
  const [transcriptState, setTranscriptState] = useState<'available' | 'no_data' | 'failed' | 'pending'>('pending');
  const [transcriptFailure, setTranscriptFailure] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [following, setFollowing] = useState(true);
  const chatListRef = useRef<HTMLOListElement>(null);
  const transcriptListRef = useRef<HTMLOListElement>(null);
  const windowBucket = Math.floor(currentTime / 10);
  const currentMilliseconds = Math.floor(currentTime * 1000);

  useEffect(() => {
    const controller = new AbortController();
    const center = windowBucket * 10_000;
    const fromMS = Math.max(0, center - 30_000);
    const toMS = center + 40_000;
    const query = `limit=200&fromMs=${fromMS}&toMs=${toMS}`;
    setLoading(true);
    setError('');
    void Promise.all([
      fetch(`/api/streams/${streamID}/chat-messages?${query}`, { signal: controller.signal }),
      fetch(`/api/streams/${streamID}/transcript-segments?${query}`, { signal: controller.signal }),
      fetch(`/api/streams/${streamID}/collections/latest`, { signal: controller.signal }),
    ]).then(async ([chatResponse, transcriptResponse, collectionResponse]) => {
      if (!chatResponse.ok || !transcriptResponse.ok) throw new Error('同期データを取得できませんでした。');
      const chatPage = await chatResponse.json() as TimelinePage<ChatMessage>;
      const transcriptPage = await transcriptResponse.json() as TimelinePage<TranscriptSegment>;
      setChat(chatPage.items);
      setTranscript(transcriptPage.items);
      if (transcriptPage.items.length > 0) {
        setTranscriptState('available');
        setTranscriptFailure('');
      } else if (collectionResponse.ok) {
        const job = await collectionResponse.json() as CollectionJob;
        const step = job.steps.find((item) => item.name === 'transcript');
        if (step?.status === 'no_data') setTranscriptState('no_data');
        else if (step?.status === 'failed') {
          setTranscriptState('failed');
          setTranscriptFailure(step.errorMessage || '字幕取得工程に失敗しました。');
        } else setTranscriptState('pending');
      } else {
        setTranscriptState('pending');
      }
    }).catch((reason: unknown) => {
      if (reason instanceof DOMException && reason.name === 'AbortError') return;
      setError(reason instanceof Error ? reason.message : '同期データを取得できませんでした。');
    }).finally(() => setLoading(false));
    return () => controller.abort();
  }, [streamID, windowBucket]);

  const activeChatID = useMemo(() => {
    let nearest: ChatMessage | undefined;
    for (const item of chat) {
      if (!nearest || Math.abs(item.elapsedMilliseconds - currentMilliseconds) < Math.abs(nearest.elapsedMilliseconds - currentMilliseconds)) nearest = item;
    }
    return nearest && Math.abs(nearest.elapsedMilliseconds - currentMilliseconds) <= 3000 ? nearest.id : null;
  }, [chat, currentMilliseconds]);
  const activeTranscriptID = transcript.find((item) => item.startOffsetMilliseconds <= currentMilliseconds && currentMilliseconds < item.endOffsetMilliseconds)?.id ?? null;

  useEffect(() => {
    if (!following) return;
    chatListRef.current?.querySelector<HTMLElement>('[aria-current="true"]')?.scrollIntoView({ block: 'center' });
    transcriptListRef.current?.querySelector<HTMLElement>('[aria-current="true"]')?.scrollIntoView({ block: 'center' });
  }, [activeChatID, activeTranscriptID, following]);

  return (
    <section className="timeline-panel" aria-labelledby="timeline-title">
      <div className="timeline-heading">
        <div>
          <p className="eyebrow">Synchronized timeline</p>
          <h2 id="timeline-title">チャット・字幕</h2>
          <p>現在位置の前後30秒を表示しています。</p>
        </div>
        <button type="button" className="secondary" aria-pressed={following} onClick={() => setFollowing((value) => !value)}>
          {following ? '自動追従を停止' : '自動追従を再開'}
        </button>
      </div>
      {loading && <p role="status">現在時刻周辺のチャットと字幕を読み込み中…</p>}
      {error && <p role="alert" className="error">{error}</p>}
      <div className="timeline-columns">
        <section aria-labelledby="chat-timeline-title">
          <h3 id="chat-timeline-title">チャット</h3>
          {!loading && chat.length === 0 && <p className="timeline-empty">この時間帯のチャットはありません。</p>}
          <ol ref={chatListRef} className="timeline-list" aria-label="現在時刻周辺のチャット" onWheel={() => setFollowing(false)}>
            {chat.map((item) => (
              <li key={item.id} aria-current={item.id === activeChatID}>
                <button type="button" onClick={() => onSeek(item.elapsedMilliseconds / 1000)}>
                  <time>{formatMilliseconds(item.elapsedMilliseconds)}</time>
                  <span><strong>{item.authorName}</strong>{item.messageText || '（本文なし）'}</span>
                </button>
              </li>
            ))}
          </ol>
        </section>
        <section aria-labelledby="transcript-timeline-title">
          <h3 id="transcript-timeline-title">字幕</h3>
          {!loading && transcriptState === 'no_data' && <p className="timeline-empty">この配信には利用可能な字幕がありません。</p>}
          {!loading && transcriptState === 'failed' && <p role="alert" className="error">字幕取得失敗: {transcriptFailure}</p>}
          {!loading && transcriptState === 'pending' && transcript.length === 0 && <p className="timeline-empty">字幕の収集が完了していません。</p>}
          {!loading && transcriptState === 'available' && transcript.length === 0 && <p className="timeline-empty">この時間帯の字幕はありません。</p>}
          <ol ref={transcriptListRef} className="timeline-list" aria-label="現在時刻周辺の字幕" onWheel={() => setFollowing(false)}>
            {transcript.map((item) => (
              <li key={item.id} aria-current={item.id === activeTranscriptID}>
                <button type="button" onClick={() => onSeek(item.startOffsetMilliseconds / 1000)}>
                  <time>{formatMilliseconds(item.startOffsetMilliseconds)}</time>
                  <span>{item.text}</span>
                </button>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </section>
  );
}

export function YouTubePlayer({
  videoId,
  sourceUrl,
  durationSeconds,
  factory = window.__YSA_YOUTUBE_PLAYER_FACTORY__ ?? createYouTubePlayer,
}: {
  videoId: string;
  sourceUrl: string;
  durationSeconds: number;
  factory?: PlayerFactory;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const adapterRef = useRef<PlayerAdapter | null>(null);
  const [state, setState] = useState<PlayerState>('loading');
  const [currentTime, setCurrentTime] = useState(0);
  const [seekValue, setSeekValue] = useState('0');
  const [error, setError] = useState('');
  const streamID = streamIDFromPath();

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    setState('loading');
    setError('');
    host.replaceChildren();
    const adapter = factory(
      host,
      videoId,
      (readyAdapter) => {
        adapterRef.current = readyAdapter;
        setState('ready');
      },
      (code) => {
        setError(errorMessage(code));
        setState('error');
      },
    );
    adapterRef.current = adapter;
    return () => {
      adapter.destroy();
      if (adapterRef.current === adapter) adapterRef.current = null;
      host.replaceChildren();
    };
  }, [factory, videoId]);

  useEffect(() => {
    if (state !== 'ready') return;
    const timer = window.setInterval(() => {
      const value = adapterRef.current?.getCurrentTime() ?? 0;
      setCurrentTime(value);
      setSeekValue(String(Math.floor(value)));
    }, 500);
    return () => window.clearInterval(timer);
  }, [state]);

  function seekTo(seconds: number) {
    const bounded = Math.min(Math.max(0, seconds), durationSeconds);
    adapterRef.current?.seekTo(bounded);
    setCurrentTime(bounded);
    setSeekValue(String(Math.floor(bounded)));
  }

  function seek() {
    const seconds = Number(seekValue);
    if (!Number.isFinite(seconds)) return;
    seekTo(seconds);
  }

  return (
    <>
      <section className="player-panel" aria-labelledby="player-title">
        <div className="player-heading">
          <div>
            <p className="eyebrow">Playback</p>
            <h2 id="player-title">配信プレーヤー</h2>
          </div>
          <output aria-label="現在の再生時刻">{formatTime(currentTime)}</output>
        </div>
        <div className="player-frame" ref={hostRef} data-video-id={videoId} />
        {state === 'loading' && <p role="status">YouTubeプレーヤーを読み込み中…</p>}
        {state === 'error' && (
          <div className="player-error">
            <p role="alert" className="error">{error}</p>
            <a href={sourceUrl} target="_blank" rel="noreferrer">YouTubeで元配信を開く</a>
          </div>
        )}
        <div className="player-controls" aria-label="動画再生操作">
          <button type="button" onClick={() => adapterRef.current?.play()} disabled={state !== 'ready'}>再生</button>
          <button type="button" className="secondary" onClick={() => adapterRef.current?.pause()} disabled={state !== 'ready'}>停止</button>
          <label htmlFor="seek-seconds">動画内時刻（秒）</label>
          <input
            id="seek-seconds"
            type="number"
            min="0"
            max={durationSeconds}
            value={seekValue}
            onChange={(event) => setSeekValue(event.target.value)}
            disabled={state !== 'ready'}
          />
          <button type="button" className="secondary" onClick={seek} disabled={state !== 'ready'}>指定時刻へ移動</button>
        </div>
      </section>
      {streamID && state === 'ready' && <TimelinePanel streamID={streamID} currentTime={currentTime} onSeek={seekTo} />}
    </>
  );
}
