import unittest

from badger_evidence.extract import extract_article, parse_value


def article(table):
    return f'''<article><front><article-meta><article-id pub-id-type="pmc">123</article-id>
      <title-group><article-title>Fixture study</article-title></title-group></article-meta></front>
      <body><table-wrap id="T1"><label>Table 1</label><caption>Human carbonic anhydrase inhibition</caption>
      <table>{table}</table></table-wrap></body></article>'''.encode()


class MeasurementTests(unittest.TestCase):
    def test_micromolar_value_and_uncertainty(self):
        result = parse_value("0.025 ± 0.002", "µM")
        self.assertEqual(result["normalized_value_nm"], 25)
        self.assertEqual(result["uncertainty"], 0.002)

    def test_bound_is_not_an_exact_measurement(self):
        result = parse_value(">100\u2009000", "nM")
        self.assertEqual(result["value"], 100000)
        self.assertEqual(result["relation"], ">")
        self.assertIn("qualified_value", result["flags"])

    def test_missing_value_is_never_zero(self):
        result = parse_value("NA", "µM")
        self.assertIsNone(result["value"])
        self.assertIn("missing_value", result["flags"])

    def test_missing_unit_does_not_default_to_nm(self):
        result = parse_value("23", None)
        self.assertEqual(result["value"], 23)
        self.assertIsNone(result["normalized_value_nm"])
        self.assertIn("missing_unit", result["flags"])

    def test_selectivity_ratio_abstains_instead_of_becoming_potency(self):
        result = parse_value("41.2 [85.8]", "µM")
        self.assertIsNone(result["value"])
        self.assertEqual(result["raw_value"], "41.2 [85.8]")

    def test_explicit_cell_unit_is_preserved(self):
        result = parse_value("2 µM", "nM")
        self.assertEqual(result["normalized_value_nm"], 2000)
        self.assertIn("cell_unit_overrides_header", result["flags"])

    def test_range_and_negative_value_are_not_silently_reduced(self):
        for value in ("2–4", "-3", "4 or 9", "1e999"):
            self.assertIsNone(parse_value(value, "nM")["value"])


class TableTests(unittest.TestCase):
    def test_merged_headers_keep_target_column_and_endpoint(self):
        data = article('''<thead><tr><th rowspan="2">Compound</th><th colspan="3">K<sub>i</sub> (nM)</th></tr>
        <tr><th>hCA I</th><th>hCA II</th><th>hCA XII</th></tr></thead>
        <tbody><tr><td>1a</td><td>999</td><td>12.1<sup>a</sup></td><td>456</td></tr></tbody>''')
        records = extract_article(data)["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["value"], 12.1)
        self.assertEqual(records[0]["measurement_type"], "Ki")
        self.assertEqual(records[0]["evidence"]["row"][2], "12.1")

    def test_bovine_and_percent_inhibition_excluded(self):
        data = article('''<thead><tr><th rowspan="2">Compounds</th>
        <th>Bovine carbonic anhydrase-II (bCA-II)</th><th colspan="2">Human carbonic anhydrase-II (hCA-II)</th></tr>
        <tr><th>IC50 (µM)</th><th>% inhibition (0.5 mM)</th><th>IC50 (µM)</th></tr></thead>
        <tbody><tr><td>4a</td><td>53.6</td><td>75.2</td><td>59.6</td></tr></tbody>''')
        records = extract_article(data)["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["value"], 59.6)
        self.assertEqual(records[0]["measurement_type"], "IC50")
        self.assertEqual(records[0]["normalized_value_nm"], 59600)

    def test_repeated_side_by_side_blocks_use_correct_compound(self):
        data = article('''<thead><tr><th>N</th><th>hCA II Ki (nM)</th><th>N</th><th>hCA II Ki (nM)</th></tr></thead>
        <tbody><tr><td>5a</td><td>35.1</td><td>6b</td><td>81.7</td></tr></tbody>''')
        records = extract_article(data)["records"]
        self.assertEqual([(r["compound_label"], r["value"]) for r in records], [("5a", 35.1), ("6b", 81.7)])
        self.assertTrue(all(r["measurement_type"] == "Ki" for r in records))
        self.assertNotEqual(records[0]["id"], records[1]["id"])

    def test_isoforms_and_ratio_columns_do_not_match_ca2(self):
        data = article('''<thead><tr><th>Compound</th><th>hCA III Ki (nM)</th><th>hCA II/hCA IX</th></tr></thead>
        <tbody><tr><td>1a</td><td>12</td><td>3</td></tr></tbody>''')
        self.assertEqual(extract_article(data)["records"], [])

    def test_identical_labels_in_other_papers_have_distinct_identities(self):
        raw = article('''<thead><tr><th>Compound</th><th>hCA II Ki (nM)</th></tr></thead>
        <tbody><tr><td>1</td><td>12</td></tr></tbody>''')
        first = extract_article(raw)["records"][0]
        second = extract_article(raw.replace(b">123<", b">124<"))["records"][0]
        self.assertNotEqual(first["compound_id"], second["compound_id"])

    def test_irregular_rows_are_reported_not_shifted(self):
        data = article('''<thead><tr><th>Compound</th><th>hCA I Ki (nM)</th><th>hCA II Ki (nM)</th></tr></thead>
        <tbody><tr><td>1</td><td>12</td></tr></tbody>''')
        result = extract_article(data)
        self.assertEqual(result["records"], [])
        self.assertEqual(result["skipped"][0]["reason"], "irregular_row_width")

    def test_sources_must_match_manifest(self):
        with self.assertRaises(ValueError):
            extract_article(article(""), {"pmcid": "PMC999"})

    def test_original_footnote_markers_are_preserved_as_evidence(self):
        raw = article('''<thead><tr><th>Compound</th><th>hCA II Ki (nM)</th></tr></thead>
        <tbody><tr><td>1<xref ref-type="table-fn">c</xref></td><td>12<sup>a</sup></td></tr></tbody>''')
        record = extract_article(raw)["records"][0]
        self.assertEqual(record["compound_label"], "1")
        self.assertEqual(record["value"], 12)
        self.assertEqual(record["evidence"]["original_row"], ["1c", "12a"])

    def test_repeated_controls_are_flagged_without_losing_provenance(self):
        raw = article('''<thead><tr><th>N</th><th>hCA II Ki (nM)</th><th>N</th><th>hCA II Ki (nM)</th></tr></thead>
        <tbody><tr><td>AAZ</td><td>12.1</td><td>AAZ</td><td>12.1</td></tr></tbody>''')
        records = extract_article(raw)["records"]
        self.assertEqual(len(records), 2)
        self.assertTrue(all("repeated_measurement" in record["flags"] for record in records))

    def test_entity_declarations_rejected(self):
        with self.assertRaises(ValueError):
            extract_article(b'<!DOCTYPE article [<!ENTITY x "oops">]><article/>')


if __name__ == "__main__":
    unittest.main()
