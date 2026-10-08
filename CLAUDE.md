# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概要

Google日本語入力（Mozc）用ユーザー辞書のデータリポジトリ。ビルド・lint は存在せず、成果物は `dict/` 配下の辞書テキスト自体。コードは音声入力アプリへ辞書を取り込むスクリプト一式で、`integrations/` 配下に置く（Python標準ライブラリのみ、依存関係なし）。

- [integrations/common/dict_entries.py](integrations/common/dict_entries.py) — `dict/` の読み込み。3列・固有名詞のみという不変条件はここ1箇所
- [integrations/amical/import_to_amical.py](integrations/amical/import_to_amical.py) — Amical 用
- [integrations/openwhispr/import_to_openwhispr.py](integrations/openwhispr/import_to_openwhispr.py) — OpenWhispr 用

テストは `python3 -m unittest discover -s tests -v`（リポジトリ直下）で走る。

## 辞書ファイルの不変条件

`dict/` 配下の `*_terms.txt` が辞書ファイル（技術系は `dict/技術/`、それ以外は `dict/一般/`）。UTF-8 / タブ区切り / 3列固定：

```
読み(ひらがな)	単語	品詞
```

- 列数が3でない行は Amical スクリプトが警告してスキップする。タブをスペースにしないこと
- `#` 始まりの行はカテゴリ見出しコメント（`# ===== 企業・組織 =====`）。Mozc の辞書ツールもスクリプトも無視する
- 読みはひらがなのみ。Amical 側でカタカナ化して置換トリガーに使うため、ここが崩れると音声入力側も壊れる
- 品詞は主に `固有名詞` と `名詞`。**`固有名詞` だけが音声入力アプリ（Amical / OpenWhispr）に取り込まれる**（日本語の一般用語は Whisper がそのまま正しく書き起こすため）。新語を追加するときはこの区別を意識する

## よくある作業

### 語を追加・削除する

1. 該当する `*_terms.txt` の適切なカテゴリコメントの下に追記（音声入力アプリに反映したい固有名詞は品詞を `固有名詞` に）
2. README の辞書一覧に語数が書かれているので更新する
3. 反映したいアプリの取り込みを実行 — Amical は `dict/` の固有名詞を全部入れるが、OpenWhispr は `words.txt` に列挙した語だけなので、必要なら `words.txt` にも追記する

### Amical へ取り込む

```bash
python3 integrations/amical/import_to_amical.py --dry-run   # 投入内容の確認（DB非破壊）
python3 integrations/amical/import_to_amical.py             # 実行（要 Amical 終了。DBは自動バックアップ）
python3 integrations/amical/import_to_amical.py --db path/to/amical.db   # DBパス指定
```

`~/Library/Application Support/Amical/amical.db` の `vocabulary` テーブル（`word`, `replacement_word`, `is_replacement`）に `insert or ignore` で直接投入する。`word` が一意キーのため、辞書に語を足して再実行すれば差分だけ入る。実行前に Amical プロセスを `pgrep` で検出して起動中なら中断し、`amical.db.bak-<日付>` を作る。

### OpenWhispr へ取り込む

```bash
python3 integrations/openwhispr/import_to_openwhispr.py --dry-run   # 投入内容の確認（API非破壊）
python3 integrations/openwhispr/import_to_openwhispr.py             # 実行（要 OpenWhispr 起動）
```

投入する語は `integrations/openwhispr/words.txt` に1行1語で明示する（STT ヒントの上限に収めるため、`dict/` の固有名詞を全部は入れない）。行の並び順が初回投入時の優先度になる。語を足すときは `dict/` と `words.txt` の両方に追記する。

**Amical と違い、OpenWhispr は起動している必要がある。** SQLite（`~/Library/Application Support/open-whispr/transcriptions.db` の `custom_dictionary`）を直接書かず、アプリのローカル HTTP API（CLIブリッジ、`~/.openwhispr/cli-bridge.json` の port + token）の `POST /v1/dictionary/update` に差分の `add` だけを送る。**削除はしない**ので、手で入れた語は消えない。減らしたいときは Settings > Dictionary から削除し、`words.txt` からも消す。追加した語は OpenWhispr アカウントへクラウド同期される。

`snippets`（トリガー→置換）は使わない。展開が Unicode 単語境界必須でかな・漢字が境界にならず、日本語文中のカナトリガーが発火しないため。

### 誤爆する置換を直す（Amical）

Amical の置換は CJK に対して**単語境界なしの部分文字列置換**。そのため短い読みを置換トリガーにすると一般語を壊す（「ごー」→Go だと「ゴール」が「Goル」になる）。誤爆を見つけたら：

1. 読みをスクリプトの `EXCLUDE_READINGS` に理由コメント付きで追加
2. Amical の Settings > Dictionary から該当の置換エントリを手動削除（追加だけではDB上の既存エントリは消えない）
3. スクリプトを再実行

除外された読みの表記は置換ではなく**ヒントモード**（`is_replacement=0`、AIプロンプトへの注入、直近200語のみ有効）で登録される。ただし別の読みで置換登録済みの表記はヒントに入れない（`build_rows` の `replaced_words` 判定）。

### Windows向けに配布する

Windows版 Google日本語入力は UTF-8 でインポートに失敗することがあるため UTF-16LE(BOM) に変換して渡す（コマンドは README 参照）。`*_win.txt` は `.gitignore` 済み — コミットせず都度生成する。
