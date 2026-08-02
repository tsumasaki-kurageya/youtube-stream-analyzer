import { useEffect, useRef, useState } from 'react';

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

type YouTubePlayer = {
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
        onReady: (event: { target: YouTubePlayer }) => void;
        onError: (event: { data: number }) => void;
      };
    },
  ) => YouTubePlayer;
};

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

function adapterFromPlayer(player: YouTubePlayer): PlayerAdapter {
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
  let player: YouTubePlayer | null = null;
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

function errorMessage(code?: number): string {
  if (code === 101 || code === 150) return 'この動画はYouTube側の設定により埋め込み再生できません。';
  if (code === 100) return '動画が削除されたか、非公開になっています。';
  return 'YouTubeプレーヤーを読み込めませんでした。';
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

  function seek() {
    const seconds = Number(seekValue);
    if (!Number.isFinite(seconds)) return;
    const bounded = Math.min(Math.max(0, seconds), durationSeconds);
    adapterRef.current?.seekTo(bounded);
    setCurrentTime(bounded);
    setSeekValue(String(Math.floor(bounded)));
  }

  return (
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
  );
}
