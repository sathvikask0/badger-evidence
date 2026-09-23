"""Regression tests for trustworthy scoped extraction metrics."""

from copy import deepcopy
import unittest

from badger_evidence.evaluation import evaluate


def record(**changes):
    result = {
        "pmcid": "PMC123",
        "table_id": "T1",
        "compound_label": "1a",
        "measurement_type": "Ki",
        "value": 1000.0,
        "unit": "nM",
        "relation": "=",
    }
    result.update(changes)
    return result


def benchmark(*records):
    return {
        "records": list(records) or [record()],
        "scoped_tables": [{"pmcid": "PMC123", "table_id": "T1"}],
        "annotation_method": "Agent-transcribed public table, manually checked by agent",
    }


class EvaluationTests(unittest.TestCase):
    def test_exact_match_and_honest_label(self):
        result = evaluate([record()], benchmark())
        for field in ("precision", "recall", "f1"):
            self.assertEqual(result[field], 1.0)
        self.assertEqual(result["true_positives"], 1)
        self.assertIn("Agent-transcribed", result["benchmark_label"])
        self.assertFalse(result["independently_scientist_validated"])
        self.assertEqual(result["missing_records"], [])
        self.assertEqual(result["extra_records"], [])

    def test_concentration_units_are_exactly_normalized(self):
        for value, unit in [(1, "µM"), (1, "μM"), (1, "uM"), (0.001, "mM"), (0.000001, "M")]:
            with self.subTest(unit=unit):
                result = evaluate([record(value=value, unit=unit)], benchmark())
                self.assertEqual(result["true_positives"], 1)

    def test_wrong_unit_is_a_mismatch(self):
        result = evaluate([record(unit="µM")], benchmark())
        self.assertEqual(result["true_positives"], 0)
        self.assertEqual(result["false_positives"], 1)
        self.assertEqual(result["false_negatives"], 1)

    def test_no_tolerance_invents_equivalence(self):
        result = evaluate([record(value=999.999999)], benchmark())
        self.assertEqual(result["true_positives"], 0)

    def test_hallucinated_record_reduces_precision(self):
        result = evaluate([record(), record(compound_label="invented")], benchmark())
        self.assertEqual(result["precision"], 0.5)
        self.assertEqual(result["recall"], 1.0)
        self.assertAlmostEqual(result["f1"], 2 / 3)
        self.assertEqual(result["extra_records"][0]["compound_label"], "invented")

    def test_missing_record_reduces_recall(self):
        result = evaluate([record()], benchmark(record(), record(compound_label="2b")))
        self.assertEqual(result["precision"], 1.0)
        self.assertEqual(result["recall"], 0.5)
        self.assertEqual(result["missing_records"][0]["compound_label"], "2b")

    def test_inequalities_remain_distinct(self):
        for relation in ["<", ">", "<=", ">="]:
            with self.subTest(relation=relation):
                result = evaluate([record(relation=relation)], benchmark())
                self.assertEqual(result["true_positives"], 0)
        result = evaluate([record(relation=">", value=1, unit="µM")], benchmark(record(relation=">")))
        self.assertEqual(result["true_positives"], 1)
        result = evaluate([record(relation=">")], benchmark(record(relation=">=")))
        self.assertEqual(result["true_positives"], 0)

    def test_wrong_endpoint_never_matches(self):
        result = evaluate([record(measurement_type="IC50")], benchmark())
        self.assertEqual(result["true_positives"], 0)
        self.assertEqual(result["false_positives"], 1)
        self.assertEqual(result["false_negatives"], 1)

    def test_duplicate_prediction_cannot_inflate_recall(self):
        result = evaluate([record(), record(), record()], benchmark())
        self.assertEqual(result["true_positives"], 1)
        self.assertEqual(result["false_positives"], 2)
        self.assertEqual(result["recall"], 1.0)
        self.assertEqual(len(result["extra_records"]), 2)

    def test_duplicate_gold_requires_duplicate_predictions(self):
        result = evaluate([record()], benchmark(record(), record()))
        self.assertEqual(result["expected"], 2)
        self.assertEqual(result["true_positives"], 1)
        self.assertEqual(result["false_negatives"], 1)
        self.assertEqual(result["recall"], 0.5)

    def test_unscoped_tables_do_not_affect_metrics(self):
        result = evaluate([
            record(),
            record(table_id="T2", measurement_type="unannotated"),
            record(pmcid="PMC456"),
        ], benchmark())
        self.assertEqual(result["predicted"], 1)
        self.assertEqual(result["ignored_unscoped_records"], 2)
        self.assertEqual(result["precision"], 1.0)

    def test_wrong_target_does_not_match(self):
        result = evaluate([record(target="CA1")], benchmark())
        self.assertEqual(result["true_positives"], 0)
        self.assertEqual(result["false_positives"], 1)
        result = evaluate([record(target="CA2")], benchmark())
        self.assertEqual(result["true_positives"], 1)

    def test_empty_predictions_score_zero(self):
        result = evaluate([], benchmark())
        self.assertEqual(result["precision"], 0)
        self.assertEqual(result["recall"], 0)
        self.assertEqual(result["f1"], 0)
        self.assertEqual(result["false_negatives"], 1)

    def test_empty_gold_is_invalid(self):
        for gold in [{}, {"records": [], "scoped_tables": [{"pmcid": "PMC123", "table_id": "T1"}]}]:
            with self.subTest(gold=gold), self.assertRaises(ValueError):
                evaluate([], gold)

    def test_invalid_gold_scope_is_rejected(self):
        for changes in [{"scoped_tables": []}, {"records": [record(table_id="T2")]}, {"records": [record(target="CA1")]}]:
            gold = benchmark()
            gold.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                evaluate([], gold)

    def test_malformed_values_raise_instead_of_silently_disappearing(self):
        for changes in [
            {"value": float("nan")}, {"value": float("inf")}, {"value": True},
            {"value": "1000"}, {"unit": "mg/mL"}, {"relation": "approximately"},
            {"measurement_type": "Kd"}, {"compound_label": ""}, {"target": None},
        ]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                evaluate([record(**changes)], benchmark())

    def test_missing_required_field_raises(self):
        for field in record():
            prediction = record()
            del prediction[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                evaluate([prediction], benchmark())

    def test_wrong_container_types_raise_clear_errors(self):
        for predictions, gold in [(None, benchmark()), ([], None), ([None], benchmark())]:
            with self.subTest(predictions=predictions, gold=gold), self.assertRaises(ValueError):
                evaluate(predictions, gold)

    def test_null_matches_are_disclosed_and_not_numeric(self):
        missing = record(compound_label="NA-row", value=None, relation=None)
        gold = benchmark()
        gold["expected_missing"] = [{
            "pmcid": "PMC123", "table_id": "T1", "compound_label": "NA-row",
            "measurement_type": "Ki", "source_value": "NA",
        }]
        result = evaluate([record(), missing], gold)
        self.assertEqual(result["true_positives"], 1)
        self.assertEqual(result["predicted"], 1)
        self.assertEqual(result["expected"], 1)
        self.assertEqual(result["null_value_matches"], 1)
        self.assertEqual(result["expected_missing_values"], 1)
        self.assertEqual(result["correct_missing_value_abstentions"], 1)
        self.assertEqual(result["false_positives"], 0)
        self.assertEqual(result["precision"], 1)

    def test_fabricated_missing_value_is_false_positive(self):
        gold = benchmark(record(), record(compound_label="NA-row", value=None))
        result = evaluate([record(), record(compound_label="NA-row", value=0)], gold)
        self.assertEqual(result["true_positives"], 1)
        self.assertEqual(result["false_positives"], 1)
        self.assertEqual(result["fabricated_missing_values"], 1)
        self.assertEqual(result["precision"], 0.5)

    def test_abstaining_on_real_number_still_misses_record(self):
        result = evaluate([record(value=None, relation=None)], benchmark())
        self.assertEqual(result["true_positives"], 0)
        self.assertEqual(result["predicted"], 0)
        self.assertEqual(result["false_negatives"], 1)
        self.assertEqual(result["unexpected_abstentions"], 1)

    def test_duplicate_abstentions_do_not_inflate_missing_matches(self):
        missing = record(compound_label="NA-row", value=None, relation=None)
        gold = benchmark(record(), missing)
        result = evaluate([record(), missing, missing], gold)
        self.assertEqual(result["correct_missing_value_abstentions"], 1)
        self.assertEqual(result["unexpected_abstentions"], 1)
        self.assertEqual(result["false_positives"], 0)

    def test_null_only_gold_cannot_claim_numeric_accuracy(self):
        with self.assertRaises(ValueError):
            evaluate([record(value=None)], benchmark(record(value=None)))

    def test_contradictory_gold_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([], benchmark(record(), record(value=None)))

    def test_unreported_missing_cell_is_visible_separately(self):
        gold = benchmark(record(), record(compound_label="NA-row", value=None))
        result = evaluate([record()], gold)
        self.assertEqual(result["precision"], 1)
        self.assertEqual(result["recall"], 1)
        self.assertEqual(result["unreported_missing_values"], 1)

    def test_inputs_are_not_mutated(self):
        predictions = [record(compound_label="extra")]
        gold = benchmark()
        before = deepcopy((predictions, gold))
        result = evaluate(predictions, gold)
        self.assertEqual((predictions, gold), before)
        result["missing_records"][0]["value"] = 42
        self.assertEqual(gold["records"][0]["value"], 1000.0)


if __name__ == "__main__":
    unittest.main()
