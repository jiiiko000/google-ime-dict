import http.server
import json
import sys
import tempfile
import threading
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


if __name__ == "__main__":
    unittest.main()
