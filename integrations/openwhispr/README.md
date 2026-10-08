# OpenWhispr（音声入力）への辞書取り込み

音声入力アプリ [OpenWhispr](https://www.openwhispr.com/) の辞書（Dictionary）に、このリポジトリの Google IME 辞書から選んだ語を取り込むためのスクリプトです。

## 仕組み

OpenWhispr の辞書（`~/Library/Application Support/open-whispr/transcriptions.db` の `custom_dictionary` テーブル）には IME 辞書のような「読み・品詞」の概念がなく、**単語のリストだけ**を持ちます。この単語リストは次の2段階で効きます。

- **STT ヒント**: 録音時に STT プロンプトへ `word, word, ...` として混ぜ、その語を書き起こしやすくする
- **cleanup（LLM）**: 文字起こし後の整形プロンプト末尾に `Custom Dictionary (use these exact spellings when they appear in the text): ...` として全件が渡され、表記が辞書どおりに直される

`import_to_openwhispr.py` は `words.txt`（1行1語）を読み、OpenWhispr にまだ入っていない語だけを**差分で追加**します。

投入先はアプリの公式ローカル HTTP API（CLI ブリッジ）です。SQLite を直接書き換える方法は、アプリ内のコメントで「次の起動で行が消え、クラウドにも届かない」として非推奨になっています。

### `snippets`（置換）は使わない

OpenWhispr には `snippets` という「トリガー → 置換先」の置換機能もありますが、展開に使われる正規表現が **Unicode の単語境界を必須**としています（`(?<=^|[\s\p{P}\p{S}])…(?=$|[\s\p{P}\p{S}])`）。かな・漢字は単語境界とみなされないため、日本語の文中に現れるカナトリガーはほぼ発火しません。

そのため Amical のような「読みをカタカナ化してトリガーにする」方式は採れず、`EXCLUDE_READINGS` に相当する誤爆対策も不要です。語は**単語リストとして入れる**のが正解です。

## 投入する語（`words.txt`）

固有名詞は全301語あり、そのままだと STT ヒントの上限を超えます。そこで `words.txt` に投入したい語だけを1行1語で列挙しています（初期値は85語・834字）。

- 行頭 `#` はコメント。空行とコメント行は無視されます
- **行の並び順が初回投入時の優先度**になります（`add` の順 = 挿入順 = STT ヒントの並び）
- `dict/` の固有名詞に無い語を書いた場合は警告が出ます（タイポ検出用。投入自体は行われます）

## 使い方

```bash
# リポジトリ直下で実行

# 1. 投入内容の確認（APIには書き込まない）
python3 integrations/openwhispr/import_to_openwhispr.py --dry-run

# 2. 実行（OpenWhispr を起動した状態で）
python3 integrations/openwhispr/import_to_openwhispr.py
```

**Amical とは逆に、OpenWhispr は起動している必要があります**（CLI ブリッジのポートとトークンが `~/.openwhispr/cli-bridge.json` に書かれるため）。起動していない場合はその旨のエラーで終了します。

登録済みの語はスキップされるので、**`words.txt` に語を足したら再実行すれば差分だけ追加されます**。dry-run は `words.txt` の語数と STT ヒントの文字数を表示するので、上限（下記）に収まっているか確認できます。

投入後に OpenWhispr の Settings > Dictionary で反映を確認してください。

### STT ヒントの文字数上限

単語リストはプロバイダごとの上限で切られ、超えた分は音声認識には効きません（cleanup プロンプトには全件が届くため、そちらでは効きます）。

| プロバイダ | 上限 |
| --- | --- |
| Groq | 890字 |
| Whisper 系（`whisper-large-v3` など） | 900字（デコーダが実際に読むのは約550字） |
| `gpt-4o-transcribe` 系 | 8,000字 |

Whisper 系はプロンプトを後方から切るため、`words.txt` の**後半ほど STT に効きやすい**という逆転が起きます。実際に音声で試して、誤変換が残るようなら並び順を入れ替えてください。

## メンテナンス

- **語を足す**: `dict/` の該当ファイルに追記したうえで、`words.txt` にも1行足す（`dict/` の語が自動で入るわけではありません。STT 枠に収めるため意図的に絞っています）
- **語を減らす**: スクリプトは削除を行いません。OpenWhispr の Settings > Dictionary から該当語を削除し、`words.txt` からも消す
- **並び順を変える**: 並び順は初回投入時に決まります。変えたい語は Settings > Dictionary で削除してから再実行してください
- **誤変換が出たら**: その語を `words.txt` から消し、Settings > Dictionary でも削除する。単語リストはあくまでヒントなので、Amical の部分文字列置換ほどの誤爆は起きませんが、辞書にある語に引っ張られて表記が変わることがあります
- **クラウド同期**: 追加した語は `sync_status='pending'` として OpenWhispr アカウントへ同期されます（Amical は完全ローカル）。同期されたくない語は入れないでください
