# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概要

Google日本語入力（Mozc）用ユーザー辞書のデータリポジトリ。ビルド・テスト・lint は存在せず、成果物は `dict/` 配下の辞書テキスト自体。唯一のコードは音声入力アプリ Amical への取り込みスクリプト [integrations/amical/import_to_amical.py](integrations/amical/import_to_amical.py)（Python標準ライブラリのみ、依存関係なし）。

## 辞書ファイルの不変条件

`dict/` 配下の `*_terms.txt` が辞書ファイル（技術系は `dict/技術/`、それ以外は `dict/一般/`）。UTF-8 / タブ区切り / 3列固定：

```
読み(ひらがな)	単語	品詞
```

- 列数が3でない行は Amical スクリプトが警告してスキップする。タブをスペースにしないこと
- `#` 始まりの行はカテゴリ見出しコメント（`# ===== 企業・組織 =====`）。Mozc の辞書ツールもスクリプトも無視する
- 読みはひらがなのみ。Amical 側でカタカナ化して置換トリガーに使うため、ここが崩れると音声入力側も壊れる
- 品詞は主に `固有名詞` と `名詞`。**`固有名詞` だけが Amical に取り込まれる**（日本語の一般用語は Whisper がそのまま正しく書き起こすため）。新語を追加するときはこの区別を意識する

## よくある作業

### 語を追加・削除する

1. 該当する `*_terms.txt` の適切なカテゴリコメントの下に追記（Amical に反映したい固有名詞は品詞を `固有名詞` に）
2. README の辞書一覧に語数が書かれているので更新する
3. Amical にも反映するなら下記の取り込みを実行

### Amical へ取り込む

```bash
python3 integrations/amical/import_to_amical.py --dry-run   # 投入内容の確認（DB非破壊）
python3 integrations/amical/import_to_amical.py             # 実行（要 Amical 終了。DBは自動バックアップ）
python3 integrations/amical/import_to_amical.py --db path/to/amical.db   # DBパス指定
```

`~/Library/Application Support/Amical/amical.db` の `vocabulary` テーブル（`word`, `replacement_word`, `is_replacement`）に `insert or ignore` で直接投入する。`word` が一意キーのため、辞書に語を足して再実行すれば差分だけ入る。実行前に Amical プロセスを `pgrep` で検出して起動中なら中断し、`amical.db.bak-<日付>` を作る。

### 誤爆する置換を直す

Amical の置換は CJK に対して**単語境界なしの部分文字列置換**。そのため短い読みを置換トリガーにすると一般語を壊す（「ごー」→Go だと「ゴール」が「Goル」になる）。誤爆を見つけたら：

1. 読みをスクリプトの `EXCLUDE_READINGS` に理由コメント付きで追加
2. Amical の Settings > Dictionary から該当の置換エントリを手動削除（追加だけではDB上の既存エントリは消えない）
3. スクリプトを再実行

除外された読みの表記は置換ではなく**ヒントモード**（`is_replacement=0`、AIプロンプトへの注入、直近200語のみ有効）で登録される。ただし別の読みで置換登録済みの表記はヒントに入れない（`build_rows` の `replaced_words` 判定）。

### Windows向けに配布する

Windows版 Google日本語入力は UTF-8 でインポートに失敗することがあるため UTF-16LE(BOM) に変換して渡す（コマンドは README 参照）。`*_win.txt` は `.gitignore` 済み — コミットせず都度生成する。
