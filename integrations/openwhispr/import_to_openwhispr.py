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

import sys
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


def find_unknown_words(wanted, known_words):
    """known_words に無い語を wanted の順で返す(警告用)。"""
    known = {w.lower() for w in known_words}
    return [w for w in wanted if w.lower() not in known]
