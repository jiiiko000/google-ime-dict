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
