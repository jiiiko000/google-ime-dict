# OpenWhispr 連携の追加と integrations/ への再編 — 設計書

日付: 2026-10-09
ブランチ: `openwhispr-integration`
状態: 設計承認済み（実装計画は未作成）

## 背景と目的

このリポジトリは Google 日本語入力（Mozc）用のユーザー辞書を管理している。`dict/` の
固有名詞を音声入力アプリに取り込む仕組みとして、すでに Amical 用の
`amical/import_to_amical.py` がある。今回、同じ辞書を **OpenWhispr** にも取り込めるようにする。

あわせて、アプリごとの取り込みスクリプトがリポジトリ直下に並ぶ状態をやめ、
`integrations/<アプリ名>/` にまとめる。

## 調査結果: OpenWhispr の語彙の仕組み

実装は OpenWhispr.app（Electron）の `app.asar` 内ソースと、ローカルの実データを読んで確認した。
以下はすべて実装の根拠になる事実。

### 保存先

`~/Library/Application Support/open-whispr/transcriptions.db`（SQLite, WAL）の
`custom_dictionary` テーブル。**単語のリストだけ**で、IME 辞書のような読み・品詞・
トリガーの概念はない。

```sql
CREATE TABLE custom_dictionary (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  word TEXT NOT NULL UNIQUE,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  client_dict_id TEXT, cloud_id TEXT,
  source TEXT NOT NULL DEFAULT 'manual',
  sync_status TEXT DEFAULT 'pending', deleted_at TEXT, updated_at DATETIME
);
```

- `source` は `'manual' | 'learned'` の2値のみ（`src/types/electron.ts` の型定義）。
  外部取り込み用の値は存在しないため `manual` を使う。
- `client_dict_id` は AFTER INSERT トリガが UUID を補完する。

### 効き方（2段階）

1. **STT プロンプトへのヒント** — `getCustomDictionaryPrompt()` が単語を `", "` で連結し、
   録音時の STT リクエストに載せる。`src/utils/dictionaryPromptCap.js` が上限を課し、
   **先頭から**切る（`trimDictionaryPrompt`）。

   | 条件 | 上限 |
   | --- | --- |
   | Groq | 890字 |
   | Whisper 系（`whisper-large-v3` など） | 900字（デコーダが実際に読むのは約550字） |
   | `gpt-4o-transcribe` 系 | 8,000字 |

2. **cleanup（LLM）プロンプトへの全件注入** — 認識後の整形プロンプト末尾に
   `"\n\nCustom Dictionary (use these exact spellings when they appear in the text): "`
   に続けて**全件**が入る（`src/config/prompts/index.ts` の `appendDictionarySuffix`）。
   こちらに上限はない。

### `snippets` は使えない

`snippets(trigger, replacement)` は文字起こし後の置換機能だが、`src/utils/snippets.ts` の
`expandSnippets` は次の正規表現で展開する。

```js
(?<=^|[\s\p{P}\p{S}])(?:trigger…)(?=$|[\s\p{P}\p{S}])
```

**Unicode 単語境界が必須**で、かな・漢字は `\p{L}`（境界ではない）ため、日本語の文中に
現れるカナトリガーは発火しない。Amical のような部分文字列置換ではないので、逆に
Amical の `EXCLUDE_READINGS` に相当する誤爆対策も不要。

### 公式のローカル HTTP API（CLI ブリッジ）

`~/.openwhispr/cli-bridge.json`（mode 0600）に `{version, port, token}` が書かれる。
port は 8200〜8219、loopback のみ、`Authorization: Bearer <token>` 必須。

| メソッド | パス | 用途 |
| --- | --- | --- |
| `GET` | `/v1/dictionary/list` | `{data: [word, …]}` |
| `POST` | `/v1/dictionary/update` | `{add: [...], remove: [...]}` → `{data: {words, added, removed}}` |

`add`/`remove` の検証は「文字列の配列であること」のみで、語数・文字種・空白の制限はない。
実測で `GET /v1/dictionary/list` が 200 を返すことを確認済み。

アプリ内コメントに「SQLite を直接書くと次の起動で行が消え、クラウドにも届かない (#1295)」
と明記されており、**DB 直書きは非推奨**。

### Amical との対比

| | Amical | OpenWhispr |
| --- | --- | --- |
| 保存先 | `amical.db` の `vocabulary` テーブル | `transcriptions.db` の `custom_dictionary` |
| 投入経路 | SQLite へ直接 `insert or ignore` | ローカル HTTP API |
| アプリの状態 | **終了している必要がある** | **起動している必要がある** |
| 語の概念 | 置換（トリガー→置換先）とヒントの2種 | 単語リストのみ |
| 読みの扱い | カタカナ化してトリガーに使う | 使わない |
| 同期 | ローカルのみ | OpenWhispr アカウントへクラウド同期される |

## 決定事項

### 1. ディレクトリ構成

```
README.md                          # OpenWhispr 節を追加、辞書一覧の語数を修正
CLAUDE.md                          # パス更新 + OpenWhispr 手順
dict/                              # 変更なし
integrations/
  common/
    dict_entries.py                # dict/ の読み込み（不変条件を1箇所に）
  amical/                          # ← 現 amical/ を git mv
    import_to_amical.py            # 共通モジュールを使うよう小改修
    README.md
  openwhispr/
    import_to_openwhispr.py
    words.txt                      # 投入する語（1行1語、順序=優先度）
    README.md
```

移動は `git mv` で履歴を保つ。リポジトリ直下の空 `openwhispr/` は削除する。

### 2. 共通モジュール `integrations/common/dict_entries.py`

`load_entries()` を提供し、両スクリプトから `sys.path` 経由で import する
（スクリプトは従来どおり `python3 integrations/amical/import_to_amical.py` で直接実行できる）。

責務は `dict/**/*_terms.txt` を再帰的に読み、次を行うことだけ:

- 空行と `#` 始まりの行をスキップ
- 列数が3でない行は警告してスキップ
- 品詞が `固有名詞` の行だけを対象にする
- `(読み, 単語)` の重複を排除
- ファイル順・行順を保持して `(読み, 単語)` を返す

**理由**: 「3列固定・固有名詞のみ」はこのリポジトリの核となる不変条件なので、2箇所に
複製すると片方だけ緩くなる。

### 3. `integrations/openwhispr/import_to_openwhispr.py`

1. `words.txt` を読む（1行1語、`#` 始まりはコメント、**順序を保持**、大小文字を無視して重複排除）
2. `dict/` の固有名詞と照合し、**`words.txt` にあるが `dict/` に無い語は警告**する（タイポ・陳腐化の検出）。
   警告のみで**投入はする**。ユーザーが明示的に列挙した語を黙って落とす方が事故になるため
3. `~/.openwhispr/cli-bridge.json` から port と token を読み、`GET /v1/dictionary/list` で現在の語を取得
4. **差分だけ** `POST /v1/dictionary/update {"add": [...]}` する。**`remove` は送らない**
5. `--dry-run` は 2〜4 の結果を表示するだけで POST しない
6. 次の場合は何をする必要があるかを示すエラーで終了する
   - `~/.openwhispr/cli-bridge.json` が無い →「OpenWhispr を起動してください」
   - ブリッジに接続できない（アプリが落ちている等）、または 401/404 が返る

`snippets` は使わない（前述の理由）。追加した語がクラウド同期される点は README に明記する。

**「追加のみ」にする理由**: ユーザーがアプリの UI や音声で手動追加した語を、スクリプトの
再実行で消してしまわないため。既存語はアプリ側の `applyDictionaryChanges` がスキップする
ので、再実行は冪等になる。語を減らしたいときはアプリの Settings > Dictionary から削除する。

### 4. `words.txt` の初期内容

固有名詞は 301語・2,773字（`, ` 区切り換算、平均9.2字/語）あり、STT ヒントの上限
（890字 ≒ 約95語）を超える。そこで STT に効かせたい語を `words.txt` に明示的に列挙し、
**約85語**を初期値とする（上限ちょうどではなく余裕を残す）。選定基準は「Whisper が
誤りやすい英字の製品名・モデル名」で、グループ分けのコメントを付ける。初期リストは
ドラフトであり、ユーザーが編集する前提。

`remove` を送らないため、**順序は初回投入時に確定**する（`add` の順 = 挿入順 =
`getDictionary()` の `ORDER BY id ASC`）。後から並べ替えるにはアプリ UI で対象語を
削除してから再実行する。手順は README に書く。

### 5. ドキュメント更新

- `README.md`: OpenWhispr への取り込み節を追加。辞書一覧の語数を実測値に修正する
  （`dict/技術/ai_terms.txt` は「181語」と書かれているが実際は290行 = 固有名詞143 + 名詞147）
- `CLAUDE.md`: スクリプトのパスを `integrations/` に更新し、OpenWhispr の手順を追記

## 却下した代替案

| 案 | 却下理由 |
| --- | --- |
| SQLite へ直接書き込む | アプリ内コメントで明示的に非推奨（#1295）。次回起動で行が消え、クラウドにも届かない |
| `snippets` でカナ→英字置換 | Unicode 単語境界必須のため日本語文中で発火しない |
| `dict/` に4列目（優先フラグ）を足す | 3列固定の不変条件を壊す。Amical スクリプトが警告してスキップし、Google IME のインポートも崩れる |
| 辞書ファイル単位で選ぶ | 粒度が粗すぎる。`ai` だけで1,386字、`cloud+dev` で1,030字と上限を超え、`dev+web`(84語) は恣意的 |
| 優先リストをスクリプト内に持つ | `words.txt` の方が一覧しやすく、順序を表現でき、Python を触らず語を足せる |
| 3列形式の専用ファイル | `dict/` と同じ三列を手で維持することになり、二重管理が最も重い |

## 受け入れ基準

- `python3 integrations/openwhispr/import_to_openwhispr.py --dry-run` が、
  追加予定の語・すでに入っている語・`words.txt` と `dict/` の不整合を表示し、POST しない
- 本実行後、OpenWhispr の Settings > Dictionary と `GET /v1/dictionary/list` に語が現れる
- もう一度実行しても二重登録されない（冪等）
- OpenWhispr が起動していないときは、何をする必要があるかを示すエラーで終了する
- `python3 integrations/amical/import_to_amical.py --dry-run` が移動後も従来どおり動く

## 留保（実測して調整する）

- `whisper-large-v3` はプロンプトを**後方から**切る（223トークン ≒ 550字）ため、
  `words.txt` の**後半ほど STT に効き、前半は cleanup プロンプト経由でのみ効く**という
  逆転が起きうる。初回投入後に実際に音声で試し、必要なら並び順を入れ替える
- 上記はプロバイダ依存（`gpt-4o-transcribe` 系には窓がない）。cleanup 経由では常に全件が
  効くため、語が「まったく効かない」ことはない
