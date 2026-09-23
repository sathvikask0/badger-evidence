import csv
import io
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from badger_evidence.pipeline import build_dataset
from badger_evidence.server import make_server


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(build_dataset(), port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_browser_and_data_are_served(self):
        with urlopen(self.url + "/") as response:
            self.assertIn(b"Badger", response.read())
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        with urlopen(self.url + "/api/dataset") as response:
            self.assertEqual(len(json.load(response)["articles"]), 10)

    def test_export_respects_filters(self):
        with urlopen(self.url + "/api/export.csv?pmcid=PMC8910009&measurement=Ki&q=2a") as response:
            rows = list(csv.DictReader(io.StringIO(response.read().decode("utf-8-sig"))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["value"], "5.9")

    def test_evaluation_endpoint(self):
        with urlopen(self.url + "/api/evaluation") as response:
            self.assertGreaterEqual(json.load(response)["expected"], 50)

    def test_source_can_be_downloaded(self):
        with urlopen(self.url + "/api/source/PMC8910009.xml") as response:
            self.assertIn(b"<article", response.read())
            self.assertIn("attachment", response.headers["Content-Disposition"])

    def test_unlisted_sources_and_traversal_are_rejected(self):
        for path in ("/api/source/PMC0.xml", "/../data/manifest.json", "/.git/config", "/api/source/../../README.md"):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.url + path)
            self.assertEqual(error.exception.code, 404)
            error.exception.close()


if __name__ == "__main__":
    unittest.main()
