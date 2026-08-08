# M4 実配信完了デモ手順

M4「配信を事前予約し、終了後に自動収集する」の実データ完了確認手順です。

CIのfixture検証は`apps/web/e2e/m4-completion.spec.ts`で、実際の`youtube-data-gateway`プロセスを含むフルスタック構成として実施します。ただし、M4完了には実在する開始予定または配信中のYouTube配信で、予約登録からM3閲覧までを手動収集操作なしで完了させる必要があります。

Railway検証環境を使用する場合は、先に[Railway検証環境の構築手順](./railway-verification-environment.md)を完了してください。

## 1. 対象配信の条件

次の条件を満たす、未登録の配信を使用します。

- 公開されているYouTubeライブ配信
- 開始予定または配信中で、デモ実施時間内に終了する見込みがある
- チャットリプレイが有効になる見込みがある
- 字幕が利用可能になる見込みがある
- メンバー限定、年齢制限、地域制限、非公開ではない
- 同じvideo IDを過去のM3/M4デモで登録していない

実配信の終了時刻やYouTube側のアーカイブ処理時間は制御できません。未確認範囲が残った場合はIssue #76と親Issue #68を閉じません。

## 2. ローカル実行時の設定

Railwayを使用しない場合は、秘密情報をリポジトリ、Issue、ログ、レポートへ記録せず、次を設定します。

```bash
export YSA_DATABASE_URL='postgres://...'
export YSA_YOUTUBE_API_KEY='...'
export YSA_YOUTUBE_API_BASE_URL='https://www.googleapis.com/youtube/v3'
export YSA_GATEWAY_TOKENS='<Gatewayが受理するtoken>'
export YSA_GATEWAY_CONTINUATION_SECRET='<32文字以上のsecret>'
export YSA_GATEWAY_BEARER_TOKEN='<Workerが送る同じtoken>'
export YSA_CHAT_REPLAY_BASE_URL='http://localhost:18081'
export YSA_TRANSCRIPT_BASE_URL='http://localhost:18081'
```

必要なサービスを別ターミナルで起動します。

```bash
make db-up
make db-migrate
make api
make gateway
make worker
make web
```

監視プロセス再起動の確認を行うため、ワーカーは独立したターミナルで起動します。

## 3. 予約登録

1. Web UIの`/reservations/new`を開く
2. 対象の開始予定または配信中URLを入力する
3. 動画IDを確認し、解析予約を登録する
4. 予約詳細URLからReservation IDを記録する
5. 初期状態と登録時刻を確認する

収集開始APIやM3の収集開始ボタンは操作しません。

## 4. 監視プロセス再起動

予約が`scheduled`、`monitoring`、または`live`の間にワーカーを一度停止し、同じ環境変数で再起動します。

Railwayでは`worker`サービスの既存DeploymentをRestartします。ローカルでは次のように再起動します。

```text
Ctrl+C
make worker
```

再起動後も同じReservation IDが監視され、状態が継続更新されることを確認します。

## 5. 終了後の自動収集

Web UIの予約詳細で、次の状態を確認します。

```text
scheduled または monitoring
→ live
→ waiting_for_archive
→ collecting
→ completed
```

配信終了後、YouTube側でアーカイブとチャットリプレイが利用可能になるまで`waiting_for_archive`が継続することがあります。`collecting`への遷移後も、利用者は収集開始操作を行いません。

## 6. M3閲覧確認

`completed`になった予約から「収集済み配信を開く」を選択し、次を確認します。

- プレーヤー、チャット、字幕が同一画面に表示される
- 再生位置周辺のチャットと字幕が同期表示される
- 実在する語でチャット・字幕検索ができる
- タイムライン項目または検索結果から該当時刻へ移動できる
- CollectionJobが1件だけ作成されている

字幕が存在しない配信を使った場合は件数を記録できますが、字幕を含むM3同期閲覧の確認は未完了として扱います。

## 7. 証跡レポート

ローカルでは次のコマンドを実行します。

```bash
cd apps/api
go run ./cmd/m4-demo-report \
  -reservation-id '<reservation-uuid>' \
  -strict \
  -worker-restart-confirmed \
  -m3-sync-confirmed \
  -m3-search-confirmed \
  -m3-seek-confirmed
```

Railwayでは`api`サービスへSSHし、コンテナ内で次を実行します。

```bash
./m4-demo-report \
  -reservation-id '<reservation-uuid>' \
  -strict \
  -worker-restart-confirmed \
  -m3-sync-confirmed \
  -m3-search-confirmed \
  -m3-seek-confirmed
```

JSONが必要な場合は`-format json`、ファイル出力する場合は`-output /tmp/m4-demo-report.md`を追加します。

レポートには次を含みます。

- Reservation IDとYouTube video ID
- 予約、配信、収集の時刻
- 予約状態遷移
- 自動作成されたCollectionJob IDと工程状態
- 同一streamのCollectionJob件数
- チャット保存件数と字幕保存件数
- ワーカー再起動、M3同期表示、検索、時刻ジャンプの確認結果
- M4完了条件のPASS / INCOMPLETE判定

レポートにはCookie、APIキー、チャット本文、字幕本文、認証ヘッダーを含めません。

## 8. Issueへの記録

PASSレポートをIssue #76へ貼り付け、次も明記します。

- デモ実施日
- 対象が予約時点で開始予定だったか配信中だったか
- ワーカーを再起動した時点の予約状態
- YouTube側のアーカイブ待機時間
- 未確認範囲

実配信でPASSになり、未確認範囲がなくなった場合に限りIssue #76を閉じます。その後、親Issue #68の完了条件を再確認します。
