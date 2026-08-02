type SearchItem = {
  id: string;
  type: 'chat' | 'transcript';
  offsetMilliseconds: number;
  endOffsetMilliseconds?: number | null;
  text: string;
  speaker?: string | null;
  languageCode?: string | null;
};

type SearchPage = {
  items: SearchItem[];
  nextCursor?: string | null;
  hasMore: boolean;
};

type SearchState = {
  query: string;
  items: SearchItem[];
  nextCursor: string | null;
  loading: boolean;
  error: string;
  request: AbortController | null;
  debounce: number | null;
};

const state: SearchState = {
  query: '',
  items: [],
  nextCursor: null,
  loading: false,
  error: '',
  request: null,
  debounce: null,
};

let mountedFor = '';

function streamID(): string | null {
  return window.location.pathname.match(/^\/streams\/([^/]+)$/)?.[1] ?? null;
}

function formatTime(milliseconds: number): string {
  const total = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return [hours, minutes, seconds].map((value) => String(value).padStart(2, '0')).join(':');
}

function seekTo(milliseconds: number): void {
  const input = document.querySelector<HTMLInputElement>('#seek-seconds');
  const button = [...document.querySelectorAll<HTMLButtonElement>('button')]
    .find((candidate) => candidate.textContent?.trim() === '指定時刻へ移動');
  if (!input || !button) return;
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
  setter?.call(input, String(Math.floor(milliseconds / 1000)));
  input.dispatchEvent(new Event('input', { bubbles: true }));
  button.click();
  document.querySelector('.player-panel')?.scrollIntoView({ block: 'start', behavior: 'smooth' });
}

function appendHighlighted(parent: HTMLElement, text: string, query: string): void {
  const lower = text.toLocaleLowerCase();
  const needle = query.toLocaleLowerCase();
  let cursor = 0;
  let index = lower.indexOf(needle);
  while (index >= 0) {
    parent.append(document.createTextNode(text.slice(cursor, index)));
    const mark = document.createElement('mark');
    mark.textContent = text.slice(index, index + query.length);
    parent.append(mark);
    cursor = index + query.length;
    index = lower.indexOf(needle, cursor);
  }
  parent.append(document.createTextNode(text.slice(cursor)));
}

function render(panel: HTMLElement): void {
  const result = panel.querySelector<HTMLElement>('[data-search-results]');
  const status = panel.querySelector<HTMLElement>('[data-search-status]');
  const more = panel.querySelector<HTMLButtonElement>('[data-search-more]');
  if (!result || !status || !more) return;
  result.replaceChildren();
  status.textContent = state.error || (state.loading ? '検索中…' : '');
  status.setAttribute('role', state.error ? 'alert' : 'status');

  if (!state.loading && !state.error && state.query && state.items.length === 0) {
    const empty = document.createElement('p');
    empty.className = 'search-empty';
    empty.textContent = `「${state.query}」に一致するチャット・字幕はありません。`;
    result.append(empty);
  }

  const list = document.createElement('ol');
  list.className = 'search-results';
  list.setAttribute('aria-label', 'チャット・字幕検索結果');
  for (const item of state.items) {
    const row = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    button.addEventListener('click', () => seekTo(item.offsetMilliseconds));
    const meta = document.createElement('span');
    meta.className = 'search-result-meta';
    const kind = item.type === 'chat' ? 'チャット' : '字幕';
    const detail = item.type === 'chat' ? item.speaker ?? '投稿者不明' : item.languageCode ?? '言語不明';
    meta.textContent = `${kind} · ${formatTime(item.offsetMilliseconds)} · ${detail}`;
    const body = document.createElement('span');
    body.className = 'search-result-text';
    appendHighlighted(body, item.text || '（本文なし）', state.query);
    button.append(meta, body);
    row.append(button);
    list.append(row);
  }
  if (state.items.length > 0) result.append(list);
  more.hidden = !state.nextCursor;
  more.disabled = state.loading;
}

async function search(panel: HTMLElement, append: boolean): Promise<void> {
  const id = streamID();
  if (!id || !state.query) return;
  state.request?.abort();
  const controller = new AbortController();
  state.request = controller;
  state.loading = true;
  state.error = '';
  if (!append) {
    state.items = [];
    state.nextCursor = null;
  }
  render(panel);
  const params = new URLSearchParams({ q: state.query, limit: '50' });
  if (append && state.nextCursor) params.set('cursor', state.nextCursor);
  try {
    const response = await fetch(`/api/streams/${id}/search?${params}`, { signal: controller.signal });
    if (!response.ok) {
      const problem = await response.json().catch(() => ({})) as { title?: string };
      throw new Error(problem.title || '検索を完了できませんでした。');
    }
    const page = await response.json() as SearchPage;
    state.items = append ? [...state.items, ...page.items] : page.items;
    state.nextCursor = page.hasMore ? page.nextCursor ?? null : null;
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === 'AbortError') return;
    state.error = reason instanceof Error ? reason.message : '検索を完了できませんでした。';
  } finally {
    if (state.request === controller) {
      state.loading = false;
      render(panel);
    }
  }
}

function createPanel(id: string): HTMLElement {
  const panel = document.createElement('section');
  panel.className = 'search-panel';
  panel.dataset.searchPanel = id;
  panel.setAttribute('aria-labelledby', 'stream-search-title');
  panel.innerHTML = `
    <div class="search-heading">
      <div>
        <p class="eyebrow">Search</p>
        <h2 id="stream-search-title">チャット・字幕を検索</h2>
        <p>文字列で横断検索し、結果から動画内時刻へ移動します。</p>
      </div>
    </div>
    <label for="stream-search-query">検索語</label>
    <input id="stream-search-query" type="search" maxlength="200" autocomplete="off" placeholder="発言や字幕を入力" />
    <p data-search-status aria-live="polite"></p>
    <div data-search-results></div>
    <button type="button" class="secondary" data-search-more hidden>次の50件を読み込む</button>
  `;
  const input = panel.querySelector<HTMLInputElement>('#stream-search-query');
  input?.addEventListener('input', () => {
    state.query = input.value.trim();
    state.items = [];
    state.nextCursor = null;
    state.error = '';
    state.request?.abort();
    if (state.debounce !== null) window.clearTimeout(state.debounce);
    if (!state.query) {
      state.loading = false;
      render(panel);
      return;
    }
    state.debounce = window.setTimeout(() => void search(panel, false), 300);
  });
  panel.querySelector('[data-search-more]')?.addEventListener('click', () => void search(panel, true));
  return panel;
}

function mount(): void {
  const id = streamID();
  if (!id) {
    document.querySelector('[data-search-panel]')?.remove();
    mountedFor = '';
    return;
  }
  if (mountedFor === id && document.querySelector(`[data-search-panel="${id}"]`)) return;
  const anchor = document.querySelector('.timeline-panel');
  if (!anchor) return;
  document.querySelector('[data-search-panel]')?.remove();
  state.query = '';
  state.items = [];
  state.nextCursor = null;
  state.error = '';
  state.loading = false;
  const panel = createPanel(id);
  anchor.insertAdjacentElement('afterend', panel);
  mountedFor = id;
}

const observer = new MutationObserver(mount);
observer.observe(document.body, { childList: true, subtree: true });
window.addEventListener('popstate', mount);
mount();
