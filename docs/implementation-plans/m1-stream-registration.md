# M1実装計画 — 終了済み配信の登録と配信情報確認

## 1. 到達状態

利用者が実在する終了済みYouTube配信のURLを入力し、取得した配信情報を確認したうえで登録できる。

登録済み配信は一覧から選択でき、詳細画面で保存済みの配信情報を再確認できる。ブラウザやアプリケーションを再起動しても登録内容は保持される。

M1はPhase 1の入口であり、ライブチャット、字幕、バックグラウンドジョブ、解析予約は扱わない。

## 2. 利用者の操作シナリオ

1. 配信一覧画面を開く。
2. 「配信を登録」を選択する。
3. 終了済みYouTube配信のURLを入力する。
4. 「配信情報を確認」を実行する。
5. タイトル、チャンネル、サムネイル、配信日時、動画時間を確認する。
6. 「登録」を実行する。
7. 登録完了後、配信詳細画面へ遷移する。
8. 配信一覧へ戻り、登録した配信が表示されていることを確認する。
9. アプリケーションを再起動し、一覧と詳細に登録内容が残っていることを確認する。
10. 同じ配信URLを再登録し、重複せず既存の配信詳細へ案内されることを確認する。

異常系では、次の違いを利用者が判別できるようにする。

- YouTube動画URLとして解釈できない
- 動画が存在しない、非公開、または取得不能
- 終了済みライブ配信ではない
- YouTube APIの認証・クォータ・一時障害
- アプリケーション内部またはDB接続の障害

## 3. 現在との差分

M0完了時点では開発環境、共通コマンド、CI、計画テンプレートのみが存在し、アプリケーション実装は存在しない。

M1では次を初めて導入する。

- `apps/web` のReactアプリケーション
- `apps/api` のGo Main API
- PostgreSQLのローカル実行環境
- DBマイグレーション
- OpenAPI契約
- YouTube Data API v3との同期連携
- 配信登録、一覧、詳細の永続化機能
- Web、API、DBを縦断するE2Eテスト

## 4. システムを縦断する処理フロー

### 4.1 配信プレビュー

```text
利用者
  -> Web UIでYouTube URLを入力
  -> Main APIへプレビュー要求
  -> URLからYouTube動画IDを抽出
  -> YouTube Data API videos.listを呼び出す
  -> 終了済みライブ配信であることを検証
  -> UI表示用の配信情報へ正規化
  -> Web UIで確認
```

プレビュー結果はDBへ保存しない。

### 4.2 配信登録

```text
利用者
  -> Web UIで登録を確定
  -> Main APIへ元のYouTube URLを送信
  -> Main APIがYouTube情報を再取得・再検証
  -> stream.streamsへINSERT
  -> YouTube動画IDの一意制約で重複を防止
  -> 新規または既存のStreamを返す
  -> Web UIが配信詳細へ遷移
```

クライアントからタイトル等のメタデータを正本として受け取らない。登録時にMain APIが再取得することで改ざんと古いプレビュー情報の保存を避ける。

### 4.3 一覧・詳細表示

```text
利用者
  -> Web UIで一覧または詳細を開く
  -> Main APIへ取得要求
  -> PostgreSQLから保存済みStreamを取得
  -> Web UIで表示
```

一覧と詳細表示時にはYouTube APIを再呼び出さず、登録時に保存した情報を表示する。

## 5. 設計判断

### 5.1 M1のメタデータ取得はMain APIで同期実行する

M1ではバックグラウンドジョブを対象外とするため、プレビューおよび登録に必要な軽量なメタデータ取得はMain APIが同期実行する。

システム全体構成では配信収集ワーカーがメタデータ取得責務を持つが、M1では利用者の入力に対する即時確認処理としてMain API内のYouTubeゲートウェイへ限定する。M2以降の長時間収集処理はPythonワーカーへ分離する。

この責務整理は実装開始前にADRとして確定する。

### 5.2 YouTube情報源

YouTube Data API v3の `videos.list` を使用し、次のpartを取得する。

- `snippet`
- `contentDetails`
- `liveStreamingDetails`
- `status`

APIキーは `YSA_YOUTUBE_API_KEY` でMain APIへ渡す。

M1ではyt-dlpをメタデータ取得の主経路にしない。API応答の契約とエラー分類を明確にし、UIプレビューの応答時間を予測可能にするためである。

### 5.3 対応するYouTube URL

最低限、次を受け付ける。

- `https://www.youtube.com/watch?v={videoId}`
- `https://youtu.be/{videoId}`
- `https://www.youtube.com/live/{videoId}`

次も同一動画IDへ正規化する。

- 追加クエリパラメータ付きURL
- 開始時刻指定付きURL
- `www` なしのYouTube URL
- モバイル用ホスト

YouTube以外のホスト、動画IDを抽出できないURL、動画ID単体の入力はM1では拒否する。

### 5.4 終了済みライブ配信の判定

次をすべて満たした動画を登録可能とする。

- `videos.list` の結果に対象動画が存在する
- `liveStreamingDetails` が存在する
- `actualEndTime` が存在する
- `status.privacyStatus` がAPIキーによる取得可能範囲にある

`contentDetails.duration` はISO 8601 durationから秒へ変換して保存する。

通常動画、配信中、配信予定、削除済み、非公開で取得できない動画は登録不可とする。

### 5.5 登録の冪等性

`youtube_video_id` にDB一意制約を設定する。

同じ配信を再登録した場合はエラー画面にせず、既存のStreamを返して詳細画面へ遷移する。

- 新規登録: HTTP 201
- 既存返却: HTTP 200

競合する同時登録でもDB制約を正本として重複を防ぐ。

### 5.6 API契約を先に定義する

OpenAPIをAPI契約の正本とし、Goサーバー型とWebクライアント型の生成範囲を実装時に確定する。

M1では外部公開APIではなくWeb UI専用APIとして設計するが、エラーコードとレスポンス構造は安定した契約として定義する。

## 6. データモデル

PostgreSQLの `stream` スキーマに `streams` テーブルを作成する。

### 6.1 `stream.streams`

| 列 | 型 | 制約・用途 |
|---|---|---|
| `id` | UUID | 主キー。アプリケーション側またはDB側で生成 |
| `youtube_video_id` | VARCHAR(11) | NOT NULL、UNIQUE |
| `source_url` | TEXT | NOT NULL。利用者が登録に使用したURL |
| `title` | TEXT | NOT NULL |
| `channel_id` | TEXT | NOT NULL |
| `channel_title` | TEXT | NOT NULL |
| `thumbnail_url` | TEXT | NOT NULL |
| `scheduled_start_at` | TIMESTAMPTZ | NULL可 |
| `actual_start_at` | TIMESTAMPTZ | NOT NULL |
| `actual_end_at` | TIMESTAMPTZ | NOT NULL |
| `duration_seconds` | BIGINT | NOT NULL、0以上 |
| `published_at` | TIMESTAMPTZ | NULL可 |
| `created_at` | TIMESTAMPTZ | NOT NULL、デフォルト現在時刻 |
| `updated_at` | TIMESTAMPTZ | NOT NULL、デフォルト現在時刻 |

### 6.2 制約

- `youtube_video_id` の一意制約
- `actual_end_at >= actual_start_at`
- `duration_seconds >= 0`

### 6.3 保存しないもの

M1では次を保存しない。

- YouTube APIの生レスポンス
- 動画説明全文
- タグ
- 視聴回数等の変動値
- チャット、字幕、時系列指標
- 収集ジョブ状態

後続機能で必要になった項目は、必要性が明確になったマイルストーンでマイグレーション追加する。

## 7. API

ベースパスは `/api` とする。

### 7.1 `POST /api/streams/preview`

入力:

```json
{
  "url": "https://www.youtube.com/watch?v=..."
}
```

成功レスポンス:

```json
{
  "youtubeVideoId": "...",
  "title": "...",
  "channelId": "...",
  "channelTitle": "...",
  "thumbnailUrl": "...",
  "scheduledStartAt": "...",
  "actualStartAt": "...",
  "actualEndAt": "...",
  "durationSeconds": 12345,
  "publishedAt": "..."
}
```

プレビューでは永続化しない。

### 7.2 `POST /api/streams`

入力:

```json
{
  "url": "https://www.youtube.com/watch?v=..."
}
```

Main APIがYouTube情報を再取得して保存する。

- 201: 新規登録
- 200: 既存Streamを返却
- `Location`: `/api/streams/{id}`

### 7.3 `GET /api/streams`

M1では登録日時降順で返す。

将来のページングを想定してレスポンスを配列直返しにせず、次の形にする。

```json
{
  "items": [],
  "total": 0
}
```

M1のデータ量ではページングUIを実装しない。

### 7.4 `GET /api/streams/{streamId}`

UUIDで保存済みStreamを取得する。

存在しない場合は404を返す。

### 7.5 エラー形式

RFC 9457に沿ったProblem Details形式を採用する。

アプリケーション固有の `code` を追加する。

候補:

- `INVALID_YOUTUBE_URL`
- `YOUTUBE_VIDEO_NOT_FOUND`
- `NOT_ENDED_LIVE_STREAM`
- `YOUTUBE_ACCESS_DENIED`
- `YOUTUBE_QUOTA_EXCEEDED`
- `YOUTUBE_TEMPORARILY_UNAVAILABLE`
- `STREAM_NOT_FOUND`
- `INTERNAL_ERROR`

外部APIの詳細メッセージやAPIキーをクライアントへ露出しない。

## 8. UI

### 8.1 画面構成

#### `/streams`

- 登録済み配信一覧
- 主操作「配信を登録」
- 0件時の空状態
- API取得失敗時の再読み込み導線

一覧項目:

- サムネイル
- タイトル
- チャンネル名
- 配信日時
- 動画時間

ジョブ状態、解析状態、診断情報、未実装機能への導線は表示しない。

#### `/streams/new`

- YouTube URL入力
- 「配信情報を確認」
- プレビューカード
- 「登録」
- 入力し直す操作
- 入力検証・取得エラー表示

プレビュー取得中と登録中を区別する。

#### `/streams/{streamId}`

- サムネイル
- タイトル
- チャンネル名
- 配信開始・終了日時
- 動画時間
- 元のYouTube URLへの外部リンク
- 配信一覧へ戻る導線

動画プレーヤー、チャット、字幕、収集開始ボタンは表示しない。

### 8.2 UI状態

- 初期状態
- 入力検証エラー
- プレビュー読込中
- プレビュー成功
- プレビュー取得失敗
- 登録中
- 登録成功
- 登録失敗
- 一覧0件
- 一覧読込中・失敗
- 詳細読込中・404・失敗

### 8.3 フォーム方針

React Hook FormとZodを使用する。

クライアント側検証は空文字とURL形式の早期フィードバックに限定し、YouTube動画ID抽出と登録可否の最終判断はMain APIで行う。

### 8.4 アクセシビリティ

- 入力には明示的なlabelを付ける
- エラーを入力と関連付け、支援技術へ通知する
- 読込中はボタンを無効化し状態を伝える
- 一覧カード全体を曖昧なクリック領域にせず、タイトルリンクを主導線にする
- キーボードのみで登録から詳細確認まで完走できる

## 9. バックグラウンド処理

M1では該当なし。

YouTubeメタデータ取得は利用者のプレビュー・登録要求内で同期実行する。ジョブテーブル、Pythonワーカー、リトライキューはM2まで導入しない。

Main API内では外部HTTP呼び出しにタイムアウトを設定し、限定的な一時エラー再試行を検討する。ただし、利用者の要求を長時間保持する再試行は行わない。

## 10. 実装タスクと依存関係

各行を原則1 Issueとする。Issue化時に受け入れ条件と対象外を転記する。

| 順序 | タスク | 依存先 | 完了の証拠 |
|---|---|---|---|
| 1 | M1の責務判断とAPI・データ設計をADRとして確定する | なし | Accepted ADR、レビュー済みOpenAPI草案、ER定義 |
| 2 | M1ローカル実行基盤を追加する | 1 | PostgreSQL、Web、APIを共通コマンドで起動できる |
| 3 | Go Main APIの最小構成とDBマイグレーションを実装する | 1, 2 | health check、migration up/down、DB統合テスト成功 |
| 4 | YouTube URL解析とメタデータ取得ゲートウェイを実装する | 1, 3 | URL解析単体テスト、YouTube APIスタブ統合テスト成功 |
| 5 | 配信プレビューAPIと登録画面を縦断実装する | 3, 4 | 実URLでプレビュー表示、異常系UI確認 |
| 6 | Stream登録・重複防止APIを実装する | 3, 4 | 新規201、重複200、同時登録で1行のみ |
| 7 | 配信一覧・詳細APIとWeb UIを縦断実装する | 5, 6 | 登録後に一覧・詳細表示、再起動後も保持 |
| 8 | M1の自動テスト、CI、完了デモ手順を完成させる | 5, 6, 7 | E2E成功、実データ完了デモ、ドキュメント更新 |

### 10.1 タスク分割の原則

- Web雛形、API雛形、DBだけを完成扱いにしない
- タスク5以降は利用者が確認可能な縦断スライスにする
- 将来機能の共通化をIssueへ混ぜない
- 各Issueで `make check` に必要な検証を追加する

## 11. テスト計画

### 11.1 単体テスト

Go:

- 対応URLごとの動画ID抽出
- 不正ホスト、動画ID欠落、異常なURL
- ISO 8601 durationの秒変換
- YouTube APIレスポンスの正規化
- 終了済み配信判定
- YouTubeエラーからアプリケーションエラーへの分類

Web:

- URLフォームの入力検証
- プレビュー状態遷移
- APIエラーコードに応じたメッセージ表示
- 日時・動画時間表示

### 11.2 統合テスト

- PostgreSQLに対するmigration up/down
- Stream repositoryのinsert/get/list
- `youtube_video_id` の一意制約
- 同時登録時の冪等性
- HTTPハンドラーとDBの統合
- YouTube APIスタブサーバーを利用したpreview/register

テストでは実際のYouTube APIへ依存しない。

### 11.3 E2Eテスト

Playwrightで最低限、次を自動化する。

1. 配信一覧0件から登録画面へ移動する
2. URLを入力してプレビューする
3. メタデータを確認して登録する
4. 詳細画面を確認する
5. 一覧へ戻り登録済み配信を確認する
6. 同じURLを再登録し、既存詳細へ遷移する

CIのE2EではYouTube APIスタブを使用し、結果を決定的にする。

異常系E2E:

- 不正URL
- 終了済み配信ではない応答
- YouTube API障害

### 11.4 実データ検証

マイルストーン完了時のみ、実在する公開済みの終了済みライブ配信と実APIキーを使って次を確認する。

- プレビュー
- 登録
- 一覧
- 詳細
- 再起動後の保持
- 重複登録

使用した配信URL、実行日、確認結果を完了デモ手順へ記録する。APIキーは記録しない。

### 11.5 CI変更

`make check` から次を実行できるようにする。

- Web format/lint/typecheck/unit test/build
- Go format/lint/unit test/integration test/build
- migration検証
- OpenAPI整合性検証
- Playwright E2E

ジョブは診断しやすい単位へ分けてもよいが、ローカルとCIで検証入口を一致させる。

## 12. 完了デモ

1. `.env` にローカルDB接続情報と `YSA_YOUTUBE_API_KEY` を設定する。
2. ドキュメント記載のコマンドでPostgreSQL、Main API、Web UIを起動する。
3. 空の配信一覧を開く。
4. 実在する終了済み配信URLを入力する。
5. プレビューにタイトル、チャンネル、サムネイル、配信日時、動画時間が表示されることを確認する。
6. 登録し、詳細画面が表示されることを確認する。
7. 一覧へ戻り、登録した配信が表示されることを確認する。
8. アプリケーションを停止・再起動する。
9. 一覧と詳細が引き続き表示されることを確認する。
10. 同じURLを再登録し、データ件数が増えず既存詳細へ遷移することを確認する。
11. 不正URLと終了していない配信URLで理由が表示されることを確認する。
12. `make check` が成功することを確認する。

## 13. 対象外

- バックグラウンドジョブ
- Python配信収集ワーカー
- ライブチャット取得
- 字幕取得
- 動画プレーヤー
- 動画との時刻同期
- 解析予約
- リアルタイム収集
- Azure Blob Storage
- 認証・複数ユーザー
- クラウドへのデプロイ
- 視聴回数等のメタデータ更新
- 配信削除・編集
- ページング、検索、並び替えUI
- M2以降のボタン、メニュー、プレースホルダー

## 14. 未決事項

実装Issueへ分解する前に、次をレビューして確定する。

1. Main APIによる同期メタデータ取得をM1の責務例外として採用するか。
2. APIクライアント生成をWebまで行うか、Goサーバー型生成のみにするか。
3. UUID生成をGo側とPostgreSQL側のどちらへ置くか。
4. PostgreSQLのローカル起動をDev Container内サービスとルートComposeのどちらで提供するか。
5. CI E2E用YouTube APIスタブをGoプロセス内、WireMock系ツール、独立テストサーバーのどれで実装するか。
6. サムネイルURLはYouTube URLを保存するだけとし、M1ではBlobへ複製しない方針でよいか。
7. プレビューと登録の2回分のYouTube API呼び出しを許容するか。`videos.list` は1リクエストあたり1 quota unitであり、M1では単純性と保存データの信頼性を優先する。

上記以外の将来設計はM1で決定しない。
