# OpenWhispr 連携 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `dict/` の固有名詞から選んだ語を OpenWhispr の辞書へ投入するスクリプトを追加し、Amical / OpenWhispr の取り込みスクリプトを `integrations/` にまとめる。

**Architecture:** `integrations/common/dict_entries.py` が `dict/` の読み込み（3列・固有名詞のみという不変条件）を一手に引き、`integrations/amical/` と `integrations/openwhispr/` がそれを使う。OpenWhispr 側は SQLite を直接書かず、アプリの公式ローカル HTTP API（CLI ブリッジ）に対して `words.txt` と現在の辞書の**差分だけを追加**する。

**Tech Stack:** Python 3.9.6（`/usr/bin/python3`）の標準ライブラリのみ。テストは stdlib の `unittest`。追加依存なし。

**Spec:** `docs/superpowers/specs/2026-10-09-openwhispr-integration-design.md`

## Global Constraints

- Python 3.9.6（`/usr/bin/python3`）で動くこと
- **標準ライブラリのみ**。依存パッケージを追加しない
- 3.10 以降の構文を使わない（`list[str]`、`X | None`、`match`）。既存の `import_to_amical.py` と同じく型注釈は書かず docstring で示す
- `dict/` の不変条件を壊さない: UTF-8 / タブ区切り / `読み(ひらがな)\t単語\t品詞` の3列固定
- テストはリポジトリ直下で `python3 -m unittest discover -s tests -v` が通ること
- コミットメッセージの末尾に `Co-Authored-By: Claude Code <noreply@anthropic.com>`

## Review Focus

スペックが明示していないが、使う人に最も影響が出やすい入力・状態。各項目のテストは、そのコードを持つタスクに置く。

1. `words.txt` が空、またはコメントだけ → 追加0件で正常終了し、クラッシュしないこと（Task 5）
2. ブリッジ設定が無い / JSON が壊れている / 接続できない → 何をすべきかを示すエラーで終了すること（Task 4・5）
3. 大小文字違いの重複（`Kubernetes` と `kubernetes`）→ 二重登録せず既存扱いにすること（Task 3・4）
4. `words.txt` の語が `dict/` の固有名詞に無い → 警告したうえで投入すること（Task 5）
5. `words.txt` の合計が890字を超える → 警告を出すこと（Task 5）

---

### Task 1: `integrations/` への移動

**Files:**
- Move: `amical/` → `integrations/amical/`
- Delete: 空の `openwhispr/`（リポジトリ直下）
- Modify: `integrations/amical/import_to_amical.py:26`（基準ディレクトリの取り方）
- Modify: `integrations/amical/README.md`、`README.md`、`CLAUDE.md`（パス表記）

**Interfaces:**
- Consumes: なし
- Produces: 以降のタスクが前提とするパス `integrations/{common,amical,openwhispr}/`。`integrations/amical/import_to_amical.py` は移動後も `--dry-run` が同一出力であること

- [ ] **Step 1: 移動前のベースラインを取る**

```bash
cd /Users/kojima/dev/projects/google-ime-dict
python3 amical/import_to_amical.py --dry-run > /tmp/amical_before.txt 2>&1
wc -l /tmp/amical_before.txt
```

Expected: `304 /tmp/amical_before.txt`、1行目が `固有名詞: 301語 → 置換 250件 / ヒント 49件`

- [ ] **Step 2: 移動する**

```bash
mkdir -p integrations
git mv amical integrations/amical
rmdir openwhispr
```

- [ ] **Step 3: `DICT_DIR` の基準ディレクトリを直す**

`integrations/amical/import_to_amical.py:26` は現在 `REPO_DIR = Path(__file__).resolve().parent.parent`。移動後はこれが `integrations/` を指してしまうので `parents[2]` に変える。

```python
REPO_DIR = Path(__file__).resolve().parents[2]
```

- [ ] **Step 4: 移動後も同一出力であることを確認する**

```bash
python3 integrations/amical/import_to_amical.py --dry-run > /tmp/amical_after.txt 2>&1
diff /tmp/amical_before.txt /tmp/amical_after.txt && echo "IDENTICAL"
```

Expected: `IDENTICAL`

- [ ] **Step 5: ドキュメントのパス表記を更新する**

`grep -rn "amical/import_to_amical\|amical/README" README.md CLAUDE.md integrations/amical/README.md` で洗い出し、`integrations/amical/...` に直す（README.md 3箇所、CLAUDE.md 4箇所、integrations/amical/README.md 2箇所）。

```bash
grep -rn "amical/import_to_amical\|amical/README" --exclude-dir=.git --exclude-dir=docs .
```

Expected: `integrations/amical/...` を含む行だけが残る

- [ ] **Step 6: コミット**

```bash
git add -A
git commit -m "$(cat <<'EOF'
取り込みスクリプトを integrations/ 配下に移動

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 共通モジュール `dict_entries.py` の抽出

**Files:**
- Create: `integrations/common/dict_entries.py`
- Create: `tests/test_dict_entries.py`
- Modify: `integrations/amical/import_to_amical.py`（自前の `load_entries` を削除し、共通モジュールから import）

**Interfaces:**
- Consumes: なし
- Produces: `load_entries(dict_dir=None) -> list[tuple[str, str]]`（`integrations/common/dict_entries.py`）。戻り値は `(読み, 単語)` のリストで、品詞が `固有名詞` の行のみ。ファイル順（パスのソート順）→行順を保持。`(読み, 単語)` の重複は最初の1件だけ。`dict_dir` を省略すると `Path(__file__).resolve().parents[2] / "dict"`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_dict_entries.py`。一時ディレクトリに辞書ファイルを作って検証する（実物の `dict/` に依存させない）。

```python
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))

from common.dict_entries import load_entries


class LoadEntriesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, relpath, body):
        path = self.dir / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_reads_only_proper_nouns(self):
        self.write("一般/a_terms.txt", "かいしゃ\t会社\t名詞\nあんすろぴっく\tAnthropic\t固有名詞\n")
        self.assertEqual(load_entries(self.dir), [("あんすろぴっく", "Anthropic")])

    def test_skips_lines_without_three_columns(self):
        self.write("a_terms.txt", "くばねてす\tKubernetes\nあんすろぴっく\tAnthropic\t固有名詞\n")
        self.assertEqual(load_entries(self.dir), [("あんすろぴっく", "Anthropic")])

    def test_ignores_comments_and_blank_lines(self):
        self.write("a_terms.txt", "# ===== 企業 =====\n\nあんすろぴっく\tAnthropic\t固有名詞\n")
        self.assertEqual(load_entries(self.dir), [("あんすろぴっく", "Anthropic")])

    def test_dedupes_same_reading_and_word_pair(self):
        self.write("a_terms.txt", "くばねてす\tKubernetes\t固有名詞\nくばねてす\tKubernetes\t固有名詞\n")
        self.assertEqual(load_entries(self.dir), [("くばねてす", "Kubernetes")])

    def test_keeps_same_word_with_different_readings(self):
        self.write("a_terms.txt", "くばねてす\tKubernetes\t固有名詞\nくーばねてす\tKubernetes\t固有名詞\n")
        self.assertEqual(
            load_entries(self.dir),
            [("くばねてす", "Kubernetes"), ("くーばねてす", "Kubernetes")],
        )

    def test_ignores_files_not_named_terms(self):
        self.write("notes.txt", "あんすろぴっく\tAnthropic\t固有名詞\n")
        self.assertEqual(load_entries(self.dir), [])

    def test_reads_subdirectories_in_sorted_path_order(self):
        self.write("技術/b_terms.txt", "びー\tB\t固有名詞\n")
        self.write("技術/a_terms.txt", "えー\tA\t固有名詞\n")
        self.assertEqual(load_entries(self.dir), [("えー", "A"), ("びー", "B")])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'common'`

- [ ] **Step 3: `integrations/common/dict_entries.py` を実装する**

`integrations/amical/import_to_amical.py` の既存 `load_entries()` のロジックをそのまま移す（挙動を変えない）。署名と固定値:

```python
DICT_DIR = Path(__file__).resolve().parents[2] / "dict"

def load_entries(dict_dir=None):
    """dict/ 配下の *_terms.txt から固有名詞の (読み, 単語) を読み込む。"""
```

- 対象は `sorted(base.rglob("*_terms.txt"))`
- `#` 始まりと空行はスキップ
- `line.split("\t")` が3要素でなければ `print(f"warning: 列数が3でない行をスキップ: {txt.relative_to(base)}: {line!r}")` してスキップ（既存と同じ文言）
- `pos != "固有名詞"` はスキップ
- `(reading, word)` の重複はスキップ
- `base = Path(dict_dir) if dict_dir else DICT_DIR`

- [ ] **Step 4: テストが通ることを確認する**

Run: `python3 -m unittest discover -s tests -v`
Expected: `OK`（7 tests）

- [ ] **Step 5: Amical スクリプトを共通モジュールに載せる**

`integrations/amical/import_to_amical.py` から自前の `load_entries()` を削除し、先頭で共通モジュールを import する。

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.dict_entries import load_entries
```

`main()` の `entries = load_entries()` はそのまま（`dict_dir` 省略で `dict/` を読む）。

- [ ] **Step 6: Amical の出力が変わっていないことを確認する**

```bash
python3 integrations/amical/import_to_amical.py --dry-run > /tmp/amical_after2.txt 2>&1
diff /tmp/amical_before.txt /tmp/amical_after2.txt && echo "IDENTICAL"
```

Expected: `IDENTICAL`

- [ ] **Step 7: コミット**

```bash
git add -A
git commit -m "$(cat <<'EOF'
dict/ の読み込みを integrations/common に共通化

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `words.txt` の読み込みと差分計算

**Files:**
- Create: `integrations/openwhispr/import_to_openwhispr.py`
- Create: `tests/test_import_to_openwhispr.py`

**Interfaces:**
- Consumes: `common.dict_entries.load_entries(dict_dir=None)`（Task 2）
- Produces: このファイルに置く純粋関数
  - `read_words_file(path) -> list[str]` — 1行1語。`#` 始まりと空行は無視。大小文字を無視して重複排除し、初出順を保つ
  - `plan_additions(wanted, existing) -> list[str]` — `wanted` のうち `existing` に無いものを `wanted` の順で返す（大小文字を無視して比較）
  - `find_unknown_words(wanted, known_words) -> list[str]` — `known_words` に無い語を `wanted` の順で返す（大小文字を無視）
  - モジュール定数 `WORDS_PATH`（`integrations/openwhispr/words.txt`）、`BRIDGE_CONFIG_PATH`（`Path.home() / ".openwhispr" / "cli-bridge.json"`）、`STT_PROMPT_CHAR_LIMIT = 890`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_import_to_openwhispr.py` の先頭に、以降のタスクでも使うimportの下ごしらえを置く。

```python
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations" / "openwhispr"))

import import_to_openwhispr as ow


class ReadWordsFileTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "words.txt"

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, body):
        self.path.write_text(body, encoding="utf-8")

    def test_returns_lines_in_file_order(self):
        self.write("Terraform\nAnthropic\n")
        self.assertEqual(ow.read_words_file(self.path), ["Terraform", "Anthropic"])

    def test_ignores_comments_and_blank_lines(self):
        self.write("# ===== AI =====\n\nAnthropic\n  \n")
        self.assertEqual(ow.read_words_file(self.path), ["Anthropic"])

    def test_strips_surrounding_whitespace(self):
        self.write("  Anthropic  \n")
        self.assertEqual(ow.read_words_file(self.path), ["Anthropic"])

    def test_dedupes_case_insensitively_keeping_first(self):
        self.write("Kubernetes\nkubernetes\nKUBERNETES\n")
        self.assertEqual(ow.read_words_file(self.path), ["Kubernetes"])

    def test_empty_file_returns_empty_list(self):
        self.write("")
        self.assertEqual(ow.read_words_file(self.path), [])


class PlanAdditionsTest(unittest.TestCase):
    def test_returns_only_missing_words_in_wanted_order(self):
        self.assertEqual(
            ow.plan_additions(["A", "B", "C"], ["C"]),
            ["A", "B"],
        )

    def test_ignores_case_when_comparing(self):
        self.assertEqual(ow.plan_additions(["Kubernetes"], ["kubernetes"]), [])

    def test_existing_empty_returns_all(self):
        self.assertEqual(ow.plan_additions(["A", "B"], []), ["A", "B"])


class FindUnknownWordsTest(unittest.TestCase):
    def test_returns_words_absent_from_known(self):
        self.assertEqual(ow.find_unknown_words(["A", "B"], {"B"}), ["A"])

    def test_ignores_case(self):
        self.assertEqual(ow.find_unknown_words(["kubernetes"], {"Kubernetes"}), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'import_to_openwhispr'`

- [ ] **Step 3: `integrations/openwhispr/import_to_openwhispr.py` を実装する**

先頭は既存スクリプトと同じ体裁（`#!/usr/bin/env python3` と docstring、`argparse` は Task 5 で追加）。共通モジュールの import はパスを通してから行う。

```python
REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "integrations"))
from common.dict_entries import load_entries

WORDS_PATH = Path(__file__).resolve().parent / "words.txt"
BRIDGE_CONFIG_PATH = Path.home() / ".openwhispr" / "cli-bridge.json"
STT_PROMPT_CHAR_LIMIT = 890
```

`read_words_file` / `plan_additions` / `find_unknown_words` を実装する。3つとも `w.lower()` で比較する。

- [ ] **Step 4: テストが通ることを確認する**

Run: `python3 -m unittest discover -s tests -v`
Expected: `OK`（17 tests）

- [ ] **Step 5: コミット**

```bash
git add -A
git commit -m "$(cat <<'EOF'
OpenWhispr用の語リスト読み込みと差分計算を追加

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: CLI ブリッジのクライアント

**Files:**
- Modify: `integrations/openwhispr/import_to_openwhispr.py`
- Modify: `tests/test_import_to_openwhispr.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `class BridgeError(RuntimeError)` — ブリッジとのやり取りに失敗した
  - `class BridgeNotRunning(BridgeError)` — 設定が無い / 接続できない
  - `class DictionaryBridge` — `__init__(self, base_url, token)`、`from_config_file(cls, path)`（クラスメソッド。設定は `{version, port, token}` の JSON）、`list_words(self) -> list[str]`、`add_words(self, words) -> int`（実際に追加された語数を返す）
  - 接続先は `http://127.0.0.1:<port>`。`Authorization: Bearer <token>` を付ける

- [ ] **Step 1: 失敗するテストを書く**

標準ライブラリの `http.server` をスレッドで立て、リクエストを記録するスタブをテストファイルに置く。以降のタスクでも使う。

```python
import http.server
import json
import threading


class StubBridge:
    """CLI ブリッジの代わり。受けたリクエストを記録して固定の応答を返す。"""

    def __init__(self, words=None):
        self.words = list(words or [])
        self.requests = []  # (method, path, body)
        self.auth_headers = []
        stub = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _record(self, method, body):
                stub.requests.append((method, self.path, body))
                stub.auth_headers.append(self.headers.get("Authorization"))

            def do_GET(self):
                self._record("GET", None)
                self._send({"data": list(stub.words), "has_more": False, "next_cursor": None})

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                self._record("POST", body)
                added = 0
                for word in body.get("add", []):
                    if word.lower() not in {w.lower() for w in stub.words}:
                        stub.words.append(word)
                        added += 1
                self._send({"data": {"words": list(stub.words), "added": added, "removed": 0}})

            def _send(self, payload):
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def config_file(self, directory, token="test-token"):
        path = Path(directory) / "cli-bridge.json"
        path.write_text(
            json.dumps({"version": 1, "port": self.port, "token": token}),
            encoding="utf-8",
        )
        return path
```

テスト本体:

```python
class DictionaryBridgeTest(unittest.TestCase):
    def setUp(self):
        self.stub = StubBridge(["OpenWhispr"])
        self.addCleanup(self.stub.stop)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def bridge(self):
        path = self.stub.config_file(self._tmp.name)
        return ow.DictionaryBridge.from_config_file(path)

    def test_from_config_file_missing_file_raises_not_running(self):
        with self.assertRaises(ow.BridgeNotRunning):
            ow.DictionaryBridge.from_config_file(Path(self._tmp.name) / "nope.json")

    def test_from_config_file_broken_json_raises_bridge_error(self):
        path = Path(self._tmp.name) / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ow.BridgeError):
            ow.DictionaryBridge.from_config_file(path)

    def test_from_config_file_missing_keys_raises_bridge_error(self):
        path = Path(self._tmp.name) / "keys.json"
        path.write_text(json.dumps({"version": 1}), encoding="utf-8")
        with self.assertRaises(ow.BridgeError):
            ow.DictionaryBridge.from_config_file(path)

    def test_list_words_returns_current_dictionary(self):
        self.assertEqual(self.bridge().list_words(), ["OpenWhispr"])

    def test_list_words_sends_bearer_token(self):
        self.bridge().list_words()
        self.assertEqual(self.stub.auth_headers, ["Bearer test-token"])

    def test_add_words_posts_add_and_returns_added_count(self):
        worker = self.bridge()
        self.assertEqual(worker.add_words(["Anthropic", "Terraform"]), 2)
        self.assertIn(
            ("POST", "/v1/dictionary/update", {"add": ["Anthropic", "Terraform"]}),
            self.stub.requests,
        )

    def test_add_words_skips_words_already_present_case_insensitively(self):
        worker = self.bridge()
        self.assertEqual(worker.add_words(["openwhispr", "Anthropic"]), 1)

    def test_connection_refused_raises_not_running(self):
        dead = ow.DictionaryBridge("http://127.0.0.1:1", "test-token")
        with self.assertRaises(ow.BridgeNotRunning):
            dead.list_words()
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `AttributeError: module 'import_to_openwhispr' has no attribute 'DictionaryBridge'`

- [ ] **Step 3: `DictionaryBridge` を実装する**

`urllib.request` / `urllib.error` / `json` を使う（`requests` は使わない）。

- `from_config_file`: ファイルが無ければ `BridgeNotRunning(f"CLIブリッジの設定が見つかりません: {path}")`。`json.loads` の失敗・`port`/`token` の欠落は `BridgeError(f"CLIブリッジの設定を読めません: {path}: {e}")`
- 共通の送信処理: `urllib.request.Request(url, data=..., headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method=...)`、タイムアウト10秒
- `urllib.error.HTTPError` → `BridgeError(f"{method} {path} が {e.code} を返しました: {body}")`
- `urllib.error.URLError` → `BridgeNotRunning(f"OpenWhispr に接続できません ({base_url}): {e.reason}")`
- `list_words` は応答の `["data"]` を返す。`add_words` は `["data"]["added"]` を返す

- [ ] **Step 4: テストが通ることを確認する**

Run: `python3 -m unittest discover -s tests -v`
Expected: `OK`（25 tests）

- [ ] **Step 5: コミット**

```bash
git add -A
git commit -m "$(cat <<'EOF'
OpenWhisprのCLIブリッジクライアントを追加

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: CLI エントリ（`--dry-run` と本実行）

**Files:**
- Modify: `integrations/openwhispr/import_to_openwhispr.py`
- Modify: `tests/test_import_to_openwhispr.py`

**Interfaces:**
- Consumes: `common.dict_entries.load_entries`（Task 2）、`read_words_file` / `plan_additions` / `find_unknown_words` / `STT_PROMPT_CHAR_LIMIT`（Task 3）、`DictionaryBridge` / `BridgeError` / `BridgeNotRunning`（Task 4）
- Produces: `main(argv=None) -> int`（終了コードを返す。`0` 成功、`1` エラー）。`if __name__ == "__main__": sys.exit(main())`

オプション:

| オプション | 既定値 |
| --- | --- |
| `--dry-run` | なし（フラグ） |
| `--words PATH` | `WORDS_PATH` |
| `--bridge-config PATH` | `BRIDGE_CONFIG_PATH` |
| `--dict-dir PATH` | `None`（`common.dict_entries.DICT_DIR` = `dict/`） |

- [ ] **Step 1: 失敗するテストを書く**

`main()` をスタブサーバに対して丸ごと動かす。`--dict-dir` と `--words` は一時ディレクトリに向ける。

```python
class MainTest(unittest.TestCase):
    def setUp(self):
        self.stub = StubBridge(["OpenWhispr"])
        self.addCleanup(self.stub.stop)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.config = self.stub.config_file(self.dir)
        self.dict_dir = self.dir / "dict"
        self.dict_dir.mkdir()
        (self.dict_dir / "a_terms.txt").write_text(
            "あんすろぴっく\tAnthropic\t固有名詞\nてらふぉーむ\tTerraform\t固有名詞\n",
            encoding="utf-8",
        )
        self.words = self.dir / "words.txt"

    def write_words(self, body):
        self.words.write_text(body, encoding="utf-8")

    def run_main(self, *extra):
        argv = [
            "--words", str(self.words),
            "--bridge-config", str(self.config),
            "--dict-dir", str(self.dict_dir),
        ] + list(extra)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = ow.main(argv)
        return code, out.getvalue()

    def posted_adds(self):
        return [r[2]["add"] for r in self.stub.requests if r[0] == "POST"]

    def test_dry_run_prints_additions_without_posting(self):
        self.write_words("Anthropic\nTerraform\n")
        code, out = self.run_main("--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(self.posted_adds(), [])
        self.assertIn("+ Anthropic", out)
        self.assertIn("+ Terraform", out)

    def test_posts_only_the_diff(self):
        self.write_words("Anthropic\nTerraform\n")
        self.stub.words.append("Anthropic")
        code, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(self.posted_adds(), [["Terraform"]])

    def test_second_run_posts_nothing(self):
        self.write_words("Anthropic\nTerraform\n")
        self.assertEqual(self.run_main()[0], 0)
        self.assertEqual(self.run_main()[0], 0)
        self.assertEqual(self.posted_adds(), [["Anthropic", "Terraform"]])

    def test_empty_words_file_exits_zero_and_posts_nothing(self):
        self.write_words("")
        code, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(self.posted_adds(), [])

    def test_comments_only_words_file_exits_zero(self):
        self.write_words("# まだ何も無い\n")
        self.assertEqual(self.run_main()[0], 0)

    def test_missing_bridge_config_exits_nonzero_with_hint(self):
        self.config.unlink()
        self.write_words("Anthropic\n")
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("OpenWhispr を起動", out)

    def test_warns_about_words_missing_from_dict_dir_but_still_adds_them(self):
        self.write_words("Anthropic\nNope\n")
        code, out = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("Nope", out)
        self.assertEqual(self.posted_adds(), [["Anthropic", "Nope"]])

    def test_warns_when_prompt_exceeds_char_limit(self):
        long_word = "X" * 900
        (self.dict_dir / "b_terms.txt").write_text(
            "えっくす\t%s\t固有名詞\n" % long_word, encoding="utf-8"
        )
        self.write_words(long_word + "\n")
        code, out = self.run_main("--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("warning", out)
```

`contextlib` と `io` をテストファイルの import に足すこと。

- [ ] **Step 2: テストが失敗することを確認する**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL — `AttributeError: module 'import_to_openwhispr' has no attribute 'main'`

- [ ] **Step 3: `main()` を実装する**

固定する出力（`--dry-run`）:

```
words.txt: 2語 (STT ヒント用 19字 / 上限 890字)
OpenWhispr の辞書: 1語 / 追加予定: 1語
  + Terraform
```

固定する出力（本実行）:

```
words.txt: 2語 (STT ヒント用 19字 / 上限 890字)
OpenWhispr の辞書: 1語 / 追加予定: 1語
投入完了: 1件 追加 (辞書 合計 2語)
OpenWhispr の Settings > Dictionary で確認してください。
```

- `words.txt` が無い → `error: 語のファイルが見つかりません: {path}` で `return 1`
- 890字を超えたら `warning: STT ヒントの上限を {n}字 超えています（Whisper系では後半のみ届きます）` を出す（処理は続ける）
- `dict/` に無い語があれば `warning: dict/ の固有名詞に見つからない語 ({n}件): {カンマ区切り}` を出したうえで**投入はする**
- `BridgeNotRunning` → `error: {e}` と `OpenWhispr を起動してから、もう一度実行してください。` を出して `return 1`
- `BridgeError` → `error: {e}` を出して `return 1`
- 追加が0件なら `追加する語はありません。` を出して `return 0`（POST しない）
- `--dry-run` では `  + {word}` を追加予定の語だけ並べる

- [ ] **Step 4: テストが通ることを確認する**

Run: `python3 -m unittest discover -s tests -v`
Expected: `OK`（33 tests）

- [ ] **Step 5: 実際の OpenWhispr を止めた状態で案内が出ることを目視する**

```bash
python3 integrations/openwhispr/import_to_openwhispr.py --dry-run --words /dev/null
```

Expected: `words.txt: 0語 …` の行のあと、ブリッジに繋がれば `追加する語はありません。`、
繋がらなければ `OpenWhispr を起動してから、もう一度実行してください。`（どちらでも異常ではない）

- [ ] **Step 6: コミット**

```bash
git add -A
git commit -m "$(cat <<'EOF'
OpenWhispr取り込みのCLIエントリを追加

dry-runでは投入内容だけを表示し、本実行では現在の辞書との差分のみを
CLIブリッジ経由で追加する(削除はしない)。

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `words.txt` の初期語と `integrations/openwhispr/README.md`

**Files:**
- Create: `integrations/openwhispr/words.txt`
- Create: `integrations/openwhispr/README.md`

**Interfaces:**
- Consumes: `read_words_file`（Task 3）
- Produces: `integrations/openwhispr/words.txt` — 85語、834字（`, ` 区切り換算）、890字上限内

- [ ] **Step 1: `words.txt` を書く**

1行1語。行頭 `#` はコメント。**並び順は初回投入時の優先度**になる。以下の85語をこの順で書く（`#` グループ見出し付き）。

```
# ===== AI企業・モデル =====
Anthropic
OpenAI
Google DeepMind
Mistral AI
xAI
NVIDIA
Hugging Face
ElevenLabs
Groq
Sakana AI
ChatGPT
Claude
Claude Code
Claude Desktop
Gemini
Llama
DeepSeek
Qwen
Whisper
NotebookLM
# ===== AI開発ツール =====
Cursor
Windsurf
Cline
Codex
GitHub Copilot
Devin
Aider
OpenCode
OpenHands
LangChain
LangGraph
LlamaIndex
Ollama
OpenRouter
Dify
Pinecone
Weaviate
Qdrant
PyTorch
Jupyter Notebook
# ===== クラウド基盤・サービス =====
AWS
Google Cloud
Azure
Cloudflare
Vercel
Netlify
DigitalOcean
EC2
S3
Lambda
Fargate
EKS
RDS
DynamoDB
CloudFront
BigQuery
Cloud Run
GKE
Firebase
Supabase
Snowflake
Databricks
# ===== 開発ツール・SaaS =====
Kubernetes
Docker
Docker Compose
Helm
Terraform
Ansible
Prometheus
Grafana
Elasticsearch
OpenTelemetry
nginx
Traefik
GitHub
GitHub Actions
GitLab
Jenkins
TypeScript
Next.js
Tailwind CSS
Vite
Playwright
Datadog
Sentry
```

- [ ] **Step 2: 語数・字数・辞書との整合を確認する**

リポジトリ直下で実行する。

```bash
python3 -I -c "
import sys
from pathlib import Path
sys.path.insert(0, 'integrations')
sys.path.insert(0, 'integrations/openwhispr')
import import_to_openwhispr as ow
from common.dict_entries import load_entries

words = ow.read_words_file(Path('integrations/openwhispr/words.txt'))
known = {w for _, w in load_entries()}
print('語数:', len(words))
print('STTヒント字数:', len(', '.join(words)))
print('dict/ に無い語:', ow.find_unknown_words(words, known))
"
```

Expected:
```
語数: 85
STTヒント字数: 834
dict/ に無い語: []
```

- [ ] **Step 3: `integrations/openwhispr/README.md` を書く**

`integrations/amical/README.md` と同じ構成・同じ調子で書く。必ず含める内容:

- 仕組み: `custom_dictionary` は**単語リストのみ**（読み・品詞なし）で、(1) 録音時の STT プロンプトへのヒント、(2) 認識後の cleanup プロンプト末尾への全件注入、の2段階で効く
- **`snippets`（置換）は使わない**: 展開が Unicode 単語境界必須（`(?<=^|[\s\p{P}\p{S}])`）で、かな・漢字は境界にならないため日本語文中のカナトリガーが発火しない。よって Amical のような誤爆対策（`EXCLUDE_READINGS`）も不要
- 使い方: `python3 integrations/openwhispr/import_to_openwhispr.py --dry-run` / `python3 integrations/openwhispr/import_to_openwhispr.py`。**Amical と逆に OpenWhispr は起動している必要がある**
- 追加のみで削除はしない（手で入れた語を消さないため）。減らすときは Settings > Dictionary から
- 投入した語は OpenWhispr アカウントへクラウド同期される（Amical は完全ローカル）
- STT ヒントの上限: Whisper 系は890字（デコーダが読むのは約550字）、Groq は890字、`gpt-4o-transcribe` 系は8,000字。`--dry-run` が字数を表示する
- メンテナンス: 語を足す手順、並び順は初回投入時に決まる（変えるには Settings > Dictionary で削除してから再実行）、誤変換が出たら該当語を `words.txt` から消して UI でも削除する
- DB を直接書き換えない理由（アプリ内コメント #1295 の要約）

- [ ] **Step 4: コミット**

```bash
git add -A
git commit -m "$(cat <<'EOF'
OpenWhisprに投入する語リストと説明を追加

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: ルート README.md / CLAUDE.md の更新

**Files:**
- Modify: `README.md`（Amical 節の下に OpenWhispr 節を追加、辞書一覧の語数を実測値に修正）
- Modify: `CLAUDE.md`（概要・よくある作業に OpenWhispr を追記）

**Interfaces:**
- Consumes: なし
- Produces: なし（ドキュメントのみ）

- [ ] **Step 1: 辞書一覧の語数を実測値に直す**

`README.md` の表の語数は `dict/技術/ai_terms.txt` の値が古い。実測は次のとおり（行数 / うち固有名詞）。

| ファイル | 行数 | 固有名詞 |
| --- | --- | --- |
| `dict/技術/ai_terms.txt` | 290 | 143 |
| `dict/技術/dev_terms.txt` | 92 | 38 |
| `dict/技術/web_terms.txt` | 113 | 46 |
| `dict/技術/cloud_terms.txt` | 87 | 74 |
| `dict/一般/general_terms.txt` | 158 | 0 |
| `dict/一般/business_it_terms.txt` | 107 | 0 |

```bash
python3 -I -c "
import pathlib
for p in sorted(pathlib.Path('dict').rglob('*_terms.txt')):
    rows=[l.split('\t') for l in p.read_text(encoding='utf-8').splitlines() if l and not l.startswith('#')]
    noun=sum(1 for r in rows if len(r)==3 and r[2]=='固有名詞')
    print(p, len(rows), noun)
"
```

Expected: 上の表と同じ数値が出る。出た値を README の表に反映する

- [ ] **Step 2: README.md に OpenWhispr 節を追加する**

`## Amical（音声入力）への取り込み` の直後に、同じ粒度で `## OpenWhispr（音声入力）への取り込み` を追加する。コマンド2行と `integrations/openwhispr/README.md` へのリンク、および「Amical と逆に OpenWhispr を起動した状態で実行する」ことを明記。`dict/` の語を増やしたときは `words.txt` に足す必要がある、という一文も入れる。

- [ ] **Step 3: CLAUDE.md を更新する**

- 概要の「唯一のコードは…」を、`integrations/` 配下の3つ（`common/dict_entries.py`、`amical/import_to_amical.py`、`openwhispr/import_to_openwhispr.py`）を指すよう書き換える。テストは `python3 -m unittest discover -s tests -v` で走ることも書く
- 「よくある作業」に「Amical へ取り込む」と並べて「OpenWhispr へ取り込む」を追加（コマンド、起動が必要なこと、差分のみ追加されること）
- 「誤爆する置換を直す」節は Amical 固有なので、見出しに Amical と付ける

- [ ] **Step 4: 記載したコマンドが実在すること確認する**

```bash
python3 integrations/openwhispr/import_to_openwhispr.py --help
python3 -m unittest discover -s tests -v 2>&1 | tail -3
```

Expected: `--help` が `--dry-run` / `--words` / `--bridge-config` / `--dict-dir` を表示し、unittest が `OK`

- [ ] **Step 5: コミット**

```bash
git add -A
git commit -m "$(cat <<'EOF'
OpenWhispr取り込みの手順をREADMEとCLAUDE.mdに追記

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: 実機での動作確認（手動・ユーザーが実行）

**Files:**
- なし（確認のみ）

**Interfaces:**
- Consumes: ここまでのすべて
- Produces: 受け入れ基準の確認結果

このタスクは OpenWhispr の実データとクラウドに書き込むため、**実行するかどうかはユーザーが決める**。自動では実行しない。

- [ ] **Step 1: OpenWhispr を起動しておく**

- [ ] **Step 2: dry-run で投入内容を確認する**

```bash
python3 integrations/openwhispr/import_to_openwhispr.py --dry-run
```

Expected: `words.txt: 85語 (STT ヒント用 834字 / 上限 890字)`、`追加予定: 85語`（既に投入済みならその分減る）

- [ ] **Step 3: 本実行する**

```bash
python3 integrations/openwhispr/import_to_openwhispr.py
```

Expected: `投入完了: 85件 追加 (辞書 合計 86語)`（既存の `OpenWhispr` を含む）

- [ ] **Step 4: アプリ側で確認する**

Settings > Dictionary に85語が並んでいること。`python3 -I -c` で `GET /v1/dictionary/list` を叩いて件数が一致すること。

- [ ] **Step 5: 冪等性を確認する**

もう一度 Step 3 を実行し、`追加する語はありません。` と出て何も追加されないこと。

- [ ] **Step 6: 音声で実際に試す**

「クバネテス」「テラフォーム」「アンスロピック」などを音声入力し、`Kubernetes` / `Terraform` / `Anthropic` になるか確認する。ならない語があれば `words.txt` の並び順（Whisper 系はプロンプトの後半のみ届く）を入れ替えて、Settings > Dictionary から該当語を削除してから再実行する。
