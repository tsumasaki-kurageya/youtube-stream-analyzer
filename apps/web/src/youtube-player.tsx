import { useEffect, useRef, useState } from 'react';

export type PlayerState = 'loading' | 'ready' | 'error';

export interface PlayerAdapter {
  destroy(): void;
}

export type PlayerFactory = (
  element: HTMLElement,
  videoId: string,
  onReady: (adapter: PlayerAdapter) => void,
  onError: (code?: number) => void,
) => PlayerAdapter;

type YouTubePlayerInstance = {
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
  return { destroy: () => player.destroy() };
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
        playerVars: { playsinline: 1, rel: 0 },
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
    destroy: () => {
      destroyed = true;
      player?.destroy();
      player = null;
    },
  };
}

function errorMessage(code?: number): string {
  if (code === 101 || code === 150) return 'この動画はYouTube側の設定により埋め込み再生できません。';
  if (code === 100) return '動画が削除されたか、非公開になっています。';
  return 'YouTubeプレーヤーを読み込めませんでした。';
}

export function YouTubePlayer({
  videoId,
  sourceUrl,
  factory = window.__YSA_YOUTUBE_PLAYER_FACTORY__ ?? createYouTubePlayer,
}: {
  videoId: string;
  sourceUrl: string;
  durationSeconds?: number;
  factory?: PlayerFactory;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<PlayerState>('loading');
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
      () => setState('ready'),
      (code) => {
        setError(errorMessage(code));
        setState('error');
      },
    );
    return () => {
      adapter.destroy();
      host.replaceChildren();
    };
  }, [factory, videoId]);

  return (
    <section className="player-panel" aria-labelledby="player-title">
      <div className="player-heading">
        <div>
          <p className="eyebrow">Playback</p>
          <h2 id="player-title">配信プレーヤー</h2>
        </div>
      </div>
      <div className="player-frame" ref={hostRef} data-video-id={videoId} />
      {state === 'loading' && <p role="status">YouTubeプレーヤーを読み込み中…</p>}
      {state === 'error' && (
        <div className="player-error">
          <p role="alert" className="error">{error}</p>
          <a href={sourceUrl} target="_blank" rel="noreferrer">YouTubeで元配信を開く</a>
        </div>
      )}
    </section>
  );
}
