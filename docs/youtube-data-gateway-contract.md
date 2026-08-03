# YouTube Data Gateway 実装契約

Issue #87で確定した、`youtube-data-gateway`実装者向けの要点です。詳細な設計判断は[ADR-0004](./decisions/0004-youtube-data-gateway-service.md)、機械検証可能なHTTP契約は[`contracts/youtube-data-gateway.yaml`](../contracts/youtube-data-gateway.yaml)を正本とします。

## サービス境界

```text
Python Worker
  ├─ CollectionStep、lease、進捗、再実行
  ├─ 全ページ取得制御
  ├─ 経過時刻計算
  └─ PostgreSQL保存
        ↓ private HTTP + Bearer token
youtube-data-gateway
  ├─ YouTubeアクセス
  ├─ YouTube固有レスポンス解釈
  ├─ チャット・字幕の正規化
  └─ 外部エラー分類
        ↓
      YouTube
```

Gatewayはステートレスです。DBへ接続せず、ジョブ状態や収集結果を保持しません。

## 初版API

| Endpoint | 用途 |
|---|---|
| `GET /healthz` | liveness |
| `GET /readyz` | 必須設定とprovider初期化のreadiness |
| `GET /v1/chat-replay/pages` | 正規化済みチャット1ページ |
| `GET /v1/transcripts/tracks` | 字幕トラック一覧 |
| `GET /v1/transcripts/segments` | 正規化済み字幕1ページ |

`/v1/*`はBearer token必須です。health/readinessはprobe用に認証不要ですが、Gateway自体を外部公開しません。

## 認証情報

- Gateway: `YSA_GATEWAY_AUTH_TOKEN`
- Gatewayの移行期間: `YSA_GATEWAY_AUTH_TOKEN_PREVIOUS`
- Worker: 現行tokenのみ
- YouTube用Cookie等: Gateway側の秘密変数またはsecret volumeだけに配置

Cookie、token、Authorization header、YouTube生レスポンスをDB・通常ログ・レスポンス・CI artifactへ出力しません。

## エラー処理

エラーは`application/problem+json`で返します。Workerは`code`と`retryable`を使用し、HTTP本文の文言を判定に使いません。

- データなし: 正常な空配列、または恒久取得不能を示す404
- 処理待ち: `409 SOURCE_NOT_READY`, retryable=true
- rate limit: `429 YOUTUBE_RATE_LIMITED`, retryable=true
- 上流一時障害: 503/504, retryable=true
- 外部仕様変更: `502 YOUTUBE_SOURCE_CHANGED`, retryable=false

## 後続Issue

- #88: チャットリプレイprovider実装
- #89: 字幕provider実装
- #90: Workerクライアント移行、契約E2E、Railwayデプロイ
- #76: 実配信完了デモ
