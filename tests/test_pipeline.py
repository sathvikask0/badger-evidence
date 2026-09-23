import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from badger_evidence.evaluation import evaluate
from badger_evidence.pipeline import DATA, build_dataset, csv_export, filter_records


class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = build_dataset()

    def test_ten_real_papers_with_source_linked_records(self):
        dataset = self.dataset
        self.assertEqual(len(dataset["articles"]), 10)
        self.assertEqual({a["pmcid"] for a in dataset["articles"]}, {r["pmcid"] for r in dataset["records"]})
        self.assertGreater(len(dataset["records"]), 100)
        self.assertEqual(len({r["id"] for r in dataset["records"]}), len(dataset["records"]))
        for r in dataset["records"]:
            self.assertEqual(r["review_status"], "unreviewed")
            self.assertEqual(len(r["source_sha256"]), 64)
            self.assertEqual(r["raw_value"], r["evidence"]["row"][r["target_column"]])
            self.assertIn(r["table_id"], r["source_url"])

    def test_build_is_reproducible(self):
        self.assertEqual(self.dataset, build_dataset())

    def test_scoped_regression_reference_has_no_wrong_or_missed_measurements(self):
        gold = json.loads((DATA / "gold" / "annotations.json").read_text())
        report = evaluate(self.dataset["records"], gold)
        self.assertGreaterEqual(report["expected"], 50)
        self.assertEqual(report["false_positives"], 0, report)
        self.assertEqual(report["false_negatives"], 0, report)
        self.assertEqual(report["correct_missing_value_abstentions"], report["expected_missing_values"])
        self.assertEqual(report["unreported_missing_values"], 0)
        self.assertEqual(report["unexpected_abstentions"], 0)
        self.assertEqual(report["fabricated_missing_values"], 0)

    def test_modified_source_fails_integrity_check(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            first = json.loads((DATA / "manifest.json").read_text())[0]
            (directory / "manifest.json").write_text(json.dumps([first]))
            (directory / "source").mkdir()
            (directory / "source" / first["filename"]).write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "checksum"):
                build_dataset(directory)

    def test_duplicate_articles_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            first = json.loads((DATA / "manifest.json").read_text())[0]
            (directory / "manifest.json").write_text(json.dumps([first, first]))
            (directory / "source").mkdir()
            (directory / "source" / first["filename"]).write_bytes((DATA / "source" / first["filename"]).read_bytes())
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                build_dataset(directory)

    def test_filter_and_csv_round_trip_keep_provenance(self):
        selected = filter_records(self.dataset["records"], pmcid="PMC8910009", measurement="Ki")
        rows = list(csv.DictReader(io.StringIO(csv_export(selected))))
        self.assertEqual(len(rows), 16)
        self.assertEqual(rows[0]["compound_label"], "2a")
        self.assertEqual(rows[0]["value"], "5.9")
        self.assertEqual(rows[0]["relation"], "=")
        self.assertIn("ijms-23-02540-t002", rows[0]["source_url"])

    def test_csv_formula_injection_is_neutralized(self):
        record = {**self.dataset["records"][0], "compound_label": '=HYPERLINK("https://example.com")'}
        row = next(csv.DictReader(io.StringIO(csv_export([record]))))
        self.assertTrue(row["compound_label"].startswith("'="))


if __name__ == "__main__":
    unittest.main()
