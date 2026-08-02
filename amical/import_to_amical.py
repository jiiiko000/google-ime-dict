#!/usr/bin/env python3
"""Google日本語入力用の辞書(*.txt)を Amical の語彙DBに取り込む。

Amical の語彙には「読み・品詞」の概念がないため、次の方針で変換する:

- 品詞=固有名詞のみ対象(日本語の一般用語は Whisper がほぼ正しく書き起こすため)
- 基本は置換モード: 読みをカタカナ化したものをトリガーに、表記へ置換する
  (例: くばねてす → トリガー「クバネテス」、置換先「Kubernetes」)
- Amical の置換はCJKに対して単語境界なしの部分文字列置換なので、
  日本語の一般語と衝突する読みは EXCLUDE_READINGS で除外し、
  表記のみをヒントモード(AIプロンプトへの注入)で登録する

使い方:
    python3 amical/import_to_amical.py --dry-run   # 投入内容の確認のみ
    python3 amical/import_to_amical.py             # 実際にDBへ投入(要 Amical 終了)
"""

import argparse
import shutil
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
DB_PATH = (
    Path.home() / "Library" / "Application Support" / "Amical" / "amical.db"
)

# 置換トリガーにすると日本語の一般語を壊す読み(部分文字列置換のため)。
# これらの表記はヒントモードで登録する。
EXCLUDE_READINGS = {
    "ごー",        # ゴール → Goル
    "ばん",        # バンド → Bunド
    "ぼっくす",    # サンドボックス → サンドBox
    "びゅー",      # レビュー → レVue
    "びーと",      # ビート(音楽)
    "びーてすと",  # エービーテスト → エーVitest
    "じぇすと",    # ダイジェスト → ダイJest
    "らむだ",      # ラムダ式 → Lambda式
    "らま",        # パノラマ → パノLlama
    "えさ",        # エサ(餌)
    "じら",        # ゴジラ → ゴJira
    "みろ",        # ミロのヴィーナス
    "そら",        # ソラナ → Soraナ
    "べお",        # ベオグラード → Veoグラード
    "ずーむ",      # ズームイン/ズームレンズ
    "らすと",      # イラスト → イRust
    "るびー",      # ルビー(宝石)
    "おくた",      # オクターブ → Oktaーブ
    "あさな",      # アサナ(ヨガ)
    "れんだー",    # カレンダー → カRender
    "おーろら",    # オーロラ(極光)
    "しゃーぷ",    # シャープ(一般語・社名)
    "のーど",      # ノード(グラフのnode)
    "ぱっかー",    # バックパッカー → バックPacker
    "くえん",      # クエン酸 → Qwen酸
    "かーそる",    # カーソル(一般語)
    "りみっくす",  # リミックス(音楽)
    "くろま",      # クロマキー → Chromaキー
    "すとらいぷ",  # ストライプ(柄)
    "らんうぇい",  # ランウェイ(ファッション)
    "ばっくろぐ",  # バックログ(アジャイル一般語)
    "ぐろっく",    # Grok/Groq でトリガー重複、かつグロック(銃)
    "はいく",      # ハイク/俳句
    "そねっと",    # ソネット(詩)
    "おーぱす",    # オーパス(音楽)
}


def hira_to_kata(s: str) -> str:
    return "".join(
        chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s
    )


def load_entries():
    """全 *.txt から固有名詞の (読み, 表記) を読み込む。"""
    entries = []
    seen = set()
    for txt in sorted(REPO_DIR.glob("*.txt")):
        for line in txt.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) != 3:
                print(f"warning: 列数が3でない行をスキップ: {txt.name}: {line!r}")
                continue
            reading, word, pos = (c.strip() for c in cols)
            if pos != "固有名詞":
                continue
            if (reading, word) in seen:
                continue
            seen.add((reading, word))
            entries.append((reading, word))
    return entries


def build_rows(entries):
    """(word, replacement_word, is_replacement) の行リストを作る。"""
    replacements = []   # (トリガー=カタカナ読み, 表記)
    replaced_words = set()
    excluded = []
    for reading, word in entries:
        if reading in EXCLUDE_READINGS:
            excluded.append((reading, word))
        else:
            replacements.append((hira_to_kata(reading), word))
            replaced_words.add(word)

    # 除外された語のうち、別の読みで置換登録済みの表記はヒント不要
    hints = sorted({w for _, w in excluded if w not in replaced_words})

    rows = [(trigger, word, 1) for trigger, word in replacements]
    rows += [(word, None, 0) for word in hints]
    return rows, excluded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="DBに書き込まず投入内容を表示する")
    parser.add_argument("--db", type=Path, default=DB_PATH,
                        help=f"amical.db のパス (default: {DB_PATH})")
    args = parser.parse_args()

    entries = load_entries()
    rows, excluded = build_rows(entries)
    n_repl = sum(1 for r in rows if r[2] == 1)
    n_hint = len(rows) - n_repl

    print(f"固有名詞: {len(entries)}語 → 置換 {n_repl}件 / ヒント {n_hint}件")

    if args.dry_run:
        print("\n--- 置換モード (トリガー → 表記) ---")
        for trigger, word, is_repl in rows:
            if is_repl:
                print(f"  {trigger} → {word}")
        print("\n--- ヒントモード ---")
        for word, _, is_repl in rows:
            if not is_repl:
                print(f"  {word}")
        return

    if not args.db.exists():
        sys.exit(f"error: DBが見つかりません: {args.db}")

    if subprocess.run(["pgrep", "-x", "Amical"], capture_output=True).returncode == 0:
        sys.exit("error: Amical が起動中です。終了してから実行してください。")

    backup = args.db.with_name(f"amical.db.bak-{date.today().isoformat()}")
    shutil.copy2(args.db, backup)
    print(f"バックアップ: {backup}")

    con = sqlite3.connect(args.db)
    try:
        before = con.execute("select count(*) from vocabulary").fetchone()[0]
        con.executemany(
            "insert or ignore into vocabulary"
            " (word, replacement_word, is_replacement) values (?, ?, ?)",
            rows,
        )
        con.commit()
        after = con.execute("select count(*) from vocabulary").fetchone()[0]
    finally:
        con.close()

    print(f"投入完了: {after - before}件 追加 (既存と重複した {len(rows) - (after - before)}件はスキップ)")
    print(f"vocabulary 合計: {after}件。Amical を起動して Settings > Dictionary で確認してください。")


if __name__ == "__main__":
    main()
