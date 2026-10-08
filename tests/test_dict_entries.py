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
