"""dict/ 配下のGoogle日本語入力用辞書を読み込む共通モジュール。

Amical / OpenWhispr など、取り込み先のアプリごとのスクリプトが共有する。
「UTF-8 / タブ区切り / 3列固定」「固有名詞だけを取り込む」という不変条件を
ここ1箇所に閉じ込めるのが目的。
"""

from pathlib import Path

DICT_DIR = Path(__file__).resolve().parents[2] / "dict"


def load_entries(dict_dir=None):
    """dict/ 配下の *_terms.txt から固有名詞の (読み, 単語) を読み込む。

    戻り値は (読み, 単語) のリスト。品詞が「固有名詞」の行だけを対象にし、
    ファイル順(パスのソート順)→行順を保つ。(読み, 単語) が重複する行は
    最初の1件だけを残す。列数が3でない行は警告してスキップする。

    dict_dir を省略するとリポジトリ直下の dict/ を読む。
    """
    base = Path(dict_dir) if dict_dir else DICT_DIR
    entries = []
    seen = set()
    for txt in sorted(base.rglob("*_terms.txt")):
        for line in txt.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) != 3:
                rel = txt.relative_to(base)
                print(f"warning: 列数が3でない行をスキップ: {rel}: {line!r}")
                continue
            reading, word, pos = (c.strip() for c in cols)
            if pos != "固有名詞":
                continue
            if (reading, word) in seen:
                continue
            seen.add((reading, word))
            entries.append((reading, word))
    return entries
