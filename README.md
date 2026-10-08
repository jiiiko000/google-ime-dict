# Google日本語入力 ユーザー辞書コレクション

Google日本語入力（Mozc）用のユーザー辞書をトピック別にまとめたリポジトリです。各辞書は UTF-8 / タブ区切り / `読み(ひらがな)\t単語\t品詞` の3列形式で、辞書ツールからそのままインポートできます。

## 辞書一覧

辞書ファイルは `dict/` 配下にトピックの性質で分けて置いています（技術系は `dict/技術/`、それ以外は `dict/一般/`）。

| ファイル | 内容 |
| --- | --- |
| `dict/技術/ai_terms.txt` | AI・機械学習用語（290語）。企業・モデル名（OpenAI, Anthropic, Sakana AI, Claude, Gemini, Kimi, GLM など）、ML基礎用語（勾配降下法, 過学習 など）、生成AI用語（RAG, ハルシネーション, エージェント, 推論時計算 など）、開発ツール・エージェント（Claude Code, Cursor, CrewAI, MCP など） |
| `dict/技術/dev_terms.txt` | 開発ツール・インフラ用語（92語）。コンテナ・K8s（Kubernetes, Helm, Istio など）、IaC（Terraform, Ansible など）、監視（Prometheus, Grafana, オブザーバビリティ など）、CI/CD・Git・ネットワーク用語 |
| `dict/技術/web_terms.txt` | プログラミング・Web技術用語（113語）。言語・フレームワーク（TypeScript, React, Next.js, Rails など）、開発ツール（Vite, ESLint, Playwright など）、概念（非同期処理, 冪等性, ハイドレーション, リファクタリング など） |
| `dict/技術/cloud_terms.txt` | クラウド・SaaS製品名（87語）。クラウド基盤（AWS, Google Cloud, Azure, Cloudflare など）、AWS/GCPサービス名（Lambda, S3, BigQuery など）、SaaS（Datadog, Slack, Notion, Figma, Jira など） |
| `dict/一般/general_terms.txt` | 汎用一般辞書（158語）。記号・矢印（→, ※, 〜, 【】 など）、日付・曜日・時間（上旬, 四半期, 年度末 など）、数量・単位（%, 万円, ㎡ など）、誤変換しやすい同音異義語（移動, 対象, 保証, 要件 など）、ビジネス挨拶・定型表現（お疲れ様です, 承知しました, 取り急ぎ など） |
| `dict/一般/business_it_terms.txt` | IT一般・ビジネス用語（107語）。DX・運用（オンプレミス, 冗長化, インシデント対応, SLA など）、セキュリティ（ゼロトラスト, 脆弱性診断, ISMS など）、プロジェクト管理（アジャイル, PoC, RFP など） |

各辞書ファイル内は `# =====` で始まるコメント行でカテゴリ分けしています。Google日本語入力の辞書ツールは `#` で始まる行を無視してインポートしますが、もしコメント行が原因でエラーになる場合は `grep -v '^#' dict/技術/ai_terms.txt > ai_terms_plain.txt` で除去したファイルを使ってください。

## Macでのインポート手順

1. Google日本語入力の環境設定を開く（メニューバーのGoogle日本語入力アイコン、または「システム設定 > キーボード > 入力ソース」経由）
2. 「辞書ツール」を開く
3. メニューの「管理対象の辞書」から「インポート...」を選択
4. 取り込みたい辞書ファイルを選択し、フォーマットは「Google」を選んでインポート

辞書ごとに別の「管理対象の辞書」としてインポートしておくと、トピック単位で更新・削除しやすくなります。

## Windowsでのインポート手順

1. Google日本語入力のプロパティ（タスクトレイのアイコンを右クリック > プロパティ）を開く
2. 「辞書ツール」を起動
3. 「管理対象の辞書」>「インポート」で辞書ファイルを選択

Windows版のGoogle日本語入力は文字コードによってインポートに失敗することがあります。うまく読み込めない場合は、事前に以下のコマンドでUTF-16LE（BOM付き）に変換したファイルを使ってください（`dict/技術/ai_terms.txt` の部分は対象ファイルのパスに読み替え）。

```bash
iconv -f UTF-8 -t UTF-16LE dict/技術/ai_terms.txt | { printf '\xff\xfe'; cat; } > ai_terms_win.txt
```

変換後のファイルをWindows機にコピーしてインポートします（`*_win.txt` は配布物として管理せず、必要になったタイミングで都度生成してください）。

## Amical（音声入力）への取り込み

音声入力アプリ [Amical](https://amical.ai/) の語彙にも、この辞書から固有名詞を取り込めます。変換の仕組みと使い方は [amical/README.md](amical/README.md) を参照してください。

```bash
python3 amical/import_to_amical.py --dry-run   # 投入内容の確認
python3 amical/import_to_amical.py             # 実行（Amical を終了してから。DBは自動バックアップ）
```

辞書に語を追加したら再実行すれば差分だけ追加されます（登録済みの語はスキップ）。

## 辞書を追加したいとき

### 既存の辞書に用語を追加する

対象の `.txt` に1行ずつ `読み(ひらがな)\t単語\t品詞` の形式で追記してください。品詞は基本的に固有名詞（企業名・製品名・人名）または名詞（一般的な用語）を使っています。

### 新しい辞書ファイルを作る

トピックごとに `<topic>_terms.txt` を `dict/技術/` または `dict/一般/` に追加し、上の「辞書一覧」の表に1行足してください。Amical 取り込みスクリプトは `dict/` 配下の **`_terms.txt` で終わるファイル**だけを読むので、この命名を守ってください。例:

- `dict/一般/company_terms.txt` — 社内用語・プロジェクト名・人名
- `dict/一般/finance_terms.txt` — 金融・会計用語
