# YouTube Data Gateway

YouTube固有のチャットリプレイ・字幕取得処理を、配信収集Workerから隔離する内部HTTPサービスです。

## 設定

```bash
export YSA_GATEWAY_TOKENS='local-current-token,local-previous-token'
export YSA_GATEWAY_CONTINUATION_SECRET='replace-with-at-least-32-characters'
```

任意設定:

```bash
export YSA_GATEWAY_PROXY_URL='http://user:password@proxy.example:8080'
export YSA_GATEWAY_COOKIE_FILE='/run/secrets/youtube-cookies.txt'
export YSA_GATEWAY_REQUEST_TIMEOUT_SECONDS='20'
export YSA_GATEWAY_CHAT_PAGE_SIZE='500'
export YSA_GATEWAY_TRANSCRIPT_PAGE_SIZE='1000'
```

CookieファイルはNetscape形式を使用します。Cookie、Bearer token、プロキシ認証情報をリポジトリ、Issue、通常ログへ保存しません。

## 起動

```bash
cd apps/youtube-data-gateway
python -m pip install -e '.[dev]'
ysa-youtube-data-gateway
```

## 確認

```bash
curl http://localhost:8080/healthz
curl http://localhost:8080/readyz
curl -H 'Authorization: Bearer local-current-token' \
  'http://localhost:8080/v1/transcripts/tracks?videoId=<video-id>'
```

## 取得方式

- チャットリプレイ: yt-dlpのYouTube抽出・Innertube設定生成を利用し、Gatewayが1ページ単位で取得・正規化する
- 字幕: `youtube-transcript-api`でトラックと字幕セグメントを取得し、Gateway契約へ正規化する

両方ともYouTubeの非公開Web APIへ依存するため、外部仕様変更は`YOUTUBE_SOURCE_CHANGED`として明示します。

クラウド事業者のIPアドレスはYouTubeに遮断される場合があります。`YOUTUBE_RATE_LIMITED`または`YOUTUBE_TEMPORARILY_UNAVAILABLE`が継続する場合は、検証環境へ住宅系の回転プロキシを設定します。アカウントCookieは公開配信でプロキシを代替する目的には使用しません。
