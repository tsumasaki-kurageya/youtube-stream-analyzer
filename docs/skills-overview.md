# Skills 概要一覧

最終確認日: 2026-07-30

この文書は、現在の環境で `SKILL.md` が確認できた Skills を1か所にまとめたものです。

## 見方

- **利用可**: このセッションの「Available skills」カタログに掲載されている Skill。依頼内容が説明に合えば Codex が利用します。
- **保存済み**: `SKILL.md` は存在しますが、現在のセッションのカタログには掲載されていない Skill。インストール直後の再読み込み、プラグインの有効化、依存機能などの確認が必要な場合があります。
- Skill は通常、名前を明示するか、説明に合う依頼をすると選択されます。名前を明示したい場合は「`tdd` を使って実装して」のように依頼します。
- ディスク上にあることと、そのセッションで実際に選択可能であることは同義ではありません。

## 全体像

| 配置元 | 件数 | 利用可 | 保存済み |
|---|---:|---:|---:|
| Codex システム | 6 | 5 | 1 |
| Figma プラグイン | 12 | 12 | 0 |
| GitHub プラグイン | 4 | 4 | 0 |
| Slack プラグイン | 6 | 6 | 0 |
| OpenAI Templates プラグイン | 20 | 0 | 20 |
| このリポジトリ | 42 | 17 | 25 |
| **合計** | **90** | **44** | **46** |

## Codex システム Skills

配置場所: `/home/vscode/.codex/skills/.system`

| Skill | 状態 | 概要 |
|---|---|---|
| `imagegen` | 利用可 | 写真、イラスト、テクスチャ、スプライト、モックアップなどのラスター画像を生成・編集する。SVGやHTML/CSSで作るべき視覚要素には使わない。 |
| `openai-docs` | 利用可 | OpenAI API、ChatGPT、Codex、モデル選定などを、最新の公式ドキュメントに基づいて調査・説明する。 |
| `plugin-creator` | 利用可 | Codex プラグインのディレクトリ、マニフェスト、任意の構成、個人マーケットプレイス登録を作成・更新する。 |
| `review-agent` | 保存済み | 指定された差分を読み取り専用でレビューし、実際に修正可能な不具合を優先して報告する、委譲用レビュー Skill。 |
| `skill-creator` | 利用可 | 専門知識やワークフロー、ツール連携を持つ新しい Skill の設計・作成・改善を支援する。 |
| `skill-installer` | 利用可 | curated list または GitHub リポジトリから Codex Skills をインストールする。インストール候補の一覧にも使う。 |

## Figma プラグイン Skills

配置元: Figma プラグイン `2.0.16`

| Skill | 状態 | 概要 |
|---|---|---|
| `figma:figma-code-connect` | 利用可 | Figma コンポーネントと実装コードのスニペットを対応付ける Code Connect の `.figma.ts` / `.figma.js` を作成・保守する。 |
| `figma:figma-create-new-file` | 利用可 | 新しい Design、FigJam、Slides ファイルを作る前に必ず使う前提 Skill。ファイル種別と名前を整理して作成処理へつなぐ。 |
| `figma:figma-design-to-code` | 利用可 | Figma デザインをアプリケーションコードへ実装するための手順を提供する。デザインコンテキスト取得前の必須 Skill。 |
| `figma:figma-generate-design` | 利用可 | コードや説明から、ページ、モーダル、サイドバーなどの複合画面を Figma に組み立てる。既存トークンやコンポーネントを優先する。 |
| `figma:figma-generate-diagram` | 利用可 | フローチャート、構成図、シーケンス図、ERD、状態図、ガント、タイムラインなどを FigJam に生成する前提と制約を扱う。 |
| `figma:figma-generate-library` | 利用可 | コードベースから Figma の変数、トークン、テーマ、コンポーネント、バリアントを備えたデザインシステムを構築・更新する。 |
| `figma:figma-implement-motion` | 利用可 | Figma 上のモーションやアニメーションを、本番向けアプリケーションコードへ変換する。 |
| `figma:figma-swiftui` | 利用可 | Figma と SwiftUI を双方向に変換する。iOS/iPhone/iPad 画面のデザイン実装や、SwiftUI から Figma への反映に使う。 |
| `figma:figma-use` | 利用可 | Figma 内でノード、変数、トークン、コンポーネント、Auto Layout などを JavaScript で読み書きする際の必須基盤 Skill。 |
| `figma:figma-use-figjam` | 利用可 | `figma-use` に FigJam 固有の操作コンテキストを追加する。 |
| `figma:figma-use-motion` | 利用可 | `figma-use` にキーフレーム、イージング、継続時間などのモーション操作を追加する。 |
| `figma:figma-use-slides` | 利用可 | `figma-use` に Figma Slides 固有の操作コンテキストを追加する。 |

## GitHub プラグイン Skills

配置元: GitHub プラグイン `0.1.8-2841cf9749ae`

| Skill | 状態 | 概要 |
|---|---|---|
| `github:gh-address-comments` | 利用可 | Pull Request の未解決レビュー、変更要求、インラインコメントを調べ、選択した指摘を実装して対処する。 |
| `github:gh-fix-ci` | 利用可 | GitHub Actions の失敗チェックとログを調査し、原因を特定して承認された修正を実装する。 |
| `github:github` | 利用可 | リポジトリ、Issue、Pull Request の一般的な調査・要約・トリアージを行い、適切な GitHub ワークフローへ案内する。 |
| `github:yeet` | 利用可 | ローカル変更の範囲を確認し、意図的にコミット、push、Draft Pull Request 作成まで進める公開ワークフロー。 |

## Slack プラグイン Skills

配置元: Slack プラグイン `0.1.4`

| Skill | 状態 | 概要 |
|---|---|---|
| `slack:slack` | 利用可 | Slack の会話を読み、依頼に合う Slack ワークフローへ振り分け、読み取りや書き込みを行う基盤 Skill。 |
| `slack:slack-channel-summarization` | 利用可 | 1つの Slack チャンネルの活動を、短い要約、投稿用アップデート、サマリードキュメントにまとめる。 |
| `slack:slack-daily-digest` | 利用可 | 選択したチャンネルやトピックから、その日の Slack ダイジェストを作る。 |
| `slack:slack-notification-triage` | 利用可 | 最近の Slack 活動を優先順位付きキューやタスクリストに整理する。 |
| `slack:slack-outgoing-message` | 利用可 | Slack に送るメッセージや Canvas の文章を作成・推敲する。送信・下書き作成を伴う場合の中心 Skill。 |
| `slack:slack-reply-drafting` | 利用可 | Slack の文脈から返信が必要そうなメッセージを見つけ、返信案を作る。 |

## OpenAI Templates プラグイン Skills

配置元: OpenAI Templates プラグイン `0.1.0`

これらは、名前どおりの成果物テンプレートをユーザーが選択したときに使う Skills です。現在はファイルが保存されていますが、このセッションの利用可能カタログには掲載されていません。

| Skill | 状態 | 成果物 | 概要 |
|---|---|---|---|
| `artifact-template-analytics-dashboard` | 保存済み | スプレッドシート | 獲得、エンゲージメント、継続、売上、コンバージョンファネルの KPI をグラフ付きで監視する。 |
| `artifact-template-business-review` | 保存済み | プレゼンテーション | 業績、KPI、セグメント結果、戦略優先事項、意思決定、見通しをレビューする。 |
| `artifact-template-design-report` | 保存済み | ドキュメント | エグゼクティブサマリー、主要所見、示唆、推奨事項、付録を含むデザインレポートを作る。 |
| `artifact-template-experiment-analysis` | 保存済み | ドキュメント | 仮説、方法、結果、解釈、限界、次のアクションを含む実験分析を作る。 |
| `artifact-template-financial-budget` | 保存済み | スプレッドシート | 実績、予算、シナリオ予測、差異、キャッシュランウェイ、部門計画をモデル化する。 |
| `artifact-template-investment-committee-memo` | 保存済み | ドキュメント | 投資仮説、取引詳細、財務分析、リスク、推奨判断を含む投資委員会メモを作る。 |
| `artifact-template-legal-memorandum` | 保存済み | ドキュメント | 論点、簡潔な回答、関連事実、分析、結論を備えたリーガルメモを作る。 |
| `artifact-template-market-trends-report` | 保存済み | プレゼンテーション | 市場・業界トレンド、裏付け、示唆、推奨対応を伝える。 |
| `artifact-template-minimal-letterhead` | 保存済み | ドキュメント | 差出人、宛先、本文、署名を持つミニマルなレターヘッド形式のビジネス文書を作る。 |
| `artifact-template-operating-calendar` | 保存済み | スプレッドシート | 年次・月次のマイルストーン、キャンペーン、ローンチ、期限、定例イベントを計画する。 |
| `artifact-template-operating-review` | 保存済み | プレゼンテーション | スコアカード、部門更新、リスク、意思決定、アクションを含む週次運営レビューを作る。 |
| `artifact-template-project-kickoff` | 保存済み | プレゼンテーション | 目標、スコープ、役割、マイルストーン、リスク、働き方をチームでそろえる。 |
| `artifact-template-project-tracker` | 保存済み | スプレッドシート | ワークストリーム、タスク、担当者、状態、優先度、日付、ガント予定を管理する。 |
| `artifact-template-sales-pipeline` | 保存済み | スプレッドシート | 商談、ステージ、担当者、金額、確度、予測、次の一手、リスクを追跡する。 |
| `artifact-template-simple-dark-mode` | 保存済み | プレゼンテーション | 太いタイポグラフィ、シンプルなセクション、チャート、画像を使うダークテーマの資料を作る。 |
| `artifact-template-simple-light-mode` | 保存済み | プレゼンテーション | 余白のあるタイポグラフィ、シンプルなセクション、チャート、画像を使うライトテーマの資料を作る。 |
| `artifact-template-strategy-memorandum` | 保存済み | ドキュメント | 戦略的背景、選択肢、根拠、リスク、マイルストーン、明確な推奨をまとめる。 |
| `artifact-template-system-design` | 保存済み | ドキュメント | 要件、構成要素、データフロー、API、トレードオフ、運用を含むシステム設計を文書化する。 |
| `artifact-template-team-alignment` | 保存済み | プレゼンテーション | オフサイトや計画会議向けに、背景、目標、優先事項、意思決定、アクションを整理する。 |
| `artifact-template-three-statement-forecast` | 保存済み | スプレッドシート | 損益計算書、貸借対照表、キャッシュフローを連動させた財務予測を作る。 |

## このリポジトリの Skills

配置場所: `.agents/skills/`、`.codex/skills/`

| Skill | 状態 | 概要 |
|---|---|---|
| `ask-matt` | 保存済み | 状況に合う Skill やフローを選ぶための、この Skill 集のルーター。 |
| `batch-grill-me` | 保存済み | 計画や設計の未解決点を、ラウンドごとにまとめて質問する集中的なインタビュー。 |
| `claude-handoff` | 保存済み | 現在の会話を新しいバックグラウンドエージェントへ引き継ぎ、作業を継続させる。 |
| `code-review` | 利用可 | 固定した比較起点以降の変更を「リポジトリ標準」と「仕様適合」の2軸で並列レビューする。 |
| `codebase-design` | 利用可 | 深いモジュール、境界、インターフェース、テスト容易性、AI による探索容易性を考える共通語彙を提供する。 |
| `design-an-interface` | 利用可 | 1つのモジュールに対して大きく異なる複数のインターフェース案を並列生成し、比較する。 |
| `diagnosing-bugs` | 利用可 | 難しいバグ、例外、失敗、速度低下を、仮説と検証を繰り返して診断する。 |
| `domain-modeling` | 利用可 | プロジェクトのドメインモデル、用語、ユビキタス言語を整理し、必要に応じて設計判断を記録する。 |
| `edit-article` | 保存済み | 記事の構成を組み直し、明瞭さを上げ、文章を引き締める。 |
| `git-guardrails-claude-code` | 利用可 | Claude Code に hooks を設定し、push、`reset --hard`、clean、強制的なブランチ削除など危険な Git 操作を防ぐ。 |
| `grill-me` | 保存済み | 計画や設計を鋭くするため、未解決点を粘り強く質問するインタビュー。 |
| `grill-with-docs` | 保存済み | 計画や設計を質問で詰めながら、ADR と用語集も同時に作る。 |
| `grilling` | 利用可 | 計画、判断、アイデアを厳しくストレステストし、曖昧さや弱い前提をあぶり出す。 |
| `graphify` | 保存済み | コード、文書、設定等をローカルの知識グラフへ変換し、構造や関係を照会する。プロジェクトスコープの Codex Skill。 |
| `handoff` | 保存済み | 現在の会話と作業状況を、別のエージェントが再開できる引き継ぎ文書に圧縮する。 |
| `implement` | 保存済み | 仕様書またはチケット群に基づいて、作業を実装する。 |
| `improve-codebase-architecture` | 保存済み | コードベースのモジュール深化候補を探し、視覚的な HTML レポートを作り、選択した候補を掘り下げる。 |
| `loop-me` | 保存済み | このワークスペースで作りたいワークフローの仕様を、反復的な質問で固める。 |
| `migrate-to-shoehorn` | 利用可 | テスト内の `as` 型アサーションを `@total-typescript/shoehorn` を使う部分テストデータへ移行する。 |
| `obsidian-vault` | 利用可 | Obsidian Vault 内のノートを検索・作成・整理し、wikilink と索引ノートを管理する。 |
| `prototype` | 利用可 | 状態モデル、ロジック、UI の感触を確かめるため、捨てる前提の小さなプロトタイプを作る。 |
| `qa` | 利用可 | 会話形式で不具合報告を受け、コードベースの文脈を調べながら GitHub Issue として整理・登録する。 |
| `request-refactor-plan` | 利用可 | ユーザーへのインタビューから、小さなコミット単位の詳細なリファクタ計画を作り、GitHub Issue にする。 |
| `research` | 利用可 | 信頼度の高い一次情報を調査し、結果をリポジトリ内の Markdown ファイルに保存する。 |
| `resolving-merge-conflicts` | 利用可 | 進行中の Git merge / rebase の競合を安全に解消する。 |
| `scaffold-exercises` | 利用可 | セクション、問題、解答、解説を持つ演習ディレクトリを作り、lint を通る雛形にする。 |
| `setup-matt-pocock-skills` | 保存済み | Issue tracker、トリアージ用ラベル、ドメイン文書構成を準備し、このエンジニアリング Skill 集を初期設定する。 |
| `setup-pre-commit` | 利用可 | Husky、lint-staged、Prettier、型チェック、テストを使う pre-commit 検証をセットアップする。 |
| `setup-ts-deep-modules` | 保存済み | TypeScript リポジトリに dependency-cruiser を導入し、各 package の内部実装を entry point の背後に隠す。 |
| `tdd` | 利用可 | Red–Green–Refactor のテスト駆動で機能追加やバグ修正を進め、必要に応じて統合テストを作る。 |
| `teach` | 保存済み | このワークスペースを題材に、新しい Skill や概念をユーザーへ教える。 |
| `to-questionnaire` | 保存済み | 自分たちだけでは決められない判断事項を、別の関係者が回答できる質問票に変換する。 |
| `to-spec` | 保存済み | 追加インタビューなしで、現在までの会話を仕様書にまとめ、プロジェクトの Issue tracker へ公開する。 |
| `to-tickets` | 保存済み | 計画や仕様を、依存関係を明記した tracer-bullet 型の小さなチケット群へ分割し、tracker に公開する。 |
| `triage` | 保存済み | Issue と外部 Pull Request を分類、検証、追加質問、実装可能な brief 作成という状態遷移でトリアージする。 |
| `ubiquitous-language` | 保存済み | 会話から DDD 形式の用語集を抽出し、曖昧さと推奨用語を示して `UBIQUITOUS_LANGUAGE.md` に保存する。 |
| `wayfinder` | 保存済み | 1セッションを超える大規模作業を、Issue tracker 上の意思決定チケットの地図として計画し、順に解決する。 |
| `wizard` | 保存済み | 外部サービス設定や一度限りの移行を人間が手順どおり進められる、対話式 Bash wizard を生成する。 |
| `writing-beats` | 保存済み | 素材を読者の理解順に並べ、各用語を必要になる前に説明する「beats」の流れを作る。 |
| `writing-fragments` | 保存済み | 構成を決める前に、文章の素材・断片・アイデアを広く掘り出す。 |
| `writing-great-skills` | 保存済み | 予測可能で使いやすい Skill を書くための語彙と設計原則を提供する。 |
| `writing-shape` | 保存済み | 生の素材を段落単位で整理し、記事全体の形に組み立てる。 |

## 未インストールと表示された推奨プラグイン

以下は今回の棚卸し時点で「available but not installed」と明記されていたプラグインです。上記89件の Skills には含めていません。

| プラグイン | 主な用途 |
|---|---|
| Atlassian Rovo | Jira、Confluence など Atlassian 製品の情報検索・操作 |
| Box | Box 内のファイル検索・参照・管理 |
| Gmail | Gmail の検索、要約、下書き、送信 |
| Google Calendar | Google Calendar の予定検索・作成・変更 |
| Google Drive | Google Drive のファイル検索・参照・管理 |
| Notion | Notion のページやデータベースの検索・編集 |
| Outlook Calendar | Outlook Calendar の予定検索・作成・変更 |
| Outlook Email | Outlook メールの検索、要約、下書き、送信 |
| SharePoint | SharePoint のサイトや文書の検索・参照・管理 |
| Teams | Microsoft Teams の会話やチャンネルの検索・投稿 |

## 使い分けの早見表

| やりたいこと | 最初に検討する Skill |
|---|---|
| バグの原因を調べたい | `diagnosing-bugs` |
| テストから実装したい | `tdd` |
| 変更差分をレビューしたい | `code-review` |
| API やモジュール境界を設計したい | `codebase-design`、`design-an-interface` |
| 計画の弱点を洗い出したい | `grilling` |
| 小さく試作して判断したい | `prototype` |
| 技術調査を文書に残したい | `research` |
| リファクタを安全な手順に分けたい | `request-refactor-plan` |
| Figma をコードにしたい | `figma:figma-design-to-code` |
| コードや説明を Figma にしたい | `figma:figma-generate-design` と `figma:figma-use` |
| GitHub Actions の失敗を直したい | `github:gh-fix-ci` |
| PR レビューコメントへ対応したい | `github:gh-address-comments` |
| 変更を commit、push、Draft PR にしたい | `github:yeet` |
| Slack を要約したい | `slack:slack-channel-summarization` または `slack:slack-daily-digest` |
| Skill 自体を作りたい | `skill-creator` |
| Skill を追加インストールしたい | `skill-installer` |
