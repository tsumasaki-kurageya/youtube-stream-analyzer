# M3 完了デモ手順

M3「動画、チャット、字幕を同期して場面を探す」の完了確認手順です。

## CIで自動確認する範囲

`apps/web/e2e/m3-completion.spec.ts`は、PostgreSQL、Main API、Pythonワーカー、Web UIを実際に起動し、YouTubeメタデータ、チャット、字幕の取得先だけを決定的なfixtureへ差し替えます。

```bash
make db-migrate
cd apps/worker && python -m pip install -e '.[dev]'
cd ../web && npm install && npx playwright install chromium
npm run test:e2e -- m3-completion.spec.ts
```

確認対象:

- 配信登録と `metadata / chat_replay / transcript` の複数工程収集
- 字幕あり配信の正常完了
- チャット・字幕のDB保存
- プレーヤー現在時刻周辺の同期表示
- 字幕項目からのシーク
- チャット・字幕横断検索と検索結果からの時刻ジャンプ
- 同じ配信の再収集でチャット・字幕が重複しないこと
- 字幕なしを `no_data` として正常完了すること
- 字幕取得の一時障害を `partial` として記録すること
- 失敗した `transcript` 工程だけを再実行し、成功済み工程を維持すること

Playwrightは失敗時のtrace、screenshot、video、HTML reportをCI artifactへ保存します。CIは併せてGo、Python、Web、DB migration、OpenAPI、artifact秘密情報検査を実行します。

## 数時間規模の実配信デモ

### 前提

- 実YouTube Data APIを利用できる `YSA_YOUTUBE_API_KEY`
- 実チャットリプレイGatewayの `YSA_CHAT_REPLAY_BASE_URL`
- 実字幕Gatewayの `YSA_TRANSCRIPT_BASE_URL`
- PostgreSQL、Main API、Pythonワーカー、Web UI
- 数時間規模で、チャットリプレイと字幕が利用できる終了済み配信
- 字幕が存在しないことを確認済みの終了済み配信

### 字幕あり配信

1. 対象配信を登録する。
2. `POST /api/streams/{streamId}/collections`で全工程収集を開始する。
3. `metadata → chat_replay → transcript`の順に進み、Jobが`succeeded`になることを確認する。
4. 配信詳細を開き、動画、チャット、字幕が同一画面で表示されることを確認する。
5. 先頭付近、中間、末尾で動画を再生し、対応するチャットと字幕の時刻を確認する。
6. チャット項目と字幕項目をそれぞれ選択し、動画が該当時刻へ移動することを確認する。
7. 配信内検索で実在する語を検索し、チャットと字幕の両方が返ることを確認する。
8. 検索結果を選択し、動画が該当時刻へ移動することを確認する。
9. 同じ配信を再収集し、チャット件数と字幕件数が増加しないことを確認する。

### 字幕なし配信

1. 対象配信を登録し、全工程収集を開始する。
2. `transcript`工程が`no_data`、Jobが`succeeded`になることを確認する。
3. 同期閲覧画面で「利用可能な字幕がない」状態が表示され、チャットと動画は利用できることを確認する。

### 部分失敗と工程単位再実行

1. 字幕Gatewayを一時的に失敗させ、全工程収集を開始する。
2. `metadata`と`chat_replay`が`succeeded`、`transcript`が`failed`、Jobが`partial`になることを確認する。
3. 字幕Gatewayを復旧し、`POST /api/collection-jobs/{jobId}/steps/transcript/retry`を実行する。
4. `transcript`のattemptが増え、Jobが`succeeded`になることを確認する。
5. 先に保存済みのチャットが重複・消失していないことを確認する。

## 実施結果記録

機密情報や大量のチャット・字幕本文は記録しません。

| 項目 | 字幕あり | 字幕なし | 部分失敗・再実行 |
|---|---|---|---|
| 実施日 | 未実施 | 未実施 | 未実施 |
| YouTube video ID |  |  |  |
| 動画時間 |  |  |  |
| CollectionJob ID |  |  |  |
| 最終Job状態 |  |  |  |
| チャット件数 |  |  |  |
| 字幕件数 |  |  |  |
| 再収集後件数 |  |  |  |
| 同期表示確認 |  |  |  |
| 項目シーク確認 |  |  |  |
| 検索時刻ジャンプ確認 |  |  |  |
| 補足 |  |  |  |

## M3完了判定

CI fixtureによるフルスタック検証だけではM3完了とはしません。上表の字幕あり・字幕なし実配信確認が完了し、未確認範囲がなくなった時点で親Issue #51を完了扱いにします。
