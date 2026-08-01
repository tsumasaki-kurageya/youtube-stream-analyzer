import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

type Health = { status: string };

function App() {
  const [status, setStatus] = useState('確認中');

  useEffect(() => {
    fetch('/api/health')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<Health>;
      })
      .then((health) => setStatus(health.status === 'ok' ? '接続済み' : '異常'))
      .catch(() => setStatus('未接続'));
  }, []);

  return (
    <main>
      <h1>YouTube Stream Analyzer</h1>
      <p>M1のローカル開発基盤を起動しています。</p>
      <p> Main API: <strong>{status}</strong></p>
    </main>
  );
}

const root = document.getElementById('root');
if (!root) throw new Error('root element not found');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
