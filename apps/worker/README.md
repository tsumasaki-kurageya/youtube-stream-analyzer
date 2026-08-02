# 配信収集ワーカー

M2以降の長時間収集処理を担当するPythonワーカーです。Issue #32では、PostgreSQLへ接続し、安全に起動・停止できる実行基盤までを提供します。ジョブ取得とチャット収集は後続Issueで実装します。

## セットアップ

リポジトリルートで次を実行します。

```bash
make setup
make db-up
make worker
```

`make dev`ではWeb、Main API、ワーカーをまとめて起動します。Composeだけでワーカーを確認する場合は次を使用します。

```bash
docker compose --profile worker up worker
```

## 環境変数

- `YSA_DATABASE_URL`: PostgreSQL接続文字列。必須。
- `YSA_WORKER_ID`: ログと将来のジョブリースで使用する識別子。既定値は`local-worker`。
- `YSA_WORKER_POLL_INTERVAL_SECONDS`: 待機間隔。正の数。既定値は3秒。

## 品質確認

```bash
make worker-check
```

Ruff、mypy、pytestを実行します。起動時に`SELECT 1`を実行し、DB接続できない場合はエラー終了します。SIGINTまたはSIGTERMを受けると待機を解除して安全に終了します。
