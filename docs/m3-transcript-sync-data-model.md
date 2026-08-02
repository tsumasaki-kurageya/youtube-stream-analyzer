# M3 字幕・同期データモデル

Issue #52の実装正本。ADR 0003とOpenAPI 0.3.0を補足する。

## 1. CollectionJob

CollectionJobは1回の利用者収集要求を表す。M3では標準工程`metadata`、`chat_replay`、`transcript`を持つ。

推奨追加・変更項目:

| 列 | 型 | 説明 |
|---|---|---|
| status | text | queued / running / succeeded / partial / failed / cancelled |
| requested_steps | text[] | 要求された工程名 |
| progress_count | bigint | 全Stepの保存件数合計。表示用の集約値 |
| error_code | text nullable | Job全体がfailedの場合の代表エラー |
| error_message | text nullable | 代表エラー表示 |

Job状態は直接任意更新せず、Step更新トランザクション内で集約規則から再計算する。

## 2. CollectionStep

| 列 | 型 | 制約・説明 |
|---|---|---|
| id | uuid | PK |
| job_id | uuid | FK collection_jobs |
| name | text | metadata / chat_replay / transcript |
| status | text | queued / running / succeeded / no_data / failed / cancelled |
| attempt | integer | 1以上。最新attempt番号 |
| progress_count | bigint | 0以上 |
| worker_id | text nullable | lease所有者 |
| lease_expires_at | timestamptz nullable | lease期限 |
| heartbeat_at | timestamptz nullable | 最終heartbeat |
| error_code | text nullable | 失敗分類 |
| error_message | text nullable | 利用者表示可能な要約 |
| retryable | boolean nullable | failed時に必須 |
| started_at | timestamptz nullable | 最新attempt開始 |
| finished_at | timestamptz nullable | 最新attempt終了 |
| created_at | timestamptz | 作成時刻 |
| updated_at | timestamptz | 更新時刻 |

制約:

- UNIQUE(job_id, name)
- active状態はqueued/running
- running時だけworker_id、lease_expires_at、heartbeat_atを必須にする
- failed時はerror_code、error_message、retryableを必須にする
- succeeded/no_data/failed/cancelled時はfinished_atを必須にする

## 3. CollectionStepAttempt

工程単位再実行の監査・診断用履歴。

| 列 | 型 | 説明 |
|---|---|---|
| id | uuid | PK |
| step_id | uuid | FK collection_steps |
| attempt | integer | 1以上 |
| status | text | queued / running / succeeded / no_data / failed / cancelled |
| worker_id | text nullable | 実行ワーカー |
| progress_count | bigint | この試行の保存件数 |
| error_code | text nullable | エラー分類 |
| error_message | text nullable | エラー要約 |
| retryable | boolean nullable | 再実行可能性 |
| started_at | timestamptz nullable | 開始 |
| finished_at | timestamptz nullable | 終了 |
| created_at | timestamptz | 作成 |

制約:

- UNIQUE(step_id, attempt)
- Stepのattemptは最新Attemptと一致する
- 同一Stepでqueued/runningのAttemptは1件だけ

## 4. TranscriptTrack

取得した字幕トラックの選択根拠と再収集単位を保持する。

| 列 | 型 | 説明 |
|---|---|---|
| id | uuid | PK |
| stream_id | uuid | FK streams |
| external_track_id | text | 取得元トラックID |
| language_code | text | BCP 47相当 |
| display_name | text | 表示名 |
| is_auto_generated | boolean | 自動生成か |
| is_selected | boolean | M3で採用したトラックか |
| source_etag | text nullable | 取得元識別子 |
| collected_by_step_id | uuid | 成功したStep |
| created_at / updated_at | timestamptz | 監査時刻 |

制約:

- UNIQUE(stream_id, external_track_id)
- 配信ごとのis_selected=trueは原則1件

選択規則:

1. `ja`の手動字幕
2. `ja`の自動生成字幕
3. 配信メタデータの既定言語に一致する手動字幕
4. 既定言語に一致する自動字幕
5. 取得可能な手動字幕
6. 取得可能な自動字幕

同順位は外部トラックID昇順で決定し、選択を決定的にする。

## 5. TranscriptSegment

| 列 | 型 | 制約・説明 |
|---|---|---|
| id | uuid | PK |
| stream_id | uuid | FK streams |
| track_id | uuid | FK transcript_tracks |
| source_segment_id | text | 取得元IDまたは決定的生成ID |
| start_offset_milliseconds | bigint | 0以上 |
| end_offset_milliseconds | bigint | startより大きい |
| text | text | 空文字不可 |
| normalized_text | text | 検索用正規化文字列 |
| collected_by_step_id | uuid | FK collection_steps |
| created_at / updated_at | timestamptz | 監査時刻 |

制約:

- UNIQUE(stream_id, track_id, source_segment_id)
- CHECK(start_offset_milliseconds >= 0)
- CHECK(end_offset_milliseconds > start_offset_milliseconds)
- INDEX(stream_id, start_offset_milliseconds, end_offset_milliseconds, id)
- INDEX(stream_id, normalized_text)は初期段階では通常indexを必須にせず、検索計測後にpg_trgmを判断する

## 6. 再収集トランザクション

字幕保存はトラック単位で次を実施する。

1. 取得結果を一時テーブルまたはメモリ上で完全に取得する
2. DBトランザクションを開始する
3. TranscriptTrackをupsertする
4. Segmentをsource_segment_id単位でupsertする
5. 今回の完全取得結果に含まれない既存Segmentを削除する
6. Stepをsucceededへ更新する
7. commitする

取得途中または保存途中の失敗では既存の成功データを削除しない。

字幕なしの場合はTrack/Segmentを作成せず、Stepをno_dataへ更新する。

## 7. Timeline API

`GET /streams/{streamId}/timeline?fromMs=0&toMs=30000&types=chat,transcript`

規則:

- `0 <= fromMs < toMs`
- 最大範囲は5分。長時間配信の全件返却を禁止する
- chatは`offsetMilliseconds >= fromMs AND < toMs`
- transcriptは`start < toMs AND end > fromMs`の重なり条件
- 応答はchatItemsとtranscriptItemsを分離する
- 各配列は動画内時刻、IDで安定ソートする

## 8. Search API

`GET /streams/{streamId}/search?q=...&types=chat,transcript&cursor=...&limit=50`

規則:

- qはtrim後1〜200文字
- types省略時はchat,transcript
- limit既定50、最大100
- 大文字小文字を区別しない部分一致
- 統一結果はtype、id、offsetMilliseconds、endOffsetMilliseconds、text、speaker、languageCodeを持つ
- 並び順はoffsetMilliseconds、type、id
- カーソルは並び順の複合値をopaqueにencodeする

## 9. UI状態解釈

| Step状態 | UI表示 | 操作 |
|---|---|---|
| queued | 開始待ち | なし |
| running | 収集中、件数表示 | なし |
| succeeded | 収集完了 | データ閲覧 |
| no_data | 字幕なし等、正常なデータなし | 説明表示 |
| failed retryable=true | 失敗理由 | この工程を再実行 |
| failed retryable=false | 取得不能理由 | 外部サービス導線または説明 |
| cancelled | 取消済み | なし |

Jobがpartialでも、成功済み工程のデータ閲覧を妨げない。

## 10. 実装順への制約

- #53はgateway契約とエラー分類をこの文書へ合わせる
- #54はTrack/Segmentと取得APIを実装する
- #55はStepAttempt、集約状態、工程再実行を実装する
- #56以降はelapsed millisecondsだけを同期基準に使用する
