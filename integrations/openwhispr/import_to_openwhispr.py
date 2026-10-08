#!/usr/bin/env python3
"""Google日本語入力用の辞書から選んだ語を OpenWhispr の辞書に取り込む。

OpenWhispr の語彙(`custom_dictionary`)には読み・品詞の概念がなく、単語の
リストだけを持つ。この単語リストは次の2段階で効く:

- 録音時に STT プロンプトへヒントとして混ぜる(Whisper系は約550字しか読まない)
- 文字起こし後の cleanup プロンプト末尾に全件を渡す(上限なし)

そのため「どの語を入れるか」が重要で、投入する語は words.txt に1行1語で
明示する(行の並び順が初回投入時の優先度になる)。

投入は SQLite への直接書き込みではなく、アプリの公式ローカル HTTP API
(CLIブリッジ, ~/.openwhispr/cli-bridge.json) に対して行う。差分だけを
追加し、削除はしない(手で入れた語を消さないため)。

使い方:
    python3 integrations/openwhispr/import_to_openwhispr.py --dry-run   # 投入内容の確認のみ
    python3 integrations/openwhispr/import_to_openwhispr.py             # 実際に投入(要 OpenWhispr 起動)
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "integrations"))
from common.dict_entries import load_entries

WORDS_PATH = Path(__file__).resolve().parent / "words.txt"
BRIDGE_CONFIG_PATH = Path.home() / ".openwhispr" / "cli-bridge.json"

# Whisper系/ Groq の STT プロンプト上限。超えた分は届かない。
STT_PROMPT_CHAR_LIMIT = 890


def read_words_file(path):
    """投入する語を1行1語で読み込む。

    `#` 始まりの行と空行は無視する。大小文字を無視して重複を排除し、
    初出順を保つ。
    """
    words = []
    seen = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        word = line.strip()
        if not word or word.startswith("#"):
            continue
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        words.append(word)
    return words


def plan_additions(wanted, existing):
    """wanted のうち existing に無いものを、wanted の順で返す。"""
    have = {w.lower() for w in existing}
    return [w for w in wanted if w.lower() not in have]


def plan_existing(wanted, existing):
    """wanted のうち existing にすでに入っているものを、wanted の順で返す。"""
    have = {w.lower() for w in existing}
    return [w for w in wanted if w.lower() in have]


def find_unknown_words(wanted, known_words):
    """known_words に無い語を wanted の順で返す(警告用)。"""
    known = {w.lower() for w in known_words}
    return [w for w in wanted if w.lower() not in known]


class BridgeError(RuntimeError):
    """CLI ブリッジとのやり取りに失敗した。"""


class BridgeNotRunning(BridgeError):
    """OpenWhispr が起動していない、またはブリッジに接続できない。"""


# HTTP ステータスごとの対処法。利用者が次に何をすればいいかを示す。
HTTP_HINTS = {
    401: " (OpenWhispr を一度終了して起動し直し、~/.openwhispr/cli-bridge.json を読み直してください)",
    404: " (このバージョンの OpenWhispr に辞書APIがない可能性があります。アプリを更新してください)",
}


class DictionaryBridge:
    """OpenWhispr の CLI ブリッジ(ローカル HTTP API)経由で辞書を読み書きする。

    ポートとトークンは ~/.openwhispr/cli-bridge.json に書かれており、
    アプリが起動している間だけ存在する。
    """

    def __init__(self, base_url, token):
        self.base_url = base_url.rstrip("/")
        self.token = token

    @classmethod
    def from_config_file(cls, path):
        path = Path(path)
        if not path.exists():
            raise BridgeNotRunning(f"CLIブリッジの設定が見つかりません: {path}")
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
            port = int(config["port"])
            token = config["token"]
        except (OSError, ValueError, KeyError, TypeError) as e:
            # OSError は権限なし・ディレクトリを指している等。ValueError は
            # 不正な JSON と不正な UTF-8 の両方。
            raise BridgeError(f"CLIブリッジの設定を読めません: {path}: {e}")
        return cls(f"http://127.0.0.1:{port}", token)

    def _request(self, method, path, payload=None):
        headers = {"Authorization": f"Bearer {self.token}"}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                raw = res.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            hint = HTTP_HINTS.get(e.code, "")
            raise BridgeError(f"{method} {path} が {e.code} を返しました: {body}{hint}")
        except OSError as e:
            # URLError だけでなく、応答が返る前に切れた場合(urlopen 内の
            # getresponse が投げる RemoteDisconnected など)もここに来る。
            reason = getattr(e, "reason", e)
            raise BridgeNotRunning(
                f"OpenWhispr に接続できません ({self.base_url}): {reason}"
            )
        try:
            return json.loads(raw)
        except ValueError as e:
            raise BridgeError(f"{method} {path} の応答を読めません: {e}: {raw!r}")

    def list_words(self):
        """現在 OpenWhispr に入っている語の一覧を返す。"""
        data = self._request("GET", "/v1/dictionary/list")
        words = data.get("data") if isinstance(data, dict) else None
        if not isinstance(words, list) or not all(
            isinstance(w, str) for w in words
        ):
            raise BridgeError(f"辞書の一覧を読めません（応答の形式が想定と違います）: {data!r}")
        return words

    def add_words(self, words):
        """語を追加し、実際に追加された語数を返す(既存の語はスキップされる)。"""
        data = self._request("POST", "/v1/dictionary/update", {"add": list(words)})
        payload = data.get("data") if isinstance(data, dict) else None
        added = payload.get("added") if isinstance(payload, dict) else None
        if not isinstance(added, int) or isinstance(added, bool):
            raise BridgeError(f"投入の結果を読めません（応答の形式が想定と違います）: {data!r}")
        return added


def report_bridge_error(e):
    """ブリッジ由来の例外を説明し、終了コード 1 を返す。"""
    print(f"error: {e}")
    if isinstance(e, BridgeNotRunning):
        print("OpenWhispr を起動してから、もう一度実行してください。")
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="APIに書き込まず投入内容を表示する")
    parser.add_argument("--words", type=Path, default=WORDS_PATH,
                        help=f"投入する語のファイル (default: {WORDS_PATH})")
    parser.add_argument("--bridge-config", type=Path, default=BRIDGE_CONFIG_PATH,
                        help=f"cli-bridge.json のパス (default: {BRIDGE_CONFIG_PATH})")
    parser.add_argument("--dict-dir", type=Path, default=None,
                        help="照合に使う辞書ディレクトリ (default: リポジトリの dict/)")
    args = parser.parse_args(argv)

    if not args.words.exists():
        print(f"error: 語のファイルが見つかりません: {args.words}")
        return 1

    wanted = read_words_file(args.words)
    print(f"words.txt: {len(wanted)}語 ({len(', '.join(wanted))}字)")

    unknown = find_unknown_words(wanted, {w for _, w in load_entries(args.dict_dir)})
    if unknown:
        print(f"warning: dict/ の固有名詞に見つからない語 ({len(unknown)}件): "
              f"{', '.join(unknown)}")

    try:
        bridge = DictionaryBridge.from_config_file(args.bridge_config)
        existing = bridge.list_words()
    except BridgeError as e:
        return report_bridge_error(e)

    additions = plan_additions(wanted, existing)
    already = plan_existing(wanted, existing)
    # OpenWhispr は辞書「全体」を連結してから上限を適用するので、
    # 既存の語(手動追加・自動学習)も含めて数える。
    prompt_chars = len(", ".join(list(existing) + additions))
    print(f"OpenWhispr の辞書: {len(existing)}語 / 追加予定: {len(additions)}語 "
          f"/ words.txt の登録済み: {len(already)}語")
    print(f"STT ヒント: 投入後の合計 {prompt_chars}字 / 上限 {STT_PROMPT_CHAR_LIMIT}字")
    if prompt_chars > STT_PROMPT_CHAR_LIMIT:
        print(f"warning: 上限を {prompt_chars - STT_PROMPT_CHAR_LIMIT}字 超えた分は"
              f"音声認識に届きません（OpenWhispr が辞書を先頭から詰めるため）。"
              f"語を減らすか、優先度の低い語を words.txt の後ろに移してください。")

    if args.dry_run:
        for word in additions:
            print(f"  + {word}")
        for word in already:
            print(f"  = {word} (登録済み)")
        return 0

    if not additions:
        print("追加する語はありません。")
        return 0

    try:
        added = bridge.add_words(additions)
    except BridgeError as e:
        return report_bridge_error(e)
    print(f"投入完了: {added}件 追加 (辞書 合計 {len(existing) + added}語)")
    print("OpenWhispr の Settings > Dictionary で確認してください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
